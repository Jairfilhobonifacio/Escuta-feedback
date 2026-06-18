"""Testes do RAG honesto CABEADO no resolver + visibilidade de KB quebrada.

Cobre dois achados:

#5 — Caminho real "cliente faz uma pergunta durante a pesquisa" usa
     `answer_question_grounded` (atrás de NO_KB_FALLBACK_ENABLED, default ON):
     com KB vazio/score baixo, o cliente recebe a mensagem HONESTA
     (`HONEST_NO_KB_MSG`) em vez de cair num reply genérico. Com a flag OFF,
     preserva o comportamento antigo (cai no `intent.reply` via
     `answer_from_context`, que devolve None sem KB).

#7 — Quando o RETRIEVAL LANÇA (embedder/pgvector quebrado — p.ex.
     sentence-transformers ausente), o erro é logado como ERROR (FALHA de KB,
     VISÍVEL) e NÃO se passa por "respondido honestamente": o fluxo cai no
     genérico, distinguível de "sem contexto".

Nada toca a Groq nem o pgvector reais: LLM dublado e `KnowledgeBase.search`
monkeypatchado. Usa a fixture `session` (SQLite in-memory) de tests/conftest.py.
"""
from __future__ import annotations

import logging
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey import brain as brain_mod  # noqa: E402
from app.domain.survey import resolver as resolver_mod  # noqa: E402
from app.domain.survey.brain import HONEST_NO_KB_MSG, SurveyBrain  # noqa: E402
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


class _QuestionLLM:
    """Dublê de GroqLLM. `interpret_reply` classifica como 'question' com um reply
    GENÉRICO; conta as chamadas para provarmos que o caminho honesto (KB vazio) NÃO
    gasta uma chamada de LLM na composição da resposta."""

    GENERIC_REPLY = "Sou o assistente de pesquisas da empresa! 🙂"

    def __init__(self):
        self.calls: list[str] = []

    async def chat_json(self, system: str, user: str, **kwargs):
        self.calls.append(system)
        if "INTENÇÃO" in system or "Classifique" in system:
            return {"kind": "question", "score": None, "reply": self.GENERIC_REPLY}
        # _ANSWER_SYSTEM (se chegasse aqui com KB) — não deve ocorrer nos cenários
        # de KB vazio/erro; devolve algo só para flagrar se for chamado indevido.
        return {"answerable": True, "answer": "NÃO DEVERIA APARECER"}


class _DummyEmbedder:
    """Embedder não-None só para destravar o caminho RAG do resolver (a busca real
    é monkeypatchada)."""

    async def embed_one(self, text: str):
        return [0.0] * 384


async def _pending_nps(session):
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.flush()
    survey = Survey(
        organization_id=org.id, name="NPS", type="nps", status="active",
        questions=[{"key": "nps", "kind": "nps", "text": "De 0 a 10?"},
                   {"key": "reason", "kind": "open", "text": "Por quê?"}],
    )
    contact = Contact(
        organization_id=org.id, phone="5511999990000", name="X", opt_in=True, profile_data={}
    )
    session.add_all([survey, contact])
    await session.flush()
    await SurveyDispatcher(session, org.id, FakeMessagingService()).dispatch(survey, [contact])
    await session.commit()
    return org, contact


# --- #5: KB vazio + flag ON ⇒ cliente recebe a mensagem HONESTA -------------------


