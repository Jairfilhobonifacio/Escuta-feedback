"""Testes dos BOARDS dinâmicos — /api/boards CRUD, items por coluna e board-move.

Mesma infra de test_campanha.py / test_monitoring_api.py: app real + SQLite
in-memory (override de get_session) + messaging fake. Nenhum teste toca
Supabase/WAHA/Groq. Tudo persiste em JSON existente (Organization.settings /
Contact.profile_data) — sem migration.
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
from app.models.cluster import FeedbackCluster  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
from app.models.playbook import CsTask  # noqa: E402
from app.models.survey import Message  # noqa: E402
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


# --- BOARDS: defaults + CRUD --------------------------------------------------


@pytest.mark.asyncio
async def test_boards_default_quando_vazio(client, org):
    """GET /api/boards sem boards salvos -> 7 defaults: Follow-up (o Trello simples que
    abre por padrão) + 2 de feedback (Triagem + Campanha win-back) + 2 de cliente
    (Win-back clientes + Cancelados por estado) + 2 do board universal (Tarefas + Roadmap)."""
    data = (await client.get("/api/boards")).json()
    assert isinstance(data, list) and len(data) == 7
    by_id = {b["id"]: b for b in data}
    assert {"default-followup", "default-triagem", "default-winback",
            "default-clientes-winback", "default-clientes-estado",
            "default-tarefas", "default-roadmap"} <= set(by_id)

    # Follow-up vem PRIMEIRO (é o board que abre por padrão em /board).
    assert data[0]["id"] == "default-followup"
    followup = by_id["default-followup"]
    assert followup["nome"] == "Follow-up"
    assert followup["entidade"] == "feedback" and followup["campo"] == "selo"
    assert [c["valor"] for c in followup["colunas"]] == [
        "contatado", "respondeu", "nao_respondeu"
    ]
    by_valor = {c["valor"]: c for c in followup["colunas"]}
    assert by_valor["contatado"]["nome"] == "Contatados"
    assert by_valor["respondeu"]["nome"] == "Respondidos"
    assert by_valor["nao_respondeu"]["nome"] == "Não responderam"

    triagem = by_id["default-triagem"]
    assert triagem["entidade"] == "feedback"
    assert triagem["campo"] == "action_status"
    valores = [c["valor"] for c in triagem["colunas"]]
    assert valores == ["novo", "em_analise", "planejado", "resolvido", "descartado"]

    winback = by_id["default-winback"]
    assert winback["entidade"] == "feedback"
    assert winback["campo"] == "selo"
    assert [c["valor"] for c in winback["colunas"]] == [
        "contatado", "respondeu", "cortesia", "reativou"
    ]


@pytest.mark.asyncio
async def test_boards_default_cliente(client, org):
    """Os 2 defaults de CLIENTE: Win-back (clientes) por selo + Cancelados por estado."""
    data = (await client.get("/api/boards")).json()
    by_id = {b["id"]: b for b in data}

    wb = by_id["default-clientes-winback"]
    assert wb["nome"] == "Win-back (clientes)"
    assert wb["entidade"] == "cliente" and wb["campo"] == "selo"
    assert [c["valor"] for c in wb["colunas"]] == [
        "contatado", "respondeu", "cortesia", "reativou"
    ]

    est = by_id["default-clientes-estado"]
    assert est["nome"] == "Cancelados por estado"
    assert est["entidade"] == "cliente" and est["campo"] == "estado"
    assert [c["valor"] for c in est["colunas"]] == [
        "cancelled", "paid_without_access", "active_paying"
    ]
    by_valor = {c["valor"]: c for c in est["colunas"]}
    assert by_valor["cancelled"]["nome"] == "Cancelou"
    assert by_valor["paid_without_access"]["nome"] == "Pagou sem acesso"
    assert by_valor["active_paying"]["nome"] == "Ativo"


@pytest.mark.asyncio
async def test_boards_crud_completo(client, org, session):
    """POST cria (id gerado); GET lista; PATCH edita nome+colunas; DELETE remove."""
    # POST: cria um board por action_status.
    body = {
        "nome": "Meu Funil",
        "campo": "action_status",
        "colunas": [
            {"nome": "A fazer", "valor": "novo", "cor": "#6366f1"},
            {"nome": "Feito", "valor": "resolvido"},
        ],
    }
    r = await client.post("/api/boards", json=body)
    assert r.status_code == 201, r.text
    board = r.json()
    bid = board["id"]
    assert bid and board["nome"] == "Meu Funil" and board["campo"] == "action_status"
    assert len(board["colunas"]) == 2
    # cor default aplicada na coluna sem cor.
    feito = next(c for c in board["colunas"] if c["valor"] == "resolvido")
    assert feito["cor"] == "#6366f1"

    # GET lista os 6 defaults + o board criado (criar NÃO esconde os defaults).
    lista = (await client.get("/api/boards")).json()
    ids = [b["id"] for b in lista]
    assert bid in ids
    assert {"default-triagem", "default-winback",
            "default-clientes-winback", "default-clientes-estado",
            "default-tarefas", "default-roadmap"} <= set(ids)
    assert ids[-1] == bid  # custom vem depois dos defaults

    # Persistiu em Organization.settings["boards"] (sem migration).
    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    assert [b["id"] for b in o.settings["boards"]] == [bid]

    # PATCH: muda nome e colunas.
    r = await client.patch(
        f"/api/boards/{bid}",
        json={"nome": "Funil Renomeado", "colunas": [{"nome": "Tudo", "valor": "novo"}]},
    )
    assert r.status_code == 200, r.text
    patched = r.json()
    assert patched["nome"] == "Funil Renomeado"
    assert [c["valor"] for c in patched["colunas"]] == ["novo"]

    # PATCH parcial: só o nome, colunas intactas.
    r = await client.patch(f"/api/boards/{bid}", json={"nome": "So Nome"})
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == "So Nome"
    assert [c["valor"] for c in r.json()["colunas"]] == ["novo"]

    # DELETE: remove; lista volta aos defaults (board era o último).
    r = await client.delete(f"/api/boards/{bid}")
    assert r.status_code == 200, r.text
    assert r.json()["removido"] is True
    lista = (await client.get("/api/boards")).json()
    assert {b["id"] for b in lista} == {
        "default-followup",
        "default-triagem", "default-winback",
        "default-clientes-winback", "default-clientes-estado",
        "default-tarefas", "default-roadmap",
    }


@pytest.mark.asyncio
async def test_boards_post_campo_invalido_422(client, org):
    r = await client.post("/api/boards", json={"nome": "X", "campo": "qualquer", "colunas": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_boards_post_cliente_ok(client, org, session):
    """POST entidade=cliente com campo válido (estado) cria e persiste com a entidade."""
    body = {
        "nome": "Por estado", "entidade": "cliente", "campo": "estado",
        "colunas": [{"nome": "Cancelou", "valor": "cancelled"}],
    }
    r = await client.post("/api/boards", json=body)
    assert r.status_code == 201, r.text
    board = r.json()
    assert board["entidade"] == "cliente" and board["campo"] == "estado"

    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    saved = next(b for b in o.settings["boards"] if b["id"] == board["id"])
    assert saved["entidade"] == "cliente" and saved["campo"] == "estado"


@pytest.mark.asyncio
async def test_boards_post_cliente_campo_incompativel_422(client, org):
    """POST entidade=cliente com campo='action_status' (só de feedback) -> 422."""
    r = await client.post(
        "/api/boards",
        json={"nome": "X", "entidade": "cliente", "campo": "action_status", "colunas": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_boards_post_feedback_campo_de_cliente_422(client, org):
    """POST entidade=feedback (default) com campo='estado' (só de cliente) -> 422."""
    r = await client.post("/api/boards", json={"nome": "X", "campo": "estado", "colunas": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_boards_post_entidade_invalida_422(client, org):
    r = await client.post(
        "/api/boards", json={"nome": "X", "entidade": "alien", "campo": "selo", "colunas": []}
    )
    assert r.status_code == 422


# --- FASE C: board universal (tarefa + melhoria) — defaults + POST -------------


@pytest.mark.asyncio
async def test_boards_default_tarefa_e_melhoria(client, org):
    """Os 2 defaults do board universal: Tarefas (CS) por status + Roadmap por status."""
    data = (await client.get("/api/boards")).json()
    by_id = {b["id"]: b for b in data}

    tarefas = by_id["default-tarefas"]
    assert tarefas["nome"] == "Tarefas (CS)"
    assert tarefas["entidade"] == "tarefa" and tarefas["campo"] == "status"
    assert [c["valor"] for c in tarefas["colunas"]] == [
        "aberta", "em_andamento", "concluida", "adiada"
    ]

    roadmap = by_id["default-roadmap"]
    assert roadmap["nome"] == "Roadmap"
    assert roadmap["entidade"] == "melhoria" and roadmap["campo"] == "status"
    assert [c["valor"] for c in roadmap["colunas"]] == [
        "ideia", "planejada", "em_andamento", "entregue", "descartada"
    ]


@pytest.mark.asyncio
async def test_boards_post_tarefa_ok(client, org, session):
    """POST entidade=tarefa com campo válido (status) cria e persiste com a entidade."""
    body = {
        "nome": "Minhas tarefas", "entidade": "tarefa", "campo": "status",
        "colunas": [{"nome": "Aberta", "valor": "aberta"}],
    }
    r = await client.post("/api/boards", json=body)
    assert r.status_code == 201, r.text
    board = r.json()
    assert board["entidade"] == "tarefa" and board["campo"] == "status"

    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    saved = next(b for b in o.settings["boards"] if b["id"] == board["id"])
    assert saved["entidade"] == "tarefa" and saved["campo"] == "status"


@pytest.mark.asyncio
async def test_boards_post_melhoria_ok(client, org, session):
    """POST entidade=melhoria com campo válido (status) cria e persiste com a entidade."""
    body = {
        "nome": "Meu roadmap", "entidade": "melhoria", "campo": "status",
        "colunas": [{"nome": "Ideia", "valor": "ideia"}],
    }
    r = await client.post("/api/boards", json=body)
    assert r.status_code == 201, r.text
    board = r.json()
    assert board["entidade"] == "melhoria" and board["campo"] == "status"

    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    saved = next(b for b in o.settings["boards"] if b["id"] == board["id"])
    assert saved["entidade"] == "melhoria" and saved["campo"] == "status"


@pytest.mark.asyncio
async def test_boards_post_tarefa_campo_invalido_422(client, org):
    """POST entidade=tarefa com campo='action_status' (de feedback, não de tarefa) -> 422."""
    r = await client.post(
        "/api/boards",
        json={"nome": "X", "entidade": "tarefa", "campo": "action_status", "colunas": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_boards_post_melhoria_campo_invalido_422(client, org):
    """POST entidade=melhoria com campo='selo' (não é campo de melhoria) -> 422."""
    r = await client.post(
        "/api/boards",
        json={"nome": "X", "entidade": "melhoria", "campo": "selo", "colunas": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_board_patch_default_materializa(client, org, session):
    """PATCH num board DEFAULT o materializa nos settings com o id default."""
    r = await client.patch("/api/boards/default-triagem", json={"nome": "Triagem Pro"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "default-triagem" and r.json()["nome"] == "Triagem Pro"

    o = (await session.execute(select(Organization).where(Organization.id == org.id))).scalar_one()
    ids = [b["id"] for b in o.settings["boards"]]
    assert "default-triagem" in ids


@pytest.mark.asyncio
async def test_board_patch_inexistente_404(client, org):
    r = await client.patch(f"/api/boards/{uuid.uuid4().hex}", json={"nome": "X"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_boards_editar_default_nao_esconde_os_outros(client, org):
    """Regressão: materializar/editar UM default (PATCH) não pode sumir com os outros 3
    da listagem. Antes, GET devolvia só os persistidos -> selector ficava com 1 board."""
    await client.patch("/api/boards/default-triagem", json={"nome": "Triagem Pro"})
    lista = (await client.get("/api/boards")).json()
    by_id = {b["id"]: b for b in lista}
    # Os 4 defaults continuam visíveis; o editado mostra o nome novo.
    assert {"default-triagem", "default-winback",
            "default-clientes-winback", "default-clientes-estado"} <= set(by_id)
    assert by_id["default-triagem"]["nome"] == "Triagem Pro"


@pytest.mark.asyncio
async def test_boards_delete_default_tombstone_e_ressuscita(client, org):
    """DELETE de um default o remove da listagem (tombstone); editar o mesmo id depois
    o ressuscita."""
    # Default não materializado: DELETE registra tombstone e some da listagem.
    r = await client.delete("/api/boards/default-winback")
    assert r.status_code == 200 and r.json()["removido"] is True
    ids = {b["id"] for b in (await client.get("/api/boards")).json()}
    assert "default-winback" not in ids
    assert {"default-triagem", "default-clientes-winback", "default-clientes-estado",
            "default-tarefas", "default-roadmap"} <= ids
    # /items do default deletado -> 404 (não é mais encontrável).
    assert (await client.get("/api/boards/default-winback/items")).status_code == 404

    # Re-editar o default ressuscita-o (limpa o tombstone).
    r = await client.patch("/api/boards/default-winback", json={"nome": "Win-back de volta"})
    assert r.status_code == 200
    ids = {b["id"] for b in (await client.get("/api/boards")).json()}
    assert "default-winback" in ids


# --- BOARDS: items por coluna -------------------------------------------------


@pytest.mark.asyncio
async def test_board_items_por_action_status(client, org, session):
    """GET /api/boards/{id}/items (campo=action_status) agrupa feedbacks por status,
    com count total e items ordenados por urgência."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    bob = await _contact(session, org, "5531900000002", "Bob")
    session.add_all([
        # 2 'novo' (um churn negativo = mais urgente)
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
            external_id="n1", text="cancelei", sentiment="negativo", action_status="novo",
            occurred_at=_dt(2026, 6, 1),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=bob.id, source="bizzu_app", type="elogio",
            external_id="n2", text="legal", sentiment="positivo", action_status="novo",
            occurred_at=_dt(2026, 6, 2),
        ),
        # 1 'resolvido'
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
            external_id="r1", text="corrigido", action_status="resolvido",
            occurred_at=_dt(2026, 6, 3),
        ),
    ])
    await session.commit()

    # Cria um board action_status com 2 colunas (novo, resolvido).
    r = await client.post("/api/boards", json={
        "nome": "Ops", "campo": "action_status",
        "colunas": [{"nome": "Novo", "valor": "novo"}, {"nome": "Resolvido", "valor": "resolvido"}],
    })
    bid = r.json()["id"]

    data = (await client.get(f"/api/boards/{bid}/items")).json()
    assert data["campo"] == "action_status"
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["novo"]["count"] == 2
    assert cols["resolvido"]["count"] == 1
    # 'novo' ordenado por urgência: o churn negativo (Ana) vem antes do elogio (Bob).
    novos = cols["novo"]["items"]
    assert novos[0]["contato_nome"] == "Ana"
    # Cada item traz selos (camada win-back) — vazio aqui.
    assert novos[0]["selos"] == []


