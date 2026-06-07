"""Camada de API (rotas HTTP do FastAPI)."""
from __future__ import annotations

from app.api.webhook import router as webhook_router

__all__ = ["webhook_router"]
