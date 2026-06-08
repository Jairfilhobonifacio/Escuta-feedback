"""Composição e envio do digest semanal.

Fluxo: agrega os números → o brain narra (LLM) → se o LLM falhar, cai num
texto determinístico (o digest NUNCA sai vazio) → envia no WhatsApp do dono
(Organization.settings.owner_phone) via o canal injetado.

O telefone do dono vive em Organization.settings['owner_phone'] (dígitos).
Sem ele, o compose ainda devolve o texto (para dry-run/painel), mas o envio
informa que não há destinatário configurado.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.digest.aggregator import DigestData, aggregate
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.brain import SurveyBrain
from app.models.core import Organization

logger = logging.getLogger(__name__)


def fallback_text(data: DigestData) -> str:
    """Digest determinístico — usado quando o LLM não está disponível."""
    if not data.has_activity:
        return (
            f"Resumo da semana — {data.org_name} 👋\n"
            f"Foi uma semana quieta: nenhuma pesquisa respondida nos últimos "
            f"{data.period_days} dias. Que tal disparar uma rodada de NPS?"
        )
    lines = [f"Resumo da semana — {data.org_name} 👋"]
    if data.nps is not None:
        delta = data.nps_delta
        var = f" ({'+' if delta and delta > 0 else ''}{delta} vs semana passada)" if delta is not None else ""
        lines.append(f"NPS: {data.nps}{var} · {data.answered} resposta(s) de {data.sent} enviada(s).")
    else:
        lines.append(f"{data.answered} resposta(s) de {data.sent} enviada(s).")
    if data.top_themes:
        temas = ", ".join(f"{t} ({c})" for t, c in data.top_themes[:3])
        lines.append(f"Temas mais citados: {temas}.")
    if data.churn:
        lines.append(f"{len(data.churn)} cancelamento(s) com motivo registrado.")
    if data.urgent:
        lines.append(f"⚠️ {len(data.urgent)} caso(s) urgente(s) para olhar.")
    return "\n".join(lines)


async def build_digest(
    session: AsyncSession, organization_id: uuid.UUID, brain: Optional[SurveyBrain], days: int = 7
) -> tuple[str, DigestData]:
    """Monta o texto do digest (narrado pelo LLM, ou determinístico no fallback)."""
    data = await aggregate(session, organization_id, days)
    text = None
    if brain is not None and data.has_activity:
        try:
            text = await brain.narrate_digest(data.as_dict())
        except Exception:  # noqa: BLE001 — narrativa nunca derruba o digest
            logger.warning("digest: narrate_digest falhou — usando fallback", exc_info=True)
    return (text or fallback_text(data)), data


async def send_digest(
    session: AsyncSession,
    organization_id: uuid.UUID,
    brain: Optional[SurveyBrain],
    messaging: IMessagingService,
    days: int = 7,
    waha_session: str = "default",
) -> dict:
    """Monta e ENVIA o digest ao dono. Retorna um resumo do que aconteceu."""
    text, data = await build_digest(session, organization_id, brain, days)

    org = await session.get(Organization, organization_id)
    owner_phone = (org.settings or {}).get("owner_phone") if org else None
    if not owner_phone:
        return {"sent": False, "reason": "sem owner_phone em Organization.settings", "text": text}

    await messaging.send_text(chat_id=owner_phone, text=text, session=waha_session)
    return {"sent": True, "to": owner_phone, "text": text, "data": data.as_dict()}
