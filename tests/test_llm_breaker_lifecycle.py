"""Ciclo de vida do circuit breaker PADRÃO do GroqLLM — escopo de PROCESSO.

Regressão do bug "breaker decorativo": o GroqLLM é instanciado POR REQUEST (ex.:
o webhook cria um a cada mensagem). Antes, o construtor criava um `CircuitBreaker`
NOVO e zerado por instância — o contador de falhas nunca acumulava entre requests
e o circuito NUNCA abria em produção (a feature de resiliência estava desligada,
apesar dos testes unitários verdes que exercitavam só a classe isolada).

A correção: o breaker padrão é um SINGLETON de módulo (`_DEFAULT_BREAKER`),
compartilhado por todas as instâncias de GroqLLM SEM breaker injetado. Estes
testes provam que N falhas distribuídas entre N instâncias DIFERENTES abrem o
mesmo circuito — e que a injeção de breaker continua sobrescrevendo o singleton.

ISOLAMENTO: como o singleton é compartilhado, um teste que abre o circuito
contaminaria o próximo. A fixture autouse `_reset_breaker` zera `_DEFAULT_BREAKER`
antes e depois de CADA teste deste módulo (não toca o conftest global). Nada toca
a Groq real: o POST HTTP é monkeypatchado por um stub.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.services import llm as llm_mod  # noqa: E402
from app.services.circuit_breaker import CircuitBreaker, CircuitState  # noqa: E402
from app.services.llm import (  # noqa: E402
    GroqLLM,
    _UpstreamError,
    reset_default_breaker,
)


@pytest.fixture(autouse=True)
def _reset_breaker():
    """Zera o breaker padrão de processo antes e depois de cada teste do módulo.

    Sem isso, um teste que abre o circuito vazaria estado para o seguinte (e para
    qualquer outro módulo que instancie GroqLLM sem breaker injetado).
    """
    reset_default_breaker()
    yield
    reset_default_breaker()


def _make_llm() -> GroqLLM:
    """Uma instância NOVA de GroqLLM SEM breaker injetado — pega o singleton."""
    return GroqLLM(api_key="x", model="m", fallback_model=None)


# --- a propriedade central: estado persiste ENTRE instâncias ----------------------


def test_instancias_sem_breaker_compartilham_o_mesmo_breaker():
    """Sem breaker injetado, toda instância usa o MESMO objeto breaker (singleton)."""
    a = _make_llm()
    b = _make_llm()
    assert a.breaker is b.breaker
    assert a.breaker is llm_mod._DEFAULT_BREAKER


@pytest.mark.asyncio
async def test_falhas_distribuidas_entre_instancias_abrem_o_circuito(monkeypatch):
    """3 falhas reais (5xx), UMA por instância DIFERENTE, abrem o circuito padrão.

    Esta é a prova do bug: com breaker-por-instância, cada chamada zeraria e o
    circuito nunca abriria. Com o singleton, as falhas acumulam entre instâncias.
    """
    posts = {"n": 0}

    async def fake_post(self, model, payload):
        posts["n"] += 1
        raise _UpstreamError("HTTP 503")

    # Patcha no método da CLASSE: vale para toda instância de GroqLLM criada aqui.
    monkeypatch.setattr(GroqLLM, "_post", fake_post)

    # 3 instâncias DISTINTAS, cada uma faz UMA chamada que falha de verdade.
    for _ in range(llm_mod._BREAKER_FAILURE_THRESHOLD):
        llm = _make_llm()
        assert await llm.chat_json("sys", "user") is None  # never-raises

    assert llm_mod._DEFAULT_BREAKER.state is CircuitState.OPEN
    assert posts["n"] == llm_mod._BREAKER_FAILURE_THRESHOLD

    # Uma instância NOVA agora falha rápido: aberto ⇒ não toca a rede, devolve None.
    nova = _make_llm()
    assert await nova.chat_json("sys", "user") is None
    assert posts["n"] == llm_mod._BREAKER_FAILURE_THRESHOLD  # não incrementou


@pytest.mark.asyncio
async def test_circuito_aberto_persiste_para_proxima_instancia(monkeypatch):
    """Abrir o circuito em uma instância faz a SEGUINTE já nascer falhando rápido."""
    async def fail_post(self, model, payload):
        raise _UpstreamError("HTTP 502")

    monkeypatch.setattr(GroqLLM, "_post", fail_post)

    # Abre o circuito usando a primeira instância.
    primeira = _make_llm()
    for _ in range(llm_mod._BREAKER_FAILURE_THRESHOLD):
        assert await primeira.chat_json("sys", "user") is None
    assert llm_mod._DEFAULT_BREAKER.state is CircuitState.OPEN

    # A próxima instância (request seguinte) NÃO deve tocar a rede.
    chamou = {"n": 0}

    async def conta_post(self, model, payload):
        chamou["n"] += 1
        return '{"ok": true}'

    monkeypatch.setattr(GroqLLM, "_post", conta_post)
    segunda = _make_llm()
    assert await segunda.chat_json("sys", "user") is None
    assert chamou["n"] == 0  # circuito aberto pulou a chamada


# --- a injeção continua sobrescrevendo o singleton (testes dependem disso) ---------


def test_breaker_injetado_sobrescreve_o_singleton():
    cb = CircuitBreaker(
        failure_threshold=2, recovery_timeout=5, expected_exception=_UpstreamError
    )
    llm = GroqLLM(api_key="x", model="m", breaker=cb)
    assert llm.breaker is cb
    assert llm.breaker is not llm_mod._DEFAULT_BREAKER


@pytest.mark.asyncio
async def test_breaker_injetado_nao_contamina_o_singleton(monkeypatch):
    """Abrir um breaker INJETADO não toca o singleton de processo."""
    cb = CircuitBreaker(
        failure_threshold=3, recovery_timeout=30, expected_exception=_UpstreamError
    )

    async def fail_post(self, model, payload):
        raise _UpstreamError("HTTP 500")

    monkeypatch.setattr(GroqLLM, "_post", fail_post)

    llm = GroqLLM(api_key="x", model="m", fallback_model=None, breaker=cb)
    for _ in range(3):
        assert await llm.chat_json("sys", "user") is None

    assert cb.state is CircuitState.OPEN
    assert llm_mod._DEFAULT_BREAKER.state is CircuitState.CLOSED  # intacto


# --- o reset existe e funciona (isolamento) ---------------------------------------


@pytest.mark.asyncio
async def test_reset_default_breaker_zera_o_estado(monkeypatch):
    async def fail_post(self, model, payload):
        raise _UpstreamError("HTTP 503")

    monkeypatch.setattr(GroqLLM, "_post", fail_post)

    llm = _make_llm()
    for _ in range(llm_mod._BREAKER_FAILURE_THRESHOLD):
        assert await llm.chat_json("sys", "user") is None
    assert llm_mod._DEFAULT_BREAKER.state is CircuitState.OPEN

    reset_default_breaker()
    assert llm_mod._DEFAULT_BREAKER.state is CircuitState.CLOSED
    assert llm_mod._DEFAULT_BREAKER.failure_count == 0
