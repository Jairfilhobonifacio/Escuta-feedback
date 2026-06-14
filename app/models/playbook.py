"""Models da Fase 2 — Playbooks & Automação (gatilho → ação) + fila de Tarefas de CS.

Duas tabelas novas (ver docs/FASE2_PLAYBOOKS_SPEC.md §2):

- `Playbook`: a REGRA, stateless. Um gatilho (`trigger_type`) + uma condição livre
  (`trigger_config`, JSONB) + uma ação (`action_type`/`action_config`). O motor
  (`app/domain/cs/engine.py`) lê os playbooks `enabled` da org, resolve candidatos e
  cria tarefas (ou alerta o dono). Os enums NÃO viram CHECK no banco — são validados
  na API, igual a `FeedbackItem.action_status`/`Improvement.status` (vocabulário cresce).

- `CsTask`: a TAREFA concreta na fila de CS (contas a abordar hoje). Nasce de um
  playbook (ou manual = `playbook_id` NULL). `dedup_key` (UNIQUE por org) dá
  idempotência ao motor: rodar duas vezes no mesmo mês não duplica a tarefa.

Tipos portáveis (PG + SQLite) — ver app/models/base.py. JSONB livre via `JSONVariant`.
IMPORTANTE: índices PARCIAIS (`postgresql_where`) ficam SÓ na migration — colocá-los
no `__table_args__` quebraria o `create_all` do SQLite nos testes (regra §1.4 da spec).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, Text, ForeignKey, UniqueConstraint, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant


class Playbook(Base):
    __tablename__ = "playbooks"
    __table_args__ = (
        # Índice simples só por org (o parcial por trigger fica na migration, PG-only).
        Index("ix_playbooks_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=func.true(), default=True)
    # Gatilho: 'nps_detractor' | 'health_at_risk' | 'inactive_days' | 'renewal_soon' |
    # 'churn_detected'. Validado na API (sem CHECK no banco).
    trigger_type: Mapped[str] = mapped_column(String)
    # Condição livre do gatilho. Ex.: {"band":"at_risk"}, {"days":14},
    # {"days_before":7}, {"max_score":6}. Avaliada por comparação de chaves (sem eval).
    trigger_config: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    # Ação: 'create_task' | 'alert_owner'. Validado na API.
    action_type: Mapped[str] = mapped_column(String)
    # Config da ação. Ex.: {"title":"Abordar {nome}","priority":"alta","sla_hours":24,"owner":"cs"}.
    action_config: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CsTask(Base):
    __tablename__ = "cs_tasks"
    __table_args__ = (
        # Idempotência do motor: (org, dedup_key) único. dedup_key NULL = duplicata
        # permitida (tarefas manuais não deduplicam). Em SQLite/PG, múltiplos NULL
        # NÃO colidem num UNIQUE — então tarefas manuais convivem sem problema.
        UniqueConstraint("organization_id", "dedup_key", name="uq_cs_tasks_dedup"),
        Index("ix_cs_tasks_org_status_due", "organization_id", "status", "due_at"),
        Index("ix_cs_tasks_contact", "contact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    # Contato alvo da tarefa (NULL = tarefa sem contato resolvido).
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    # Playbook que originou a tarefa (NULL = tarefa manual).
    playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("playbooks.id", ondelete="SET NULL"), nullable=True
    )
    # Contexto opcional: feedback/survey que motivaram a tarefa.
    feedback_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("feedback_items.id", ondelete="SET NULL"), nullable=True
    )
    survey_response_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("survey_responses.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String)                                  # interpolável com {nome}
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)             # contexto livre do gatilho
    # 'aberta' | 'em_andamento' | 'concluida' | 'adiada' — validado na API.
    status: Mapped[str] = mapped_column(String, server_default="aberta", default="aberta")
    # 'baixa' | 'normal' | 'alta' | 'urgente' — validado na API.
    priority: Mapped[str] = mapped_column(String, server_default="normal", default="normal")
    owner: Mapped[str | None] = mapped_column(String, nullable=True)           # slug/telefone/email do responsável
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)              # SLA = created_at + sla_hours
    snoozed_until: Mapped[datetime | None] = mapped_column(nullable=True)       # preenchido ao adiar (status='adiada')
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)             # anotações do operador
    # Snapshot do gatilho: {health, health_band, nps_score, perfil, trigger_type}.
    meta: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    # Idempotência do motor: f"{trigger_type}:{contact_id}:{YYYY-MM}". NULL = duplicata permitida.
    dedup_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)           # preenchido ao virar 'concluida'
