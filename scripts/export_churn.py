"""Exporta os clientes que deram CHURN no plano MENSAL da Bizzu -> HTML de abordagem.

Espelha scripts/export_anuais_ativos.py, mas filtra os clientes que **cancelaram**
(`subscription.cancelled == true`) do **plano mensal**, classifica cada um por perfil
de churn e injeta um JSON no template docs/campanhas/_abordagem-churn.template.html,
gerando docs/campanhas/abordagem-churn-mensal.html — a tela que o Jair usa para
abordar quem saiu, **extrair o porquê do churn** (causa-raiz) e abrir reativação.

  NÃO dispara mensagem em nenhum caminho — só LÊ a API e GERA um HTML local.

Modos:
  (real)   py scripts/export_churn_mensal.py        (precisa BIZZU_PARTNER_API_KEY)
  --demo   py scripts/export_churn_mensal.py --demo  (6 fictícios, não toca API/PII)

Privacidade (LGPD): o HTML gerado contém PII -> NÃO commitar. stdout sem PII.
`churn_involuntario` (PAYMENT_FAILED) aparece marcado **nao_contatar** (winback e-mail).

TLS (Avast intercepta): truststore.inject_into_ssl() no TOPO, antes de qualquer import app.*.
"""
from __future__ import annotations

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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_env() -> None:
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

_CAMPANHAS_DIR = _PROJECT_ROOT / "docs" / "campanhas"
_TEMPLATE_PATH = _CAMPANHAS_DIR / "_abordagem-churn.template.html"
_OUTPUT_PATH = _CAMPANHAS_DIR / "abordagem-churn.html"
_PLACEHOLDER = "/*__CLIENTES__*/"

# Tradução do cancellationReason (API) -> rótulo PT-BR para a UI.
_MOTIVO_LABEL = {
    "GUARANTEE_REFUND": "Reembolso na garantia",
    "USER_CANCEL": "Cancelou (voluntário)",
    "PAYMENT_FAILED": "Pagamento falhou",
    "OTHER": "Outro",
}

# Objetivo de abordagem por perfil de churn.
_OBJETIVO = {
    "churn_rapido": "entender_inicio",
    "churn_pos_uso": "entender_parada",
    "churn_outro": "entender",
    "churn_involuntario": "nao_contatar",
    "vai_expirar": "reter",
}

# Mensagem on-brand sugerida (1º contato) por perfil. None = não contatar.
# Texto canônico do docs/campanhas/mensagens-churn-mensal.md (variação A).
_CHURN_MSG = {
    "churn_rapido": (
        "vi que você testou o Bizzu e acabou cancelando logo no início 😕 queria muito "
        "entender: o que faltou pra fazer sentido pra você? sua resposta vai direto pro "
        "time que constrói o produto."
    ),
    "churn_pos_uso": (
        "vi que você usou o Bizzu por um tempo e depois cancelou 😕 posso te perguntar, de "
        "boa: o que pesou na decisão de parar? quero levar isso pro time."
    ),
    "churn_outro": (
        "vi aqui que você cancelou sua assinatura do Bizzu 😕 pode me contar em uma frase o "
        "que te fez sair? sua resposta vai direto pro time."
    ),
    "vai_expirar": (
        "vi que seu acesso ao Bizzu tá quase no fim ⏳ antes de ir, posso te perguntar: tem "
        "alguma coisa que faria você continuar com a gente? pode falar com sinceridade."
    ),
    "churn_involuntario": None,
}

# Roteiro de perguntas que o Jair conduz na conversa (e o bot aprofunda):
# por que saiu -> o que faltou -> o que faria voltar.
_ROTEIRO = [
    "O que te fez cancelar o Bizzu?",
    "O que faltou pra valer a pena pra você?",
    "Se a gente resolvesse isso, o que faria você considerar voltar?",
]

