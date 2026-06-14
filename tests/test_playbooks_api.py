"""API de Playbooks + fila de Tarefas (Fase 2) — /api/playbooks e /api/tarefas.

Mesma infra do test_monitoring_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA.
"""
from __future__ import annotations

import os
import sys
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
from app.models.playbook import CsTask, Playbook  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402

_PB_KEYS = {
    "id", "name", "description", "enabled", "trigger_type", "trigger_config",
    "action_type", "action_config", "created_at", "updated_at",
}
_TAREFA_KEYS = {
    "id", "contato_id", "contato_nome", "contato_whatsapp", "playbook_id", "playbook_nome",
    "title", "reason", "status", "priority", "owner", "due_at", "snoozed_until", "notes",
    "health", "health_band", "meta", "criada_em", "atualizada_em",
}


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
            c._fake = fake  # type: ignore[attr-defined]
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={"owner_phone": "5531999999999"})
    session.add(o)
    await session.commit()
    return o


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


# --- CRUD /api/playbooks -----------------------------------------------------


@pytest.mark.asyncio
async def test_playbooks_crud(client, org, session):
    # vazio
    assert (await client.get("/api/playbooks")).json() == []

    # criar
    r = await client.post("/api/playbooks", json={
        "name": "Detrator → tarefa",
        "trigger_type": "nps_detractor",
        "trigger_config": {"max_score": 6},
        "action_type": "create_task",
        "action_config": {"title": "Abordar {nome}", "priority": "alta", "sla_hours": 24, "owner": "cs"},
    })
    assert r.status_code == 201, r.text
    out = r.json()
    assert set(out.keys()) == _PB_KEYS
    assert out["name"] == "Detrator → tarefa"
    assert out["enabled"] is True
    assert out["trigger_config"] == {"max_score": 6}
    pid = out["id"]

    # listar
    lst = (await client.get("/api/playbooks")).json()
    assert len(lst) == 1 and lst[0]["id"] == pid

    # patch parcial: desliga + muda config
    r = await client.patch(f"/api/playbooks/{pid}", json={"enabled": False, "trigger_config": {"max_score": 4}})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    assert r.json()["trigger_config"] == {"max_score": 4}

    # delete
    r = await client.delete(f"/api/playbooks/{pid}")
    assert r.status_code == 204
    assert (await client.get("/api/playbooks")).json() == []


