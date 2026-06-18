"""API PÚBLICA de integração — sistemas externos puxam dados por tag, via token.

Item da reunião: expor uma porta read-only para terceiros (ex.: BI, CRM, automações)
buscarem feedbacks e clientes da org filtrando por "tag" (selo de campanha). Tudo
GET, somente leitura, sempre filtrado por `_get_org` (a org única do piloto).

Auth (contrato): header `X-API-Key` com o token de `settings.integration_api_key`.
- Sem a env configurada -> 503 (integração DESLIGADA) — mesma filosofia do webhook
  da Bizzu e do LLM: sem segredo, a porta nem abre.
- Header ausente/errado -> 401. A comparação usa `hmac.compare_digest` (constante no
  tempo, evita timing attack). A CHAVE NUNCA é logada.

O router é montado com prefixo /api no main.py, então as rotas são declaradas com
/integration (resultando em /api/integration/...). Reusa os helpers do admin.py
(`_get_org`, `_feedback_out`, `_selo_match_clause`, `_partner_fields`,
`_nps_bucket_label`) e o validador canônico de WhatsApp — sem duplicar regra.
"""
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import (
    _feedback_out,
    _get_org,
    _partner_fields,
    _selo_match_clause,
)
from app.config import settings
from app.db import get_session
from app.domain.contacts.whatsapp import tem_whatsapp as tem_whatsapp_fn
from app.models.core import Contact
from app.models.feedback import FeedbackItem

router = APIRouter(tags=["integration"])


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependency de auth da API de integração.

    - settings.integration_api_key None/"" -> 503 (integração desligada): sem token
      configurado no servidor, a porta nem existe.
    - header X-API-Key ausente ou diferente do token -> 401. Comparação constante no
      tempo via hmac.compare_digest. NUNCA logamos a chave (nem a recebida nem a real).
    """
    expected = settings.integration_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="integração desligada (sem INTEGRATION_API_KEY)")
    # compare_digest exige str/bytes — header ausente vira "" (nunca casa um token real).
    if not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="X-API-Key ausente ou inválida")


def _clip_limite(limite: int) -> int:
    """Clampa o tamanho da página em [1, 500] (mesmo teto do feed do painel)."""
    return max(1, min(int(limite), 500))


# --- GET /integration/feedbacks ----------------------------------------------


@router.get("/integration/feedbacks")
async def integration_feedbacks(
    selo: str | None = None,
    tipo: str | None = None,
    limite: int = 100,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
) -> list[dict[str, Any]]:
    """Feedbacks da org para sistemas externos (read-only), JSON enxuto.

    Filtros (todos opcionais; ausentes = sem recorte):
    - `selo`: "puxar por tag" (pedido da reunião) — só feedbacks de CONTATOS com aquele
      selo de campanha aplicado (`Contact.profile_data["selos"]`, ver campanha.py).
    - `tipo`: filtra por `FeedbackItem.type` ('nps' | 'churn' | 'elogio' | ...).
    - `limite`: tamanho da página (clampado em [1, 500]); ordem = mais recente primeiro.

    Cada item reusa `_feedback_out` (mesma forma do feed do painel) e expõe um
    subconjunto estável: id, tipo, texto, sentimento, action_status, selos,
    contato_nome, occurred_at."""
    org = await _get_org(session)
    limite = _clip_limite(limite)
    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"

    stmt = (
        select(FeedbackItem, Contact)
        .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
        .where(FeedbackItem.organization_id == org.id)
    )
    if selo:
        stmt = stmt.where(_selo_match_clause(selo, dialect))
    if tipo:
        stmt = stmt.where(FeedbackItem.type == tipo)

    # occurred_at é NULLABLE (ex.: sinais sem data de ocorrência) — ordenar só por ele
    # joga os NULL pro fim/erra a ordem. Usa a MESMA chave do painel: coalesce(occurred, created).
    order_key = func.coalesce(FeedbackItem.occurred_at, FeedbackItem.created_at)
    rows = (
        await session.execute(
            stmt.order_by(order_key.desc(), FeedbackItem.created_at.desc()).limit(limite)
        )
    ).all()

    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for f, c in rows:
        full = _feedback_out(f, c, now)
        out.append(
            {
                "id": full["id"],
                "tipo": full["type"],
                "texto": full["text"],
                "sentimento": full["sentiment"],
                "action_status": full["action_status"],
                "selos": full["selos"],
                "contato_nome": full["contato_nome"],
                "occurred_at": full["occurred_em"],
            }
        )
    return out


# --- GET /integration/clientes -----------------------------------------------


@router.get("/integration/clientes")
async def integration_clientes(
    estado: str | None = None,
    limite: int = 100,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_api_key),
) -> list[dict[str, Any]]:
    """Clientes contatáveis da org para sistemas externos (read-only), JSON enxuto.

    Filtros (opcionais):
    - `estado`: estado da assinatura no snapshot partner (JSON path), ex.: 'cancelled',
      'active_paying'. Ausente = todos.
    - `limite`: tamanho da página (clampado em [1, 500]).

    Cada item: id, nome, whatsapp, tem_whatsapp (validador canônico), estado, selos,
    health_band (banda do Health Score CS)."""
    from app.domain.cs.health import compute_health

    org = await _get_org(session)
    limite = _clip_limite(limite)

    stmt = select(Contact).where(Contact.organization_id == org.id)
    if estado:
        stmt = stmt.where(
            Contact.profile_data["partner"]["subscription"]["state"].as_string() == estado
        )

    contacts = (
        (await session.execute(stmt.order_by(Contact.created_at.desc()).limit(limite)))
        .scalars()
        .all()
    )

    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for c in contacts:
        pf = _partner_fields(c, now)
        sub_state = (
            ((c.profile_data or {}).get("partner") or {}).get("subscription") or {}
        ).get("state")
        health = compute_health(
            nps_score=pf["nps_score"],
            perfil=pf["perfil"],
            subscription_state=sub_state,
            now=now,
        )
        raw_selos = (c.profile_data or {}).get("selos")
        selos = [str(x) for x in raw_selos if x] if isinstance(raw_selos, list) else []
        out.append(
            {
                "id": str(c.id),
                "nome": c.name,
                "whatsapp": c.phone,
                "tem_whatsapp": tem_whatsapp_fn(c.phone),
                "estado": sub_state,
                "selos": selos,
                "health_band": health.band,
            }
        )
    return out
