"""Exporta os clientes do plano ANUAL ATIVO da Bizzu -> HTML de abordagem no WhatsApp.

Puxa TODOS os clientes pela API de Clientes (Partner) da Bizzu, mantém só os ANUAIS
ATIVOS (assinatura paga, plano anual), classifica cada um por PERFIL e injeta um JSON
no template de UI (docs/campanhas/_abordagem-anuais.template.html), gerando
docs/campanhas/abordagem-anuais.html — a tela que o Jair usa para abordar esses
clientes um a um no WhatsApp.

  NÃO dispara mensagem em nenhum caminho — só LÊ a API e GERA um HTML local.

Modos:
  (real)   py scripts/export_anuais_ativos.py
           Chama a API da Bizzu (precisa BIZZU_PARTNER_API_KEY no .env), filtra os
           anuais ativos e gera o HTML.
  --demo   py scripts/export_anuais_ativos.py --demo
           NÃO toca a API: gera ~8 clientes FICTÍCIOS (whatsapp fake) cobrindo todos
           os perfis/objetivos e injeta no mesmo template. Serve p/ validar a UI sem
           tocar produção nem dados pessoais reais.

Privacidade (LGPD): o HTML gerado contém PII (nome/whatsapp) -> NÃO deve ser commitado
(ver aviso no fim da execução). O stdout NUNCA imprime nome/e-mail/whatsapp — só números
e distribuições. A chave da API nunca aparece na saída.

TLS (CRÍTICO nesta máquina — Avast intercepta TLS): truststore.inject_into_ssl() roda
no TOPO, ANTES de qualquer import de app.* (httpx falha o TLS sem isso).
"""
from __future__ import annotations

# --- Fix TLS ANTES de qualquer import que abra conexão TLS (HTTPS à api.bizzu.ai). ---
# Global por processo — espelha app/main.py e os outros scripts standalone do repo.
import truststore

truststore.inject_into_ssl()

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# --- sys.path: garante que `import app.*` resolva a partir da raiz do projeto. ---
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_env() -> None:
    """Carrega o .env da raiz para os.environ (mesmo padrão de dispatch_by_profile.py).

    setdefault: não sobrescreve o que já vier do ambiente. As chaves relevantes aqui são
    BIZZU_PARTNER_API_URL e BIZZU_PARTNER_API_KEY (lidas pelo BizzuPartnerClient).
    """
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


load_env()

# --- Caminhos do template e do HTML gerado (em docs/campanhas/). ---
_CAMPANHAS_DIR = _PROJECT_ROOT / "docs" / "campanhas"
_TEMPLATE_PATH = _CAMPANHAS_DIR / "_abordagem-anuais.template.html"
_OUTPUT_PATH = _CAMPANHAS_DIR / "abordagem-anuais.html"
# Marcador LITERAL dentro do template que será trocado pela atribuição JS dos dados.
_PLACEHOLDER = "/*__CLIENTES__*/"

# State da assinatura que conta como "ativo pagante" (doc da API / profiles.py).
STATE_ACTIVE_PAYING = "active_paying"
# Limiar (em dias) abaixo do qual o objetivo vira "renovacao".
RENEWAL_WINDOW_DAYS = 30

# Perfis cujo objetivo (quando NÃO está perto de renovar) é "relacionamento" vs "nps".
_PROFILES_RELACIONAMENTO = {
    "ativo_fiel",
    "embaixador",
    "ativo_promotor",
    "ativo_em_risco",
}
_PROFILES_NPS = {
    "ativo_silencioso",
    "ativo_passivo",
    "ativo_recente",
}


def _digits_only(value: str | None) -> str:
    """Só os dígitos de um telefone (igual ao sync_partner_customers)."""
    return re.sub(r"\D", "", value or "")


