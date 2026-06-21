"""Loop de correção (Feature 2): aprende das edições MANUAIS de feedback.

Sem tabela/migration nova: lê as correções já gravadas pelo PATCH /feedbacks/{id}
em `Contact.profile_data["feedback_log"]` (formato `{feedback_id, campos, at, por}`).
Filtra os eventos cujo `campos` inclui "sentiment" ou "themes" (o que um humano
corrige), dedup por feedback (evento mais recente), carrega o FeedbackItem atual (já
reflete a correção) e monta exemplos few-shot para CALIBRAR o classificador.

Org-scoped, top-N (8-12), texto truncado em 240 chars. 1 leitura de DB por chamada
(o caller de lote reusa a lista entre itens). Best-effort: erro/vazio ⇒ lista vazia.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Contact
from app.models.feedback import FeedbackItem

logger = logging.getLogger(__name__)

# Campos que, quando aparecem num evento do feedback_log, indicam correção humana
# da classificação (é o que vale calibrar). Espelha admin._append_feedback_log.
_CORRECTION_FIELDS = ("sentiment", "themes")
_TEXT_MAX = 240
_DEFAULT_LIMIT = 10
# Quantos contatos (mais recentes) varrer — barato no piloto (1 org), barato no Modal.
_CONTACT_SCAN_CAP = 200


@dataclass(frozen=True)
class CorrectionExample:
    texto: str
    sentiment: str
    themes: list[str]


async def collect_correction_examples(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> list[CorrectionExample]:
    """Exemplos de correções humanas da org, mais recentes primeiro (top-`limit`).

    Lê o feedback_log dos contatos da org (varredura curta), pega os eventos de
    correção de sentiment/themes, dedup por feedback_id (evento `at` mais recente),
    e materializa o FeedbackItem ATUAL (já corrigido). Descarta itens sem text/sentiment.
    NUNCA lança: qualquer falha ⇒ []."""
    if limit <= 0:
        return []
    try:
        contacts = (
            await session.execute(
                select(Contact)
                .where(Contact.organization_id == organization_id)
                .order_by(Contact.updated_at.desc())
                .limit(_CONTACT_SCAN_CAP)
            )
        ).scalars().all()

        # dedup por feedback_id: guarda o evento `at` mais recente de cada feedback.
        latest_at: dict[str, str] = {}
        for c in contacts:
            raw = (c.profile_data or {}).get("feedback_log")
            if not isinstance(raw, list):
                continue
            for e in raw:
                if not isinstance(e, dict):
                    continue
                campos = e.get("campos")
                if not isinstance(campos, list):
                    continue
                if not any(f in campos for f in _CORRECTION_FIELDS):
                    continue
                fid = e.get("feedback_id")
                at = e.get("at") or ""
                if not fid:
                    continue
                fid = str(fid)
                if at >= latest_at.get(fid, ""):
                    latest_at[fid] = at

        if not latest_at:
            return []

        # Ordena por `at` desc e materializa só os top candidatos (corta cedo).
        ordered = sorted(latest_at.items(), key=lambda kv: kv[1], reverse=True)
        examples: list[CorrectionExample] = []
        for fid, _at in ordered:
            if len(examples) >= limit:
                break
            try:
                feedback_uuid = uuid.UUID(fid)
            except (ValueError, TypeError):
                continue
            fb = (
                await session.execute(
                    select(FeedbackItem).where(
                        FeedbackItem.id == feedback_uuid,
                        FeedbackItem.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if fb is None or not fb.text or not fb.sentiment:
                continue
            themes = fb.themes if isinstance(fb.themes, list) else []
            examples.append(
                CorrectionExample(
                    texto=str(fb.text).strip()[:_TEXT_MAX],
                    sentiment=str(fb.sentiment),
                    themes=[str(t) for t in themes][:3],
                )
            )
        return examples
    except Exception:  # noqa: BLE001 — loop é enriquecedor, nunca ponto de falha.
        logger.warning("collect_correction_examples falhou — seguindo sem exemplos", exc_info=True)
        return []
