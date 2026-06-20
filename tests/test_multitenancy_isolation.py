"""Isolamento MULTI-TENANT (IDOR entre organizações).

Prova que uma org NÃO acessa (lê/move/edita/deleta) recursos de OUTRA org pelos
endpoints do painel (boards/admin/tasks) e que o webhook resolve a org dona pela
sessão WAHA (com fallback single-org p/ o piloto).

⚠️ Detalhe-chave do projeto: os endpoints do painel resolvem a org SEMPRE pelo
`settings.default_org_slug` ("bizzu") via `_get_org`. Logo, nestes testes:
  - org A == a org DEFAULT ("bizzu") — é "quem está logado" no painel;
  - org B == uma 2ª org ("rival") — seus recursos têm de ficar INVISÍVEIS para A.
O ataque IDOR é: estando logado como A, passar um id de recurso de B e tentar
agir sobre ele. Com o escopo por organization_id, B sempre dá 404 para A.

Mesma infra dos outros testes de API: app real + SQLite in-memory (override de
get_session) + messaging fake. Nada toca Supabase/WAHA/Groq.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import app.api.webhook as webhook  # noqa: E402
from app.api.admin import get_messaging  # noqa: E402
from app.api.webhook import _resolve_org_for_inbound  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.cluster import FeedbackCluster  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
from app.models.playbook import CsTask  # noqa: E402
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
async def orgs(session):
    """Duas orgs: A = a DEFAULT ('bizzu', quem o painel "loga") e B = 'rival'."""
    a = Organization(slug="bizzu", name="Bizzu", settings={})
    b = Organization(slug="rival", name="Rival", settings={})
    session.add_all([a, b])
    await session.commit()
    return a, b


async def _contact(session, org, phone, name="X"):
    c = Contact(organization_id=org.id, phone=phone, name=name, opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    return c


async def _feedback(session, org, contact, **kw):
    f = FeedbackItem(
        organization_id=org.id,
        contact_id=contact.id if contact else None,
        source=kw.pop("source", "manual"),
        type=kw.pop("type", "nps"),
        external_id=kw.pop("external_id", uuid.uuid4().hex),
        text=kw.pop("text", "texto"),
        action_status=kw.pop("action_status", "a_abordar"),
        **kw,
    )
    session.add(f)
    await session.flush()
    return f


# --- WEBHOOK: resolução de org por sessão WAHA + fallback --------------------


@pytest.mark.asyncio
async def test_webhook_resolve_org_por_sessao_waha(orgs, session):
    """Cada org liga sua sessão WAHA (settings['waha_session']); o inbound resolve a
    org DONA daquela sessão — não cai sempre na default."""
    a, b = orgs
    # B liga uma sessão própria; A fica sem (segue como default).
    b.settings = {**(b.settings or {}), "waha_session": "rival-session"}
    await session.commit()

    got = await _resolve_org_for_inbound(session, "rival-session")
    assert got is not None and got.id == b.id  # resolveu para B, NÃO para a default A


@pytest.mark.asyncio
async def test_webhook_fallback_para_default_quando_sessao_nao_casa(orgs, session):
    """Piloto single-org: sessão desconhecida (ninguém a registrou) CAI na org default
    (preserva o comportamento atual)."""
    a, _b = orgs  # a == default ('bizzu')
    got = await _resolve_org_for_inbound(session, "sessao-que-ninguem-registrou")
    assert got is not None and got.id == a.id


@pytest.mark.asyncio
async def test_webhook_fallback_quando_sem_sessao(orgs, session):
    """Sem sessão no envelope (None) também cai na default — nunca mistura tenants."""
    a, _b = orgs
    got = await _resolve_org_for_inbound(session, None)
    assert got is not None and got.id == a.id


# --- BOARDS: items de um board só enxergam recursos da própria org -----------


@pytest.mark.asyncio
async def test_board_items_nao_vazam_feedbacks_de_outra_org(client, orgs, session):
    """O board de feedbacks (org A=default) NÃO conta nem lista feedbacks da org B."""
    a, b = orgs
    ca = await _contact(session, a, "5531900000001", "Ana-A")
    cb = await _contact(session, b, "5531900000002", "Bea-B")
    await _feedback(session, a, ca, action_status="a_abordar", text="feedback de A")
    await _feedback(session, b, cb, action_status="a_abordar", text="feedback de B")
    await session.commit()

    # Board default de triagem (action_status). Quem chama é A (default).
    r = await client.get("/api/boards/default-triagem/items")
    assert r.status_code == 200, r.text
    data = r.json()
    col_novo = next(c for c in data["colunas"] if c["valor"] == "a_abordar")
    # Só o feedback de A aparece; o de B não conta nem vaza.
    assert col_novo["count"] == 1
    textos = {it["text"] for it in col_novo["items"]}
    assert textos == {"feedback de A"}
    assert "feedback de B" not in textos


# --- ADMIN (feedbacks): move/patch/delete por id NÃO atingem outra org -------


@pytest.mark.asyncio
async def test_move_feedback_de_outra_org_da_404(client, orgs, session):
    """POST /feedbacks/{id}/move com um feedback de B (logado como A) => 404, e o
    feedback de B fica INTACTO (status não muda)."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002", "Bea-B")
    fb = await _feedback(session, b, cb, action_status="a_abordar")
    await session.commit()
    fb_id = fb.id

    r = await client.post(f"/api/feedbacks/{fb_id}/move", json={"status": "resolvido"})
    assert r.status_code == 404, r.text

    # Recarrega do banco: o feedback de B continua 'novo' (não foi mexido).
    again = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb_id))
    ).scalar_one()
    assert again.action_status == "a_abordar"


