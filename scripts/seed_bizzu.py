"""Seed IDEMPOTENTE do tenant-piloto Bizzu (org + survey NPS + contatos de teste).

Cria (ou reaproveita, se já existirem) os dados mínimos para tocar o piloto:
  - Organization(slug='bizzu', name='Bizzu')
  - Survey(name='NPS Bizzu', type='nps', status='active') com 2 perguntas (nps + open)
  - N contatos de teste com opt_in=True

100% async (SQLAlchemy 2.0: AsyncSession + select()). Toda query filtra por chave
única (slug / (org_id, name) / (org_id, phone)) ANTES de inserir, então rodar o
script 2x não duplica nada.

Como rodar (precisa de DATABASE_URL = postgresql+asyncpg://...):

    # Linha de comando (PowerShell):
    $env:PYTHONUTF8=1
    $env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
    python scripts/seed_bizzu.py

    # Telefones customizados (apenas dígitos: DDI+DDD+numero):
    python scripts/seed_bizzu.py --phones 5531999998888,5531888887777

Sem DATABASE_URL o script imprime instruções e sai com código != 0 (não tenta
conectar em banco nenhum).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

# Permite rodar standalone (`python scripts/seed_bizzu.py`) sem instalar o pacote:
# garante que a raiz do projeto esteja no sys.path para `import app...` resolver.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Carrega .env (se python-dotenv estiver instalado) ANTES de importar app.config /
# app.db, pois ambos avaliam as variáveis de ambiente no momento do import.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:  # python-dotenv ausente ou .env inexistente: seguimos com o ambiente atual.
    pass


# --- Dados do seed -------------------------------------------------------------

ORG_SLUG = "bizzu"
ORG_NAME = "Bizzu"

SURVEY_NAME = "NPS Bizzu"
SURVEY_TYPE = "nps"
SURVEY_STATUS = "active"
SURVEY_QUESTIONS = [
    {
        "key": "nps",
        "kind": "nps",
        "text": "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?",
    },
    {
        "key": "reason",
        "kind": "open",
        "text": "Massa! 🙌 Por quê? (pode mandar em texto)",
    },
]

# Política do projeto (07/06): SEM dados mockados. O seed não cria mais contatos
# fictícios — telefones reais via --phones são obrigatórios (org+survey seguem ok).


def _digits_only(value: str) -> str:
    """Mantém apenas dígitos (DDI+DDD+numero), descartando +, espaços, hífens etc."""
    return re.sub(r"\D", "", value or "")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed idempotente do tenant-piloto Bizzu (org + survey NPS + contatos).",
    )
    parser.add_argument(
        "--phones",
        type=str,
        default=None,
        help=(
            "Lista de telefones REAIS separados por vírgula (apenas dígitos: "
            "DDI+DDD+numero), ex.: 5531999998888,5531888887777. Obrigatório para "
            "criar contatos — sem ele o seed cria/garante apenas org + survey."
        ),
    )
    return parser.parse_args(argv)


def _contacts_from_args(phones_arg: str | None) -> list[dict[str, str | None]]:
    """Monta a lista de contatos a partir do --phones (sem fallback fictício)."""
    if not phones_arg:
        return []

    contacts: list[dict[str, str | None]] = []
    for i, raw in enumerate(phones_arg.split(","), start=1):
        phone = _digits_only(raw)
        if not phone:
            continue
        contacts.append({"phone": phone, "name": f"Contato {i}"})
    return contacts


# --- Lógica de seed (async, SQLAlchemy 2.0) ------------------------------------


async def _get_or_create_org(session, name: str, slug: str):
    """get-or-create por slug (unique)."""
    from sqlalchemy import select
    from app.models.core import Organization

    existing = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    org = Organization(slug=slug, name=name, settings={})
    session.add(org)
    # flush para obter o id gerado (default=uuid.uuid4) antes de usá-lo nas FKs.
    await session.flush()
    return org, True


async def _get_or_create_survey(session, organization_id):
    """get-or-create por (organization_id, name) (unique)."""
    from sqlalchemy import select
    from app.models.survey import Survey

    existing = (
        await session.execute(
            select(Survey).where(
                Survey.organization_id == organization_id,
                Survey.name == SURVEY_NAME,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    survey = Survey(
        organization_id=organization_id,
        name=SURVEY_NAME,
        type=SURVEY_TYPE,
        status=SURVEY_STATUS,
        questions=SURVEY_QUESTIONS,
    )
    session.add(survey)
    await session.flush()
    return survey, True


async def _get_or_create_contact(session, organization_id, phone: str, name: str | None):
    """get-or-create por (organization_id, phone) (unique). Sempre com opt_in=True."""
    from sqlalchemy import select
    from app.models.core import Contact

    existing = (
        await session.execute(
            select(Contact).where(
                Contact.organization_id == organization_id,
                Contact.phone == phone,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    contact = Contact(
        organization_id=organization_id,
        phone=phone,
        name=name,
        opt_in=True,
        profile_data={},
    )
    session.add(contact)
    await session.flush()
    return contact, True


async def seed(contacts_spec: list[dict[str, str | None]]) -> int:
    """Executa o seed dentro de uma única transação. Retorna o exit code."""
    # Import tardio: db.py avalia SessionLocal no import a partir de DATABASE_URL.
    from app.db import SessionLocal

    if SessionLocal is None:
        print(
            "ERRO: DATABASE_URL não configurada — não há engine de banco.\n"
            "\n"
            "Defina a variável de ambiente (postgresql+asyncpg) e rode de novo. Ex.:\n"
            '  PowerShell:  $env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"\n'
            "  bash:        export DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db\n"
            "\n"
            "Você também pode criar um arquivo .env na raiz (veja .env.example) — ele é\n"
            "carregado automaticamente se python-dotenv estiver instalado.",
            file=sys.stderr,
        )
        return 1

    async with SessionLocal() as session:
        org, org_created = await _get_or_create_org(session, ORG_NAME, ORG_SLUG)
        survey, survey_created = await _get_or_create_survey(session, org.id)

        contact_results: list[tuple[object, bool]] = []
        for spec in contacts_spec:
            phone = str(spec["phone"])
            name = spec.get("name")
            contact, created = await _get_or_create_contact(session, org.id, phone, name)
            contact_results.append((contact, created))

        await session.commit()

    # --- Resumo --------------------------------------------------------------
    print("=== Seed Bizzu concluído ===")
    print(
        f"Organization: id={org.id} slug={org.slug!r} name={org.name!r} "
        f"[{'criada' if org_created else 'existente'}]"
    )
    print(
        f"Survey:       id={survey.id} name={survey.name!r} type={survey.type!r} "
        f"status={survey.status!r} [{'criado' if survey_created else 'existente'}] "
        f"({len(survey.questions)} perguntas)"
    )
    print(f"Contatos ({len(contact_results)}):")
    for contact, created in contact_results:
        marca = "criado" if created else "existente"
        print(
            f"  - id={contact.id} phone={contact.phone} name={contact.name!r} "
            f"opt_in={contact.opt_in} [{marca}]"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    contacts_spec = _contacts_from_args(args.phones)
    if args.phones is not None and not contacts_spec:
        print(
            "ERRO: nenhum telefone válido em --phones (use apenas dígitos: DDI+DDD+numero).",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(seed(contacts_spec))


if __name__ == "__main__":
    raise SystemExit(main())
