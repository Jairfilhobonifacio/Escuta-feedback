"""Testes do Item C — reordenação manual DENTRO da coluna (campo='action_status').

Mesma infra de test_boards.py: app real + SQLite in-memory (override de get_session)
+ messaging fake. Nenhum teste toca Supabase/WAHA/Groq. A ordem manual persiste em
Organization.settings["board_card_order"] — sem migration.

DECISÃO DE PRODUTO (fixa) coberta aqui: cards SEM ordem manual (novos) aparecem por
URGÊNCIA no TOPO; cards COM ordem manual abaixo, na ordem salva.
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

from app.api.admin import get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


@pytest_asyncio.fixture
async def client(session):
    fake = FakeMessagingService()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_messaging] = lambda: fake
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


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


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


async def _fb(session, org, contact, ext, status="a_abordar", **kw):
    f = FeedbackItem(
        organization_id=org.id,
        contact_id=contact.id if contact else None,
        source=kw.pop("source", "bizzu_app"),
        type=kw.pop("type", "outro"),
        external_id=ext,
        text=kw.pop("text", ext),
        action_status=status,
        occurred_at=kw.pop("occurred_at", _dt(2026, 6, 1)),
        **kw,
    )
    session.add(f)
    await session.flush()
    return f


async def _board_action_status(client):
    """Cria um board action_status com a coluna 'novo' e devolve o id."""
    r = await client.post("/api/boards", json={
        "nome": "Ops", "campo": "action_status",
        "colunas": [{"nome": "A abordar", "valor": "a_abordar"}, {"nome": "Resolvido", "valor": "resolvido"}],
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _ids_da_coluna(data, valor):
    cols = {c["valor"]: c for c in data["colunas"]}
    return [it["id"] for it in cols[valor]["items"]]


# --- reorder persiste e reflete no GET ----------------------------------------


@pytest.mark.asyncio
async def test_reorder_intra_coluna_persiste_e_reflete_no_get(client, org, session):
    """Mover um card p/ position fixa reordena a coluna no GET /items (ordem salva
    vence a urgência) e persiste em settings['board_card_order']."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    a = await _fb(session, org, ana, "a")
    b = await _fb(session, org, ana, "b")
    c = await _fb(session, org, ana, "c")
    await session.commit()
    bid = await _board_action_status(client)

    # Ordena manualmente: c, a, b  (cada move põe o card na posição pedida).
    for pos, fb in [(0, c), (1, a), (2, b)]:
        r = await client.post(
            f"/api/feedbacks/{fb.id}/board-move",
            json={"campo": "action_status", "valor": "a_abordar", "position": pos},
        )
        assert r.status_code == 200, r.text

    data = (await client.get(f"/api/boards/{bid}/items")).json()
    assert _ids_da_coluna(data, "a_abordar") == [str(c.id), str(a.id), str(b.id)]

    # Persistiu no JSONB de settings (sem migration).
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    assert o.settings["board_card_order"]["a_abordar"] == [str(c.id), str(a.id), str(b.id)]


