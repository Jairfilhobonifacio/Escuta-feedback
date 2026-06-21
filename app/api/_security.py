"""Dependências de autenticação compartilhadas das portas do Escuta.

Mesma filosofia do `require_api_key` da API de integração (app/api/integration.py),
mas com um detalhe deliberado para NÃO quebrar o piloto que ainda não configurou
segredos: aqui o default é **fail-open quando NÃO configurado** (libera + WARN),
e **fail-closed quando configurado** (exige o header, 401 sem/errado). Em produção
é OBRIGATÓRIO setar os segredos (PANEL_API_KEY / WAHA_WEBHOOK_SECRET) para a trava
valer — sem eles a porta fica aberta e só registra um aviso no log.

A comparação é sempre constante no tempo (`hmac.compare_digest`) e a chave NUNCA é
logada (nem a recebida nem a esperada).
"""
from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


async def require_panel_key(x_panel_key: str | None = Header(default=None)) -> None:
    """Auth do painel interno (admin/whatsapp/campanha/boards/tasks/playbooks/...).

    - settings.panel_api_key None/"" -> LIBERA + logger.warning (piloto sem trava).
      ⚠️ EM PRODUÇÃO É OBRIGATÓRIO SETAR `PANEL_API_KEY` — sem ela a porta fica aberta.
    - configurada + header X-Panel-Key ausente/errado -> 401 (fail-closed).
      Comparação constante no tempo via hmac.compare_digest; a chave nunca é logada.
    """
    expected = settings.panel_api_key
    if not expected:
        # C1: em produção, segredo ausente é fail-CLOSED (503) — a porta NÃO fica
        # aberta. Em dev, mantém o fail-OPEN histórico (libera + WARN) p/ o piloto/suíte.
        if settings.app_env == "production":
            raise HTTPException(status_code=503, detail="PANEL_API_KEY não configurada (produção)")
        logger.warning(
            "painel SEM autenticação (defina PANEL_API_KEY para travar /api/* do painel)"
        )
        return
    if not hmac.compare_digest(x_panel_key or "", expected):
        raise HTTPException(status_code=401, detail="X-Panel-Key ausente ou inválida")


async def require_waha_webhook_secret(
    x_webhook_secret: str | None = Header(default=None),
) -> None:
    """Auth de ORIGEM do webhook do WAHA (POST /api/webhook/waha).

    - settings.waha_webhook_secret None/"" -> LIBERA + logger.warning (piloto sem trava).
      ⚠️ EM PRODUÇÃO É OBRIGATÓRIO SETAR `WAHA_WEBHOOK_SECRET` para impedir mensagens forjadas.
    - configurada + header X-Webhook-Secret ausente/errado -> 401 (fail-closed).
      Comparação constante no tempo via hmac.compare_digest; o segredo nunca é logado.
    """
    expected = settings.waha_webhook_secret
    if not expected:
        # C1: produção é fail-CLOSED (503); dev mantém fail-OPEN (libera + WARN).
        if settings.app_env == "production":
            raise HTTPException(
                status_code=503, detail="WAHA_WEBHOOK_SECRET não configurado (produção)"
            )
        logger.warning(
            "webhook WAHA SEM autenticação (defina WAHA_WEBHOOK_SECRET para exigir X-Webhook-Secret)"
        )
        return
    if not hmac.compare_digest(x_webhook_secret or "", expected):
        raise HTTPException(status_code=401, detail="X-Webhook-Secret ausente ou inválido")
