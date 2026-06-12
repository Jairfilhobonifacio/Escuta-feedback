"""Testes da classificação pura de perfis (app/domain/segmentation/profiles.py).

stdlib + pytest, sem banco. Cobre os 13 perfis + precedência + fronteiras + edge cases.
Refinamento 2026-06-09: + ativo_promotor, ativo_passivo, ativo_fiel, churn_outro.

Rodar: python tests/test_partner_profiles.py   (ou: pytest tests/test_partner_profiles.py)
"""
import os
import sys

# permite rodar standalone (sem instalar o pacote)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.segmentation.profiles import (  # noqa: E402
    PROFILE_ATIVO_EM_RISCO,
    PROFILE_ATIVO_FIEL,
    PROFILE_ATIVO_PASSIVO,
    PROFILE_ATIVO_PROMOTOR,
    PROFILE_ATIVO_RECENTE,
    PROFILE_ATIVO_SILENCIOSO,
    PROFILE_CHURN_INVOLUNTARIO,
    PROFILE_CHURN_OUTRO,
    PROFILE_CHURN_POS_USO,
    PROFILE_CHURN_RAPIDO,
    PROFILE_CORTESIA,
    PROFILE_EMBAIXADOR,
    PROFILE_INDEFINIDO,
    PROFILE_VAI_EXPIRAR,
    classify_profile,
)


def _customer(*, state=None, complimentary=False, cancelled=False, reason=None,
              days=None, score=None, voted=None, active=None):
    """Monta um PartnerCustomer mínimo. score/voted None -> ausentes no nps."""
    sub = {
        "state": state,
        "complimentary": complimentary,
        "cancelled": cancelled,
        "cancellationReason": reason,
        "daysAsSubscriber": days,
        "active": active,
    }
    nps = {}
    if score is not None:
        nps["score"] = score
    if voted is not None:
        nps["voted"] = voted
    return {"subscription": sub, "nps": nps}


# ===================================== os 13 perfis (caminho feliz) =====================================

def test_cortesia():
    r = classify_profile(_customer(state="complimentary", complimentary=True))
    assert r["profile"] == PROFILE_CORTESIA and r["should_contact"] is True


def test_churn_involuntario_nao_contatar():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="PAYMENT_FAILED", days=100))
    assert r["profile"] == PROFILE_CHURN_INVOLUNTARIO and r["should_contact"] is False


def test_churn_rapido_por_guarantee_refund():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="GUARANTEE_REFUND", days=2))
    assert r["profile"] == PROFILE_CHURN_RAPIDO


def test_churn_rapido_por_dias_curtos():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=3))
    assert r["profile"] == PROFILE_CHURN_RAPIDO


def test_churn_pos_uso():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=60))
    assert r["profile"] == PROFILE_CHURN_POS_USO and r["should_contact"] is True


def test_vai_expirar_cancelled_with_access():
    r = classify_profile(_customer(state="cancelled_with_access"))
    assert r["profile"] == PROFILE_VAI_EXPIRAR and r["should_contact"] is True


def test_vai_expirar_past_due():
    r = classify_profile(_customer(state="past_due"))
    assert r["profile"] == PROFILE_VAI_EXPIRAR


def test_churn_outro_reason_desconhecido():
    # cancelado com reason OTHER (não involuntário/rápido/pós-uso) -> churn_outro
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="OTHER", days=45))
    assert r["profile"] == PROFILE_CHURN_OUTRO and r["should_contact"] is True


def test_churn_outro_zona_cinza_dias():
    # USER_CANCEL em 15 dias: nem rápido (>7) nem pós-uso (<30) -> churn_outro
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=15))
    assert r["profile"] == PROFILE_CHURN_OUTRO


def test_embaixador():
    r = classify_profile(_customer(state="active_paying", days=120, score=10, voted=True))
    assert r["profile"] == PROFILE_EMBAIXADOR and r["should_contact"] is True


def test_ativo_em_risco_detrator():
    r = classify_profile(_customer(state="active_paying", days=50, voted=True, score=4))
    assert r["profile"] == PROFILE_ATIVO_EM_RISCO and r["should_contact"] is True


def test_ativo_promotor_recente():
    # score 9-10 mas days < 90 -> promotor (não embaixador)
    r = classify_profile(_customer(state="active_paying", days=30, voted=True, score=10))
    assert r["profile"] == PROFILE_ATIVO_PROMOTOR and r["should_contact"] is True


def test_ativo_passivo_7():
    r = classify_profile(_customer(state="active_paying", days=50, voted=True, score=7))
    assert r["profile"] == PROFILE_ATIVO_PASSIVO


def test_ativo_passivo_8():
    r = classify_profile(_customer(state="active_paying", days=50, voted=True, score=8))
    assert r["profile"] == PROFILE_ATIVO_PASSIVO


def test_ativo_recente():
    r = classify_profile(_customer(state="active_paying", days=5))
    assert r["profile"] == PROFILE_ATIVO_RECENTE and r["should_contact"] is True


def test_ativo_silencioso():
    r = classify_profile(_customer(state="active_paying", days=50, voted=False))
    assert r["profile"] == PROFILE_ATIVO_SILENCIOSO and r["should_contact"] is True


def test_ativo_fiel_sem_nota():
    # >= 90 dias, sem nota, não silencioso -> fiel por tempo
    r = classify_profile(_customer(state="active_paying", days=200, voted=True))
    assert r["profile"] == PROFILE_ATIVO_FIEL and r["should_contact"] is True


