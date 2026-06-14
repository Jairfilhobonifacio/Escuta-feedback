"""Health Score (CS Fase 1) — fórmula transparente, função pura, sem rede."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.cs.health import (  # noqa: E402
    BAND_AT_RISK,
    BAND_HEALTHY,
    BAND_WATCH,
    band_for,
    compute_health,
)

NOW = datetime(2026, 6, 13, tzinfo=timezone.utc)


def test_promotor_engajado_e_saudavel():
    r = compute_health(
        nps_score=10, perfil="ativo_promotor", last_feedback_at=NOW - timedelta(days=5),
        pos_count=3, subscription_state="active", now=NOW,
    )
    assert r.score >= 70 and r.band == BAND_HEALTHY
    assert any("promotor" in f["label"] for f in r.factors)


def test_detrator_churn_em_risco():
    r = compute_health(
        nps_score=2, perfil="churn_rapido", last_feedback_at=NOW - timedelta(days=120),
        neg_count=4, subscription_state="cancelled", now=NOW,
    )
    assert r.score < 40 and r.band == BAND_AT_RISK


def test_sem_sinais_fica_neutro_watch():
    # base 50, só "nunca deu feedback" (-8) -> 42 (watch)
    r = compute_health(now=NOW)
    assert r.band == BAND_WATCH


def test_clamp_0_100():
    alto = compute_health(
        nps_score=10, perfil="embaixador", last_feedback_at=NOW, pos_count=9,
        subscription_state="active", now=NOW,
    )
    baixo = compute_health(
        nps_score=0, perfil="churn_pos_uso", last_feedback_at=NOW - timedelta(days=400),
        neg_count=9, subscription_state="cancelled", now=NOW,
    )
    assert 0 <= alto.score <= 100 and alto.score == 100
    assert 0 <= baixo.score <= 100 and baixo.score == 0


def test_factors_explicam_o_score():
    r = compute_health(nps_score=2, perfil="ativo_em_risco", now=NOW)
    labels = [f["label"] for f in r.factors]
    assert any("detrator" in l for l in labels)
    assert any("risco" in l for l in labels)


def test_perfil_desconhecido_com_prefixo_churn():
    r = compute_health(perfil="churn_qualquer_coisa", now=NOW)
    assert any(f["delta"] < 0 for f in r.factors)


def test_band_boundaries():
    assert band_for(70) == BAND_HEALTHY
    assert band_for(69) == BAND_WATCH
    assert band_for(40) == BAND_WATCH
    assert band_for(39) == BAND_AT_RISK
