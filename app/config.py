"""Configuração (stdlib-only, sem pydantic para manter db.py importável enxuto).

Lê de variáveis de ambiente. Em produção, vêm de Secrets do Modal; em dev, de .env
carregado pelo runner.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # postgresql+asyncpg://user:pass@host:5432/db  (Supabase)
    database_url: str = os.getenv("DATABASE_URL", "")
    # Gateway WAHA
    waha_base_url: str = os.getenv("WAHA_BASE_URL", "http://localhost:3000")
    waha_api_key: str | None = os.getenv("WAHA_API_KEY")
    waha_session: str = os.getenv("WAHA_SESSION", "default")
    # Org do piloto
    default_org_slug: str = os.getenv("DEFAULT_ORG_SLUG", "bizzu")
    # Segredo compartilhado p/ eventos da Bizzu (HMAC-SHA256). Sem ele o endpoint
    # /api/events/bizzu responde 503 (integração desligada).
    bizzu_webhook_secret: str | None = os.getenv("BIZZU_WEBHOOK_SECRET")
    # LLM (Groq) — cérebro do fluxo de survey (interpretação de respostas livres,
    # opt-out, perguntas) + classificação de feedback. Sem chave = desligado e o
    # fluxo determinístico segue intacto. LLM_ENABLED=0 força OFF mesmo com chave.
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    llm_enabled: bool = (
        os.getenv("LLM_ENABLED", "1") == "1" and bool(os.getenv("GROQ_API_KEY"))
    )
    # Modo de teste: aceita mensagens do "chat consigo mesmo" (ver webhook.py).
    # NUNCA ligar em produção — existe só para o E2E com um único número.
    self_chat_test: bool = os.getenv("SELF_CHAT_TEST", "0") == "1"


settings = Settings()
