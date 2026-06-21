"""Testes da automação de follow-up (níveis 1-2) no Escuta:

- PATCH /api/feedbacks/{id}: set follow_up_at (ISO) e clear (null).
- Auto-reabrir no webhook inbound: feedbacks do contato em status TERMINAL ou
  'aguardando_retorno' voltam para 'a_abordar' + follow_up_at=NULL ao chegar inbound.
- Fila GET /api/feedbacks?follow_up_vencido=... + contagem 'follow_up_pendentes'
  (vencidos) no bloco 'metricas' do GET /api/central/overview.

Mesma infra dos demais testes: app real + SQLite in-memory (override de get_session),
LLM desligado no ingestor (captura 100% offline), NENHUM disparo real de WhatsApp.
"""
from __future__ import annotations

import dataclasses
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

import app.domain.feedback.ingest as _ingest  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    """Desliga o LLM no ingestor: captura offline e determinística (sem Groq)."""
    monkeypatch.setattr(
        _ingest, "settings", dataclasses.replace(_ingest.settings, llm_enabled=False)
    )


@pytest_asyncio.fixture
async def org(session):
    # slug 'bizzu' == settings.default_org_slug (o webhook/_get_org resolvem por ele).
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


async def _contact(session, org, phone, name, **kw):
    c = Contact(
        organization_id=org.id,
        phone=phone,
        name=name,
        opt_in=kw.pop("opt_in", True),
        profile_data=kw.pop("profile_data", {}),
    )
    session.add(c)
    await session.flush()
    return c


async def _feedback(session, org, *, contact_id=None, status="a_abordar", follow_up_at=None, **kw):
    f = FeedbackItem(
        organization_id=org.id,
        contact_id=contact_id,
        source=kw.pop("source", "whatsapp"),
        type=kw.pop("type", "churn"),
        external_id=kw.pop("external_id", None),
        text=kw.pop("text", "preciso voltar a falar com esse cliente"),
        action_status=status,
        follow_up_at=follow_up_at,
        **kw,
    )
    session.add(f)
    await session.flush()
    return f


def _inbound_payload(*, from_, body, msg_id):
    return {
        "event": "message",
        "payload": {"from": f"{from_}@c.us", "body": body, "id": msg_id, "fromMe": False},
    }


# --- PATCH: set / clear follow_up_at -----------------------------------------


@pytest.mark.asyncio
async def test_patch_set_follow_up_at(client, org, session):
    f = await _feedback(session, org)
    await session.commit()

    when = "2026-07-20T15:30:00Z"
    r = await client.patch(f"/api/feedbacks/{f.id}", json={"follow_up_at": when})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["follow_up_at"] is not None
    # Aware/UTC normalizado por _coerce_dt; bate o instante enviado.
    assert datetime.fromisoformat(body["follow_up_at"]) == datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc)

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == f.id))).scalar_one()
    assert row.follow_up_at is not None


@pytest.mark.asyncio
async def test_patch_clear_follow_up_at(client, org, session):
    f = await _feedback(
        session, org, follow_up_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    )
    await session.commit()

    r = await client.patch(f"/api/feedbacks/{f.id}", json={"follow_up_at": None})
    assert r.status_code == 200, r.text
    assert r.json()["follow_up_at"] is None

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == f.id))).scalar_one()
    assert row.follow_up_at is None


@pytest.mark.asyncio
async def test_patch_follow_up_ausente_nao_mexe(client, org, session):
    """Campo ausente no corpo => mantém o follow_up_at atual (model_fields_set)."""
    f = await _feedback(
        session, org, follow_up_at=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    )
    await session.commit()

    r = await client.patch(f"/api/feedbacks/{f.id}", json={"action_note": "liguei"})
    assert r.status_code == 200, r.text
    assert r.json()["follow_up_at"] is not None  # intacto


