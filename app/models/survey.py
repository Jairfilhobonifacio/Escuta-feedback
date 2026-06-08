"""Models do domínio de Survey (camada NOVA — ver docs/PRD_FASE0.md §4).

survey_responses espelha o padrão de `campaign_sends` do Nexus (estado por contato
+ unique para idempotência). O estado "aguardando resposta" vive em `status`.
Tipos portáveis (PG + SQLite) — ver app/models/base.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, ForeignKey, UniqueConstraint, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant
# Reexporta as constantes de estado (fonte da verdade: constants.py, stdlib-only)
from app.domain.survey.constants import (  # noqa: F401
    STATUS_SENT,
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
)


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_survey_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)            # "NPS Bizzu"
    type: Mapped[str] = mapped_column(String)            # 'nps' | 'exit'
    # [{key:'nps', kind:'nps', text:'...'}, {key:'reason', kind:'open', text:'...'},
    #  {key:'thanks', kind:'thanks', text:'...'}]
    questions: Mapped[list] = mapped_column(JSONVariant, default=list)
    # Evento de ciclo de vida que dispara esta survey automaticamente via
    # /api/events/* (ex.: 'subscription_cancelled'). NULL = só disparo manual.
    trigger_event: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SurveyRun(Base):
    __tablename__ = "survey_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("surveys.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[str] = mapped_column(String, default="manual")
    status: Mapped[str] = mapped_column(String, default="running")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    __table_args__ = (
        UniqueConstraint("survey_run_id", "contact_id", name="uq_survey_response_run_contact"),
        Index("ix_survey_response_org_contact_status", "organization_id", "contact_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    survey_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("survey_runs.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String, default=STATUS_SENT)
    answer_score: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 0..10
    nps_bucket: Mapped[str | None] = mapped_column(String, nullable=True)      # promoter/passive/detractor
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)       # motivo (follow-up)
    # Enriquecimento por IA (SurveyBrain.classify_feedback) — tudo nullable:
    # ausência = não classificado (LLM off/erro), nunca bloqueia o fluxo.
    sentiment: Mapped[str | None] = mapped_column(String, nullable=True)       # positivo/neutro/negativo
    themes: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)    # ["preço", ...]
    ai_meta: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)   # urgency, opt_out, modelo...
    channel_msg_id: Mapped[str | None] = mapped_column(String, nullable=True)  # waha id da pergunta
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