@pytest.mark.asyncio
async def test_playbook_nome_duplicado_409(client, org):
    body = {"name": "X", "trigger_type": "nps_detractor", "action_type": "create_task"}
    assert (await client.post("/api/playbooks", json=body)).status_code == 201
    r = await client.post("/api/playbooks", json=body)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_playbook_enum_invalido_422(client, org):
    # trigger_type inválido
    r = await client.post("/api/playbooks", json={
        "name": "ruim", "trigger_type": "nao_existe", "action_type": "create_task",
    })
    assert r.status_code == 422
    # action_type inválido
    r = await client.post("/api/playbooks", json={
        "name": "ruim2", "trigger_type": "nps_detractor", "action_type": "fazer_magica",
    })
    assert r.status_code == 422
    # priority inválida no action_config
    r = await client.post("/api/playbooks", json={
        "name": "ruim3", "trigger_type": "nps_detractor", "action_type": "create_task",
        "action_config": {"priority": "altíssima"},
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_playbook_patch_404(client, org):
    import uuid
    r = await client.patch(f"/api/playbooks/{uuid.uuid4()}", json={"enabled": False})
    assert r.status_code == 404


# --- POST /api/playbooks/run -------------------------------------------------


@pytest.mark.asyncio
async def test_run_dry_run_nao_grava(client, org, session):
    ana = Contact(
        organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True,
        profile_data={"partner": {"nps": {"score": 3}}},
    )
    session.add(ana)
    await session.commit()
    await client.post("/api/playbooks", json={
        "name": "PB", "trigger_type": "nps_detractor", "action_type": "create_task",
        "action_config": {"title": "Abordar {nome}", "sla_hours": 24},
    })

    r = await client.post("/api/playbooks/run", params={"dry_run": "true"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["dry_run"] is True
    assert rep["evaluated"] == 1
    assert len(rep["tasks_would_create"]) == 1
    assert rep["tasks_created"] == 0
    # nada na fila
    assert (await client.get("/api/tarefas")).json()["total"] == 0


@pytest.mark.asyncio
async def test_run_wet_run_cria_tarefa_na_fila(client, org, session):
    ana = Contact(
        organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True,
        profile_data={"partner": {"nps": {"score": 2}}},
    )
    session.add(ana)
    await session.commit()
    await client.post("/api/playbooks", json={
        "name": "PB", "trigger_type": "nps_detractor", "action_type": "create_task",
        "action_config": {"title": "Abordar {nome}", "priority": "alta", "sla_hours": 24},
    })

    r = await client.post("/api/playbooks/run", params={"dry_run": "false"})
    assert r.status_code == 200, r.text
    assert r.json()["tasks_created"] == 1

    fila = (await client.get("/api/tarefas")).json()
    assert fila["total"] == 1
    item = fila["items"][0]
    assert set(item.keys()) == _TAREFA_KEYS
    assert item["title"] == "Abordar Ana"
    assert item["priority"] == "alta"
    assert item["playbook_nome"] == "PB"
    assert item["contato_nome"] == "Ana"
    # health recomputado inline (detrator NPS 2 → score baixo)
    assert item["health"] is not None and item["health_band"] in ("at_risk", "watch", "healthy")


# --- /api/tarefas: criação manual, filtros, counts, sort ---------------------


@pytest.mark.asyncio
async def test_tarefa_manual_crud_e_health(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()

    r = await client.post("/api/tarefas", json={
        "contact_id": str(ana.id), "title": "Ligar pra Ana", "reason": "follow-up", "priority": "alta", "owner": "felipe",
    })
    assert r.status_code == 201, r.text
    out = r.json()
    assert set(out.keys()) == _TAREFA_KEYS
    assert out["title"] == "Ligar pra Ana"
    assert out["priority"] == "alta"
    assert out["owner"] == "felipe"
    assert out["playbook_id"] is None  # manual
    assert out["status"] == "aberta"
    assert out["contato_nome"] == "Ana"

    fila = (await client.get("/api/tarefas")).json()
    assert fila["total"] == 1
    assert fila["counts_by_status"] == {"aberta": 1, "em_andamento": 0, "concluida": 0, "adiada": 0}


@pytest.mark.asyncio
async def test_tarefa_manual_contato_inexistente_404(client, org):
    import uuid
    r = await client.post("/api/tarefas", json={"contact_id": str(uuid.uuid4()), "title": "x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tarefa_manual_priority_invalida_422(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()
    r = await client.post("/api/tarefas", json={"contact_id": str(ana.id), "title": "x", "priority": "epica"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tarefas_filtros_e_counts(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    bob = Contact(organization_id=org.id, phone="5531900000002", name="Bob", opt_in=True, profile_data={})
    session.add_all([ana, bob])
    await session.flush()
    session.add_all([
        CsTask(organization_id=org.id, contact_id=ana.id, title="A", status="aberta", priority="alta", owner="cs"),
        CsTask(organization_id=org.id, contact_id=bob.id, title="B", status="em_andamento", priority="normal", owner="cx"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="C", status="concluida", priority="baixa", owner="cs"),
    ])
    await session.commit()

    todos = (await client.get("/api/tarefas")).json()
    assert todos["total"] == 3
    assert todos["counts_by_status"] == {"aberta": 1, "em_andamento": 1, "concluida": 1, "adiada": 0}

    # filtro por status
    abertas = (await client.get("/api/tarefas", params={"status": "aberta"})).json()
    assert abertas["total"] == 1 and abertas["items"][0]["title"] == "A"

    # filtro por owner
    cs = (await client.get("/api/tarefas", params={"owner": "cs"})).json()
    assert cs["total"] == 2
    assert {i["title"] for i in cs["items"]} == {"A", "C"}

    # filtro por priority
    alta = (await client.get("/api/tarefas", params={"priority": "alta"})).json()
    assert alta["total"] == 1 and alta["items"][0]["title"] == "A"

    # filtro por contact_id
    da_ana = (await client.get("/api/tarefas", params={"contact_id": str(ana.id)})).json()
    assert da_ana["total"] == 2


@pytest.mark.asyncio
async def test_tarefas_sort_prioridade(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    session.add_all([
        CsTask(organization_id=org.id, contact_id=ana.id, title="baixa", status="aberta", priority="baixa"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="urgente", status="aberta", priority="urgente"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="normal", status="aberta", priority="normal"),
    ])
    await session.commit()

    data = (await client.get("/api/tarefas", params={"sort": "prioridade"})).json()
    assert [i["title"] for i in data["items"]] == ["urgente", "normal", "baixa"]


# --- PATCH /api/tarefas/{id} -------------------------------------------------


@pytest.mark.asyncio
async def test_patch_tarefa_concluida_grava_closed_at(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    t = CsTask(organization_id=org.id, contact_id=ana.id, title="A", status="aberta", priority="normal")
    session.add(t)
    await session.commit()

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "concluida"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "concluida"
    # closed_at gravado no banco
    row = (await session.execute(select(CsTask).where(CsTask.id == t.id))).scalar_one()
    assert row.closed_at is not None


@pytest.mark.asyncio
async def test_patch_tarefa_snooze_forca_adiada(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    t = CsTask(organization_id=org.id, contact_id=ana.id, title="A", status="aberta", priority="normal")
    session.add(t)
    await session.commit()

    until = _dt(2026, 7, 1).isoformat()
    r = await client.patch(f"/api/tarefas/{t.id}", json={"snoozed_until": until})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "adiada"  # snooze força adiada mesmo sem status no corpo
    assert out["snoozed_until"] is not None


@pytest.mark.asyncio
async def test_patch_tarefa_status_invalido_422(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    t = CsTask(organization_id=org.id, contact_id=ana.id, title="A", status="aberta", priority="normal")
    session.add(t)
    await session.commit()
    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "fechada_total"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_tarefa_404(client, org):
    import uuid
    r = await client.patch(f"/api/tarefas/{uuid.uuid4()}", json={"status": "concluida"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tarefa_de_outra_org_nao_aparece(client, org, session):
    """Isolamento multi-tenant: tarefa de outra org não vaza na fila."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    session.add(CsTask(organization_id=other.id, contact_id=None, title="alheia", status="aberta", priority="normal"))
    await session.commit()

    fila = (await client.get("/api/tarefas")).json()
    assert fila["total"] == 0
