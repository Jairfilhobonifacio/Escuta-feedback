"""Serviço de sincronização ASSÍNCRONA da base de clientes da Bizzu (API Partner).

Roda FORA do request (agendado via BackgroundTasks no POST /api/sources/{key}/sync):
a sessão do request já fechou, então criamos a NOSSA própria sessão a partir de
`SessionLocal` e recarregamos a org. Pagina TODOS os clientes pela API de Clientes
(somente leitura), canoniza o telefone (`phone_key`), deduplica por variante
(`phone_variants`) e enriquece o `Contact` com o snapshot `profile_data["partner"]` —
o MESMO shape que o painel filtra em GET /clientes (`partner.profile`,
`partner.subscription.state/planType`, `partner.nps.score`).

O progresso é gravado em `settings["sources"]["bizzu_partner"]["sync"]`
(copia-edita-reatribui o JSONB; SEM migration), commitado a cada ~25 clientes para o
polling enxergar o avanço.

Robustez:
  - fail-soft por cliente: um item ruim (sem telefone ou que explode) conta em `errors`
    e o lote SEGUE — um cliente não derruba o sync.
  - erro global (ex.: BizzuPartnerAuthError quando falta a chave) → status='error' com
    mensagem curta (SEM PII e SEM a chave).
Idempotente/re-rodável: re-sync atualiza o snapshot, não duplica contato.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.domain.sources import sync_state, write_sync

logger = logging.getLogger(__name__)

SOURCE_KEY = "bizzu_partner"
PROGRESS_EVERY = 25  # commita o progresso a cada N clientes processados


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_partner_snapshot(customer: dict, classification: dict) -> dict[str, Any]:
    """Snapshot enxuto p/ gravar em profile_data['partner'].

    Espelha `_build_partner_profile` de scripts/sync_partner_customers.py (a fonte de
    verdade do shape interno): perfil + campos de assinatura/nps que alimentam os filtros
    do painel. Não guarda e-mail nem nome aqui (nome vai em Contact.name). id como string.
    """
    sub = customer.get("subscription") or {}
    nps = customer.get("nps") or {}
    cid = customer.get("id")
    return {
        "partner_customer_id": str(cid) if cid is not None else None,
        "profile": classification["profile"],
        "profile_reason": classification["reason"],
        "should_contact": classification["should_contact"],
        "subscription": {
            "state": sub.get("state"),
            "active": sub.get("active"),
            "cancelled": sub.get("cancelled"),
            "complimentary": sub.get("complimentary"),
            "planType": sub.get("planType"),
            "planName": sub.get("planName"),
            "startedAt": sub.get("startedAt"),
            "cancellationReason": sub.get("cancellationReason"),
            "daysAsSubscriber": sub.get("daysAsSubscriber"),
            "currentPeriodEnd": sub.get("currentPeriodEnd"),
            "totalPaidCentavos": sub.get("totalPaidCentavos"),
        },
        "nps": {
            "voted": nps.get("voted"),
            "score": nps.get("score"),
            "respondedAt": nps.get("respondedAt"),
        },
    }


def _safe_error(exc: Exception) -> str:
    """Mensagem curta de erro p/ o painel — NUNCA vaza PII nem a chave da API."""
    from app.integrations.bizzu_partner import BizzuPartnerAuthError

    if isinstance(exc, BizzuPartnerAuthError):
        return "chave da API Partner ausente ou inválida (configure BIZZU_PARTNER_API_KEY)"
    return f"falha ao sincronizar ({type(exc).__name__})"


async def run_bizzu_sync(organization_id: Any, *, page_size: int = 100, client: Any = None) -> None:
    """Sincroniza a base de clientes da Bizzu para a org, enriquecendo os Contacts.

    Cria a PRÓPRIA sessão (a BackgroundTask roda fora do request). `client` é injetável
    para teste (sem rede). Atualiza o estado de progresso em settings["sources"] e nunca
    propaga exceção — falhas viram status='error' (global) ou contam em `errors` (item).
    """
    # Imports tardios: evita ciclo (admin importa este módulo) e deixa o teste monkeypatchar
    # app.db.SessionLocal por um sessionmaker do engine SQLite in-memory.
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.domain.contacts.whatsapp import phone_key, phone_variants
    from app.domain.segmentation.profiles import classify_profile
    from app.integrations.bizzu_partner import BizzuPartnerClient
    from app.models.core import Contact, Organization

    if SessionLocal is None:
        logger.error("run_bizzu_sync: DATABASE_URL não configurada — abortando sync")
        return

    client = client or BizzuPartnerClient()

    async def _reload_org(session: Any) -> Any:
        return (
            await session.execute(select(Organization).where(Organization.id == organization_id))
        ).scalar_one_or_none()

    async def _upsert(session: Any, org_id: Any, customer: dict) -> str:
        """Cria/atualiza 1 contato a partir do PartnerCustomer. Devolve created|updated|error."""
        raw = customer.get("whatsapp") or customer.get("telefone") or customer.get("phone") or ""
        canon = phone_key(raw)
        if canon is None:
            return "error"  # sem telefone válido → pulo contado como erro
        variants = phone_variants(raw)
        name = (customer.get("name") or "").strip() or None
        partner = build_partner_snapshot(customer, classify_profile(customer))

        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.organization_id == org_id, Contact.phone.in_(variants)
                )
            )
        ).scalars().first()

        if contact is None:
            contact = Contact(
                organization_id=org_id,
                phone=canon,
                name=name,
                profile_data={"partner": partner},
                opt_in=False,
            )
            session.add(contact)
            await session.flush()
            return "created"

        # Atualiza: name só se vazio; partner SEMPRE refresca (snapshot da API).
        if not contact.name and name:
            contact.name = name
        profile = dict(contact.profile_data or {})  # copia-edita-reatribui (JSON puro)
        profile["partner"] = partner
        contact.profile_data = profile
        return "updated"

    processed = created = updated = errors = 0
    async with SessionLocal() as session:
        org = await _reload_org(session)
        if org is None:
            logger.error("run_bizzu_sync: org %s não encontrada — abortando", organization_id)
            return

        sync = sync_state(org, SOURCE_KEY)
        try:
            async for customer in client.iter_all_customers(page_size=page_size):
                processed += 1
                try:
                    outcome = await _upsert(session, org.id, customer)
                except Exception:  # noqa: BLE001 — fail-soft: um cliente ruim não derruba o lote.
                    errors += 1
                    logger.warning("run_bizzu_sync: cliente falhou — seguindo", exc_info=True)
                else:
                    if outcome == "created":
                        created += 1
                    elif outcome == "updated":
                        updated += 1
                    else:
                        errors += 1
                # Progresso visível no polling: commita a cada N processados.
                if processed % PROGRESS_EVERY == 0:
                    sync.update(
                        {"processed": processed, "created": created, "updated": updated, "errors": errors}
                    )
                    write_sync(org, SOURCE_KEY, sync)
                    await session.commit()

            sync.update(
                {
                    "status": "done",
                    "finished_at": _now_iso(),
                    "processed": processed,
                    "total": processed,
                    "created": created,
                    "updated": updated,
                    "errors": errors,
                }
            )
            write_sync(org, SOURCE_KEY, sync)
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — erro global (ex.: auth/rede): vira status='error'.
            await session.rollback()
            org = await _reload_org(session)
            if org is not None:
                sync = sync_state(org, SOURCE_KEY)
                sync.update(
                    {
                        "status": "error",
                        "finished_at": _now_iso(),
                        "processed": processed,
                        "total": processed,
                        "created": created,
                        "updated": updated,
                        "errors": errors,
                        "error_msg": _safe_error(exc),
                    }
                )
                write_sync(org, SOURCE_KEY, sync)
                await session.commit()
            logger.warning("run_bizzu_sync: falha global (%s) — sync marcado como error", type(exc).__name__)
