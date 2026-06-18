"""Testes de AUTENTICAÇÃO de ORIGEM do webhook do WAHA (#4) e do PAINEL (#3).

Webhook (POST /api/webhook/waha), via `require_waha_webhook_secret` (X-Webhook-Secret):
- COM secret setado: header ausente/errado -> 401 (fail-closed); header certo -> 200.
- SEM secret (default da suíte): aceita e emite logger.warning.

Painel (qualquer rota com a dep `require_panel_key`, X-Panel-Key):
- COM PANEL_API_KEY setado: header ausente/errado -> 401; header certo -> passa.
- SEM PANEL_API_KEY (default): libera + logger.warning.

Infra: app real + SQLite in-memory (override de get_session), igual aos demais.
NENHUM disparo real de WhatsApp. O segredo é injetado por monkeypatch no módulo
`app.api._security` (onde a dependency lê `settings`), sem tocar variáveis de
ambiente nem o conftest compartilhado.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import app.api._security as _security  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402


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
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _contact(session, org, phone):
    c = Contact(organization_id=org.id, phone=phone, name="Lead", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    return c


def _payload(*, from_, body, msg_id):
    return {
        "event": "message",
        "payload": {"from": f"{from_}@c.us", "body": body, "id": msg_id, "fromMe": False},
    }


def _set_secret(monkeypatch, *, waha=None, panel=None):
    """Injeta segredos no `settings` que a dependency lê (módulo _security)."""
    monkeypatch.setattr(
        _security,
        "settings",
        dataclasses.replace(_security.settings, waha_webhook_secret=waha, panel_api_key=panel),
    )


# ============================ WEBHOOK (#4) ====================================


@pytest.mark.asyncio
async def test_webhook_sem_secret_aceita_e_avisa(client, org, session, monkeypatch, caplog):
    """Default da suíte: WAHA_WEBHOOK_SECRET ausente -> 200 + WARN (fail-open)."""
    _set_secret(monkeypatch, waha=None)
    await _contact(session, org, "5531900000010")
    await session.commit()

    with caplog.at_level(logging.WARNING, logger="app.api._security"):
        r = await client.post(
            "/api/webhook/waha",
            json=_payload(from_="5531900000010", body="oi", msg_id="wamid.AUTH0"),
        )
    assert r.status_code == 200, r.text
    assert any("SEM autenticação" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_webhook_com_secret_sem_header_401(client, org, session, monkeypatch):
    """Com secret setado e header ausente -> 401 (fail-closed)."""
    _set_secret(monkeypatch, waha="s3cr3t")
    await _contact(session, org, "5531900000011")
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_="5531900000011", body="oi", msg_id="wamid.AUTH1"),
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_webhook_com_secret_header_errado_401(client, org, session, monkeypatch):
    """Com secret setado e header errado -> 401 (fail-closed)."""
    _set_secret(monkeypatch, waha="s3cr3t")
    await _contact(session, org, "5531900000012")
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        headers={"X-Webhook-Secret": "errado"},
        json=_payload(from_="5531900000012", body="oi", msg_id="wamid.AUTH2"),
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_webhook_com_secret_header_certo_200(client, org, session, monkeypatch):
    """Com secret setado e header CORRETO -> 200 (passa)."""
    _set_secret(monkeypatch, waha="s3cr3t")
    await _contact(session, org, "5531900000013")
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        headers={"X-Webhook-Secret": "s3cr3t"},
        json=_payload(from_="5531900000013", body="oi", msg_id="wamid.AUTH3"),
    )
    assert r.status_code == 200, r.text


# ============================ PAINEL (#3) =====================================


@pytest.mark.asyncio
async def test_painel_sem_key_libera_e_avisa(client, org, monkeypatch, caplog):
    """Default da suíte: PANEL_API_KEY ausente -> rota do painel passa + WARN."""
    _set_secret(monkeypatch, panel=None)
    with caplog.at_level(logging.WARNING, logger="app.api._security"):
        r = await client.get("/api/selos")  # rota do admin_router (painel)
    assert r.status_code == 200, r.text
    assert any("painel SEM autenticação" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_painel_com_key_sem_header_401(client, org, monkeypatch):
    """Com PANEL_API_KEY setado e header ausente -> 401 (fail-closed)."""
    _set_secret(monkeypatch, panel="p4nel")
    r = await client.get("/api/selos")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_painel_com_key_header_certo_passa(client, org, monkeypatch):
    """Com PANEL_API_KEY setado e header CORRETO -> a auth passa (rota responde)."""
    _set_secret(monkeypatch, panel="p4nel")
    r = await client.get("/api/selos", headers={"X-Panel-Key": "p4nel"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_webhook_nao_exige_panel_key(client, org, session, monkeypatch):
    """O webhook NÃO herda a auth do painel: com PANEL_API_KEY setado (mas sem
    WAHA_WEBHOOK_SECRET), o POST no webhook continua 200 sem X-Panel-Key."""
    _set_secret(monkeypatch, waha=None, panel="p4nel")
    await _contact(session, org, "5531900000014")
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_="5531900000014", body="oi", msg_id="wamid.AUTH4"),
    )
    assert r.status_code == 200, r.text
