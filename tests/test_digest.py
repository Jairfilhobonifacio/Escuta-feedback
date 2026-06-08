"""Testes do digest semanal: agregação (SQLite real), narrativa (FakeLLM) e
fallback determinístico. Janelas controladas mexendo em sent_at/closed_at.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.digest.aggregator import DigestData, aggregate  # noqa: E402
from app.domain.digest.service import build_digest, fallback_text, send_digest  # noqa: E402
from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse, SurveyRun  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402
from tests.test_brain import FakeLLM  # noqa: E402

NOW = datetime.now(timezone.utc)


async def _org(session, owner_phone=None):
    settings = {"owner_phone": owner_phone} if owner_phone else {}
    org = Organization(slug="bizzu", name="Bizzu", settings=settings)
    session.add(org)
    await session.flush()
    return org


async def _survey(session, org, stype="nps"):
    s = Survey(
        organization_id=org.id, name=f"S-{stype}", type=stype, status="active",
        questions=[{"key": "nps", "kind": "nps", "text": "q"}, {"key": "reason", "kind": "open", "text": "r"}],
    )
    session.add(s)
    await session.flush()
    run = SurveyRun(survey_id=s.id, organization_id=org.id, trigger="t", status="done")
    session.add(run)
    await session.flush()
    return s, run


async def _resp(session, org, run, contact_name, *, days_ago, score=None, bucket=None,
                text=None, sentiment=None, themes=None, urgency=None, stype_closed=True):
    when = NOW - timedelta(days=days_ago)
    c = Contact(organization_id=org.id, phone=f"55{uuid.uuid4().int % 10**11:011d}",
                name=contact_name, opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    r = SurveyResponse(
        survey_run_id=run.id, contact_id=c.id, organization_id=org.id,
        status="closed" if stype_closed else "sent",
        answer_score=score, nps_bucket=bucket, answer_text=text,
        sentiment=sentiment, themes=themes, ai_meta={"urgency": urgency} if urgency else None,
        sent_at=when, answered_at=when if score is not None else None,
        closed_at=when if stype_closed else None,
    )
    session.add(r)
    await session.flush()
    return r


# --- agregação -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_nps_delta_e_temas(session):
    org = await _org(session)
    nps_survey, run = await _survey(session, org, "nps")

    # Semana atual: 2 promoters, 1 detractor → NPS = round((2-1)/3*100) = 33
    await _resp(session, org, run, "A", days_ago=1, score=10, bucket="promoter",
                text="ótimo", sentiment="positivo", themes=["conteúdo"])
    await _resp(session, org, run, "B", days_ago=2, score=9, bucket="promoter",
                text="muito bom", sentiment="positivo", themes=["conteúdo", "preço"])
    await _resp(session, org, run, "C", days_ago=3, score=3, bucket="detractor",
                text="caro e travando", sentiment="negativo", themes=["preço"], urgency="alta")
    # Semana anterior: 1 detractor → NPS prev = -100
    await _resp(session, org, run, "D", days_ago=10, score=2, bucket="detractor",
                text="ruim", sentiment="negativo", themes=["bug"])
    await session.commit()

    data = await aggregate(session, org.id, days=7)
    assert data.nps == 33
    assert data.nps_prev == -100
    assert data.nps_delta == 133
    assert data.answered == 3
    assert data.sentiment == {"positivo": 2, "neutro": 0, "negativo": 1}
    assert dict(data.top_themes)["preço"] == 2
    assert dict(data.top_themes)["conteúdo"] == 2
    assert len(data.urgent) == 1 and data.urgent[0].contact_name == "C"


@pytest.mark.asyncio
async def test_aggregate_churn_e_semana_vazia(session):
    org = await _org(session)
    exit_survey, run = await _survey(session, org, "exit")
    await _resp(session, org, run, "Churned", days_ago=2, text="achei caro", sentiment="negativo", themes=["preço"])
    await session.commit()

    data = await aggregate(session, org.id, days=7)
    assert len(data.churn) == 1
    assert data.churn[0].text == "achei caro"
    assert data.has_activity is True

    # janela curtíssima (0 dias) → tudo cai fora → sem atividade
    empty = await aggregate(session, org.id, days=0)
    assert empty.has_activity is False


# --- narrativa + fallback --------------------------------------------------------


@pytest.mark.asyncio
async def test_build_digest_usa_narrativa_do_llm(session):
    org = await _org(session)
    _, run = await _survey(session, org, "nps")
    await _resp(session, org, run, "A", days_ago=1, score=10, bucket="promoter", text="top", sentiment="positivo", themes=["x"])
    await session.commit()

    brain = SurveyBrain(FakeLLM({"message": "Resumo da semana 👋 NPS subiu!"}))
    text, data = await build_digest(session, org.id, brain, days=7)
    assert text == "Resumo da semana 👋 NPS subiu!"
    assert data.nps == 100


@pytest.mark.asyncio
async def test_build_digest_fallback_quando_llm_falha(session):
    org = await _org(session)
    _, run = await _survey(session, org, "nps")
    await _resp(session, org, run, "A", days_ago=1, score=9, bucket="promoter", text="bom", sentiment="positivo", themes=["preço"])
    await session.commit()

    brain = SurveyBrain(FakeLLM(None))  # LLM devolve None
    text, _ = await build_digest(session, org.id, brain, days=7)
    assert "Resumo da semana" in text
    assert "NPS: 100" in text
    assert "preço" in text


def test_fallback_text_semana_vazia():
    data = DigestData(org_name="Bizzu", period_days=7)
    txt = fallback_text(data)
    assert "quieta" in txt.lower()


# --- envio -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_digest_sem_owner_phone_nao_envia(session):
    org = await _org(session, owner_phone=None)
    _, run = await _survey(session, org, "nps")
    await _resp(session, org, run, "A", days_ago=1, score=9, bucket="promoter", text="b", sentiment="positivo", themes=["x"])
    await session.commit()

    fake = FakeMessagingService()
    res = await send_digest(session, org.id, None, fake, days=7)
    assert res["sent"] is False
    assert fake.sent == []
    assert "owner_phone" in res["reason"]


@pytest.mark.asyncio
async def test_send_digest_com_owner_phone_envia(session):
    org = await _org(session, owner_phone="5524998365809")
    _, run = await _survey(session, org, "nps")
    await _resp(session, org, run, "A", days_ago=1, score=9, bucket="promoter", text="b", sentiment="positivo", themes=["x"])
    await session.commit()

    fake = FakeMessagingService()
    res = await send_digest(session, org.id, None, fake, days=7)  # brain=None → fallback determinístico
    assert res["sent"] is True
    assert res["to"] == "5524998365809"
    assert len(fake.sent) == 1
    assert fake.sent[0]["chat_id"] == "5524998365809"
    assert "Resumo da semana" in fake.sent[0]["text"]
