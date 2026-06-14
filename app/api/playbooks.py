"""API de Playbooks (Fase 2) — CRUD das regras + disparo do motor.

Mesmo padrão do resto do painel (admin.py): org única pelo slug default, helper
`_get_org`, schemas Pydantic inline, serializer `_out`. Os enums (trigger/action/
priority) são validados aqui (sem CHECK no banco — vocabulário pode crescer).

- GET    /api/playbooks            → lista
- POST   /api/playbooks            → cria (201; 409 nome duplicado; 422 enum inválido)
- PATCH  /api/playbooks/{id}       → edição parcial (via model_fields_set)
- DELETE /api/playbooks/{id}       → 204
- POST   /api/playbooks/run        → roda o motor (dry_run=true por default); chamável
                                     por cron externo, igual ao /api/digest/run.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _get_org, get_messaging
from app.db import get_session
from app.domain.cs.engine import ACTION_TYPES, PRIORITIES, TRIGGER_TYPES, run_playbooks
from app.domain.interfaces.messaging_service import IMessagingService
from app.models.playbook import Playbook

router = APIRouter(tags=["playbooks"])


def _out(pb: Playbook) -> dict[str, Any]:
    return {
        "id": str(pb.id),
        "name": pb.name,
        "description": pb.description,
        "enabled": pb.enabled,
        "trigger_type": pb.trigger_type,
        "trigger_config": pb.trigger_config or {},
        "action_type": pb.action_type,
        "action_config": pb.action_config or {},
        "created_at": pb.created_at.isoformat() if pb.created_at else None,
        "updated_at": pb.updated_at.isoformat() if pb.updated_at else None,
    }


class PlaybookIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    trigger_type: str = Field(min_length=1, max_length=60)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    action_type: str = Field(min_length=1, max_length=60)
    action_config: dict[str, Any] = Field(default_factory=dict)


class PlaybookPatchIn(BaseModel):
    """PATCH parcial. `model_fields_set` distingue "não enviado" de "enviado como null"."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    trigger_type: str | None = Field(default=None, min_length=1, max_length=60)
    trigger_config: dict[str, Any] | None = None
    action_type: str | None = Field(default=None, min_length=1, max_length=60)
    action_config: dict[str, Any] | None = None


def _validate_enums(trigger_type: str | None, action_type: str | None, priority: Any) -> None:
    if trigger_type is not None and trigger_type not in TRIGGER_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"trigger_type inválido: '{trigger_type}' (use {', '.join(TRIGGER_TYPES)})",
        )
    if action_type is not None and action_type not in ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"action_type inválido: '{action_type}' (use {', '.join(ACTION_TYPES)})",
        )
    if priority is not None and priority not in PRIORITIES:
        raise HTTPException(
            status_code=422,
            detail=f"priority inválida: '{priority}' (use {', '.join(PRIORITIES)})",
        )


@router.get("/playbooks")
async def list_playbooks(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    org = await _get_org(session)
    rows = (
        (
            await session.execute(
                select(Playbook)
                .where(Playbook.organization_id == org.id)
                .order_by(Playbook.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_out(pb) for pb in rows]


@router.post("/playbooks", status_code=201)
async def create_playbook(body: PlaybookIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _get_org(session)
    _validate_enums(body.trigger_type, body.action_type, (body.action_config or {}).get("priority"))

    exists = (
        await session.execute(
            select(Playbook).where(Playbook.organization_id == org.id, Playbook.name == body.name)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"já existe um playbook chamado '{body.name}'")

    pb = Playbook(
        organization_id=org.id,
        name=body.name.strip(),
        description=(body.description.strip() or None) if body.description else None,
        enabled=body.enabled,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config or {},
        action_type=body.action_type,
        action_config=body.action_config or {},
    )
    session.add(pb)
    await session.commit()
    # Materializa created_at/updated_at gerados pelo banco (evita IO fora do contexto async).
    await session.refresh(pb)
    return _out(pb)


@router.patch("/playbooks/{playbook_id}")
async def update_playbook(
    playbook_id: str, body: PlaybookPatchIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    org = await _get_org(session)
    try:
        pid = uuid.UUID(playbook_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    sent = body.model_fields_set
    next_priority = (body.action_config or {}).get("priority") if "action_config" in sent else None
    _validate_enums(
        body.trigger_type if "trigger_type" in sent else None,
        body.action_type if "action_type" in sent else None,
        next_priority,
    )

    pb = (
        await session.execute(
            select(Playbook).where(Playbook.id == pid, Playbook.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if pb is None:
        raise HTTPException(status_code=404, detail="playbook não encontrado")

    if "name" in sent and body.name is not None:
        # Nome novo não pode colidir com OUTRO playbook da org.
        dup = (
            await session.execute(
                select(Playbook).where(
                    Playbook.organization_id == org.id,
                    Playbook.name == body.name,
                    Playbook.id != pid,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status_code=409, detail=f"já existe um playbook chamado '{body.name}'")
        pb.name = body.name.strip()
    if "description" in sent:
        pb.description = (body.description.strip() or None) if body.description else None
    if "enabled" in sent and body.enabled is not None:
        pb.enabled = body.enabled
    if "trigger_type" in sent and body.trigger_type is not None:
        pb.trigger_type = body.trigger_type
    if "trigger_config" in sent and body.trigger_config is not None:
        pb.trigger_config = body.trigger_config
    if "action_type" in sent and body.action_type is not None:
        pb.action_type = body.action_type
    if "action_config" in sent and body.action_config is not None:
        pb.action_config = body.action_config

    await session.commit()
    # `updated_at` (onupdate) é gerado pelo banco e expira pós-UPDATE — recarrega in-context.
    await session.refresh(pb)
    return _out(pb)


@router.delete("/playbooks/{playbook_id}", status_code=204)
async def delete_playbook(playbook_id: str, session: AsyncSession = Depends(get_session)) -> None:
    org = await _get_org(session)
    try:
        pid = uuid.UUID(playbook_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    pb = (
        await session.execute(
            select(Playbook).where(Playbook.id == pid, Playbook.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if pb is None:
        raise HTTPException(status_code=404, detail="playbook não encontrado")
    await session.delete(pb)
    await session.commit()


@router.post("/playbooks/run")
async def run_playbooks_endpoint(
    dry_run: bool = True,
    session: AsyncSession = Depends(get_session),
    messaging: IMessagingService = Depends(get_messaging),
) -> dict[str, Any]:
    """Roda o motor de playbooks da org. `dry_run=true` (default) não grava nada.

    Ponto de entrada de um cron externo (Modal/n8n), igual ao /api/digest/run. Com
    `dry_run=false`, cria as tarefas e (para playbooks alert_owner) avisa o dono.
    """
    org = await _get_org(session)
    report = await run_playbooks(session, org.id, dry_run=dry_run, messaging=messaging)
    return report.as_dict()
