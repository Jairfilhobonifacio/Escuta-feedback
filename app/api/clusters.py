"""API do Clustering Semântico de Dores (Camada 1) — /api/feedbacks/*.

Mesmo padrão do painel (admin.py/playbooks.py): org única pelo slug default via
`_get_org`, `Depends(get_session)`, schemas Pydantic inline, serializer `_out`.

O embedder é injetável (`get_embedder_dep`) para os testes stubarem a geração de
embeddings sem carregar o MiniLM nem tocar a rede. Todo SQL pgvector (coluna
`embedding`/`centroid`, fora do ORM) sai por `text()` + bind — nunca f-string.

- POST  /api/feedbacks/reindex?limit=200        → {reindexed, remaining}
- POST  /api/feedbacks/cluster?dry_run=true     → ClusterReport
- GET   /api/feedbacks/clusters?days=&sort=     → {clusters, total_items_clustered, total_unclustered}
- GET   /api/feedbacks/clusters/{id}            → {cluster, items:[até 50]}
- PATCH /api/feedbacks/clusters/{id}            → ClusterOut (operador corrige label/description)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _feedback_out, _get_org, get_brain
from app.config import settings
from app.db import get_session
from app.domain.clustering.engine import run_clustering
from app.domain.prioridade import peso_pagante, priority_index
from app.domain.survey.brain import SurveyBrain
from app.models.cluster import FeedbackCluster
from app.models.core import Contact
from app.models.feedback import FeedbackItem
from app.services.embeddings import EmbeddingService, get_embedder, to_pgvector

router = APIRouter(tags=["clusters"])


def get_embedder_dep() -> EmbeddingService:
    """Encoder local (MiniLM). Substituível via dependency_overrides nos testes."""
    return get_embedder()


def _llm_from_brain(brain: SurveyBrain | None) -> Any:
    """Extrai o cliente LLM cru do SurveyBrain (o engine usa chat_json/complete).

    Reusa a MESMA injeção do resto do painel (`get_brain`): com a Groq off/sem chave
    o brain é None → clustering roda sem rotulagem (best-effort). Os testes injetam
    um FakeLLM por aqui (override de get_brain) sem tocar a Groq.
    """
    if brain is None:
        return None
    # SurveyBrain guarda o cliente Groq em .llm (ver app/domain/survey/brain.py).
    return getattr(brain, "llm", None) or brain


# --- POST /api/feedbacks/reindex ---------------------------------------------


@router.post("/feedbacks/reindex")
async def reindex_feedbacks(
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
    embedder: EmbeddingService = Depends(get_embedder_dep),
) -> dict[str, Any]:
    """Gera embeddings (MiniLM 384d) para feedback_items sem `embedding` ainda.

    Lote: pega até `limit` itens da org com `embedding IS NULL AND text IS NOT NULL`,
    embeda em batch e grava por SQL cru (`CAST(:v AS vector)`). Best-effort por item:
    uma falha de gravação não derruba o lote. Retorna {reindexed, remaining}.

    Pode ser chamado por um cron externo (igual ao /api/digest/run) até `remaining=0`.
    """
    org = await _get_org(session)
    limit = max(1, min(int(limit), 1000))

    rows = (
        await session.execute(
            text(
                """
                SELECT id, text
                FROM feedback_items
                WHERE organization_id = :org AND embedding IS NULL AND text IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"org": str(org.id), "lim": limit},
        )
    ).all()

    pending = [(r.id, r.text) for r in rows if (r.text or "").strip()]
    reindexed = 0
    if pending:
        vectors = await embedder.embed([t for _, t in pending])
        for (item_id, _), vec in zip(pending, vectors):
            try:
                await session.execute(
                    text(
                        "UPDATE feedback_items SET embedding = CAST(:v AS vector) "
                        "WHERE id = :id AND organization_id = :org"
                    ),
                    {"v": to_pgvector(vec), "id": str(item_id), "org": str(org.id)},
                )
                reindexed += 1
            except Exception:  # noqa: BLE001 — best-effort por item; não derruba o lote.
                continue
        await session.commit()

    remaining = (
        await session.execute(
            text(
                "SELECT count(*) FROM feedback_items "
                "WHERE organization_id = :org AND embedding IS NULL AND text IS NOT NULL"
            ),
            {"org": str(org.id)},
        )
    ).scalar_one()

    return {"reindexed": reindexed, "remaining": int(remaining)}


