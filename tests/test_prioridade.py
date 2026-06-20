"""Índice de Prioridade das dores (FRENTE F1) — testes da função pura.

A função `priority_index` (app/domain/prioridade.py) é pura, sem sessão/rede:
recebe os números agregados (clientes distintos, peso de pagantes, neg/item count)
+ os pesos e devolve `{priority_index, priority_band, breakdown}`. Espelha o estilo
de teste de selos_vivos: exercita a fórmula da §2.3 da SPEC, a tolerância a entradas
sujas (`partner` None/malformado nunca lança) e as bandas alta/media/baixa.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.prioridade import (  # noqa: E402
    DEFAULT_WEIGHTS,
    is_paying,
    peso_pagante,
    priority_index,
)


# --- is_paying: regra canônica da §2.2 ---------------------------------------


def test_is_paying_estados_reais_do_codigo():
    # state (lower) contém paying/paid/active E não contém cancel/complimentary.
    assert is_paying({"subscription": {"state": "active_paying"}}) is True
    assert is_paying({"subscription": {"state": "paid_without_access"}}) is True
    assert is_paying({"subscription": {"state": "cancelled"}}) is False
    assert is_paying({"subscription": {"state": "complimentary"}}) is False
    assert is_paying({"subscription": {"state": "past_due"}}) is False


def test_is_paying_tolera_none_e_sujeira():
    assert is_paying(None) is False
    assert is_paying({}) is False
    assert is_paying({"subscription": None}) is False
    assert is_paying({"subscription": {}}) is False
    assert is_paying({"subscription": {"state": None}}) is False
    assert is_paying("não é dict") is False
    # case-insensitive
    assert is_paying({"subscription": {"state": "ACTIVE_PAYING"}}) is True


# --- peso_pagante: 0 / 1.0 (mensal) / mult (anual) ---------------------------


def test_peso_pagante_nao_pagante_zero():
    assert peso_pagante({"subscription": {"state": "cancelled"}}) == 0.0
    assert peso_pagante(None) == 0.0


def test_peso_pagante_mensal_um():
    p = {"subscription": {"state": "active_paying", "planType": "mensal"}}
    assert peso_pagante(p) == 1.0


def test_peso_pagante_anual_multiplicado():
    p = {"subscription": {"state": "active_paying", "planType": "anual"}}
    # default PLANO_ALTO_MULT = 1.5; pagante anual pesa mais que mensal.
    assert peso_pagante(p) == 1.5
    assert peso_pagante(p, plano_alto_mult=2.0) == 2.0
    # plano anual mas NÃO pagante (cancelado) não ganha peso.
    cancelado_anual = {"subscription": {"state": "cancelled", "planType": "anual"}}
    assert peso_pagante(cancelado_anual) == 0.0


def test_peso_pagante_anual_lido_de_plan_name():
    # espelha compute_urgencia: planType OU planName contém 'anual'.
    p = {"subscription": {"state": "active_paying", "planName": "Plano Anual"}}
    assert peso_pagante(p) == 1.5


# --- priority_index: fórmula da §2.3 -----------------------------------------


def test_priority_index_componentes_e_formula():
    # 7 distintos, paying_weighted = 6 (ex.: 4 mensais + (2 - clamp)…), neg 11/20.
    out = priority_index(
        distinct_customers=7,
        paying_weighted=6.0,
        neg_count=11,
        item_count=20,
        weights=DEFAULT_WEIGHTS,
    )
    # volume_score = min(1, 7/10) = 0.7
    assert out["breakdown"]["volume_score"] == pytest.approx(0.70)
    # revenue_score = 6/7 ≈ 0.857 (clamp em 1.0)
    assert out["breakdown"]["revenue_score"] == pytest.approx(6 / 7, abs=1e-3)
    # gravity_score = 11/20 = 0.55
    assert out["breakdown"]["gravity_score"] == pytest.approx(0.55)
    esperado = round(
        100 * (0.50 * 0.70 + 0.30 * (6 / 7) + 0.20 * 0.55), 1
    )
    assert out["priority_index"] == esperado
    # pesos expostos para a UI explicar a prioridade.
    assert out["breakdown"]["weights"] == {"volume": 0.5, "revenue": 0.3, "gravity": 0.2}


def test_priority_index_volume_satura_em_vol_ref():
    # 50 distintos com VOL_REF=10 satura volume_score em 1.0 (não passa de 1).
    out = priority_index(
        distinct_customers=50, paying_weighted=0.0, neg_count=0, item_count=1,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["breakdown"]["volume_score"] == 1.0


def test_priority_index_revenue_clampa_em_um():
    # paying_weighted > distinct (todos anuais) → revenue_score clampa em 1.0.
    out = priority_index(
        distinct_customers=2, paying_weighted=3.0, neg_count=0, item_count=1,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["breakdown"]["revenue_score"] == 1.0


def test_priority_index_gravity_zero_quando_sem_negativos():
    # neg_count=0 com item_count>0 → gravity_score=0 (sentimento pendente), índice
    # segue válido por volume+receita (caso explícito da §2.3).
    out = priority_index(
        distinct_customers=10, paying_weighted=10.0, neg_count=0, item_count=5,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["breakdown"]["gravity_score"] == 0.0
    # volume_score=1.0, revenue_score=1.0, gravity_score=0 → 100*(0.5+0.3+0) = 80.0
    assert out["priority_index"] == 80.0
    assert out["priority_band"] == "alta"


def test_priority_index_item_count_zero_nao_divide_por_zero():
    out = priority_index(
        distinct_customers=0, paying_weighted=0.0, neg_count=0, item_count=0,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["breakdown"]["gravity_score"] == 0.0
    assert out["breakdown"]["revenue_score"] == 0.0
    assert out["priority_index"] == 0.0
    assert out["priority_band"] == "baixa"


# --- bandas: alta >= 66, media >= 33, baixa < 33 -----------------------------


def test_priority_band_alta():
    # tudo no talo: volume 1, revenue 1, gravity 1 → 100 → alta
    out = priority_index(
        distinct_customers=10, paying_weighted=10.0, neg_count=5, item_count=5,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["priority_index"] == 100.0
    assert out["priority_band"] == "alta"


def test_priority_band_media():
    # volume 0.5 (5/10), sem receita, gravity 0.5 → 100*(0.25+0+0.10) = 35 → media
    out = priority_index(
        distinct_customers=5, paying_weighted=0.0, neg_count=5, item_count=10,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["priority_index"] == 35.0
    assert out["priority_band"] == "media"


def test_priority_band_baixa():
    # volume 0.2 (2/10), sem receita, sem gravidade → 10 → baixa
    out = priority_index(
        distinct_customers=2, paying_weighted=0.0, neg_count=0, item_count=4,
        weights=DEFAULT_WEIGHTS,
    )
    assert out["priority_index"] == 10.0
    assert out["priority_band"] == "baixa"


def test_priority_band_fronteiras_exatas():
    # 66 e 33 são inclusivos (>=). Forja índices exatos via gravity puro.
    # gravity=1 com peso 0.20 → 20; some volume p/ chegar nas fronteiras.
    # 66: volume_score tal que 100*(0.5*v) = 66 → v=1.32 (impossível); usamos a
    # combinação volume=1 (50) + gravity nas frações certas (0.8 → 16) = 66.
    alta = priority_index(
        distinct_customers=10, paying_weighted=0.0, neg_count=8, item_count=10,
        weights=DEFAULT_WEIGHTS,
    )
    assert alta["priority_index"] == 66.0
    assert alta["priority_band"] == "alta"


# --- pesos custom mudam o resultado (§5 critério de aceite) ------------------


def test_pesos_custom_mudam_o_indice():
    base = dict(distinct_customers=10, paying_weighted=0.0, neg_count=0, item_count=1)
    # default: 100*(0.5*1) = 50
    padrao = priority_index(**base, weights=DEFAULT_WEIGHTS)
    assert padrao["priority_index"] == 50.0
    # peso de volume 1.0 (e nada mais) → 100*(1.0*1) = 100
    custom = priority_index(
        **base,
        weights={"volume": 1.0, "revenue": 0.0, "gravity": 0.0, "volume_ref": 10},
    )
    assert custom["priority_index"] == 100.0
    assert custom["breakdown"]["weights"] == {"volume": 1.0, "revenue": 0.0, "gravity": 0.0}


def test_volume_ref_custom_muda_saturacao():
    # VOL_REF=5 → 5 distintos já saturam volume_score em 1.0
    out = priority_index(
        distinct_customers=5, paying_weighted=0.0, neg_count=0, item_count=1,
        weights={"volume": 0.5, "revenue": 0.3, "gravity": 0.2, "volume_ref": 5},
    )
    assert out["breakdown"]["volume_score"] == 1.0


def test_priority_index_clampa_em_100_com_pesos_somando_mais_que_um():
    # Pesos são configuráveis por env; se somarem > 1.0 o raw passa de 1.0 e o
    # índice estouraria 100 sem clamp. Aqui todos os componentes = 1.0 e os pesos
    # somam 3.0 → raw=3.0 → índice DEVE ser clampado em 100.0 (não 300.0).
    out = priority_index(
        distinct_customers=10, paying_weighted=10.0, neg_count=5, item_count=5,
        weights={"volume": 1.0, "revenue": 1.0, "gravity": 1.0, "volume_ref": 10},
    )
    assert out["breakdown"]["volume_score"] == 1.0
    assert out["breakdown"]["revenue_score"] == 1.0
    assert out["breakdown"]["gravity_score"] == 1.0
    assert out["priority_index"] <= 100.0
    assert out["priority_index"] == 100.0
    assert out["priority_band"] == "alta"