# Prioridade base por perfil (maior = aparece no topo da worklist).
_PRIORIDADE = {
    "churn_pos_uso": 3,   # usou bastante: vale entender + reativar
    "churn_rapido": 2,    # fricção de entrada: consertar
    "vai_expirar": 2,
    "churn_outro": 1,
    "churn_involuntario": 0,
}


def _digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_date(value: Any) -> str:
    dt = _parse_dt(value)
    return dt.date().strftime("%d/%m/%Y") if dt is not None else ""


def _fmt_reais(centavos: Any) -> str:
    if not isinstance(centavos, (int, float)):
        return ""
    inteiro, cents = divmod(int(round(centavos)), 100)
    milhar = f"{inteiro:,}".replace(",", ".")
    return f"R$ {milhar},{cents:02d}"


def _is_mensal(plan_type: str | None, plan_name: str | None) -> bool:
    """Heurística TOLERANTE de 'plano mensal' (inverso do _is_anual)."""
    pt = (plan_type or "").strip().lower()
    pn = (plan_name or "").strip().lower()
    if any(tok in pt for tok in ("mensal", "monthly", "month", "mês", "mes")):
        return True
    return any(tok in pn for tok in ("mensal", "mês", " mes"))


def _is_anual(plan_type: str | None, plan_name: str | None) -> bool:
    pt = (plan_type or "").strip().lower()
    pn = (plan_name or "").strip().lower()
    return any(tok in pt for tok in ("anual", "annual", "year")) or "anual" in pn


def _plan_matches(plan: str, sub: dict) -> bool:
    """Filtro de plano: 'todos' não filtra; 'mensal'/'anual' usam a heurística."""
    if plan == "todos":
        return True
    if plan == "mensal":
        return _is_mensal(sub.get("planType"), sub.get("planName"))
    return _is_anual(sub.get("planType"), sub.get("planName"))


def _is_churn(sub: dict) -> bool:
    """Pediu/sofreu cancelamento: flag cancelled OU state cancelado (com/sem acesso)."""
    return bool(sub.get("cancelled")) or sub.get("state") in ("cancelled", "cancelled_with_access")


def _build_cliente(customer: dict, classification: dict, today: date) -> dict:
    """Monta o cliente de churn no contrato que a UI espera."""
    sub = customer.get("subscription") or {}
    nps = customer.get("nps") or {}

    nome_completo = (customer.get("name") or "").strip()
    primeiro = nome_completo.split()[0] if nome_completo else ""
    whatsapp = _digits_only(customer.get("whatsapp"))

    days_raw = sub.get("daysAsSubscriber")
    dias_de_casa = int(days_raw) if isinstance(days_raw, (int, float)) else None
    meses_de_casa = round(dias_de_casa / 30) if dias_de_casa is not None else None

    reason = sub.get("cancellationReason")
    motivo_label = _MOTIVO_LABEL.get(reason, reason or "—")

    score_raw = nps.get("score")
    nps_score = int(score_raw) if isinstance(score_raw, (int, float)) else None

    perfil = classification["profile"]
    should_contact = bool(classification.get("should_contact"))
    objetivo = _OBJETIVO.get(perfil, "entender")

    msg = _CHURN_MSG.get(perfil)
    if msg is None or not should_contact:
        mensagem_sugerida = None
    else:
        saud = f"Oi {primeiro}! " if primeiro else "Oi! "
        mensagem_sugerida = saud + msg + " (se for mais fácil, pode me responder por áudio 🎙️)"

    votou = bool(nps.get("voted"))
    # Ex-promotor: saiu MESMO gostando (NPS >= 9) -> churn evitável, reativação quente.
    ex_promotor = votou and nps_score is not None and nps_score >= 9

    # Prioridade: base do perfil + detrator que saiu; ex-promotor vai pro topo.
    prioridade = _PRIORIDADE.get(perfil, 1)
    if nps_score is not None and nps_score <= 6:
        prioridade += 1
    if ex_promotor:
        prioridade += 3

    return {
        "ex_promotor": ex_promotor,
        "roteiro": _ROTEIRO,
        "nome": primeiro,
        "nome_completo": nome_completo,
        "email": (customer.get("email") or "").strip(),
        "whatsapp": whatsapp,
        "plano": sub.get("planName"),
        "plan_type": sub.get("planType"),
        "estado": sub.get("state"),
        "cancelou_em": _fmt_date(sub.get("cancelledAt")),
        "dias_de_casa": dias_de_casa,
        "meses_de_casa": meses_de_casa,
        "motivo": reason,
        "motivo_label": motivo_label,
        "total_pago": _fmt_reais(sub.get("totalPaidCentavos")),
        "nps_score": nps_score,
        "nps_comment": (nps.get("comment") or "").strip(),
        "nps_votou": bool(nps.get("voted")),
        "perfil": perfil,
        "objetivo": objetivo,
        "should_contact": should_contact,
        "prioridade": prioridade,
        "mensagem_sugerida": mensagem_sugerida,
    }


