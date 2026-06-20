"""Cliente da API de Clientes da Bizzu (Partner) — somente leitura (GET).

A "API de dados de usuários" da Bizzu (`docs/analise-bizzu/api-clientes-partner.md`).
Serve para CLASSIFICAR e PRIORIZAR contatos por perfil — nunca para disparar
mensagem. Endpoints usados:

  GET /partner/customers?page=&pageSize=&search=  -> {items[], total, page, pageSize}
  GET /partner/customers/by-email?email=          -> 1 PartnerCustomer (404 se não cliente)

Auth: header `X-API-Key` (segredo `BIZZU_PARTNER_API_KEY`). Lê o env do MESMO jeito
que o resto do repo (os.getenv com default), espelhando `app/config.py` e os scripts.

Privacidade (LGPD): este módulo carrega PII (nome, e-mail, whatsapp). NUNCA loga a
chave nem PII completa — só contagens, página e ids opacos. Ver regras na doc §2.

TLS: usa httpx (mesma lib do resto do repo). O fix de TLS é `truststore.inject_into_ssl()`,
global por processo — já roda em `app/main.py` (app FastAPI) e no topo dos scripts
standalone. Por isso este módulo NÃO chama inject_into_ssl() nem passa verify=.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# Lidas do ambiente no mesmo padrão os.getenv(default) do repo (config.py / scripts).
BIZZU_PARTNER_API_URL = os.getenv("BIZZU_PARTNER_API_URL", "https://api.bizzu.ai")
BIZZU_PARTNER_API_KEY = os.getenv("BIZZU_PARTNER_API_KEY")

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500  # limite da API (doc §1)

# Retry da paginação: tenta de novo em falhas TRANSITÓRIAS (502/503/504/429/rede/timeout)
# para não truncar o sync silenciosamente quando uma página falha pontualmente.
DEFAULT_MAX_RETRIES = 4  # = 1 tentativa + 3 retries
RETRY_BACKOFF_BASE_SECONDS = 0.5  # backoff exponencial: 0.5s, 1s, 2s, ...
# Status HTTP considerados transitórios (vale a pena re-tentar).
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class BizzuPartnerError(RuntimeError):
    """Erro de chamada à API de Clientes da Bizzu (rede/HTTP)."""


class BizzuPartnerAuthError(BizzuPartnerError):
    """401 — chave ausente/ inválida (X-API-Key)."""


class BizzuPartnerRetryableError(BizzuPartnerError):
    """Erro TRANSITÓRIO (502/503/504/429/rede/timeout) — vale re-tentar a página."""


class BizzuPartnerClient:
    """Cliente fino da API de Clientes (Partner) da Bizzu.

    Instância barata; abre um httpx.AsyncClient efêmero por chamada (padrão do repo,
    ver GroqLLM/WAHAService). Não guarda estado entre requests.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        # Default vem do env (mesmo padrão do repo); argumentos permitem override em teste.
        self.base_url = (base_url or BIZZU_PARTNER_API_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else BIZZU_PARTNER_API_KEY
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            # Não há chave -> 401 garantido; falha cedo e claro (sem vazar nada).
            raise BizzuPartnerAuthError(
                "BIZZU_PARTNER_API_KEY ausente — peça a chave ao Felipe e ponha no .env."
            )
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET com tratamento de 401/404; nunca loga chave nem PII."""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=self._headers())
        except httpx.HTTPError as exc:  # rede/timeout -> transitório (vale re-tentar)
            logger.warning("BizzuPartner: falha de rede em GET %s (%s)", path, type(exc).__name__)
            raise BizzuPartnerRetryableError(f"falha de rede em GET {path}") from exc

        if resp.status_code == 401:
            logger.warning("BizzuPartner: 401 em GET %s (chave inválida/ausente)", path)
            raise BizzuPartnerAuthError(f"401 em GET {path} — X-API-Key inválida")
        if resp.status_code == 404:
            # 404 é semântico (by-email de não-cliente); deixa o chamador decidir.
            logger.info("BizzuPartner: 404 em GET %s", path)
            raise BizzuPartnerError(f"404 em GET {path}")
        if resp.status_code in RETRYABLE_STATUS:
            # 5xx/429: instabilidade momentânea da API -> transitório (vale re-tentar).
            logger.warning("BizzuPartner: HTTP %s (transitório) em GET %s", resp.status_code, path)
            raise BizzuPartnerRetryableError(f"HTTP {resp.status_code} em GET {path}")
        if resp.status_code >= 400:
            logger.warning("BizzuPartner: HTTP %s em GET %s", resp.status_code, path)
            raise BizzuPartnerError(f"HTTP {resp.status_code} em GET {path}")

        try:
            return resp.json()
        except ValueError as exc:
            raise BizzuPartnerError(f"resposta não-JSON em GET {path}") from exc

    async def list_customers(
        self, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, search: str = ""
    ) -> dict[str, Any]:
        """Uma página de clientes. Retorna {items[], total, page, pageSize}."""
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["search"] = search
        data = await self._get("/partner/customers", params=params)
        if not isinstance(data, dict):
            raise BizzuPartnerError("/partner/customers: payload inesperado (esperava objeto)")
        # Loga só contagens/página — nunca PII.
        items = data.get("items") or []
        logger.info(
            "BizzuPartner: page=%s pageSize=%s items=%s total=%s",
            data.get("page", page),
            data.get("pageSize", page_size),
            len(items),
            data.get("total"),
        )
        return data

    async def _list_customers_with_retry(
        self, page: int, page_size: int, search: str, max_retries: int
    ) -> dict[str, Any]:
        """`list_customers` com retry+backoff em erro TRANSITÓRIO (502/503/504/429/rede/timeout).

        Re-tenta a MESMA página até `max_retries` tentativas (backoff exponencial). 401/404
        e demais 4xx NÃO são re-tentados (não-transitórios). Se esgotar as tentativas,
        propaga o último erro transitório (subclasse de BizzuPartnerError) — assim a
        paginação falha ALTO em vez de truncar silenciosamente.
        """
        attempt = 0
        while True:
            try:
                return await self.list_customers(page=page, page_size=page_size, search=search)
            except BizzuPartnerRetryableError as exc:
                attempt += 1
                if attempt >= max_retries:
                    logger.warning(
                        "BizzuPartner: página %s falhou após %s tentativa(s) (%s) — desistindo",
                        page, attempt, exc,
                    )
                    raise
                delay = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "BizzuPartner: página %s falhou (%s); re-tentando em %.1fs (tentativa %s/%s)",
                    page, exc, delay, attempt + 1, max_retries,
                )
                await asyncio.sleep(delay)

    async def iter_all_customers(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: str = "",
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> AsyncIterator[dict[str, Any]]:
        """Itera TODOS os clientes, paginando até `items` vir vazio.

        Usa `total` como salvaguarda: para também ao já ter rendido >= total
        (evita loop infinito se a API repetir páginas). Rende um PartnerCustomer
        (dict) por vez.

        Cada página é buscada com retry+backoff (`max_retries`) em falhas transitórias
        (502/503/504/429/rede/timeout) — uma página instável é re-tentada em vez de
        truncar o sync sem aviso. Erros não-transitórios (401/404/outros 4xx) e a
        falha após esgotar as tentativas propagam normalmente.
        """
        page = 1
        seen = 0
        total: int | None = None
        while True:
            data = await self._list_customers_with_retry(
                page=page, page_size=page_size, search=search, max_retries=max_retries
            )
            items = data.get("items") or []
            if total is None:
                t = data.get("total")
                total = int(t) if isinstance(t, (int, float)) else None
            if not items:
                break
            for item in items:
                yield item
                seen += 1
            if total is not None and seen >= total:
                break
            page += 1

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Busca 1 cliente por e-mail. Retorna o PartnerCustomer ou None (404)."""
        try:
            data = await self._get("/partner/customers/by-email", params={"email": email})
        except BizzuPartnerAuthError:
            raise
        except BizzuPartnerError as exc:
            if "404" in str(exc):
                # Não é cliente (ou nunca pagou) — semântica de "não encontrado".
                return None
            raise
        return data if isinstance(data, dict) else None
