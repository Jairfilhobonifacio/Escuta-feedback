"""Clustering Semântico de Dores (Camada 1) — testes sem tocar pgvector.

Estratégia (docs/CLUSTERING_DORES_SPEC.md §6):
- Engine: o `run_clustering(dry_run=True)` recebe os vetores por um HOOK
  (`load_vectors`) que devolve `LoadedItem`s com numpy sintético — zero pgvector,
  zero MiniLM, zero rede. Testa-se o AGRUPAMENTO (dois temas separados) e que o dry
  run NÃO grava nada.
- Rotulagem: `_label_cluster` é exercido direto com um `FakeLLM` (1 chamada/cluster).
- API: `GET /PATCH /feedbacks/clusters` com `FeedbackCluster` pré-inseridos (sem
  `centroid`, fora do ORM) + `FeedbackItem`s com `cluster_id`, no SQLite in-memory.
- `reindex`: `get_session` é dublado por uma sessão fake (o UPDATE/SELECT do
  embedding usa a coluna pgvector, inexistente no SQLite) + `FakeEmbedder` — testa a
  ORQUESTRAÇÃO (pega pendentes → embeda em lote → conta restantes) sem banco vetorial.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import _get_org, get_brain  # noqa: E402
from app.api.clusters import get_embedder_dep  # noqa: E402
from app.db import get_session  # noqa: E402
from app.domain.clustering.engine import (  # noqa: E402
    ClusterDraft,
    LoadedItem,
    _agglomerate,
    _dominant_sentiment,
    _label_cluster,
    run_clustering,
)
from app.main import app  # noqa: E402
from app.models.cluster import FeedbackCluster  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from tests.fakes import FakeEmbedder, FakeLLM  # noqa: E402


# --- helpers -----------------------------------------------------------------


def _unit(vec: list[float]) -> np.ndarray:
    a = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return (a / n).astype(np.float32) if n else a


def _item(vec: list[float], sentiment=None, text=None) -> LoadedItem:
    return LoadedItem(id=uuid.uuid4(), vector=_unit(vec), sentiment=sentiment, text=text)


# Dois "temas" claramente separados em 4 dims (quase ortogonais entre grupos).
_GROUP_A = [
    _item([1.0, 0.02, 0.0, 0.0], "negativo", "não consigo logar"),
    _item([0.98, 0.05, 0.01, 0.0], "negativo", "login não funciona"),
    _item([0.97, 0.0, 0.03, 0.0], "neutro", "problema pra entrar na conta"),
]
_GROUP_B = [
    _item([0.0, 0.0, 1.0, 0.02], "positivo", "preço justo"),
    _item([0.01, 0.0, 0.98, 0.05], "positivo", "barato e bom"),
]


# --- Engine: agrupamento (puro, sem DB) --------------------------------------


def test_agglomerate_separa_dois_temas():
    drafts = _agglomerate(_GROUP_A + _GROUP_B, threshold=0.75)
    assert len(drafts) == 2
    sizes = sorted(d.item_count for d in drafts)
    assert sizes == [2, 3]
    # O centroide é unitário (renormalizado).
    for d in drafts:
        assert abs(float(np.linalg.norm(d.centroid)) - 1.0) < 1e-4


def test_agglomerate_threshold_alto_nao_une_nada():
    # 5 vetores mutuamente ortogonais; threshold alto não une ninguém.
    orto = [
        _item([1, 0, 0, 0, 0]), _item([0, 1, 0, 0, 0]), _item([0, 0, 1, 0, 0]),
        _item([0, 0, 0, 1, 0]), _item([0, 0, 0, 0, 1]),
    ]
    drafts = _agglomerate(orto, threshold=0.75)
    assert len(drafts) == 5
    assert all(d.item_count == 1 for d in drafts)


def test_agglomerate_vazio():
    assert _agglomerate([], threshold=0.75) == []


def test_dominant_sentiment_conta_e_desempata():
    assert _dominant_sentiment(["negativo", "negativo", "neutro"]) == "negativo"
    assert _dominant_sentiment([None, None]) is None
    # Empate negativo/positivo → negativo (sinal mais acionável).
    assert _dominant_sentiment(["positivo", "negativo"]) == "negativo"


# --- Engine: run_clustering dry_run via hook (sem pgvector) -------------------


@pytest.mark.asyncio
async def test_run_clustering_dry_run_agrupa_e_nao_grava(session):
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.commit()

    async def _load(_session, _org_id):
        return _GROUP_A + _GROUP_B

    report = await run_clustering(
        session, org.id, embedder=FakeEmbedder(), llm=None,
        threshold=0.75, dry_run=True, load_vectors=_load,
    )
    assert report.dry_run is True
    assert report.evaluated == 5
    # Aglomera SEPARANDO por sentimento: GROUP_A (2 negativo + 1 neutro) vira 2 clusters
    # e GROUP_B (2 positivo) vira 1 — uma dor nunca mistura elogio com crítica.
    assert report.clusters_found == 3
    assert report.clusters_created == 0  # dry run não cria
    assert report.items_assigned == 0
    assert len(report.clusters) == 3
    counts = sorted(c["item_count"] for c in report.clusters)
    assert counts == [1, 2, 2]
    # Cada cluster tem um único sentimento dominante (prova da separação).
    assert {c["dominant_sentiment"] for c in report.clusters} == {"negativo", "neutro", "positivo"}

    # Nada gravado: nenhuma FeedbackCluster e nenhum item com cluster_id.
    assert (await session.execute(select(FeedbackCluster))).scalars().all() == []


@pytest.mark.asyncio
async def test_run_clustering_sem_itens_retorna_vazio(session):
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.commit()

    async def _load(_session, _org_id):
        return []

    report = await run_clustering(
        session, org.id, embedder=FakeEmbedder(), dry_run=True, load_vectors=_load,
    )
    assert report.evaluated == 0
    assert report.clusters_found == 0
    assert report.clusters == []


# --- Engine: rotulagem via FakeLLM (1 chamada/cluster, best-effort) ----------


@pytest.mark.asyncio
async def test_label_cluster_usa_llm():
    draft = ClusterDraft(
        member_ids=[uuid.uuid4()],
        centroid=_unit([1.0, 0.0]),
        dominant_sentiment="negativo",
        texts=["não consigo logar", "login quebrado"],
    )
    fake = FakeLLM({"label": "Acesso à conta", "description": "Falha no login.", "dominant_sentiment": "negativo"})
    out = await _label_cluster(fake, draft)
    assert out == {"label": "Acesso à conta", "description": "Falha no login.", "dominant_sentiment": "negativo"}
    assert len(fake.calls) == 1  # exatamente 1 chamada por cluster


@pytest.mark.asyncio
async def test_label_cluster_best_effort_sem_llm_e_payload_invalido():
    draft = ClusterDraft(
        member_ids=[uuid.uuid4()], centroid=_unit([1.0, 0.0]),
        dominant_sentiment=None, texts=["algum texto"],
    )
    assert await _label_cluster(None, draft) is None          # sem LLM
    assert await _label_cluster(FakeLLM(None), draft) is None  # LLM devolve None
    # Cluster sem textos não chama o LLM.
    vazio = ClusterDraft(member_ids=[uuid.uuid4()], centroid=_unit([1.0]), dominant_sentiment=None, texts=[])
    fake = FakeLLM()
    assert await _label_cluster(fake, vazio) is None
    assert fake.calls == []


# --- API: fixtures ------------------------------------------------------------


@pytest_asyncio.fixture
async def client(session):
    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    # Sem LLM por padrão nos testes de API (rotulagem best-effort = None).
    app.dependency_overrides[get_brain] = lambda: None
    app.dependency_overrides[get_embedder_dep] = lambda: FakeEmbedder()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={"owner_phone": "5531999999999"})
    session.add(o)
    await session.commit()
    return o


# --- API: GET /feedbacks/clusters --------------------------------------------


@pytest.mark.asyncio
async def test_list_clusters_pain_score_e_sort(client, org, session):
    # Dor 1: 3 itens, 2 negativos → pain_score = 3 * (2/3) = 2.0
    dor1 = FeedbackCluster(
        organization_id=org.id, label="Acesso", dominant_sentiment="negativo", item_count=3,
    )
    # Dor 2: 2 itens, 0 negativos → pain_score = 0.0
    dor2 = FeedbackCluster(
        organization_id=org.id, label="Preço", dominant_sentiment="positivo", item_count=2,
    )
    session.add_all([dor1, dor2])
    await session.flush()

    session.add_all([
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="a",
                     sentiment="negativo", themes=["login"], cluster_id=dor1.id),
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="b",
                     sentiment="negativo", themes=["login", "conta"], cluster_id=dor1.id),
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="c",
                     sentiment="neutro", themes=["conta"], cluster_id=dor1.id),
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="d",
                     sentiment="positivo", themes=["preço"], cluster_id=dor2.id),
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="e",
                     sentiment="positivo", cluster_id=dor2.id),
        # item sem cluster e com texto → conta em total_unclustered
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="solto"),
    ])
    await session.commit()

    data = (await client.get("/api/feedbacks/clusters", params={"sort": "dor", "days": 0})).json()
    assert data["total_items_clustered"] == 5
    assert data["total_unclustered"] == 1
    assert len(data["clusters"]) == 2
    # sort=dor → a dor com maior pain_score primeiro
    first = data["clusters"][0]
    assert first["label"] == "Acesso"
    assert first["neg_count"] == 2
    assert first["pain_score"] == 2.0
    assert first["top_themes"]  # top tags cruzadas (login/conta)
    assert "login" in first["top_themes"]
    assert data["clusters"][1]["pain_score"] == 0.0

    # sort=volume idem aqui (3 > 2)
    vol = (await client.get("/api/feedbacks/clusters", params={"sort": "volume", "days": 0})).json()
    assert [c["item_count"] for c in vol["clusters"]] == [3, 2]


@pytest.mark.asyncio
async def test_list_clusters_filtro_days(client, org, session):
    from datetime import timedelta

    velho = FeedbackCluster(organization_id=org.id, label="Antiga", item_count=1)
    session.add(velho)
    await session.flush()
    # Força created/updated bem no passado (fora da janela de 30 dias).
    old_dt = datetime.now(timezone.utc) - timedelta(days=200)
    velho.created_at = old_dt
    velho.updated_at = old_dt
    await session.commit()

    # days=30 (default) NÃO traz a antiga; days=0 traz tudo.
    recente = (await client.get("/api/feedbacks/clusters", params={"days": 30})).json()
    assert recente["clusters"] == []
    todos = (await client.get("/api/feedbacks/clusters", params={"days": 0})).json()
    assert len(todos["clusters"]) == 1


# --- API: GET /feedbacks/clusters/{id} ---------------------------------------


@pytest.mark.asyncio
async def test_get_cluster_detalhe_com_itens(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    dor = FeedbackCluster(organization_id=org.id, label="Acesso", item_count=1, dominant_sentiment="negativo")
    session.add(dor)
    await session.flush()
    session.add(
        FeedbackItem(organization_id=org.id, contact_id=ana.id, source="s", type="nps",
                     text="não logo", sentiment="negativo", cluster_id=dor.id)
    )
    await session.commit()

    r = await client.get(f"/api/feedbacks/clusters/{dor.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cluster"]["label"] == "Acesso"
    assert body["cluster"]["item_count"] == 1
    assert len(body["items"]) == 1
    # Itens no formato do feed (mesmas chaves do inbox).
    assert body["items"][0]["text"] == "não logo"
    assert body["items"][0]["contato_nome"] == "Ana"
    assert "urgencia" in body["items"][0]


@pytest.mark.asyncio
async def test_get_cluster_404_e_id_invalido(client, org):
    assert (await client.get(f"/api/feedbacks/clusters/{uuid.uuid4()}")).status_code == 404
    assert (await client.get("/api/feedbacks/clusters/nao-e-uuid")).status_code == 422


# --- API: PATCH /feedbacks/clusters/{id} -------------------------------------


@pytest.mark.asyncio
async def test_patch_cluster_corrige_label(client, org, session):
    dor = FeedbackCluster(organization_id=org.id, label="ruim", description="x", item_count=1)
    session.add(dor)
    await session.commit()

    r = await client.patch(f"/api/feedbacks/clusters/{dor.id}", json={"label": "Dificuldade no acesso"})
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "Dificuldade no acesso"
    assert r.json()["description"] == "x"  # não tocado

    row = (await session.execute(select(FeedbackCluster).where(FeedbackCluster.id == dor.id))).scalar_one()
    assert row.label == "Dificuldade no acesso"


@pytest.mark.asyncio
async def test_patch_cluster_404(client, org):
    r = await client.patch(f"/api/feedbacks/clusters/{uuid.uuid4()}", json={"label": "x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cluster_de_outra_org_nao_aparece(client, org, session):
    """Isolamento multi-tenant: dor de outra org não vaza na lista nem no detalhe."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    alheia = FeedbackCluster(organization_id=other.id, label="alheia", item_count=1)
    session.add(alheia)
    await session.commit()

    assert (await client.get("/api/feedbacks/clusters", params={"days": 0})).json()["clusters"] == []
    assert (await client.get(f"/api/feedbacks/clusters/{alheia.id}")).status_code == 404