# --- auto-reabrir no inbound -------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status_terminal", ["resolvido", "sem_retorno", "descartado", "aguardando_retorno"])
async def test_inbound_reabre_status_terminal_e_aguardando(client, org, session, status_terminal):
    phone = "5531988880001"
    contato = await _contact(session, org, phone, "Lead Reabrir")
    f = await _feedback(
        session, org, contact_id=contato.id, status=status_terminal,
        follow_up_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_inbound_payload(from_=phone, body="oi, voltei a usar!", msg_id="wamid.RE1"),
    )
    assert r.status_code == 200, r.text

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == f.id))).scalar_one()
    assert row.action_status == "a_abordar"  # reaberto
    assert row.follow_up_at is None  # follow-up zerado


@pytest.mark.asyncio
async def test_inbound_nao_mexe_em_status_ativo(client, org, session):
    """'em_acompanhamento' já está ativo: o inbound NÃO o derruba para 'a_abordar'."""
    phone = "5531988880002"
    contato = await _contact(session, org, phone, "Lead Ativo")
    f = await _feedback(session, org, contact_id=contato.id, status="em_acompanhamento")
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_inbound_payload(from_=phone, body="alguma novidade?", msg_id="wamid.RE2"),
    )
    assert r.status_code == 200, r.text

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == f.id))).scalar_one()
    assert row.action_status == "em_acompanhamento"  # intacto


@pytest.mark.asyncio
async def test_inbound_reabrir_respeita_flag_off(client, session):
    """selo_auto_inbound=False desliga TAMBÉM o auto-reabrir (mesmo gate do selo)."""
    o = Organization(slug="bizzu", name="Bizzu", settings={"selo_auto_inbound": False})
    session.add(o)
    await session.commit()

    phone = "5531988880003"
    contato = await _contact(session, o, phone, "Lead Flag Off")
    f = await _feedback(session, o, contact_id=contato.id, status="resolvido")
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_inbound_payload(from_=phone, body="oi", msg_id="wamid.RE3"),
    )
    assert r.status_code == 200, r.text

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == f.id))).scalar_one()
    assert row.action_status == "resolvido"  # não reabriu (flag off)


# --- fila: filtro follow_up_vencido ------------------------------------------


@pytest.mark.asyncio
async def test_lista_filtra_follow_up_vencido(client, org, session):
    agora = datetime.now(timezone.utc)
    contato = await _contact(session, org, "5531977770001", "Lead Fila")
    # vencido (passado)
    venc = await _feedback(
        session, org, contact_id=contato.id, follow_up_at=agora - timedelta(days=2),
        external_id="venc",
    )
    # futuro (não vencido)
    await _feedback(
        session, org, contact_id=contato.id, follow_up_at=agora + timedelta(days=5),
        external_id="fut",
    )
    # sem follow-up
    await _feedback(session, org, contact_id=contato.id, follow_up_at=None, external_id="sem")
    await session.commit()

    r = await client.get("/api/feedbacks", params={"follow_up_vencido": "true"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    ids = [it["id"] for it in data["items"]]
    assert str(venc.id) in ids

    r2 = await client.get("/api/feedbacks", params={"follow_up_vencido": "false"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["total"] == 2  # futuro + sem follow-up


# --- central: contagem follow_up_pendentes -----------------------------------


@pytest.mark.asyncio
async def test_central_overview_conta_follow_up_pendentes(client, org, session):
    agora = datetime.now(timezone.utc)
    contato = await _contact(session, org, "5531966660001", "Lead Central")
    await _feedback(
        session, org, contact_id=contato.id, follow_up_at=agora - timedelta(hours=1),
        external_id="p1",
    )
    await _feedback(
        session, org, contact_id=contato.id, follow_up_at=agora - timedelta(days=3),
        external_id="p2",
    )
    await _feedback(
        session, org, contact_id=contato.id, follow_up_at=agora + timedelta(days=1),
        external_id="fut",
    )
    await _feedback(session, org, contact_id=contato.id, follow_up_at=None, external_id="sem")
    await session.commit()

    r = await client.get("/api/central/overview")
    assert r.status_code == 200, r.text
    metricas = r.json()["metricas"]
    assert metricas["follow_up_pendentes"] == 2  # só os 2 vencidos
