"""Gera (e opcionalmente envia) o digest semanal da Voz do Cliente.

Por padrão é DRY-RUN: monta e imprime o texto, sem enviar. Com --send, manda
no WhatsApp do dono (Organization.settings['owner_phone']) via WAHA.

Uso:
    py scripts/send_digest.py [--org bizzu] [--days 7] [--send]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import truststore

truststore.inject_into_ssl()  # Groq via TLS interceptado pelo antivírus

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass


async def run(org_slug: str, days: int, send: bool) -> int:
    from sqlalchemy import select
    from app.config import settings
    from app.db import SessionLocal
    from app.domain.digest.service import build_digest, send_digest
    from app.domain.survey.brain import SurveyBrain
    from app.models.core import Organization
    from app.services.llm import GroqLLM
    from app.services.waha import WAHAService

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada.", file=sys.stderr)
        return 1

    brain = (
        SurveyBrain(GroqLLM(settings.groq_api_key, settings.groq_model))
        if settings.llm_enabled and settings.groq_api_key
        else None
    )

    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if org is None:
            print(f"ERRO: org '{org_slug}' não existe.", file=sys.stderr)
            return 1

        if not send:
            text, data = await build_digest(session, org.id, brain, days)
            print("=" * 56)
            print(f"DIGEST (DRY-RUN) — org '{org_slug}', janela {days}d, brain={'on' if brain else 'off'}")
            print("=" * 56)
            print(text)
            print("=" * 56)
            owner = (org.settings or {}).get("owner_phone")
            print(f"owner_phone: {owner or '(não configurado — use --send falharia)'}")
            print(f"atividade: sent={data.sent} answered={data.answered} nps={data.nps} "
                  f"temas={data.top_themes} urgentes={len(data.urgent)} churn={len(data.churn)}")
            return 0

        messaging = WAHAService(settings.waha_base_url, settings.waha_api_key, settings.waha_session)
        result = await send_digest(session, org.id, brain, messaging, days, settings.waha_session)
        if result.get("sent"):
            print(f"=== Digest ENVIADO para {result['to']} ===")
            print(result["text"])
        else:
            print(f"=== NÃO enviado: {result.get('reason')} ===")
            print(result.get("text", ""))
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Digest semanal da Voz do Cliente.")
    p.add_argument("--org", default="bizzu")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--send", action="store_true", help="envia de verdade (default: dry-run)")
    args = p.parse_args(argv)
    return asyncio.run(run(args.org, args.days, args.send))


if __name__ == "__main__":
    raise SystemExit(main())
