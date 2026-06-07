"""API do painel (Fase 1) — dashboard, surveys, contatos e disparo.

Mesma filosofia do webhook da Fase 0: org única resolvida pelo slug default
(multi-tenant pleno fica para quando houver auth). Todos os endpoints filtram
por `organization_id`.

Sem mocks: o disparo usa o WAHA real via `get_messaging` (injetável nos testes).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.dispatcher import SurveyDispatcher
from app.models.core import Contact, Organization
from app.models.survey import Survey, SurveyResponse, SurveyRun
from app.services.waha import WAHAService

router = APIRouter(tags=["admin"])


def get_messaging() -> IMessagingService:
    """Canal de envio real (WAHA). Substituível via dependency_overrides nos testes."""
    return WAHAService(settings.waha_base_url, settings.waha_api_key, settings.waha_session)


async def _get_org(session: AsyncSession) -> Organization:
    org = (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail=f"org '{settings.default_org_slug}' não encontrada (rode o seed)")
    return org


# --- Dashboard -------------------------------------------------------------


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _get_org(session)

    total = (
        await session.execute(
            select(func.count()).select_from(SurveyResponse).where(SurveyResponse.organization_id == org.id)
        )
    ).scalar_one()

    by_bucket = dict(
        (
            await session.execute(
                select(SurveyResponse.nps_bucket, func.count())
                .where(SurveyResponse.organization_id == org.id, SurveyResponse.answer_score.is_not(None))
                .group_by(SurveyResponse.nps_bucket)
            )
        ).all()
    )
    promoters = by_bucket.get("promoter", 0)
    passives = by_bucket.get("passive", 0)
    detractors = by_bucket.get("detractor", 0)
    answered = promoters + passives + detractors

    closed = (
        await session.execute(
            select(func.count())
            .select_from(SurveyResponse)
            .where(SurveyResponse.organization_id == org.id, SurveyResponse.status == "closed")
        )
    ).scalar_one()

    nps = round(((promoters - detractors) / answered) * 100) if answered else None

    recent_rows = (
        await session.execute(
            select(SurveyResponse, Contact)
            .join(Contact, Contact.id == SurveyResponse.contact_id)
            .where(SurveyResponse.organization_id == org.id)
            .order_by(SurveyResponse.sent_at.desc())
            .limit(20)
        )
    ).all()

    return {
        "org": {"slug": org.slug, "name": org.name},
        "kpis": {
            "sent": total,
            "answered": answered,
            "closed": closed,
            "response_rate": round(answered / total * 100) if total else None,
            "nps": nps,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
        },
        "recent": [
            {
                "id": str(r.id),
                "contact_name": c.name,
                "contact_phone": c.phone,
                "status": r.status,
                "score": r.answer_score,
                "bucket": r.nps_bucket,
                "text": r.answer_text,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            }
            for r, c in recent_rows
        ],
    }


# --- Surveys ----------------------------------------------------------------


class SurveyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    nps_question: str = Field(min_length=1, max_length=500)
    reason_prompt: str = Field(min_length=1, max_length=500)


def _survey_out(s: Survey) -> dict[str, Any]:
    nps_q = next((q.get("text") for q in (s.questions or []) if q.get("kind") == "nps"), None)
    reason_q = next((q.get("text") for q in (s.questions or []) if q.get("kind") == "open"), None)
    return {
        "id": str(s.id),
        "name": s.name,
        "type": s.type,
        "status": s.status,
        "nps_question": nps_q,
        "reason_prompt": reason_q,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/surveys")
async def list_surveys(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    org = await _get_org(session)
    rows = (
        (
            await session.execute(
                select(Survey).where(Survey.organization_id == org.id).order_by(Survey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_survey_out(s) for s in rows]


@router.post("/surveys", status_code=201)
async def create_survey(body: SurveyIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _get_org(session)
    exists = (
        await session.execute(
            select(Survey).where(Survey.organization_id == org.id, Survey.name == body.name)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"já existe uma pesquisa chamada '{body.name}'")

    survey = Survey(
        organization_id=org.id,
        name=body.name,
        type="nps",
        status="active",
        questions=[
            {"key": "nps", "kind": "nps", "text": body.nps_question},
            {"key": "reason", "kind": "open", "text": body.reason_prompt},
        ],
    )
    session.add(survey)
    await session.commit()
    return _survey_out(survey)


# --- Contatos ----------------------------------------------------------------


class ContactIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    name: str | None = Field(default=None, max_length=120)


@router.get("/contacts")
async def list_contacts(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    org = await _get_org(session)
    rows = (
        (
            await session.execute(
                select(Contact).where(Contact.organization_id == org.id).order_by(Contact.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(c.id),
            "phone": c.phone,
            "name": c.name,
            "opt_in": c.opt_in,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.post("/contacts", status_code=201)
async def create_contact(body: ContactIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _get_org(session)
    phone = re.sub(r"\D", "", body.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="telefone inválido — use DDI+DDD+número, só dígitos")

    exists = (
        await session.execute(
            select(Contact).where(Contact.organization_id == org.id, Contact.phone == phone)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"contato {phone} já existe")

    contact = Contact(
        organization_id=org.id,
        phone=phone,
        name=(body.name or "").strip() or None,
        opt_in=True,
        profile_data={},
    )
    session.add(contact)
    await session.commit()
    return {"id": str(contact.id), "phone": contact.phone, "name": contact.name, "opt_in": contact.opt_in}


# --- Disparo ------------------------------------------------------------------


class DispatchIn(BaseModel):
    contact_ids: list[str] = Field(min_length=1)


@router.post("/surveys/{survey_id}/dispatch")
async def dispatch_survey(
    survey_id: str,
    body: DispatchIn,
    session: AsyncSession = Depends(get_session),
    messaging: IMessagingService = Depends(get_messaging),
) -> dict[str, Any]:
    org = await _get_org(session)

    try:
        sid = uuid.UUID(survey_id)
        cids = [uuid.UUID(c) for c in body.contact_ids]
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    survey = (
        await session.execute(
            select(Survey).where(Survey.id == sid, Survey.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if survey is None:
        raise HTTPException(status_code=404, detail="pesquisa não encontrada")
    if survey.status != "active":
        raise HTTPException(status_code=409, detail=f"pesquisa está '{survey.status}', não 'active'")

    contacts = (
        (
            await session.execute(
                select(Contact).where(Contact.id.in_(cids), Contact.organization_id == org.id)
            )
        )
        .scalars()
        .all()
    )
    if len(contacts) != len(cids):
        raise HTTPException(status_code=404, detail="um ou mais contatos não encontrados")
    no_opt_in = [c.phone for c in contacts if not c.opt_in]
    if no_opt_in:
        raise HTTPException(status_code=409, detail=f"sem opt-in: {', '.join(no_opt_in)}")

    dispatcher = SurveyDispatcher(
        session, org.id, messaging, whatsapp_session=settings.waha_session, delay_seconds=1.0
    )
    run = await dispatcher.dispatch(survey, contacts)
    await session.commit()

    return {
        "run_id": str(run.id),
        "survey": survey.name,
        "dispatched_to": [{"phone": c.phone, "name": c.name} for c in contacts],
        "count": len(contacts),
    }
