"""Testes da API PÚBLICA de integração — GET /api/integration/feedbacks e /clientes.

Cobrem o contrato de auth por header X-API-Key:
  (a) sem header -> 401;
  (b) header errado -> 401;
  (c) com a chave certa -> 200 e filtra por selo (a "tag" da reunião);
  (d) sem INTEGRATION_API_KEY configurada -> 503 (integração desligada).

Mesma infra dos demais testes de API: httpx ASGITransport + SQLite in-memory
(override de get_session). O token é injetado na dataclass frozen de settings via
object.__setattr__ (restaurado no teardown), igual ao test_events_bizzu.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.config import settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402

API_KEY = "test-integration-key"


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client(session):
    """Client com banco SQLite e INTEGRATION_API_KEY de teste injetada."""

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override

    original_key = settings.integration_api_key
    object.__setattr__(settings, "integration_api_key", API_KEY)  # dataclass frozen
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        object.__setattr__(settings, "integration_api_key", original_key)
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _seed_feedbacks(session, org):
    """Ana tem o selo 'vip' + 1 feedback nps; Bob sem selo + 1 feedback churn."""
    ana = Contact(
        organization_id=org.id, phone="5531987654321", name="Ana",
        opt_in=True, profile_data={"selos": ["vip"]},
    )
    bob = Contact(
        organization_id=org.id, phone="5531912345678", name="Bob",
        opt_in=True, profile_data={},
    )
    session.add_all([ana, bob])
    await session.flush()
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="bizzu_app",
                type="nps", external_id="a:nps", score=9, nps_bucket="promoter",
                text="adoro", sentiment="positivo", occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=bob.id, source="bizzu_billing",
                type="churn", external_id="b:churn", text="caro",
                sentiment="negativo", occurred_at=_dt(2026, 6, 5),
            ),
        ]
    )
    await session.commit()
    return ana, bob


# --- (a) sem header -> 401 ----------------------------------------------------


@pytest.mark.asyncio
async def test_feedbacks_sem_header_401(client, org):
    r = await client.get("/api/integration/feedbacks")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_clientes_sem_header_401(client, org):
    r = await client.get("/api/integration/clientes")
    assert r.status_code == 401, r.text


# --- (b) header errado -> 401 -------------------------------------------------


@pytest.mark.asyncio
async def test_feedbacks_header_errado_401(client, org):
    r = await client.get("/api/integration/feedbacks", headers={"X-API-Key": "errado"})
    assert r.status_code == 401, r.text


# --- (c) com a chave certa -> 200 e filtra por selo ---------------------------


@pytest.mark.asyncio
async def test_feedbacks_chave_certa_200_filtra_por_selo(client, org, session):
    await _seed_feedbacks(session, org)
    hdr = {"X-API-Key": API_KEY}

    # Sem filtro: traz os dois feedbacks, JSON enxuto com as chaves do contrato.
    r = await client.get("/api/integration/feedbacks", headers=hdr)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 2
    assert set(data[0].keys()) == {
        "id", "tipo", "texto", "sentimento", "action_status",
        "selos", "contato_nome", "occurred_at",
    }

    # ?selo=vip ("puxar por tag"): só o feedback do contato com o selo.
    r = await client.get("/api/integration/feedbacks", headers=hdr, params={"selo": "vip"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [f["contato_nome"] for f in data] == ["Ana"]
    assert data[0]["selos"] == ["vip"]
    assert data[0]["tipo"] == "nps"

    # ?tipo=churn: filtra por type.
    r = await client.get("/api/integration/feedbacks", headers=hdr, params={"tipo": "churn"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [f["contato_nome"] for f in data] == ["Bob"]
    assert data[0]["sentimento"] == "negativo"


@pytest.mark.asyncio
async def test_clientes_chave_certa_200(client, org, session):
    await _seed_feedbacks(session, org)
    r = await client.get("/api/integration/clientes", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200, r.text
    data = r.json()
    assert {c["nome"] for c in data} == {"Ana", "Bob"}
    ana = next(c for c in data if c["nome"] == "Ana")
    assert set(ana.keys()) == {
        "id", "nome", "whatsapp", "tem_whatsapp", "estado", "selos", "health_band",
    }
    assert ana["tem_whatsapp"] is True
    assert ana["selos"] == ["vip"]


# --- (d) sem env configurada -> 503 -------------------------------------------


@pytest.mark.asyncio
async def test_sem_env_configurada_503(client, org):
    """INTEGRATION_API_KEY ausente -> 503 mesmo com header (integração desligada)."""
    original = settings.integration_api_key
    object.__setattr__(settings, "integration_api_key", None)
    try:
        r = await client.get(
            "/api/integration/feedbacks", headers={"X-API-Key": API_KEY}
        )
        assert r.status_code == 503, r.text
        r = await client.get("/api/integration/clientes", headers={"X-API-Key": API_KEY})
        assert r.status_code == 503, r.text
    finally:
        object.__setattr__(settings, "integration_api_key", original)
