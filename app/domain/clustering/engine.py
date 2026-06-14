"""Motor do Clustering Semântico de Dores (Camada 1).

Agrupa os `feedback_items` de uma org por SIGNIFICADO (não por tag): lê os
embeddings (MiniLM 384d, L2-normalizados, já gerados pelo reindex), faz
clustering aglomerativo por cosseno e descobre DORES. Cada dor vira uma
`FeedbackCluster` com centroide, sentimento dominante e (best-effort) um rótulo
do LLM.

Princípios (docs/CLUSTERING_DORES_SPEC.md §2):
- Reusa a infra que já existe: `EmbeddingService`/`to_pgvector` e o padrão de
  query pgvector de `app/domain/knowledge/retriever.py` (SQL cru via `text()` +
  bind; NUNCA f-string em SQL). A coluna `embedding`/`centroid` é pgvector, fora
  do ORM — só tocada por SQL cru aqui.
- `dry_run=True` (default): NÃO grava nada — só relata o que faria (`ClusterReport`).
- Clustering aglomerativo O(n²) por union-find (ok p/ ~centenas de itens). Acima de
  ~2k itens, trocar por `scipy.cluster.hierarchy.linkage(method='average')` +
  `fcluster` (anotado, não implementado — manteria a dependência leve).
- Upsert idempotente: ao gravar, um cluster novo cujo centroide tem cosine >= 0.92
  com o centroide de um cluster ANTIGO da org reusa aquele cluster (estabiliza ids
  entre rodadas) em vez de criar um duplicado.
- Rotulagem LLM: 1 chamada POR cluster (não por item), best-effort (try/except
  engole; o cluster fica sem label). Só rotula clusters NOVOS ou que cresceram >20%.

NUNCA lança por causa do LLM. O SQL pgvector é Postgres-only; os testes injetam os
vetores por um hook (`load_vectors`) e nunca tocam pgvector.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Sequence

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings import EmbeddingService, to_pgvector

logger = logging.getLogger(__name__)

# Cosseno mínimo para unir dois itens no mesmo cluster (aglomerativo). Calibrado em
# 0.48 (14/06): com MiniLM (inglês) em PT, 0.75 fragmentava (16 dores p/ 27 feedbacks).
DEFAULT_THRESHOLD = 0.48
# Cosseno mínimo para REUSAR um cluster existente ao gravar (estabiliza ids).
REUSE_THRESHOLD = 0.92
# Crescimento relativo de item_count que dispara nova rotulagem LLM.
RELABEL_GROWTH = 0.20
# Quantos textos (os mais próximos do centroide) vão no prompt de rotulagem.
LABEL_SAMPLE_SIZE = 5
SENTIMENTS: tuple[str, ...] = ("positivo", "neutro", "negativo")


@dataclass
class LoadedItem:
    """Um feedback carregado para clusterização: id + vetor + metadados de texto."""

    id: uuid.UUID
    vector: np.ndarray  # float32, L2-normalizado (cosine = dot)
    sentiment: Optional[str]
    text: Optional[str]


@dataclass
class ClusterDraft:
    """Um cluster recém-computado (antes de virar/atualizar uma FeedbackCluster)."""

    member_ids: list[uuid.UUID]
    centroid: np.ndarray
    dominant_sentiment: Optional[str]
    texts: list[str]  # textos dos membros, ordenados por proximidade ao centroide

    @property
    def item_count(self) -> int:
        return len(self.member_ids)


@dataclass
class ClusterReport:
    """Resultado de uma rodada (formato do POST /api/feedbacks/cluster)."""

    evaluated: int = 0          # itens com embedding considerados
    clusters_found: int = 0     # grupos formados nesta rodada
    clusters_created: int = 0   # FeedbackCluster novas gravadas (wet run)
    clusters_updated: int = 0   # FeedbackCluster reusadas/atualizadas (wet run)
    items_assigned: int = 0     # feedback_items com cluster_id setado (wet run)
    dry_run: bool = True
    clusters: list[dict[str, Any]] = field(default_factory=list)  # preview por cluster

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "clusters_found": self.clusters_found,
            "clusters_created": self.clusters_created,
            "clusters_updated": self.clusters_updated,
            "items_assigned": self.items_assigned,
            "dry_run": self.dry_run,
            "clusters": self.clusters,
        }


# --- Carga dos vetores (SQL cru, pgvector) -----------------------------------

# Tipo do hook que carrega os vetores. Em prod, lê pgvector via SQL cru; nos
# testes, devolve vetores numpy sintéticos sem tocar o banco vetorial.
LoadVectorsFn = Callable[[AsyncSession, uuid.UUID], Awaitable[list[LoadedItem]]]


def _parse_vector(raw: Any) -> Optional[np.ndarray]:
    """pgvector chega como str '[0.1,0.2,...]' (sem codec) OU já como list. -> float32."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        arr = np.asarray(raw, dtype=np.float32)
    elif isinstance(raw, str):
        s = raw.strip().lstrip("[").rstrip("]")
        if not s:
            return None
        try:
            arr = np.asarray([float(x) for x in s.split(",")], dtype=np.float32)
        except ValueError:
            return None
    else:
        return None
    return arr if arr.size else None


