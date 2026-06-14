"""API da fila de Tarefas de CS (Fase 2) — /api/tarefas.

A fila priorizada de "contas a abordar hoje". Nasce de playbooks (motor) ou manual.
Mesmo padrão do painel: org única pelo slug default, `_get_org`, schemas inline,
serializer `_out`. O `health`/`health_band` é RECOMPUTADO inline (reusa a Fase 1)
para refletir o estado ATUAL do contato, não um snapshot congelado.

- GET   /api/tarefas?status=&owner=&priority=&contact_id=&playbook_id=&sort=&limit=&offset=
        → {items, total, counts_by_status:{aberta,em_andamento,concluida,adiada}}
- POST  /api/tarefas        → tarefa manual (201)
- PATCH /api/tarefas/{id}   → edição parcial; status=concluida grava closed_at;
                              setar snoozed_until força status=adiada.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _get_org, _partner_fields
from app.db import get_session
from app.domain.cs.engine import PRIORITIES
from app.domain.cs.health import compute_health
from app.models.core import Contact
from app.models.feedback import FeedbackItem
from app.models.playbook import CsTask, Playbook

router = APIRouter(tags=["tarefas"])

# Estados da tarefa. Ordem = funil; usada no cabeçalho de contagem.
TASK_STATUSES: tuple[str, ...] = ("aberta", "em_andamento", "concluida", "adiada")
# Prioridade -> rank p/ ordenação (urgente primeiro). Reusa o vocabulário do motor.
_PRIORITY_RANK = {"urgente": 0, "alta": 1, "normal": 2, "baixa": 3}


def _out(
    t: CsTask,
    contact: Optional[Contact],
    playbook_nome: Optional[str],
    health: Optional[int],
    health_band: Optional[str],
) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "contato_id": str(t.contact_id) if t.contact_id else None,
        "contato_nome": contact.name if contact else None,
        "contato_whatsapp": contact.phone if contact else None,
        "playbook_id": str(t.playbook_id) if t.playbook_id else None,
        "playbook_nome": playbook_nome,
        "title": t.title,
        "reason": t.reason,
        "status": t.status,
        "priority": t.priority,
        "owner": t.owner,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "snoozed_until": t.snoozed_until.isoformat() if t.snoozed_until else None,
        "notes": t.notes,
        "health": health,
        "health_band": health_band,
        "meta": t.meta,
        "criada_em": t.created_at.isoformat() if t.created_at else None,
        "atualizada_em": t.updated_at.isoformat() if t.updated_at else None,
    }


def _health_for(contact: Optional[Contact], last_at: Optional[datetime], now: datetime):
    """(health, health_band) atual do contato via Health Score (Fase 1). None se sem contato."""
    if contact is None:
        return None, None
    pf = _partner_fields(contact, now)
    sub_state = (
        ((contact.profile_data or {}).get("partner") or {}).get("subscription") or {}
    ).get("state")
    r = compute_health(
        nps_score=pf["nps_score"],
        perfil=pf["perfil"],
        last_feedback_at=last_at,
        subscription_state=sub_state,
        now=now,
    )
    return r.score, r.band


async def _last_feedback_by_contact(session: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    """Último occurred/created de FeedbackItem por contato (recência do Health Score)."""
    rows = (
        await session.execute(
            select(
                FeedbackItem.contact_id,
                func.max(func.coalesce(FeedbackItem.occurred_at, FeedbackItem.created_at)),
            )
            .where(FeedbackItem.organization_id == org_id, FeedbackItem.contact_id.is_not(None))
            .group_by(FeedbackItem.contact_id)
        )
    ).all()
    return {cid: last for cid, last in rows if last is not None}


def _sla_sort_key(t: CsTask):
    """due_at asc (nulls por último) — para sort='sla'."""
    return (t.due_at is None, t.due_at or datetime.max.replace(tzinfo=timezone.utc))


@router.get("/tarefas")
async def list_tarefas(
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    contact_id: str | None = None,
    playbook_id: str | None = None,
    sort: Literal["prioridade", "recente", "sla"] = "prioridade",
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Fila de tarefas da org + contato/playbook juntados + health recomputado.

    Retorno: {"items": [...], "total": N, "counts_by_status": {aberta, ...}}.
    `total` = total do filtro (ignora limit/offset). `counts_by_status` cobre os 4
    estados (zeros inclusos) sob o MESMO filtro EXCETO o próprio `status` (abas no front).

    `sort`: `prioridade` (default: urgente→baixa, depois due_at asc) | `recente`
    (created desc) | `sla` (due_at asc, nulls por último).
    """
    org = await _get_org(session)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    base = select(CsTask).where(CsTask.organization_id == org.id)
    if status:
        base = base.where(CsTask.status == status)
    if owner:
        base = base.where(CsTask.owner == owner)
    if priority:
        base = base.where(CsTask.priority == priority)
    if contact_id:
        try:
            base = base.where(CsTask.contact_id == uuid.UUID(contact_id))
        except ValueError:
            raise HTTPException(status_code=422, detail="contact_id inválido")
    if playbook_id:
        try:
            base = base.where(CsTask.playbook_id == uuid.UUID(playbook_id))
        except ValueError:
            raise HTTPException(status_code=422, detail="playbook_id inválido")

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    tasks = (await session.execute(base)).scalars().all()

    # Ordenação em Python (a fila é pequena; prioridade combina rank + due_at).
    if sort == "recente":
        tasks.sort(key=lambda t: t.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    elif sort == "sla":
        tasks.sort(key=_sla_sort_key)
    else:  # prioridade
        tasks.sort(
            key=lambda t: (
                _PRIORITY_RANK.get(t.priority, 2),
                t.due_at is None,
                t.due_at or datetime.max.replace(tzinfo=timezone.utc),
            )
        )

    page = tasks[offset : offset + limit]

    # Junta contato + playbook + health só da PÁGINA (evita N+1 desnecessário).
    now = datetime.now(timezone.utc)
    contact_ids = {t.contact_id for t in page if t.contact_id is not None}
    playbook_ids = {t.playbook_id for t in page if t.playbook_id is not None}

    contacts: dict[uuid.UUID, Contact] = {}
    if contact_ids:
        rows = (
            await session.execute(select(Contact).where(Contact.id.in_(contact_ids)))
        ).scalars().all()
        contacts = {c.id: c for c in rows}

    playbook_names: dict[uuid.UUID, str] = {}
    if playbook_ids:
        rows = (
            await session.execute(
                select(Playbook.id, Playbook.name).where(Playbook.id.in_(playbook_ids))
            )
        ).all()
        playbook_names = {pid: name for pid, name in rows}

    last_by_contact = await _last_feedback_by_contact(session, org.id) if contact_ids else {}

    items: list[dict[str, Any]] = []
    for t in page:
        contact = contacts.get(t.contact_id) if t.contact_id else None
        health, band = _health_for(contact, last_by_contact.get(t.contact_id), now)
        items.append(
            _out(t, contact, playbook_names.get(t.playbook_id) if t.playbook_id else None, health, band)
        )

    # counts_by_status: mesmo filtro MENOS o próprio status.
    counts_stmt = select(CsTask.status, func.count()).where(CsTask.organization_id == org.id)
    if owner:
        counts_stmt = counts_stmt.where(CsTask.owner == owner)
    if priority:
        counts_stmt = counts_stmt.where(CsTask.priority == priority)
    if contact_id:
        counts_stmt = counts_stmt.where(CsTask.contact_id == uuid.UUID(contact_id))
    if playbook_id:
        counts_stmt = counts_stmt.where(CsTask.playbook_id == uuid.UUID(playbook_id))
    counts_raw = dict((await session.execute(counts_stmt.group_by(CsTask.status))).all())
    counts_by_status = {s: int(counts_raw.get(s, 0)) for s in TASK_STATUSES}

    return {"items": items, "total": int(total), "counts_by_status": counts_by_status}


class TarefaCreateIn(BaseModel):
    """Tarefa manual (sem playbook). Exige contact_id; título obrigatório."""

    contact_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)
    priority: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None


