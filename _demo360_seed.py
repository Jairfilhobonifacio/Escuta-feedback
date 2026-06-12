"""Seed de DEMONSTRAÇÃO da ficha 360 num SQLite isolado (sem PII real, sem Supabase).

Cria ./_demo360.db com org + 1 contato + 2 FeedbackItems (NPS app, churn) + 2
SurveyResponses (Exit, CSAT) — a mesma cliente do preview. Imprime o contact_id
para montar a URL /contatos/{id}. A API sobe apontando para o MESMO arquivo.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
import app.models.core  # noqa: F401  (registra tabelas)
import app.models.survey  # noqa: F401
import app.models.feedback  # noqa: F401
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem
from app.models.survey import Survey, SurveyResponse, SurveyRun

DB_URL = "sqlite+aiosqlite:///C:/Users/jboni/Documents/Projetos/escuta/_demo360.db"


def _dt(y, m, d, h=10, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


async def main() -> None:
    # zera o arquivo p/ rodar limpo
    path = DB_URL.split(":///")[1]
    if os.path.exists(path):
        os.remove(path)

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        org = Organization(slug="bizzu", name="Bizzu", settings={})
        s.add(org)
        await s.flush()

        contact = Contact(
            organization_id=org.id,
            phone="5531988887777",
            name="Maria Helena Duarte",
            opt_in=True,
            profile_data={
                "partner": {
                    "profile": "churn_pos_uso",
                    "subscription": {
                        "state": "cancelled",
                        "planType": "anual",
                        "daysAsSubscriber": 95,
                        "cancellationReason": "USER_CANCEL",
                    },
                    "nps": {"voted": True, "score": 8},
                }
            },
        )
        s.add(contact)
        await s.flush()

        # --- FeedbackItems (fontes externas via pull) ---
        s.add(
            FeedbackItem(
                organization_id=org.id, contact_id=contact.id, source="bizzu_billing",
                type="churn", external_id="partner:churn:demo", text="USER_CANCEL",
                occurred_at=_dt(2026, 6, 5, 12, 3), extra={"profile": "churn_pos_uso"},
            )
        )
        s.add(
            FeedbackItem(
                organization_id=org.id, contact_id=contact.id, source="bizzu_app",
                type="nps", external_id="partner:nps:demo", score=8, nps_bucket="passive",
                occurred_at=_dt(2026, 5, 20, 19, 2),
            )
        )

        # --- SurveyResponses (coletadas pelo Escuta via WhatsApp) ---
        exit_s = Survey(organization_id=org.id, name="Exit Bizzu", type="exit", status="active", questions=[])
        csat_s = Survey(organization_id=org.id, name="CSAT Tópico Bizzu", type="nps", status="active", questions=[])
        s.add_all([exit_s, csat_s])
        await s.flush()

        exit_run = SurveyRun(survey_id=exit_s.id, organization_id=org.id, trigger="demo:exit", status="done")
        csat_run = SurveyRun(survey_id=csat_s.id, organization_id=org.id, trigger="demo:csat", status="done")
        s.add_all([exit_run, csat_run])
        await s.flush()

        s.add(
            SurveyResponse(
                survey_run_id=exit_run.id, contact_id=contact.id, organization_id=org.id,
                status="closed", answer_text="Achei caro pro meu momento e acabei parando de estudar. O produto é bom.",
                sentiment="negativo", themes=["preço", "tempo"], ai_meta={"urgency": "media"},
                sent_at=_dt(2026, 6, 5, 12, 40), closed_at=_dt(2026, 6, 5, 12, 40),
            )
        )
        s.add(
            SurveyResponse(
                survey_run_id=csat_run.id, contact_id=contact.id, organization_id=org.id,
                status="closed", answer_score=9, nps_bucket="promoter",
                answer_text="Os comentários das questões salvaram meu estudo, muito bom!",
                sentiment="positivo", themes=["qualidade do conteúdo"], ai_meta={"urgency": "baixa"},
                sent_at=_dt(2026, 5, 10, 9, 11), closed_at=_dt(2026, 5, 10, 9, 11),
            )
        )

        await s.commit()
        print(f"CONTACT_ID={contact.id}")

    await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
