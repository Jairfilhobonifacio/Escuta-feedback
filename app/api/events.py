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
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.brain import SurveyBrain
from app.domain.survey.constants import STATUS_INGESTED
from app.domain.survey.dispatcher import SurveyDispatcher
from app.domain.feedback.ingest import ingest_feedback_item
from app.domain.survey.parsers import nps_bucket
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem
from app.models.survey import Survey, SurveyResponse, SurveyRun
from app.services.llm import GroqLLM

# Reusa o provider real/injetável do admin (WAHA em prod, fake nos testes).
from app.api.admin import get_messaging

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)

TIMESTAMP_TOLERANCE_SECONDS = 300
DISPATCH_COOLDOWN = timedelta(days=7)

# Eventos que viram FeedbackItem GENÉRICO (mega central) em vez de disparar survey.
# evento → (source, type). Manter sincronizado com os patches do backend.
GENERIC_EVENT_MAP: dict[str, tuple[str, str]] = {
    "question_reported": ("bizzu_app", "report"),
    "edital_requested": ("bizzu_platform", "edital_request"),
    "ticket_created": ("bizzu_support", "ticket"),
    # 'ticket_resolved' NÃO entra aqui: dispara a survey "CSAT Atendimento"
    # (trigger_event='ticket_resolved') via WhatsApp — a resposta vira SurveyResponse.
}

# Campos de properties que viram colunas próprias do FeedbackItem (não vão no extra).
_GENERIC_RESERVED = ("score", "text", "observacao", "comment", "reason", "occurred_at")

# Fase 2 (Playbooks): evento de ciclo de vida → gatilhos do motor a acionar inline.
# Conservador por ora: cancelamento já virou FeedbackItem(type='churn') antes daqui,
# então o gatilho 'churn_detected' encontra o candidato. Atrás da flag INLINE (OFF).
_EVENT_TRIGGER_MAP: dict[str, list[str]] = {
    "subscription_cancelled": ["churn_detected"],
}


class EventUser(BaseModel):
    id: str | None = Field(default=None, max_length=120)  # tickets públicos podem não ter userId
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


async def _classify_response(resp: SurveyResponse, survey_name: str) -> None:
    """Classifica o feedback textual (sentiment/themes/urgency) — best-effort.

    Espelha resolver._classify: nunca lança, nunca bloqueia o commit. Sem LLM
    ligado ou sem texto, vira no-op (a response fica apenas sem tags de IA).
    """
    if not (settings.llm_enabled and settings.groq_api_key and resp.answer_text):
        return
    try:
        brain = SurveyBrain(GroqLLM(settings.groq_api_key, settings.groq_model))
        tags = await brain.classify_feedback(resp.answer_text, resp.answer_score, survey_name)
    except Exception:  # noqa: BLE001 — IA é enriquecedor, nunca ponto de falha.
        logger.warning("classify ingest falhou — seguindo sem tags", exc_info=True)
        return
    if tags is None:
        return
    resp.sentiment = tags.sentiment
    resp.themes = tags.themes
    resp.ai_meta = {**(resp.ai_meta or {}), "urgency": tags.urgency}


async def _ingest_response(
    session: AsyncSession,
    org: Organization,
    survey: Survey,
    payload: BizzuEvent,
    contact: Contact,
    trigger: str,
) -> dict[str, Any]:
    """Registra uma resposta JÁ respondida no app (ex.: NPS in-app), sem disparo WA.

    Diferente do caminho normal: não exige opt-in (não há envio), não respeita
    cooldown (não é repergunta) e cria a response já fechada (status='ingested')
    com a nota/comentário vindos em `properties`. Classifica o comentário por IA
    (best-effort). NUNCA instancia o SurveyDispatcher → impossível tocar o WAHA.
    """
    now = datetime.now(timezone.utc)

    score_raw = payload.properties.get("score")
    score = int(score_raw) if isinstance(score_raw, (int, float)) else None
    comment_raw = payload.properties.get("comment")
    comment = str(comment_raw).strip()[:2000] if comment_raw else None

    run = SurveyRun(
        survey_id=survey.id,
        organization_id=org.id,
        trigger=trigger,
        status="done",
    )
    session.add(run)
    await session.flush()  # garante run.id

    resp = SurveyResponse(
        survey_run_id=run.id,
        contact_id=contact.id,
        organization_id=org.id,
        status=STATUS_INGESTED,
        answer_score=score,
        nps_bucket=nps_bucket(score),
        answer_text=comment,
        source="in_app",
        sent_at=now,       # alimenta o cooldown de surveys WA distintas, se houver
        answered_at=now,
        closed_at=now,
    )
    session.add(resp)
    await session.flush()  # idempotência: UNIQUE(survey_run_id, contact_id)

    await _classify_response(resp, survey.name)

    await session.commit()
    return {
        "dispatched": False,
        "ingested": True,
        "response_id": str(resp.id),
        "survey": survey.name,
        "phone": contact.phone,
    }


