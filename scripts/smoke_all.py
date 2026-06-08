"""Smoke E2E da aplicação inteira — valida cada camada contra serviços REAIS.

Não envia WhatsApp (a lógica é exercida direto pelo resolver/brain; o canal
outbound não é tocado). Não suja o Supabase: as camadas de lógica rodam em
SQLite in-memory; o RAG só LÊ o corpus já ingerido; os eventos HTTP usam casos
que não disparam (no_survey / HMAC inválido).

Uso (com a API 8000 no ar):
    PYTHONUTF8=1 HF_HUB_OFFLINE=1   (e .env carregado)
    py scripts/smoke_all.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request

import truststore

truststore.inject_into_ssl()  # TLS interceptado pelo antivírus → usa CA do SO

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402,F401
import app.models.survey  # noqa: E402,F401
import app.models.knowledge  # noqa: E402,F401
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse  # noqa: E402
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402
from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.domain.knowledge.retriever import KnowledgeBase  # noqa: E402
from app.services.llm import GroqLLM  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402
from app.db import SessionLocal  # noqa: E402

API = "http://localhost:8000"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


class FakeMsg:
    async def send_text(self, chat_id, text, session=None):
        return {"data": {"id": "smoke"}}


def _brain() -> SurveyBrain:
    return SurveyBrain(GroqLLM(settings.groq_api_key, settings.groq_model))


async def _sqlite_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _pending(session, stype="nps"):
    org = Organization(slug="smoke", name="Smoke", settings={})
    session.add(org)
    await session.flush()
    qs = (
        [{"key": "nps", "kind": "nps", "text": "De 0 a 10, recomendaria?"},
         {"key": "reason", "kind": "open", "text": "Por quê?"}]
    )
    survey = Survey(organization_id=org.id, name="S", type=stype, status="active", questions=qs)
    contact = Contact(organization_id=org.id, phone="5500000000000", name="Teste", opt_in=True, profile_data={})
    session.add_all([survey, contact])
    await session.flush()
    await SurveyDispatcher(session, org.id, FakeMsg()).dispatch(survey, [contact])
    await session.commit()
    return org, contact


# ---------------------------------------------------------------------------


async def test_infra():
    print("\n── Infra ──")
    # Groq: testa o que a APLICAÇÃO usa (chat/completions), não /models (que pode
    # estar fora do escopo da chave — daria falso negativo).
    try:
        out = await GroqLLM(settings.groq_api_key, settings.groq_model).chat_json(
            'Responda só com JSON {"ok": true}.', "ping"
        )
        check("Groq chat/completions (modelo " + settings.groq_model + ")", bool(out))
    except Exception as e:
        check("Groq chat/completions", False, str(e)[:80])

    check("LLM habilitado (settings.llm_enabled)", settings.llm_enabled)

    # pgvector + corpus
    try:
        async with SessionLocal() as s:
            n = (await s.execute(text("SELECT count(*) FROM knowledge_chunks"))).scalar_one()
        check("Corpus ingerido no pgvector", n > 0, f"{n} chunks")
    except Exception as e:
        check("Corpus ingerido no pgvector", False, str(e)[:80])


async def test_brain_layer():
    print("\n── Camada 1+2: SurveyBrain (Groq real) ──")
    brain = _brain()

    # score em linguagem natural (sem dígito/extenso)
    async with await _sqlite_session() as s:
        org, contact = await _pending(s)
        r = SurveyContextResolver(s, org.id, brain=brain)
        reply = await r.resolve(contact.id, "gostei muito, recomendo demais!")
        await s.commit()
        resp = (await s.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))).scalar_one()
        check("Resposta natural vira nota", resp.answer_score is not None,
              f"score={resp.answer_score} bucket={resp.nps_bucket}")

    # opt-out desliga contato
    async with await _sqlite_session() as s:
        org, contact = await _pending(s)
        r = SurveyContextResolver(s, org.id, brain=brain)
        await r.resolve(contact.id, "não quero mais receber essas mensagens, me tira")
        await s.commit()
        await s.refresh(contact)
        check("Opt-out desliga o contato", contact.opt_in is False)

    # classificação no fechamento
    async with await _sqlite_session() as s:
        org, contact = await _pending(s)
        r = SurveyContextResolver(s, org.id, brain=brain)
        await r.resolve(contact.id, "2")
        await r.resolve(contact.id, "muito caro e o suporte não responde, vou sair")
        await s.commit()
        resp = (await s.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))).scalar_one()
        ok = resp.sentiment == "negativo" and bool(resp.themes)
        check("Feedback classificado (sentiment/themes)", ok,
              f"{resp.sentiment} {resp.themes} urg={(resp.ai_meta or {}).get('urgency')}")


async def test_rag_layer():
    print("\n── Camada 3: RAG (pgvector + Groq real) ──")
    brain = _brain()
    embedder = get_embedder()
    async with SessionLocal() as s:
        org = (await s.execute(select(Organization).where(Organization.slug == "bizzu"))).scalar_one()
        kb = KnowledgeBase(s, org.id, embedder)

        chunks = await kb.search("tem garantia se eu não gostar?")
        ans = await brain.answer_from_context("tem garantia se eu não gostar?", chunks)
        check("Pergunta no corpus → resposta grounded", bool(ans),
              (ans or "")[:70])

        chunks2 = await kb.search("qual a capital da França?")
        ans2 = await brain.answer_from_context("qual a capital da França?", chunks2)
        check("Pergunta fora do corpus → recusa (gating)", ans2 is None)


def _http_json(method, path, body=None, headers=None):
    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


async def test_http():
    print("\n── Endpoints HTTP (API 8000 real) ──")
    st, _ = _http_json("GET", "/health")
    check("GET /health", st == 200)

    st, dash = _http_json("GET", "/api/dashboard")
    ok = st == 200 and "nps" in (dash or {}) and "exit" in (dash or {})
    check("GET /api/dashboard (blocos nps+exit)", ok,
          f"nps={dash['nps']['nps'] if ok else '?'} exit_sent={dash['exit']['sent'] if ok else '?'}")

    # gancho de churn: HMAC válido em evento sem survey (não dispara WhatsApp)
    secret = settings.bizzu_webhook_secret or ""
    body = json.dumps({
        "event": "evento_inexistente_smoke", "event_id": "smoke-1",
        "user": {"id": "u", "name": "S", "phone": "5500000000000", "whatsapp_opt_in": True},
        "properties": {},
    }).encode()
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    st, resp = _http_json("POST", "/api/events/bizzu", body, {
        "Content-Type": "application/json", "X-Escuta-Timestamp": ts, "X-Escuta-Signature": sig})
    check("POST /api/events/bizzu HMAC válido → 202", st == 202,
          f"reason={resp.get('reason') if resp else '?'}")

    # HMAC inválido rejeitado
    st2, _ = _http_json("POST", "/api/events/bizzu", body, {
        "Content-Type": "application/json", "X-Escuta-Timestamp": ts, "X-Escuta-Signature": "deadbeef"})
    check("POST /api/events/bizzu HMAC inválido → 401", st2 == 401)


async def main():
    print("=" * 60)
    print("SMOKE E2E — Escuta (todas as camadas, serviços reais)")
    print("=" * 60)
    await test_infra()
    await test_brain_layer()
    await test_rag_layer()
    await test_http()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"RESULTADO: {passed}/{total} verdes")
    if passed < total:
        print("Falhas:")
        for name, ok, det in RESULTS:
            if not ok:
                print(f"  - {name}: {det}")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