# --- API: inbox aceita filtro cluster_id -------------------------------------


@pytest.mark.asyncio
async def test_list_feedbacks_filtra_por_cluster_id(client, org, session):
    dor = FeedbackCluster(organization_id=org.id, label="Acesso", item_count=1)
    session.add(dor)
    await session.flush()
    session.add_all([
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="da dor", cluster_id=dor.id),
        FeedbackItem(organization_id=org.id, source="s", type="nps", text="solta"),
    ])
    await session.commit()

    todos = (await client.get("/api/feedbacks")).json()
    assert todos["total"] == 2
    so_dor = (await client.get("/api/feedbacks", params={"cluster_id": str(dor.id)})).json()
    assert so_dor["total"] == 1
    assert so_dor["items"][0]["text"] == "da dor"


# --- API: POST /feedbacks/reindex (sessão dublada + FakeEmbedder) ------------


class _FakeResult:
    def __init__(self, rows=None, scalar=None, one=...):
        self._rows = rows or []
        self._scalar = scalar
        self._one = one

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return None if self._one is ... else self._one


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeReindexSession:
    """Sessão dublada: o reindex faz _get_org (Select) → SELECT pendentes (text) →
    UPDATE (×N, text) → SELECT count (text).

    A coluna pgvector não existe no SQLite, então o UPDATE/SELECT reais quebrariam.
    Roteia por TIPO de statement: o ORM `select(Organization)` do _get_org devolve a
    org real; as queries `text()` do reindex devolvem resultados canados. Conta os
    UPDATEs e exercita a orquestração (FakeEmbedder chamado em 1 lote).
    """

    def __init__(self, org, pending_rows):
        self._org = org
        self._pending = pending_rows
        self.updates = 0
        self._text_selects = 0

    async def execute(self, statement, params=None):
        from sqlalchemy.sql.elements import TextClause

        if not isinstance(statement, TextClause):
            # _get_org: select(Organization).where(slug == ...)
            return _FakeResult(one=self._org)
        sql = str(statement).strip().lower()
        if sql.startswith("update"):
            self.updates += 1
            return _FakeResult()
        # SELECTs text(): 1º = pendentes; 2º = count restante (0 após embedar todos).
        self._text_selects += 1
        if self._text_selects == 1:
            return _FakeResult(rows=self._pending)
        return _FakeResult(scalar=0)

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_reindex_orquestra_embedding_em_lote(session, org):
    pending = [_Row(id=uuid.uuid4(), text="não consigo logar"), _Row(id=uuid.uuid4(), text="caro demais")]
    fake_session = _FakeReindexSession(org, pending)
    fake_embedder = FakeEmbedder()

    async def _session_override():
        yield fake_session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_embedder_dep] = lambda: fake_embedder
    app.dependency_overrides[get_brain] = lambda: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/feedbacks/reindex", params={"limit": 200})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reindexed"] == 2
    assert body["remaining"] == 0
    assert fake_session.updates == 2            # um UPDATE por item pendente
    assert fake_embedder.calls == [["não consigo logar", "caro demais"]]  # 1 batch
