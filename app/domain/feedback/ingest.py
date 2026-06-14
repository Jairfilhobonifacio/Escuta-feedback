"""Ingestor da Mega Central: cria/atualiza um FeedbackItem (dedup + classificação IA).

É o ponto único por onde TODA fonte entra na central — hoje a API de Clientes
(pull); amanhã eventos de ticket/report/edital (push). Idempotente por
`external_id`: re-ingerir o mesmo sinal ATUALIZA (snapshot pode mudar — ex.: motivo
de churn) em vez de duplicar. Classificação por IA é best-effort (nunca bloqueia).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.survey.parsers import nps_bucket
from app.models.feedback import FeedbackItem

logger = logging.getLogger(__name__)

_SCORED_TYPES = ("nps", "csat")


def _parse_dt(value: Any) -> datetime | None:
    """ISO-8601 (str da API) → datetime aware; tolera None/objeto/valor inválido."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _classify(item: FeedbackItem) -> None:
    """Sentimento/tema/urgência via LLM — best-effort, nunca lança."""
    if not (settings.llm_enabled and settings.groq_api_key and item.text):
        return
    try:
        from app.domain.survey.brain import SurveyBrain
        from app.services.llm import GroqLLM

        brain = SurveyBrain(GroqLLM(settings.groq_api_key, settings.groq_model))
        tags = await brain.classify_feedback(item.text, item.score, f"{item.source}:{item.type}")
    except Exception:  # noqa: BLE001 — IA é enriquecedor, nunca ponto de falha.
        logger.warning("feedback classify falhou — seguindo sem tags", exc_info=True)
        return
    if tags is None:
        return
    item.sentiment = tags.sentiment
    item.themes = tags.themes
    item.ai_meta = {**(item.ai_meta or {}), "urgency": tags.urgency}


async def ingest_feedback_item(
    session: AsyncSession,
    organization_id: uuid.UUID,
    contact_id: uuid.UUID | None,
    spec: dict[str, Any],
    *,
    classify: bool = True,
) -> FeedbackItem:
    """Cria OU atualiza um FeedbackItem a partir de um spec (dedup por external_id).

    `classify=False` pula a IA (útil em sync de lote — 233 clientes não viram 233
    chamadas LLM; a classificação pode ser feita depois sob demanda).
    """
    score = spec.get("score")
    score = int(score) if isinstance(score, (int, float)) else None
    text = spec.get("text")
    text = (str(text).strip() or None) if text else None
    occurred_at = _parse_dt(spec.get("occurred_at"))
    external_id = spec.get("external_id")
    # bucket: usa o do spec se já vier pronto (ex.: ponte SurveyResponse, que já
    # classificou a nota); senão deriva da nota para os tipos pontuados.
    bucket = spec.get("nps_bucket")
    if bucket is None and spec.get("type") in _SCORED_TYPES:
        bucket = nps_bucket(score)
    # Enriquecimento JÁ computado pela fonte (sentiment/themes/urgency) — aplicado
    # sem chamar o LLM. Ausência = None (não sobrescreve com vazio sem querer).
    pre_sentiment = spec.get("sentiment")
    pre_themes = spec.get("themes")
    pre_ai_meta = spec.get("ai_meta")

    existing = None
    if external_id:
        existing = (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.organization_id == organization_id,
                    FeedbackItem.external_id == external_id,
                )
            )
        ).scalar_one_or_none()

    if existing is not None:
        text_changed = (existing.text or None) != text
        if contact_id is not None:
            existing.contact_id = contact_id
        existing.score = score
        existing.nps_bucket = bucket
        existing.text = text
        if occurred_at is not None:
            existing.occurred_at = occurred_at
        if spec.get("extra") is not None:
            existing.extra = spec["extra"]
        # Enriquecimento pré-pronto da fonte refresca o snapshot (sem LLM).
        if pre_sentiment is not None:
            existing.sentiment = pre_sentiment
        if pre_themes is not None:
            existing.themes = pre_themes
        if pre_ai_meta is not None:
            existing.ai_meta = {**(existing.ai_meta or {}), **pre_ai_meta}
        if classify and text_changed:
            await _classify(existing)
        await session.flush()
        return existing

    item = FeedbackItem(
        organization_id=organization_id,
        contact_id=contact_id,
        source=spec["source"],
        type=spec["type"],
        external_id=external_id,
        score=score,
        nps_bucket=bucket,
        text=text,
        sentiment=pre_sentiment,
        themes=pre_themes,
        ai_meta=pre_ai_meta,
        occurred_at=occurred_at,
        extra=spec.get("extra"),
    )
    session.add(item)
    await session.flush()
    if classify:
        await _classify(item)
        await session.flush()
    return item
