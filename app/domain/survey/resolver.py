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
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.knowledge.retriever import KnowledgeBase
from app.domain.survey import brain as brain_mod
from app.domain.survey.brain import OPT_OUT_CONFIRM_MSG, SurveyBrain
from app.domain.survey.constants import (
    STATUS_SENT,
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
)
from app.domain.feedback.from_survey import feedback_from_survey_response
from app.domain.survey.logic import decide_next
from app.domain.survey.parsers import nps_bucket
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem
from app.models.survey import Message, Survey, SurveyRun, SurveyResponse
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


def _too_similar(a: str, b: str) -> bool:
    """True se duas falas do bot são ~idênticas (rede anti-repetição, independe do LLM)."""
    na = " ".join((a or "").lower().split())
    nb = " ".join((b or "").lower().split())
    if not na or not nb:
        return False
    return SequenceMatcher(None, na, nb).ratio() > 0.85


DEFAULT_WINDOW = timedelta(hours=24)

# Aprofundamento: nº máximo de perguntas de follow-up por response (adaptativo).
MAX_FOLLOWUPS = 2

HANDOFF_REPLY = (
    "Entendi — vou te conectar com uma pessoa do nosso time. "
    "Já já alguém te responde por aqui. 🙏"
)

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
        embedder: EmbeddingService | None = None,
        messaging: IMessagingService | None = None,
        waha_session: str = "default",
    ):
        self.session = session
        self.org_id = organization_id
        self.window = window
        self.brain = brain
        # embedder presente ⇒ o intent "question" tenta RAG (corpus da org) antes
        # de cair na resposta genérica. Sem ele, comportamento atual preservado.
        self.embedder = embedder
        # messaging presente ⇒ o hand-off humano alerta o dono (owner_phone).
        self.messaging = messaging
        self.waha_session = waha_session

    async def resolve(self, contact_id: uuid.UUID, message: str) -> Optional[SurveyReply]:
        """Retorna o que responder, ou None se o contato não tem pesquisa pendente."""
        now = datetime.now(timezone.utc)

        pending = await self._find_pending(contact_id, now)
        if pending is None:
            return None

        # Agente VoC (Fase 2, atrás de flag voc_agent_enabled, DEFAULT OFF): conduz o
        # turno com function-calling sobre as tools de CS. Best-effort e fallback total
        # — se desligado, sem brain, sem reply utilizável OU em qualquer falha, cai no
        # fluxo abaixo. Com a flag OFF (default) o pacote voc nem é importado, e o
        # comportamento é BYTE-A-BYTE idêntico ao atual.
        if settings.voc_agent_enabled and self.brain is not None:
            voc_reply = await self._run_voc_agent(pending, contact_id, message, now)
            if voc_reply is not None:
                return voc_reply

        # Survey Agent (atrás de flag): conduz a pesquisa como conversa de verdade
        # — lê o histórico inteiro + o estado e decide o turno (captura/CORRIGE nota,
        # aprofunda sem repetir, fecha quando suficiente). Fallback para a máquina de
        # estados se desligado OU se o LLM cair neste turno.
        if settings.survey_agent_enabled and self.brain is not None:
            agent_reply = await self._run_agent(pending, contact_id, message, now)
            if agent_reply is not None:
                return agent_reply

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
        reply_text = decision.reply_text
        if decision.answer_score is not None:
            pending.answer_score = decision.answer_score
            pending.nps_bucket = decision.nps_bucket
            pending.answered_at = now
            # Follow-up adaptativo à nota: troca o "Massa! 🙌" fixo (cego ao bucket)
            # por uma pergunta com o tom certo — empatia p/ detrator, festa p/ promotor.
            if decision.new_status == STATUS_AWAITING_REASON:
                reply_text = await self._adaptive_reason(
                    decision.answer_score, pending.survey_run_id, decision.reply_text
                )
        if decision.answer_text is not None:
            # Em rodada de follow-up, ACUMULA (motivo original + aprofundamento);
            # senão, grava normal.
            if pending.answer_text and (pending.ai_meta or {}).get("follow_up_count"):
                pending.answer_text = f"{pending.answer_text}\n— {decision.answer_text}"
            else:
                pending.answer_text = decision.answer_text
        if decision.new_status == STATUS_CLOSED:
            pending.closed_at = now
            await self._classify(pending)
            # Fase 2 (Playbooks): plugue INLINE do motor, atrás de flag (default OFF)
            # e best-effort — quando um detrator fecha, roda o gatilho nps_detractor.
            await self._maybe_run_playbooks_inline(pending, contact_id)
            # Fase 2: alerta o dono em tempo real se for detrator urgente/negativo.
            await self._notify_detractor_realtime(pending, contact_id)
            # Aprofundamento: antes de fechar de vez, talvez UMA pergunta de follow-up.
            followup = await self._maybe_followup(pending, now)
            if followup is not None:
                return followup
            # Fechou de fato: espelha no inbox da mega central (idempotente).
            await self._to_central(pending)

        await self.session.flush()
        return SurveyReply(
            text=reply_text,
            survey_response_id=str(pending.id),
            closed=(decision.new_status == STATUS_CLOSED),
        )

    # --- inteligência ---------------------------------------------------------

    async def _adaptive_reason(
        self, score: Optional[int], survey_run_id: uuid.UUID, fallback: str
    ) -> str:
        """Pergunta de motivo adaptada à nota (empatia p/ detrator, festa p/ promotor).

        Best-effort: sem brain, score None ou LLM falhando ⇒ devolve o texto fixo
        do survey (comportamento Fase 0 preservado)."""
        if self.brain is None or score is None:
            return fallback
        try:
            run = await self.session.get(SurveyRun, survey_run_id)
            survey = await self.session.get(Survey, run.survey_id) if run else None
            msg = await self.brain.compose_reason_prompt(
                score, survey.name if survey else "pesquisa"
            )
            return msg or fallback
        except Exception:  # noqa: BLE001 — nunca derruba o webhook; cai no texto fixo.
            logger.warning("compose_reason_prompt lançou — usando texto fixo", exc_info=True)
            return fallback

    # --- Agente VoC (Fase 2: function-calling sobre as tools de CS) ------------

    async def _run_voc_agent(
        self, pending: SurveyResponse, contact_id: uuid.UUID, message: str, now: datetime
    ) -> Optional[SurveyReply]:
        """Conduz UM turno via Agente VoC (function-calling). None ⇒ fallback total.

        Só é chamado com a flag voc_agent_enabled ON e brain presente (de onde sai o
        GroqLLM com chat_with_tools). Imports são LOCAIS de propósito: com a flag OFF
        o pacote voc nunca é tocado. Best-effort: qualquer falha, ou uma resposta vazia/
        não-concluída, devolve None e o resolver segue no fluxo determinístico/Survey Agent.
        """
        llm = getattr(self.brain, "llm", None)
        if llm is None:
            return None
        try:
            from app.domain.voc.orchestrator import VoCAgentOrchestrator
            from app.domain.voc.tools import VoCToolContext, build_default_registry

            ctx = VoCToolContext(
                session=self.session,
                org_id=self.org_id,
                messaging=self.messaging,
                waha_session=self.waha_session,
                now=lambda: now,
            )
            registry = build_default_registry(ctx)
            orchestrator = VoCAgentOrchestrator(llm, registry)
            history = await self._load_history(contact_id)
            result = await orchestrator.run(message, history)
        except Exception:  # noqa: BLE001 — agente VoC nunca derruba o webhook.
            logger.warning("Agente VoC lançou — fallback determinístico", exc_info=True)
            return None

        # Só assume o turno se o agente realmente conduziu (concluiu com texto). Caso
        # contrário, devolve None para o fluxo de sempre tratar a mensagem.
        if not result.completed or not result.reply:
            return None

        meta = dict(pending.ai_meta or {})
        meta["voc_agent"] = True
        if result.tool_calls_made:
            meta["voc_tools"] = result.tool_calls_made
        pending.ai_meta = meta
        await self.session.flush()
        return SurveyReply(text=result.reply, survey_response_id=str(pending.id), closed=False)

    # --- Survey Agent (conversa de verdade, no lugar da máquina de estados) -----

    async def _run_agent(
        self, pending: SurveyResponse, contact_id: uuid.UUID, message: str, now: datetime
    ) -> Optional[SurveyReply]:
        """Conduz UM turno via Survey Agent. None ⇒ fallback p/ a máquina de estados.

        Estado da pesquisa (nota/motivo/tópicos já perguntados/turnos) vive na linha
        pendente; o agente lê a conversa toda e decide. Nota é MUTÁVEL (corrige 10→1).
        """
        history = await self._load_history(contact_id)
        if not history or history[-1] != ("inbound", message):
            history = [*history, ("inbound", message)]

        meta = dict(pending.ai_meta or {})
        topics = list(meta.get("topics") or [])
        turns = int(meta.get("agent_turns", 0) or 0)
        survey_name, nps_question = await self._survey_meta(pending.survey_run_id)

        try:
            d = await self.brain.run_survey_turn(  # type: ignore[union-attr]
                survey_name=survey_name,
                nps_question=nps_question,
                history=history,
                score=pending.answer_score,
                reason=pending.answer_text,
                topics=topics,
                followups=turns,
            )
        except Exception:  # noqa: BLE001 — agente nunca derruba o webhook.
            logger.warning("run_survey_turn lançou — fallback determinístico", exc_info=True)
            return None
        if d is None:
            return None

        # Anti-loop: depois de muitos turnos, força encerrar.
        nxt = d["next"]
        if turns >= 5 and nxt not in ("close", "handoff", "opt_out"):
            nxt = "close"
        # Anti-repetição mecânica (vale sobretudo no modelo de reserva, mais fraco):
        # se a fala sairia ~idêntica à última do bot, não repete — fecha gentil.
        if nxt in ("ask_score", "probe"):
            last_out = next(
                (b for dirn, b in reversed(history[:-1]) if str(dirn).lower().startswith("out")),
                None,
            )
            if last_out and _too_similar(d["reply"], last_out):
                nxt = "close"
                d = {
                    **d,
                    "reply": "Tranquilo, não precisa detalhar mais — já anotei seu retorno aqui. Valeu pelo seu tempo! 🙏",
                }

        if nxt == "opt_out":
            contact = await self.session.get(Contact, contact_id)
            if contact is not None:
                contact.opt_in = False
            pending.status = STATUS_EXPIRED
            meta["opt_out"] = True
            meta["agent"] = True
            pending.ai_meta = meta
            await self.session.flush()
            return SurveyReply(text=d["reply"], survey_response_id=str(pending.id), closed=True)

        if nxt == "handoff":
            return await self._handle_handoff(pending, contact_id, message, now)

        # Captura OU corrige a nota (estado mutável — permite mudar 10 → 1).
        if d["score"] is not None:
            if pending.answer_score is None:
                pending.answered_at = now
            pending.answer_score = d["score"]
            pending.nps_bucket = nps_bucket(d["score"])
        if d["reason"]:
            pending.answer_text = d["reason"]
        if d["topic"]:
            topics = list(dict.fromkeys([*topics, d["topic"]]))
        meta["topics"] = topics
        meta["agent_turns"] = turns + 1
        meta["agent"] = True
        pending.ai_meta = meta

        if nxt == "close":
            pending.status = STATUS_CLOSED
            pending.closed_at = now
            await self._classify(pending)
            await self._notify_detractor_realtime(pending, contact_id)
            # Fechou de fato: espelha no inbox da mega central (idempotente).
            await self._to_central(pending)
            closed = True
        else:
            pending.status = STATUS_AWAITING_REASON  # segue aberto p/ o próximo turno
            closed = False

        await self.session.flush()
        return SurveyReply(text=d["reply"], survey_response_id=str(pending.id), closed=closed)

    async def _load_history(
        self, contact_id: uuid.UUID, limit: int = 16
    ) -> list[tuple[str, str]]:
        """Últimas mensagens da conversa (transcript), em ordem cronológica."""
        q = (
            select(Message.direction, Message.body)
            .where(
                Message.organization_id == self.org_id,
                Message.contact_id == contact_id,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(q)).all()
        return [(str(d), str(b)) for d, b in reversed(rows)]

    async def _survey_meta(self, survey_run_id: uuid.UUID) -> tuple[str, str]:
        """(nome do survey, texto da pergunta de nota) para contextualizar o agente."""
        run = await self.session.get(SurveyRun, survey_run_id)
        survey = await self.session.get(Survey, run.survey_id) if run else None
        name = survey.name if survey else "pesquisa"
        question = ""
        if survey and survey.questions:
            main = (
                next((x for x in survey.questions if x.get("kind") == "nps"), None)
                or next((x for x in survey.questions if x.get("kind") == "open"), None)
            )
            if main and main.get("text"):
                question = main["text"]
        return name, question

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
            reply = await self._adaptive_reason(intent.score, pending.survey_run_id, reason_prompt)
            await self.session.flush()
            return SurveyReply(
                text=reply,
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

        if intent.kind == "handoff":
            return await self._handle_handoff(pending, contact_id, message, now)

        if intent.kind == "question":
            # RAG: tenta responder com fatos do corpus da org (grounded).
            # Com no_kb_fallback_enabled ON (default), `_answer_question` já devolve
            # a frase HONESTA ("não sei, vou encaminhar pro time") quando o corpus
            # não cobre — então essa resposta tem precedência sobre o `intent.reply`
            # genérico do brain (o `or` só usa o genérico se o RAG devolver None,
            # i.e. RAG indisponível ou flag OFF). Sem nenhuma das duas, vira retry
            # determinístico (nunca inventa).
            answer = await self._answer_question(message) or intent.reply
            if not answer:
                return None
            text = f"{answer}\n\nQuando puder, me manda a notinha de 0 a 10 🙂"
            return SurveyReply(
                text=text,
                survey_response_id=str(pending.id),
                closed=False,
            )

        return None  # unclear → retry determinístico

    async def _answer_question(self, message: str) -> Optional[str]:
        """Resposta grounded via RAG.

        - Sem embedder/brain ⇒ None (RAG indisponível; quem chama usa o genérico).
        - O RETRIEVAL (embed + pgvector) roda numa caixa de erro SEPARADA: se ele
          LANÇA (ex.: sentence-transformers ausente, pgvector fora do ar) isso é
          FALHA DE KB, não "sem resposta" — logamos como ERROR e devolvemos None
          (cai no genérico), JAMAIS deixando um erro de infra se passar por uma
          resposta honesta de "não sei".
        - Com `no_kb_fallback_enabled` ON (default) a composição usa
          `answer_question_grounded`: KB vazio/score baixo OU LLM não-respondível ⇒
          devolve `HONEST_NO_KB_MSG` (nunca inventa). Com a flag OFF preserva o
          comportamento antigo via `answer_from_context` (None quando não cobre).
        """
        if self.embedder is None or self.brain is None:
            return None
        # 1) Retrieval — falha aqui é FALHA DE KB (≠ "sem contexto"): logar alto.
        try:
            kb = KnowledgeBase(self.session, self.org_id, self.embedder)
            chunks = await kb.search(message)
        except Exception:  # noqa: BLE001 — nunca derruba o webhook, mas é VISÍVEL.
            logger.error(
                "RAG: FALHA na busca da base de conhecimento (retrieval lançou — "
                "embedder/pgvector indisponível?). NÃO é ausência de resposta; "
                "caindo no genérico sem se passar por 'respondido honestamente'.",
                exc_info=True,
            )
            return None
        # 2) Composição da resposta — best-effort; sem contexto não é erro de infra.
        # Lê a flag pelo mesmo ponto de indireção do brain (settings é frozen; isto
        # é o que os testes monkeypatcham para alternar o caminho honesto).
        try:
            if brain_mod._no_kb_fallback_enabled():
                return await self.brain.answer_question_grounded(message, chunks)
            return await self.brain.answer_from_context(message, chunks)
        except Exception:  # noqa: BLE001 — geração é best-effort; cai no genérico.
            logger.warning("RAG: composição da resposta falhou — caindo no genérico", exc_info=True)
            return None

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

    async def _to_central(self, pending: SurveyResponse) -> None:
        """Leva a resposta fechada para a mega central (inbox de monitoramento).

        Idempotente por external_id='survey_response:<id>' (reabrir+refechar a
        mesma resposta atualiza o MESMO FeedbackItem). Best-effort: um erro aqui
        nunca derruba o webhook nem impede o fechamento da pesquisa. Chamado só
        no fechamento real (status closed), depois de _classify, para o sinal já
        nascer com sentiment/themes/urgency.
        """
        try:
            await feedback_from_survey_response(self.session, pending)
        except Exception:  # noqa: BLE001 — ponte p/ a central nunca quebra o fluxo.
            logger.warning(
                "survey→central: falha ao espelhar resposta no inbox — seguindo",
                exc_info=True,
            )

    # --- aprofundamento (probing) --------------------------------------------

    async def _maybe_followup(self, pending: SurveyResponse, now: datetime) -> Optional[SurveyReply]:
        """Decide UMA pergunta de aprofundamento antes de fechar. None ⇒ fecha normal.

        Adaptativo (até MAX_FOLLOWUPS), com viés para detrator/negativo: promotor
        satisfeito (nota ≥ 7 e sem sentimento negativo) fecha direto. Best-effort:
        sem brain ou LLM falhando ⇒ fecha normal.
        """
        if self.brain is None or not pending.answer_text:
            return None
        count = int((pending.ai_meta or {}).get("follow_up_count", 0) or 0)
        if count >= MAX_FOLLOWUPS:
            return None
        score = pending.answer_score
        # Promotor satisfeito não é aprofundado (não cansar quem está feliz).
        if score is not None and score >= 7 and pending.sentiment != "negativo":
            return None
        try:
            run = await self.session.get(SurveyRun, pending.survey_run_id)
            survey = await self.session.get(Survey, run.survey_id) if run else None
            question = await self.brain.decide_followup(
                pending.answer_text, score, survey.name if survey else "pesquisa",
                sentiment=pending.sentiment,
            )
        except Exception:  # noqa: BLE001 — aprofundamento nunca derruba o fluxo.
            logger.warning("decide_followup lançou — fechando normal", exc_info=True)
            return None
        if not question:
            return None
        # Reabre a pendência para receber o aprofundamento (não fecha ainda).
        pending.status = STATUS_AWAITING_REASON
        pending.closed_at = None
        meta = dict(pending.ai_meta or {})
        meta["follow_up_count"] = count + 1
        pending.ai_meta = meta
        await self.session.flush()
        return SurveyReply(text=question, survey_response_id=str(pending.id), closed=False)

    # --- hand-off humano ------------------------------------------------------

    async def _handle_handoff(
        self, pending: SurveyResponse, contact_id: uuid.UUID, message: str, now: datetime
    ) -> SurveyReply:
        """Escala para humano: marca a conversa, PAUSA o bot e alerta o dono."""
        meta = dict(pending.ai_meta or {})
        meta["handoff"] = True
        meta["handoff_reason"] = message[:500]
        pending.ai_meta = meta
        pending.status = STATUS_EXPIRED  # encerra a pendência da pesquisa (humano assume)

        contact = await self.session.get(Contact, contact_id)
        if contact is not None:
            contact.needs_human_handoff = True   # PAUSA o bot p/ este contato
            contact.handoff_at = now

        # Registra na mega central (aparece na ficha 360 / dashboard).
        self.session.add(
            FeedbackItem(
                organization_id=self.org_id,
                contact_id=contact_id,
                source="whatsapp",
                type="handoff",
                text=message[:2000],
                occurred_at=now,
                ai_meta={"urgency": "alta"},
                extra={"reason": "hand-off solicitado/detectado pelo bot"},
            )
        )
        await self.session.flush()

        await self._notify_handoff(contact, message)
        await self._open_support_ticket(contact, message)
        # Quem pede humano costuma topar conversar: oferece a call direto (se houver link).
        from app.domain.survey.helpers import append_call_link

        reply = append_call_link(HANDOFF_REPLY, settings.bizzu_call_url)
        return SurveyReply(text=reply, survey_response_id=str(pending.id), closed=True)

    async def _notify_handoff(self, contact: Optional[Contact], message: str) -> None:
        """Alerta o dono no WhatsApp (owner_phone). Best-effort — nunca lança."""
        if self.messaging is None:
            return
        try:
            org = await self.session.get(Organization, self.org_id)
            owner_phone = (org.settings or {}).get("owner_phone") if org else None
            if not owner_phone:
                logger.warning("hand-off: sem owner_phone em Organization.settings — alerta não enviado")
                return
            phone = contact.phone if contact else "?"
            nome = (contact.name if contact and contact.name else phone)
            alert = (
                "🚨 Hand-off — um cliente precisa de você\n"
                f"Contato: {nome} ({phone})\n"
                f"Mensagem: {str(message)[:300]}\n"
                "O bot pausou esse contato. Responda direto pelo WhatsApp."
            )
            await self.messaging.send_text(chat_id=owner_phone, text=alert, session=self.waha_session)
        except Exception:  # noqa: BLE001
            logger.warning("hand-off: falha ao alertar o dono", exc_info=True)

    async def _maybe_run_playbooks_inline(self, pending: SurveyResponse, contact_id: uuid.UUID) -> None:
        """Plugue INLINE do motor de Playbooks (Fase 2), atrás de flag e best-effort.

        Com `PLAYBOOKS_INLINE_ENABLED` OFF (default) é um no-op — o motor só roda via
        POST /api/playbooks/run. Com a flag ON, quando um DETRATOR fecha a pesquisa,
        roda o motor restrito ao gatilho 'nps_detractor' (dry_run=False) para já criar
        a tarefa de CS. NUNCA propaga exceção: o webhook do WAHA não pode cair por isso.
        """
        if not settings.playbooks_inline_enabled:
            return
        if pending.nps_bucket != "detractor":
            return
        try:
            from app.domain.cs.engine import run_playbooks

            await run_playbooks(
                self.session,
                self.org_id,
                triggers=["nps_detractor"],
                dry_run=False,
                messaging=self.messaging,
            )
        except Exception:  # noqa: BLE001 — motor é enriquecedor, nunca ponto de falha.
            logger.warning("playbooks inline (resolver): falhou — seguindo", exc_info=True)

    async def _notify_detractor_realtime(self, pending: SurveyResponse, contact_id: uuid.UUID) -> None:
        """Alerta o dono em TEMPO REAL quando um detrator urgente/negativo fecha (Fase 2).

        Critério: nps_bucket=='detractor' E (urgência alta OU sentimento negativo).
        Anti-spam: 1× por response; não duplica se já houve hand-off. Best-effort.
        """
        if self.messaging is None:
            return
        meta = pending.ai_meta or {}
        if pending.nps_bucket != "detractor":
            return
        if meta.get("urgency") != "alta" and pending.sentiment != "negativo":
            return
        if meta.get("handoff") or meta.get("detractor_alert_sent"):
            return
        try:
            org = await self.session.get(Organization, self.org_id)
            owner_phone = (org.settings or {}).get("owner_phone") if org else None
            if not owner_phone:
                logger.warning("detrator: sem owner_phone em Organization.settings — alerta não enviado")
                return
            contact = await self.session.get(Contact, contact_id)
            phone = contact.phone if contact else "?"
            nome = (contact.name if contact and contact.name else phone)
            alert = (
                "🚨 Detrator — atenção imediata\n"
                f"Contato: {nome} ({phone})\n"
                f"Nota: {pending.answer_score}/10 · urgência: {meta.get('urgency', 'alta')}\n"
                f"Motivo: {str(pending.answer_text or '')[:200]}\n"
                f"Temas: {', '.join(pending.themes or []) or '—'}"
            )
            await self.messaging.send_text(chat_id=owner_phone, text=alert, session=self.waha_session)
            new_meta = dict(meta)
            new_meta["detractor_alert_sent"] = True
            pending.ai_meta = new_meta
        except Exception:  # noqa: BLE001
            logger.warning("detrator: falha ao alertar o dono", exc_info=True)

    async def _open_support_ticket(self, contact: Optional[Contact], message: str) -> None:
        """Abre um ticket no Atendimentos da Bizzu (hand-off, 3ª opção). Best-effort.

        No-op se não configurado. Requer o endpoint do backend
        (docs/patches/bizzu-backend-support-ticket-endpoint.patch) + envs
        BIZZU_SUPPORT_TICKET_URL e BIZZU_SUPPORT_API_KEY no Escuta.
        """
        url = settings.bizzu_support_ticket_url
        key = settings.bizzu_support_api_key
        if not url or not key:
            return
        try:
            import httpx

            nome = (contact.name if contact and contact.name else "Cliente")
            payload = {
                "nome": nome,
                "email": "via-whatsapp@escuta.bizzu.ai",
                "telefone": contact.phone if contact else None,
                "assunto": "Hand-off do WhatsApp (Escuta)",
                "mensagem": str(message)[:2000],
                "tipo": "reclamacao",
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(url, json=payload, headers={"X-API-Key": key})
        except Exception:  # noqa: BLE001 — abrir ticket nunca derruba o hand-off.
            logger.warning("hand-off: falha ao abrir ticket no Atendimentos", exc_info=True)

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