# --- idempotência -------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_idempotente_mesma_posicao(client, org, session):
    """Mover 2x para a MESMA posição = mesmo array (remove-then-insert idempotente)."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    a = await _fb(session, org, ana, "a")
    b = await _fb(session, org, ana, "b")
    await session.commit()
    await _board_action_status(client)

    base = lambda fb, pos: client.post(  # noqa: E731
        f"/api/feedbacks/{fb.id}/board-move",
        json={"campo": "action_status", "valor": "a_abordar", "position": pos},
    )
    await base(a, 0)
    await base(b, 1)
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    primeiro = list(o.settings["board_card_order"]["a_abordar"])

    # Re-move b para a mesma posição 1 -> array idêntico.
    await base(b, 1)
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    assert o.settings["board_card_order"]["a_abordar"] == primeiro == [str(a.id), str(b.id)]


# --- novos cards entram por urgência no topo ----------------------------------


@pytest.mark.asyncio
async def test_novos_sem_ordem_entram_por_urgencia_no_topo(client, org, session):
    """Card SEM ordem manual aparece por urgência ACIMA dos cards já ordenados."""
    risco = await _contact(
        session, org, "5531900000001", "Risco",
        profile_data={"partner": {"profile": "ativo_em_risco", "subscription": {"planType": "anual"}}},
    )
    feliz = await _contact(session, org, "5531900000002", "Feliz")
    # 'velho' será fixado manualmente; 'urgente' (churn negativo de conta em risco) NÃO.
    velho = await _fb(session, org, feliz, "velho", type="elogio", sentiment="positivo")
    await session.commit()
    bid = await _board_action_status(client)

    # Fixa só o 'velho' na coluna (ordem manual = [velho]).
    r = await client.post(
        f"/api/feedbacks/{velho.id}/board-move",
        json={"campo": "action_status", "valor": "a_abordar", "position": 0},
    )
    assert r.status_code == 200, r.text

    # Agora chega um card NOVO sem ordem manual, mais urgente.
    urgente = await _fb(session, org, risco, "urgente", type="churn", sentiment="negativo")
    await session.commit()

    ids = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    # Novo (sem ordem) por urgência no TOPO; o manual ('velho') abaixo.
    assert ids == [str(urgente.id), str(velho.id)]


# --- fallback: coluna sem card_order = urgência -------------------------------


@pytest.mark.asyncio
async def test_fallback_sem_card_order_usa_urgencia(client, org, session):
    """Coluna sem ordem manual salva = ordenação por urgência (comportamento atual)."""
    risco = await _contact(
        session, org, "5531900000001", "Risco",
        profile_data={"partner": {"profile": "ativo_em_risco", "subscription": {"planType": "anual"}}},
    )
    feliz = await _contact(session, org, "5531900000002", "Feliz")
    urgente = await _fb(session, org, risco, "urgente", type="churn", sentiment="negativo")
    calmo = await _fb(session, org, feliz, "calmo", type="elogio", sentiment="positivo")
    await session.commit()
    bid = await _board_action_status(client)

    # Nunca mexemos na ordem -> settings sem 'board_card_order'.
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    assert "board_card_order" not in (o.settings or {})

    ids = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert ids == [str(urgente.id), str(calmo.id)]  # urgência desc


# --- retrocompat: position=None não altera ordem ------------------------------


@pytest.mark.asyncio
async def test_position_none_nao_altera_ordem(client, org, session):
    """board-move SEM position (payload antigo) muda o status mas NÃO grava ordem manual."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    fb = await _fb(session, org, ana, "x", status="a_abordar", type="bug")
    await session.commit()

    r = await client.post(
        f"/api/feedbacks/{fb.id}/board-move",
        json={"campo": "action_status", "valor": "em_acompanhamento"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["action_status"] == "em_acompanhamento"

    f = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert f.action_status == "em_acompanhamento"
    # Não criou board_card_order (retrocompat intacta).
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    assert "board_card_order" not in (o.settings or {})


# --- isolamento por org -------------------------------------------------------


@pytest.mark.asyncio
async def test_isolamento_por_org(client, org, session):
    """A ordem manual de uma org não vaza para outra: cada org tem seu próprio mapa."""
    # Org A (a fixture `org`) recebe uma ordem manual.
    ana = await _contact(session, org, "5531900000001", "Ana")
    a1 = await _fb(session, org, ana, "a1")
    a2 = await _fb(session, org, ana, "a2")

    # Org B, isolada.
    org_b = Organization(slug="outra", name="Outra", settings={})
    session.add(org_b)
    await session.flush()
    bob = await _contact(session, org_b, "5531900000099", "Bob")
    b1 = await _fb(session, org_b, bob, "b1")
    await session.commit()

    # Ordena em A: a2, a1.
    for pos, fb in [(0, a2), (1, a1)]:
        await client.post(
            f"/api/feedbacks/{fb.id}/board-move",
            json={"campo": "action_status", "valor": "a_abordar", "position": pos},
        )

    oa = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    ob = (await session.execute(select(Organization).where(Organization.id == org_b.id))).scalar_one()
    assert oa.settings["board_card_order"]["a_abordar"] == [str(a2.id), str(a1.id)]
    # Org B nunca foi tocada: sem mapa, e seu card não aparece na ordem de A.
    assert "board_card_order" not in (ob.settings or {})
    assert str(b1.id) not in oa.settings["board_card_order"]["a_abordar"]