async def load_items_from_db(session: AsyncSession, org_id: uuid.UUID) -> list[LoadedItem]:
    """Carga real (Postgres): feedback_items da org com embedding != NULL.

    SQL cru de propósito (a coluna `embedding` é pgvector, fora do ORM). Cast do
    UUID para texto no bind, igual ao retriever do RAG.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT id, embedding, sentiment, text
                FROM feedback_items
                WHERE organization_id = :org AND embedding IS NOT NULL
                """
            ),
            {"org": str(org_id)},
        )
    ).all()
    out: list[LoadedItem] = []
    for r in rows:
        vec = _parse_vector(r.embedding)
        if vec is None:
            continue
        out.append(LoadedItem(id=r.id, vector=vec, sentiment=r.sentiment, text=r.text))
    return out


# --- Clustering aglomerativo por cosseno (union-find, O(n²)) ------------------


def _normalize(vec: np.ndarray) -> np.ndarray:
    """Renormaliza L2 (defensivo: o reindex já normaliza, mas a média do centroide não)."""
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def _dominant_sentiment(sentiments: Sequence[Optional[str]]) -> Optional[str]:
    """Sentimento mais frequente entre os membros (ignora None). Empate: 'negativo' pesa mais."""
    counts = Counter(s for s in sentiments if s)
    if not counts:
        return None
    top = max(counts.values())
    tied = [s for s, n in counts.items() if n == top]
    if len(tied) == 1:
        return tied[0]
    # Desempate: prioriza o sinal mais acionável (negativo > neutro > positivo).
    for pref in ("negativo", "neutro", "positivo"):
        if pref in tied:
            return pref
    return tied[0]


def _agglomerate(items: list[LoadedItem], threshold: float) -> list[ClusterDraft]:
    """Une itens por cosseno >= threshold (vetores já normalizados → dot = cosine).

    Union-find O(n²): para cada par (i<j), se sim(i,j) >= threshold, une os grupos.
    Retorna os clusters com centroide (média renormalizada), sentimento dominante e
    os textos dos membros ordenados por proximidade ao centroide (para o prompt).
    """
    n = len(items)
    if n == 0:
        return []

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    matrix = np.vstack([it.vector for it in items]).astype(np.float32)  # (n, 384)
    # Similaridade par-a-par numa tacada (cosine = dot, pois L2-normalizados).
    sims = matrix @ matrix.T
    for i in range(n):
        row = sims[i]
        for j in range(i + 1, n):
            if row[j] >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)

    drafts: list[ClusterDraft] = []
    for members in groups.values():
        sub = matrix[members]
        centroid = _normalize(sub.mean(axis=0))
        # Ordena membros por proximidade ao centroide (os mais representativos primeiro).
        proximity = sub @ centroid
        order = np.argsort(-proximity)
        ordered_members = [members[k] for k in order]
        member_ids = [items[m].id for m in ordered_members]
        sentiments = [items[m].sentiment for m in ordered_members]
        texts = [items[m].text for m in ordered_members if (items[m].text or "").strip()]
        drafts.append(
            ClusterDraft(
                member_ids=member_ids,
                centroid=centroid,
                dominant_sentiment=_dominant_sentiment(sentiments),
                texts=texts,
            )
        )
    # Maiores dores primeiro (mais itens = sinal mais forte).
    drafts.sort(key=lambda d: d.item_count, reverse=True)
    return drafts


def _agglomerate_by_sentiment(items: list[LoadedItem], threshold: float) -> list[ClusterDraft]:
    """Aglomera SEPARANDO por sentimento — uma dor não mistura elogio com crítica.

    O embedding (MiniLM, treinado em inglês) captura o TÓPICO em português mas erra a
    nuance de sentimento; sem separar, "gostei da plataforma" e "plataforma complicada"
    cairiam no mesmo balde só por "plataforma". Particiona por sentimento (None = balde
    próprio) e aglomera cada partição isoladamente.
    """
    buckets: dict[Optional[str], list[LoadedItem]] = {}
    for it in items:
        buckets.setdefault(it.sentiment, []).append(it)
    drafts: list[ClusterDraft] = []
    for group in buckets.values():
        drafts.extend(_agglomerate(group, threshold))
    drafts.sort(key=lambda d: d.item_count, reverse=True)
    return drafts


