"""Ingestão do corpus de conhecimento → knowledge_chunks (pgvector).

Lê os .md de docs/corpus_bizzu/ (ou --dir), quebra cada um em chunks por seção
(chunk_markdown), gera embeddings locais (all-MiniLM-L6-v2) e faz upsert na
tabela knowledge_chunks da org (default: bizzu).

Idempotente por (org, source=arquivo): re-ingerir um arquivo apaga os chunks
antigos daquele arquivo e reinsere — editar o corpus e rodar de novo converge.

Uso:
    py scripts/ingest_knowledge.py [--dir docs/corpus_bizzu] [--org bizzu] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:
    pass

DEFAULT_DIR = os.path.join("docs", "corpus_bizzu")


async def ingest(corpus_dir: str, org_slug: str, dry_run: bool) -> int:
    import glob

    from sqlalchemy import select, text
    from app.db import SessionLocal
    from app.domain.knowledge.chunking import chunk_markdown
    from app.models.core import Organization
    from app.services.embeddings import get_embedder, to_pgvector

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada.", file=sys.stderr)
        return 1

    files = sorted(glob.glob(os.path.join(_PROJECT_ROOT, corpus_dir, "*.md")))
    if not files:
        print(f"ERRO: nenhum .md em {corpus_dir}", file=sys.stderr)
        return 1

    # Quebra todos os arquivos em chunks (lógica pura).
    per_file: list[tuple[str, list]] = []
    total_chunks = 0
    for path in files:
        source = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            chunks = chunk_markdown(fh.read())
        per_file.append((source, chunks))
        total_chunks += len(chunks)
        print(f"  {source}: {len(chunks)} chunk(s)")

    print(f"Total: {total_chunks} chunk(s) de {len(files)} arquivo(s)")
    if dry_run:
        print("=== DRY-RUN: nada gravado ===")
        return 0

    embedder = get_embedder()

    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if org is None:
            print(f"ERRO: org '{org_slug}' não existe (rode o seed).", file=sys.stderr)
            return 1

        inserted = 0
        for source, chunks in per_file:
            # Re-ingest idempotente: zera os chunks anteriores deste arquivo.
            await session.execute(
                text(
                    "DELETE FROM knowledge_chunks "
                    "WHERE organization_id = :org AND source = :src"
                ),
                {"org": str(org.id), "src": source},
            )
            if not chunks:
                continue
            vectors = await embedder.embed([c.content for c in chunks])
            for chunk, vec in zip(chunks, vectors):
                await session.execute(
                    text(
                        """
                        INSERT INTO knowledge_chunks
                            (organization_id, source, title, content, chunk_metadata, embedding)
                        VALUES
                            (:org, :src, :title, :content, CAST(:meta AS jsonb), CAST(:emb AS vector))
                        """
                    ),
                    {
                        "org": str(org.id),
                        "src": source,
                        "title": chunk.title,
                        "content": chunk.content,
                        "meta": _json_tags(chunk.tags),
                        "emb": to_pgvector(vec),
                    },
                )
                inserted += 1
        await session.commit()

    print(f"=== Ingest concluído: {inserted} chunk(s) gravados na org '{org_slug}' ===")
    return 0


def _json_tags(tags: list[str]) -> str:
    import json

    return json.dumps({"tags": tags}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestão do corpus → knowledge_chunks (RAG).")
    parser.add_argument("--dir", default=DEFAULT_DIR, help="diretório do corpus (.md)")
    parser.add_argument("--org", default="bizzu", help="slug da organização")
    parser.add_argument("--dry-run", action="store_true", help="só conta chunks, não grava")
    args = parser.parse_args(argv)
    return asyncio.run(ingest(args.dir, args.org, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
