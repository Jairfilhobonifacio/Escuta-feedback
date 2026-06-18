"""Diagnóstico (read-only) do universo de churn: cruza state da assinatura, perfil
de segmentação e feedbacks type=churn, p/ entender por que o universo da campanha
diverge de 'quem cancelou'. Não grava nada. Uso: py scripts/_analise_universo.py
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()

import asyncio
import collections
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
import app.models.improvement  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401
import app.models.cluster  # noqa: E402,F401
import app.models.playbook  # noqa: E402,F401


async def main() -> None:
    if SessionLocal is None:
        print("DATABASE_URL nao configurada"); return
    async with SessionLocal() as s:
        org = (
            await s.execute(select(Organization).where(Organization.slug == os.getenv("DEFAULT_ORG_SLUG", "bizzu")))
        ).scalar_one_or_none()
        if org is None:
            print("org nao encontrada"); return

        contacts = (await s.execute(select(Contact).where(Contact.organization_id == org.id))).scalars().all()
        churn_fb = set(
            (await s.execute(
                select(FeedbackItem.contact_id).where(
                    FeedbackItem.organization_id == org.id, FeedbackItem.type == "churn"
                )
            )).scalars().all()
        )

        states = collections.Counter()
        perfis = collections.Counter()
        sem_partner = 0
        uni_perfil_ou_fb = 0
        cancelled = 0
        cancelled_fora_universo = 0

        for c in contacts:
            partner = (c.profile_data or {}).get("partner") or {}
            if not partner:
                sem_partner += 1
            sub = partner.get("subscription") or {}
            state = str(sub.get("state") or "(sem state)")
            perfil = str(partner.get("profile") or "(sem perfil)")
            states[state] += 1
            perfis[perfil] += 1

            is_churn_perfil = perfil.startswith("churn")
            is_churn_fb = c.id in churn_fb
            is_cancelled = "cancel" in state.lower()

            if is_churn_perfil or is_churn_fb:
                uni_perfil_ou_fb += 1
            if is_cancelled:
                cancelled += 1
                if not (is_churn_perfil or is_churn_fb):
                    cancelled_fora_universo += 1

        print(f"== ORG {org.slug} ==")
        print(f"Contacts no Escuta: {len(contacts)}  | sem snapshot partner: {sem_partner}")
        print(f"Contacts com FeedbackItem type=churn: {len(churn_fb)}")
        print("\n-- por subscription.state --")
        for k, v in states.most_common():
            print(f"  {k:28} {v}")
        print("\n-- por perfil (segmentacao) --")
        for k, v in perfis.most_common():
            print(f"  {k:28} {v}")
        print("\n== UNIVERSO ==")
        print(f"  Universo ATUAL (perfil churn OU fb churn): {uni_perfil_ou_fb}")
        print(f"  Contacts com state cancelled*: {cancelled}")
        print(f"  Cancelados FORA do universo atual (perdidos): {cancelled_fora_universo}")
        print(f"  Universo CORRETO (cancelled OU perfil churn OU fb churn): {uni_perfil_ou_fb + cancelled_fora_universo}")


asyncio.run(main())
