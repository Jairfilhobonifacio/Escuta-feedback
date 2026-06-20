"""Testes da SUGESTÃO de selos por IA — POST /api/contacts/{id}/sugerir-selos.

Mesma infra dos demais (app real + SQLite in-memory via override de get_session).
O LLM é SEMPRE um FAKE injetado em `get_llm` por `dependency_overrides` — NENHUM
teste toca a Groq real. Cobrimos: (1) parse das sugestões do LLM; (2) filtro dos
selos JÁ aplicados (e dos selos vivos de estado); (3) degradação para [] quando o
LLM falha (chat_json -> None) ou quando a IA está desligada (get_llm -> None).
"""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.campanha import get_llm  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402


class FakeLLM:
    """Dublê de GroqLLM: `chat_json` devolve um payload fixo (ou None p/ falha).

    Aceita a mesma assinatura `chat_json(system, user, **kw)` que o endpoint chama.
    Guarda a última chamada para asserts. `payload=None` simula LLM indisponível/
    JSON inválido (o GroqLLM real devolve None nesses casos, jamais lança)."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0
        self.last_user = None

    async def chat_json(self, system, user, **kwargs):
        self.calls += 1
        self.last_user = user
        return self.payload


@pytest_asyncio.fixture
async def client(session):
    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _contact(session, org, *, selos=None, profile=None):
    p = dict(profile or {})
    if selos is not None:
        p["selos"] = list(selos)
    c = Contact(organization_id=org.id, phone="5511999990000", name="Cliente Teste", opt_in=True, profile_data=p)
    session.add(c)
    await session.flush()
    return c


def _use_llm(payload):
    """Aponta get_llm para um FakeLLM com este payload (devolve o fake p/ asserts)."""
    fake = FakeLLM(payload)
    app.dependency_overrides[get_llm] = lambda: fake
    return fake


@pytest.mark.asyncio
async def test_parseia_sugestoes_do_llm(client, org, session):
    """O endpoint parseia a lista de sugestões {nome, motivo} que o LLM devolve."""
    contact = await _contact(session, org, selos=[])
    await session.commit()

    fake = _use_llm(
        {
            "sugestoes": [
                {"nome": "pediu desconto", "motivo": "Cliente perguntou sobre cupom no NPS."},
                {"nome": "risco de churn", "motivo": "Reclamou que vai cancelar."},
            ]
        }
    )

    r = await client.post(f"/api/contacts/{contact.id}/sugerir-selos")
    assert r.status_code == 200
    body = r.json()
    assert [s["nome"] for s in body["sugestoes"]] == ["pediu desconto", "risco de churn"]
    assert all(s["motivo"] for s in body["sugestoes"])
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_filtra_selos_ja_aplicados_e_vivos(client, org, session):
    """Sugestões que o cliente JÁ tem (case-insensitive) ou que são selos VIVOS de
    estado (VIP/Detrator/...) são removidas; o resto passa."""
    contact = await _contact(session, org, selos=["pediu desconto"])
    await session.commit()

    _use_llm(
        {
            "sugestoes": [
                {"nome": "Pediu Desconto", "motivo": "duplicata do já aplicado (case-insensitive)"},
                {"nome": "Detrator", "motivo": "selo vivo de estado — não deve sugerir"},
                {"nome": "promessa de retorno", "motivo": "prometeu voltar mês que vem"},
            ]
        }
    )

    r = await client.post(f"/api/contacts/{contact.id}/sugerir-selos")
    assert r.status_code == 200
    nomes = [s["nome"] for s in r.json()["sugestoes"]]
    assert nomes == ["promessa de retorno"]


@pytest.mark.asyncio
async def test_degrada_quando_llm_falha(client, org, session):
    """LLM indisponível/JSON inválido (chat_json -> None) ⇒ {"sugestoes": []}, sem 500."""
    contact = await _contact(session, org, selos=[])
    await session.commit()

    _use_llm(None)  # GroqLLM real devolve None em falha/parse — simulamos isso.

    r = await client.post(f"/api/contacts/{contact.id}/sugerir-selos")
    assert r.status_code == 200
    assert r.json() == {"sugestoes": []}


@pytest.mark.asyncio
async def test_degrada_quando_ia_desligada(client, org, session):
    """Sem GROQ_API_KEY/flag (get_llm -> None) ⇒ {"sugestoes": []}, sem chamar LLM."""
    contact = await _contact(session, org, selos=[])
    await session.commit()

    app.dependency_overrides[get_llm] = lambda: None

    r = await client.post(f"/api/contacts/{contact.id}/sugerir-selos")
    assert r.status_code == 200
    assert r.json() == {"sugestoes": []}


@pytest.mark.asyncio
async def test_payload_sem_lista_vira_vazio(client, org, session):
    """Payload do LLM sem a lista 'sugestoes' (ou malformado) ⇒ [] (parse defensivo)."""
    contact = await _contact(session, org, selos=[])
    await session.commit()

    _use_llm({"resposta": "qualquer coisa fora do contrato"})

    r = await client.post(f"/api/contacts/{contact.id}/sugerir-selos")
    assert r.status_code == 200
    assert r.json() == {"sugestoes": []}


@pytest.mark.asyncio
async def test_contexto_inclui_feedback_do_contato(client, org, session):
    """O contexto enviado ao LLM inclui o texto do FeedbackItem do contato."""
    contact = await _contact(session, org, selos=[])
    session.add(
        FeedbackItem(
            organization_id=org.id,
            contact_id=contact.id,
            source="forms",
            type="nps",
            score=3,
            sentiment="negativo",
            text="O app trava toda hora e ninguém responde o suporte.",
        )
    )
    await session.commit()

    fake = _use_llm({"sugestoes": [{"nome": "problema técnico", "motivo": "app trava"}]})

    r = await client.post(f"/api/contacts/{contact.id}/sugerir-selos")
    assert r.status_code == 200
    # O motivo/texto do feedback foi para o prompt (user message do LLM).
    assert "app trava" in (fake.last_user or "")


@pytest.mark.asyncio
async def test_contato_inexistente_404(client, org, session):
    """Contato de outra org / inexistente ⇒ 404 (org-scoped, como os demais)."""
    await session.commit()
    _use_llm({"sugestoes": []})
    r = await client.post(f"/api/contacts/{uuid_fixo()}/sugerir-selos")
    assert r.status_code == 404


def uuid_fixo() -> str:
    return "00000000-0000-0000-0000-000000000999"
