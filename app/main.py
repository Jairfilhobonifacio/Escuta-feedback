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

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api._security import require_panel_key
from app.api.admin import router as admin_router
from app.api.boards import router as boards_router
from app.api.campanha import router as campanha_router
from app.api.clusters import router as clusters_router
from app.api.digest import router as digest_router
from app.api.events import router as events_router
from app.api.integration import router as integration_router
from app.api.playbooks import router as playbooks_router
from app.api.tasks import router as tasks_router
from app.api.webhook import router as webhook_router
from app.api.whatsapp import router as whatsapp_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Escuta")


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
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth do PAINEL (X-Panel-Key) aplicada a TODOS os routers do painel via
# dependencies=[Depends(require_panel_key)]. Fail-OPEN quando PANEL_API_KEY não está
# setado (libera + WARN, p/ não quebrar piloto/suíte); fail-CLOSED quando setado.
# ⚠️ EM PRODUÇÃO É OBRIGATÓRIO SETAR `PANEL_API_KEY` para a trava valer.
# Exceções (NÃO ganham a dep do painel):
#   - webhook: tem a sua própria (require_waha_webhook_secret, #4);
#   - events: tem HMAC próprio no handler (X-Escuta-Signature) — não mexemos;
#   - integration: tem a sua (require_api_key, X-API-Key).
_panel = [Depends(require_panel_key)]

app.include_router(webhook_router, prefix="/api")
app.include_router(admin_router, prefix="/api", dependencies=_panel)
app.include_router(events_router, prefix="/api")
app.include_router(digest_router, prefix="/api", dependencies=_panel)
app.include_router(playbooks_router, prefix="/api", dependencies=_panel)
app.include_router(tasks_router, prefix="/api", dependencies=_panel)
app.include_router(clusters_router, prefix="/api", dependencies=_panel)
app.include_router(campanha_router, prefix="/api", dependencies=_panel)
app.include_router(boards_router, prefix="/api", dependencies=_panel)
app.include_router(whatsapp_router, prefix="/api", dependencies=_panel)
app.include_router(integration_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
