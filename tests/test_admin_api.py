"""Testes da API do painel (admin.py) — httpx ASGITransport + SQLite in-memory.

Override de `get_session` (banco de teste) e `get_messaging` (FakeMessagingService):
nenhum teste toca Supabase nem WAHA.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import (  # noqa: E402
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_SENT,
    SurveyResponse,
    SurveyRun,
)
from tests.fakes import FakeMessagingService  # noqa: E402


@pytest_asyncio.fixture
async def client(session):
    """Client HTTP com o app real, banco SQLite e messaging fake."""
    fake = FakeMessagingService()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_messaging] = lambda: fake
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.fake_messaging = fake  # type: ignore[attr-defined]
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


@pytest.mark.asyncio
async def test_dashboard_vazio(client, org):
    r = await client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert data["org"]["slug"] == "bizzu"
    assert data["kpis"]["sent"] == 0
    assert data["kpis"]["nps"] is None
    assert data["nps"] == data["kpis"]  # alias retrocompat
    assert data["exit"] == {"sent": 0, "answered": 0, "recent": []}
    assert data["recent"] == []


@pytest.mark.asyncio
async def test_dashboard_separa_nps_de_exit(client, org, session):
    """Mix de responses NPS + exit: KPIs de NPS não são contaminados pela exit,
    e o bloco `exit` traz contadores e os motivos de cancelamento."""
    nps_survey = (
        await client.post(
            "/api/surveys",
            json={"name": "NPS Bizzu", "nps_question": "De 0 a 10?", "reason_prompt": "Por quê?"},
        )
    ).json()
    exit_survey = (
        await client.post(
            "/api/surveys",
            json={"name": "Exit Bizzu", "type": "exit", "reason_prompt": "O que te levou a cancelar?"},
        )
    ).json()

    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    bia = Contact(organization_id=org.id, phone="5531900000002", name="Bia", opt_in=True, profile_data={})
    jair = Contact(organization_id=org.id, phone="5524998365809", name="Jair Filho", opt_in=True, profile_data={})
    caio = Contact(organization_id=org.id, phone="5531900000004", name="Caio", opt_in=True, profile_data={})
    session.add_all([ana, bia, jair, caio])
    await session.flush()

    now = datetime.now(timezone.utc)
    run_nps = SurveyRun(survey_id=uuid.UUID(nps_survey["id"]), organization_id=org.id)
    run_exit = SurveyRun(survey_id=uuid.UUID(exit_survey["id"]), organization_id=org.id)
    session.add_all([run_nps, run_exit])
    await session.flush()

    session.add_all(
        [
            # NPS completa: nota 9 (promotora) + motivo, fechada.
            SurveyResponse(
                survey_run_id=run_nps.id, contact_id=ana.id, organization_id=org.id,
                status=STATUS_CLOSED, answer_score=9, nps_bucket="promoter",
                answer_text="resumos ótimos", sent_at=now, answered_at=now, closed_at=now,
            ),
            # NPS só enviada (sem resposta ainda).
            SurveyResponse(
                survey_run_id=run_nps.id, contact_id=bia.id, organization_id=org.id,
                status=STATUS_SENT, sent_at=now,
            ),
            # Exit respondida: motivo SEM nota (answer_score NULL), fechada.
            SurveyResponse(
                survey_run_id=run_exit.id, contact_id=jair.id, organization_id=org.id,
                status=STATUS_CLOSED, answer_text="Cancelei porque ficou caro",
                sent_at=now, answered_at=now, closed_at=now,
            ),
            # Exit enviada, aguardando o motivo.
            SurveyResponse(
                survey_run_id=run_exit.id, contact_id=caio.id, organization_id=org.id,
                status=STATUS_AWAITING_REASON, sent_at=now,
            ),
        ]
    )
    await session.commit()

    data = (await client.get("/api/dashboard")).json()

    # KPIs de NPS contam SÓ as responses do survey 'nps' (2 enviadas, 1 nota).
    k = data["kpis"]
    assert k["sent"] == 2
    assert k["answered"] == 1
    assert k["closed"] == 1
    assert k["response_rate"] == 50
    assert k["promoters"] == 1 and k["passives"] == 0 and k["detractors"] == 0
    assert k["nps"] == 100  # a exit fechada NÃO vira resposta/detrator de NPS
    assert data["nps"] == k

    # Bloco exit: 2 enviadas, 1 respondida (closed com answer_text) + motivo.
    e = data["exit"]
    assert e["sent"] == 2
    assert e["answered"] == 1
    assert len(e["recent"]) == 1
    motivo = e["recent"][0]
    assert motivo["contact_name"] == "Jair Filho"
    assert motivo["text"] == "Cancelei porque ficou caro"
    assert motivo["closed_at"] is not None

    # Recentes (lista geral) ganham survey_type/survey_name.
    assert len(data["recent"]) == 4
    by_contact = {r["contact_name"]: r for r in data["recent"]}
    assert by_contact["Jair Filho"]["survey_type"] == "exit"
    assert by_contact["Jair Filho"]["survey_name"] == "Exit Bizzu"
    assert by_contact["Jair Filho"]["score"] is None
    assert by_contact["Ana"]["survey_type"] == "nps"
    assert by_contact["Ana"]["survey_name"] == "NPS Bizzu"
    assert by_contact["Caio"]["status"] == STATUS_AWAITING_REASON


@pytest.mark.asyncio
async def test_dashboard_sem_org_da_404(client):
    r = await client.get("/api/dashboard")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_crud_survey_e_contato(client, org):
    # cria survey
    r = await client.post(
        "/api/surveys",
        json={"name": "NPS Piloto", "nps_question": "De 0 a 10?", "reason_prompt": "Por quê?"},
    )
    assert r.status_code == 201, r.text
    survey = r.json()
    assert survey["nps_question"] == "De 0 a 10?"

    # duplicada -> 409
    r = await client.post(
        "/api/surveys",
        json={"name": "NPS Piloto", "nps_question": "x", "reason_prompt": "y"},
    )
    assert r.status_code == 409

    # cria contato (normaliza máscara)
    r = await client.post("/api/contacts", json={"phone": "+55 (24) 99836-5809", "name": "Jair"})
    assert r.status_code == 201, r.text
    contact = r.json()
    assert contact["phone"] == "5524998365809"
    assert contact["opt_in"] is True

    # duplicado -> 409
    r = await client.post("/api/contacts", json={"phone": "5524998365809"})
    assert r.status_code == 409

    # listas
    assert len((await client.get("/api/surveys")).json()) == 1
    assert len((await client.get("/api/contacts")).json()) == 1


@pytest.mark.asyncio
async def test_dispatch_envia_e_registra(client, org):
    survey = (
        await client.post(
            "/api/surveys",
            json={"name": "NPS X", "nps_question": "De 0 a 10, recomendaria?", "reason_prompt": "Conta mais?"},
        )
    ).json()
    contact = (await client.post("/api/contacts", json={"phone": "5531988887777", "name": "Ana"})).json()

    r = await client.post(f"/api/surveys/{survey['id']}/dispatch", json={"contact_ids": [contact["id"]]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["count"] == 1
    assert out["dispatched_to"][0]["phone"] == "5531988887777"

    # enviou de verdade pelo canal (fake) com saudação renderizada
    sent = client.fake_messaging.sent
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "5531988887777"
    assert "De 0 a 10" in sent[0]["text"]

    # dashboard reflete o envio
    kpis = (await client.get("/api/dashboard")).json()["kpis"]
    assert kpis["sent"] == 1


@pytest.mark.asyncio
async def test_dispatch_contato_inexistente_404(client, org):
    survey = (
        await client.post(
            "/api/surveys", json={"name": "S", "nps_question": "q", "reason_prompt": "r"}
        )
    ).json()
    r = await client.post(
        f"/api/surveys/{survey['id']}/dispatch",
        json={"contact_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert r.status_code == 404