# --- Rotulagem via LLM (best-effort, 1 chamada/cluster) ----------------------


async def _label_cluster(llm: Any, draft: ClusterDraft) -> Optional[dict[str, Any]]:
    """Pede ao LLM {label, description, dominant_sentiment} a partir de top-N textos.

    Best-effort total: qualquer falha (sem llm, exceção, parse) -> None, e o cluster
    fica sem rótulo. Usa `chat_json` (JSON-mode) se disponível; senão `complete`.
    """
    if llm is None:
        return None
    sample = [t.strip() for t in draft.texts[:LABEL_SAMPLE_SIZE] if (t or "").strip()]
    if not sample:
        return None
    bullets = "\n".join(f"- {t[:280]}" for t in sample)
    system = (
        "Você analisa feedbacks de clientes e nomeia a DOR comum a um grupo. "
        "Responda SEMPRE em português do Brasil, em JSON."
    )
    user = (
        "Abaixo estão feedbacks de clientes que falam da MESMA dor/assunto. "
        "Resuma a dor comum a todos.\n\n"
        f"{bullets}\n\n"
        'Responda em JSON com as chaves: "label" (título curto da dor, até 6 palavras), '
        '"description" (1 frase explicando a dor) e "dominant_sentiment" '
        '(um de: positivo, neutro, negativo).'
    )
    try:
        data: Optional[dict[str, Any]] = None
        if hasattr(llm, "chat_json"):
            data = await llm.chat_json(system, user, temperature=0.2, max_tokens=200)
        elif hasattr(llm, "complete"):
            raw = await llm.complete(user, system=system, max_tokens=200)
            data = json.loads(raw) if raw else None
        if not isinstance(data, dict):
            return None
        label = (str(data.get("label")).strip() or None) if data.get("label") else None
        description = (str(data.get("description")).strip() or None) if data.get("description") else None
        sent = data.get("dominant_sentiment")
        sent = sent if sent in SENTIMENTS else None
        if label is None and description is None:
            return None
        return {"label": label, "description": description, "dominant_sentiment": sent}
    except Exception:  # noqa: BLE001 — rotulagem nunca derruba a rodada.
        logger.warning("clustering: falha ao rotular cluster via LLM", exc_info=True)
        return None


# --- Persistência (wet run): upsert + atribuição -----------------------------


@dataclass
class _ExistingCluster:
    id: uuid.UUID
    centroid: Optional[np.ndarray]
    item_count: int


async def _load_existing_clusters(session: AsyncSession, org_id: uuid.UUID) -> list[_ExistingCluster]:
    """Clusters já gravados da org (id, centroide, item_count) para reuso/estabilidade."""
    rows = (
        await session.execute(
            text(
                """
                SELECT id, centroid, item_count
                FROM feedback_clusters
                WHERE organization_id = :org
                """
            ),
            {"org": str(org_id)},
        )
    ).all()
    out: list[_ExistingCluster] = []
    for r in rows:
        out.append(
            _ExistingCluster(
                id=r.id,
                centroid=_parse_vector(r.centroid),
                item_count=int(r.item_count or 0),
            )
        )
    return out


def _best_reuse(
    draft_centroid: np.ndarray, existing: list[_ExistingCluster], used: set[uuid.UUID]
) -> Optional[_ExistingCluster]:
    """Cluster antigo (ainda não reusado) com cosine >= REUSE_THRESHOLD mais alto."""
    best: Optional[_ExistingCluster] = None
    best_sim = REUSE_THRESHOLD
    for ex in existing:
        if ex.id in used or ex.centroid is None:
            continue
        sim = float(np.dot(draft_centroid, ex.centroid))
        if sim >= best_sim:
            best_sim = sim
            best = ex
    return best


