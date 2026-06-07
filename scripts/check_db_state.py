"""Diagnóstico rápido do estado do banco (go-live Fase 0). Não imprime segredos."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


async def main() -> None:
    load_env()
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, echo=False)
    async with engine.connect() as conn:
        tables = (await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
        ))).scalars().all()
        print(f"Tabelas public: {', '.join(tables) or '(nenhuma)'}")
        for t in tables:
            if t == "alembic_version":
                ver = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                print(f"  alembic_version: {ver}")
                continue
            n = (await conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))).scalar()
            print(f"  {t}: {n} linhas")
        orgs = (await conn.execute(text(
            "SELECT slug, name FROM organizations ORDER BY created_at"
        ))).all() if "organizations" in tables else []
        for slug, name in orgs:
            print(f"  org: {slug} ({name})")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