@pytest.mark.asyncio
async def test_board_items_por_selo(client, org, session):
    """GET items (campo=selo) agrupa os feedbacks de contatos com o selo da coluna."""
    # Ana tem selo 'contatado'; Bob tem 'respondeu'; Cida sem selo.
    ana = await _contact(session, org, "5531900000001", "Ana", profile_data={"selos": ["contatado"]})
    bob = await _contact(session, org, "5531900000002", "Bob", profile_data={"selos": ["respondeu"]})
    cida = await _contact(session, org, "5531900000003", "Cida")
    session.add_all([
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
            external_id="a1", text="cancelei", action_status="novo", occurred_at=_dt(2026, 6, 1),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=bob.id, source="bizzu_app", type="nps",
            external_id="b1", text="ok", action_status="novo", occurred_at=_dt(2026, 6, 2),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=cida.id, source="bizzu_app", type="outro",
            external_id="c1", text="nada", action_status="novo", occurred_at=_dt(2026, 6, 3),
        ),
    ])
    await session.commit()

    # Usa o board default winback (campo=selo) — colunas contatado/respondeu/cortesia/reativou.
    data = (await client.get("/api/boards/default-winback/items")).json()
    assert data["campo"] == "selo"
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["contatado"]["count"] == 1  # só Ana
    assert cols["respondeu"]["count"] == 1  # só Bob
    assert cols["cortesia"]["count"] == 0
    # O feedback da Ana na coluna 'contatado' carrega o selo do contato.
    assert cols["contatado"]["items"][0]["contato_nome"] == "Ana"
    assert "contatado" in cols["contatado"]["items"][0]["selos"]


