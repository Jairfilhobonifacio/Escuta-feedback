"""Testes das Melhorias do roadmap ("Fechar o loop") + filtro de tema.

Cobre: CRUD de Improvement, link de feedbacks, notify em modo PREVIEW (sem enviar
nada — messaging fake), salvaguarda do confirm, opt_in/cooldown, filtro `theme` no
inbox e isolamento multi-tenant. Mesma infra de test_monitoring_api.py: app real +
SQLite in-memory (override de get_session) + messaging fake. Nada toca Supabase/WAHA.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import get_brain, get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.cluster import FeedbackCluster  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
from app.models.survey import Message  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


@pytest_asyncio.fixture
async def fake_messaging():
    return FakeMessagingService()


@pytest_asyncio.fixture
async def client(session, fake_messaging):
    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_messaging] = lambda: fake_messaging
    # Sem brain (sem auto-classify): isola os testes do LLM.
    app.dependency_overrides[get_brain] = lambda: None
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


async def _mk_contact(session, org, *, phone, name, opt_in=True, profile=None):
    c = Contact(
        organization_id=org.id, phone=phone, name=name, opt_in=opt_in,
        profile_data=profile or {},
    )
    session.add(c)
    await session.flush()
    return c


async def _mk_feedback(session, org, *, contact=None, themes=None, text="feedback", type_="sugestao"):
    f = FeedbackItem(
        organization_id=org.id,
        contact_id=contact.id if contact else None,
        source="manual", type=type_, text=text, themes=themes,
        occurred_at=_dt(2026, 6, 1),
    )
    session.add(f)
    await session.flush()
    return f


# --- CRUD de Improvement ------------------------------------------------------


@pytest.mark.asyncio
async def test_create_improvement_201(client, org):
    r = await client.post("/api/improvements", json={"title": "Filtro por banca"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Filtro por banca"
    assert body["status"] == "ideia"
    assert body["feedback_count"] == 0
    assert body["delivered_em"] is None
    assert body["notified_em"] is None
    assert uuid.UUID(body["id"])


@pytest.mark.asyncio
async def test_create_improvement_title_obrigatorio_422(client, org):
    r = await client.post("/api/improvements", json={"description": "sem titulo"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_improvements_com_feedback_count(client, org, session):
    imp = Improvement(organization_id=org.id, title="Melhoria A", status="planejada")
    session.add(imp)
    await session.flush()
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana")
    await _mk_feedback(session, org, contact=c, themes=["preço"])
    f2 = await _mk_feedback(session, org, contact=c, themes=["preço"])
    f2.improvement_id = imp.id
    f1 = (await session.execute(select(FeedbackItem).where(FeedbackItem.id != f2.id))).scalars().first()
    f1.improvement_id = imp.id
    await session.commit()

    r = await client.get("/api/improvements")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["title"] == "Melhoria A"
    assert items[0]["status"] == "planejada"
    assert items[0]["feedback_count"] == 2


@pytest.mark.asyncio
async def test_patch_status_entregue_grava_delivered_at(client, org, session):
    imp = Improvement(organization_id=org.id, title="X", status="em_andamento")
    session.add(imp)
    await session.commit()

    r = await client.patch(f"/api/improvements/{imp.id}", json={"status": "entregue"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "entregue"
    assert body["delivered_em"] is not None


@pytest.mark.asyncio
async def test_patch_status_invalido_422(client, org, session):
    imp = Improvement(organization_id=org.id, title="X")
    session.add(imp)
    await session.commit()
    r = await client.patch(f"/api/improvements/{imp.id}", json={"status": "voando"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_title_description(client, org, session):
    imp = Improvement(organization_id=org.id, title="Antigo")
    session.add(imp)
    await session.commit()
    r = await client.patch(
        f"/api/improvements/{imp.id}", json={"title": "Novo", "description": "desc"}
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Novo"
    assert r.json()["description"] == "desc"


@pytest.mark.asyncio
async def test_patch_entregue_idempotente_nao_recarimba(client, org, session):
    """Re-PATCH para 'entregue' não muda o delivered_at já gravado."""
    imp = Improvement(
        organization_id=org.id, title="X", status="entregue",
        delivered_at=_dt(2026, 6, 1),
    )
    session.add(imp)
    await session.commit()
    r = await client.patch(f"/api/improvements/{imp.id}", json={"status": "entregue"})
    assert r.status_code == 200
    assert r.json()["delivered_em"] == _dt(2026, 6, 1).isoformat()


# --- Campos novos: cluster_id / effort / target_date (Camada 3) ---------------


async def _mk_cluster(session, org, *, label=None):
    cl = FeedbackCluster(organization_id=org.id, label=label, item_count=0)
    session.add(cl)
    await session.flush()
    return cl


@pytest.mark.asyncio
async def test_create_improvement_com_campos_novos(client, org, session):
    """create aceita cluster_id (da org), effort e target_date; serializa os três."""
    cl = await _mk_cluster(session, org, label="Dor")
    await session.commit()

    r = await client.post(
        "/api/improvements",
        json={
            "title": "Com extras",
            "cluster_id": str(cl.id),
            "effort": "G",
            "target_date": "2026-07-01T00:00:00+00:00",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["cluster_id"] == str(cl.id)
    assert body["effort"] == "G"
    assert body["target_date"] == "2026-07-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_create_improvement_effort_minusculo_normaliza(client, org, session):
    r = await client.post("/api/improvements", json={"title": "x", "effort": "m"})
    assert r.status_code == 201
    assert r.json()["effort"] == "M"


@pytest.mark.asyncio
async def test_create_improvement_effort_invalido_422(client, org, session):
    r = await client.post("/api/improvements", json={"title": "x", "effort": "ENORME"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_improvement_cluster_de_outra_org_404(client, org, session):
    """cluster_id de OUTRA org no create -> 404 (isolamento)."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    alheio = FeedbackCluster(organization_id=other.id, label="Alheia", item_count=0)
    session.add(alheio)
    await session.commit()

    r = await client.post(
        "/api/improvements", json={"title": "x", "cluster_id": str(alheio.id)}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_campos_novos(client, org, session):
    """PATCH parcial seta effort, target_date e cluster_id (model_fields_set)."""
    cl = await _mk_cluster(session, org, label="Dor")
    imp = Improvement(organization_id=org.id, title="X")
    session.add(imp)
    await session.commit()

    r = await client.patch(
        f"/api/improvements/{imp.id}",
        json={"effort": "P", "cluster_id": str(cl.id), "target_date": "2026-08-01T00:00:00+00:00"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effort"] == "P"
    assert body["cluster_id"] == str(cl.id)
    assert body["target_date"] == "2026-08-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_patch_limpa_cluster_e_effort_com_null(client, org, session):
    """Enviar null limpa o campo (model_fields_set distingue de 'não enviado')."""
    cl = await _mk_cluster(session, org, label="Dor")
    imp = Improvement(
        organization_id=org.id, title="X", cluster_id=cl.id, effort="G",
    )
    session.add(imp)
    await session.commit()

    r = await client.patch(
        f"/api/improvements/{imp.id}", json={"cluster_id": None, "effort": None}
    )
    assert r.status_code == 200
    assert r.json()["cluster_id"] is None
    assert r.json()["effort"] is None


@pytest.mark.asyncio
async def test_patch_effort_invalido_422(client, org, session):
    imp = Improvement(organization_id=org.id, title="X")
    session.add(imp)
    await session.commit()
    r = await client.patch(f"/api/improvements/{imp.id}", json={"effort": "gigante"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_nao_mexe_em_campo_nao_enviado(client, org, session):
    """PATCH só de title não zera effort/cluster_id já gravados."""
    cl = await _mk_cluster(session, org, label="Dor")
    imp = Improvement(organization_id=org.id, title="Antigo", cluster_id=cl.id, effort="M")
    session.add(imp)
    await session.commit()

    r = await client.patch(f"/api/improvements/{imp.id}", json={"title": "Novo"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Novo"
    assert body["effort"] == "M"
    assert body["cluster_id"] == str(cl.id)


# --- Link de feedbacks --------------------------------------------------------


@pytest.mark.asyncio
async def test_link_feedbacks_vincula_e_conta(client, org, session):
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana")
    f1 = await _mk_feedback(session, org, contact=c, themes=["preço"])
    f2 = await _mk_feedback(session, org, contact=c, themes=["bug"])
    await session.commit()

    r = await client.post(
        f"/api/improvements/{imp.id}/link",
        json={"feedback_ids": [str(f1.id), str(f2.id)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["improvement"]["feedback_count"] == 2
    assert set(body["linked"]) == {str(f1.id), str(f2.id)}

    # de fato setou improvement_id no banco
    refreshed = (await session.execute(select(FeedbackItem))).scalars().all()
    assert all(f.improvement_id == imp.id for f in refreshed)


@pytest.mark.asyncio
async def test_link_feedback_de_outra_org_404(client, org, session):
    """Vincular feedback de OUTRA org é rejeitado (404) — isolamento."""
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    alheio = FeedbackItem(
        organization_id=other.id, source="manual", type="nps", text="alheio",
        occurred_at=_dt(2026, 6, 1),
    )
    session.add(alheio)
    await session.commit()

    r = await client.post(
        f"/api/improvements/{imp.id}/link", json={"feedback_ids": [str(alheio.id)]}
    )
    assert r.status_code == 404
    # não vinculou
    await session.refresh(alheio)
    assert alheio.improvement_id is None


# --- Notify (preview / confirm / opt_in / cooldown) ---------------------------


@pytest.mark.asyncio
async def test_notify_preview_nao_envia(client, org, session, fake_messaging):
    """DEFAULT = preview: retorna would_send com a mensagem, SEM enviar nada e SEM
    gravar notified_at."""
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana Promotora", opt_in=True)
    f = await _mk_feedback(session, org, contact=c, themes=["preço"])
    f.improvement_id = imp.id
    await session.commit()

    r = await client.post(f"/api/improvements/{imp.id}/notify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"] is True
    assert body["sent"] is False
    assert body["theme"] == "preço"
    assert len(body["would_send"]) == 1
    msg = body["would_send"][0]["mensagem"]
    assert "Ana" in msg
    assert "preço" in msg
    assert "—" not in msg  # marca: sem travessão
    assert body["skipped"] == []

    # NADA foi enviado (salvaguarda)
    assert fake_messaging.sent == []
    # notified_at continua None
    await session.refresh(imp)
    assert imp.notified_at is None


@pytest.mark.asyncio
async def test_notify_confirm_envia_e_grava(client, org, session, fake_messaging):
    """confirm=true envia de verdade (messaging fake), grava outbound + notified_at."""
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana", opt_in=True)
    f = await _mk_feedback(session, org, contact=c, themes=["edital"])
    f.improvement_id = imp.id
    await session.commit()

    r = await client.post(f"/api/improvements/{imp.id}/notify?confirm=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"] is False
    assert body["sent"] is True
    assert body["sent_count"] == 1
    assert body["notified_em"] is not None

    # mensagem realmente passou pelo messaging fake
    assert len(fake_messaging.sent) == 1
    assert fake_messaging.sent[0]["chat_id"] == "5531900000001"

    # outbound gravado no transcript
    msgs = (await session.execute(select(Message))).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].direction == "outbound"

    # notified_at gravado
    await session.refresh(imp)
    assert imp.notified_at is not None


@pytest.mark.asyncio
async def test_notify_pula_sem_opt_in(client, org, session, fake_messaging):
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    c = await _mk_contact(session, org, phone="5531900000002", name="Bia", opt_in=False)
    f = await _mk_feedback(session, org, contact=c, themes=["preço"])
    f.improvement_id = imp.id
    await session.commit()

    r = await client.post(f"/api/improvements/{imp.id}/notify?confirm=true")
    assert r.status_code == 200
    body = r.json()
    assert body["would_send"] == []
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "sem_opt_in"
    assert fake_messaging.sent == []  # nada enviado


@pytest.mark.asyncio
async def test_notify_respeita_cooldown(client, org, session, fake_messaging):
    """Contato com outbound recente cai no cooldown (skipped), mesmo com opt_in."""
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    c = await _mk_contact(session, org, phone="5531900000003", name="Caio", opt_in=True)
    f = await _mk_feedback(session, org, contact=c, themes=["preço"])
    f.improvement_id = imp.id
    # outbound de 1h atrás -> dentro da janela de cooldown (default 20h)
    session.add(
        Message(
            organization_id=org.id, contact_id=c.id, direction="outbound", body="oi",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    await session.commit()

    r = await client.post(f"/api/improvements/{imp.id}/notify")
    assert r.status_code == 200
    body = r.json()
    assert body["would_send"] == []
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "cooldown"


@pytest.mark.asyncio
async def test_notify_sem_tema_usa_fallback(client, org, session):
    """Feedbacks sem themes -> theme None -> mensagem com fallback genérico (sem crash)."""
    imp = Improvement(organization_id=org.id, title="Loop")
    session.add(imp)
    c = await _mk_contact(session, org, phone="5531900000004", name="Duda", opt_in=True)
    f = await _mk_feedback(session, org, contact=c, themes=None)
    f.improvement_id = imp.id
    await session.commit()

    r = await client.post(f"/api/improvements/{imp.id}/notify")
    assert r.status_code == 200
    body = r.json()
    assert body["theme"] is None
    assert len(body["would_send"]) == 1
    assert "Duda" in body["would_send"][0]["mensagem"]


@pytest.mark.asyncio
async def test_improvement_de_outra_org_404(client, org, session):
    """GET/PATCH/notify de melhoria de OUTRA org dá 404 (isolamento)."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    imp = Improvement(organization_id=other.id, title="Alheia")
    session.add(imp)
    await session.commit()

    assert (await client.patch(f"/api/improvements/{imp.id}", json={"title": "x"})).status_code == 404
    assert (await client.post(f"/api/improvements/{imp.id}/notify")).status_code == 404
    assert (
        await client.post(f"/api/improvements/{imp.id}/link", json={"feedback_ids": [str(uuid.uuid4())]})
    ).status_code == 404


@pytest.mark.asyncio
async def test_list_improvements_isolada_por_org(client, org, session):
    """A lista só traz melhorias da org default — nunca de outra org."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    session.add(Improvement(organization_id=org.id, title="Minha"))
    session.add(Improvement(organization_id=other.id, title="Alheia"))
    await session.commit()

    r = await client.get("/api/improvements")
    titles = [i["title"] for i in r.json()]
    assert titles == ["Minha"]


# --- Filtro de tema no inbox --------------------------------------------------


@pytest.mark.asyncio
async def test_filtro_theme_match_exato(client, org, session):
    """GET /api/feedbacks?theme=preço só traz feedbacks cujo array themes CONTÉM
    'preço' exatamente (não substring, não outros temas)."""
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana")
    await _mk_feedback(session, org, contact=c, themes=["preço", "suporte"], text="caro")
    await _mk_feedback(session, org, contact=c, themes=["bug"], text="travou")
    await _mk_feedback(session, org, contact=c, themes=["preços"], text="plural")  # não casa (exato)
    await _mk_feedback(session, org, contact=c, themes=None, text="sem tema")
    await session.commit()

    r = await client.get("/api/feedbacks?theme=preço")
    assert r.status_code == 200, r.text
    body = r.json()
    texts = sorted(it["text"] for it in body["items"])
    assert texts == ["caro"]
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_filtro_theme_combina_com_outros_filtros(client, org, session):
    """theme combina com os demais filtros (ex.: type) e o total reflete os dois."""
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana")
    await _mk_feedback(session, org, contact=c, themes=["preço"], text="a", type_="bug")
    await _mk_feedback(session, org, contact=c, themes=["preço"], text="b", type_="sugestao")
    await session.commit()

    r = await client.get("/api/feedbacks?theme=preço&type=bug")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["text"] == "a"


@pytest.mark.asyncio
async def test_filtro_theme_sem_match_vazio(client, org, session):
    c = await _mk_contact(session, org, phone="5531900000001", name="Ana")
    await _mk_feedback(session, org, contact=c, themes=["bug"], text="x")
    await session.commit()

    r = await client.get("/api/feedbacks?theme=inexistente")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


# --- Esteira (Fase D, REGRA 2): melhoria entregue resolve os feedbacks ----------


def _set_esteira(org, enabled: bool) -> None:
    """Liga/desliga a feature `esteira_enabled` POR ORG (Central do Agente). O handler de
    admin lê via feature_enabled(org, ...); gravamos o override em settings["features"]
    (copia-edita-reatribui o JSONB, padrão do projeto)."""
    s = dict(org.settings or {})
    feats = dict(s.get("features") or {})
    feats["esteira_enabled"] = enabled
    s["features"] = feats
    org.settings = s


async def _mk_fb_acionavel(session, org, imp, action_status):
    """FeedbackItem vinculado a `imp` com o action_status pedido."""
    f = FeedbackItem(
        organization_id=org.id, source="manual", type="sugestao", text="dor",
        improvement_id=imp.id, action_status=action_status,
        occurred_at=_dt(2026, 6, 1),
    )
    session.add(f)
    await session.flush()
    return f


@pytest.mark.asyncio
async def test_esteira_entregue_resolve_feedbacks_vinculados(client, org, session, monkeypatch):
    """Flag ON + status->entregue: TODO feedback vinculado não-terminal vira 'resolvido';
    os já terminais (resolvido/descartado) ficam intactos; feedback de OUTRA melhoria não
    é tocado."""
    _set_esteira(org, True)
    imp = Improvement(organization_id=org.id, title="Loop", status="em_andamento")
    outra = Improvement(organization_id=org.id, title="Outra", status="ideia")
    session.add_all([imp, outra])
    await session.flush()

    f_novo = await _mk_fb_acionavel(session, org, imp, "a_abordar")
    f_analise = await _mk_fb_acionavel(session, org, imp, "em_acompanhamento")
    f_resolvido = await _mk_fb_acionavel(session, org, imp, "resolvido")
    f_descartado = await _mk_fb_acionavel(session, org, imp, "descartado")
    f_outra = await _mk_fb_acionavel(session, org, outra, "a_abordar")
    await session.commit()

    r = await client.patch(f"/api/improvements/{imp.id}", json={"status": "entregue"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "entregue"

    for f in (f_novo, f_analise):
        await session.refresh(f)
        assert f.action_status == "resolvido"  # não-terminais -> resolvidos
    await session.refresh(f_resolvido)
    assert f_resolvido.action_status == "resolvido"  # já estava
    await session.refresh(f_descartado)
    assert f_descartado.action_status == "descartado"  # terminal preservado
    await session.refresh(f_outra)
    assert f_outra.action_status == "a_abordar"  # de outra melhoria, intacto


@pytest.mark.asyncio
async def test_esteira_entregue_flag_off_nao_mexe(client, org, session, monkeypatch):
    """Flag OFF: entregar a melhoria NÃO resolve os feedbacks vinculados."""
    _set_esteira(org, False)
    imp = Improvement(organization_id=org.id, title="Loop", status="em_andamento")
    session.add(imp)
    await session.flush()
    f = await _mk_fb_acionavel(session, org, imp, "a_abordar")
    await session.commit()

    r = await client.patch(f"/api/improvements/{imp.id}", json={"status": "entregue"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "entregue"

    await session.refresh(f)
    assert f.action_status == "a_abordar"  # intacto


@pytest.mark.asyncio
async def test_esteira_entregue_idempotente_reentrega_noop(client, org, session, monkeypatch):
    """Re-PATCH para 'entregue' (já estava entregue) não re-dispara a esteira: um feedback
    reaberto manualmente após a 1ª entrega permanece como o operador deixou."""
    _set_esteira(org, True)
    imp = Improvement(organization_id=org.id, title="Loop", status="em_andamento")
    session.add(imp)
    await session.flush()
    f = await _mk_fb_acionavel(session, org, imp, "a_abordar")
    await session.commit()

    r1 = await client.patch(f"/api/improvements/{imp.id}", json={"status": "entregue"})
    assert r1.status_code == 200
    await session.refresh(f)
    assert f.action_status == "resolvido"

    # operador reabre o feedback manualmente
    f.action_status = "em_acompanhamento"
    await session.commit()

    # re-entregar (já estava entregue) NÃO re-resolve
    r2 = await client.patch(f"/api/improvements/{imp.id}", json={"status": "entregue"})
    assert r2.status_code == 200
    await session.refresh(f)
    assert f.action_status == "em_acompanhamento"
