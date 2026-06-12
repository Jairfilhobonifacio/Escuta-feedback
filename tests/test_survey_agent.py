"""Testes determinísticos do Survey Agent (`SurveyContextResolver._run_agent`).

O Survey Agent conduz a pesquisa como uma conversa: lê o histórico inteiro +
o estado da `SurveyResponse` pendente e decide o turno numa única chamada ao
LLM (capturar/CORRIGIR a nota, aprofundar sem repetir, fechar, escalar, opt-out).

Como a flag `settings.survey_agent_enabled` mora num dataclass `frozen` (não dá
para monkeypatchar por setattr), testamos chamando `resolver._run_agent(...)`
DIRETAMENTE — sem passar por `resolve()`, que checa a flag.

Estilo espelha `tests/test_chatbot.py`: SQLite in-memory (fixture `session`),
fixtures `org`/`contact`, helper `_make_pending`, FakeLLM roteado pelo system
prompt. O agente roteia pelo `_SURVEY_AGENT_SYSTEM` ("pesquisador de satisfação
simpático e esperto"); ao FECHAR ele ainda chama `classify_feedback`
("classifica feedback") — por isso o FakeLLM trata os dois prompts.
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
from app.domain.survey.parsers import nps_bucket  # noqa: E402
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402
from app.models.core import Contact  # noqa: E402
from app.models.core import Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.survey import Message, Survey, SurveyResponse, SurveyRun  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


class FakeAgentLLM:
    """chat_json roteado pelo system prompt para controlar o Survey Agent.

    - `_SURVEY_AGENT_SYSTEM` (contém "pesquisador de satisfação simpático e
      esperto") → devolve o dict do turno do agente. Pode ser um dict (mesma
      resposta sempre) OU uma lista (consumida por chamada, p/ multi-turno).
    - "classifica feedback" → tags devolvidas no fechamento (`_classify`).
    - qualquer outro prompt → None.

    `run_survey_turn` chama `chat_json(system, user, temperature=..., max_tokens=...)`,
    então aceitamos **kwargs.
    """

    def __init__(self, *, agent=None, classify=None):
        self._agent = agent      # dict OU lista de dicts (consumida por chamada)
        self._classify = classify

    async def chat_json(self, system: str, user: str, **kwargs):
        if "pesquisador de satisfação simpático e esperto" in system:
            a = self._agent
            if isinstance(a, list):
                return a.pop(0) if a else None
            return a
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


async def _make_pending(session, org, contact, *, status, score=None, ai_meta=None, questions=None):
    """Cria Survey + SurveyRun + SurveyResponse pendente (espelha test_chatbot)."""
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
        status=status, answer_score=score, nps_bucket=nps_bucket(score),
        answer_text=None, ai_meta=ai_meta, sent_at=_now(),
    )
    session.add(resp)
    await session.commit()
    return survey, resp


async def _add_inbound(session, org, contact, body):
    """Grava uma linha inbound no transcript (para `_load_history` ter contexto)."""
    session.add(Message(organization_id=org.id, contact_id=contact.id, direction="inbound", body=body))
    await session.commit()


async def _add_outbound(session, org, contact, body):
    """Grava uma linha outbound (fala anterior do bot) no transcript."""
    session.add(Message(organization_id=org.id, contact_id=contact.id, direction="outbound", body=body))
    await session.commit()


# --- anti-repetição mecânica (independe do LLM) ------------------------------


@pytest.mark.asyncio
async def test_anti_repeticao_fecha_em_vez_de_repetir(session, org, contact):
    """Se o agente fosse repetir ~a mesma fala anterior, a trava fecha gentil em
    vez de mandar a repetição (rede de segurança p/ o modelo de reserva)."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=2)
    pergunta = "Poxa, sinto muito. Foi algo específico que não funcionou bem?"
    await _add_outbound(session, org, contact, pergunta)  # o bot JÁ fez essa pergunta

    brain = SurveyBrain(FakeAgentLLM(
        agent={"score": 2, "reason": None, "topic": None, "next": "probe", "reply": pergunta},
        classify={"sentiment": "negativo", "themes": [], "urgency": "media"},
    ))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    r = await resolver._run_agent(resp, contact.id, "nada", _now())
    assert r is not None and r.closed is True       # fechou em vez de repetir
    assert r.text != pergunta                        # NÃO repetiu a pergunta
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED


# --- 1) Correção de nota (o bug central) -------------------------------------


