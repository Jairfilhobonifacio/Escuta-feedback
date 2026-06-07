"""Eventos de ciclo de vida vindos de sistemas dos clientes (PoC: Bizzu).

POST /api/events/bizzu — o backend da Bizzu (EscutaService no NestJS) envia
eventos como 'subscription_cancelled'; aqui casamos evento → survey ativa com
`trigger_event` correspondente e disparamos via WhatsApp.

Autenticação: HMAC-SHA256 do corpo CRU com segredo compartilhado
(BIZZU_WEBHOOK_SECRET), no formato assinatura = hmac(secret, f"{ts}.{body}").
Headers: X-Escuta-Timestamp (unix segundos) + X-Escuta-Signature (hex).
Timestamp fora da tolerância (5 min) é rejeitado (anti-replay básico);
`event_id` repetido vira no-op idempotente (dedupe via SurveyRun.trigger).

Respostas são SEMPRE 202 com {dispatched: bool, reason: ...} para o emissor
fire-and-forget não tratar erro de negócio como falha de entrega — exceto
autenticação (401/503) e payload malformado (422).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.dispatcher import SurveyDispatcher
from app.models.core import Contact, Organization
from app.models.survey import Survey, SurveyResponse, SurveyRun

# Reusa o provider real/injetável do admin (WAHA em prod, fake nos testes).
from app.api.admin import get_messaging

router = APIRouter(tags=["events"])

TIMESTAMP_TOLERANCE_SECONDS = 300
DISPATCH_COOLDOWN = timedelta(days=7)


class EventUser(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=200)
    phone: str = Field(min_length=8, max_length=32)
    whatsapp_opt_in: bool = False


class BizzuEvent(BaseModel):
    event: str = Field(min_length=1, max_length=120)          # ex.: subscription_cancelled
    event_id: str | None = Field(default=None, max_length=200)  # id p/ idempotência
    user: EventUser
    properties: dict[str, Any] = Field(default_factory=dict)


def _verify_signature(secret: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _skip(reason: str, **extra: Any) -> dict[str, Any]:
    return {"dispatched": False, "reason": reason, **extra}


@router.post("/events/bizzu", status_code=202)
async def bizzu_event(
    request: Request,
    session: AsyncSession = Depends(get_session),
    messaging: IMessagingService = Depends(get_messaging),
) -> dict[str, Any]:
    secret = settings.bizzu_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="integração Bizzu não configurada (BIZZU_WEBHOOK_SECRET)")

    timestamp = request.headers.get("X-Escuta-Timestamp", "")
    signature = request.headers.get("X-Escuta-Signature", "")
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="faltam X-Escuta-Timestamp/X-Escuta-Signature")

    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="timestamp inválido")
    if abs(time.time() - ts) > TIMESTAMP_TOLERANCE_SECONDS:
        raise HTTPException(status_code=401, detail="timestamp fora da tolerância")

    raw_body = await request.body()
    if not _verify_signature(secret, timestamp, raw_body, signature):
        raise HTTPException(status_code=401, detail="assinatura inválida")

    try:
        payload = BizzuEvent.model_validate_json(raw_body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    phone = re.sub(r"\D", "", payload.user.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="telefone inválido — use DDI+DDD+número")

    org = (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail=f"org '{settings.default_org_slug}' não encontrada (rode o seed)")

    # Evento → survey ativa configurada para ele (sem survey = integração "muda")
    survey = (
        await session.execute(
            select(Survey).where(
                Survey.organization_id == org.id,
                Survey.trigger_event == payload.event,
                Survey.status == "active",
            )
        )
    ).scalar_one_or_none()
    if survey is None:
        return _skip("no_survey", event=payload.event)

    # Idempotência: mesmo event_id já processado → no-op
    trigger = f"bizzu:{payload.event}:{payload.event_id or 'sem-id'}"
    if payload.event_id is not None:
        dup = (
            await session.execute(
                select(SurveyRun.id).where(
                    SurveyRun.organization_id == org.id, SurveyRun.trigger == trigger
                )
            )
        ).first()
        if dup is not None:
            return _skip("duplicate", event_id=payload.event_id)

    # Contato: get-or-create pelo telefone. Consentimento vem do emissor
    # (sistema do cliente é a fonte do opt-in); nunca rebaixamos aqui.
    contact = (
        await session.execute(
            select(Contact).where(Contact.organization_id == org.id, Contact.phone == phone)
        )
    ).scalar_one_or_none()
    if contact is None:
        contact = Contact(
            organization_id=org.id,
            phone=phone,
            name=(payload.user.name or "").strip() or None,
            opt_in=payload.user.whatsapp_opt_in,
            profile_data={"bizzu_user_id": payload.user.id},
        )
        session.add(contact)
        await session.flush()
    elif payload.user.whatsapp_opt_in and not contact.opt_in:
        contact.opt_in = True

    if not contact.opt_in:
        await session.commit()  # persiste o contato mesmo sem disparo
        return _skip("no_opt_in", phone=phone)

    # Cooldown: não reperguntar a mesma survey ao mesmo contato em < 7 dias
    cutoff = datetime.now(timezone.utc) - DISPATCH_COOLDOWN
    recent = (
        await session.execute(
            select(SurveyResponse.id)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .where(
                SurveyRun.survey_id == survey.id,
                SurveyResponse.contact_id == contact.id,
                SurveyResponse.sent_at >= cutoff,
            )
            .limit(1)
        )
    ).first()
    if recent is not None:
        await session.commit()
        return _skip("cooldown", phone=phone)

    dispatcher = SurveyDispatcher(
        session, org.id, messaging, whatsapp_session=settings.waha_session
    )
    run = await dispatcher.dispatch(survey, [contact], trigger=trigger)
    await session.commit()

    return {
        "dispatched": True,
        "run_id": str(run.id),
        "survey": survey.name,
        "phone": phone,
    }
