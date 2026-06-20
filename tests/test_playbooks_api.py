"""API de Playbooks + fila de Tarefas (Fase 2) — /api/playbooks e /api/tarefas.

Mesma infra do test_monitoring_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA.
"""
from __future__ import annotations

import dataclasses
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

import app.api.tasks as _tasks_mod  # noqa: E402
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
    "health", "health_band", "meta", "feedback_id", "feedback_preview", "criada_em", "atualizada_em",
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


@pytest.mark.asyncio
async def test_tarefas_filtro_status_isola_estados(client, org, session):
    """Filtro por status em SQL: só retorna tarefas no estado pedido (counts ignoram status)."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    session.add_all([
        CsTask(organization_id=org.id, contact_id=ana.id, title="A1", status="aberta", priority="normal"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="A2", status="aberta", priority="normal"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="EA", status="em_andamento", priority="normal"),
    ])
    await session.commit()

    em_and = (await client.get("/api/tarefas", params={"status": "em_andamento"})).json()
    assert em_and["total"] == 1
    assert {i["title"] for i in em_and["items"]} == {"EA"}
    # counts_by_status ignora o próprio filtro de status (abas no front).
    assert em_and["counts_by_status"] == {"aberta": 2, "em_andamento": 1, "concluida": 0, "adiada": 0}


@pytest.mark.asyncio
async def test_tarefas_filtro_contact_id_isola_contato(client, org, session):
    """Filtro por contact_id em SQL: só as tarefas do contato pedido."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    bob = Contact(organization_id=org.id, phone="5531900000002", name="Bob", opt_in=True, profile_data={})
    session.add_all([ana, bob])
    await session.flush()
    session.add_all([
        CsTask(organization_id=org.id, contact_id=ana.id, title="A", status="aberta", priority="normal"),
        CsTask(organization_id=org.id, contact_id=bob.id, title="B", status="aberta", priority="normal"),
        CsTask(organization_id=org.id, contact_id=ana.id, title="A2", status="aberta", priority="normal"),
    ])
    await session.commit()

    da_ana = (await client.get("/api/tarefas", params={"contact_id": str(ana.id)})).json()
    assert da_ana["total"] == 2
    assert {i["title"] for i in da_ana["items"]} == {"A", "A2"}
    assert all(i["contato_id"] == str(ana.id) for i in da_ana["items"])


@pytest.mark.asyncio
async def test_tarefas_filtro_contact_id_invalido_422(client, org):
    r = await client.get("/api/tarefas", params={"contact_id": "nao-e-uuid"})
    assert r.status_code == 422


# --- /api/tarefas: vínculo a FeedbackItem ------------------------------------


@pytest.mark.asyncio
async def test_tarefa_com_feedback_id_persiste_e_aparece_no_get(client, org, session):
    """Criar tarefa vinculada a um FeedbackItem: feedback_id volta no POST e no GET,
    com preview truncado do texto."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
        score=3, text="O app trava na hora de abrir o simulado, perdi minha sessão de estudo inteira.",
    )
    session.add(fb)
    await session.commit()

    r = await client.post("/api/tarefas", json={
        "contact_id": str(ana.id), "title": "Abordar Ana sobre o NPS", "feedback_id": str(fb.id),
    })
    assert r.status_code == 201, r.text
    out = r.json()
    assert set(out.keys()) == _TAREFA_KEYS
    assert out["feedback_id"] == str(fb.id)
    # POST devolve o preview do feedback vinculado.
    assert out["feedback_preview"] == fb.text

    # Persistiu na coluna dedicada.
    import uuid as _uuid
    row = (await session.execute(select(CsTask).where(CsTask.id == _uuid.UUID(out["id"])))).scalar_one()
    assert str(row.feedback_item_id) == str(fb.id)

    # GET expõe feedback_id + preview.
    fila = (await client.get("/api/tarefas")).json()
    item = next(i for i in fila["items"] if i["id"] == out["id"])
    assert item["feedback_id"] == str(fb.id)
    assert item["feedback_preview"] == fb.text


@pytest.mark.asyncio
async def test_tarefa_feedback_preview_trunca_texto_longo(client, org, session):
    """Texto longo do feedback é truncado no preview (com reticências)."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="ticket",
        text="x" * 500,
    )
    session.add(fb)
    await session.commit()

    r = await client.post("/api/tarefas", json={
        "contact_id": str(ana.id), "title": "T", "feedback_id": str(fb.id),
    })
    assert r.status_code == 201, r.text
    fila = (await client.get("/api/tarefas")).json()
    item = next(i for i in fila["items"] if i["feedback_id"] == str(fb.id))
    assert item["feedback_preview"] is not None
    assert len(item["feedback_preview"]) <= 140
    assert item["feedback_preview"].endswith("…")  # reticências