@pytest.mark.asyncio
async def test_pergunta_com_kb_vazio_flag_on_responde_honesto(session, monkeypatch):
    """KB vazio (retrieval devolve []) com NO_KB_FALLBACK ON: o cliente recebe a
    frase honesta cabeada (HONEST_NO_KB_MSG), NÃO o reply genérico do brain."""
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)

    async def _empty_search(self, query, *a, **kw):
        return []  # KB vazio / nada acima do piso

    monkeypatch.setattr(resolver_mod.KnowledgeBase, "search", _empty_search, raising=True)

    org, contact = await _pending_nps(session)
    llm = _QuestionLLM()
    resolver = SurveyContextResolver(
        session, org.id, brain=SurveyBrain(llm), embedder=_DummyEmbedder()
    )

    reply = await resolver.resolve(contact.id, "quanto custa o plano premium?")

    assert reply is not None
    assert HONEST_NO_KB_MSG in reply.text          # frase honesta efetivamente enviada
    assert _QuestionLLM.GENERIC_REPLY not in reply.text  # genérico NÃO vaza
    assert "0 a 10" in reply.text                   # ainda retoma a nota
    assert reply.closed is False
    # 1 chamada de LLM (interpret_reply); a composição honesta NÃO chamou o LLM.
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_pergunta_com_kb_vazio_flag_off_volta_ao_generico(session, monkeypatch):
    """Flag OFF: comportamento antigo preservado — sem KB, `answer_from_context`
    devolve None e o resolver usa o reply genérico (nada de honesto)."""
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: False)

    async def _empty_search(self, query, *a, **kw):
        return []

    monkeypatch.setattr(resolver_mod.KnowledgeBase, "search", _empty_search, raising=True)

    org, contact = await _pending_nps(session)
    llm = _QuestionLLM()
    resolver = SurveyContextResolver(
        session, org.id, brain=SurveyBrain(llm), embedder=_DummyEmbedder()
    )

    reply = await resolver.resolve(contact.id, "quanto custa o plano premium?")

    assert reply is not None
    assert _QuestionLLM.GENERIC_REPLY in reply.text  # genérico de volta
    assert HONEST_NO_KB_MSG not in reply.text         # honesto desligado
    assert "0 a 10" in reply.text


# --- #7: retrieval LANÇA ⇒ ERROR logado e NÃO mascarado como "honesto" ------------


@pytest.mark.asyncio
async def test_retrieval_que_lanca_loga_error_e_nao_se_passa_por_honesto(
    session, monkeypatch, caplog
):
    """Embedder/pgvector quebrado (search LANÇA): é FALHA de KB — logada como ERROR
    e VISÍVEL — e NÃO pode virar a resposta honesta de 'não sei'. O fluxo cai no
    genérico (distinguível de 'sem contexto')."""
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)

    async def _boom_search(self, query, *a, **kw):
        raise RuntimeError("sentence-transformers ausente / pgvector fora do ar")

    monkeypatch.setattr(resolver_mod.KnowledgeBase, "search", _boom_search, raising=True)

    org, contact = await _pending_nps(session)
    llm = _QuestionLLM()
    resolver = SurveyContextResolver(
        session, org.id, brain=SurveyBrain(llm), embedder=_DummyEmbedder()
    )

    with caplog.at_level(logging.ERROR, logger=resolver_mod.logger.name):
        reply = await resolver.resolve(contact.id, "quanto custa o plano premium?")

    # (a) erro VISÍVEL como ERROR, deixando claro que é FALHA de KB
    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records, "a falha de retrieval deveria ter sido logada como ERROR"
    assert any("FALHA" in r.getMessage() for r in err_records)

    # (b) NÃO se passou por 'respondido honestamente': caiu no genérico.
    assert reply is not None
    assert HONEST_NO_KB_MSG not in reply.text
    assert _QuestionLLM.GENERIC_REPLY in reply.text


@pytest.mark.asyncio
async def test_kb_vazio_nao_loga_error(session, monkeypatch, caplog):
    """Contraprova: KB vazio (sem exceção) NÃO é erro — não deve logar ERROR.
    Garante que 'sem contexto' e 'KB quebrada' são caminhos distinguíveis."""
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)

    async def _empty_search(self, query, *a, **kw):
        return []

    monkeypatch.setattr(resolver_mod.KnowledgeBase, "search", _empty_search, raising=True)

    org, contact = await _pending_nps(session)
    resolver = SurveyContextResolver(
        session, org.id, brain=SurveyBrain(_QuestionLLM()), embedder=_DummyEmbedder()
    )

    with caplog.at_level(logging.ERROR, logger=resolver_mod.logger.name):
        reply = await resolver.resolve(contact.id, "quanto custa?")

    assert reply is not None
    assert HONEST_NO_KB_MSG in reply.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
