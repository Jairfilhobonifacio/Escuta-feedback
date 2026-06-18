"""Testes do fallback HONESTO do RAG (NO_KB_FALLBACK) + circuit breaker no GroqLLM.

Nada toca a Groq real: o LLM é dublado e, no teste do breaker, o POST HTTP é
monkeypatchado por um stub que devolve falha/sucesso. Invariantes:
- KB vazio OU score abaixo do piso ⇒ resposta HONESTA (não alucina), sem chamar LLM.
- Com a flag NO_KB_FALLBACK_ENABLED OFF ⇒ volta ao None antigo.
- O circuit breaker do GroqLLM conta falhas reais (5xx/timeout) e, aberto, pula a
  chamada (chat_json devolve None sem tocar a rede) preservando o never-raises.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey import brain as brain_mod  # noqa: E402
from app.domain.survey.brain import HONEST_NO_KB_MSG, SurveyBrain  # noqa: E402
from app.services.circuit_breaker import CircuitBreaker, CircuitState  # noqa: E402
from app.services.llm import GroqLLM, _UpstreamError  # noqa: E402


@dataclass
class Chunk:
    """Dublê de RetrievedChunk."""

    title: str
    content: str
    score: float


class FakeLLM:
    """Devolve um JSON fixo e CONTA quantas vezes foi chamado (p/ provar que o
    caminho honesto NÃO gasta uma chamada de LLM)."""

    def __init__(self, response=None):
        self.response = response
        self.calls = 0

    async def chat_json(self, system: str, user: str, **kwargs):
        self.calls += 1
        return self.response


# --- KB vazio / fraco → honesto (sem alucinação) ----------------------------------


@pytest.mark.asyncio
async def test_kb_vazio_responde_honesto_sem_chamar_llm(monkeypatch):
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)
    llm = FakeLLM(response={"answerable": True, "answer": "INVENTADO: o preço é R$ 99"})
    brain = SurveyBrain(llm)

    answer = await brain.answer_question_grounded("quanto custa o plano premium?", chunks=[])

    assert answer == HONEST_NO_KB_MSG
    assert llm.calls == 0  # não chamou o LLM → impossível alucinar


@pytest.mark.asyncio
async def test_score_abaixo_do_piso_responde_honesto(monkeypatch):
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)
    llm = FakeLLM(response={"answerable": True, "answer": "INVENTADO"})
    brain = SurveyBrain(llm)

    # Trecho existe, mas o melhor score (0.12) está abaixo do piso do brain (0.30):
    # tratado como "sem KB" → honesto, sem chamar o LLM.
    fraco = [Chunk(title="FAQ", content="algo tangencial", score=0.12)]
    answer = await brain.answer_question_grounded("posso pausar a assinatura?", fraco)

    assert answer == HONEST_NO_KB_MSG
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_contexto_relevante_mas_llm_nao_responde_cai_no_honesto(monkeypatch):
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)
    # Há trecho relevante (score alto), mas o LLM julga não-respondível.
    llm = FakeLLM(response={"answerable": False, "answer": None})
    brain = SurveyBrain(llm)
    bom = [Chunk(title="Planos", content="conteúdo relevante e útil", score=0.82)]

    answer = await brain.answer_question_grounded("pergunta fora do que o trecho cobre?", bom)

    assert answer == HONEST_NO_KB_MSG
    assert llm.calls == 1  # aqui SIM consultou (tinha contexto), mas não inventou


@pytest.mark.asyncio
async def test_contexto_relevante_devolve_resposta_grounded(monkeypatch):
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: True)
    llm = FakeLLM(response={"answerable": True, "answer": "Sim, dá pra pausar pelo app."})
    brain = SurveyBrain(llm)
    bom = [Chunk(title="Assinatura", content="É possível pausar a assinatura pelo app.", score=0.77)]

    answer = await brain.answer_question_grounded("consigo pausar?", bom)

    assert answer == "Sim, dá pra pausar pelo app."
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_flag_off_volta_ao_none_antigo(monkeypatch):
    monkeypatch.setattr(brain_mod, "_no_kb_fallback_enabled", lambda: False)
    llm = FakeLLM(response=None)
    brain = SurveyBrain(llm)

    answer = await brain.answer_question_grounded("qualquer coisa?", chunks=[])

    assert answer is None  # flag OFF: quem chama decide o genérico
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_answer_from_context_mantem_contrato_none(monkeypatch):
    """O método antigo segue devolvendo None com KB vazio (resolver não muda)."""
    llm = FakeLLM(response={"answerable": True, "answer": "x"})
    brain = SurveyBrain(llm)
    assert await brain.answer_from_context("q", chunks=[]) is None
    assert llm.calls == 0


# --- circuit breaker no GroqLLM (POST stubbado, zero rede) -------------------------


@pytest.mark.asyncio
async def test_groqllm_breaker_abre_e_pula_chamada(monkeypatch):
    """3 falhas reais (5xx) abrem o circuito; aberto, chat_json devolve None SEM
    nem tentar o POST — e nunca lança."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, expected_exception=_UpstreamError)
    llm = GroqLLM(api_key="x", model="m", fallback_model=None, breaker=cb)

    posts = {"n": 0}

    async def fake_post(model, payload):
        posts["n"] += 1
        raise _UpstreamError("HTTP 503")

    monkeypatch.setattr(llm, "_post", fake_post)

    # 3 chamadas que falham de verdade → abre. chat_json engole e devolve None.
    for _ in range(3):
        assert await llm.chat_json("sys", "user") is None
    assert cb.state is CircuitState.OPEN
    assert posts["n"] == 3

    # Aberto: a próxima chat_json NÃO faz POST e ainda devolve None (never-raises).
    assert await llm.chat_json("sys", "user") is None
    assert posts["n"] == 3  # não incrementou → pulou a chamada


@pytest.mark.asyncio
async def test_groqllm_json_invalido_nao_abre_circuito(monkeypatch):
    """JSON malformado é erro de validação, não instabilidade: não conta pro breaker."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, expected_exception=_UpstreamError)
    llm = GroqLLM(api_key="x", model="m", fallback_model=None, breaker=cb)

    async def fake_post(model, payload):
        return "isto não é json {{{"

    monkeypatch.setattr(llm, "_post", fake_post)

    for _ in range(5):
        assert await llm.chat_json("sys", "user") is None
    assert cb.state is CircuitState.CLOSED  # 5 JSONs inválidos, circuito intacto
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_groqllm_sucesso_devolve_dict(monkeypatch):
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, expected_exception=_UpstreamError)
    llm = GroqLLM(api_key="x", model="m", fallback_model=None, breaker=cb)

    async def fake_post(model, payload):
        return '{"kind": "score", "score": 8}'

    monkeypatch.setattr(llm, "_post", fake_post)
    data = await llm.chat_json("sys", "user")
    assert data == {"kind": "score", "score": 8}
    assert cb.state is CircuitState.CLOSED