def _render_html(clientes: list[dict]) -> str:
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template não encontrado: {_TEMPLATE_PATH}\n"
            "Gere 'docs/campanhas/_abordagem-churn.template.html' antes de exportar."
        )
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    if _PLACEHOLDER not in template:
        raise ValueError(f"O template não contém o marcador '{_PLACEHOLDER}'.")
    payload = json.dumps(clientes, ensure_ascii=False)
    return template.replace(_PLACEHOLDER, f"window.CLIENTES = {payload};")


def _print_resumo(total_bruto: int, clientes: list[dict], plan_types: set[str]) -> None:
    por_perfil: dict[str, int] = {}
    por_objetivo: dict[str, int] = {}
    contataveis = 0
    for c in clientes:
        por_perfil[c["perfil"]] = por_perfil.get(c["perfil"], 0) + 1
        por_objetivo[c["objetivo"]] = por_objetivo.get(c["objetivo"], 0) + 1
        if c["should_contact"] and c["mensagem_sugerida"]:
            contataveis += 1

    print("=== RESUMO (sem PII) ===")
    print(f"  Total bruto da API ......... {total_bruto}")
    print(f"  Churn mensal mantidos ...... {len(clientes)}")
    print(f"  Contatáveis (com opt-in?) .. {contataveis}  (involuntário NÃO contar — winback e-mail)")
    if plan_types:
        print(f"  planType DISTINTOS vistos: {', '.join(sorted(repr(p) for p in plan_types))}")
    print("  --- distribuição por perfil de churn ---")
    for perfil, count in sorted(por_perfil.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {perfil:<22} {count:>4}")
    print("  --- distribuição por objetivo ---")
    for obj, count in sorted(por_objetivo.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {obj:<22} {count:>4}")
    print(f"  HTML gerado: {_OUTPUT_PATH}")
    print(f"  AVISO LGPD: '{_OUTPUT_PATH.name}' contém PII — NÃO commite esse arquivo.")


# --------------------------------------------------------------------------- demo


def _demo_customers() -> list[dict]:
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    def _iso_ago(days: int) -> str:
        return (now - timedelta(days=max(0, days))).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _cust(idx, name, *, days, reason, score=None, voted=False, total, comment="", payment="credit_card"):
        return {
            "id": f"demo-{idx}",
            "name": name,
            "email": f"demo{idx}@example.test",
            "whatsapp": f"55319000000{idx:02d}",
            "signedUpAt": _iso_ago(days + 5),
            "subscription": {
                "state": "cancelled",
                "active": False,
                "cancelled": True,
                "complimentary": False,
                "planName": "Plano Mensal",
                "planType": "mensal",
                "paymentMethod": payment,
                "startedAt": _iso_ago(days),
                "daysAsSubscriber": days,
                "cancelledAt": _iso_ago(max(1, days // 5)),
                "cancellationReason": reason,
                "totalPaidCentavos": total,
                "lastPaymentAt": _iso_ago(max(1, days // 2)),
            },
            "nps": {
                "voted": voted,
                "score": score,
                "comment": comment,
                "respondedAt": _iso_ago(max(1, days // 3)) if voted else None,
            },
        }

    return [
        _cust(1, "Ana Garantia", days=4, reason="GUARANTEE_REFUND", score=3, voted=True,
              total=2000, comment="achei caro e travou logo no começo", payment="pix"),
        _cust(2, "Bruno Cedo", days=2, reason="USER_CANCEL", score=2, voted=True,
              total=2000, comment="não era o que eu esperava"),
        _cust(3, "Carla Usou e Parou", days=75, reason="USER_CANCEL", score=6, voted=True,
              total=12000, comment="parei de estudar um tempo e não voltei"),
        _cust(4, "Diego Fiel que Saiu", days=160, reason="USER_CANCEL", voted=False, total=24000),
        _cust(5, "Eva Outro", days=15, reason="OTHER", voted=False, total=4000, payment="boleto"),
        _cust(6, "Felipe Pagamento", days=40, reason="PAYMENT_FAILED", voted=False, total=8000),
        _cust(7, "Gabriel Gostava", days=50, reason="USER_CANCEL", score=10, voted=True,
              total=10000, comment="amava o produto, mas apertou o orçamento esse mês"),
    ]


async def run_demo(plan: str = "todos") -> int:
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
        if not _plan_matches(plan, sub):
            continue
        clientes.append(_build_cliente(customer, classify_profile(customer), today))

    clientes.sort(key=lambda c: c["prioridade"], reverse=True)
    _OUTPUT_PATH.write_text(_render_html(clientes), encoding="utf-8")
    print("=== MODO --demo (dados FICTÍCIOS, API não tocada) ===")
    _print_resumo(total_bruto=len(raw), clientes=clientes, plan_types=plan_types)
    return 0


# ---------------------------------------------------------------------------- real


async def run_real(plan: str = "todos") -> int:
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
    plan_types_cancelados: set[str] = set()

    try:
        async for customer in client.iter_all_customers(page_size=500):
            total_bruto += 1
            sub = customer.get("subscription") or {}
            # 1) precisa ter pedido cancelamento (fez churn).
            if not _is_churn(sub):
                continue
            pt = sub.get("planType")
            if pt is not None:
                plan_types_cancelados.add(str(pt))
            # 2) filtro de plano (default 'todos' = não filtra).
            if not _plan_matches(plan, sub):
                continue
            clientes.append(_build_cliente(customer, classify_profile(customer), today))
    except BizzuPartnerAuthError:
        print("ERRO: X-API-Key inválida/ausente (401). Pôr BIZZU_PARTNER_API_KEY no .env.", file=sys.stderr)
        return 1
    except BizzuPartnerError as exc:
        print(f"ERRO: API de Clientes da Bizzu falhou ({exc}).", file=sys.stderr)
        return 1

    clientes.sort(key=lambda c: c["prioridade"], reverse=True)
    _OUTPUT_PATH.write_text(_render_html(clientes), encoding="utf-8")
    _print_resumo(total_bruto=total_bruto, clientes=clientes, plan_types=plan_types_cancelados)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exporta os clientes que deram CHURN no plano MENSAL para um HTML de abordagem. NÃO dispara mensagem."
    )
    parser.add_argument("--demo", action="store_true", help="não chama a API: 6 clientes fictícios")
    parser.add_argument("--plan", choices=["todos", "mensal", "anual"], default="todos",
                        help="filtra por plano (default: todos os que pediram cancelamento)")
    args = parser.parse_args(argv)
    return asyncio.run(run_demo(args.plan) if args.demo else run_real(args.plan))


if __name__ == "__main__":
    raise SystemExit(main())