@pytest.mark.asyncio
async def test_board_items_404(client, org):
    r = await client.get(f"/api/boards/{uuid.uuid4().hex}/items")
    assert r.status_code == 404


# --- BOARD MOVE ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_board_move_action_status(client, org, session):
    """POST /api/feedbacks/{id}/board-move campo=action_status muda o status."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
        external_id="m1", text="quebrou", action_status="novo", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.post(
        f"/api/feedbacks/{fb.id}/board-move", json={"campo": "action_status", "valor": "em_analise"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["action_status"] == "em_analise"

    f = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert f.action_status == "em_analise"


@pytest.mark.asyncio
async def test_board_move_action_status_invalido_422(client, org, session):
    ana = await _contact(session, org, "5531900000001", "Ana")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
        external_id="m2", text="x", action_status="novo", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.post(
        f"/api/feedbacks/{fb.id}/board-move", json={"campo": "action_status", "valor": "voando"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_board_move_selo_aplica_no_contato(client, org, session):
    """POST board-move campo=selo aplica o selo ao CONTATO (idempotente) + cria no catálogo."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        external_id="s1", text="cancelei", action_status="novo", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.post(
        f"/api/feedbacks/{fb.id}/board-move", json={"campo": "selo", "valor": "contatado"}
    )
    assert r.status_code == 200, r.text
    assert "contatado" in r.json()["selos"]

    # Aplicou ao contato (profile_data["selos"]).
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["selos"] == ["contatado"]

    # Criou no catálogo de selos da org (reuso da lógica do campanha.py).
    cat = (await client.get("/api/selos")).json()
    assert any(it["nome"] == "contatado" for it in cat["catalogo"])
    assert cat["uso"]["contatado"] == 1

    # Idempotente: re-mover o mesmo selo não duplica.
    await client.post(
        f"/api/feedbacks/{fb.id}/board-move", json={"campo": "selo", "valor": "contatado"}
    )
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["selos"] == ["contatado"]


