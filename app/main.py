"""App FastAPI do Escuta — coleta de feedback por WhatsApp (multi-tenant)."""
from __future__ import annotations

from fastapi import FastAPI

from app.api.webhook import router as webhook_router

app = FastAPI(title="Escuta")

app.include_router(webhook_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
