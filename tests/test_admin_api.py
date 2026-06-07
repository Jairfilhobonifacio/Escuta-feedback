"""Testes da API do painel (admin.py) — httpx ASGITransport + SQLite in-memory.

Override de `get_session` (banco de teste) e `get_messaging` (FakeMessagingService):
nenhum teste toca Supabase nem WAHA.
"""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Organization  # noqa: E402
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
    assert data["recent"] == []


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