@pytest.mark.asyncio
async def test_board_move_selo_followup_single_membership(client, org, session):
    """Board Follow-up (Trello simples): os selos contatado/respondeu/nao_respondeu são
    MUTUAMENTE EXCLUSIVOS — aplicar um remove os outros do contato (card vive em UMA
    coluna). Selos fora do grupo (ex.: cortesia) convivem normalmente."""
    ana = await _contact(session, org, "5531900000009", "Ana")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        external_id="sm1", text="cancelei", action_status="novo", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    base = f"/api/feedbacks/{fb.id}/board-move"

    # Contatado -> só 'contatado'.
    await client.post(base, json={"campo": "selo", "valor": "contatado"})
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["selos"] == ["contatado"]

    # Um selo FORA do grupo coexiste (campanha multi-coluna).
    await client.post(base, json={"campo": "selo", "valor": "cortesia"})
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert set(c.profile_data["selos"]) == {"contatado", "cortesia"}

    # Mover para 'respondeu' tira 'contatado' (exclusivo) mas mantém 'cortesia'.
    r = await client.post(base, json={"campo": "selo", "valor": "respondeu"})
    assert r.status_code == 200, r.text
    assert "respondeu" in r.json()["selos"] and "contatado" not in r.json()["selos"]
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert set(c.profile_data["selos"]) == {"respondeu", "cortesia"}

    # Mover para 'nao_respondeu' tira 'respondeu'.
    await client.post(base, json={"campo": "selo", "valor": "nao_respondeu"})
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert set(c.profile_data["selos"]) == {"nao_respondeu", "cortesia"}


@pytest.mark.asyncio
async def test_board_move_feedback_inexistente_404(client, org):
    r = await client.post(
        f"/api/feedbacks/{uuid.uuid4()}/board-move", json={"campo": "action_status", "valor": "novo"}
    )
    assert r.status_code == 404


# --- BOARDS de CLIENTE: items por selo/estado/perfil --------------------------


def _partner(state=None, profile=None, nps=None):
    """Monta um snapshot partner mínimo em profile_data (espelha a API de Clientes)."""
    p: dict = {}
    if state is not None:
        p.setdefault("subscription", {})["state"] = state
    if profile is not None:
        p["profile"] = profile
    if nps is not None:
        p["nps"] = {"score": nps}
    return {"partner": p}


@pytest.mark.asyncio
async def test_board_items_cliente_por_selo(client, org, session):
    """GET items de board cliente campo=selo agrupa CONTATOS pelo selo aplicado.

    O card é de CLIENTE (id/nome/whatsapp/tem_whatsapp/perfil/estado/health/
    health_band/selos), não de feedback."""
    await _contact(session, org, "5531900000001", "Ana", profile_data={"selos": ["contatado"]})
    await _contact(session, org, "5531900000002", "Bob", profile_data={"selos": ["respondeu"]})
    # Cida sem WhatsApp (placeholder 'nowa-') também com 'contatado'.
    await _contact(session, org, "nowa-9", "Cida", profile_data={"selos": ["contatado"]})
    # Edu com telefone FIXO (DDD+8) também com 'contatado' => sem WhatsApp.
    await _contact(session, org, "553192973323", "Edu", profile_data={"selos": ["contatado"]})
    await session.commit()

    data = (await client.get("/api/boards/default-clientes-winback/items")).json()
    assert data["entidade"] == "cliente" and data["campo"] == "selo"
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["contatado"]["count"] == 3  # Ana + Cida + Edu
    assert cols["respondeu"]["count"] == 1  # Bob
    assert cols["cortesia"]["count"] == 0

    card = next(it for it in cols["contatado"]["items"] if it["nome"] == "Ana")
    # Card de CLIENTE: chaves esperadas + tipos.
    assert set(card) >= {
        "id", "nome", "whatsapp", "tem_whatsapp", "perfil", "estado",
        "health", "health_band", "selos",
    }
    assert card["tem_whatsapp"] is True and "contatado" in card["selos"]
    cida = next(it for it in cols["contatado"]["items"] if it["nome"] == "Cida")
    assert cida["tem_whatsapp"] is False  # phone 'nowa-...' => sem WhatsApp
    edu = next(it for it in cols["contatado"]["items"] if it["nome"] == "Edu")
    assert edu["tem_whatsapp"] is False  # phone FIXO (DDD+8 díg) => sem WhatsApp


@pytest.mark.asyncio
async def test_board_items_cliente_por_estado(client, org, session):
    """GET items de board cliente campo=estado agrupa pelo subscription.state do snapshot."""
    await _contact(session, org, "5531900000001", "Ana",
                   profile_data=_partner(state="cancelled"))
    await _contact(session, org, "5531900000002", "Bob",
                   profile_data=_partner(state="active_paying"))
    await _contact(session, org, "5531900000003", "Cida",
                   profile_data=_partner(state="paid_without_access"))
    await _contact(session, org, "5531900000004", "Dida")  # sem snapshot -> nenhuma coluna
    await session.commit()

    data = (await client.get("/api/boards/default-clientes-estado/items")).json()
    assert data["entidade"] == "cliente" and data["campo"] == "estado"
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["cancelled"]["count"] == 1
    assert cols["active_paying"]["count"] == 1
    assert cols["paid_without_access"]["count"] == 1
    assert cols["cancelled"]["items"][0]["nome"] == "Ana"
    assert cols["cancelled"]["items"][0]["estado"] == "cancelled"


@pytest.mark.asyncio
async def test_board_items_cliente_por_perfil(client, org, session):
    """GET items de board cliente campo=perfil: match exato + startswith para 'churn'."""
    await _contact(session, org, "5531900000001", "Ana",
                   profile_data=_partner(profile="churn_rapido"))
    await _contact(session, org, "5531900000002", "Bob",
                   profile_data=_partner(profile="churn_pos_uso"))
    await _contact(session, org, "5531900000003", "Cida",
                   profile_data=_partner(profile="ativo_promotor"))
    await session.commit()

    # Board cliente por perfil: coluna 'churn' (prefixo) + 'ativo_promotor' (exato).
    r = await client.post("/api/boards", json={
        "nome": "Por perfil", "entidade": "cliente", "campo": "perfil",
        "colunas": [
            {"nome": "Churn", "valor": "churn"},
            {"nome": "Promotor", "valor": "ativo_promotor"},
        ],
    })
    bid = r.json()["id"]

    data = (await client.get(f"/api/boards/{bid}/items")).json()
    assert data["entidade"] == "cliente" and data["campo"] == "perfil"
    cols = {c["valor"]: c for c in data["colunas"]}
    # 'churn' casa por prefixo: Ana (churn_rapido) + Bob (churn_pos_uso).
    assert cols["churn"]["count"] == 2
    assert {it["nome"] for it in cols["churn"]["items"]} == {"Ana", "Bob"}
    # 'ativo_promotor' casa exato: só Cida.
    assert cols["ativo_promotor"]["count"] == 1
    assert cols["ativo_promotor"]["items"][0]["nome"] == "Cida"


