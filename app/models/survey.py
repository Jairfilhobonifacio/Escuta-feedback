"""Models do domínio de Survey (camada NOVA — ver docs/PRD_FASE0.md §4).

survey_responses espelha o padrão de `campaign_sends` do Nexus (estado por contato
+ unique para idempotência). O estado "aguardando resposta" vive em `status`.
Tipos portáveis (PG + SQLite) — ver app/models/base.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, Boolean, ForeignKey, UniqueConstraint, Index, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant
# Reexporta as constantes de estado (fonte da verdade: constants.py, stdlib-only)
from app.domain.survey.constants import (  # noqa: F401
    STATUS_SENT,
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
    STATUS_INGESTED,
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
    # ingest_mode=True: a survey RECEBE respostas já dadas (ex.: NPS in-app do app
    # Bizzu) via /api/events/*; o handler registra+classifica e NÃO dispara WhatsApp.
    ingest_mode: Mapped[bool] = mapped_column(Boolean, default=False)
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
    # Origem da resposta: 'whatsapp' (disparada+respondida no WA) ou 'in_app'
    # (ingerida já respondida — ex.: NPS in-app do Bizzu, sem disparo).
    source: Mapped[str] = mapped_column(String, default="whatsapp")


class Message(Base):
    """Transcript da conversa (append-only) — base do chatbot e do hand-off humano.

    Complementar ao SurveyResponse: a response é o estado/resultado; a Message é
    cada turno trocado (inbound do contato, outbound do bot). Dá histórico para o
    aprofundamento ter contexto e para o humano assumir sabendo o que já foi dito.
    """
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_message_org_contact_time", "organization_id", "contact_id", "created_at"),
        Index("ix_message_contact_time", "contact_id", "created_at"),
        # Dedup atômico do transcript: o MESMO turno do WAHA (channel_msg_id) só
        # entra UMA vez por org. PARCIAL (channel_msg_id IS NOT NULL) — mensagens
        # sem id de canal (outbound do bot) não colidem entre si. No Postgres vira
        # um índice único parcial; o SQLite dos testes ignora o `sqlite_where` e
        # aplica o unique direto (todas as linhas de teste têm channel_msg_id).
        Index(
            "uq_messages_org_channel_msg_id",
            "organization_id",
            "channel_msg_id",
            unique=True,
            postgresql_where=text("channel_msg_id IS NOT NULL"),
            sqlite_where=text("channel_msg_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    survey_response_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("survey_responses.id", ondelete="SET NULL"), nullable=True
    )
    direction: Mapped[str] = mapped_column(String)            # 'inbound' | 'outbound'
    body: Mapped[str] = mapped_column(Text)
    channel_msg_id: Mapped[str | None] = mapped_column(String, nullable=True)  # id da msg no WAHA
    # Saco de metadados livres da mensagem (JSONB no PG, JSON no SQLite). Schema em
    # app/schemas/messages.py (MessageMetadata). NULL = sem metadados. SEMPRE montar
    # via copia-edita-reatribui (nunca mutar in-place o dict de uma linha existente).
    msg_metadata: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
