"""Models base (espelham o Nexus, subconjunto mínimo da Fase 0).

Tipos portáveis (PG + SQLite) — ver app/models/base.py. Na Fase 1 expandimos com
a cópia completa de `app/services/database.py` do Nexus (Message, WhatsAppChannel…).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    settings: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("organization_id", "phone", name="uq_contact_org_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    phone: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_data: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # Hand-off humano: quando True, o bot PARA de automatizar este contato
    # (um humano assume a conversa pelo WhatsApp). Limpar p/ devolver ao bot.
    needs_human_handoff: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class User(Base):
    """Operador/membro da equipe com acesso ao painel Escuta.

    Coexiste com o operador único via ENV (ESCUTA_OPERATOR_USER +
    ESCUTA_OPERATOR_PASSWORD_HASH) para backward-compat. Login tenta ENV
    primeiro; se não bater, busca nesta tabela por email.

    Papéis: owner · admin · member.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_user_org_email"),
        Index("ix_users_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    invited_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