@pytest.mark.asyncio
async def test_board_items_cliente_ordena_por_health_asc(client, org, session):
    """items de board cliente vêm ordenados por health ASC (pior cliente primeiro)."""
    # Saudável (NPS promotor + ativo) vs. em risco (NPS detrator + cancelado).
    await _contact(session, org, "5531900000001", "Saudavel",
                   profile_data={"selos": ["contatado"],
                                 **_partner(state="active_paying", profile="ativo_promotor", nps=10)})
    await _contact(session, org, "5531900000002", "Risco",
                   profile_data={"selos": ["contatado"],
                                 **_partner(state="cancelled", profile="churn_rapido", nps=2)})
    await session.commit()

    data = (await client.get("/api/boards/default-clientes-winback/items")).json()
    contatado = {c["valor"]: c for c in data["colunas"]}["contatado"]
    nomes = [it["nome"] for it in contatado["items"]]
    assert nomes[0] == "Risco" and nomes[-1] == "Saudavel"
    assert contatado["items"][0]["health"] <= contatado["items"][-1]["health"]


# --- BOARD MOVE de CLIENTE ----------------------------------------------------


@pytest.mark.asyncio
async def test_contact_board_move_selo_aplica(client, org, session):
    """POST /api/contacts/{id}/board-move campo=selo aplica o selo ao contato (idempotente)."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    await session.commit()

    r = await client.post(
        f"/api/contacts/{ana.id}/board-move", json={"campo": "selo", "valor": "contatado"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(ana.id)
    assert "contatado" in body["selos"]

    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["selos"] == ["contatado"]

    # Criou no catálogo de selos da org (reuso da lógica do campanha.py).
    cat = (await client.get("/api/selos")).json()
    assert any(it["nome"] == "contatado" for it in cat["catalogo"])

    # Idempotente: re-mover o mesmo selo não duplica.
    await client.post(
        f"/api/contacts/{ana.id}/board-move", json={"campo": "selo", "valor": "contatado"}
    )
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["selos"] == ["contatado"]


@pytest.mark.asyncio
async def test_contact_board_move_estado_recusa_409(client, org, session):
    """campo=estado é read-only (vem da API de Clientes) -> 409 e não altera o contato."""
    ana = await _contact(session, org, "5531900000001", "Ana",
                         profile_data=_partner(state="active_paying"))
    await session.commit()

    r = await client.post(
        f"/api/contacts/{ana.id}/board-move", json={"campo": "estado", "valor": "cancelled"}
    )
    assert r.status_code == 409
    assert "API" in r.json()["detail"]

    # Não mexeu no snapshot.
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["partner"]["subscription"]["state"] == "active_paying"


@pytest.mark.asyncio
async def test_contact_board_move_perfil_recusa_409(client, org, session):
    """campo=perfil é read-only -> 409."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    await session.commit()
    r = await client.post(
        f"/api/contacts/{ana.id}/board-move", json={"campo": "perfil", "valor": "churn_rapido"}
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_contact_board_move_campo_invalido_422(client, org, session):
    """campo fora de {selo, estado, perfil} -> 422."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    await session.commit()
    r = await client.post(
        f"/api/contacts/{ana.id}/board-move", json={"campo": "action_status", "valor": "novo"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_contact_board_move_inexistente_404(client, org):
    r = await client.post(
        f"/api/contacts/{uuid.uuid4()}/board-move", json={"campo": "selo", "valor": "contatado"}
    )
    assert r.status_code == 404


# --- E) status de campanha no inbox (GET /api/feedbacks ?selo + selos no item) -


@pytest.mark.asyncio
async def test_feedbacks_inclui_selos_e_filtra_por_selo(client, org, session):
    """GET /api/feedbacks traz `selos` do contato em cada item e aceita ?selo=<nome>."""
    ana = await _contact(session, org, "5531900000001", "Ana", profile_data={"selos": ["contatado"]})
    bob = await _contact(session, org, "5531900000002", "Bob")
    session.add_all([
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
            external_id="f1", text="cancelei", action_status="novo", occurred_at=_dt(2026, 6, 1),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=bob.id, source="bizzu_app", type="nps",
            external_id="f2", text="ok", action_status="novo", occurred_at=_dt(2026, 6, 2),
        ),
    ])
    await session.commit()

    # Sem filtro: 2 itens; o da Ana carrega selos=["contatado"], o do Bob selos=[].
    data = (await client.get("/api/feedbacks")).json()
    assert data["total"] == 2
    by_name = {it["contato_nome"]: it for it in data["items"]}
    assert by_name["Ana"]["selos"] == ["contatado"]
    assert by_name["Bob"]["selos"] == []

    # Filtro ?selo=contatado: só o feedback da Ana.
    data = (await client.get("/api/feedbacks", params={"selo": "contatado"})).json()
    assert data["total"] == 1
    assert data["items"][0]["contato_nome"] == "Ana"

    # Filtro por selo inexistente: zero.
    data = (await client.get("/api/feedbacks", params={"selo": "nao_existe"})).json()
    assert data["total"] == 0


# --- FASE A: cards RICOS (board revela as conexões do card) --------------------


@pytest.mark.asyncio
async def test_card_feedback_revela_tarefa_melhoria_dor_conversa(client, org, session):
    """Card de FEEDBACK (board action_status) enriquece em LOTE: tem_tarefa+status,
    improvement_id+melhoria_titulo, dor_label, conversa_count, assignee, team_tag,
    abordado. Um feedback "pelado" (Bob) traz os defaults (sem tarefa/melhoria/dor)."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    bob = await _contact(session, org, "5531900000002", "Bob")

    melhoria = Improvement(organization_id=org.id, title="App mais rápido", status="planejada")
    dor = FeedbackCluster(organization_id=org.id, label="Lentidão no app")
    session.add_all([melhoria, dor])
    await session.flush()

    fb_ana = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
        external_id="rica1", text="travou", action_status="novo", occurred_at=_dt(2026, 6, 1),
        assignee="cs@bizzu", team_tag="produto", abordado=True,
        improvement_id=melhoria.id, cluster_id=dor.id,
    )
    fb_bob = FeedbackItem(
        organization_id=org.id, contact_id=bob.id, source="bizzu_app", type="elogio",
        external_id="rica2", text="curti", action_status="novo", occurred_at=_dt(2026, 6, 2),
    )
    session.add_all([fb_ana, fb_bob])
    await session.flush()

    # 2 tarefas vinculadas ao feedback da Ana: a mais recente ('em_andamento') vence.
    session.add_all([
        CsTask(
            organization_id=org.id, contact_id=ana.id, feedback_item_id=fb_ana.id,
            title="Abordar Ana (antiga)", status="concluida", created_at=_dt(2026, 6, 1),
        ),
        CsTask(
            organization_id=org.id, contact_id=ana.id, feedback_item_id=fb_ana.id,
            title="Abordar Ana (nova)", status="em_andamento", created_at=_dt(2026, 6, 5),
        ),
    ])
    # 3 mensagens trocadas com a Ana; Bob não tem nenhuma.
    session.add_all([
        Message(organization_id=org.id, contact_id=ana.id, direction="inbound", body="oi"),
        Message(organization_id=org.id, contact_id=ana.id, direction="outbound", body="ola"),
        Message(organization_id=org.id, contact_id=ana.id, direction="inbound", body="travou de novo"),
    ])
    await session.commit()

    r = await client.post("/api/boards", json={
        "nome": "Ops Ricas", "campo": "action_status",
        "colunas": [{"nome": "Novo", "valor": "novo"}],
    })
    bid = r.json()["id"]

    data = (await client.get(f"/api/boards/{bid}/items")).json()
    items = {it["contato_nome"]: it for it in data["colunas"][0]["items"]}

    card_ana = items["Ana"]
    # Chaves novas presentes (forma exata).
    assert set(card_ana) >= {
        "tem_tarefa", "tarefa_status", "improvement_id", "melhoria_titulo",
        "dor_label", "conversa_count", "assignee", "team_tag", "abordado",
    }
    assert card_ana["tem_tarefa"] is True
    assert card_ana["tarefa_status"] == "em_andamento"  # tarefa MAIS RECENTE
    assert card_ana["improvement_id"] == str(melhoria.id)
    assert card_ana["melhoria_titulo"] == "App mais rápido"
    assert card_ana["dor_label"] == "Lentidão no app"
    assert card_ana["conversa_count"] == 3
    assert card_ana["assignee"] == "cs@bizzu"
    assert card_ana["team_tag"] == "produto"
    assert card_ana["abordado"] is True

    # Feedback pelado: defaults coerentes.
    card_bob = items["Bob"]
    assert card_bob["tem_tarefa"] is False
    assert card_bob["tarefa_status"] is None
    assert card_bob["improvement_id"] is None
    assert card_bob["melhoria_titulo"] is None
    assert card_bob["dor_label"] is None
    assert card_bob["conversa_count"] == 0


