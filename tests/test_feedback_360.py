"""Testes da Mega Central de Dados:
- partner_map (puro): PartnerCustomer -> specs de FeedbackItem.
- ingestor: cria + dedup por external_id (snapshot atualiza, não duplica).
- GET /api/contacts/{id}/360: unifica snapshot + FeedbackItem + SurveyResponse.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.domain.feedback.ingest import ingest_feedback_item  # noqa: E402
from app.domain.feedback.partner_map import partner_feedback_specs  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.survey import Survey, SurveyResponse, SurveyRun  # noqa: E402


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


@pytest_asyncio.fixture
async def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


# --- partner_map (puro) ------------------------------------------------------


def test_partner_map_nps_e_churn():
    customer = {
        "id": "cust-1",
        "nps": {"voted": True, "score": 9, "comment": "Adorei o Raio-X", "respondedAt": "2026-06-01T10:00:00Z"},
        "subscription": {
            "cancelled": True,
            "cancellationReason": "USER_CANCEL",
            "cancelledAt": "2026-06-05T12:00:00Z",
            "daysAsSubscriber": 40,
        },
    }
    specs = partner_feedback_specs(customer, {"profile": "churn_pos_uso"})
    by_type = {s["type"]: s for s in specs}
    assert set(by_type) == {"nps", "churn"}
    assert by_type["nps"]["score"] == 9 and by_type["nps"]["text"] == "Adorei o Raio-X"
    assert by_type["nps"]["external_id"] == "partner:nps:cust-1:2026-06-01T10:00:00Z"
    assert by_type["churn"]["text"] == "USER_CANCEL"
    assert by_type["churn"]["external_id"] == "partner:churn:cust-1"


def test_partner_map_ativo_sem_voto_nao_gera_sinal():
    customer = {"id": "c2", "nps": {"voted": False}, "subscription": {"state": "active_paying", "cancelled": False}}
    assert partner_feedback_specs(customer) == []


# --- ingestor (dedup) --------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_cria_e_classifica_bucket(session, org):
    spec = {
        "source": "bizzu_app", "type": "nps", "external_id": "partner:nps:x:1",
        "score": 10, "text": "top", "occurred_at": "2026-06-01T09:00:00Z",
    }
    item = await ingest_feedback_item(session, org.id, None, spec, classify=False)
    assert item.nps_bucket == "promoter"
    assert isinstance(item.occurred_at, datetime)
    assert item.sentiment is None  # classify=False → sem IA


@pytest.mark.asyncio
async def test_ingest_dedup_atualiza_nao_duplica(session, org):
    spec = {"source": "bizzu_app", "type": "nps", "external_id": "partner:nps:y:1", "score": 9, "text": "bom"}
    a = await ingest_feedback_item(session, org.id, None, spec, classify=False)
    b = await ingest_feedback_item(session, org.id, None, {**spec, "score": 5, "text": "piorou"}, classify=False)
    assert b.id == a.id
    assert b.score == 5 and b.nps_bucket == "detractor" and b.text == "piorou"
    rows = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.organization_id == org.id))
    ).scalars().all()
    assert len(rows) == 1


# --- endpoint /360 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_360_unifica_fontes(client, session, org):
    contact = Contact(
        organization_id=org.id, phone="5524998365809", name="Jair", opt_in=True,
        profile_data={"partner": {"profile": "ativo_promotor", "subscription": {"state": "active_paying"}}},
    )
    session.add(contact)
    await session.flush()

    # sinal ingerido de fonte externa (FeedbackItem)
    await ingest_feedback_item(
        session, org.id, contact.id,
        {"source": "bizzu_billing", "type": "churn", "external_id": "partner:churn:z",
         "text": "achei caro", "occurred_at": "2026-06-02T10:00:00Z"},
        classify=False,
    )

    # resposta coletada pelo Escuta (SurveyResponse via WhatsApp)
    survey = Survey(organization_id=org.id, name="NPS Bizzu", type="nps", status="active", questions=[])
    session.add(survey)
    await session.flush()
    run = SurveyRun(survey_id=survey.id, organization_id=org.id, trigger="t", status="done")
    session.add(run)
    await session.flush()
    session.add(
        SurveyResponse(
            survey_run_id=run.id, contact_id=contact.id, organization_id=org.id,
            status="closed", answer_score=9, nps_bucket="promoter", answer_text="curti",
            sent_at=datetime(2026, 6, 1, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
    )
    await session.commit()

    r = await client.get(f"/api/contacts/{contact.id}/360")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["contact"]["name"] == "Jair"
    assert data["partner"]["profile"] == "ativo_promotor"
    assert data["summary"] == {"total": 2, "feedback_items": 1, "survey_responses": 1}
    assert {t["kind"] for t in data["timeline"]} == {"feedback_item", "survey"}
    # timeline desc por data: churn (06-02) vem antes do survey (06-01)
    assert data["timeline"][0]["type"] == "churn"


@pytest.mark.asyncio
async def test_contact_360_404(client, org):
    r = await client.get(f"/api/contacts/{uuid.uuid4()}/360")
    assert r.status_code == 404