def _parse_dt(value: Any) -> datetime | None:
    """ISO-8601 (str da API) -> datetime aware; tolera None/valor inválido.

    Mesmo padrão de app/domain/feedback/ingest.py (_parse_dt): troca 'Z' por +00:00.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_date(value: Any) -> str:
    """ISO-8601 -> "DD/MM/AAAA" (PT-BR, para EXIBIÇÃO). "" se ausente/ilegível."""
    dt = _parse_dt(value)
    return dt.date().strftime("%d/%m/%Y") if dt is not None else ""


def _fmt_reais(centavos: Any) -> str:
    """Centavos (int) -> "R$ 1.234,56" (vírgula decimal, ponto de milhar). "" se ausente.

    Ex.: 12000 -> "R$ 120,00"; 1200000 -> "R$ 12.000,00". Sem dependência de locale
    (locale não é confiável cross-OS): formata o agrupamento de milhar à mão.
    """
    if not isinstance(centavos, (int, float)):
        return ""
    inteiro, cents = divmod(int(round(centavos)), 100)
    # Agrupa milhares com ponto: "1234" -> "1.234".
    milhar = f"{inteiro:,}".replace(",", ".")
    return f"R$ {milhar},{cents:02d}"


def _is_anual(plan_type: str | None, plan_name: str | None) -> bool:
    """Heurística TOLERANTE de 'plano anual' (o vocabulário real da API é confirmado nos logs).

    planType (lower) contém anual/annual/year, OU planName (lower) contém 'anual'.
    """
    pt = (plan_type or "").strip().lower()
    pn = (plan_name or "").strip().lower()
    if any(token in pt for token in ("anual", "annual", "year")):
        return True
    return "anual" in pn


def _objetivo_sugerido(perfil: str, dias_para_renovar: int | None) -> str:
    """Objetivo de abordagem: renovação se perto de renovar; senão por perfil.

    - dias_para_renovar != None e <= 30 -> "renovacao"
    - senão: perfis de relacionamento -> "relacionamento"; perfis de NPS -> "nps"
    - qualquer outro perfil -> "relacionamento"
    """
    if dias_para_renovar is not None and dias_para_renovar <= RENEWAL_WINDOW_DAYS:
        return "renovacao"
    if perfil in _PROFILES_NPS:
        return "nps"
    # _PROFILES_RELACIONAMENTO e qualquer outro caem em relacionamento.
    return "relacionamento"


def _build_cliente(customer: dict, classification: dict, today: date) -> dict:
    """Monta o objeto cliente no CONTRATO COMPLETO que a UI espera (nomes exatos).

    Contrato (a UI depende EXATAMENTE destas chaves):
      nome, nome_completo, email, whatsapp, plano, plan_type, estado,
      metodo_pagamento, cadastro_em, assinante_desde, dias_de_casa, meses_de_casa,
      renova_em, dias_para_renovar, ultimo_pagamento, total_pago,
      nps_score, nps_comment, nps_votou, nps_respondido_em,
      perfil, objetivo_sugerido

    Datas de SAÍDA = "DD/MM/AAAA" (PT-BR). dias_de_casa e dias_para_renovar ficam
    INTEIROS (a UI calcula/filtra com eles).
    """
    sub = customer.get("subscription") or {}
    nps = customer.get("nps") or {}

    nome_completo = (customer.get("name") or "").strip()
    # Primeiro token do nome (saudação curta no WhatsApp). Vazio -> string vazia.
    primeiro = nome_completo.split()[0] if nome_completo else ""
    email = (customer.get("email") or "").strip()
    whatsapp = _digits_only(customer.get("whatsapp"))

    plano = sub.get("planName")
    plan_type = sub.get("planType")
    estado = sub.get("state")
    metodo_pagamento = sub.get("paymentMethod") or ""

    days_raw = sub.get("daysAsSubscriber")
    dias_de_casa = int(days_raw) if isinstance(days_raw, (int, float)) else None
    meses_de_casa = round(dias_de_casa / 30) if dias_de_casa is not None else None

    # renova_em: currentPeriodEnd formatado "DD/MM/AAAA" (None se ausente/ilegível).
    renova_dt = _parse_dt(sub.get("currentPeriodEnd"))
    renova_em = renova_dt.date().strftime("%d/%m/%Y") if renova_dt is not None else None
    # dias_para_renovar: (data de renovação - hoje).days INT; None se não houver data.
    dias_para_renovar = (renova_dt.date() - today).days if renova_dt is not None else None

    score_raw = nps.get("score")
    nps_score = int(score_raw) if isinstance(score_raw, (int, float)) else None
    nps_comment = (nps.get("comment") or "").strip()

    perfil = classification["profile"]

    return {
        "nome": primeiro,
        "nome_completo": nome_completo,
        "email": email,
        "whatsapp": whatsapp,
        "plano": plano,
        "plan_type": plan_type,
        "estado": estado,
        "metodo_pagamento": metodo_pagamento,
        "cadastro_em": _fmt_date(customer.get("signedUpAt")),
        "assinante_desde": _fmt_date(sub.get("startedAt")),
        "dias_de_casa": dias_de_casa,
        "meses_de_casa": meses_de_casa,
        "renova_em": renova_em,
        "dias_para_renovar": dias_para_renovar,
        "ultimo_pagamento": _fmt_date(sub.get("lastPaymentAt")),
        "total_pago": _fmt_reais(sub.get("totalPaidCentavos")),
        "nps_score": nps_score,
        "nps_comment": nps_comment,
        "nps_votou": bool(nps.get("voted")),
        "nps_respondido_em": _fmt_date(nps.get("respondedAt")),
        "perfil": perfil,
        "objetivo_sugerido": _objetivo_sugerido(perfil, dias_para_renovar),
    }


def _render_html(clientes: list[dict]) -> str:
    """Lê o template, injeta `window.CLIENTES = <json>;` no marcador e devolve o HTML.

    Erra com mensagem clara se o template não existir (a UI é gerada por OUTRO agente).
    """
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template não encontrado: {_TEMPLATE_PATH}\n"
            "Rode o agente da UI (art-director / design) para gerar "
            "'docs/campanhas/_abordagem-anuais.template.html' ANTES de exportar os dados."
        )
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    if _PLACEHOLDER not in template:
        raise ValueError(
            f"O template {_TEMPLATE_PATH.name} não contém o marcador literal "
            f"'{_PLACEHOLDER}'. A UI precisa desse marcador onde os dados são injetados."
        )
    # ensure_ascii=False: acentos legíveis. O JSON vira atribuição a window.CLIENTES.
    payload = json.dumps(clientes, ensure_ascii=False)
    injection = f"window.CLIENTES = {payload};"
    return template.replace(_PLACEHOLDER, injection)


def _print_resumo(total_bruto: int, clientes: list[dict], plan_types_vistos: set[str]) -> None:
    """Imprime o RESUMO sem PII: contagens + distribuições + caminho do HTML."""
    por_perfil: dict[str, int] = {}
    por_objetivo: dict[str, int] = {}
    for c in clientes:
        por_perfil[c["perfil"]] = por_perfil.get(c["perfil"], 0) + 1
        por_objetivo[c["objetivo_sugerido"]] = por_objetivo.get(c["objetivo_sugerido"], 0) + 1

    print("=== RESUMO (sem PII) ===")
    print(f"  Total bruto da API ....... {total_bruto}")
    print(f"  Anuais ativos mantidos ... {len(clientes)}")
    # Vocabulário REAL de planType encontrado (confirma a heurística de 'anual').
    if plan_types_vistos:
        vistos = ", ".join(sorted(repr(p) for p in plan_types_vistos))
        print(f"  planType DISTINTOS vistos: {vistos}")

    print("  --- distribuição por perfil ---")
    for perfil, count in sorted(por_perfil.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {perfil:<20} {count:>4}")
    print("  --- distribuição por objetivo_sugerido ---")
    for obj, count in sorted(por_objetivo.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {obj:<20} {count:>4}")

    print(f"  HTML gerado: {_OUTPUT_PATH}")
    print(
        "  AVISO LGPD: 'abordagem-anuais.html' contém PII (nome/whatsapp) — "
        "NÃO commite esse arquivo."
    )


# --------------------------------------------------------------------------- demo


def _demo_customers() -> list[dict]:
    """~8 clientes FICTÍCIOS (whatsapp fake) cobrindo todos os perfis e objetivos.

    Formato idêntico a um PartnerCustomer da API, para passar pelo MESMO pipeline
    (classify_profile + _build_cliente). Preenche TODOS os campos do contrato novo
    (email/total_pago/datas coerentes; nps_comment em alguns). Nenhum dado real é tocado.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    def _iso_in(days: int) -> str:
        # ISO com Z (como a API entrega), `days` dias DEPOIS de hoje (futuro se >0).
        return (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _iso_ago(days: int) -> str:
        # ISO com Z, `days` dias ANTES de hoje (passado).
        return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _cust(
        idx: int,
        name: str,
        *,
        days: int,
        score,
        voted: bool,
        period_in: int,
        total_centavos: int,
        comment: str = "",
        payment: str = "credit_card",
    ) -> dict:
        # signedUpAt um pouco antes de virar assinante; startedAt = days dias atrás.
        signed_ago = days + 5
        # respondedAt só faz sentido se votou (senão fica ausente).
        responded_at = _iso_ago(max(1, days // 2)) if voted else None
        return {
            "id": f"demo-{idx}",
            "name": name,
            "email": f"demo{idx}@example.test",
            "whatsapp": f"55319000000{idx:02d}",
            "signedUpAt": _iso_ago(signed_ago),
            "subscription": {
                "state": STATE_ACTIVE_PAYING,
                "active": True,
                "cancelled": False,
                "complimentary": False,
                "planName": "Plano Anual",
                "planType": "anual",
                "paymentMethod": payment,
                "startedAt": _iso_ago(days),
                "daysAsSubscriber": days,
                "currentPeriodEnd": _iso_in(period_in),
                "totalPaidCentavos": total_centavos,
                "lastPaymentAt": _iso_ago(min(days, 365)),  # última cobrança anual
            },
            "nps": {
                "voted": voted,
                "score": score,
                "comment": comment,
                "respondedAt": responded_at,
            },
        }

    # Combinações escolhidas p/ cobrir os perfis ATIVOS e os 3 objetivos:
    #  - embaixador (>=90d + >=9), ativo_promotor (<90d + >=9), ativo_em_risco (<=6),
    #    ativo_passivo (7-8), ativo_recente (<=14, sem nota), ativo_silencioso (voted=False),
    #    ativo_fiel (>=90d, sem nota). + 1 perto de renovar (objetivo=renovacao).
    # total_centavos variados p/ exercitar o formatador de R$ (milhar, centavos != 00).
    return [
        _cust(
            1, "Ana Embaixadora", days=200, score=10, voted=True, period_in=120,
            total_centavos=23980, comment="Mudou minha rotina de estudos, recomendo demais!",
        ),
        _cust(
            2, "Bruno Promotor", days=40, score=9, voted=True, period_in=200,
            total_centavos=11990, comment="Conteúdo excelente, só faltam mais simulados.",
        ),
        _cust(
            3, "Carla Em Risco", days=120, score=4, voted=True, period_in=180,
            total_centavos=12000, comment="Travou várias vezes no app, fiquei frustrada.",
            payment="pix",
        ),
        # Passivo (7-8): votou neutro, sem comentário escrito.
        _cust(
            4, "Diego Passivo", days=150, score=8, voted=True, period_in=90,
            total_centavos=12000,
        ),
        # Recente (<=14d, sem nota): ainda não votou.
        _cust(
            5, "Eva Recente", days=10, score=None, voted=False, period_in=355,
            total_centavos=9900, payment="pix",
        ),
        # Silencioso (voted=False, sem nota).
        _cust(
            6, "Felipe Silencioso", days=60, score=None, voted=False, period_in=150,
            total_centavos=11990, payment="boleto",
        ),
        # Fiel (>=90d, sem nota).
        _cust(
            7, "Gina Fiel", days=400, score=None, voted=False, period_in=70,
            total_centavos=1200000,  # R$ 12.000,00 — exercita o ponto de milhar
        ),
        # Perto de renovar (period_in <= 30) -> objetivo_sugerido vira "renovacao".
        _cust(
            8, "Heitor Renovando", days=350, score=9, voted=True, period_in=12,
            total_centavos=23980, comment="Vou renovar com certeza, valeu muito a pena.",
        ),
    ]


async def run_demo() -> int:
    """Gera o HTML a partir de clientes fictícios. NÃO chama a API nem grava PII real."""
    from app.domain.segmentation.profiles import classify_profile

    today = datetime.now(timezone.utc).date()
    raw = _demo_customers()
    clientes: list[dict] = []
    plan_types: set[str] = set()
    for customer in raw:
        sub = customer.get("subscription") or {}
        pt = sub.get("planType")
        if pt is not None:
            plan_types.add(str(pt))
        cls = classify_profile(customer)
        clientes.append(_build_cliente(customer, cls, today))

    html = _render_html(clientes)
    _OUTPUT_PATH.write_text(html, encoding="utf-8")
    print("=== MODO --demo (dados FICTÍCIOS, API não tocada) ===")
    _print_resumo(total_bruto=len(raw), clientes=clientes, plan_types_vistos=plan_types)
    return 0


# ---------------------------------------------------------------------------- real


async def run_real() -> int:
    """Puxa a API, filtra anuais ativos, classifica e gera o HTML."""
    from app.domain.segmentation.profiles import classify_profile
    from app.integrations.bizzu_partner import (
        BizzuPartnerAuthError,
        BizzuPartnerClient,
        BizzuPartnerError,
    )

    today = datetime.now(timezone.utc).date()
    client = BizzuPartnerClient()

    total_bruto = 0
    clientes: list[dict] = []
    # Vocabulário REAL de planType visto entre os ATIVOS (confirma a heurística 'anual').
    plan_types_ativos: set[str] = set()

    try:
        async for customer in client.iter_all_customers(page_size=500):
            total_bruto += 1
            sub = customer.get("subscription") or {}
            # 1) precisa ser ativo pagante.
            if sub.get("state") != STATE_ACTIVE_PAYING:
                continue
            # Registra o planType visto entre ativos (sem PII), p/ confirmar vocabulário.
            pt = sub.get("planType")
            if pt is not None:
                plan_types_ativos.add(str(pt))
            # 2) precisa ser plano anual (tolerante).
            if not _is_anual(sub.get("planType"), sub.get("planName")):
                continue
            cls = classify_profile(customer)
            clientes.append(_build_cliente(customer, cls, today))
    except BizzuPartnerAuthError:
        print(
            "ERRO: X-API-Key inválida/ausente na API de Clientes da Bizzu (401). "
            "Rotacionar / pedir a chave ao Felipe e pôr BIZZU_PARTNER_API_KEY no .env.",
            file=sys.stderr,
        )
        return 1
    except BizzuPartnerError as exc:
        print(f"ERRO: API de Clientes da Bizzu falhou ({exc}).", file=sys.stderr)
        return 1

    html = _render_html(clientes)
    _OUTPUT_PATH.write_text(html, encoding="utf-8")
    _print_resumo(total_bruto=total_bruto, clientes=clientes, plan_types_vistos=plan_types_ativos)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Exporta os clientes ANUAIS ATIVOS da Bizzu para um HTML de abordagem no "
            "WhatsApp (injeta os dados num template). NÃO dispara mensagem."
        )
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="não chama a API: gera clientes fictícios cobrindo todos os perfis/objetivos",
    )
    args = parser.parse_args(argv)

    # _render_html valida o template; se faltar, erra cedo e claro nos dois modos.
    if args.demo:
        return asyncio.run(run_demo())
    return asyncio.run(run_real())


if __name__ == "__main__":
    raise SystemExit(main())
