"""Engine e sessão async (SQLAlchemy 2.0).

A URL vem de DATABASE_URL (Supabase, postgresql+asyncpg). Os testes de integração
NÃO usam este módulo — eles criam um engine SQLite in-memory próprio no conftest.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Engine só é criado se houver DATABASE_URL (evita estourar import em dev/CI).
engine = (
    create_async_engine(settings.database_url, pool_pre_ping=True)
    if settings.database_url
    else None
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency do FastAPI: cede uma AsyncSession por request."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL não configurada — não há engine de banco.")
    async with SessionLocal() as session:
        yield session
