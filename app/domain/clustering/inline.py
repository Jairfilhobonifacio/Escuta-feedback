"""Geração INLINE de embedding no write-path (Camada 1), fire-and-forget.

Atrás da flag `CLUSTERING_INLINE_ENABLED` (default OFF). Quando ON, o `create_feedback`
(e, no futuro, a ingestão de eventos) agenda — DEPOIS do commit — um
`asyncio.create_task(embed_feedback_item_bg(...))` que abre uma sessão NOVA, gera o
embedding (MiniLM, offline) e grava por SQL cru. Best-effort total: qualquer falha é
engolida (log) e NUNCA afeta a resposta do endpoint, que já respondeu 201.

Usa o `SessionLocal` do app (Postgres real) — por isso é no-op se não houver
DATABASE_URL (ex.: testes), o que mantém os testes longe de embeddings/pgvector.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from app.services.embeddings import get_embedder, to_pgvector

logger = logging.getLogger(__name__)


async def embed_feedback_item_bg(item_id: uuid.UUID, org_id: uuid.UUID, content: str) -> None:
    """Gera+grava o embedding de UM feedback numa sessão nova. Nunca lança."""
    try:
        content = (content or "").strip()
        if not content:
            return
        # Import tardio para evitar ciclo e respeitar DATABASE_URL ausente nos testes.
        from app.db import SessionLocal

        if SessionLocal is None:
            return
        vec = await get_embedder().embed_one(content)
        async with SessionLocal() as session:
            await session.execute(
                text(
                    "UPDATE feedback_items SET embedding = CAST(:v AS vector) "
                    "WHERE id = :id AND organization_id = :org AND embedding IS NULL"
                ),
                {"v": to_pgvector(vec), "id": str(item_id), "org": str(org_id)},
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — inline best-effort; nunca derruba o write-path.
        logger.warning("clustering inline: falha ao gerar embedding do feedback %s", item_id, exc_info=True)


def maybe_schedule_embed(item_id: uuid.UUID, org_id: uuid.UUID, content: str | None) -> None:
    """Agenda o embed em background SE a flag estiver ON. No-op se OFF/sem texto.

    Síncrono e à prova de queda: cria a task e retorna na hora (fire-and-forget).
    """
    from app.config import settings  # tardio: lê o estado atual da flag

    if not settings.clustering_inline_enabled:
        return
    if not (content or "").strip():
        return
    try:
        import asyncio

        asyncio.create_task(embed_feedback_item_bg(item_id, org_id, content or ""))
    except RuntimeError:
        # Sem event loop rodando (contexto não-async) — ignora silenciosamente.
        logger.debug("clustering inline: sem event loop para agendar embedding")
