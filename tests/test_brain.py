"""Testes do SurveyBrain + integração com o SurveyContextResolver.

LLM dublado (FakeLLM devolve JSONs prontos) — nenhum teste toca a Groq.
Invariante central: com brain=None OU LLM falhando, o comportamento é
byte-a-byte o da Fase 0 (retry determinístico) — IA nunca quebra o fluxo.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey.brain import OPT_OUT_CONFIRM_MSG, BrainIntent, FeedbackTags, SurveyBrain  # noqa: E402
from app.domain.survey.constants import (  # noqa: E402
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
    STATUS_SENT,
)
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.domain.survey.resolver import DEFAULT_RETRY_MSG, SurveyContextResolver  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse  # noqa: E402
from sqlalchemy import select  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


class FakeLLM:
    """Dublê de GroqLLM: devolve a sequência de JSONs configurada."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, system: str, user: str):
        self.calls.append((system, user))
        if not self.responses:
            return None
        return self.responses.pop(0)


class BoomLLM:
    async def chat_json(self, system: str, user: str):
        raise RuntimeError("boom")


# --- helpers de cenário ----------------------------------------------------------


async def _setup_pending_nps(session) -> tuple[Organization, Contact, SurveyResponse]:
    """Org + survey NPS + contato com pergunta enviada (status sent)."""
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.flush()
    survey = Survey(
        organization_id=org.id,
        name="NPS Bizzu",
        type="nps",
        status="active",
        questions=[
            {"key": "nps", "kind": "nps", "text": "De 0 a 10, recomendaria o Bizzu?"},
            {"key": "reason", "kind": "open", "text": "Por quê?"},
        ],
    )
    contact = Contact(organization_id=org.id, phone="5524998365809", name="Jair", opt_in=True, profile_data={})
    session.add_all([survey, contact])
    await session.flush()

    dispatcher = SurveyDispatcher(session, org.id, FakeMessagingService())
    await dispatcher.dispatch(survey, [contact])
    await session.commit()

    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    return org, contact, resp


# --- unidade: SurveyBrain valida o que vem do LLM ---------------------------------


@pytest.mark.asyncio
async def test_interpret_score_natural():
    brain = SurveyBrain(FakeLLM({"kind": "score", "score": 8, "reply": None}))
    intent = await brain.interpret_reply("De 0 a 10?", "ah eu acho que uns oito")
    assert intent == BrainIntent(kind="score", score=8, reply=None)


@pytest.mark.asyncio
async def test_interpret_score_invalido_vira_none():
    brain = SurveyBrain(FakeLLM({"kind": "score", "score": 47, "reply": None}))
    assert await brain.interpret_reply("De 0 a 10?", "quarenta e sete") is None
    brain2 = SurveyBrain(FakeLLM({"kind": "score", "score": "oito", "reply": None}))
    assert await brain2.interpret_reply("De 0 a 10?", "oito") is None


@pytest.mark.asyncio
async def test_interpret_kind_desconhecido_ou_llm_off():
    assert await SurveyBrain(FakeLLM({"kind": "huh"})).interpret_reply("q", "m") is None
    assert await SurveyBrain(FakeLLM(None)).interpret_reply("q", "m") is None


@pytest.mark.asyncio
async def test_interpret_question_trunca_e_exige_reply():
    longa = {"kind": "question", "score": None, "reply": "x" * 1000}
    intent = await SurveyBrain(FakeLLM(longa)).interpret_reply("q", "como cancelo?")
    assert intent.kind == "question" and len(intent.reply) == 600
    sem_reply = {"kind": "question", "score": None, "reply": None}
    assert await SurveyBrain(FakeLLM(sem_reply)).interpret_reply("q", "?") is None


@pytest.mark.asyncio
async def test_classify_valida_enums_e_limita_temas():
    ok = {"sentiment": "negativo", "themes": ["Preço", " suporte ", "ux", "extra4"], "urgency": "alta"}
    tags = await SurveyBrain(FakeLLM(ok)).classify_feedback("caro demais", 3, "NPS")
    assert tags == FeedbackTags(sentiment="negativo", themes=["preço", "suporte", "ux"], urgency="alta")

    ruim = {"sentiment": "meh", "themes": [], "urgency": "alta"}
    assert await SurveyBrain(FakeLLM(ruim)).classify_feedback("x", None, "NPS") is None


# --- integração: resolver com brain ------------------------------------------------


