"""SurveyContextResolver — casa resposta inbound ↔ pergunta ↔ pessoa.

Plumbing de banco apenas; a decisão fica em logic.decide_next (pura/testável).

Fase 0: usado no caminho inbound enxuto (webhook → resolver). Fase 1: injetado
em `orchestrator._process_message_internal` ENTRE behaviors (≈L217) e RAG (≈L219),
retornando cedo para atalhar o LLM quando a mensagem é resposta de pesquisa.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.survey.constants import STATUS_SENT, STATUS_AWAITING_REASON, STATUS_CLOSED
from app.domain.survey.logic import decide_next
from app.models.survey import Survey, SurveyRun, SurveyResponse

DEFAULT_WINDOW = timedelta(hours=24)

# Templates default (usados se o survey não definir os textos)
DEFAULT_REASON_PROMPT = "Massa! 🙌 Por quê? (pode mandar em texto)"
DEFAULT_THANKS_MSG = "Valeu demais pelo retorno! 🙏 Anotado por aqui."
DEFAULT_RETRY_MSG = "Quase! Me manda só um número de 0 a 10 🙂"


@dataclass
class SurveyReply:
    """Resposta que o canal deve enviar de volta ao contato."""
    text: str
    survey_response_id: str
    closed: bool = False


class SurveyContextResolver:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID, window: timedelta = DEFAULT_WINDOW):
        self.session = session
        self.org_id = organization_id
        self.window = window

    async def resolve(self, contact_id: uuid.UUID, message: str) -> Optional[SurveyReply]:
        """Retorna o que responder, ou None se o contato não tem pesquisa pendente."""
        now = datetime.now(timezone.utc)

        pending = await self._find_pending(contact_id, now)
        if pending is None:
            return None

        reason_prompt, thanks_msg, retry_msg = await self._prompts(pending.survey_run_id)

        decision = decide_next(
            pending.status,
            message,
            reason_prompt=reason_prompt,
            thanks_msg=thanks_msg,
            retry_msg=retry_msg,
        )
        if decision is None:
            return None

        # Aplica a decisão à linha pendente
        pending.status = decision.new_status
        if decision.answer_score is not None:
            pending.answer_score = decision.answer_score
            pending.nps_bucket = decision.nps_bucket
            pending.answered_at = now
        if decision.answer_text is not None:
            pending.answer_text = decision.answer_text
        if decision.new_status == STATUS_CLOSED:
            pending.closed_at = now

        await self.session.flush()
        return SurveyReply(
            text=decision.reply_text,
            survey_response_id=str(pending.id),
            closed=(decision.new_status == STATUS_CLOSED),
        )

    async def _find_pending(self, contact_id: uuid.UUID, now: datetime) -> Optional[SurveyResponse]:
        q = (
            select(SurveyResponse)
            .where(
                SurveyResponse.organization_id == self.org_id,
                SurveyResponse.contact_id == contact_id,
                SurveyResponse.status.in_([STATUS_SENT, STATUS_AWAITING_REASON]),
                SurveyResponse.sent_at >= now - self.window,
            )
            .order_by(SurveyResponse.sent_at.desc())
            .limit(1)
        )
        return (await self.session.execute(q)).scalar_one_or_none()

    async def _prompts(self, survey_run_id: uuid.UUID) -> tuple[str, str, str]:
        """Lê os textos das perguntas do survey (fallback nos defaults)."""
        run = await self.session.get(SurveyRun, survey_run_id)
        survey = await self.session.get(Survey, run.survey_id) if run else None
        reason_prompt = DEFAULT_REASON_PROMPT
        thanks_msg = DEFAULT_THANKS_MSG
        if survey and survey.questions:
            reason_q = next((x for x in survey.questions if x.get("kind") == "open"), None)
            if reason_q and reason_q.get("text"):
                reason_prompt = reason_q["text"]
            thanks_q = next((x for x in survey.questions if x.get("kind") == "thanks"), None)
            if thanks_q and thanks_q.get("text"):
                thanks_msg = thanks_q["text"]
        return reason_prompt, thanks_msg, DEFAULT_RETRY_MSG