@pytest.mark.asyncio
async def test_tarefa_sem_feedback_tem_feedback_id_none(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()
    r = await client.post("/api/tarefas", json={"contact_id": str(ana.id), "title": "sem feedback"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["feedback_id"] is None
    assert out["feedback_preview"] is None


@pytest.mark.asyncio
async def test_tarefa_feedback_inexistente_404(client, org, session):
    import uuid
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()
    r = await client.post("/api/tarefas", json={
        "contact_id": str(ana.id), "title": "x", "feedback_id": str(uuid.uuid4()),
    })
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tarefa_feedback_id_invalido_422(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()
    r = await client.post("/api/tarefas", json={
        "contact_id": str(ana.id), "title": "x", "feedback_id": "nao-e-uuid",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tarefa_feedback_de_outra_org_404(client, org, session):
    """Isolamento multi-tenant: não dá pra vincular feedback de outra org."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb_alheio = FeedbackItem(organization_id=other.id, source="x", type="nps", text="alheio")
    session.add(fb_alheio)
    await session.commit()
    r = await client.post("/api/tarefas", json={
        "contact_id": str(ana.id), "title": "x", "feedback_id": str(fb_alheio.id),
    })
    assert r.status_code == 404


# --- POST /api/tarefas/gerar-de-feedbacks ------------------------------------


@pytest.mark.asyncio
async def test_gerar_de_feedbacks_cria_e_e_idempotente(client, org, session):
    """2 churns negativos sem tarefa -> criadas=2; rodar de novo -> criadas=0 (idempotente)."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    bob = Contact(organization_id=org.id, phone="5531900000002", name="Bob", opt_in=True, profile_data={})
    session.add_all([ana, bob])
    await session.flush()
    fb1 = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        sentiment="negativo", text="Cancelei porque o preço subiu demais e não vi valor.",
    )
    fb2 = FeedbackItem(
        organization_id=org.id, contact_id=bob.id, source="bizzu_billing", type="churn",
        sentiment="negativo", text="Não consegui acessar o conteúdo que eu queria.",
    )
    session.add_all([fb1, fb2])
    await session.commit()

    r = await client.post("/api/tarefas/gerar-de-feedbacks", json={})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["criadas"] == 2
    assert out["ja_existiam"] == 0
    assert len(out["tarefas"]) == 2
    # cada tarefa criada respeita o contrato e vem vinculada ao feedback, status "aberta".
    vinculados = set()
    for t in out["tarefas"]:
        assert set(t.keys()) == _TAREFA_KEYS
        assert t["status"] == "aberta"
        assert t["feedback_id"] is not None
        assert t["title"].startswith("Tratar:")
        vinculados.add(t["feedback_id"])
    assert vinculados == {str(fb1.id), str(fb2.id)}

    # apareceram na fila
    fila = (await client.get("/api/tarefas")).json()
    assert fila["total"] == 2

    # idempotente: rodar de novo não duplica
    r2 = await client.post("/api/tarefas/gerar-de-feedbacks", json={})
    assert r2.status_code == 201, r2.text
    out2 = r2.json()
    assert out2["criadas"] == 0
    assert out2["ja_existiam"] == 2
    assert out2["tarefas"] == []
    assert (await client.get("/api/tarefas")).json()["total"] == 2


@pytest.mark.asyncio
async def test_gerar_de_feedbacks_respeita_filtros(client, org, session):
    """Feedback fora do filtro (tipo/sentimento) não vira tarefa."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    churn_neg = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        sentiment="negativo", text="Cancelei, não valeu a pena.",
    )
    # fora do filtro: tipo != churn
    nps_neg = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
        sentiment="negativo", score=3, text="App lento.",
    )
    # fora do filtro: sentimento != negativo
    churn_pos = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        sentiment="positivo", text="Saí mas adorei o produto.",
    )
    session.add_all([churn_neg, nps_neg, churn_pos])
    await session.commit()

    r = await client.post("/api/tarefas/gerar-de-feedbacks", json={})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["criadas"] == 1
    assert out["tarefas"][0]["feedback_id"] == str(churn_neg.id)
    # só o churn negativo gerou tarefa
    fila = (await client.get("/api/tarefas")).json()
    assert fila["total"] == 1


@pytest.mark.asyncio
async def test_gerar_de_feedbacks_action_status_e_limite(client, org, session):
    """Filtro action_status restringe; `limite` corta o lote (resto fica p/ próxima rodada)."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    novos = [
        FeedbackItem(
            organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
            sentiment="negativo", action_status="a_abordar", text=f"motivo {i}",
        )
        for i in range(3)
    ]
    # mesmo casando tipo+sentimento, action_status != a_abordar fica de fora
    resolvido = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        sentiment="negativo", action_status="resolvido", text="já tratado",
    )
    session.add_all(novos + [resolvido])
    await session.commit()

    r = await client.post("/api/tarefas/gerar-de-feedbacks", json={"action_status": "a_abordar", "limite": 2})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["criadas"] == 2  # limite corta em 2
    assert (await client.get("/api/tarefas")).json()["total"] == 2

    # próxima rodada pega o 3º "a_abordar" (o "resolvido" continua de fora)
    r2 = await client.post("/api/tarefas/gerar-de-feedbacks", json={"action_status": "a_abordar", "limite": 2})
    out2 = r2.json()
    assert out2["criadas"] == 1
    assert out2["ja_existiam"] == 2
    assert (await client.get("/api/tarefas")).json()["total"] == 3


@pytest.mark.asyncio
async def test_gerar_de_feedbacks_titulo_fallback_sem_texto(client, org, session):
    """Sem texto no feedback, o título cai para tipo + contato."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        sentiment="negativo", text=None,
    )
    session.add(fb)
    await session.commit()

    r = await client.post("/api/tarefas/gerar-de-feedbacks", json={})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["criadas"] == 1
    assert out["tarefas"][0]["title"] == "Tratar churn de Ana"


@pytest.mark.asyncio
async def test_gerar_de_feedbacks_isola_org(client, org, session):
    """Multi-tenant: feedback de outra org não vira tarefa na org corrente."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    fb_alheio = FeedbackItem(
        organization_id=other.id, source="bizzu_billing", type="churn",
        sentiment="negativo", text="churn de outra org",
    )
    session.add(fb_alheio)
    await session.commit()

    r = await client.post("/api/tarefas/gerar-de-feedbacks", json={})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["criadas"] == 0
    assert out["ja_existiam"] == 0
    assert (await client.get("/api/tarefas")).json()["total"] == 0


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


# --- Esteira (Fase D, REGRA 1): concluir tarefa resolve o feedback vinculado ----


def _set_esteira(monkeypatch, enabled: bool) -> None:
    """Liga/desliga a flag esteira_enabled no binding `settings` que o handler de
    tarefas usa (frozen dataclass -> dataclasses.replace, igual ao padrão do projeto)."""
    monkeypatch.setattr(
        _tasks_mod, "settings", dataclasses.replace(_tasks_mod.settings, esteira_enabled=enabled)
    )


async def _mk_tarefa_com_feedback(session, org, *, action_status="a_abordar"):
    """Contato + FeedbackItem (com action_status dado) + CsTask vinculada e aberta."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
        score=3, text="trava ao abrir", action_status=action_status,
    )
    session.add(fb)
    await session.flush()
    t = CsTask(
        organization_id=org.id, contact_id=ana.id, title="Abordar Ana",
        status="aberta", priority="normal", feedback_item_id=fb.id,
    )
    session.add(t)
    await session.commit()
    return t, fb


@pytest.mark.asyncio
async def test_esteira_concluir_tarefa_resolve_feedback(client, org, session, monkeypatch):
    """Flag ON + tarefa->concluida + feedback não-terminal: feedback vira 'resolvido'
    e o retorno traz feedback_resolvido=True."""
    _set_esteira(monkeypatch, True)
    t, fb = await _mk_tarefa_com_feedback(session, org, action_status="a_abordar")

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "concluida"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "concluida"
    assert body["feedback_resolvido"] is True

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert row.action_status == "resolvido"


@pytest.mark.asyncio
async def test_esteira_feedback_ja_resolvido_e_noop(client, org, session, monkeypatch):
    """Feedback já em estado terminal (resolvido) -> a esteira não mexe e
    feedback_resolvido=False (idempotência)."""
    _set_esteira(monkeypatch, True)
    t, fb = await _mk_tarefa_com_feedback(session, org, action_status="resolvido")

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "concluida"})
    assert r.status_code == 200, r.text
    assert r.json()["feedback_resolvido"] is False

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert row.action_status == "resolvido"  # inalterado


@pytest.mark.asyncio
async def test_esteira_descartado_tambem_e_noop(client, org, session, monkeypatch):
    """O outro estado terminal ('descartado') também é preservado (não vira resolvido)."""
    _set_esteira(monkeypatch, True)
    t, fb = await _mk_tarefa_com_feedback(session, org, action_status="descartado")

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "concluida"})
    assert r.status_code == 200, r.text
    assert r.json()["feedback_resolvido"] is False

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert row.action_status == "descartado"


@pytest.mark.asyncio
async def test_esteira_flag_off_nao_mexe(client, org, session, monkeypatch):
    """Flag OFF: concluir a tarefa NÃO toca o feedback e feedback_resolvido=False."""
    _set_esteira(monkeypatch, False)
    t, fb = await _mk_tarefa_com_feedback(session, org, action_status="a_abordar")

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "concluida"})
    assert r.status_code == 200, r.text
    assert r.json()["feedback_resolvido"] is False

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert row.action_status == "a_abordar"  # intacto


@pytest.mark.asyncio
async def test_esteira_status_diferente_de_concluida_nao_mexe(client, org, session, monkeypatch):
    """PATCH que NÃO conclui (ex.: status=em_andamento) não dispara a esteira."""
    _set_esteira(monkeypatch, True)
    t, fb = await _mk_tarefa_com_feedback(session, org, action_status="a_abordar")

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "em_andamento"})
    assert r.status_code == 200, r.text
    assert r.json()["feedback_resolvido"] is False

    row = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb.id))).scalar_one()
    assert row.action_status == "a_abordar"


@pytest.mark.asyncio
async def test_esteira_tarefa_sem_feedback_nao_quebra(client, org, session, monkeypatch):
    """Concluir tarefa SEM feedback vinculado: feedback_resolvido=False, sem erro."""
    _set_esteira(monkeypatch, True)
    ana = Contact(organization_id=org.id, phone="5531900000002", name="Bia", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    t = CsTask(organization_id=org.id, contact_id=ana.id, title="sem fb", status="aberta", priority="normal")
    session.add(t)
    await session.commit()

    r = await client.patch(f"/api/tarefas/{t.id}", json={"status": "concluida"})
    assert r.status_code == 200, r.text
    assert r.json()["feedback_resolvido"] is False
