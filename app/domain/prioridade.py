"""Índice de Prioridade das DORES — volume × receita × gravidade (read-only).

A tela de Mapeamento (`/temas`) precisa de um índice TRANSPARENTE que ordene as dores
(clusters) pelo quanto MERECEM ação agora — não só pelo `pain_score` (que conta itens,
não clientes, e ignora a receita em risco). Este módulo é a peça de domínio dessa
priorização: uma função PURA (sem sessão/rede, nunca lança) que combina três sinais já
presentes na base num índice 0..100 + uma banda (alta/media/baixa), com os pesos e os
componentes EXPOSTOS para a UI explicar "por que essa prioridade".

Filosofia idêntica à de `selos_vivos.py`: calcula-se a cada LEITURA a partir do snapshot
`partner` (que muda fora do run de clustering — renovação, cancelamento), de modo a
refletir sempre o estado atual. Nada é persistido.

Os três sinais (SPEC §2.2):
  - volume   — nº de clientes DISTINTOS com a dor (não nº de itens).
  - receita  — fração de clientes PAGANTES entre os distintos (pagante anual pesa mais).
  - gravidade— fração negativa = neg_count / item_count (negatividade do sentimento).

Tolerância a None/sujeira: `partner` ausente/malformado nunca dispara peso e jamais
lança (espelha `selos_vivos.peso_pagante`/`is_paying`).
"""
from __future__ import annotations

from typing import Any

# --- Pesos default (SPEC §2.3). O endpoint sobrescreve com os de app/config.py. -----
# Mantidos aqui também para a função pura ser usável/testável sem importar config.
DEFAULT_WEIGHTS: dict[str, float] = {
    "volume": 0.50,   # peso do volume (clientes distintos)
    "revenue": 0.30,  # peso da receita (pagantes / plano alto)
    "gravity": 0.20,  # peso da gravidade (negatividade)
    "volume_ref": 10,        # volume que satura volume_score em 1.0
    "plano_alto_mult": 1.5,  # multiplicador do pagante anual (plano alto)
}

# Bandas do índice (SPEC §2.3): limites INCLUSIVOS no piso de cada faixa.
_BAND_ALTA_MIN = 66.0
_BAND_MEDIA_MIN = 33.0

# Substrings (lower) da regra canônica de "pagante" (SPEC §2.2): o state precisa conter
# uma das positivas E nenhuma das negativas.
_PAYING_SUBSTR = ("paying", "paid", "active")
_NOT_PAYING_SUBSTR = ("cancel", "complimentary")
# Substring que marca plano ALTO (anual) — espelha o `'anual' in plano` de compute_urgencia.
_PLANO_ALTO_SUBSTR = "anual"


def _subscription(partner: Any) -> dict[str, Any]:
    """`partner.subscription` como dict; {} quando partner/sub é None ou não-dict."""
    if not isinstance(partner, dict):
        return {}
    sub = partner.get("subscription")
    return sub if isinstance(sub, dict) else {}


def is_paying(partner: Any) -> bool:
    """True quando o snapshot `partner` indica assinatura PAGANTE (SPEC §2.2).

    Regra canônica: `subscription.state` (lower) contém `paying`/`paid`/`active` E NÃO
    contém `cancel`/`complimentary`. Estados vistos no código (admin.py:1104): pagantes
    = `active_paying`, `paid_without_access`; não-pagantes = `cancelled`,
    `complimentary`, `past_due`. Tolerante a None/sujeira — nunca lança.
    """
    state = _subscription(partner).get("state")
    if not state:
        return False
    st = str(state).lower()
    if any(bad in st for bad in _NOT_PAYING_SUBSTR):
        return False
    return any(good in st for good in _PAYING_SUBSTR)


def _is_plano_alto(partner: Any) -> bool:
    """Plano ALTO (anual) — `subscription.planType`/`planName` contém 'anual'.

    Espelha o detector de plano anual de `compute_urgencia` (admin.py:1010-1012), que
    olha planType OU planName.
    """
    sub = _subscription(partner)
    plano = str(sub.get("planType") or sub.get("planName") or "").lower()
    return _PLANO_ALTO_SUBSTR in plano


def peso_pagante(partner: Any, *, plano_alto_mult: float = 1.5) -> float:
    """Peso de receita de UM cliente (SPEC §2.3):

      - 0.0              quando não é pagante;
      - 1.0              pagante de plano normal (mensal);
      - `plano_alto_mult` pagante de plano alto (anual), default 1.5.

    Tolerante a None/sujeira — nunca lança.
    """
    if not is_paying(partner):
        return 0.0
    return float(plano_alto_mult) if _is_plano_alto(partner) else 1.0


def priority_index(
    distinct_customers: int,
    paying_weighted: float,
    neg_count: int,
    item_count: int,
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Índice de prioridade 0..100 de uma dor (função PURA). SPEC §2.3.

    Args (já agregados pelo endpoint — esta função não toca o banco):
      - distinct_customers: nº de clientes DISTINTOS no cluster (volume).
      - paying_weighted:    Σ peso_pagante dos clientes distintos (receita ponderada).
      - neg_count:          nº de itens com sentimento negativo (gravidade).
      - item_count:         nº total de itens do cluster (denominador da gravidade).
      - weights:            pesos + refs (default `DEFAULT_WEIGHTS`); chaves: `volume`,
                            `revenue`, `gravity`, `volume_ref`, `plano_alto_mult`.

    Componentes normalizados em 0..1:
      volume_score  = min(1.0, distinct_customers / volume_ref)
      revenue_score = min(1.0, paying_weighted / max(distinct_customers, 1))
      gravity_score = neg_count / item_count   (0 se item_count == 0)

    Devolve `{"priority_index", "priority_band", "breakdown"}` — `breakdown` traz os
    três componentes + os pesos efetivos, para a UI explicar a prioridade. Nunca lança.
    """
    w = weights or DEFAULT_WEIGHTS
    w_volume = float(w.get("volume", DEFAULT_WEIGHTS["volume"]))
    w_revenue = float(w.get("revenue", DEFAULT_WEIGHTS["revenue"]))
    w_gravity = float(w.get("gravity", DEFAULT_WEIGHTS["gravity"]))
    volume_ref = float(w.get("volume_ref", DEFAULT_WEIGHTS["volume_ref"])) or 1.0

    distinct = max(0, int(distinct_customers or 0))
    items = max(0, int(item_count or 0))
    neg = max(0, int(neg_count or 0))
    paying = max(0.0, float(paying_weighted or 0.0))

    volume_score = min(1.0, distinct / volume_ref) if volume_ref else 0.0
    revenue_score = min(1.0, paying / max(distinct, 1))
    gravity_score = (neg / items) if items else 0.0

    raw = w_volume * volume_score + w_revenue * revenue_score + w_gravity * gravity_score
    index = round(100.0 * raw, 1)

    if index >= _BAND_ALTA_MIN:
        band = "alta"
    elif index >= _BAND_MEDIA_MIN:
        band = "media"
    else:
        band = "baixa"

    return {
        "priority_index": index,
        "priority_band": band,
        "breakdown": {
            "volume_score": round(volume_score, 4),
            "revenue_score": round(revenue_score, 4),
            "gravity_score": round(gravity_score, 4),
            "weights": {
                "volume": w_volume,
                "revenue": w_revenue,
                "gravity": w_gravity,
            },
        },
    }
