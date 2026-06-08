"""Testes do RAG: chunking (puro), brain.answer_from_context (LLM dublado) e
o fallback do resolver quando não há embedder.

A busca pgvector real (KnowledgeBase.search) é Postgres-only e fica para o
smoke E2E; aqui garantimos a lógica que cerca o retrieval.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.knowledge.chunking import Chunk, chunk_markdown  # noqa: E402
from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.domain.survey.resolver import DEFAULT_RETRY_MSG, SurveyContextResolver  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse  # noqa: E402
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from sqlalchemy import select  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402
from tests.test_brain import FakeLLM  # noqa: E402


# --- chunking (puro) -------------------------------------------------------------


def test_chunk_markdown_uma_secao_por_heading():
    doc = """---
title: Planos
source: bizzu
tags: [preço, plano]
---
Intro do documento sobre planos.

## Mensal
A assinatura mensal dá acesso completo.

## Anual
O plano anual sai mais barato no total.
"""
    chunks = chunk_markdown(doc)
    titles = [c.title for c in chunks]
    assert "Planos" in titles  # intro vira seção própria
    assert "Planos — Mensal" in titles
    assert "Planos — Anual" in titles
    mensal = next(c for c in chunks if c.title == "Planos — Mensal")
    assert "acesso completo" in mensal.content
    assert mensal.tags == ["preço", "plano"]


def test_chunk_markdown_sem_frontmatter_e_secao_vazia():
    doc = "## Só Título\n\n## Com Corpo\nconteúdo aqui"
    chunks = chunk_markdown(doc)
    # seção vazia é descartada; só a com corpo entra
    assert [c.title for c in chunks] == ["Bizzu — Com Corpo"]


def test_chunk_markdown_fatia_secao_longa():
    paras = "\n\n".join([f"Parágrafo número {i} " + "x" * 200 for i in range(12)])
    chunks = chunk_markdown(f"## Longa\n{paras}")
    assert len(chunks) >= 2  # estourou MAX_CHARS e foi fatiada
    assert all(c.title == "Bizzu — Longa" for c in chunks)


# --- brain.answer_from_context (groundedness) ------------------------------------


class _C:
    def __init__(self, title, content):
        self.title, self.content = title, content


@pytest.mark.asyncio
async def test_answer_grounded_quando_contexto_responde():
    brain = SurveyBrain(FakeLLM({"answerable": True, "answer": "A garantia é de 7 dias com reembolso."}))
    chunks = [_C("Garantia", "Você tem 7 dias de garantia com reembolso integral.")]
    ans = await brain.answer_from_context("tem garantia?", chunks)
    assert ans == "A garantia é de 7 dias com reembolso."


@pytest.mark.asyncio
async def test_answer_none_quando_nao_respondivel():
    brain = SurveyBrain(FakeLLM({"answerable": False, "answer": None}))
    chunks = [_C("Outro", "Assunto totalmente diferente.")]
    assert await brain.answer_from_context("qual o cnpj?", chunks) is None


@pytest.mark.asyncio
async def test_answer_none_sem_chunks_nao_chama_llm():
    fake = FakeLLM({"answerable": True, "answer": "não deveria"})
    brain = SurveyBrain(fake)
    assert await brain.answer_from_context("qualquer", []) is None
    assert fake.calls == []  # gating: sem contexto, nem chama o LLM


@pytest.mark.asyncio
async def test_answer_trunca_resposta_longa():
    brain = SurveyBrain(FakeLLM({"answerable": True, "answer": "x" * 1000}))
    ans = await brain.answer_from_context("?", [_C("t", "c")])
    assert len(ans) == 600


# --- resolver: sem embedder, "question" cai no genérico (RAG não obrigatório) -----


async def _pending_nps(session):
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.flush()
    survey = Survey(
        organization_id=org.id, name="NPS", type="nps", status="active",
        questions=[{"key": "nps", "kind": "nps", "text": "De 0 a 10?"},
                   {"key": "reason", "kind": "open", "text": "Por quê?"}],
    )
    contact = Contact(organization_id=org.id, phone="5511999990000", name="X", opt_in=True, profile_data={})
    session.add_all([survey, contact])
    await session.flush()
    await SurveyDispatcher(session, org.id, FakeMessagingService()).dispatch(survey, [contact])
    await session.commit()
    return org, contact


@pytest.mark.asyncio
async def test_question_sem_embedder_usa_resposta_generica(session):
    org, contact = await _pending_nps(session)
    # brain classifica como question e dá um reply genérico; embedder=None ⇒ sem RAG.
    brain = SurveyBrain(FakeLLM({"kind": "question", "score": None, "reply": "Sou o assistente de pesquisas!"}))
    resolver = SurveyContextResolver(session, org.id, brain=brain, embedder=None)

    reply = await resolver.resolve(contact.id, "quem é você?")
    assert reply is not None
    assert "assistente de pesquisas" in reply.text
    assert "0 a 10" in reply.text
    assert reply.closed is False
