"""Improvement — melhoria do roadmap ("Fechar o loop").

Uma melhoria do produto que NASCE de feedbacks dos clientes. O operador agrupa
feedbacks (FeedbackItem) numa melhoria, acompanha o status (ideia → entregue) e,
quando entrega, pode avisar os clientes que pediram ("você pediu, a gente fez").

Vínculo: FeedbackItem.improvement_id aponta para cá (um feedback pertence a no
máximo UMA melhoria). A melhoria não conhece os feedbacks diretamente — a contagem
é derivada por query (feedback_count). Multi-tenant por organization_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Improvement(Base):
    __tablename__ = "improvements"
    __table_args__ = (
        Index("ix_improvement_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Estágio no roadmap: 'ideia' | 'planejada' | 'em_andamento' | 'entregue' | 'descartada'.
    # Validado na API (sem CHECK no banco — vocabulário pode crescer).
    status: Mapped[str] = mapped_column(String, server_default="ideia", default="ideia")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Quando a melhoria foi marcada como 'entregue' (preenchido na API ao virar entregue).
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Quando os clientes foram avisados ("você pediu, a gente fez") — NULL = ainda não.
    notified_at: Mapped[datetime | None] = mapped_column(nullable=True)