# --- POST /api/feedbacks/cluster ---------------------------------------------


@router.post("/feedbacks/cluster")
async def cluster_feedbacks(
    dry_run: bool = True,
    threshold: float = 0.75,
    session: AsyncSession = Depends(get_session),
    embedder: EmbeddingService = Depends(get_embedder_dep),
    brain: SurveyBrain | None = Depends(get_brain),
) -> dict[str, Any]:
    """Roda o motor de clustering da org. `dry_run=true` (default) NÃO grava nada.

    Com `dry_run=false`, grava/atualiza `feedback_clusters` (reusa cluster antigo por
    cosseno >= 0.92), atribui `cluster_id` aos itens e rotula via LLM (best-effort).
    """
    org = await _get_org(session)
    report = await run_clustering(
        session,
        org.id,
        embedder=embedder,
        llm=_llm_from_brain(brain),
        threshold=threshold,
        dry_run=dry_run,
    )
    return report.as_dict()


# --- GET /api/feedbacks/clusters ---------------------------------------------


def _priority_weights() -> dict[str, float]:
    """Pesos do índice de prioridade a partir de `config` (transparentes/ajustáveis)."""
    return {
        "volume": settings.priority_weight_volume,
        "revenue": settings.priority_weight_revenue,
        "gravity": settings.priority_weight_gravity,
        "volume_ref": settings.priority_volume_ref,
        "plano_alto_mult": settings.priority_plano_alto_mult,
    }


def _cluster_out(
    c: FeedbackCluster,
    neg_count: int,
    top_themes: list[str],
    counts: tuple[int, int, float] | None = None,
) -> dict[str, Any]:
    """Serializa uma dor. `pain_score = item_count * neg_fraction` (0..item_count).

    `counts` = (distinct_customers, paying_customers, paying_weighted) agregados pelo
    endpoint (ver `_customer_counts_by_cluster`); None = cluster sem itens/contatos
    (tudo 0). ADITIVO: `pain_score` permanece para back-compat; os campos do índice de
    prioridade (`distinct_customers`, `paying_customers`, `priority_index`,
    `priority_band`, `priority_breakdown`) são novos. O índice sai da função pura
    `app/domain/prioridade.py` com os pesos de `config` (§2.3).
    """
    item_count = int(c.item_count or 0)
    neg_fraction = (neg_count / item_count) if item_count else 0.0

    distinct_customers, paying_customers, paying_weighted = counts or (0, 0, 0.0)
    prioridade = priority_index(
        distinct_customers=distinct_customers,
        paying_weighted=paying_weighted,
        neg_count=int(neg_count),
        item_count=item_count,
        weights=_priority_weights(),
    )
    return {
        "id": str(c.id),
        "label": c.label,
        "description": c.description,
        "dominant_sentiment": c.dominant_sentiment,
        "item_count": item_count,
        "neg_count": int(neg_count),
        "pain_score": round(item_count * neg_fraction, 2),
        "top_themes": top_themes,
        "improvement_id": str(c.improvement_id) if c.improvement_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        # --- Índice de prioridade (aditivo, §2.3) ---
        "distinct_customers": int(distinct_customers),
        "paying_customers": int(paying_customers),
        "priority_index": prioridade["priority_index"],
        "priority_band": prioridade["priority_band"],
        "priority_breakdown": prioridade["breakdown"],
    }


