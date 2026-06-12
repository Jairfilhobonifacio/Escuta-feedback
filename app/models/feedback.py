"""Mega Central de Dados — model FeedbackItem (camada Fase 2).

Um registro GENÉRICO de sinal de feedback de QUALQUER fonte (NPS in-app, churn,
ticket de suporte, report de questão, solicitação de edital...). Unifica tudo num
formato só, classificado por IA, para a Visão 360 do cliente e o clustering.

Diferença de SurveyResponse:
- SurveyResponse = resposta COLETADA pelo Escuta (survey via WhatsApp).
- FeedbackItem  = sinal INGERIDO de uma fonte externa (pull da API de Clientes
  hoje; push de eventos do backend no futuro).
A Visão 360 (GET /api/contacts/{id}/360) une os dois por contato.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, ForeignKey, UniqueConstraint, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant


class FeedbackItem(Base):
    __tablename__ = "feedback_items"
    __table_args__ = (
        # Idempotência da ingestão: cada sinal tem um id estável por fonte.
        UniqueConstraint("organization_id", "external_id", name="uq_feedback_org_external"),
        Index("ix_feedback_org_contact_occurred", "organization_id", "contact_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # De onde veio: 'bizzu_app' | 'bizzu_billing' | 'bizzu_support' | 'whatsapp' | ...
    source: Mapped[str] = mapped_column(String)
    # O que é: 'nps' | 'churn' | 'csat' | 'ticket' | 'report' | 'edital_request' | ...
    type: Mapped[str] = mapped_column(String)
    # id estável da fonte p/ dedup (ex.: 'partner:churn:<customer_id>'). NULL = sem dedup.
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 0..10 (nps/csat)
    nps_bucket: Mapped[str | None] = mapped_column(String, nullable=True)    # promoter/passive/detractor
    text: Mapped[str | None] = mapped_column(Text, nullable=True)            # comentário/motivo livre

    # Enriquecimento por IA (mesma semântica de SurveyResponse) — tudo nullable.
    sentiment: Mapped[str | None] = mapped_column(String, nullable=True)
    themes: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    ai_meta: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    occurred_at: Mapped[datetime | None] = mapped_column(nullable=True)      # quando aconteceu na fonte
    extra: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)   # metadados livres (NÃO usar 'metadata' — reservado)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
