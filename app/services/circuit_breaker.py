"""Circuit breaker simples e testável — protege chamadas a serviços externos.

Princípio: quando um dependente (ex.: a API da Groq) começa a falhar em série,
parar de bater nele por um tempo é melhor do que segurar o webhook do WhatsApp
em cada timeout. O breaker "abre" após N falhas consecutivas e passa a FALHAR
RÁPIDO (levanta `CircuitOpenError` sem nem tentar a chamada) por uma janela de
recuperação; depois disso entra em "half-open" e deixa UMA chamada de teste
passar — sucesso fecha de novo, falha reabre.

Estados:
- closed:    tudo normal; conta falhas consecutivas. `failure_threshold` falhas → open.
- open:      falha rápido; após `recovery_timeout` segundos → half-open (na próxima chamada).
- half-open: deixa 1 chamada de teste passar. Sucesso → closed (zera). Falha → open.

Relógio injetável: por padrão usa `time.monotonic` (imune a ajustes de NTP). Nos
testes, passe `clock=` para avançar o "agora" sem `sleep` real e exercitar a
janela de recuperação de forma determinística.

Uso (síncrono ou assíncrono — o breaker detecta a corrotina):

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

    # como wrapper de chamada:
    result = await cb.call(async_fn, arg1, arg2)
    result = cb.call(sync_fn, arg1)

    # como decorator:
    @cb
    async def fetch(...): ...
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Levantada quando o circuito está aberto: a chamada falha rápido, sem tentar."""


class CircuitBreaker:
    """Circuit breaker de N falhas consecutivas com janela de recuperação.

    Conta SÓ as exceções listadas em `expected_exception` (default: qualquer
    `Exception`) como "falha de chamada" — quem chama deve garantir que erros de
    validação (não-falhas) NÃO cheguem aqui como exceção, ou restringir o tipo.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        expected_exception: type[BaseException] | tuple[type[BaseException], ...] = Exception,
        clock: Callable[[], float] = time.monotonic,
        name: str = "circuit",
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold deve ser >= 1")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self._clock = clock
        self.name = name

        self._state: CircuitState = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None

    # --- introspecção (útil em testes/observabilidade) --------------------------

    @property
    def state(self) -> CircuitState:
        """Estado LÓGICO atual: já considera a expiração da janela de recuperação.

        Se está `open` e o `recovery_timeout` já passou, reporta `half_open` (a
        próxima chamada será a de teste). Não muta — só `call`/`_before` mutam.
        """
        if self._state is CircuitState.OPEN and self._recovery_elapsed():
            return CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failures

    # --- núcleo -----------------------------------------------------------------

    def _recovery_elapsed(self) -> bool:
        if self._opened_at is None:
            return True
        return (self._clock() - self._opened_at) >= self.recovery_timeout

    def _before_call(self) -> None:
        """Decide se a chamada PODE prosseguir; transiciona open→half-open se cabível."""
        if self._state is CircuitState.OPEN:
            if self._recovery_elapsed():
                self._state = CircuitState.HALF_OPEN
                logger.info("CircuitBreaker[%s]: recovery — half-open (chamada de teste)", self.name)
            else:
                raise CircuitOpenError(
                    f"CircuitBreaker[{self.name}] aberto — falhando rápido (sem tentar a chamada)"
                )
        # closed e half-open seguem.

    def _on_success(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            logger.info("CircuitBreaker[%s]: sucesso em half-open — fechando", self.name)
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = None

    def _on_failure(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            # Teste de recuperação falhou: reabre imediatamente e reinicia a janela.
            self._open()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        logger.warning(
            "CircuitBreaker[%s]: ABERTO (%d falhas consecutivas) — janela de %.0fs",
            self.name, self._failures, self.recovery_timeout,
        )

    # --- API de chamada ---------------------------------------------------------

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoca `func` sob a proteção do breaker.

        Se `func` devolver uma corrotina (função async), devolve uma corrotina que
        DEVE ser aguardada — a contagem de sucesso/falha ocorre no await. Para
        chamadas síncronas, executa e contabiliza na hora.
        """
        self._before_call()
        try:
            result = func(*args, **kwargs)
        except self.expected_exception:
            self._on_failure()
            raise
        except BaseException:
            # Exceção inesperada (não é "falha de chamada"): não conta, mas propaga.
            raise

        if asyncio.iscoroutine(result):
            return self._await_result(result)

        self._on_success()
        return result

    async def _await_result(self, coro: Any) -> Any:
        try:
            result = await coro
        except self.expected_exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    async def call_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Versão explicitamente assíncrona: aguarda e contabiliza. Útil quando
        `func` pode levantar SÍNCRONO antes de retornar a corrotina."""
        self._before_call()
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
        except self.expected_exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Permite usar a instância como decorator (sync ou async)."""
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await self.call_async(func, *args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)

        return sync_wrapper

    def reset(self) -> None:
        """Volta ao estado inicial (closed, zero falhas) — manual/observabilidade."""
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = None
