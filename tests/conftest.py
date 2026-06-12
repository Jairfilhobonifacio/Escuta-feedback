"""Fixtures de integração — engine SQLite in-memory async (sem Supabase).

Cria um engine `sqlite+aiosqlite:///:memory:`, roda `Base.metadata.create_all`
(via `conn.run_sync`) e cede uma `AsyncSession` limpa por teste.

IMPORTANTE: importamos `app.models.core` e `app.models.survey` ANTES do
create_all para registrar as tabelas no metadata da Base. Adicionamos a raiz do
repo ao sys.path para que `import app...` funcione rodando standalone ou via pytest.
"""
from __future__ import annotations

import os
import sys

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Permite rodar standalone / sem instalar o pacote.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.models.base import Base  # noqa: E402
# Importa os models para registrar as tabelas no Base.metadata antes do create_all.
import app.models.core  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401
import app.models.feedback  # noqa: E402,F401


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Engine SQLite in-memory + schema criado; cede uma AsyncSession por teste."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            yield s
    finally:
        await engine.dispose()
