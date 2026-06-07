"""Base declarativa do SQLAlchemy 2.0 (async) + tipos portáveis.

Os tipos são escolhidos para renderizar nativo no Postgres (Supabase) e ainda
funcionar em SQLite (testes de integração sem precisar do banco real):
- `Uuid` genérico → UUID nativo no PG, CHAR(32) no SQLite.
- `JSONVariant` → JSONB no PG, JSON genérico nos demais.
- `Mapped[datetime]` → timestamptz (igual à migration); sem isso o bind compila
  como TIMESTAMP WITHOUT TIME ZONE e o asyncpg rejeita datetimes aware (UTC)
  que o domínio usa (`datetime.now(timezone.utc)`).
Defaults de PK ficam no lado Python (`default=uuid.uuid4`) para o create_all dos
testes funcionar; o `server_default gen_random_uuid()` mora só na migration (PG).
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB

# JSONB no Postgres; JSON genérico nos demais dialetos (ex.: SQLite nos testes).
JSONVariant = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """Base comum a todos os models."""

    type_annotation_map = {
        # Alinha o ORM à migration (colunas timestamptz) — ver docstring acima.
        datetime: DateTime(timezone=True),
    }
