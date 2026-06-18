"""Sync de contatos Bizzu → Escuta (piloto, 1 sentido).

Lê usuários da Bizzu com telefone + consentimento de WhatsApp
(usuarios.whatsappOptIn = true, não deletados) direto do Postgres deles e faz
upsert em `contacts` da org 'bizzu' no Escuta:

  - contato novo  → cria com opt_in=True, nome e profile_data.bizzu_user_id
  - já existe     → eleva opt_in se estava False, preenche nome/bizzu_user_id
                    se ausentes (nunca sobrescreve nome já preenchido)

Idempotente: rodar N vezes converge. NÃO dispara mensagem nenhuma (só dados);
por isso o default executa de verdade — use --dry-run para só inspecionar.

Envs:
  DATABASE_URL        — Supabase do Escuta (postgresql+asyncpg://...), via .env
  BIZZU_DATABASE_URL  — Postgres da Bizzu (obrigatória), ex.:
                        postgresql://USER:SENHA@localhost:5432/plataforma
                        Defina no .env / ambiente; sem default por conter senha.

Uso:
    py scripts/sync_bizzu_contacts.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:
    pass

ORG_SLUG = "bizzu"


def _bizzu_database_url() -> str:
    """URL do Postgres da Bizzu, lida do ambiente (nunca hardcoded).

    Sem default: a string contém credenciais. Defina BIZZU_DATABASE_URL no
    .env ou no ambiente antes de rodar.
    """
    url = os.getenv("BIZZU_DATABASE_URL")
    if not url:
        raise SystemExit(
            "ERRO: variável de ambiente BIZZU_DATABASE_URL não definida.\n"
            "      Defina-a com a string de conexão do Postgres da Bizzu, ex.:\n"
            "        postgresql://USER:SENHA@localhost:5432/plataforma\n"
            "      (no .env do Escuta ou exportando no shell)."
        )
    return url


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


async def _fetch_bizzu_users() -> list[dict]:
    """Usuários da Bizzu elegíveis: telefone + whatsappOptIn, vivos."""
    import asyncpg

    conn = await asyncpg.connect(_bizzu_database_url())
    try:
        rows = await conn.fetch(
            '''
            SELECT id::text AS bizzu_user_id,
                   "primeiroNome" || ' ' || "ultimoNome" AS name,
                   telefone
            FROM usuarios
            WHERE telefone IS NOT NULL
              AND "whatsappOptIn" = true
              AND "deletedAt" IS NULL
            ORDER BY "createdAt"
            '''
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def sync(dry_run: bool) -> int:
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.core import Contact, Organization

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada (Supabase do Escuta).", file=sys.stderr)
        return 1

    users = await _fetch_bizzu_users()
    print(f"Bizzu: {len(users)} usuário(s) com telefone + whatsappOptIn")

    created = updated = unchanged = invalid = 0
    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == ORG_SLUG))
        ).scalar_one_or_none()
        if org is None:
            print(f"ERRO: org '{ORG_SLUG}' não existe no Escuta (rode o seed).", file=sys.stderr)
            return 1

        for u in users:
            phone = _digits_only(u["telefone"])
            if len(phone) < 10:
                invalid += 1
                print(f"  ~ telefone inválido, pulado: {u['telefone']!r} (user {u['bizzu_user_id']})")
                continue

            contact = (
                await session.execute(
                    select(Contact).where(
                        Contact.organization_id == org.id, Contact.phone == phone
                    )
                )
            ).scalar_one_or_none()

            if contact is None:
                created += 1
                print(f"  + criar {phone} name={u['name']!r}")
                if not dry_run:
                    session.add(
                        Contact(
                            organization_id=org.id,
                            phone=phone,
                            name=(u["name"] or "").strip() or None,
                            opt_in=True,
                            profile_data={"bizzu_user_id": u["bizzu_user_id"]},
                        )
                    )
                continue

            changes: list[str] = []
            if not contact.opt_in:
                changes.append("opt_in→True")
                if not dry_run:
                    contact.opt_in = True
            if not contact.name and u["name"]:
                changes.append(f"name→{u['name']!r}")
                if not dry_run:
                    contact.name = u["name"].strip()
            profile = dict(contact.profile_data or {})
            if "bizzu_user_id" not in profile:
                changes.append("bizzu_user_id")
                if not dry_run:
                    profile["bizzu_user_id"] = u["bizzu_user_id"]
                    contact.profile_data = profile

            if changes:
                updated += 1
                print(f"  ~ atualizar {phone}: {', '.join(changes)}")
            else:
                unchanged += 1

        if not dry_run:
            await session.commit()

    modo = "DRY-RUN (nada gravado)" if dry_run else "executado"
    print(
        f"=== Sync {modo}: {created} criado(s), {updated} atualizado(s), "
        f"{unchanged} já em dia, {invalid} inválido(s) ==="
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync de contatos Bizzu → Escuta (1 sentido).")
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que faria")
    args = parser.parse_args(argv)
    return asyncio.run(sync(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