@pytest.mark.asyncio
async def test_corrige_nota_mutavel_10_para_1(session, org, contact):
    """answer_score=10 já gravado; o cliente CORRIGE para 1. O agente trata o
    "1" como NOVA NOTA (não como motivo): answer_score vira 1 e o bucket vira
    detractor. Esse é o bug que a máquina de estados não pegava."""
    survey, resp = await _make_pending(
        session, org, contact, status=STATUS_AWAITING_REASON, score=10,
    )
    await _add_inbound(session, org, contact, "10")
    brain = SurveyBrain(FakeAgentLLM(agent={
        "score": 1, "reason": "não gostou de nada", "topic": None,
        "next": "probe", "reply": "Entendi, anotei 1...",
    }))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    r = await resolver._run_agent(resp, contact.id, "na verdade é 1", _now())
    assert r is not None
    assert r.closed is False
    assert r.text == "Entendi, anotei 1..."

    await session.refresh(resp)
    assert resp.answer_score == 1            # NOTA CORRIGIDA (não tratada como motivo)
    assert resp.nps_bucket == "detractor"    # 1 → detrator (era promoter em 10)
    assert resp.answer_text == "não gostou de nada"
    assert resp.status == STATUS_AWAITING_REASON


# --- 2) Captura inicial da nota ----------------------------------------------


@pytest.mark.asyncio
async def test_captura_inicial_da_nota(session, org, contact):
    """pending status=sent, sem nota. O agente captura 9 → answer_score=9,
    answered_at setado, status awaiting_reason, segue aberto (closed=False)."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    await _add_inbound(session, org, contact, "9")
    brain = SurveyBrain(FakeAgentLLM(agent={
        "score": 9, "reason": None, "topic": None,
        "next": "probe", "reply": "Que ótimo! O que mais ajudou?",
    }))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    assert resp.answered_at is None
    r = await resolver._run_agent(resp, contact.id, "9", _now())
    assert r is not None
    assert r.closed is False
    assert r.text == "Que ótimo! O que mais ajudou?"

    await session.refresh(resp)
    assert resp.answer_score == 9
    assert resp.nps_bucket == "promoter"
    assert resp.answered_at is not None      # marcou o instante da 1ª nota
    assert resp.status == STATUS_AWAITING_REASON


# --- 3) Fechar ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_fecha_com_motivo(session, org, contact):
    """next=="close": status CLOSED, reply devolvido, closed=True; nota+motivo
    persistidos e classify rodado (sem messaging, não alerta)."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=8)
    await _add_inbound(session, org, contact, "faltam questões")
    brain = SurveyBrain(FakeAgentLLM(
        agent={
            "score": 8, "reason": "faltam questões", "topic": "conteúdo",
            "next": "close", "reply": "Valeu, vou levar isso!",
        },
        classify={"sentiment": "neutro", "themes": ["conteúdo"], "urgency": "media"},
    ))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    r = await resolver._run_agent(resp, contact.id, "faltam questões", _now())
    assert r is not None
    assert r.closed is True
    assert r.text == "Valeu, vou levar isso!"

    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert resp.closed_at is not None
    assert resp.answer_score == 8
    assert resp.answer_text == "faltam questões"
    # classify rodou no fechamento
    assert resp.sentiment == "neutro"
    assert resp.themes == ["conteúdo"]


# --- 4) Anti-repetição / acúmulo de tópicos ----------------------------------


