"""App FastAPI do Escuta — coleta de feedback por WhatsApp (multi-tenant)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.events import router as events_router
from app.api.webhook import router as webhook_router

app = FastAPI(title="Escuta")

# Painel local (Next.js dev na 3001 — a 3000 é do WAHA).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(events_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
