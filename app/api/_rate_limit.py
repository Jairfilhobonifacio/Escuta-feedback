"""Rate limiting (slowapi) — singleton do Limiter, importável nos routers.

Usa `get_remote_address` como key (IP do request). Em serverless (Modal) atrás de
proxy/LB, o IP real chega em X-Forwarded-For — o Starlette `Request.client.host`
pode ser o IP do proxy. O `get_remote_address` do slowapi lê X-Forwarded-For
automaticamente quando presente, mas em infra com múltiplos proxies convém
configurar `trusted_hosts` no ProxyHeadersMiddleware do uvicorn.

Desabilitável via RATE_LIMIT_ENABLED=0 (útil nos testes automatizados).
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("RATE_LIMIT_ENABLED", "1") == "1",
)
