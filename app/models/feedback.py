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

from sqlalchemy import Boolean, String, Integer, Text, ForeignKey, UniqueConstraint, Index, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant


class FeedbackItem(Base):
    __tablename__ = "feedback_items"
    __table_args__ = (
        # Idempotência da ingestão: cada sinal tem um id estável por fonte.
        UniqueConstraint("organization_id", "external_id", name="uq_feedback_org_external"),
        Index("ix_feedback_org_contact_occurred", "organization_id", "contact_id", "occurred_at"),
        # Board (Camada 2): filtrar/agrupar o Kanban por responsável dentro da org.
        Index("ix_feedback_items_assignee", "organization_id", "assignee"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Melhoria do roadmap a que este feedback foi vinculado ("Fechar o loop").
    # NULL = ainda não virou melhoria. Um feedback pertence a no máximo UMA melhoria.
    # ON DELETE SET NULL: apagar a melhoria solta os feedbacks (não os apaga).
    improvement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("improvements.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Dor (cluster semântico) a que este feedback foi atribuído pelo motor de
    # clustering. NULL = ainda não agrupado. ON DELETE SET NULL: apagar a dor solta
    # os feedbacks. A coluna pgvector `embedding vector(384)` fica FORA do ORM (só na
    # migration + SQL cru, igual knowledge_chunks) — ver app/models/cluster.py.
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("feedback_clusters.id", ondelete="SET NULL"), nullable=True, index=True
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

    # Estado da AÇÃO tomada sobre o sinal (workflow de monitoramento — separado da IA).
    # 'novo' | 'em_analise' | 'planejado' | 'resolvido' | 'descartado' (validado na API).
    action_status: Mapped[str] = mapped_column(String, server_default="novo", default="novo")
    action_note: Mapped[str | None] = mapped_column(Text, nullable=True)     # nota interna do operador

    # Board de Gestão (Camada 2): roteamento por time + responsável. Sem tabela de
    # users (igual cs_tasks.owner) — slug/email livre, validado só por presença.
    # assignee = quem do time cuida; team_tag = produto/suporte/comercial/cs (roteamento).
    assignee: Mapped[str | None] = mapped_column(String, nullable=True)
    team_tag: Mapped[str | None] = mapped_column(String, nullable=True)

    # "Abordado": o operador JÁ falou com o cliente sobre este feedback (≠ action_status,
    # que é o estágio do tratamento interno). abordado_em registra o instante (preenchido na API).
    abordado: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    abordado_em: Mapped[datetime | None] = mapped_column(nullable=True)
