"""Backfill único: aplica o selo 'contatado' a quem JÁ foi abordado mas não tinha o selo.

Contexto: registrar uma abordagem (POST /contacts/{id}/outreach) agora aplica o selo
'contatado' automaticamente — mas os contatos abordados ANTES dessa mudança ficaram com
abordagem registrada (ou FeedbackItem.abordado=True) e SEM o selo. Resultado: o board de
clientes (coluna "Contatado", baseada no selo) mostrava menos gente que os stats (que
contam abordagem OU selo OU flag). Este script reconcilia os dois, uma vez.

"Foi abordado" = `profile_data["abordagens"]` não-vazio OU algum FeedbackItem.abordado=True.
Idempotente e aditivo: só ADICIONA o selo 'contatado' a quem não tem; nunca remove nada.

Uso (dry-run por padrão, nada grava):
    py scripts/backfill_selo_contatado.py
    py scripts/backfill_selo_contatado.py --apply        # grava no Supabase
    py scripts/backfill_selo_contatado.py --org bizzu --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sqlalchemy import select  # noqa: E402

from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402

# Registra TODAS as tabelas no metadata (FKs de feedback/improvement/survey/cluster/
# playbook). Sem isso o SQLAlchemy não resolve as FKs ao montar os models -> erro.
import app.models.improvement  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401
import app.models.cluster  # noqa: E402,F401
import app.models.playbook  # noqa: E402,F401

from app.api.campanha import (  # noqa: E402
    SELO_CONTATADO,
    _abordagens_do_contato,
    _selos_do_contato,
    _set_selos_do_contato,
    _upsert_catalogo,
)


async def _amain(org_slug: str, apply: bool) -> None:
    # Avast intercepta TLS → trust store do sistema (mesmo padrão do app/main.py).
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass

    from app.db import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL não configurada (app.db.SessionLocal é None)")

    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"org '{org_slug}' não encontrada")

        # Contatos cujo contato_id aparece em algum FeedbackItem abordado=True.
        abordado_ids = set(
            (
                await session.execute(
                    select(FeedbackItem.contact_id)
                    .where(
                        FeedbackItem.organization_id == org.id,
                        FeedbackItem.abordado.is_(True),
                        FeedbackItem.contact_id.is_not(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        contatos = (
            (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
            .scalars()
            .all()
        )

        atualizados: list[str] = []
        ja_tinham = 0
        for c in contatos:
            foi_abordado = bool(_abordagens_do_contato(c)) or (c.id in abordado_ids)
            if not foi_abordado:
                continue
            selos = _selos_do_contato(c)
            if SELO_CONTATADO in selos:
                ja_tinham += 1
                continue
            _set_selos_do_contato(c, [*selos, SELO_CONTATADO])
            atualizados.append(c.name or c.phone or str(c.id))

        if atualizados:
            _upsert_catalogo(org, SELO_CONTATADO, None)

        suffix = "" if apply else "  (DRY-RUN — nada gravado; use --apply p/ gravar)"
        print(f"abordados sem selo -> aplicar 'contatado': {len(atualizados)}{suffix}")
        print(f"abordados que JÁ tinham o selo: {ja_tinham}")
        for nome in atualizados:
            print(f"  + {nome}")

        if apply and atualizados:
            await session.commit()
            print(f"\nOK: {len(atualizados)} contatos receberam o selo 'contatado'.")
        else:
            await session.rollback()


def main() -> None:
    from app.config import settings

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--org", default=None, help="slug da org (default: settings.default_org_slug)")
    p.add_argument("--apply", action="store_true", help="grava (sem isso é dry-run)")
    args = p.parse_args()
    asyncio.run(_amain(args.org or settings.default_org_slug, args.apply))


if __name__ == "__main__":
    main()
