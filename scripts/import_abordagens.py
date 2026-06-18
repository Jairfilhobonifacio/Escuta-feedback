"""Fecha o loop da campanha de churn: importa as abordagens (worklist → mega central).

O worklist `docs/campanhas/_abordagem-churn.template.html` guarda, por cliente, o que o
operador apurou na conversa (por que saiu · o que faltou · o que faria voltar) + flags
(quer call / respondeu áudio / disse que voltaria). Esse conhecimento precisa VOLTAR pra
central — senão fica preso no navegador. Aqui ele vira `FeedbackItem` (type=churn,
abordado=True) e aparece na ficha 360, no feed e nos clusters como qualquer outro sinal.

Entrada: um JSON exportado do worklist (botão "📤 Exportar p/ central"):
    [
      {"whatsapp": "5531...", "nome": "Fulano",
       "motivo": "achei caro", "faltou": "mais simulados", "voltaria": "se baixar o preço",
       "flags": {"quer_call": true, "audio": false, "reativavel": true},
       "abordado_em": "2026-06-12T15:00:00Z"}
    ]

Idempotente por (contato, source): re-importar ATUALIZA a abordagem do cliente (uma por
cliente/campanha), nunca duplica. Uso:
    py scripts/import_abordagens.py --file docs/campanhas/abordagens-export.json
    py scripts/import_abordagens.py --file ... --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sqlalchemy import select  # noqa: E402

from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402

# Registra as demais tabelas no metadata (FeedbackItem.improvement_id → improvements;
# mapeamentos de survey). Sem isso, o SQLAlchemy não resolve a FK ao montar o model.
import app.models.improvement  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401

CAMPANHA_SOURCE = "campanha_churn"


@dataclass
class IngestResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def as_dict(self) -> dict:
        return {"created": self.created, "updated": self.updated, "skipped": self.skipped}


def _parse_dt(value) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _build_text(reg: dict) -> str:
    linhas: list[str] = []
    if reg.get("motivo"):
        linhas.append(f"Por que saiu: {str(reg['motivo']).strip()}")
    if reg.get("faltou"):
        linhas.append(f"O que faltou: {str(reg['faltou']).strip()}")
    if reg.get("voltaria"):
        linhas.append(f"O que faria voltar: {str(reg['voltaria']).strip()}")
    return "\n".join(linhas)


def _build_themes(flags: dict) -> list[str]:
    themes = ["churn"]
    if flags.get("quer_call"):
        themes.append("quer_call")
    if flags.get("audio"):
        themes.append("respondeu_audio")
    if flags.get("reativavel"):
        themes.append("reativavel")
    return themes


async def ingest_abordagens(session, org: Organization, registros: list[dict]) -> IngestResult:
    """Cria/atualiza um FeedbackItem (type=churn, source=campanha_churn) por contato.

    Idempotente por (contato, source): re-rodar atualiza texto/flags/abordado_em em vez
    de duplicar. Pula registros sem whatsapp ou sem nada apurado (texto e flags vazios).
    """
    res = IngestResult()
    for reg in registros:
        phone = str(reg.get("whatsapp") or reg.get("phone") or "").strip()
        if not phone:
            res.skipped += 1
            continue
        flags = reg.get("flags") or {}
        text = _build_text(reg)
        if not text and not any(flags.values()):
            res.skipped += 1  # nada apurado — não vira sinal
            continue

        contact = (
            await session.execute(
                select(Contact).where(Contact.organization_id == org.id, Contact.phone == phone)
            )
        ).scalar_one_or_none()
        if contact is None:
            contact = Contact(
                organization_id=org.id, phone=phone, name=reg.get("nome"), opt_in=False
            )
            session.add(contact)
            await session.flush()

        occurred = _parse_dt(reg.get("abordado_em"))
        themes = _build_themes(flags)
        extra = {"campanha": "churn", "flags": {k: bool(v) for k, v in flags.items()}}

        existing = (
            (
                await session.execute(
                    select(FeedbackItem).where(
                        FeedbackItem.organization_id == org.id,
                        FeedbackItem.contact_id == contact.id,
                        FeedbackItem.source == CAMPANHA_SOURCE,
                    )
                )
            )
            .scalars()
            .first()
        )

        if existing is not None:
            existing.text = text or existing.text
            existing.themes = themes
            existing.extra = extra
            existing.abordado = True
            existing.abordado_em = occurred
            existing.occurred_at = occurred
            res.updated += 1
        else:
            session.add(
                FeedbackItem(
                    organization_id=org.id,
                    contact_id=contact.id,
                    source=CAMPANHA_SOURCE,
                    type="churn",
                    text=text or None,
                    sentiment="negativo",
                    themes=themes,
                    occurred_at=occurred,
                    abordado=True,
                    abordado_em=occurred,
                    extra=extra,
                )
            )
            res.created += 1

    await session.flush()
    return res


async def _amain(file_path: str, org_slug: str, dry_run: bool) -> None:
    # Avast intercepta TLS → usa o trust store do sistema (mesmo padrão do app/main.py)
    # para o asyncpg conectar ao Supabase. Best-effort, nunca bloqueia.
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass

    from app.db import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL não configurada (app.db.SessionLocal é None)")

    with open(file_path, "r", encoding="utf-8") as fh:
        registros = json.load(fh)
    if not isinstance(registros, list):
        raise SystemExit("JSON inválido: esperado uma LISTA de abordagens")

    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"org '{org_slug}' não encontrada")
        res = await ingest_abordagens(session, org, registros)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    suffix = " (dry-run, nada gravado)" if dry_run else ""
    print(f"abordagens importadas: {res.as_dict()}{suffix}")


def main() -> None:
    from app.config import settings

    p = argparse.ArgumentParser(
        description="Importa abordagens da campanha de churn para a mega central (fecha o loop)."
    )
    p.add_argument("--file", required=True, help="JSON exportado do worklist")
    p.add_argument("--org", default=None, help="slug da org (default: settings.default_org_slug)")
    p.add_argument("--dry-run", action="store_true", help="não grava, só conta")
    args = p.parse_args()
    asyncio.run(_amain(args.file, args.org or settings.default_org_slug, args.dry_run))


if __name__ == "__main__":
    main()