@pytest.mark.asyncio
async def test_acumula_topicos_e_incrementa_turns(session, org, contact):
    """Dois turnos com `topic` diferentes: ai_meta["topics"] acumula os dois (sem
    duplicar) e agent_turns incrementa a cada turno."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    brain = SurveyBrain(FakeAgentLLM(agent=[
        {"score": 4, "reason": "caro", "topic": "preço",
         "next": "probe", "reply": "Poxa, o que pesou no preço?"},
        {"score": 4, "reason": "caro e travou", "topic": "bug",
         "next": "probe", "reply": "E o app, travou onde?"},
    ]))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    # turno 1 → topic "preço"
    await _add_inbound(session, org, contact, "tá caro")
    r1 = await resolver._run_agent(resp, contact.id, "tá caro", _now())
    assert r1 is not None and r1.closed is False
    await session.refresh(resp)
    assert (resp.ai_meta or {}).get("topics") == ["preço"]
    assert (resp.ai_meta or {}).get("agent_turns") == 1

    # turno 2 → topic "bug": acumula
    await _add_inbound(session, org, contact, "e travou")
    r2 = await resolver._run_agent(resp, contact.id, "e travou", _now())
    assert r2 is not None and r2.closed is False
    await session.refresh(resp)
    assert (resp.ai_meta or {}).get("topics") == ["preço", "bug"]
    assert (resp.ai_meta or {}).get("agent_turns") == 2


# --- 5) Handoff ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_via_agente(session, org, contact):
    """next=="handoff": contact.needs_human_handoff=True, FeedbackItem
    type="handoff" criado, status EXPIRED, dono alertado no owner_phone."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=2)
    fake_msg = FakeMessagingService()
    brain = SurveyBrain(FakeAgentLLM(agent={
        "score": 2, "reason": None, "topic": None,
        "next": "handoff", "reply": "(ignorado — handoff usa HANDOFF_REPLY)",
    }))
    resolver = SurveyContextResolver(session, org.id, brain=brain, messaging=fake_msg)

    await _add_inbound(session, org, contact, "quero falar com um humano agora")
    r = await resolver._run_agent(resp, contact.id, "quero falar com um humano agora", _now())
    assert r is not None
    assert r.closed is True

    await session.refresh(contact)
    assert contact.needs_human_handoff is True
    assert contact.handoff_at is not None

    await session.refresh(resp)
    assert resp.status == STATUS_EXPIRED
    assert (resp.ai_meta or {}).get("handoff") is True

    fi = (await session.execute(
        select(FeedbackItem).where(FeedbackItem.contact_id == contact.id, FeedbackItem.type == "handoff")
    )).scalar_one()
    assert fi.source == "whatsapp"

    # dono alertado
    assert len(fake_msg.sent) == 1
    assert fake_msg.sent[0]["chat_id"] == "5511999990000"
    assert "Hand-off" in fake_msg.sent[0]["text"]


# --- 6) Opt-out ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_opt_out_via_agente(session, org, contact):
    """next=="opt_out": contact.opt_in=False, status EXPIRED, ai_meta["opt_out"]
    True, reply do agente devolvido, closed=True."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=5)
    brain = SurveyBrain(FakeAgentLLM(agent={
        "score": None, "reason": None, "topic": None,
        "next": "opt_out", "reply": "Beleza, não mando mais.",
    }))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    await _add_inbound(session, org, contact, "para de me mandar isso")
    r = await resolver._run_agent(resp, contact.id, "para de me mandar isso", _now())
    assert r is not None
    assert r.closed is True
    assert r.text == "Beleza, não mando mais."

    await session.refresh(contact)
    assert contact.opt_in is False

    await session.refresh(resp)
    assert resp.status == STATUS_EXPIRED
    assert (resp.ai_meta or {}).get("opt_out") is True


# --- 7) Fallback (LLM indisponível) ------------------------------------------


@pytest.mark.asyncio
async def test_fallback_quando_run_survey_turn_devolve_none(session, org, contact):
    """run_survey_turn devolve None (LLM off/resposta inválida) ⇒ _run_agent
    devolve None (o resolver então cai no determinístico) e nada é mutado."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    # agent=None ⇒ FakeAgentLLM.chat_json devolve None p/ o prompt do agente ⇒
    # run_survey_turn devolve None.
    brain = SurveyBrain(FakeAgentLLM(agent=None))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    await _add_inbound(session, org, contact, "sei lá")
    r = await resolver._run_agent(resp, contact.id, "sei lá", _now())
    assert r is None

    await session.refresh(resp)
    assert resp.status == STATUS_SENT          # intacto
    assert resp.answer_score is None
    assert resp.answer_text is None


# --- 8) Anti-loop -------------------------------------------------------------


@pytest.mark.asyncio
async def test_anti_loop_forca_fechar_apos_muitos_turnos(session, org, contact):
    """Com agent_turns=5 e o agente querendo "probe" (não-terminal), o resolver
    FORÇA o fechamento (status CLOSED) — evita loop infinito de aprofundamento."""
    survey, resp = await _make_pending(
        session, org, contact, status=STATUS_AWAITING_REASON, score=6,
        ai_meta={"agent_turns": 5, "topics": ["preço"]},
    )
    brain = SurveyBrain(FakeAgentLLM(
        agent={
            "score": 6, "reason": "ainda reclamando", "topic": None,
            "next": "probe", "reply": "Me conta mais...",
        },
        classify={"sentiment": "negativo", "themes": ["preço"], "urgency": "media"},
    ))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    await _add_inbound(session, org, contact, "ainda tá ruim")
    r = await resolver._run_agent(resp, contact.id, "ainda tá ruim", _now())
    assert r is not None
    assert r.closed is True                    # forçou close apesar de next=="probe"

    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert resp.closed_at is not None
    assert (resp.ai_meta or {}).get("agent_turns") == 6
