"""Lógica pura do SurveyContextResolver (sem I/O, sem banco).

Separada do resolver async de propósito: assim dá pra testar a decisão com a
stdlib, sem precisar de SQLAlchemy/Postgres instalados. O resolver async
(resolver.py) faz só o plumbing de banco e chama `decide_next`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.survey.parsers import parse_nps, nps_bucket
from app.domain.survey.constants import STATUS_SENT, STATUS_AWAITING_REASON, STATUS_CLOSED


@dataclass
class Decision:
    """O que fazer com a resposta pendente, dado o texto recebido."""
    reply_text: str
    new_status: str
    answer_score: Optional[int] = None
    nps_bucket: Optional[str] = None
    answer_text: Optional[str] = None


def decide_next(
    status: str,
    message: str,
    *,
    reason_prompt: str,
    thanks_msg: str,
    retry_msg: str,
) -> Optional[Decision]:
    """Decide o próximo passo de uma pesquisa pendente.

    - status 'sent' (aguardando NPS): parseia 0-10. Válido → pede o motivo e
      avança p/ 'awaiting_reason'. Inválido → pede um número (mantém 'sent').
    - status 'awaiting_reason': grava o motivo e fecha ('closed').
    - qualquer outro: None (não é resposta de pesquisa).
    """
    if status == STATUS_SENT:
        score = parse_nps(message)
        if score is None:
            return Decision(reply_text=retry_msg, new_status=STATUS_SENT)
        return Decision(
            reply_text=reason_prompt,
            new_status=STATUS_AWAITING_REASON,
            answer_score=score,
            nps_bucket=nps_bucket(score),
        )

    if status == STATUS_AWAITING_REASON:
        return Decision(
            reply_text=thanks_msg,
            new_status=STATUS_CLOSED,
            answer_text=(message or "").strip(),
        )

    return None
