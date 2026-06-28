"""Testes dos endpoints da Central de Fontes — GET/PUT/POST /api/sources.

Espelha o padrão de test_agent_config (AsyncClient ASGI + override de get_session pela
session in-memory do conftest). `available` é controlado monkeypatchando a constante de
env do cliente Partner; o POST tem o `run_bizzu_sync` monkeypatchado para NÃO rodar de
verdade na suíte (só registra a chamada). Nenhum teste toca rede.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.config import settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.domain.sources import DEFAULT_SYNC  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Organization  # noqa: E402

CONTRATO_KEYS = {"key", "label", "descricao", "available", "enabled", "sync"}


def _set_available(monkeypatch, present: bool) -> None:
    """Controla `available`: a constante de env da chave do cliente Partner (sem expor valor)."""
    monkeypatch.setattr(
        "app.integrations.bizzu_partner.BIZZU_PARTNER_API_KEY",
        "test-key" if present else None,
    )


@pytest_asyncio.fixture
async def client(session):
    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


async def _seed_org(session) -> Organization:
    o = Organization(slug=settings.default_org_slug, name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _reload_org(session) -> Organization:
    return (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_get_lista_fonte(client, session, monkeypatch):
    _set_available(monkeypatch, True)
    await _seed_org(session)
    r = await client.get("/api/sources")
    assert r.status_code == 200, r.text
    fontes = r.json()["sources"]
    assert len(fontes) == 1
    f = fontes[0]
    assert set(f) == CONTRATO_KEYS
    assert f["key"] == "bizzu_partner"
    assert f["available"] is True
    assert f["enabled"] is False
    assert f["sync"]["status"] == "idle"


@pytest.mark.asyncio
async def test_put_liga_e_persiste(client, session, monkeypatch):
    _set_available(monkeypatch, True)
    await _seed_org(session)
    r = await client.put("/api/sources/bizzu_partner", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True
    org = await _reload_org(session)
    assert org.settings["sources"]["bizzu_partner"]["enabled"] is True
    g = await client.get("/api/sources")
    assert g.json()["sources"][0]["enabled"] is True


@pytest.mark.asyncio
async def test_put_desliga(client, session, monkeypatch):
    _set_available(monkeypatch, True)
    await _seed_org(session)
    await client.put("/api/sources/bizzu_partner", json={"enabled": True})
    r = await client.put("/api/sources/bizzu_partner", json={"enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    org = await _reload_org(session)
    assert org.settings["sources"]["bizzu_partner"]["enabled"] is False


@pytest.mark.asyncio
async def test_put_key_invalida_422(client, session, monkeypatch):
    _set_available(monkeypatch, True)
    await _seed_org(session)
    r = await client.put("/api/sources/fonte_inexistente", json={"enabled": True})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_liga_indisponivel_409(client, session, monkeypatch):
    """Ligar (enabled=true) uma fonte sem a chave no deploy -> 409."""
    _set_available(monkeypatch, False)
    await _seed_org(session)
    r = await client.put("/api/sources/bizzu_partner", json={"enabled": True})
    assert r.status_code == 409
    assert "BIZZU_PARTNER_API_KEY" in r.json()["detail"]
    # desligar (enabled=false) é sempre permitido, mesmo indisponível
    r2 = await client.put("/api/sources/bizzu_partner", json={"enabled": False})
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_post_sync_desligada_409(client, session, monkeypatch):
    """Fonte disponível mas DESLIGADA -> POST 409 'fonte desligada'."""
    _set_available(monkeypatch, True)
    await _seed_org(session)
    r = await client.post("/api/sources/bizzu_partner/sync")
    assert r.status_code == 409
    assert "desligada" in r.json()["detail"]


@pytest.mark.asyncio
async def test_post_sync_indisponivel_409(client, session, monkeypatch):
    _set_available(monkeypatch, False)
    await _seed_org(session)
    r = await client.post("/api/sources/bizzu_partner/sync")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_post_sync_key_invalida_422(client, session, monkeypatch):
    _set_available(monkeypatch, True)
    await _seed_org(session)
    r = await client.post("/api/sources/fonte_inexistente/sync")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_sync_202_dispara(client, session, monkeypatch):
    """Fonte ligada+disponível -> 202, status running e agenda o serviço (monkeypatchado)."""
    _set_available(monkeypatch, True)
    org = await _seed_org(session)

    chamadas: list = []

    async def _fake_run(organization_id, **kwargs):
        chamadas.append(organization_id)

    monkeypatch.setattr("app.api.admin.run_bizzu_sync", _fake_run)

    await client.put("/api/sources/bizzu_partner", json={"enabled": True})
    r = await client.post("/api/sources/bizzu_partner/sync")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["key"] == "bizzu_partner"
    assert body["sync"]["status"] == "running"
    assert body["sync"]["started_at"] is not None
    assert body["sync"]["processed"] == 0
    # agendou o serviço com a org certa (rodou no background, mas é no-op aqui)
    assert chamadas == [org.id]
    # estado 'running' persistido para o polling
    org = await _reload_org(session)
    assert org.settings["sources"]["bizzu_partner"]["sync"]["status"] == "running"


@pytest.mark.asyncio
async def test_post_sync_em_andamento_409(client, session, monkeypatch):
    """Um 2º POST com sync 'running' recente (< 15 min) -> 409 'já em andamento'."""
    _set_available(monkeypatch, True)
    await _seed_org(session)

    async def _fake_run(organization_id, **kwargs):  # no-op: deixa o estado 'running'
        return None

    monkeypatch.setattr("app.api.admin.run_bizzu_sync", _fake_run)

    await client.put("/api/sources/bizzu_partner", json={"enabled": True})
    r1 = await client.post("/api/sources/bizzu_partner/sync")
    assert r1.status_code == 202
    r2 = await client.post("/api/sources/bizzu_partner/sync")
    assert r2.status_code == 409
    assert "andamento" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_post_sync_stale_redispara(client, session, monkeypatch):
    """Sync 'running' travado há >= 15 min é stale: novo POST RE-dispara (202)."""
    _set_available(monkeypatch, True)
    org = await _seed_org(session)

    async def _fake_run(organization_id, **kwargs):
        return None

    monkeypatch.setattr("app.api.admin.run_bizzu_sync", _fake_run)

    # injeta um running iniciado há 20 min (travado)
    velho = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    org.settings = {
        "sources": {
            "bizzu_partner": {
                "enabled": True,
                "sync": {**DEFAULT_SYNC, "status": "running", "started_at": velho},
            }
        }
    }
    await session.commit()

    r = await client.post("/api/sources/bizzu_partner/sync")
    assert r.status_code == 202, r.text
    assert r.json()["sync"]["status"] == "running"