@pytest.mark.asyncio
async def test_score_em_linguagem_natural_avanca_fluxo(session):
    org, contact, resp = await _setup_pending_nps(session)
    fake = FakeLLM({"kind": "score", "score": 9, "reply": None})
    brain = SurveyBrain(fake)
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    # Sem dígito nem número por extenso: o parser determinístico NÃO resolve
    # ("nove"/"9" ele já pega sozinho — ver parsers._WORDS); aqui é semântica pura.
    reply = await resolver.resolve(contact.id, "cara, gostei demais — recomendo com certeza!")
    await session.commit()

    assert len(fake.calls) == 1  # o brain foi de fato consultado
    assert reply is not None and reply.closed is False
    assert reply.text == "Por quê?"  # avançou pro follow-up, não pro retry
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    assert resp.answer_score == 9
    assert resp.nps_bucket == "promoter"
    assert resp.ai_meta.get("score_via_llm") is True


@pytest.mark.asyncio
async def test_opt_out_desliga_contato_e_expira_pendencia(session):
    org, contact, resp = await _setup_pending_nps(session)
    brain = SurveyBrain(FakeLLM({"kind": "opt_out", "score": None, "reply": None}))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    reply = await resolver.resolve(contact.id, "para de me mandar essas paradas")
    await session.commit()

    assert reply.text == OPT_OUT_CONFIRM_MSG
    assert reply.closed is True
    await session.refresh(resp)
    await session.refresh(contact)
    assert contact.opt_in is False
    assert resp.status == STATUS_EXPIRED
    assert resp.answer_score is None  # não conta em NPS
    assert resp.ai_meta.get("opt_out") is True


@pytest.mark.asyncio
async def test_pergunta_responde_e_mantem_pendente(session):
    org, contact, resp = await _setup_pending_nps(session)
    brain = SurveyBrain(
        FakeLLM({"kind": "question", "score": None, "reply": "Sou o assistente de pesquisas do Bizzu!"})
    )
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    reply = await resolver.resolve(contact.id, "quem é você??")
    await session.commit()

    assert "assistente de pesquisas" in reply.text
    assert "notinha de 0 a 10" in reply.text  # re-engaja
    assert reply.closed is False
    await session.refresh(resp)
    assert resp.status == STATUS_SENT  # pesquisa segue pendente

    # ...e o contato ainda pode responder a nota depois (caminho determinístico)
    reply2 = await resolver.resolve(contact.id, "9")
    await session.commit()
    await session.refresh(resp)
    assert resp.answer_score == 9 and resp.status == STATUS_AWAITING_REASON


@pytest.mark.asyncio
async def test_unclear_e_llm_quebrado_caem_no_retry(session):
    org, contact, resp = await _setup_pending_nps(session)

    # unclear → retry determinístico
    brain = SurveyBrain(FakeLLM({"kind": "unclear", "score": None, "reply": None}))
    reply = await SurveyContextResolver(session, org.id, brain=brain).resolve(contact.id, "👍")
    assert reply.text == DEFAULT_RETRY_MSG

    # LLM explodindo → retry determinístico (exceção engolida)
    reply2 = await SurveyContextResolver(session, org.id, brain=SurveyBrain(BoomLLM())).resolve(
        contact.id, "blz"
    )
    assert reply2.text == DEFAULT_RETRY_MSG

    await session.refresh(resp)
    assert resp.status == STATUS_SENT  # nada mudou


@pytest.mark.asyncio
async def test_fechamento_classifica_feedback(session):
    org, contact, resp = await _setup_pending_nps(session)
    brain = SurveyBrain(
        FakeLLM({"sentiment": "negativo", "themes": ["preço"], "urgency": "media"})
    )
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    # nota pelo caminho determinístico (não consome o FakeLLM)...
    await resolver.resolve(contact.id, "3")
    # ...motivo fecha e classifica
    reply = await resolver.resolve(contact.id, "achei caro demais pelo que entrega")
    await session.commit()

    assert reply.closed is True
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert resp.sentiment == "negativo"
    assert resp.themes == ["preço"]
    assert resp.ai_meta.get("urgency") == "media"


@pytest.mark.asyncio
async def test_sem_brain_comportamento_fase0_intacto(session):
    org, contact, resp = await _setup_pending_nps(session)
    resolver = SurveyContextResolver(session, org.id)  # brain=None

    reply = await resolver.resolve(contact.id, "como assim?")
    assert reply.text == DEFAULT_RETRY_MSG

    await resolver.resolve(contact.id, "10")
    reply2 = await resolver.resolve(contact.id, "tudo ótimo")
    await session.commit()

    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert resp.sentiment is None and resp.themes is None and resp.ai_meta is None
