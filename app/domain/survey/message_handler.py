"""InboundMessageHandler — funil da mensagem inbound SEM pesquisa pendente.

Companheiro do `SurveyContextResolver` (resolver.py): aquele cuida da mensagem que
CASA com uma pesquisa pendente; este cuida do caminho de saída — quando o contato
mandou algo e NÃO há pesquisa aberta esperando resposta.

Hoje (Fase 0) esse caminho era um bloco inline no webhook (`_capturar_resposta_central`):
registra o sinal na Mega Central pro lead não sumir. Aqui ele vira um handler com
nome próprio, no mesmo espírito do resolver:

- best-effort: NUNCA lança (o webhook do WAHA não pode cair). Toda exceção é logada
  e engolida — o caller segue e dá commit.
- gated: a captura na central segue gated pela presença de `body` (texto válido);
  qualquer enriquecimento por IA já é gated pelas flags/segredos no ingestor.
- NÃO dispara WhatsApp: este caminho não chama o WAHA (a Fase 0 já não chamava).
  Devolve um `InboundOutcome` descritivo; quem envia (se um dia enviar) é o webhook.

Fase 1 (futuro): aqui entra o encaminhamento ao orchestrator/agente (RAG + LLM)
para responder dúvidas fora de pesquisa. Por ora, mantemos o comportamento atual
(capturar e seguir), só que isolado e testável.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Contact, Organization

logger = logging.getLogger(__name__)


@dataclass
class InboundOutcome:
    """Resultado do tratamento da inbound sem pesquisa pendente.

    `status` espelha o que o webhook devolve no JSON ('no_pending_survey' hoje).
    `captured` indica se um sinal foi (ou seria) registrado na central. `reply` é
    reservado p/ a Fase 1 (resposta do agente) — hoje sempre None (nada a enviar).
    """
    status: str = "no_pending_survey"
    captured: bool = False
    reply: Optional[str] = None


# Estados de assinatura (snapshot partner) que já são churn por si só. Espelha o
# vocabulário de app/api/campanha.py (_CHURN_STATES); mantido local p/ não acoplar.
_CHURN_STATES = ("cancelled", "paid_without_access")


def _contato_eh_churn(contact: Contact) -> bool:
    """Contato pertence ao universo de churn da campanha win-back?

    True se QUALQUER um:
    - tem o selo 'contatado' (foi abordado na campanha win-back);
    - `partner.subscription.state` ∈ {cancelled, paid_without_access};
    - o perfil do snapshot (`partner.profile`) começa com 'churn'.

    Import tardio de campanha.py p/ evitar ciclo (campanha não importa este módulo).
    """
    from app.api.campanha import SELO_CONTATADO, _selos_do_contato

    if SELO_CONTATADO in _selos_do_contato(contact):
        return True
    # copia-edita-reatribui NÃO se aplica aqui: só LEITURA do profile_data (sem mutação).
    partner = ((contact.profile_data or {}).get("partner") or {})
    sub = (partner.get("subscription") or {})
    if sub.get("state") in _CHURN_STATES:
        return True
    perfil = partner.get("profile") or ""
    return isinstance(perfil, str) and perfil.lower().startswith("churn")


class InboundMessageHandler:
    """Trata a inbound que não casou com pesquisa pendente. Best-effort, gated."""

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.org_id = organization_id

    async def handle(
        self,
        contact: Contact,
        body: str,
        message_id: Any = None,
    ) -> InboundOutcome:
        """Funil principal. Captura o sinal na Mega Central (idempotente) e segue.

        NUNCA lança — qualquer erro vira log + outcome 'no_pending_survey' sem
        captura. NÃO dispara WhatsApp. Gated pela presença de `body`.
        """
        if not body:
            return InboundOutcome(status="no_pending_survey", captured=False)

        org = await self.session.get(Organization, self.org_id)
        if org is None:
            logger.warning("inbound handler: org %s não encontrada — sem captura", self.org_id)
            return InboundOutcome(status="no_pending_survey", captured=False)

        captured = await self._capturar_central(org, contact, body, message_id)
        # TODO(Fase 1): encaminhar ao orchestrator/agente (RAG + LLM) aqui e, se
        # houver resposta, devolvê-la em outcome.reply para o webhook enviar.
        return InboundOutcome(status="no_pending_survey", captured=captured)

    async def _capturar_central(
        self, org: Organization, contact: Contact, body: str, message_id: Any
    ) -> bool:
        """Registra na Mega Central o sinal inbound. Best-effort + idempotente.

        Cria/atualiza um FeedbackItem (source='whatsapp') via ingestor (dedup por
        external_id 'wa:<id>'). Se o contato foi abordado na campanha (selo
        'contatado'), aplica também o selo 'respondeu'. Retorna True se registrou.
        Nunca lança.
        """
        try:
            from app.api.campanha import (
                SELO_CONTATADO,
                SELO_RESPONDEU,
                _selos_do_contato,
                _set_selos_do_contato,
                _upsert_catalogo,
            )
            from app.domain.feedback.ingest import ingest_feedback_item
            from app.models.feedback import FeedbackItem

            ftype = "churn" if _contato_eh_churn(contact) else "outro"
            external_id = f"wa:{message_id}" if message_id is not None else None

            # Sem id estável: evita duplicar em retry checando texto idêntico recente.
            if external_id is None:
                dup = (
                    await self.session.execute(
                        select(FeedbackItem).where(
                            FeedbackItem.organization_id == org.id,
                            FeedbackItem.contact_id == contact.id,
                            FeedbackItem.source == "whatsapp",
                            FeedbackItem.text == body,
                        )
                    )
                ).first()
                if dup is not None:
                    return False

            await ingest_feedback_item(
                self.session,
                org.id,
                contact.id,
                {
                    "source": "whatsapp",
                    "type": ftype,
                    "external_id": external_id,
                    "text": body,
                    "occurred_at": datetime.now(timezone.utc),
                },
            )

            # Funil da campanha: quem foi abordado ('contatado') e respondeu pelo
            # WhatsApp ganha o selo 'respondeu' (idempotente + garante no catálogo).
            selos = _selos_do_contato(contact)
            if SELO_CONTATADO in selos and SELO_RESPONDEU not in selos:
                _set_selos_do_contato(contact, [*selos, SELO_RESPONDEU])
                _upsert_catalogo(org, SELO_RESPONDEU, None)
            return True
        except Exception:  # noqa: BLE001 — captura é best-effort; nunca derruba o webhook.
            logger.warning("inbound handler: captura na central falhou (seguindo)", exc_info=True)
            return False