async def _neg_counts_by_cluster(
    session: AsyncSession, org_id: uuid.UUID, cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Nº de feedback_items com sentiment='negativo' por cluster (para pain_score)."""
    if not cluster_ids:
        return {}
    rows = (
        await session.execute(
            select(FeedbackItem.cluster_id, func.count())
            .where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.cluster_id.in_(cluster_ids),
                FeedbackItem.sentiment == "negativo",
            )
            .group_by(FeedbackItem.cluster_id)
        )
    ).all()
    return {cid: int(n) for cid, n in rows}


async def _customer_counts_by_cluster(
    session: AsyncSession, org_id: uuid.UUID, cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int, float]]:
    """Por cluster: (clientes distintos, pagantes, peso de receita) — UMA query.

    Volume conta CLIENTES DISTINTOS (`contact_id`), não itens: 3 feedbacks do mesmo
    cliente contam 1. "Pagante" e o peso (anual pesa mais) saem do snapshot
    `partner` (`Contact.profile_data["partner"]`), lido em Python — `peso_pagante`
    é a regra canônica (`app/domain/prioridade.py`). Molde = `_neg_counts_by_cluster`:
    1 SELECT agregado, agrupamento em Python (partner é JSON, fora do alcance do SQL).

    Itens sem `contact_id` não entram no volume (não há cliente para contar).
    """
    if not cluster_ids:
        return {}
    rows = (
        await session.execute(
            select(FeedbackItem.cluster_id, FeedbackItem.contact_id, Contact.profile_data)
            .join(Contact, Contact.id == FeedbackItem.contact_id)
            .where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.cluster_id.in_(cluster_ids),
                FeedbackItem.contact_id.is_not(None),
            )
        )
    ).all()

    mult = settings.priority_plano_alto_mult
    # Dedup por (cluster, contato): cada cliente conta UMA vez, com o peso do seu partner.
    seen: dict[uuid.UUID, dict[uuid.UUID, float]] = {}
    for cid, contact_id, profile_data in rows:
        if cid is None or contact_id is None:
            continue
        by_contact = seen.setdefault(cid, {})
        if contact_id in by_contact:
            continue
        partner = (profile_data or {}).get("partner") if isinstance(profile_data, dict) else None
        by_contact[contact_id] = peso_pagante(partner, plano_alto_mult=mult)

    out: dict[uuid.UUID, tuple[int, int, float]] = {}
    for cid, by_contact in seen.items():
        pesos = list(by_contact.values())
        distinct = len(pesos)
        paying = sum(1 for w in pesos if w > 0)
        weighted = float(sum(pesos))
        out[cid] = (distinct, paying, weighted)
    return out


async def _themes_by_cluster(
    session: AsyncSession, org_id: uuid.UUID, cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Top temas (tags) mais frequentes por cluster — feito em Python (themes é JSON).

    Cruza a dor (por significado) com as tags antigas, para a UI mostrar o overlap.
    """
    if not cluster_ids:
        return {}
    rows = (
        await session.execute(
            select(FeedbackItem.cluster_id, FeedbackItem.themes).where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.cluster_id.in_(cluster_ids),
            )
        )
    ).all()
    from collections import Counter

    counters: dict[uuid.UUID, Counter] = {}
    for cid, themes in rows:
        if not isinstance(themes, list):
            continue
        c = counters.setdefault(cid, Counter())
        for th in themes:
            if isinstance(th, str) and th.strip():
                c[th.strip()] += 1
    return {cid: [t for t, _ in c.most_common(5)] for cid, c in counters.items()}


