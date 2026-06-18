"""Testes do CircuitBreaker — relógio injetado, sem sleep real, sem rede.

Cobre o contrato pedido: abre após 3 falhas consecutivas; passa a half-open só
depois do recovery_timeout; fecha após 1 sucesso em half-open; e falha RÁPIDO
(CircuitOpenError) enquanto aberto. Também testa que sucesso intercalado zera a
contagem e que o wrapper funciona sync e async.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.services.circuit_breaker import (  # noqa: E402
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class FakeClock:
    """Relógio injetável: o tempo só anda quando o teste manda."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _boom():
    raise ValueError("boom")


def _ok():
    return "ok"


# --- síncrono: abrir / falhar rápido / recuperar / fechar -------------------------


def test_abre_apos_3_falhas_consecutivas():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)

    for _ in range(2):
        with pytest.raises(ValueError):
            cb.call(_boom)
    # 2 falhas: ainda fechado.
    assert cb.state is CircuitState.CLOSED

    with pytest.raises(ValueError):
        cb.call(_boom)  # 3ª falha consecutiva → abre
    assert cb.state is CircuitState.OPEN
    assert cb.failure_count == 3


def test_aberto_falha_rapido_sem_chamar_a_funcao():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)
    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(_boom)
    assert cb.state is CircuitState.OPEN

    chamadas = {"n": 0}

    def conta():
        chamadas["n"] += 1
        return "nunca"

    # Enquanto aberto e dentro da janela: CircuitOpenError, sem tocar na função.
    with pytest.raises(CircuitOpenError):
        cb.call(conta)
    assert chamadas["n"] == 0


def test_meia_aberto_so_apos_recovery_timeout():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)
    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(_boom)
    assert cb.state is CircuitState.OPEN

    # Antes da janela fechar: segue aberto, falha rápido.
    clock.advance(29)
    assert cb.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        cb.call(_ok)

    # Passada a janela: vira half-open (deixa UMA chamada de teste passar).
    clock.advance(2)  # total 31 >= 30
    assert cb.state is CircuitState.HALF_OPEN


def test_fecha_apos_um_sucesso_em_meia_aberto():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)
    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(_boom)
    clock.advance(31)
    assert cb.state is CircuitState.HALF_OPEN

    # 1 sucesso em half-open → fecha e zera a contagem.
    assert cb.call(_ok) == "ok"
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


def test_falha_em_meia_aberto_reabre_imediatamente():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)
    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(_boom)
    clock.advance(31)
    assert cb.state is CircuitState.HALF_OPEN

    # A chamada de teste falha → reabre na hora (não precisa de outras 3).
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.state is CircuitState.OPEN
    # E reinicia a janela: ainda falha rápido logo em seguida.
    with pytest.raises(CircuitOpenError):
        cb.call(_ok)


def test_sucesso_intercalado_zera_contagem():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)
    with pytest.raises(ValueError):
        cb.call(_boom)
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.failure_count == 2
    cb.call(_ok)  # sucesso reseta as falhas consecutivas
    assert cb.failure_count == 0
    # Logo, mais 2 falhas NÃO abrem (precisa de 3 SEGUIDAS).
    with pytest.raises(ValueError):
        cb.call(_boom)
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.state is CircuitState.CLOSED


def test_expected_exception_restringe_o_que_conta():
    clock = FakeClock()
    cb = CircuitBreaker(
        failure_threshold=2, recovery_timeout=30, clock=clock, expected_exception=ValueError
    )

    def type_error():
        raise TypeError("não é falha de chamada")

    # TypeError propaga mas NÃO conta como falha de circuito.
    for _ in range(3):
        with pytest.raises(TypeError):
            cb.call(type_error)
    assert cb.state is CircuitState.CLOSED
    assert cb.failure_count == 0


# --- assíncrono: mesma máquina de estados via call_async --------------------------


@pytest.mark.asyncio
async def test_async_abre_e_falha_rapido():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, clock=clock)

    async def aboom():
        raise ValueError("boom")

    for _ in range(3):
        with pytest.raises(ValueError):
            await cb.call_async(aboom)
    assert cb.state is CircuitState.OPEN

    chamou = {"n": 0}

    async def aok():
        chamou["n"] += 1
        return "ok"

    with pytest.raises(CircuitOpenError):
        await cb.call_async(aok)
    assert chamou["n"] == 0  # não tocou na função

    clock.advance(31)
    assert await cb.call_async(aok) == "ok"  # half-open → sucesso → fecha
    assert cb.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_async_via_call_detecta_corrotina():
    """`call` (não `call_async`) também aguarda corrotinas e contabiliza no await."""
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10, clock=clock)

    async def aboom():
        raise ValueError("boom")

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(aboom)
    assert cb.state is CircuitState.OPEN


@pytest.mark.asyncio
async def test_decorator_async():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10, clock=clock)

    @cb
    async def flaky(should_fail: bool):
        if should_fail:
            raise ValueError("boom")
        return "ok"

    for _ in range(2):
        with pytest.raises(ValueError):
            await flaky(True)
    assert cb.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await flaky(False)


def test_threshold_invalido():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