async def _persist(
    session: AsyncSession,
    org_id: uuid.UUID,
    drafts: list[ClusterDraft],
    *,
    llm: Any,
    now: datetime,
    report: ClusterReport,
) -> None:
    """Grava os clusters (upsert + atribuição dos feedback_items). Wet run only."""
    existing = await _load_existing_clusters(session, org_id)
    used: set[uuid.UUID] = set()

    for draft in drafts:
        reuse = _best_reuse(draft.centroid, existing, used)
        grew = True
        if reuse is not None:
            used.add(reuse.id)
            cluster_id = reuse.id
            # Cresceu >20%? (dispara nova rotulagem). Base 0 => sempre rotula.
            grew = draft.item_count > reuse.item_count * (1.0 + RELABEL_GROWTH) or reuse.item_count == 0
            report.clusters_updated += 1
        else:
            cluster_id = uuid.uuid4()
            report.clusters_created += 1

        labels = await _label_cluster(llm, draft) if grew else None

        centroid_literal = to_pgvector(draft.centroid.tolist())
        if reuse is None:
            await session.execute(
                text(
                    """
                    INSERT INTO feedback_clusters
                        (id, organization_id, label, description, dominant_sentiment,
                         item_count, centroid, created_at, updated_at)
                    VALUES
                        (:id, :org, :label, :description, :sentiment,
                         :count, CAST(:centroid AS vector), :now, :now)
                    """
                ),
                {
                    "id": str(cluster_id),
                    "org": str(org_id),
                    "label": (labels or {}).get("label"),
                    "description": (labels or {}).get("description"),
                    "sentiment": (labels or {}).get("dominant_sentiment") or draft.dominant_sentiment,
                    "count": draft.item_count,
                    "centroid": centroid_literal,
                    "now": now,
                },
            )
        else:
            # Atualiza centroide/contagem/sentimento; só sobrescreve label/description
            # se o LLM rotulou de novo (cluster cresceu) — senão preserva o que havia.
            sets = [
                "centroid = CAST(:centroid AS vector)",
                "item_count = :count",
                "dominant_sentiment = :sentiment",
                "updated_at = :now",
            ]
            params: dict[str, Any] = {
                "id": str(cluster_id),
                "org": str(org_id),
                "centroid": centroid_literal,
                "count": draft.item_count,
                "sentiment": (labels or {}).get("dominant_sentiment") or draft.dominant_sentiment,
                "now": now,
            }
            if labels is not None and (labels.get("label") or labels.get("description")):
                sets.append("label = :label")
                sets.append("description = :description")
                params["label"] = labels.get("label")
                params["description"] = labels.get("description")
            await session.execute(
                text(
                    f"UPDATE feedback_clusters SET {', '.join(sets)} "
                    "WHERE id = :id AND organization_id = :org"
                ),
                params,
            )

        # Atribui os feedback_items ao cluster (cluster_id está no ORM, mas usamos SQL
        # cru por uniformidade e para o IN (...) por id ser explícito).
        for mid in draft.member_ids:
            await session.execute(
                text("UPDATE feedback_items SET cluster_id = :cid WHERE id = :id AND organization_id = :org"),
                {"cid": str(cluster_id), "id": str(mid), "org": str(org_id)},
            )
        report.items_assigned += draft.item_count


# --- Orquestrador ------------------------------------------------------------


async def run_clustering(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    embedder: EmbeddingService,
    llm: Any = None,
    threshold: float = DEFAULT_THRESHOLD,
    dry_run: bool = True,
    now: Optional[datetime] = None,
    load_vectors: Optional[LoadVectorsFn] = None,
) -> ClusterReport:
    """Roda o clustering de dores da org e devolve um ClusterReport.

    - `embedder`: presente por simetria com o resto do domínio (os vetores já estão
      gravados; reservado para futura geração on-the-fly). Não é usado na carga atual.
    - `llm`: rotulador best-effort (`chat_json`/`complete`). None = clusters sem rótulo.
    - `threshold`: cosseno mínimo para unir itens (default 0.48; aglomera por sentimento).
    - `dry_run=True` (default): NÃO grava nada — só relata.
    - `load_vectors`: hook de carga dos vetores (default: pgvector real). Os testes
      injetam vetores sintéticos por aqui, sem tocar o banco vetorial.
    """
    now = now or datetime.now(timezone.utc)
    report = ClusterReport(dry_run=dry_run)

    loader = load_vectors or load_items_from_db
    items = await loader(session, org_id)
    report.evaluated = len(items)
    if not items:
        return report

    drafts = _agglomerate_by_sentiment(items, threshold)
    report.clusters_found = len(drafts)

    # Preview por cluster (rótulo só é chamado no wet run, para não gastar LLM no dry).
    for d in drafts:
        report.clusters.append(
            {
                "item_count": d.item_count,
                "dominant_sentiment": d.dominant_sentiment,
                "sample_texts": d.texts[:3],
            }
        )

    if dry_run:
        return report

    await _persist(session, org_id, drafts, llm=llm, now=now, report=report)
    await session.commit()
    return report