@router.get("/feedbacks/clusters")
async def list_clusters(
    days: int | None = 30,
    sort: Literal["prioridade", "dor", "volume", "recente"] = "prioridade",
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Lista as dores (clusters) da org + métricas para a aba "Por significado".

    `days`: só clusters criados/atualizados nos últimos N dias (None/0 = todos).
    `sort`: `prioridade` (priority_index desc, DEFAULT) | `dor` (pain_score desc) |
            `volume` (item_count desc) | `recente` (created desc).
    Inclui `total_items_clustered` e `total_unclustered` (itens com text e sem cluster).
    """
    org = await _get_org(session)

    stmt = select(FeedbackCluster).where(FeedbackCluster.organization_id == org.id)
    if days and int(days) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
        stmt = stmt.where(
            func.coalesce(FeedbackCluster.updated_at, FeedbackCluster.created_at) >= cutoff
        )
    clusters = (await session.execute(stmt)).scalars().all()

    cluster_ids = [c.id for c in clusters]
    neg_counts = await _neg_counts_by_cluster(session, org.id, cluster_ids)
    themes = await _themes_by_cluster(session, org.id, cluster_ids)
    customer_counts = await _customer_counts_by_cluster(session, org.id, cluster_ids)

    out = [
        _cluster_out(
            c, neg_counts.get(c.id, 0), themes.get(c.id, []), customer_counts.get(c.id)
        )
        for c in clusters
    ]

    if sort == "volume":
        out.sort(key=lambda x: x["item_count"], reverse=True)
    elif sort == "recente":
        out.sort(key=lambda x: x["created_at"] or "", reverse=True)
    elif sort == "dor":  # pain_score desc, empate por volume
        out.sort(key=lambda x: (x["pain_score"], x["item_count"]), reverse=True)
    else:  # prioridade (default): priority_index desc, empate por volume de clientes
        out.sort(key=lambda x: (x["priority_index"], x["distinct_customers"]), reverse=True)

    total_clustered = (
        await session.execute(
            select(func.count()).where(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.cluster_id.is_not(None),
            )
        )
    ).scalar_one()
    total_unclustered = (
        await session.execute(
            select(func.count()).where(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.cluster_id.is_(None),
                FeedbackItem.text.is_not(None),
            )
        )
    ).scalar_one()

    return {
        "clusters": out,
        "total_items_clustered": int(total_clustered),
        "total_unclustered": int(total_unclustered),
    }


# --- GET /api/feedbacks/clusters/{id} ----------------------------------------


@router.get("/feedbacks/clusters/{cluster_id}")
async def get_cluster(
    cluster_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Detalhe de uma dor + até 50 feedbacks dela (no MESMO formato do feed)."""
    org = await _get_org(session)
    try:
        cid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    c = (
        await session.execute(
            select(FeedbackCluster).where(
                FeedbackCluster.id == cid, FeedbackCluster.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="cluster não encontrado")

    neg = (await _neg_counts_by_cluster(session, org.id, [cid])).get(cid, 0)
    themes = (await _themes_by_cluster(session, org.id, [cid])).get(cid, [])
    counts = (await _customer_counts_by_cluster(session, org.id, [cid])).get(cid)

    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(FeedbackItem, Contact)
            .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
            .where(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.cluster_id == cid,
            )
            .order_by(
                func.coalesce(FeedbackItem.occurred_at, FeedbackItem.created_at).desc()
            )
            .limit(50)
        )
    ).all()
    items = [_feedback_out(f, ct, now) for f, ct in rows]

    return {"cluster": _cluster_out(c, neg, themes, counts), "items": items}


# --- PATCH /api/feedbacks/clusters/{id} --------------------------------------


class ClusterPatchIn(BaseModel):
    """Correção manual do operador. `model_fields_set` distingue não-enviado de null."""

    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


@router.patch("/feedbacks/clusters/{cluster_id}")
async def update_cluster(
    cluster_id: str, body: ClusterPatchIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Operador corrige o rótulo/descrição da dor. Só toca o que vier no corpo."""
    org = await _get_org(session)
    try:
        cid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    c = (
        await session.execute(
            select(FeedbackCluster).where(
                FeedbackCluster.id == cid, FeedbackCluster.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="cluster não encontrado")

    sent = body.model_fields_set
    if "label" in sent:
        c.label = (body.label.strip() or None) if body.label else None
    if "description" in sent:
        c.description = (body.description.strip() or None) if body.description else None

    await session.commit()
    await session.refresh(c)

    neg = (await _neg_counts_by_cluster(session, org.id, [cid])).get(cid, 0)
    themes = (await _themes_by_cluster(session, org.id, [cid])).get(cid, [])
    counts = (await _customer_counts_by_cluster(session, org.id, [cid])).get(cid)
    return _cluster_out(c, neg, themes, counts)