@pytest.mark.asyncio
async def test_card_feedback_selo_tambem_enriquece(client, org, session):
    """O mesmo enriquecimento vale no board campo=selo (default-winback)."""
    ana = await _contact(session, org, "5531900000001", "Ana",
                         profile_data={"selos": ["contatado"]})
    dor = FeedbackCluster(organization_id=org.id, label="Preço alto")
    session.add(dor)
    await session.flush()

    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        external_id="sl1", text="caro", action_status="novo", occurred_at=_dt(2026, 6, 1),
        cluster_id=dor.id, team_tag="comercial",
    )
    session.add(fb)
    await session.flush()
    session.add_all([
        CsTask(
            organization_id=org.id, contact_id=ana.id, feedback_item_id=fb.id,
            title="Reter Ana", status="aberta", created_at=_dt(2026, 6, 2),
        ),
        Message(organization_id=org.id, contact_id=ana.id, direction="inbound", body="muito caro"),
    ])
    await session.commit()

    data = (await client.get("/api/boards/default-winback/items")).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    card = cols["contatado"]["items"][0]
    assert card["contato_nome"] == "Ana"
    assert card["tem_tarefa"] is True and card["tarefa_status"] == "aberta"
    assert card["dor_label"] == "Preço alto"
    assert card["conversa_count"] == 1
    assert card["team_tag"] == "comercial"


@pytest.mark.asyncio
async def test_card_cliente_revela_contagens(client, org, session):
    """Card de CLIENTE traz feedbacks_count, tarefas_abertas (status!='concluida') e
    conversa_count — todos calculados em LOTE."""
    ana = await _contact(session, org, "5531900000001", "Ana",
                         profile_data={"selos": ["contatado"]})
    bob = await _contact(session, org, "5531900000002", "Bob",
                         profile_data={"selos": ["contatado"]})

    session.add_all([
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
            external_id="cf1", text="x", action_status="novo", occurred_at=_dt(2026, 6, 1),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
            external_id="cf2", text="y", action_status="novo", occurred_at=_dt(2026, 6, 2),
        ),
    ])
    session.add_all([
        # Ana: 1 aberta + 1 em_andamento (contam) + 1 concluida (NÃO conta).
        CsTask(organization_id=org.id, contact_id=ana.id, title="t1", status="aberta"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="t2", status="em_andamento"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="t3", status="concluida"),
    ])
    session.add_all([
        Message(organization_id=org.id, contact_id=ana.id, direction="inbound", body="a"),
        Message(organization_id=org.id, contact_id=ana.id, direction="outbound", body="b"),
    ])
    await session.commit()

    data = (await client.get("/api/boards/default-clientes-winback/items")).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    by_name = {it["nome"]: it for it in cols["contatado"]["items"]}

    card_ana = by_name["Ana"]
    assert set(card_ana) >= {"feedbacks_count", "tarefas_abertas", "conversa_count"}
    assert card_ana["feedbacks_count"] == 2
    assert card_ana["tarefas_abertas"] == 2  # aberta + em_andamento (concluida fora)
    assert card_ana["conversa_count"] == 2

    # Bob sem nada: contagens zeradas.
    card_bob = by_name["Bob"]
    assert card_bob["feedbacks_count"] == 0
    assert card_bob["tarefas_abertas"] == 0
    assert card_bob["conversa_count"] == 0


# --- FASE C: items de board universal (tarefa + melhoria) ----------------------


