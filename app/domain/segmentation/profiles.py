"""Classificação de clientes da Bizzu em PERFIS de feedback (função pura).

Implementa a "árvore de perfis" da reunião (doc `docs/analise-bizzu/api-clientes-partner.md` §3),
derivada 100% dos campos da API de Clientes (PartnerCustomer). É PURA: sem I/O, sem
estado, sem efeitos colaterais — só lê o dict de entrada e devolve um dict.

Entrada: um PartnerCustomer (dict da API). Campos lidos (todos tolerantes a ausência):
  - subscription{state, active, cancelled, complimentary, cancellationReason,
                 daysAsSubscriber, startedAt, cancelledAt}
  - nps{voted, score}

Saída: {"profile": str, "reason": str, "should_contact": bool}.

PRECEDÊNCIA (load-bearing — avaliada NESTA ORDEM, primeira regra que casa vence):

  TERMINAIS (qualquer state):
  1. Cortesia            (complimentary == True)
  2. Churn involuntário  (cancellationReason == PAYMENT_FAILED) -> should_contact=False (winback e-mail)
  3. Churn rápido        (GUARANTEE_REFUND, OU cancelado <= 7 dias do startedAt)
  4. Churn pós-uso       (cancelled + USER_CANCEL + daysAsSubscriber >= 30)
  5. Vai expirar         (state in {cancelled_with_access, past_due})
  6. Churn outro         (cancelled que não casou 2-5: reason OTHER, ou zona cinza 8-29 dias)

  ATIVOS (state == active_paying), nesta ordem:
  7.  Embaixador         (daysAsSubscriber >= 90 + nps.score >= 9)      fiel + promotor
  8.  Ativo em risco     (nps.score <= 6)                                detrator (urgente)
  9.  Ativo promotor     (nps.score >= 9, days < 90)                     promotor recente
  10. Ativo passivo      (nps.score 7-8)                                 votou, neutro
  11. Ativo recente      (daysAsSubscriber <= 14, sem nota)              onboarding
  12. Ativo silencioso   (nps.voted == False, sem nota)                  nunca opinou
  13. Ativo fiel         (daysAsSubscriber >= 90, sem nota)              fiel por tempo
  0.  Indefinido         (caso anômalo residual — should_contact=False)

A taxonomia é exaustiva por construção: todo cancelado cai em 2-6; todo active_paying cai
em 7-13; só sobra "indefinido" para estados de borda raros (access_without_subscription) ou
dados anômalos (votou sem score). Refinamento de 2026-06-09 (eliminou ~23% de indefinidos).
"""
from __future__ import annotations

from typing import Any

# Rótulos de perfil (strings estáveis — gravadas em profile_data e usadas em relatórios).
PROFILE_CORTESIA = "cortesia"
PROFILE_CHURN_INVOLUNTARIO = "churn_involuntario"
PROFILE_CHURN_RAPIDO = "churn_rapido"
PROFILE_CHURN_POS_USO = "churn_pos_uso"
PROFILE_CHURN_OUTRO = "churn_outro"
PROFILE_VAI_EXPIRAR = "vai_expirar"
PROFILE_EMBAIXADOR = "embaixador"
PROFILE_ATIVO_EM_RISCO = "ativo_em_risco"
PROFILE_ATIVO_PROMOTOR = "ativo_promotor"
PROFILE_ATIVO_PASSIVO = "ativo_passivo"
PROFILE_ATIVO_RECENTE = "ativo_recente"
PROFILE_ATIVO_SILENCIOSO = "ativo_silencioso"
PROFILE_ATIVO_FIEL = "ativo_fiel"
PROFILE_INDEFINIDO = "indefinido"

# Reasons de cancelamento conhecidos (doc §3).
REASON_PAYMENT_FAILED = "PAYMENT_FAILED"
REASON_GUARANTEE_REFUND = "GUARANTEE_REFUND"
REASON_USER_CANCEL = "USER_CANCEL"

# States (doc §1).
STATE_ACTIVE_PAYING = "active_paying"
STATE_CANCELLED_WITH_ACCESS = "cancelled_with_access"
STATE_PAST_DUE = "past_due"

# Fronteiras.
DAYS_FIEL = 90          # embaixador / ativo fiel
DAYS_ATIVO_RECENTE = 14
DAYS_CHURN_POS_USO = 30
DAYS_CHURN_RAPIDO = 7
SCORE_PROMOTOR = 9      # nps >= 9
SCORE_DETRATOR = 6      # nps <= 6


def _result(profile: str, reason: str, should_contact: bool) -> dict[str, Any]:
    return {"profile": profile, "reason": reason, "should_contact": should_contact}


