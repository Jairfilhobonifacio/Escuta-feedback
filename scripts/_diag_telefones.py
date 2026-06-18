"""DIAGNÓSTICO read-only: classifica os telefones dos contatos para saber, de verdade,
quem é alcançável no WhatsApp (celular BR válido) x fixo/malformado x só-email.

NÃO grava nada (rollback no fim). Uso:
    py scripts/_diag_telefones.py
    py scripts/_diag_telefones.py --org bizzu
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import Counter

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sqlalchemy import select  # noqa: E402

from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
import app.models.improvement  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401
import app.models.cluster  # noqa: E402,F401
import app.models.playbook  # noqa: E402,F401


def classificar(phone: str | None) -> str:
    """Classe estrutural do telefone (não consulta WhatsApp; só o formato)."""
    if not phone or not str(phone).strip():
        return "vazio"
    p = str(phone).strip()
    if p.startswith("nowa-"):
        return "placeholder_nowa"
    digitos = re.sub(r"\D", "", p)
    # Normaliza tirando DDI 55 quando presente.
    nac = digitos[2:] if digitos.startswith("55") and len(digitos) >= 12 else digitos
    if len(nac) == 11 and nac[2] == "9":
        # DDD(2) + 9 + 8 dígitos = celular BR -> alcançável no WhatsApp.
        return "celular_br_valido"
    if len(nac) == 10:
        # DDD(2) + 8 dígitos. Sem o 9: tipicamente FIXO (não WhatsApp).
        return "fixo_br_10d"
    if len(nac) == 11 and nac[2] != "9":
        return "11d_sem_9"  # 11 dígitos mas 3º não é 9 -> suspeito
    if len(nac) < 10:
        return "curto_invalido"
    if len(digitos) > 13:
        return "longo_estrangeiro?"
    return f"outro_{len(nac)}d"


async def _amain(org_slug: str) -> None:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass

    from app.db import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL não configurada")

    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"org '{org_slug}' não encontrada")

        contatos = (
            (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
            .scalars()
            .all()
        )

        # Universo de churn: subscription.state in {cancelled, paid_without_access} OU
        # perfil começa com 'churn' OU tem FeedbackItem type=='churn'.
        churn_fb_ids = set(
            (
                await session.execute(
                    select(FeedbackItem.contact_id)
                    .where(
                        FeedbackItem.organization_id == org.id,
                        FeedbackItem.type == "churn",
                        FeedbackItem.contact_id.is_not(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        def is_churn(c: Contact) -> bool:
            pd = c.profile_data or {}
            partner = pd.get("partner") or {}
            state = ((partner.get("subscription") or {}).get("state")) or ""
            perfil = str(partner.get("profile") or "")
            return (
                state in {"cancelled", "paid_without_access"}
                or perfil.startswith("churn")
                or (c.id in churn_fb_ids)
            )

        geral: Counter[str] = Counter()
        churn: Counter[str] = Counter()
        amostra_fixo: list[str] = []
        amostra_outro: list[str] = []
        for c in contatos:
            cls = classificar(c.phone)
            geral[cls] += 1
            if is_churn(c):
                churn[cls] += 1
            if cls in {"fixo_br_10d", "11d_sem_9"} and len(amostra_fixo) < 8:
                amostra_fixo.append(f"{c.name or '?'} -> {c.phone}")
            if cls.startswith("outro_") or cls in {"curto_invalido", "longo_estrangeiro?"}:
                if len(amostra_outro) < 8:
                    amostra_outro.append(f"{c.name or '?'} -> {c.phone}")

        def bloco(titulo: str, cont: Counter[str]) -> None:
            total = sum(cont.values())
            print(f"\n=== {titulo} (total {total}) ===")
            wa = cont.get("celular_br_valido", 0)
            print(f"  WhatsApp REAL (celular BR válido): {wa}")
            for k in sorted(cont, key=lambda x: -cont[x]):
                print(f"    {k:24s} {cont[k]}")

        bloco("TODOS os contatos da org", geral)
        bloco("Universo de CHURN", churn)

        print("\n--- amostra 'fixo/sem 9' (provável NÃO WhatsApp) ---")
        for s in amostra_fixo:
            print("   ", s)
        if amostra_outro:
            print("--- amostra 'outro/malformado' ---")
            for s in amostra_outro:
                print("   ", s)

        await session.rollback()


def main() -> None:
    from app.config import settings

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--org", default=None)
    args = p.parse_args()
    asyncio.run(_amain(args.org or settings.default_org_slug))


if __name__ == "__main__":
    main()