# ===================================== precedência =====================================

def test_cortesia_vence_active_paying():
    r = classify_profile(_customer(state="active_paying", complimentary=True, days=200, score=10))
    assert r["profile"] == PROFILE_CORTESIA


def test_payment_failed_vence_outros_churns():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="PAYMENT_FAILED", days=3))
    assert r["profile"] == PROFILE_CHURN_INVOLUNTARIO and r["should_contact"] is False


def test_past_due_nao_vira_ativo():
    r = classify_profile(_customer(state="past_due", days=200, score=10))
    assert r["profile"] == PROFILE_VAI_EXPIRAR


def test_churn_rapido_vence_pos_uso_dias_curtos():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=5))
    assert r["profile"] == PROFILE_CHURN_RAPIDO


def test_embaixador_vence_promotor():
    # >=90 dias + score>=9 -> embaixador (não promotor)
    r = classify_profile(_customer(state="active_paying", days=90, score=9))
    assert r["profile"] == PROFILE_EMBAIXADOR


def test_em_risco_vence_recente():
    # detrator recém-chegado (days 5, score 2) -> em risco (não recente)
    r = classify_profile(_customer(state="active_paying", days=5, voted=True, score=2))
    assert r["profile"] == PROFILE_ATIVO_EM_RISCO


# ===================================== fronteiras =====================================

def test_fronteira_embaixador_90_inclui():
    r = classify_profile(_customer(state="active_paying", days=90, score=9))
    assert r["profile"] == PROFILE_EMBAIXADOR


def test_fronteira_embaixador_89_vira_promotor():
    # 89 < 90 -> não embaixador; score 9 -> promotor (antes era indefinido)
    r = classify_profile(_customer(state="active_paying", days=89, score=9, voted=True))
    assert r["profile"] == PROFILE_ATIVO_PROMOTOR


def test_fronteira_ativo_recente_14_inclui():
    r = classify_profile(_customer(state="active_paying", days=14))
    assert r["profile"] == PROFILE_ATIVO_RECENTE


def test_fronteira_churn_rapido_7_inclui():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=7))
    assert r["profile"] == PROFILE_CHURN_RAPIDO


def test_fronteira_churn_rapido_8_vira_churn_outro():
    # 8 dias -> não rápido; USER_CANCEL <30 -> não pós-uso -> churn_outro (antes indefinido)
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=8))
    assert r["profile"] == PROFILE_CHURN_OUTRO


def test_fronteira_churn_pos_uso_30_inclui():
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=30))
    assert r["profile"] == PROFILE_CHURN_POS_USO


def test_fronteira_churn_pos_uso_29_vira_churn_outro():
    # 29 dias: nem rápido (>7) nem pós-uso (<30) -> churn_outro (antes indefinido)
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL", days=29))
    assert r["profile"] == PROFILE_CHURN_OUTRO


# ===================================== edge cases =====================================

def test_nps_ausente_active_paying_recente():
    c = {"subscription": {"state": "active_paying", "daysAsSubscriber": 3}}
    r = classify_profile(c)
    assert r["profile"] == PROFILE_ATIVO_RECENTE


def test_score_none_days_altos_vira_fiel():
    # days >= 90 mas score None -> ativo fiel (antes era indefinido)
    r = classify_profile(_customer(state="active_paying", days=120))
    assert r["profile"] == PROFILE_ATIVO_FIEL


def test_days_ausente_voted_false_silencioso():
    c = {"subscription": {"state": "active_paying"}, "nps": {"voted": False}}
    r = classify_profile(c)
    assert r["profile"] == PROFILE_ATIVO_SILENCIOSO


def test_days_ausente_churn_user_cancel_vira_churn_outro():
    # cancelled USER_CANCEL mas days None -> nem rápido nem pós-uso -> churn_outro
    r = classify_profile(_customer(state="cancelled", cancelled=True, reason="USER_CANCEL"))
    assert r["profile"] == PROFILE_CHURN_OUTRO


def test_active_paying_votou_sem_score_indefinido():
    # anômalo: voted True mas score None, days médio -> indefinido residual
    r = classify_profile(_customer(state="active_paying", days=50, voted=True))
    assert r["profile"] == PROFILE_INDEFINIDO and r["should_contact"] is False


def test_customer_vazio_indefinido():
    r = classify_profile({})
    assert r["profile"] == PROFILE_INDEFINIDO and r["should_contact"] is False


def test_subscription_none_nao_quebra():
    r = classify_profile({"subscription": None, "nps": None})
    assert r["profile"] == PROFILE_INDEFINIDO


def test_state_de_borda_indefinido_nao_contata():
    r = classify_profile(_customer(state="access_without_subscription"))
    assert r["profile"] == PROFILE_INDEFINIDO and r["should_contact"] is False


def test_resultado_tem_as_tres_chaves():
    r = classify_profile(_customer(state="active_paying", days=3))
    assert set(r.keys()) == {"profile", "reason", "should_contact"}
    assert isinstance(r["reason"], str) and r["reason"]


def test_funcao_e_pura_nao_muta_entrada():
    import copy
    c = _customer(state="active_paying", days=3)
    snapshot = copy.deepcopy(c)
    classify_profile(c)
    assert c == snapshot


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
