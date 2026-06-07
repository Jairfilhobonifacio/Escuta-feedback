"""Teste de integração end-to-end do fluxo de NPS (SQLite in-memory async).

Prova que a "bala atravessa": dispatch -> resposta "9" -> follow-up -> fecha,
exercitando o SurveyDispatcher e o SurveyContextResolver REAIS contra um banco
de verdade (SQLite async), sem precisar do Supabase.

Rodar: python tests/test_survey_flow_integration.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: E402

from app.models.base import Base  # noqa: E402
from app.models.core import Organization, Contact  # noqa: E402
from app.models.survey import (  # noqa: E402
    Survey, SurveyRun, SurveyResponse,
    STATUS_SENT, STATUS_AWAITING_REASON, STATUS_CLOSED,
)
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402

QUESTIONS = [
    {"key": "nps", "kind": "nps", "text": "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"},
    {"key": "reason", "kind": "open", "text": "Massa! 🙌 Por quê? (pode mandar em texto)"},
]


class FakeMessaging:
    """Implementa IMessagingService (duck typing) — só guarda o que seria enviado."""
    def __init__(self):
        self.sent = []

    async def send_text(self, chat_id, text, session=None):
        self.sent.append({"chat_id": chat_id, "text": text, "session": session})
        return {"data": {"id": "fake-msg-1"}}

    async def send_image(self, *a, **k):
        return {}

    async def send_audio(self, *a, **k):
        return {}

    async def get_contacts(self, *a, **k):
        return []


async def run() -> int:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    results = []

    def check(name, cond):
        results.append((name, bool(cond)))
        print(("  ✓ " if cond else "  ✗ ") + name)

    async with Session() as s:
        org = Organization(slug="bizzu", name="Bizzu")
        org2 = Organization(slug="outra", name="Outra Org")
        s.add_all([org, org2])
        await s.flush()

        survey = Survey(organization_id=org.id, name="NPS Bizzu", type="nps", questions=QUESTIONS, status="active")
        s.add(survey)
        c1 = Contact(organization_id=org.id, phone="5531999990001", name="Concurseiro Um", opt_in=True)
        c2 = Contact(organization_id=org.id, phone="5531999990002", name="Concurseiro Dois", opt_in=True)
        c3 = Contact(organization_id=org2.id, phone="5531999990003", name="De Outra Org", opt_in=True)
        s.add_all([c1, c2, c3])
        await s.flush()

        # --- 1) Disparo --------------------------------------------------
        fake = FakeMessaging()
        disp = SurveyDispatcher(s, org.id, fake)
        run_obj = await disp.dispatch(survey, [c1])

        resp = (await s.execute(select(SurveyResponse).where(SurveyResponse.contact_id == c1.id))).scalar_one()
        check("dispatch cria SurveyResponse status='sent'", resp.status == STATUS_SENT)
        check("dispatch grava channel_msg_id do canal", resp.channel_msg_id == "fake-msg-1")
        check("dispatcher enviou exatamente 1 mensagem", len(fake.sent) == 1)
        check("texto enviado contém a pergunta de NPS", "recomendaria" in fake.sent[0]["text"])
        check("run marcado como 'done'", run_obj.status == "done")

        # --- 2) Resposta NPS "9" ----------------------------------------
        resolver = SurveyContextResolver(s, org.id)
        r1 = await resolver.resolve(c1.id, "9")
        check("resolve('9') retorna um reply (não None)", r1 is not None)
        check("reply pergunta o motivo (pergunta 'open' do survey)", bool(r1) and "quê" in r1.text.lower())
        await s.refresh(resp)
        check("status -> 'awaiting_reason'", resp.status == STATUS_AWAITING_REASON)
        check("answer_score == 9", resp.answer_score == 9)
        check("nps_bucket == 'promoter'", resp.nps_bucket == "promoter")
        check("answered_at preenchido", resp.answered_at is not None)

        # --- 3) Follow-up (motivo) fecha --------------------------------
        r2 = await resolver.resolve(c1.id, "porque os resumos são ótimos")
        check("resolve(motivo) retorna reply", r2 is not None)
        check("reply marca closed=True", bool(r2) and r2.closed is True)
        await s.refresh(resp)
        check("status -> 'closed'", resp.status == STATUS_CLOSED)
        check("answer_text salvo", resp.answer_text == "porque os resumos são ótimos")
        check("closed_at preenchido", resp.closed_at is not None)

        # --- 4) Sem pesquisa pendente -> None ---------------------------
        r3 = await resolver.resolve(c2.id, "9")
        check("contato sem pesquisa pendente -> None (fluxo normal)", r3 is None)

        # --- 5) Resposta fora da janela de 24h -> None ------------------
        now = datetime.now(timezone.utc)
        old = SurveyResponse(
            survey_run_id=run_obj.id, contact_id=c2.id, organization_id=org.id,
            status=STATUS_SENT, sent_at=now - timedelta(hours=25),
        )
        s.add(old)
        await s.flush()
        r4 = await resolver.resolve(c2.id, "8")
        check("resposta apos 24h nao casa -> None", r4 is None)

        # --- 6) Isolamento multi-tenant ---------------------------------
        run2 = SurveyRun(survey_id=survey.id, organization_id=org2.id, trigger="manual", status="running")
        s.add(run2)
        await s.flush()
        pend2 = SurveyResponse(
            survey_run_id=run2.id, contact_id=c3.id, organization_id=org2.id,
            status=STATUS_SENT, sent_at=now,
        )
        s.add(pend2)
        await s.flush()
        r5 = await resolver.resolve(c3.id, "9")  # resolver da org1
        check("multi-tenant: org1 NAO casa contato/pesquisa da org2 -> None", r5 is None)
        resolver2 = SurveyContextResolver(s, org2.id)
        r6 = await resolver2.resolve(c3.id, "9")  # resolver da org2
        check("resolver da org2 casa o contato da org2", r6 is not None)

        await s.commit()

    await engine.dispose()

    failed = [n for n, c in results if not c]
    total = len(results)
    print(f"\n{total - len(failed)}/{total} verdes" + (" ✅" if not failed else " ❌ -> " + "; ".join(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