@pytest.mark.asyncio
async def test_patch_feedback_de_outra_org_da_404(client, orgs, session):
    """PATCH /feedbacks/{id} de B (logado como A) => 404 e nada muda em B."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002")
    fb = await _feedback(session, b, cb, action_status="a_abordar", action_note=None)
    await session.commit()
    fb_id = fb.id

    r = await client.patch(
        f"/api/feedbacks/{fb_id}", json={"action_status": "resolvido", "action_note": "hack"}
    )
    assert r.status_code == 404, r.text

    again = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb_id))
    ).scalar_one()
    assert again.action_status == "a_abordar"
    assert again.action_note is None


@pytest.mark.asyncio
async def test_delete_feedback_de_outra_org_da_404_e_nao_apaga(client, orgs, session):
    """DELETE /feedbacks/{id} de B (logado como A) => 404 e o feedback continua no banco."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002")
    fb = await _feedback(session, b, cb)
    await session.commit()
    fb_id = fb.id

    r = await client.delete(f"/api/feedbacks/{fb_id}")
    assert r.status_code == 404, r.text

    still = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb_id))
    ).scalar_one_or_none()
    assert still is not None  # NÃO apagou o recurso de B


@pytest.mark.asyncio
async def test_board_move_feedback_de_outra_org_da_404(client, orgs, session):
    """POST /feedbacks/{id}/board-move (drag-drop genérico) de B => 404; B intacto."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002")
    fb = await _feedback(session, b, cb, action_status="a_abordar")
    await session.commit()
    fb_id = fb.id

    r = await client.post(
        f"/api/feedbacks/{fb_id}/board-move",
        json={"campo": "action_status", "valor": "resolvido"},
    )
    assert r.status_code == 404, r.text
    again = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb_id))
    ).scalar_one()
    assert again.action_status == "a_abordar"


# --- TASKS: patch/criação por id NÃO cruzam org -----------------------------


@pytest.mark.asyncio
async def test_patch_tarefa_de_outra_org_da_404(client, orgs, session):
    """PATCH /tarefas/{id} de B (logado como A) => 404 e a tarefa de B fica intacta."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002")
    task = CsTask(
        organization_id=b.id, contact_id=cb.id, title="Tarefa de B", status="aberta",
        priority="normal",
    )
    session.add(task)
    await session.commit()
    tid = task.id

    r = await client.patch(f"/api/tarefas/{tid}", json={"status": "concluida"})
    assert r.status_code == 404, r.text

    again = (await session.execute(select(CsTask).where(CsTask.id == tid))).scalar_one()
    assert again.status == "aberta"


@pytest.mark.asyncio
async def test_criar_tarefa_com_contato_de_outra_org_da_404(client, orgs, session):
    """POST /tarefas com contact_id de B (logado como A) => 404 (não cria tarefa de A
    apontando para um contato de outro tenant)."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002")
    await session.commit()

    r = await client.post(
        "/api/tarefas", json={"contact_id": str(cb.id), "title": "x"}
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_criar_tarefa_com_feedback_de_outra_org_da_404(client, orgs, session):
    """POST /tarefas vinculando feedback_id de B (com contato VÁLIDO de A) => 404:
    não dá para anexar um feedback de outro tenant."""
    a, b = orgs
    ca = await _contact(session, a, "5531900000001")  # contato válido da org A
    cb = await _contact(session, b, "5531900000002")
    fb_b = await _feedback(session, b, cb)
    await session.commit()

    r = await client.post(
        "/api/tarefas",
        json={"contact_id": str(ca.id), "title": "x", "feedback_id": str(fb_b.id)},
    )
    assert r.status_code == 404, r.text


# --- IMPROVEMENTS (roadmap): patch/link/notify por id NÃO cruzam org --------


@pytest.mark.asyncio
async def test_patch_improvement_de_outra_org_da_404(client, orgs, session):
    """PATCH /improvements/{id} de B (logado como A) => 404 e o status de B não muda."""
    _a, b = orgs
    imp = Improvement(organization_id=b.id, title="Melhoria de B", status="ideia")
    session.add(imp)
    await session.commit()
    iid = imp.id

    r = await client.patch(f"/api/improvements/{iid}", json={"status": "entregue"})
    assert r.status_code == 404, r.text

    again = (
        await session.execute(select(Improvement).where(Improvement.id == iid))
    ).scalar_one()
    assert again.status == "ideia"


@pytest.mark.asyncio
async def test_link_feedbacks_cross_org_da_404(client, orgs, session):
    """POST /improvements/{id}/link de uma melhoria de A vinculando um feedback de B
    => 404; o feedback de B NÃO passa a apontar para a melhoria de A."""
    a, b = orgs
    imp_a = Improvement(organization_id=a.id, title="Melhoria de A", status="ideia")
    session.add(imp_a)
    cb = await _contact(session, b, "5531900000002")
    fb_b = await _feedback(session, b, cb)
    await session.commit()
    fb_b_id = fb_b.id

    r = await client.post(
        f"/api/improvements/{imp_a.id}/link", json={"feedback_ids": [str(fb_b_id)]}
    )
    assert r.status_code == 404, r.text

    again = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.id == fb_b_id))
    ).scalar_one()
    assert again.improvement_id is None  # feedback de B NÃO foi vinculado


@pytest.mark.asyncio
async def test_360_de_contato_de_outra_org_da_404(client, orgs, session):
    """GET /contacts/{id}/360 de um contato de B (logado como A) => 404."""
    _a, b = orgs
    cb = await _contact(session, b, "5531900000002", "Bea-B")
    await session.commit()

    r = await client.get(f"/api/contacts/{cb.id}/360")
    assert r.status_code == 404, r.text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
