"""App FastAPI do Escuta — coleta de feedback por WhatsApp (multi-tenant)."""
from __future__ import annotations

# Pegadinha desta máquina: antivírus intercepta TLS e o CA dele não está no
# bundle do certifi → chamadas HTTPS externas (Groq) falham com
# CERTIFICATE_VERIFY_FAILED. O truststore faz o SSL usar o repositório de
# certificados do SO (que confia no CA do antivírus). Precisa rodar ANTES de
# qualquer conexão TLS. Não afeta WAHA (http local) nem Supabase (asyncpg).
import truststore

truststore.inject_into_ssl()

import logging

from app.config import settings

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api._rate_limit import limiter

from app.api._security import require_panel_key
from app.api.admin import router as admin_router
from app.api.auth import require_operator
from app.api.auth import router as auth_router
from app.api.boards import router as boards_router
from app.api.campanha import router as campanha_router
from app.api.central import router as central_router
from app.api.clusters import router as clusters_router
from app.api.digest import router as digest_router
from app.api.events import router as events_router
from app.api.integration import router as integration_router
from app.api.playbooks import router as playbooks_router
from app.api.tasks import router as tasks_router
from app.api.webhook import router as webhook_router
from app.api.users import router as users_router
from app.api.whatsapp import router as whatsapp_router

logger = logging.getLogger(__name__)

# M5: SELF_CHAT_TEST aceita mensagens "do chat consigo mesmo" (fromMe) e loga o raw —
# inaceitável em produção. Fail-FAST: o app NÃO sobe em prod com o modo ligado.
if settings.app_env == "production" and settings.self_chat_test:
    raise RuntimeError(
        "SELF_CHAT_TEST ligado em produção — desligue SELF_CHAT_TEST (é só para E2E local)"
    )

# C2: origins do CORS vêm da env (CSV). Guard duro: nunca "*" junto com credentials —
# o cookie de sessão é same-origin via BFF, mas a regra de segurança vale sempre.
_cors_origins = settings.cors_allowed_origins_list
if "*" in _cors_origins:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS não pode conter '*' (incompatível com allow_credentials=True)"
    )

app = FastAPI(title="Escuta")

# Rate limiting (slowapi): registra o limiter no app state, adiciona o middleware
# de contagem e o handler que devolve 429 legível ao invés de 500.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Captura erro NÃO tratado e devolve um 500 JSON que AINDA atravessa o
# CORSMiddleware na volta — assim o browser recebe `access-control-allow-origin`
# e mostra o 500 real, em vez de um "Failed to fetch" genérico.
#
# Por que um middleware, e não @app.exception_handler(Exception): no Starlette o
# handler de Exception roda no ServerErrorMiddleware, que é o middleware MAIS
# EXTERNO (fora do CORS) — a resposta dele sai sem os headers de CORS. Um
# middleware HTTP registrado ANTES do CORSMiddleware fica mais INTERNO que ele
# (add_middleware insere no índice 0, então quem é adicionado depois fica por
# fora); logo a JSONResponse que retornamos aqui passa de volta pelo CORS.
# HTTPException NÃO é capturada (deixa o handler nativo do FastAPI tratar os 4xx).
@app.middleware("http")
async def _catch_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except (HTTPException, StarletteHTTPException):
        # 4xx/HTTP intencionais seguem para o handler nativo do FastAPI.
        raise
    except Exception:  # noqa: BLE001 — rede de segurança p/ CORS em 500.
        logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Erro interno"})


# Painel local (Next.js dev na 3001 — a 3000 é do WAHA). Adicionado DEPOIS do
# middleware de captura acima → o CORS fica mais externo e enxerga o 500 que ele
# produz, anexando os headers de CORS na resposta de erro.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware: registrado DEPOIS do CORS → fica mais INTERNO, logo
# a resposta 429 do slowapi atravessa o CORS na volta (recebe os headers).
app.add_middleware(SlowAPIMiddleware)

# Auth do PAINEL em DUAS camadas, aplicada a TODOS os routers do painel:
#   - require_panel_key (X-Panel-Key): "a chamada veio do nosso BFF" (trust server→server).
#     Fail-OPEN em dev quando PANEL_API_KEY ausente; fail-CLOSED (503) em produção (C1).
#   - require_operator (Authorization: Bearer <jwt>): "tem um operador logado por trás"
#     (identidade p/ auditoria). SEM fail-open: sem token válido = 401 sempre.
# ⚠️ EM PRODUÇÃO É OBRIGATÓRIO SETAR `PANEL_API_KEY` + os env de login (ver app/api/auth.py).
# Exceções (NÃO ganham a dep do painel nem do operador):
#   - webhook: tem a sua própria (require_waha_webhook_secret, #4);
#   - events: tem HMAC próprio no handler (X-Escuta-Signature) — não mexemos;
#   - integration: tem a sua (require_api_key, X-API-Key);
#   - auth: login público (não pode exigir operador para logar).
_panel = [Depends(require_panel_key), Depends(require_operator)]

# Auth: login público de operador. Mantém o trust BFF (require_panel_key) mas NÃO exige
# require_operator (senão ninguém logaria). /me e /logout validam o token no próprio handler.
app.include_router(auth_router, prefix="/api", dependencies=[Depends(require_panel_key)])

app.include_router(webhook_router, prefix="/api")
app.include_router(admin_router, prefix="/api", dependencies=_panel)
app.include_router(events_router, prefix="/api")
app.include_router(digest_router, prefix="/api", dependencies=_panel)
app.include_router(playbooks_router, prefix="/api", dependencies=_panel)
app.include_router(tasks_router, prefix="/api", dependencies=_panel)
app.include_router(clusters_router, prefix="/api", dependencies=_panel)
app.include_router(campanha_router, prefix="/api", dependencies=_panel)
app.include_router(central_router, prefix="/api", dependencies=_panel)
app.include_router(boards_router, prefix="/api", dependencies=_panel)
app.include_router(whatsapp_router, prefix="/api", dependencies=_panel)
app.include_router(users_router, prefix="/api", dependencies=_panel)
app.include_router(integration_router, prefix="/api")


@app.get("/health")
@limiter.limit("30/minute")
async def health(request: Request) -> dict[str, str]:
    return {"status": "ok"}
