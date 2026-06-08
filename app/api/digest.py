"""Endpoint do digest semanal — preview e disparo.

GET  /api/digest/preview  → monta o texto (não envia); para o painel/conferência.
POST /api/digest/run      → monta e ENVIA ao dono; ponto de entrada de um cron
                            (Modal/n8n) na Fase 1. Sem owner_phone, responde o
                            texto com sent=false (não é erro).

Org única do piloto (slug default), como o resto da API de Fase 0.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.domain.digest.service import build_digest, send_digest
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.brain import SurveyBrain
from app.models.core import Organization
from app.services.llm import GroqLLM
from app.services.waha import WAHAService

router = APIRouter(tags=["digest"])

DEFAULT_DAYS = 7


def _brain() -> SurveyBrain | None:
    if not settings.llm_enabled or not settings.groq_api_key:
        return None
    return SurveyBrain(GroqLLM(settings.groq_api_key, settings.groq_model))


def get_messaging() -> IMessagingService:
    return WAHAService(settings.waha_base_url, settings.waha_api_key, settings.waha_session)


async def _org(session: AsyncSession) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.slug == settings.default_org_slug))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail=f"org '{settings.default_org_slug}' não encontrada")
    return org


@router.get("/digest/preview")
async def digest_preview(days: int = DEFAULT_DAYS, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _org(session)
    text, data = await build_digest(session, org.id, _brain(), days)
    return {"text": text, "data": data.as_dict()}


@router.post("/digest/run")
async def digest_run(
    days: int = DEFAULT_DAYS,
    session: AsyncSession = Depends(get_session),
    messaging: IMessagingService = Depends(get_messaging),
) -> dict[str, Any]:
    org = await _org(session)
    result = await send_digest(session, org.id, _brain(), messaging, days, settings.waha_session)
    await session.commit()
    return result
