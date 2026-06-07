"""SurveyDispatcher — dispara a 1ª pergunta de uma survey para uma lista de contatos.

Fino de propósito (Fase 0). Espelha o padrão CampaignSend do Nexus: cria a linha
de estado por contato ANTES de enviar (idempotência via unique). Na Fase 1 isto
vira um "step de survey" dentro do campaign_worker real (agendamento + semaphore +
SELECT FOR UPDATE skip_locked).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.constants import STATUS_SENT
from app.models.core import Contact
from app.models.survey import Survey, SurveyRun, SurveyResponse


def _first_question_text(survey: Survey) -> str:
    for q in (survey.questions or []):
        if q.get("kind") == "nps":
            return q.get("text", "")
    # fallback
    return "De 0 a 10, o quanto você recomendaria a gente para um amigo?"


def _render(template: str, contact: Contact) -> str:
    nome = (contact.name or "").split(" ")[0] if contact.name else ""
    saudacao = f"Oi {nome}! " if nome else "Oi! "
    return saudacao + template


class SurveyDispatcher:
    def __init__(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        messaging: IMessagingService,
        whatsapp_session: str = "default",
        delay_seconds: float = 0.0,
    ):
        self.session = session
        self.org_id = organization_id
        self.messaging = messaging
        self.whatsapp_session = whatsapp_session
        self.delay_seconds = delay_seconds

    async def dispatch(self, survey: Survey, contacts: Iterable[Contact]) -> SurveyRun:
        now = datetime.now(timezone.utc)

        run = SurveyRun(
            survey_id=survey.id,
            organization_id=self.org_id,
            trigger="manual",
            status="running",
        )
        self.session.add(run)
        await self.session.flush()  # garante run.id

        question_text = _first_question_text(survey)

        for contact in contacts:
            resp = SurveyResponse(
                survey_run_id=run.id,
                contact_id=contact.id,
                organization_id=self.org_id,
                status=STATUS_SENT,
                sent_at=now,
            )
            self.session.add(resp)
            await self.session.flush()  # idempotência: UNIQUE(survey_run_id, contact_id)

            result = await self.messaging.send_text(
                chat_id=contact.phone,
                text=_render(question_text, contact),
                session=self.whatsapp_session,
            )
            # guarda o id da mensagem do canal, se houver
            msg_id = None
            if isinstance(result, dict):
                data = result.get("data") or {}
                msg_id = data.get("id") or result.get("id")
            # Engine WEBJS devolve o id como objeto ({"_serialized": "...", ...});
            # a coluna é VARCHAR, então normalizamos para a forma serializada.
            if isinstance(msg_id, dict):
                msg_id = msg_id.get("_serialized") or msg_id.get("id")
            resp.channel_msg_id = str(msg_id) if msg_id is not None else None

            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)

        run.status = "done"
        await self.session.flush()
        return run
