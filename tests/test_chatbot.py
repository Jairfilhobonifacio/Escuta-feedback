"""Testes do chatbot conversacional: transcript (Message), aprofundamento
(follow-up adaptativo) e hand-off humano. Usa um FakeLLM roteado por prompt
para controlar o SurveyBrain sem rede.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.domain.survey.constants import (  # noqa: E402
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
    STATUS_SENT,
)
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.domain.survey.parsers import nps_bucket  # noqa: E402
from app.domain.survey.resolver import HANDOFF_REPLY, SurveyContextResolver  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.survey import Message, Survey, SurveyResponse, SurveyRun  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


class FakeLLM:
    """chat_json roteado pelo system prompt: interpret / followup / classify / reason."""

    def __init__(self, *, interpret=None, followup=None, classify=None, reason=None):
        self._interpret = interpret
        self._followup = followup  # dict OU lista (consumida por chamada)
        self._classify = classify
        self._reason = reason  # pergunta de motivo adaptada à nota

    async def chat_json(self, system: str, user: str):
        if "should_followup" in system:
            f = self._followup
            if isinstance(f, list):
                return f.pop(0) if f else None
            return f
        if "MOTIVO da nota" in system:
            return self._reason
        if "INTENÇÃO" in system:
            return self._interpret
        if "classifica feedback" in system:
            return self._classify
        return None


def _now():
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={"owner_phone": "5511999990000"})
    session.add(o)
    await session.commit()
    return o


@pytest_asyncio.fixture
async def contact(session, org):
    c = Contact(organization_id=org.id, phone="5524998365809", name="Jair", opt_in=True, profile_data={})
    session.add(c)
    await session.commit()
    return c


async def _make_pending(session, org, contact, *, status, score=None, questions=None):
    survey = Survey(
        organization_id=org.id, name="NPS Bizzu", type="nps", status="active",
        questions=questions or [
            {"key": "nps", "kind": "nps", "text": "De 0 a 10?"},
            {"key": "reason", "kind": "open", "text": "Por quê?"},
            {"key": "thanks", "kind": "thanks", "text": "Valeu!"},
        ],
    )
    session.add(survey)
    await session.flush()
    run = SurveyRun(survey_id=survey.id, organization_id=org.id, trigger="t", status="running")
    session.add(run)
    await session.flush()
    resp = SurveyResponse(
        survey_run_id=run.id, contact_id=contact.id, organization_id=org.id,
        status=status, answer_score=score, nps_bucket=nps_bucket(score), sent_at=_now(),
    )
    session.add(resp)
    await session.commit()
    return survey, resp


# --- transcript (Message) ----------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_grava_outbound_no_transcript(session, org, contact):
    survey = Survey(organization_id=org.id, name="S", type="nps", status="active",
                    questions=[{"key": "nps", "kind": "nps", "text": "De 0 a 10?"}])
    session.add(survey)
    await session.flush()

    dispatcher = SurveyDispatcher(session, org.id, FakeMessagingService())
    await dispatcher.dispatch(survey, [contact])
    await session.commit()

    msgs = (await session.execute(select(Message).where(Message.contact_id == contact.id))).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].direction == "outbound"
    assert msgs[0].survey_response_id is not None
    assert "0 a 10" in msgs[0].body


# --- aprofundamento (follow-up adaptativo) -----------------------------------


@pytest.mark.asyncio
async def test_followup_reabre_e_acumula(session, org, contact):
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=3)
    brain = SurveyBrain(FakeLLM(
        followup=[{"should_followup": True, "question": "Pode me dar um exemplo do que aconteceu?"},
                  {"should_followup": False}],
        classify={"sentiment": "negativo", "themes": ["produto"], "urgency": "media"},
    ))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    # 1ª resposta vaga → bot aprofunda (reabre, não fecha)
    r1 = await resolver.resolve(contact.id, "não gostei")
    assert r1 is not None and r1.closed is False
    assert r1.text == "Pode me dar um exemplo do que aconteceu?"
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    assert (resp.ai_meta or {}).get("follow_up_count") == 1

    # 2ª resposta → fecha e ACUMULA o motivo original + aprofundamento
    r2 = await resolver.resolve(contact.id, "o app travou na hora da prova")
    assert r2 is not None and r2.closed is True
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert "não gostei" in resp.answer_text and "travou" in resp.answer_text


@pytest.mark.asyncio
async def test_promotor_satisfeito_nao_aprofunda(session, org, contact):
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=10)
    brain = SurveyBrain(FakeLLM(
        followup={"should_followup": True, "question": "qual parte?"},
        classify={"sentiment": "positivo", "themes": ["conteúdo"], "urgency": "baixa"},
    ))
    resolver = SurveyContextResolver(session, org.id, brain=brain)
    r = await resolver.resolve(contact.id, "tudo ótimo")
    assert r is not None and r.closed is True  # promotor fecha direto, sem follow-up
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED


# --- follow-up adaptativo à nota (não mais "Massa! 🙌" fixo) ------------------


@pytest.mark.asyncio
async def test_reason_prompt_adaptativo_para_detrator(session, org, contact):
    # nota 3: o bot NÃO manda o texto fixo — manda a pergunta empática gerada pela IA.
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    brain = SurveyBrain(FakeLLM(reason={"message": "Poxa, sinto muito 😕 Me conta o que aconteceu?"}))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    r = await resolver.resolve(contact.id, "3")
    assert r is not None and r.closed is False
    assert r.text == "Poxa, sinto muito 😕 Me conta o que aconteceu?"
    assert "Massa" not in r.text  # tom adaptado, não a comemoração fixa
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    assert resp.answer_score == 3 and resp.nps_bucket == "detractor"


@pytest.mark.asyncio
async def test_reason_prompt_fallback_sem_brain(session, org, contact):
    # sem brain (ou LLM falhando): cai no texto fixo do survey — Fase 0 preservada.
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    resolver = SurveyContextResolver(session, org.id, brain=None)

    r = await resolver.resolve(contact.id, "3")
    assert r is not None and r.text == "Por quê?"  # texto fixo das questions do _make_pending
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON


@pytest.mark.asyncio
async def test_reconciliacao_nota_alta_texto_negativo_aprofunda(session, org, contact):
    # nota 10 MAS sentimento negativo ("não gostei"): não fecha direto — aprofunda
    # apontando a incoerência, em vez de engolir a contradição.
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=10)
    brain = SurveyBrain(FakeLLM(
        followup={"should_followup": True, "question": "Você deu 10 mas falou que não gostou — o que pesou?"},
        classify={"sentiment": "negativo", "themes": ["experiência"], "urgency": "media"},
    ))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    r = await resolver.resolve(contact.id, "não gostei")
    assert r is not None and r.closed is False  # não fechou: foi entender a contradição
    assert "10" in r.text
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    assert (resp.ai_meta or {}).get("follow_up_count") == 1


# --- hand-off humano ---------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_marca_pausa_e_alerta(session, org, contact):
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    fake_msg = FakeMessagingService()
    brain = SurveyBrain(FakeLLM(interpret={"kind": "handoff", "score": None, "reply": None}))
    resolver = SurveyContextResolver(session, org.id, brain=brain, messaging=fake_msg)

    # Obs.: o parser lê "um/uma" como nota 1; uso uma mensagem sem palavra-número
    # para cair no caminho do brain (handoff). Limitação conhecida do parse_nps.
    r = await resolver.resolve(contact.id, "preciso falar com o suporte humano agora, péssima experiência")
    assert r is not None
    assert r.text == HANDOFF_REPLY
    assert r.closed is True

    # contato pausado
    await session.refresh(contact)
    assert contact.needs_human_handoff is True
    assert contact.handoff_at is not None
    # pendência encerrada (humano assume)
    await session.refresh(resp)
    assert resp.status == STATUS_EXPIRED
    assert (resp.ai_meta or {}).get("handoff") is True

    # registrado na mega central
    fi = (await session.execute(
        select(FeedbackItem).where(FeedbackItem.contact_id == contact.id, FeedbackItem.type == "handoff")
    )).scalar_one()
    assert fi.source == "whatsapp"

    # dono alertado no owner_phone
    assert len(fake_msg.sent) == 1
    assert fake_msg.sent[0]["chat_id"] == "5511999990000"
    assert "Hand-off" in fake_msg.sent[0]["text"]


# --- alertas de detrator em tempo real (Fase 2) ------------------------------


@pytest.mark.asyncio
async def test_detrator_alerta_dono_em_tempo_real(session, org, contact):
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=2)
    fake_msg = FakeMessagingService()
    brain = SurveyBrain(FakeLLM(classify={"sentiment": "negativo", "themes": ["preço"], "urgency": "alta"}))
    resolver = SurveyContextResolver(session, org.id, brain=brain, messaging=fake_msg)

    r = await resolver.resolve(contact.id, "muito caro e não me ajudou")
    assert r is not None and r.closed is True
    await session.refresh(resp)
    assert resp.nps_bucket == "detractor"
    assert (resp.ai_meta or {}).get("detractor_alert_sent") is True
    assert len(fake_msg.sent) == 1
    assert fake_msg.sent[0]["chat_id"] == "5511999990000"
    assert "Detrator" in fake_msg.sent[0]["text"]


@pytest.mark.asyncio
async def test_promotor_nao_gera_alerta(session, org, contact):
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=10)
    fake_msg = FakeMessagingService()
    brain = SurveyBrain(FakeLLM(classify={"sentiment": "positivo", "themes": ["conteúdo"], "urgency": "baixa"}))
    resolver = SurveyContextResolver(session, org.id, brain=brain, messaging=fake_msg)
    await resolver.resolve(contact.id, "excelente, recomendo demais")
    assert fake_msg.sent == []  # promotor satisfeito não dispara alerta


# --- clustering de temas (Fase 2) --------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_themes_conta_survey_e_feedback(session, org, contact):
    from app.domain.digest.aggregator import aggregate_themes

    survey, resp = await _make_pending(session, org, contact, status=STATUS_CLOSED, score=3)
    resp.themes = ["preço", "conteúdo"]
    resp.sentiment = "negativo"
    resp.closed_at = _now()
    session.add(FeedbackItem(
        organization_id=org.id, contact_id=contact.id, source="bizzu_app", type="nps",
        themes=["preço"], sentiment="negativo", occurred_at=_now(),
    ))
    await session.commit()

    themes = await aggregate_themes(session, org.id, days=7)
    by = {t.theme: t for t in themes}
    assert by["preço"].count == 2  # 1 survey + 1 feedback
    assert by["preço"].sentiment_breakdown["negativo"] == 2
    assert by["conteúdo"].count == 1
