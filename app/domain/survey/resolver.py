"""SurveyContextResolver — casa resposta inbound ↔ pergunta ↔ pessoa.

Plumbing de banco apenas; a decisão fica em logic.decide_next (pura/testável).
Com um SurveyBrain injetado (opcional), o resolver ganha inteligência nos
pontos onde o caminho determinístico não resolve:

- parser de nota falhou → brain interpreta: nota em linguagem natural ("uns
  oito"), pedido de opt-out (desliga o contato e encerra a pendência),
  pergunta do contato (responde e MANTÉM a pesquisa pendente) ou unclear
  (cai no retry determinístico de sempre).
- fechamento com motivo → brain classifica (sentiment/themes/urgency) e o
  resultado fica em survey_responses.sentiment/themes/ai_meta.

brain=None (ou qualquer falha do LLM) ⇒ comportamento idêntico ao da Fase 0.

Fase 0: usado no caminho inbound enxuto (webhook → resolver). Fase 1: injetado
em `orchestrator._process_message_internal` ENTRE behaviors (≈L217) e RAG (≈L219),
retornando cedo para atalhar o LLM quando a mensagem é resposta de pesquisa.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.survey.brain import OPT_OUT_CONFIRM_MSG, SurveyBrain
from app.domain.survey.constants import (
    STATUS_SENT,
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
)
from app.domain.survey.logic import decide_next
from app.domain.survey.parsers import nps_bucket
from app.models.core import Contact
from app.models.survey import Survey, SurveyRun, SurveyResponse

logger = logging.getLogger(__name__)

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
    def __init__(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        window: timedelta = DEFAULT_WINDOW,
        brain: SurveyBrain | None = None,
    ):
        self.session = session
        self.org_id = organization_id
        self.window = window
        self.brain = brain

    async def resolve(self, contact_id: uuid.UUID, message: str) -> Optional[SurveyReply]:
        """Retorna o que responder, ou None se o contato não tem pesquisa pendente."""
        now = datetime.now(timezone.utc)

        pending = await self._find_pending(contact_id, now)
        if pending is None:
            return None

        question_text, reason_prompt, thanks_msg, retry_msg = await self._prompts(
            pending.survey_run_id
        )

        decision = decide_next(
            pending.status,
            message,
            reason_prompt=reason_prompt,
            thanks_msg=thanks_msg,
            retry_msg=retry_msg,
        )
        if decision is None:
            return None

        # --- ponto de inteligência: parser de nota falhou (retry burro) ------
        # decide_next devolve retry quando status==sent e a mensagem não tem
        # nota válida. Antes de devolver o retry, deixamos o brain tentar.
        if (
            self.brain is not None
            and pending.status == STATUS_SENT
            and decision.new_status == STATUS_SENT
            and decision.answer_score is None
        ):
            smart = await self._think(pending, contact_id, question_text, reason_prompt, message, now)
            if smart is not None:
                return smart

        # Aplica a decisão determinística à linha pendente
        pending.status = decision.new_status
        if decision.answer_score is not None:
            pending.answer_score = decision.answer_score
            pending.nps_bucket = decision.nps_bucket
            pending.answered_at = now
        if decision.answer_text is not None:
            pending.answer_text = decision.answer_text
        if decision.new_status == STATUS_CLOSED:
            pending.closed_at = now
            await self._classify(pending)

        await self.session.flush()
        return SurveyReply(
            text=decision.reply_text,
            survey_response_id=str(pending.id),
            closed=(decision.new_status == STATUS_CLOSED),
        )

    # --- inteligência ---------------------------------------------------------

    async def _think(
        self,
        pending: SurveyResponse,
        contact_id: uuid.UUID,
        question_text: str,
        reason_prompt: str,
        message: str,
        now: datetime,
    ) -> Optional[SurveyReply]:
        """Consulta o brain para uma mensagem que o parser não entendeu.

        Retorna a SurveyReply inteligente, ou None para cair no retry padrão.
        Qualquer exceção é engolida (logada): IA jamais quebra o webhook.
        """
        try:
            intent = await self.brain.interpret_reply(question_text, message)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.warning("SurveyBrain: interpret_reply lançou — caindo no retry", exc_info=True)
            return None
        if intent is None:
            return None

        if intent.kind == "score":
            pending.status = STATUS_AWAITING_REASON
            pending.answer_score = intent.score
            pending.nps_bucket = nps_bucket(intent.score)
            pending.answered_at = now
            meta = dict(pending.ai_meta or {})
            meta["score_via_llm"] = True
            pending.ai_meta = meta
            await self.session.flush()
            return SurveyReply(
                text=reason_prompt,
                survey_response_id=str(pending.id),
                closed=False,
            )

        if intent.kind == "opt_out":
            contact = await self.session.get(Contact, contact_id)
            if contact is not None:
                contact.opt_in = False
            pending.status = STATUS_EXPIRED  # encerrada sem resposta (não conta como concluída)
            meta = dict(pending.ai_meta or {})
            meta["opt_out"] = True
            pending.ai_meta = meta
            await self.session.flush()
            return SurveyReply(
                text=OPT_OUT_CONFIRM_MSG,
                survey_response_id=str(pending.id),
                closed=True,  # nada mais pendente p/ este contato
            )

        if intent.kind == "question" and intent.reply:
            # Responde a dúvida e MANTÉM a pesquisa pendente (status intacto).
            text = f"{intent.reply}\n\nQuando puder, me manda a notinha de 0 a 10 🙂"
            return SurveyReply(
                text=text,
                survey_response_id=str(pending.id),
                closed=False,
            )

        return None  # unclear → retry determinístico

    async def _classify(self, pending: SurveyResponse) -> None:
        """Classificação multi-eixo do feedback no fechamento (best-effort)."""
        if self.brain is None or not pending.answer_text:
            return
        try:
            run = await self.session.get(SurveyRun, pending.survey_run_id)
            survey = await self.session.get(Survey, run.survey_id) if run else None
            tags = await self.brain.classify_feedback(
                pending.answer_text,
                pending.answer_score,
                survey.name if survey else "pesquisa",
            )
        except Exception:  # noqa: BLE001
            logger.warning("SurveyBrain: classify_feedback lançou — seguindo sem tags", exc_info=True)
            return
        if tags is None:
            return
        pending.sentiment = tags.sentiment
        pending.themes = tags.themes
        meta = dict(pending.ai_meta or {})
        meta["urgency"] = tags.urgency
        pending.ai_meta = meta

    # --- plumbing -------------------------------------------------------------

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

    async def _prompts(self, survey_run_id: uuid.UUID) -> tuple[str, str, str, str]:
        """Lê os textos das perguntas do survey (fallback nos defaults).

        Retorna (question_text, reason_prompt, thanks_msg, retry_msg) — a
        pergunta principal alimenta o contexto do brain.
        """
        run = await self.session.get(SurveyRun, survey_run_id)
        survey = await self.session.get(Survey, run.survey_id) if run else None
        question_text = ""
        reason_prompt = DEFAULT_REASON_PROMPT
        thanks_msg = DEFAULT_THANKS_MSG
        if survey and survey.questions:
            first_kind = "open" if survey.type == "exit" else "nps"
            main_q = next((x for x in survey.questions if x.get("kind") == first_kind), None)
            if main_q and main_q.get("text"):
                question_text = main_q["text"]
            reason_q = next((x for x in survey.questions if x.get("kind") == "open"), None)
            if reason_q and reason_q.get("text"):
                reason_prompt = reason_q["text"]
            thanks_q = next((x for x in survey.questions if x.get("kind") == "thanks"), None)
            if thanks_q and thanks_q.get("text"):
                thanks_msg = thanks_q["text"]
        return question_text, reason_prompt, thanks_msg, DEFAULT_RETRY_MSG
