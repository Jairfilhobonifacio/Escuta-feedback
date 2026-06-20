"""Backfill único: migra os action_status LEGADOS (bug-tracker) para o vocabulário
de ACOMPANHAMENTO (relacionamento).

Contexto: os status do feed deixaram de ser de bug-tracker (`novo`/`em_analise`/
`planejado`/`resolvido`/`descartado`) e passaram a ser de acompanhamento de
relacionamento (`a_abordar`/`aguardando_retorno`/`em_acompanhamento`/`resolvido`/
`sem_retorno`/`descartado`) — ver docs/BENCHMARK_ACOMPANHAMENTO_2026-06-20.md. Como
`action_status` é uma STRING LIVRE (sem CHECK/enum no banco), trocar o vocabulário NÃO
exige migration de schema; mas os valores JÁ gravados precisam ser remapeados para não
ficarem com rótulo cru no histórico. Este script faz esse remapeamento, uma vez.

Mapa de migração (os demais ficam INALTERADOS):
    novo       -> a_abordar
    em_analise -> em_acompanhamento
    planejado  -> em_acompanhamento
    (resolvido / descartado: mantidos; key e significado preservados)

Idempotente: só toca FeedbackItems cujo action_status ainda é uma das keys LEGADAS.
Re-rodar depois do --apply não encontra mais nenhuma (as keys legadas sumiram) e não
muda nada. Aditivo/seguro: nunca apaga feedbacks, nunca dispara WhatsApp, nunca toca
survey_responses/contatos — só reescreve o campo action_status.

Uso (DRY-RUN por padrão, nada grava):
    py scripts/backfill_status_acompanhamento.py
    py scripts/backfill_status_acompanhamento.py --apply           # grava no Supabase
    py scripts/backfill_status_acompanhamento.py --org bizzu --apply

Env:
    DATABASE_URL — Supabase do Escuta (postgresql+asyncpg://...), via .env (padrão
    dos outros scripts). TLS via truststore (Avast intercepta).
"""
from __future__ import annotations

# Fix TLS ANTES de qualquer import que abra conexão TLS (asyncpg ao Supabase). Global
# por processo — espelha app/main.py e os outros scripts standalone.
import truststore

truststore.inject_into_ssl()

import argparse
import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# .env -> ambiente (DATABASE_URL). app.db lê o env no import; carregar antes.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
except Exception:  # noqa: BLE001 — sem python-dotenv, conta-se com o env já exportado.
    pass

from sqlalchemy import func, select, update  # noqa: E402

from app.models.core import Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402

# Registra TODAS as tabelas no metadata (FKs de feedback/improvement/survey/cluster/
# playbook). Sem isso o SQLAlchemy não resolve as FKs ao montar os models -> erro.
import app.models.improvement  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401
import app.models.cluster  # noqa: E402,F401
import app.models.playbook  # noqa: E402,F401

# Mapa de migração: action_status LEGADO -> novo de acompanhamento. As keys ausentes
# (resolvido/descartado) ficam inalteradas — não estão aqui de propósito.
_STATUS_MIGRATION: dict[str, str] = {
    "novo": "a_abordar",
    "em_analise": "em_acompanhamento",
    "planejado": "em_acompanhamento",
}


async def _amain(org_slug: str, apply: bool) -> None:
    from app.db import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL não configurada (app.db.SessionLocal é None)")

    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"org '{org_slug}' não encontrada")

        # Quantos itens há por status legado (org-scoped) — diagnóstico + plano.
        legacy_counts: dict[str, int] = {}
        for legado in _STATUS_MIGRATION:
            n = (
                await session.execute(
                    select(func.count())
                    .select_from(FeedbackItem)
                    .where(
                        FeedbackItem.organization_id == org.id,
                        FeedbackItem.action_status == legado,
                    )
                )
            ).scalar_one()
            legacy_counts[legado] = int(n or 0)

        total = sum(legacy_counts.values())
        suffix = "" if apply else "  (DRY-RUN — nada gravado; use --apply p/ gravar)"
        print(f"org '{org_slug}': feedbacks com status legado a migrar: {total}{suffix}")
        for legado, novo in _STATUS_MIGRATION.items():
            print(f"  {legado:<12} -> {novo:<18} : {legacy_counts[legado]}")

        if total == 0:
            print("\nNada a fazer (idempotente): nenhum status legado encontrado.")
            await session.rollback()
            return

        if not apply:
            await session.rollback()
            return

        # UPDATE em lote por status legado (um por mapeamento). Só toca quem ainda está
        # na key legada -> idempotente. rowcount confirma o que mudou.
        migrados: dict[str, int] = {}
        for legado, novo in _STATUS_MIGRATION.items():
            res = await session.execute(
                update(FeedbackItem)
                .where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.action_status == legado,
                )
                .values(action_status=novo)
            )
            migrados[legado] = int(res.rowcount or 0)
        await session.commit()

        print("\n=== Backfill aplicado ===")
        for legado, novo in _STATUS_MIGRATION.items():
            print(f"  {legado:<12} -> {novo:<18} : {migrados.get(legado, 0)} atualizados")
        print(f"  TOTAL atualizado: {sum(migrados.values())}")


def main() -> None:
    from app.config import settings

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--org", default=None, help="slug da org (default: settings.default_org_slug)")
    p.add_argument("--apply", action="store_true", help="grava (sem isso é dry-run)")
    args = p.parse_args()
    asyncio.run(_amain(args.org or settings.default_org_slug, args.apply))


if __name__ == "__main__":
    main()
