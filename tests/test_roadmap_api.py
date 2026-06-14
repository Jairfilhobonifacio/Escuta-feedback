"""Testes da Camada 3 — Roadmap & Melhorias (priorização + nascer de uma dor).

Cobre os dois endpoints novos de `app/api/admin.py`:
- GET  /api/improvements/roadmap  -> lista priorizada por priority_score (desc),
  com urgencia_media (1 query em lote), cluster_label e o efeito do cluster negativo
  no score; ?status= filtra.
- POST /api/improvements/from-cluster -> cria a melhoria a partir do cluster (dor),
  seta os dois lados do vínculo, bulk-linka os feedbacks e é idempotente.

Mesma infra de test_improvements_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nada toca Supabase/WAHA.
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

from app.api.admin import get_brain, get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.cluster import FeedbackCluster  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
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


async def _mk_cluster(session, org, *, label=None, dominant=None):
    cl = FeedbackCluster(
        organization_id=org.id, label=label, dominant_sentiment=dominant, item_count=0
    )
    session.add(cl)
    await session.flush()
    return cl


async def _mk_feedback(
    session, org, *, contact=None, cluster=None, improvement=None,
    sentiment=None, type_="sugestao", text="feedback", abordado=True,
):
    f = FeedbackItem(
        organization_id=org.id,
        contact_id=contact.id if contact else None,
        cluster_id=cluster.id if cluster else None,
        improvement_id=improvement.id if improvement else None,
        source="manual", type=type_, text=text, sentiment=sentiment,
        abordado=abordado, occurred_at=_dt(2026, 6, 1),
    )
    session.add(f)
    await session.flush()
    return f


# --- GET /roadmap: priorização ------------------------------------------------


@pytest.mark.asyncio
async def test_roadmap_ordena_por_priority_score_desc(client, org, session):
    """3 melhorias com counts diferentes -> ordem desc por priority_score.

    Sem cluster: priority_score = feedback_count * max(urgencia_media, 1).
    Todos os feedbacks são iguais (mesma urgência), então mais feedbacks => score maior.
    """
    big = Improvement(organization_id=org.id, title="Muitos", status="ideia")
    mid = Improvement(organization_id=org.id, title="Alguns", status="ideia")
    small = Improvement(organization_id=org.id, title="Poucos", status="ideia")
    session.add_all([big, mid, small])
    await session.flush()

    for _ in range(3):
        await _mk_feedback(session, org, improvement=big, sentiment="neutro")
    for _ in range(2):
        await _mk_feedback(session, org, improvement=mid, sentiment="neutro")
    await _mk_feedback(session, org, improvement=small, sentiment="neutro")
    await session.commit()

    r = await client.get("/api/improvements/roadmap")
    assert r.status_code == 200, r.text
    items = r.json()
    titles = [i["title"] for i in items]
    assert titles == ["Muitos", "Alguns", "Poucos"]
    # score estritamente decrescente
    scores = [i["priority_score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[1] > scores[2]
    # feedback_count + urgencia_media presentes
    assert items[0]["feedback_count"] == 3
    assert items[0]["urgencia_media"] > 0


@pytest.mark.asyncio
async def test_roadmap_cluster_negativo_sobe_o_score(client, org, session):
    """Duas melhorias com MESMO feedback_count e urgência: a ligada a um cluster com
    feedbacks negativos tem priority_score maior (fator 1 + cluster_neg_fraction)."""
    cl = await _mk_cluster(session, org, label="Dor de preço", dominant="negativo")

    com_cluster = Improvement(
        organization_id=org.id, title="Com dor", status="ideia", cluster_id=cl.id
    )
    sem_cluster = Improvement(organization_id=org.id, title="Sem dor", status="ideia")
    session.add_all([com_cluster, sem_cluster])
    await session.flush()

    # 2 feedbacks em cada melhoria, mesma urgência (sentiment None -> sem +40).
    # Os do com_cluster também pertencem ao cluster e são negativos => neg_fraction=1.
    await _mk_feedback(session, org, improvement=com_cluster, cluster=cl, sentiment="negativo")
    await _mk_feedback(session, org, improvement=com_cluster, cluster=cl, sentiment="negativo")
    await _mk_feedback(session, org, improvement=sem_cluster, sentiment="negativo")
    await _mk_feedback(session, org, improvement=sem_cluster, sentiment="negativo")
    await session.commit()

    r = await client.get("/api/improvements/roadmap")
    assert r.status_code == 200
    items = {i["title"]: i for i in r.json()}
    assert items["Com dor"]["cluster_label"] == "Dor de preço"
    assert items["Com dor"]["cluster_neg_fraction"] == 1.0
    assert items["Sem dor"]["cluster_neg_fraction"] == 0.0
    # mesmo count/urgência, mas o fator (1+1) dobra o score do com_cluster
    assert items["Com dor"]["priority_score"] > items["Sem dor"]["priority_score"]
    # ordenação reflete isso
    assert r.json()[0]["title"] == "Com dor"


@pytest.mark.asyncio
async def test_roadmap_filtra_por_status(client, org, session):
    session.add(Improvement(organization_id=org.id, title="Planejada A", status="planejada"))
    session.add(Improvement(organization_id=org.id, title="Ideia B", status="ideia"))
    await session.commit()

    r = await client.get("/api/improvements/roadmap?status=planejada")
    assert r.status_code == 200
    titles = [i["title"] for i in r.json()]
    assert titles == ["Planejada A"]


@pytest.mark.asyncio
async def test_roadmap_sem_feedbacks_score_zero(client, org, session):
    """Melhoria sem feedbacks vinculados: feedback_count=0 => priority_score=0."""
    session.add(Improvement(organization_id=org.id, title="Vazia", status="ideia"))
    await session.commit()

    r = await client.get("/api/improvements/roadmap")
    assert r.status_code == 200
    item = r.json()[0]
    assert item["feedback_count"] == 0
    assert item["urgencia_media"] == 0.0
    assert item["priority_score"] == 0.0
    assert item["cluster_label"] is None


@pytest.mark.asyncio
async def test_roadmap_isolada_por_org(client, org, session):
    """O roadmap só traz melhorias da org default."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    session.add(Improvement(organization_id=org.id, title="Minha", status="ideia"))
    session.add(Improvement(organization_id=other.id, title="Alheia", status="ideia"))
    await session.commit()

    r = await client.get("/api/improvements/roadmap")
    titles = [i["title"] for i in r.json()]
    assert titles == ["Minha"]