def classify_profile(customer: dict) -> dict:
    """Classifica um PartnerCustomer em {profile, reason, should_contact}. PURA.

    Tolerante a campos ausentes: subscription/nps podem faltar; score/daysAsSubscriber
    podem ser None. Nunca lança por campo ausente.
    """
    sub = customer.get("subscription") or {}
    nps = customer.get("nps") or {}

    state = sub.get("state")
    cancellation_reason = sub.get("cancellationReason")
    complimentary = bool(sub.get("complimentary"))
    cancelled = bool(sub.get("cancelled"))

    days_raw = sub.get("daysAsSubscriber")
    days = days_raw if isinstance(days_raw, (int, float)) else None  # None = ausente/desconhecido

    score_raw = nps.get("score")
    score = score_raw if isinstance(score_raw, (int, float)) else None  # None = sem nota
    voted = nps.get("voted")  # True/False/None

    # ================================ TERMINAIS (qualquer state) ================================

    # 1. Cortesia (pode estar "active" mas não paga -> antes de tudo).
    if complimentary:
        return _result(PROFILE_CORTESIA, "subscription.complimentary == true", should_contact=True)

    # 2. Churn involuntário — antes dos demais churns p/ não roubar PAYMENT_FAILED deles.
    if cancellation_reason == REASON_PAYMENT_FAILED:
        return _result(
            PROFILE_CHURN_INVOLUNTARIO,
            "cancellationReason == PAYMENT_FAILED (já recebe winback por e-mail)",
            should_contact=False,
        )

    # 3. Churn rápido — GUARANTEE_REFUND, ou cancelou em <= 7 dias.
    fast_by_days = cancelled and (days is not None and days <= DAYS_CHURN_RAPIDO)
    if cancellation_reason == REASON_GUARANTEE_REFUND or fast_by_days:
        motivo = (
            "cancellationReason == GUARANTEE_REFUND"
            if cancellation_reason == REASON_GUARANTEE_REFUND
            else f"cancelled + daysAsSubscriber <= {DAYS_CHURN_RAPIDO}"
        )
        return _result(PROFILE_CHURN_RAPIDO, motivo, should_contact=True)

    # 4. Churn pós-uso — cancelou voluntariamente depois de usar (>= 30 dias).
    if (
        cancelled
        and cancellation_reason == REASON_USER_CANCEL
        and days is not None
        and days >= DAYS_CHURN_POS_USO
    ):
        return _result(
            PROFILE_CHURN_POS_USO,
            f"cancelled + USER_CANCEL + daysAsSubscriber >= {DAYS_CHURN_POS_USO}",
            should_contact=True,
        )

    # 5. Vai expirar — past_due / cancelled_with_access (ainda com acesso).
    if state in (STATE_CANCELLED_WITH_ACCESS, STATE_PAST_DUE):
        return _result(
            PROFILE_VAI_EXPIRAR,
            f"state == {state} (ainda com acesso, reter antes de perder)",
            should_contact=True,
        )

    # 6. Churn outro — cancelado que não casou 2-5 (reason OTHER, ou zona cinza 8-29 dias).
    if cancelled:
        return _result(
            PROFILE_CHURN_OUTRO,
            f"cancelled sem classificação específica (reason={cancellation_reason!r}, days={days})",
            should_contact=True,
        )

    # ============================ ATIVOS (state == active_paying) ============================
    if state == STATE_ACTIVE_PAYING:
        # 7. Embaixador — fiel (>=90d) + promotor (>=9).
        if days is not None and days >= DAYS_FIEL and score is not None and score >= SCORE_PROMOTOR:
            return _result(
                PROFILE_EMBAIXADOR,
                f"active_paying + daysAsSubscriber >= {DAYS_FIEL} + nps.score >= {SCORE_PROMOTOR}",
                should_contact=True,
            )
        # 8. Ativo em risco (detrator) — nota baixa, prioridade (pode virar churn).
        if score is not None and score <= SCORE_DETRATOR:
            return _result(
                PROFILE_ATIVO_EM_RISCO,
                f"active_paying + nps.score <= {SCORE_DETRATOR} (detrator)",
                should_contact=True,
            )
        # 9. Ativo promotor — nota >= 9 mas ainda não fiel por tempo (< 90d).
        if score is not None and score >= SCORE_PROMOTOR:
            return _result(
                PROFILE_ATIVO_PROMOTOR,
                f"active_paying + nps.score >= {SCORE_PROMOTOR} (promotor, days < {DAYS_FIEL})",
                should_contact=True,
            )
        # 10. Ativo passivo — votou neutro (7-8). (9+ e <=6 já tratados acima.)
        if score is not None:
            return _result(
                PROFILE_ATIVO_PASSIVO,
                f"active_paying + nps.score == {int(score)} (passivo 7-8)",
                should_contact=True,
            )
        # 11. Ativo recente — janela de ativação, ainda sem nota.
        if days is not None and days <= DAYS_ATIVO_RECENTE:
            return _result(
                PROFILE_ATIVO_RECENTE,
                f"active_paying + daysAsSubscriber <= {DAYS_ATIVO_RECENTE} (sem nota)",
                should_contact=True,
            )
        # 12. Ativo silencioso — nunca votou no NPS.
        if voted is False:
            return _result(
                PROFILE_ATIVO_SILENCIOSO,
                "active_paying + nps.voted == false (nunca opinou)",
                should_contact=True,
            )
        # 13. Ativo fiel — muito tempo de casa, sem nota conclusiva.
        if days is not None and days >= DAYS_FIEL:
            return _result(
                PROFILE_ATIVO_FIEL,
                f"active_paying + daysAsSubscriber >= {DAYS_FIEL} (fiel por tempo, sem nota)",
                should_contact=True,
            )
        # 0. Anômalo residual (ex.: votou sem score; days médio + voted desconhecido).
        return _result(
            PROFILE_INDEFINIDO,
            "active_paying anômalo (sem nota e days médio / voted desconhecido)",
            should_contact=False,
        )

    # ------------------------------------------------------------- 0. Fallback (borda)
    # access_without_subscription / paid_without_access / state desconhecido.
    return _result(
        PROFILE_INDEFINIDO,
        f"sem regra para state={state!r} reason={cancellation_reason!r}",
        should_contact=False,
    )