@pytest.mark.asyncio
async def test_board_items_tarefa_agrupa_por_status(client, org, session):
    """GET items de board entidade=tarefa agrupa CsTask por status, com count total e
    card enxuto de TAREFA (id, titulo, status, priority, owner, contato_nome, due_at,
    feedback_id, feedback_preview). Ordena por prioridade (urgente primeiro)."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    bob = await _contact(session, org, "5531900000002", "Bob")
    await session.flush()

    # Feedback vinculado a uma tarefa (preview do trecho no card).
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        external_id="t-fb1", text="quero cancelar minha conta", action_status="novo",
        occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.flush()

    session.add_all([
        # 2 abertas: a 'urgente' (Ana, com feedback) vem antes da 'normal' (Bob).
        CsTask(
            organization_id=org.id, contact_id=bob.id, title="Ligar pro Bob",
            status="aberta", priority="normal", owner="cs@bizzu", due_at=_dt(2026, 6, 10),
        ),
        CsTask(
            organization_id=org.id, contact_id=ana.id, feedback_item_id=fb.id,
            title="Reter Ana", status="aberta", priority="urgente", owner="cs@bizzu",
            due_at=_dt(2026, 6, 5),
        ),
        # 1 concluída.
        CsTask(
            organization_id=org.id, contact_id=ana.id, title="Follow-up Ana",
            status="concluida", priority="normal",
        ),
    ])
    await session.commit()

    data = (await client.get("/api/boards/default-tarefas/items")).json()
    assert data["entidade"] == "tarefa" and data["campo"] == "status"
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["aberta"]["count"] == 2
    assert cols["concluida"]["count"] == 1
    assert cols["em_andamento"]["count"] == 0
    assert cols["adiada"]["count"] == 0

    # Ordenação por prioridade: 'urgente' (Reter Ana) antes de 'normal' (Ligar pro Bob).
    abertas = cols["aberta"]["items"]
    assert [it["titulo"] for it in abertas] == ["Reter Ana", "Ligar pro Bob"]

    # Forma exata do card de TAREFA.
    card = abertas[0]
    assert set(card) == {
        "id", "titulo", "status", "priority", "owner",
        "contato_id", "contato_nome", "due_at", "feedback_id", "feedback_preview",
    }
    assert card["titulo"] == "Reter Ana"
    assert card["status"] == "aberta" and card["priority"] == "urgente"
    assert card["owner"] == "cs@bizzu"
    assert card["contato_nome"] == "Ana"
    # due_at é o ISO do datetime persistido (SQLite descarta o tz no round-trip).
    assert card["due_at"].startswith("2026-06-05T12:00:00")
    assert card["feedback_id"] == str(fb.id)
    assert card["feedback_preview"] == "quero cancelar minha conta"

    # Tarefa sem feedback vinculado: feedback_id/preview nulos.
    bob_card = next(it for it in abertas if it["titulo"] == "Ligar pro Bob")
    assert bob_card["feedback_id"] is None and bob_card["feedback_preview"] is None


@pytest.mark.asyncio
async def test_board_items_melhoria_agrupa_por_status(client, org, session):
    """GET items de board entidade=melhoria agrupa Improvement por status, com count
    total e feedback_count correto (em LOTE). Card enxuto de MELHORIA; ordena por
    feedback_count desc dentro da coluna."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    await session.flush()

    # 2 melhorias 'planejada' (uma com 2 feedbacks, outra com 0) + 1 'entregue' (1 fb).
    pop = Improvement(
        organization_id=org.id, title="App mais rápido", status="planejada",
        effort="M", target_date=_dt(2026, 7, 1),
    )
    vazia = Improvement(organization_id=org.id, title="Tema escuro", status="planejada")
    entregue = Improvement(organization_id=org.id, title="Login Google", status="entregue")
    session.add_all([pop, vazia, entregue])
    await session.flush()

    session.add_all([
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
            external_id="m-fb1", text="lento", action_status="novo", occurred_at=_dt(2026, 6, 1),
            improvement_id=pop.id,
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
            external_id="m-fb2", text="trava", action_status="novo", occurred_at=_dt(2026, 6, 2),
            improvement_id=pop.id,
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="elogio",
            external_id="m-fb3", text="logei rapido", action_status="resolvido",
            occurred_at=_dt(2026, 6, 3), improvement_id=entregue.id,
        ),
    ])
    await session.commit()

    data = (await client.get("/api/boards/default-roadmap/items")).json()
    assert data["entidade"] == "melhoria" and data["campo"] == "status"
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["planejada"]["count"] == 2
    assert cols["entregue"]["count"] == 1
    assert cols["ideia"]["count"] == 0

    # Ordena por feedback_count desc: 'App mais rápido' (2) antes de 'Tema escuro' (0).
    planejadas = cols["planejada"]["items"]
    assert [it["titulo"] for it in planejadas] == ["App mais rápido", "Tema escuro"]
    assert planejadas[0]["feedback_count"] == 2
    assert planejadas[1]["feedback_count"] == 0

    # Forma exata do card de MELHORIA.
    card = planejadas[0]
    assert set(card) == {"id", "titulo", "status", "feedback_count", "effort", "target_date"}
    assert card["id"] == str(pop.id)
    assert card["titulo"] == "App mais rápido"
    assert card["status"] == "planejada"
    assert card["feedback_count"] == 2
    assert card["effort"] == "M"
    # target_date é o ISO do datetime persistido (SQLite descarta o tz no round-trip).
    assert card["target_date"].startswith("2026-07-01T12:00:00")

    # Coluna 'entregue': a melhoria com 1 feedback.
    assert cols["entregue"]["items"][0]["feedback_count"] == 1


# --- FASE E: filtros no board (items E counts coerentes) -----------------------


