"""Ponte SurveyResponse -> FeedbackItem (inbox da mega central).

Cobre:
- o helper compartilhado `feedback_from_survey_response` (spec + idempotência);
- o gancho no resolver: fechar uma resposta cria/atualiza UM feedback_item
  (caminho determinístico), idempotente por external_id;
- que opt-out / hand-off (que NÃO fecham com resposta) não viram nps/outro.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.feedback.from_survey import (  # noqa: E402
    feedback_from_survey_response,
    survey_external_id,
    survey_feedback_spec,
)
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.survey import (  # noqa: E402
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    Survey,
    SurveyResponse,
    SurveyRun,
)

QUESTIONS = [
    {"key": "nps", "kind": "nps", "text": "De 0 a 10, recomendaria o Bizzu?"},
    {"key": "reason", "kind": "open", "text": "Massa! 🙌 Por quê?"},
]


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.flush()
    return o


async def _make_response(session, org, *, score=None, text=None, status=STATUS_CLOSED,
                         sentiment=None, themes=None, ai_meta=None):
    contact = Contact(organization_id=org.id, phone="5531999990001", name="X", opt_in=True)
    session.add(contact)
    await session.flush()
    survey = Survey(organization_id=org.id, name="NPS Bizzu", type="nps",
                    questions=QUESTIONS, status="active")
    session.add(survey)
    await session.flush()
    run = SurveyRun(survey_id=survey.id, organization_id=org.id, trigger="manual", status="running")
    session.add(run)
    await session.flush()
    now = datetime.now(timezone.utc)
    resp = SurveyResponse(
        survey_run_id=run.id, contact_id=contact.id, organization_id=org.id,
        status=status, answer_score=score,
        nps_bucket=("promoter" if (score or 0) >= 9 else "detractor" if score is not None else None),
        answer_text=text, sentiment=sentiment, themes=themes, ai_meta=ai_meta,
        sent_at=now, answered_at=(now if score is not None else None),
        closed_at=(now if status == STATUS_CLOSED else None),
    )
    session.add(resp)
    await session.flush()
    return contact, run, resp


# --- helper: spec (puro) -----------------------------------------------------


def test_external_id_estavel():
    rid = uuid.uuid4()
    assert survey_external_id(rid) == f"survey_response:{rid}"


@pytest.mark.asyncio
async def test_spec_nps_com_nota(session, org):
    _, _, resp = await _make_response(
        session, org, score=9, text="resumos ótimos",
        sentiment="positivo", themes=["conteúdo"], ai_meta={"urgency": "baixa"},
    )
    spec = survey_feedback_spec(resp)
    assert spec["source"] == "whatsapp"
    assert spec["type"] == "nps"
    assert spec["score"] == 9 and spec["nps_bucket"] == "promoter"
    assert spec["text"] == "resumos ótimos"
    assert spec["sentiment"] == "positivo" and spec["themes"] == ["conteúdo"]
    assert spec["external_id"] == f"survey_response:{resp.id}"
    assert spec["ai_meta"]["urgency"] == "baixa"
    assert spec["ai_meta"]["survey_response_id"] == str(resp.id)


@pytest.mark.asyncio
async def test_spec_so_texto_vira_outro(session, org):
    _, _, resp = await _make_response(session, org, score=None, text="quero cancelar")
    spec = survey_feedback_spec(resp)
    assert spec["type"] == "outro"
    assert spec["score"] is None


# --- helper: persiste + idempotência -----------------------------------------


@pytest.mark.asyncio
async def test_feedback_from_survey_response_cria_e_dedup(session, org):
    _, _, resp = await _make_response(
        session, org, score=10, text="top demais",
        sentiment="positivo", themes=["app"], ai_meta={"urgency": "baixa"},
    )

    a = await feedback_from_survey_response(session, resp)
    assert a.source == "whatsapp" and a.type == "nps"
    assert a.score == 10 and a.nps_bucket == "promoter"
    assert a.sentiment == "positivo" and a.themes == ["app"]
    assert a.ai_meta["urgency"] == "baixa"
    assert a.contact_id == resp.contact_id and a.organization_id == org.id

    # Reabre/atualiza a resposta e re-espelha: MESMO item, sem duplicar.
    resp.answer_text = "top demais — e o suporte respondeu rápido"
    await session.flush()
    b = await feedback_from_survey_response(session, resp)
    assert b.id == a.id
    assert b.text == "top demais — e o suporte respondeu rápido"

    rows = (
        await session.execute(
            select(FeedbackItem).where(FeedbackItem.external_id == survey_external_id(resp.id))
        )
    ).scalars().all()
    assert len(rows) == 1


# --- gancho no resolver ------------------------------------------------------


@pytest.mark.asyncio
async def test_gancho_fechamento_cria_feedback_item(session, org):
    """Fluxo real: responder a nota e o motivo fecha a pesquisa -> vira inbox item."""
    contact, run, resp = await _make_response(
        session, org, score=None, text=None, status="sent",
    )
    await session.commit()

    resolver = SurveyContextResolver(session, org.id)  # brain=None: determinístico
    r1 = await resolver.resolve(contact.id, "9")
    assert r1 is not None
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    # ainda não fechou -> nada na central
    pre = (await session.execute(select(FeedbackItem))).scalars().all()
    assert pre == []

    r2 = await resolver.resolve(contact.id, "os resumos são ótimos")
    assert r2 is not None and r2.closed is True
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED

    items = (
        await session.execute(
            select(FeedbackItem).where(
                FeedbackItem.external_id == survey_external_id(resp.id)
            )
        )
    ).scalars().all()
    assert len(items) == 1
    item = items[0]
    assert item.source == "whatsapp" and item.type == "nps"
    assert item.score == 9 and item.nps_bucket == "promoter"
    assert item.text == "os resumos são ótimos"
    assert item.contact_id == contact.id and item.organization_id == org.id


@pytest.mark.asyncio
async def test_gancho_idempotente_em_reprocessamento(session, org):
    """Espelhar a mesma resposta fechada 2x não duplica o feedback_item."""
    _, _, resp = await _make_response(session, org, score=8, text="bom, mas caro")
    await feedback_from_survey_response(session, resp)
    await feedback_from_survey_response(session, resp)
    rows = (
        await session.execute(
            select(FeedbackItem).where(FeedbackItem.organization_id == org.id)
        )
    ).scalars().all()
    assert len(rows) == 1