# --- POST /from-cluster: nasce de uma dor -------------------------------------


@pytest.mark.asyncio
async def test_from_cluster_cria_e_vincula_feedbacks(client, org, session):
    """Cria a melhoria a partir do cluster: title=label, seta os dois lados do
    vínculo e bulk-linka TODOS os feedbacks daquela dor."""
    cl = await _mk_cluster(session, org, label="Dificuldade no login")
    c = Contact(organization_id=org.id, phone="5531900000001", name="Ana", profile_data={})
    session.add(c)
    await session.flush()
    f1 = await _mk_feedback(session, org, contact=c, cluster=cl, sentiment="negativo")
    f2 = await _mk_feedback(session, org, contact=c, cluster=cl, sentiment="neutro")
    # feedback de OUTRO cluster não deve ser vinculado
    outro = await _mk_cluster(session, org, label="Outra dor")
    f_outro = await _mk_feedback(session, org, cluster=outro)
    await session.commit()

    r = await client.post("/api/improvements/from-cluster", json={"cluster_id": str(cl.id)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Dificuldade no login"
    assert body["status"] == "ideia"
    assert body["cluster_id"] == str(cl.id)
    assert body["feedback_count"] == 2
    imp_id = uuid.UUID(body["id"])

    # os dois lados do vínculo
    await session.refresh(cl)
    assert cl.improvement_id == imp_id

    # bulk-link: f1 e f2 apontam para a melhoria; o de outro cluster, não
    for f in (f1, f2):
        await session.refresh(f)
        assert f.improvement_id == imp_id
    await session.refresh(f_outro)
    assert f_outro.improvement_id is None


@pytest.mark.asyncio
async def test_from_cluster_usa_title_custom(client, org, session):
    """Quando `title` é dado, ele tem prioridade sobre o label do cluster."""
    cl = await _mk_cluster(session, org, label="Rótulo do cluster")
    await session.commit()

    r = await client.post(
        "/api/improvements/from-cluster",
        json={"cluster_id": str(cl.id), "title": "Título escolhido"},
    )
    assert r.status_code == 201
    assert r.json()["title"] == "Título escolhido"


@pytest.mark.asyncio
async def test_from_cluster_idempotente(client, org, session):
    """2ª chamada para um cluster que já virou melhoria devolve a MESMA (não duplica
    nem re-vincula)."""
    cl = await _mk_cluster(session, org, label="Dor X")
    await _mk_feedback(session, org, cluster=cl)
    await session.commit()

    r1 = await client.post("/api/improvements/from-cluster", json={"cluster_id": str(cl.id)})
    assert r1.status_code == 201
    first_id = r1.json()["id"]

    r2 = await client.post("/api/improvements/from-cluster", json={"cluster_id": str(cl.id)})
    assert r2.status_code == 201
    assert r2.json()["id"] == first_id  # mesma melhoria

    # só existe UMA melhoria no banco
    imps = (await session.execute(select(Improvement))).scalars().all()
    assert len(imps) == 1


@pytest.mark.asyncio
async def test_from_cluster_label_nulo_usa_fallback(client, org, session):
    """Cluster sem label e sem title -> título de fallback (não quebra/None)."""
    cl = await _mk_cluster(session, org, label=None)
    await session.commit()

    r = await client.post("/api/improvements/from-cluster", json={"cluster_id": str(cl.id)})
    assert r.status_code == 201
    assert r.json()["title"]  # string não-vazia


@pytest.mark.asyncio
async def test_from_cluster_outra_org_404(client, org, session):
    """Cluster de OUTRA org -> 404 (isolamento)."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    alheio = FeedbackCluster(organization_id=other.id, label="Alheia", item_count=0)
    session.add(alheio)
    await session.commit()

    r = await client.post("/api/improvements/from-cluster", json={"cluster_id": str(alheio.id)})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_from_cluster_id_invalido_422(client, org, session):
    r = await client.post("/api/improvements/from-cluster", json={"cluster_id": "nao-e-uuid"})
    assert r.status_code == 422