@router.post("/tarefas", status_code=201)
async def create_tarefa(body: TarefaCreateIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Cria uma tarefa manual (playbook_id NULL). Exige contact_id válido da org."""
    org = await _get_org(session)
    if body.priority is not None and body.priority not in PRIORITIES:
        raise HTTPException(
            status_code=422,
            detail=f"priority inválida: '{body.priority}' (use {', '.join(PRIORITIES)})",
        )
    try:
        cid = uuid.UUID(body.contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="contact_id inválido")

    contact = (
        await session.execute(
            select(Contact).where(Contact.id == cid, Contact.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="contato não encontrado")

    task = CsTask(
        organization_id=org.id,
        contact_id=contact.id,
        playbook_id=None,
        title=body.title.strip(),
        reason=(body.reason.strip() or None) if body.reason else None,
        status="aberta",
        priority=body.priority or "normal",
        owner=(body.owner.strip() or None) if body.owner else None,
        due_at=body.due_at,
    )
    session.add(task)
    await session.commit()
    # Materializa created_at/updated_at gerados pelo banco (evita IO fora do contexto async).
    await session.refresh(task)

    now = datetime.now(timezone.utc)
    last = (await _last_feedback_by_contact(session, org.id)).get(contact.id)
    health, band = _health_for(contact, last, now)
    return _out(task, contact, None, health, band)


class TarefaPatchIn(BaseModel):
    """PATCH parcial. `model_fields_set` distingue "não enviado" de "enviado null"."""

    status: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    priority: str | None = None
    due_at: datetime | None = None
    snoozed_until: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)


@router.patch("/tarefas/{task_id}")
async def update_tarefa(
    task_id: str, body: TarefaPatchIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Edição parcial. status=concluida grava closed_at=agora; setar snoozed_until
    força status=adiada. 422 em status/priority inválidos."""
    org = await _get_org(session)
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    sent = body.model_fields_set
    if body.status is not None and body.status not in TASK_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status inválido: '{body.status}' (use {', '.join(TASK_STATUSES)})",
        )
    if body.priority is not None and body.priority not in PRIORITIES:
        raise HTTPException(
            status_code=422,
            detail=f"priority inválida: '{body.priority}' (use {', '.join(PRIORITIES)})",
        )

    task = (
        await session.execute(
            select(CsTask).where(CsTask.id == tid, CsTask.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")

    now = datetime.now(timezone.utc)

    # Adiar: setar snoozed_until força status=adiada (mesmo que o corpo não mande status).
    if "snoozed_until" in sent:
        task.snoozed_until = body.snoozed_until
        if body.snoozed_until is not None:
            task.status = "adiada"

    if "status" in sent and body.status is not None:
        task.status = body.status
        if body.status == "concluida":
            if task.closed_at is None:
                task.closed_at = now
        else:
            # Reabrir/mover para fora de concluída limpa o closed_at.
            task.closed_at = None

    if "owner" in sent:
        task.owner = (body.owner.strip() or None) if body.owner else None
    if "priority" in sent and body.priority is not None:
        task.priority = body.priority
    if "due_at" in sent:
        task.due_at = body.due_at
    if "notes" in sent:
        task.notes = (body.notes.strip() or None) if body.notes else None

    await session.commit()
    # `updated_at` (onupdate) é gerado pelo banco e expira pós-UPDATE — recarrega in-context.
    await session.refresh(task)

    contact = None
    if task.contact_id is not None:
        contact = (
            await session.execute(select(Contact).where(Contact.id == task.contact_id))
        ).scalar_one_or_none()
    playbook_nome = None
    if task.playbook_id is not None:
        playbook_nome = (
            await session.execute(select(Playbook.name).where(Playbook.id == task.playbook_id))
        ).scalar_one_or_none()
    last = (await _last_feedback_by_contact(session, org.id)).get(task.contact_id) if task.contact_id else None
    health, band = _health_for(contact, last, now)
    return _out(task, contact, playbook_nome, health, band)
