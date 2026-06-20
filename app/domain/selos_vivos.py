"""Selos VIVOS — selos derivados do ESTADO do cliente (read-only, não persistidos).

Diferente dos selos MANUAIS (em `Contact.profile_data["selos"]`, aplicados pelo
operador na campanha win-back), os selos vivos são CALCULADOS a cada leitura a partir
do snapshot da API de Clientes (`partner`) e do Health Score já computado. Eles nunca
são gravados no banco: refletem o estado atual e mudam sozinhos quando o estado muda
(o NPS sobe, a assinatura cancela, o cliente envelhece de "Novo" etc.).

São uma camada de LEITURA: o `/api/clientes` e a ficha 360 expõem `selos_vivos` ao lado
dos selos manuais, para a UI mostrar de relance "VIP / Detrator / Em risco / Novo /
Renovação próxima" sem o operador ter de marcar nada.

Função pura e tolerante a None/sujeira: nunca lança. Campo ausente/malformado no
snapshot simplesmente não dispara o selo correspondente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Janela (em dias) em que um cliente é considerado "Novo" pela data de assinatura.
_NOVO_MAX_DIAS = 30
# Janela (em dias) em que a renovação é considerada "próxima".
_RENOVACAO_JANELA_DIAS = 15

# Estado(s) de assinatura que contam como churn/cancelamento (para o selo "Em risco").
# Casados por substring lower (cobre 'cancelled', 'canceled', etc.), espelhando a
# semântica do health.py (`"cancel" in state`).
_CANCEL_SUBSTR = "cancel"


def _band_of(health: Any) -> str | None:
    """Banda de saúde a partir do HealthResult (atributo .band) OU de um dict {'band'}.

    Tolera None e formatos inesperados — devolve None quando não consegue extrair.
    """
    if health is None:
        return None
    band = getattr(health, "band", None)
    if band is None and isinstance(health, dict):
        band = health.get("band")
    return str(band) if band else None


def _parse_iso_dt(value: Any) -> datetime | None:
    """ISO-8601 (str do snapshot, tolera 'Z') -> datetime aware (UTC); None se inválido."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def selos_vivos(
    contact: Any,
    partner: dict[str, Any] | None,
    health: Any,
    *,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Selos derivados do estado atual do cliente (read-only). Lista de
    `{"nome", "cor", "motivo", "icone"}`, só com os que se aplicam.

    Regras (cada uma independente; um cliente pode ter vários selos):
      - VIP                 nps.score >= 9                              #10b981 ⭐
      - Detrator            nps.score <= 6 E nps.voted (votou)          #ef4444 ⚠️
      - Em risco            health.band == 'at_risk' OU assinatura      #f59e0b 🔻
                            cancelada (subscription.cancelled==True OU
                            'cancel' em subscription.state)
      - Novo                subscription.daysAsSubscriber <= 30         #6366f1 🌱
      - Renovação próxima   subscription.currentPeriodEnd nos próximos  #8b5cf6 🔁
                            15 dias E assinatura ativa (não cancelada)

    `contact` é aceito por simetria de contrato (e uso futuro), mas as regras hoje
    derivam só de `partner` + `health`. Tudo best-effort: snapshot ausente/sujo não
    dispara nada e jamais lança.
    """
    now = now or datetime.now(timezone.utc)
    partner = partner if isinstance(partner, dict) else {}
    nps = partner.get("nps") if isinstance(partner.get("nps"), dict) else {}
    sub = partner.get("subscription") if isinstance(partner.get("subscription"), dict) else {}

    out: list[dict[str, str]] = []

    # --- NPS: VIP (promotor) / Detrator -------------------------------------
    raw_score = nps.get("score")
    score = int(raw_score) if isinstance(raw_score, (int, float)) else None
    # "votou": voted==True OU, na ausência da flag, a simples presença de uma nota.
    votou = bool(nps.get("voted")) or (score is not None)
    if score is not None and score >= 9:
        out.append({"nome": "VIP", "cor": "#10b981", "motivo": f"NPS {score}", "icone": "⭐"})
    if score is not None and score <= 6 and votou:
        out.append({"nome": "Detrator", "cor": "#ef4444", "motivo": f"NPS {score}", "icone": "⚠️"})

    # --- Estado da assinatura: cancelada? ------------------------------------
    state = sub.get("state")
    state_str = str(state).lower() if state else ""
    cancelada = bool(sub.get("cancelled")) or (_CANCEL_SUBSTR in state_str)

    # --- Em risco: banda at_risk OU assinatura cancelada/churn ---------------
    band = _band_of(health)
    if band == "at_risk":
        out.append({"nome": "Em risco", "cor": "#f59e0b", "motivo": "Health em risco", "icone": "🔻"})
    elif cancelada:
        out.append({"nome": "Em risco", "cor": "#f59e0b", "motivo": "Assinatura cancelada", "icone": "🔻"})

    # --- Novo: até 30 dias de casa -------------------------------------------
    raw_dias = sub.get("daysAsSubscriber")
    dias_assinante = int(raw_dias) if isinstance(raw_dias, (int, float)) else None
    if dias_assinante is not None and 0 <= dias_assinante <= _NOVO_MAX_DIAS:
        out.append({"nome": "Novo", "cor": "#6366f1", "motivo": f"{dias_assinante} dias de casa", "icone": "🌱"})

    # --- Renovação próxima: vence nos próximos 15 dias E ativo (não cancelado) -
    renova = _parse_iso_dt(sub.get("currentPeriodEnd"))
    if renova is not None and not cancelada:
        faltam = (renova.date() - now.date()).days
        if 0 <= faltam <= _RENOVACAO_JANELA_DIAS:
            rotulo = "renova hoje" if faltam == 0 else f"renova em {faltam} dia{'s' if faltam != 1 else ''}"
            out.append({"nome": "Renovação próxima", "cor": "#8b5cf6", "motivo": rotulo, "icone": "🔁"})

    return out