@pytest.mark.asyncio
async def test_board_feedback_filtrado_estado_whatsapp_team_tag(client, org, session):
    """(a) Board de FEEDBACK filtrado por estado/tem_whatsapp/team_tag reduz items E
    counts de cada coluna coerentemente (filtro aplicado ANTES do agrupamento)."""
    # Ana: cancelada, WhatsApp válido, team_tag='produto'  -> casa todos os 3 filtros.
    ana = await _contact(session, org, "5531900000001", "Ana",
                         profile_data=_partner(state="cancelled"))
    # Bob: ativo (estado != cancelled) -> cai fora pelo filtro estado.
    bob = await _contact(session, org, "5531900000002", "Bob",
                         profile_data=_partner(state="active_paying"))
    # Cida: cancelada mas FIXO (sem WhatsApp) -> cai fora pelo filtro tem_whatsapp.
    cida = await _contact(session, org, "553192973323", "Cida",
                          profile_data=_partner(state="cancelled"))
    await session.flush()

    session.add_all([
        # Ana 'novo' produto (casa) + Ana 'novo' comercial (cai pelo team_tag).
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
            external_id="fe1", text="cancelei", action_status="novo", team_tag="produto",
            occurred_at=_dt(2026, 6, 1),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
            external_id="fe2", text="bug", action_status="novo", team_tag="comercial",
            occurred_at=_dt(2026, 6, 2),
        ),
        # Bob 'novo' produto (cai pelo estado).
        FeedbackItem(
            organization_id=org.id, contact_id=bob.id, source="bizzu_app", type="nps",
            external_id="fe3", text="ok", action_status="novo", team_tag="produto",
            occurred_at=_dt(2026, 6, 3),
        ),
        # Cida 'resolvido' produto (cai pelo tem_whatsapp; e era outra coluna).
        FeedbackItem(
            organization_id=org.id, contact_id=cida.id, source="bizzu_app", type="bug",
            external_id="fe4", text="ok", action_status="resolvido", team_tag="produto",
            occurred_at=_dt(2026, 6, 4),
        ),
    ])
    await session.commit()

    r = await client.post("/api/boards", json={
        "nome": "Ops Filtro", "campo": "action_status",
        "colunas": [{"nome": "Novo", "valor": "novo"}, {"nome": "Resolvido", "valor": "resolvido"}],
    })
    bid = r.json()["id"]

    # SEM filtro: novo=3 (Ana x2, Bob), resolvido=1 (Cida).
    data = (await client.get(f"/api/boards/{bid}/items")).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["novo"]["count"] == 3
    assert cols["resolvido"]["count"] == 1

    # COM filtro estado=cancelled + tem_whatsapp=sim + team_tag=produto: só o fe1 da Ana.
    data = (await client.get(f"/api/boards/{bid}/items", params={
        "estado": "cancelled", "tem_whatsapp": "sim", "team_tag": "produto",
    })).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    # count E items batem (filtro antes do agrupamento).
    assert cols["novo"]["count"] == 1
    assert len(cols["novo"]["items"]) == 1
    assert cols["novo"]["items"][0]["contato_nome"] == "Ana"
    assert cols["novo"]["items"][0]["team_tag"] == "produto"
    # Resolvido zera: era da Cida (fixo, sem WhatsApp).
    assert cols["resolvido"]["count"] == 0
    assert cols["resolvido"]["items"] == []


@pytest.mark.asyncio
async def test_board_cliente_filtrado_health_band_e_estado(client, org, session):
    """(b) Board de CLIENTE filtrado por health_band/estado reduz items E counts
    coerentemente."""
    # Saudável + ativo (health 'healthy'); em risco + cancelado (health 'at_risk').
    await _contact(session, org, "5531900000001", "Saudavel",
                   profile_data={"selos": ["contatado"],
                                 **_partner(state="active_paying", profile="ativo_promotor", nps=10)})
    await _contact(session, org, "5531900000002", "Risco",
                   profile_data={"selos": ["contatado"],
                                 **_partner(state="cancelled", profile="churn_rapido", nps=2)})
    await session.commit()

    # SEM filtro: contatado=2.
    data = (await client.get("/api/boards/default-clientes-winback/items")).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["contatado"]["count"] == 2

    # Filtro health_band=at_risk: só "Risco".
    data = (await client.get("/api/boards/default-clientes-winback/items",
                             params={"health_band": "at_risk"})).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["contatado"]["count"] == 1
    assert len(cols["contatado"]["items"]) == 1
    assert cols["contatado"]["items"][0]["nome"] == "Risco"
    assert cols["contatado"]["items"][0]["health_band"] == "at_risk"

    # Filtro estado=active_paying: só "Saudavel".
    data = (await client.get("/api/boards/default-clientes-winback/items",
                             params={"estado": "active_paying"})).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    assert cols["contatado"]["count"] == 1
    assert cols["contatado"]["items"][0]["nome"] == "Saudavel"


@pytest.mark.asyncio
async def test_board_cliente_exclui_phone_de_grupo(client, org, session):
    """(c) Board de CLIENTE NÃO inclui um contato cujo phone é classe 'group' (JID
    '120363...'): saneamento da Fase F — não aparece em items nem no count."""
    # Lead 1:1 legítimo + um ID de GRUPO do WhatsApp (não é cliente).
    await _contact(session, org, "5531900000001", "Ana",
                   profile_data={"selos": ["contatado"]})
    await _contact(session, org, "120363001122334455", "Comunidade Bizzu",
                   profile_data={"selos": ["contatado"]})
    await session.commit()

    data = (await client.get("/api/boards/default-clientes-winback/items")).json()
    cols = {c["valor"]: c for c in data["colunas"]}
    # Só a Ana entra; o grupo é excluído do board (count E items).
    assert cols["contatado"]["count"] == 1
    nomes = {it["nome"] for it in cols["contatado"]["items"]}
    assert nomes == {"Ana"}
    assert "Comunidade Bizzu" not in nomes


@pytest.mark.asyncio
async def test_board_filtro_inaplicavel_e_ignorado_sem_erro(client, org, session):
    """(d) Filtro que não se aplica à entidade do board é ignorado, sem erro (no-op).

    'effort'/'priority' são de melhoria/tarefa; passados num board de FEEDBACK não
    filtram nada e não quebram (200, board inteiro)."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    session.add(FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="bug",
        external_id="ign1", text="x", action_status="novo", occurred_at=_dt(2026, 6, 1),
    ))
    await session.commit()

    r = await client.post("/api/boards", json={
        "nome": "Ops Ignora", "campo": "action_status",
        "colunas": [{"nome": "Novo", "valor": "novo"}],
    })
    bid = r.json()["id"]

    # effort/priority não se aplicam a feedback: ignorados, board inteiro (200, count=1).
    resp = await client.get(f"/api/boards/{bid}/items",
                            params={"effort": "M", "priority": "urgente"})
    assert resp.status_code == 200, resp.text
    cols = {c["valor"]: c for c in resp.json()["colunas"]}
    assert cols["novo"]["count"] == 1
    assert cols["novo"]["items"][0]["contato_nome"] == "Ana"
