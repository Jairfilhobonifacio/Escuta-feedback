"""Mapeia um PartnerCustomer (API de Clientes) em specs de FeedbackItem. PURA.

Sem I/O: recebe o dict cru da API + a classificação de perfil e devolve uma lista
de specs (dicts) que o ingestor (`ingest.py`) persiste. Hoje extrai 2 sinais do
snapshot da API de Clientes:
  - NPS  : se o cliente já votou no app (nota + comentário).
  - Churn: se cancelou (motivo categórico + contexto).

Cada spec tem `external_id` estável → re-sync é idempotente (atualiza, não duplica).
"""
from __future__ import annotations

from typing import Any


def _to_int(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) else None


def partner_feedback_specs(customer: dict, classification: dict | None = None) -> list[dict[str, Any]]:
    """Converte 1 PartnerCustomer em 0..2 specs de FeedbackItem (NPS e/ou churn)."""
    sub = customer.get("subscription") or {}
    nps = customer.get("nps") or {}
    cid = customer.get("id")
    cid_s = str(cid) if cid is not None else "?"
    profile = (classification or {}).get("profile")
    specs: list[dict[str, Any]] = []

    # --- NPS já votado no app ---
    if nps.get("voted") and nps.get("score") is not None:
        responded = nps.get("respondedAt")
        comment = nps.get("comment")
        specs.append(
            {
                "source": "bizzu_app",
                "type": "nps",
                "external_id": f"partner:nps:{cid_s}:{responded or nps.get('score')}",
                "score": _to_int(nps.get("score")),
                "text": (str(comment).strip() or None) if comment else None,
                "occurred_at": responded,
                "extra": {"partner_customer_id": cid_s, "profile": profile},
            }
        )

    # --- Churn (cancelado) ---
    cancelled = bool(sub.get("cancelled")) or sub.get("state") in ("cancelled", "cancelled_with_access")
    if cancelled:
        reason = sub.get("cancellationReason")
        specs.append(
            {
                "source": "bizzu_billing",
                "type": "churn",
                "external_id": f"partner:churn:{cid_s}",
                "score": None,
                "text": reason,
                "occurred_at": sub.get("cancelledAt"),
                "extra": {
                    "partner_customer_id": cid_s,
                    "cancellationReason": reason,
                    "daysAsSubscriber": sub.get("daysAsSubscriber"),
                    "planType": sub.get("planType"),
                    "profile": profile,
                },
            }
        )

    return specs