async def _get_or_create_contact(
    session: AsyncSession, org: Organization, payload: "BizzuEvent", phone: str
) -> Contact:
    """get-or-create do contato pelo telefone; eleva opt-in se o emissor sinalizar.
    Consentimento vem do emissor (sistema do cliente é a fonte do opt-in); nunca rebaixamos aqui."""
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
    return contact


async def _ingest_generic_event(
    session: AsyncSession, org: Organization, payload: "BizzuEvent", phone: str
) -> dict[str, Any]:
    """Evento genérico (ticket/report/edital) → FeedbackItem na mega central.

    Não dispara survey nem exige opt-in (não há envio). Idempotente por external_id
    quando há event_id. Classifica o texto por IA (best-effort, via ingestor).
    """
    source, ftype = GENERIC_EVENT_MAP[payload.event]
    external_id = f"bizzu:{payload.event}:{payload.event_id}" if payload.event_id else None

    if external_id is not None:
        dup = (
            await session.execute(
                select(FeedbackItem.id).where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.external_id == external_id,
                )
            )
        ).first()
        if dup is not None:
            return _skip("duplicate", event_id=payload.event_id)

    contact = await _get_or_create_contact(session, org, payload, phone)

    props = payload.properties or {}
    spec = {
        "source": source,
        "type": ftype,
        "external_id": external_id,
        "score": props.get("score"),
        "text": props.get("text") or props.get("observacao") or props.get("comment") or props.get("reason"),
        "occurred_at": props.get("occurred_at"),
        "extra": {
            "bizzu_user_id": payload.user.id,
            "event": payload.event,
            "event_id": payload.event_id,
            **{k: v for k, v in props.items() if k not in _GENERIC_RESERVED},
        },
    }
    item = await ingest_feedback_item(session, org.id, contact.id, spec, classify=True)
    await session.commit()
    return {
        "dispatched": False,
        "ingested": True,
        "feedback_id": str(item.id),
        "source": source,
        "type": ftype,
        "phone": phone,
    }


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

    # Eventos genéricos (ticket/report/edital) → FeedbackItem direto (mega central),
    # sem procurar survey nem disparar WhatsApp.
    if payload.event in GENERIC_EVENT_MAP:
        return await _ingest_generic_event(session, org, payload, phone)

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

    # Contato: get-or-create pelo telefone (helper compartilhado com o ingest genérico).
    contact = await _get_or_create_contact(session, org, payload, phone)

    # Modo ingest (ex.: NPS in-app): a resposta já veio respondida do app —
    # registra+classifica e retorna, sem opt-in/cooldown/disparo no WhatsApp.
    if survey.ingest_mode:
        return await _ingest_response(session, org, survey, payload, contact, trigger)

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

    # Fase 2 (Playbooks): plugue INLINE do motor, atrás de flag (default OFF) e
    # best-effort — roda os playbooks cujo gatilho casa com o evento recebido (ex.:
    # 'churn_detected' num 'subscription_cancelled'). NUNCA derruba o endpoint.
    await _maybe_run_playbooks_inline(session, org.id, payload.event, messaging)

    return {
        "dispatched": True,
        "run_id": str(run.id),
        "survey": survey.name,
        "phone": phone,
    }


async def _maybe_run_playbooks_inline(
    session: AsyncSession,
    org_id: "uuid.UUID",
    event: str,
    messaging: IMessagingService,
) -> None:
    """Roda o motor de Playbooks atrás de `PLAYBOOKS_INLINE_ENABLED` (default OFF).

    Com a flag OFF é no-op — o motor só roda via POST /api/playbooks/run. Com ON,
    aciona o motor (dry_run=False) restrito aos gatilhos mapeados pelo evento. O
    mapeamento é conservador (só churn por ora); demais eventos não acionam nada.
    Best-effort: try/except que loga e engole — o endpoint de eventos nunca cai.
    """
    if not settings.playbooks_inline_enabled:
        return
    triggers = _EVENT_TRIGGER_MAP.get(event)
    if not triggers:
        return
    try:
        from app.domain.cs.engine import run_playbooks

        await run_playbooks(session, org_id, triggers=triggers, dry_run=False, messaging=messaging)
    except Exception:  # noqa: BLE001 — motor é enriquecedor, nunca ponto de falha.
        logger.warning("playbooks inline (events): falhou — seguindo", exc_info=True)
