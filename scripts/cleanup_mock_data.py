"""Remove os dados mockados/fictícios do banco (one-shot, idempotente).

O que remove:
  - SurveyResponses de contatos fictícios OU com channel_msg_id de mock ('mock-%')
  - Os contatos fictícios do seed antigo (5531999990001/2)
  - SurveyRuns que ficarem sem nenhuma response

O que preserva: org 'bizzu', survey 'NPS Bizzu', contatos reais e responses reais
(inclusive a do teste E2E real de 07/06). Também corrige o nome do contato real
do piloto (estava com o nome genérico do seed).

Rodar:  PYTHONUTF8=1 py scripts/cleanup_mock_data.py
"""
from __future__ import annotations

import asyncio
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:
    pass

FAKE_PHONES = ["5531999990001", "5531999990002"]
REAL_PILOT = {"phone": "5524998365809", "name": "Jair Filho"}


async def main() -> int:
    from sqlalchemy import delete, select, update

    from app.db import SessionLocal
    from app.models.core import Contact
    from app.models.survey import SurveyResponse, SurveyRun

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada.", file=sys.stderr)
        return 1

    async with SessionLocal() as session:
        # ids dos contatos fictícios
        fake_ids = (
            (await session.execute(select(Contact.id).where(Contact.phone.in_(FAKE_PHONES))))
            .scalars()
            .all()
        )

        # 1. responses dos fictícios + responses de mock (channel_msg_id 'mock-%')
        cond = SurveyResponse.channel_msg_id.like("mock-%")
        if fake_ids:
            cond = cond | SurveyResponse.contact_id.in_(fake_ids)
        n_resp = len((await session.execute(delete(SurveyResponse).where(cond).returning(SurveyResponse.id))).all())

        # 2. contatos fictícios
        n_contacts = 0
        if fake_ids:
            n_contacts = len(
                (await session.execute(delete(Contact).where(Contact.id.in_(fake_ids)).returning(Contact.id))).all()
            )

        # 3. runs órfãos (sem nenhuma response)
        orphan_runs = (
            (
                await session.execute(
                    select(SurveyRun.id).where(
                        ~select(SurveyResponse.id)
                        .where(SurveyResponse.survey_run_id == SurveyRun.id)
                        .exists()
                    )
                )
            )
            .scalars()
            .all()
        )
        n_runs = 0
        if orphan_runs:
            n_runs = len(
                (await session.execute(delete(SurveyRun).where(SurveyRun.id.in_(orphan_runs)).returning(SurveyRun.id))).all()
            )

        # 4. corrige o nome do contato-piloto real
        renamed = (
            await session.execute(
                update(Contact)
                .where(Contact.phone == REAL_PILOT["phone"], Contact.name != REAL_PILOT["name"])
                .values(name=REAL_PILOT["name"])
                .returning(Contact.id)
            )
        ).all()

        await session.commit()

    print("=== Limpeza de dados mockados concluída ===")
    print(f"SurveyResponses removidas: {n_resp}")
    print(f"Contatos fictícios removidos: {n_contacts}")
    print(f"SurveyRuns órfãos removidos: {n_runs}")
    print(f"Contato-piloto renomeado: {'sim' if renamed else 'já estava correto'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
