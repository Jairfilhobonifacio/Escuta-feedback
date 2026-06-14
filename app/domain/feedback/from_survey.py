"""Ponte SurveyResponse → FeedbackItem (mega central).

`SurveyResponse` é a resposta COLETADA pelo Escuta (pesquisa via WhatsApp);
`FeedbackItem` é o registro genérico do inbox de monitoramento (Visão 360 +
clustering). Esta ponte leva toda resposta JÁ respondida/fechada para o inbox,
para que as respostas reais das pesquisas apareçam ao lado dos sinais ingeridos
da API de Clientes (NPS in-app / churn).

Usada nos DOIS pontos para garantir a MESMA lógica (sem duplicar):
- backfill (scripts/backfill_survey_feedback.py) — respostas já existentes;
- resolver (app/domain/survey/resolver.py) — no fechamento, daqui pra frente.

Idempotente por `external_id` = "survey_response:<uuid>" (1 FeedbackItem por
resposta). A classificação por IA (sentiment/themes/urgency) é REUSADA do que o
resolver já computou no fechamento — NÃO chama LLM de novo (classify=False).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.feedback.ingest import ingest_feedback_item
from app.models.feedback import FeedbackItem
from app.models.survey import SurveyResponse


def survey_external_id(response_id: uuid.UUID | str) -> str:
    """Chave de idempotência estável de uma resposta de pesquisa na mega central."""
    return f"survey_response:{response_id}"


def survey_feedback_spec(response: SurveyResponse) -> dict[str, Any]:
    """Monta o spec de FeedbackItem a partir de uma SurveyResponse (PURA, sem I/O).

    - source = 'whatsapp' (canal da coleta).
    - type   = 'nps' se há nota; senão 'outro' (resposta só-texto/exit sem nota).
    - score/nps_bucket/text/sentiment/themes vêm da própria resposta.
    - occurred_at = quando respondeu/fechou (answered_at > closed_at).
    - ai_meta carrega urgency + a origem (survey_response_id, run, status).
    """
    has_score = response.answer_score is not None
    occurred_at = response.answered_at or response.closed_at

    ai_meta: dict[str, Any] = {
        "survey_response_id": str(response.id),
        "survey_run_id": str(response.survey_run_id),
        "survey_status": response.status,
        "survey_source": response.source,
    }
    # Preserva o enriquecimento já feito pelo resolver no fechamento (sem re-LLM).
    src_meta = response.ai_meta or {}
    if src_meta.get("urgency") is not None:
        ai_meta["urgency"] = src_meta["urgency"]

    return {
        "source": "whatsapp",
        "type": "nps" if has_score else "outro",
        "external_id": survey_external_id(response.id),
        "score": response.answer_score,
        "nps_bucket": response.nps_bucket,
        "text": response.answer_text,
        "sentiment": response.sentiment,
        "themes": response.themes,
        "ai_meta": ai_meta,
        "occurred_at": occurred_at,
        "extra": {"origin": "survey_response"},
    }


async def feedback_from_survey_response(
    session: AsyncSession,
    response: SurveyResponse,
) -> FeedbackItem:
    """Cria/atualiza o FeedbackItem correspondente a uma SurveyResponse (idempotente).

    Reusa o upsert por external_id de `ingest_feedback_item`. `classify=False`:
    a IA já rodou no fechamento da pesquisa — só copiamos o resultado, sem nova
    chamada ao LLM (custo + latência no webhook).
    """
    spec = survey_feedback_spec(response)
    return await ingest_feedback_item(
        session,
        response.organization_id,
        response.contact_id,
        spec,
        classify=False,
    )
