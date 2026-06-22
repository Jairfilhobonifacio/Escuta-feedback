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


# --- snapshot ordem-total: card arrastado FICA onde caiu (sem salto) ----------


@pytest.mark.asyncio
async def test_reorder_primeiro_card_da_coluna_fica_onde_caiu(client, org, session):
    """Mover UM card numa coluna de cards NÃO-tocados deve deixá-lo onde caiu — não
    jogá-lo para o fim (regressão do salto otimista→servidor). Card de BAIXA urgência
    arrastado para o TOPO permanece no topo; a coluna inteira vira ordem manual.

    Com o backend antigo (insere só entre 'manuais', que ficam abaixo dos novos) o card
    iria para o FIM: [urgente, calmo]. O snapshot ordem-total mantém [calmo, urgente]."""
    risco = await _contact(
        session, org, "5531900000001", "Risco",
        profile_data={"partner": {"profile": "ativo_em_risco", "subscription": {"planType": "anual"}}},
    )
    feliz = await _contact(session, org, "5531900000002", "Feliz")
    urgente = await _fb(session, org, risco, "urgente", type="churn", sentiment="negativo")
    calmo = await _fb(session, org, feliz, "calmo", type="elogio", sentiment="positivo")
    await session.commit()
    bid = await _board_action_status(client)

    # Sanidade: sem ordem manual, urgência manda -> [urgente, calmo].
    ids0 = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert ids0 == [str(urgente.id), str(calmo.id)]

    # Arrasta o card de BAIXA urgência (calmo) para o TOPO (position 0).
    r = await client.post(
        f"/api/feedbacks/{calmo.id}/board-move",
        json={"campo": "action_status", "valor": "a_abordar", "position": 0},
    )
    assert r.status_code == 200, r.text

    ids = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert ids == [str(calmo.id), str(urgente.id)]  # FICA no topo (não salta pro fim)
    # A coluna inteira virou ordem manual (snapshot), não só o card tocado.
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    assert o.settings["board_card_order"]["a_abordar"] == [str(calmo.id), str(urgente.id)]


@pytest.mark.asyncio
async def test_reorder_move_um_card_no_meio_preserva_o_resto(client, org, session):
    """Numa coluna já ordenada manualmente, mover um único card para o meio reposiciona
    só ele e preserva os demais — a ordem do GET bate com o splice otimista do front."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    a = await _fb(session, org, ana, "a")
    b = await _fb(session, org, ana, "b")
    c = await _fb(session, org, ana, "c")
    d = await _fb(session, org, ana, "d")
    await session.commit()
    bid = await _board_action_status(client)

    # Estabelece a ordem [a, b, c, d] (cada move snapshota a coluna inteira).
    for pos, fb in [(0, a), (1, b), (2, c), (3, d)]:
        await client.post(
            f"/api/feedbacks/{fb.id}/board-move",
            json={"campo": "action_status", "valor": "a_abordar", "position": pos},
        )
    base = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert base == [str(a.id), str(b.id), str(c.id), str(d.id)]

    # Move 'd' para a position 1 (logo após 'a'): esperado [a, d, b, c].
    r = await client.post(
        f"/api/feedbacks/{d.id}/board-move",
        json={"campo": "action_status", "valor": "a_abordar", "position": 1},
    )
    assert r.status_code == 200, r.text
    ids = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert ids == [str(a.id), str(d.id), str(b.id), str(c.id)]


async def _coluna_abcd(client, org, session):
    """Coluna 'a_abordar' com 4 cards do mesmo contato ordenados manualmente [a,b,c,d]."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    fbs = {}
    for ext in ("a", "b", "c", "d"):
        fbs[ext] = await _fb(session, org, ana, ext)
    await session.commit()
    bid = await _board_action_status(client)
    for pos, ext in [(0, "a"), (1, "b"), (2, "c"), (3, "d")]:
        await client.post(
            f"/api/feedbacks/{fbs[ext].id}/board-move",
            json={"campo": "action_status", "valor": "a_abordar", "position": pos},
        )
    base = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert base == [str(fbs[e].id) for e in ("a", "b", "c", "d")]
    return bid, fbs


@pytest.mark.asyncio
async def test_reorder_move_para_frente_sem_off_by_one(client, org, session):
    """Mover um card para FRENTE (position > índice atual) na mesma coluna cai na posição
    VISUAL exata — `position` é o índice na lista COM o card, e o backend desliza -1 ao
    removê-lo, espelhando o splice otimista do front. 'a' (idx 0) p/ position 3 = [b,c,a,d]
    (com o backend cru, sem o ajuste, daria [b,c,d,a])."""
    bid, fbs = await _coluna_abcd(client, org, session)
    r = await client.post(
        f"/api/feedbacks/{fbs['a'].id}/board-move",
        json={"campo": "action_status", "valor": "a_abordar", "position": 3},
    )
    assert r.status_code == 200, r.text
    ids = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert ids == [str(fbs["b"].id), str(fbs["c"].id), str(fbs["a"].id), str(fbs["d"].id)]


@pytest.mark.asyncio
async def test_reorder_move_para_o_fim(client, org, session):
    """Arrastar um card NÃO-último para o FIM (position == len) o coloca por último — o
    slide-antes-do-clamp evita parar 1 antes do fim. 'b' (idx 1) p/ position 4 = [a,c,d,b]."""
    bid, fbs = await _coluna_abcd(client, org, session)
    r = await client.post(
        f"/api/feedbacks/{fbs['b'].id}/board-move",
        json={"campo": "action_status", "valor": "a_abordar", "position": 4},
    )
    assert r.status_code == 200, r.text
    ids = _ids_da_coluna((await client.get(f"/api/boards/{bid}/items")).json(), "a_abordar")
    assert ids == [str(fbs["a"].id), str(fbs["c"].id), str(fbs["d"].id), str(fbs["b"].id)]
