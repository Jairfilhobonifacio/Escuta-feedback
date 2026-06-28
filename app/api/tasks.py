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

import logging
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
from app.domain.features import feature_enabled
from app.domain.cs.health import compute_health
from app.models.core import Contact
from app.models.feedback import FeedbackItem
from app.models.playbook import CsTask, Playbook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tarefas"])

# Estados da tarefa. Ordem = funil; usada no cabeçalho de contagem.
TASK_STATUSES: tuple[str, ...] = ("aberta", "em_andamento", "concluida", "adiada")
# Esteira (Fase D): estados TERMINAIS de um FeedbackItem.action_status — já fechados,
# a esteira não os reabre/re-resolve (idempotência). Espelha o vocabulário de admin.py
# (acompanhamento): resolvido/sem_retorno/descartado são fins de linha.
_FEEDBACK_TERMINAL_STATUSES: frozenset[str] = frozenset({"resolvido", "sem_retorno", "descartado"})
# Prioridade -> rank p/ ordenação (urgente primeiro). Reusa o vocabulário do motor.
_PRIORITY_RANK = {"urgente": 0, "alta": 1, "normal": 2, "baixa": 3}
# Tamanho máximo do preview do feedback vinculado exposto no GET (texto truncado).
_FEEDBACK_PREVIEW_LEN = 140
# Tamanho do trecho do texto do feedback usado no título derivado ("Tratar: …").
_DERIVED_TITLE_SNIPPET_LEN = 80


def _feedback_preview(fb: Optional[FeedbackItem]) -> Optional[str]:
    """Texto do feedback vinculado, truncado p/ preview no GET. None se não houver texto."""
    if fb is None or not fb.text:
        return None
    txt = fb.text.strip()
    if len(txt) <= _FEEDBACK_PREVIEW_LEN:
        return txt
    return txt[: _FEEDBACK_PREVIEW_LEN - 1].rstrip() + "…"


def _derived_title(fb: FeedbackItem, contact: Optional[Contact]) -> str:
    """Título da tarefa gerada a partir de um feedback.

    Preferência: "Tratar: <trecho do texto>" (texto é o sinal mais rico). Sem texto,
    cai para tipo + contato: "Tratar churn de <nome|telefone|contato>".
    """
    txt = (fb.text or "").strip()
    if txt:
        snippet = txt if len(txt) <= _DERIVED_TITLE_SNIPPET_LEN else (
            txt[: _DERIVED_TITLE_SNIPPET_LEN - 1].rstrip() + "…"
        )
        return f"Tratar: {snippet}"
    quem = (contact.name if contact and contact.name else None) or (
        contact.phone if contact and contact.phone else None
    ) or "contato"
    return f"Tratar {fb.type} de {quem}"


def _out(
    t: CsTask,
    contact: Optional[Contact],
    playbook_nome: Optional[str],
    health: Optional[int],
    health_band: Optional[str],
    feedback_preview: Optional[str] = None,
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
        # Feedback vinculado (coluna dedicada cs_tasks.feedback_item_id). `feedback_preview`
        # é o texto truncado do FeedbackItem; só preenchido no GET (None no POST/PATCH).
        "feedback_id": str(t.feedback_item_id) if t.feedback_item_id else None,
        "feedback_preview": feedback_preview,
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
            await session.execute(
                select(Contact).where(
                    Contact.id.in_(contact_ids), Contact.organization_id == org.id
                )
            )
        ).scalars().all()
        contacts = {c.id: c for c in rows}

    playbook_names: dict[uuid.UUID, str] = {}
    if playbook_ids:
        rows = (
            await session.execute(
                select(Playbook.id, Playbook.name).where(
                    Playbook.id.in_(playbook_ids), Playbook.organization_id == org.id
                )
            )
        ).all()
        playbook_names = {pid: name for pid, name in rows}

    last_by_contact = await _last_feedback_by_contact(session, org.id) if contact_ids else {}

    # Preview do feedback vinculado: carrega só os FeedbackItem da página (evita N+1).
    feedback_ids = {t.feedback_item_id for t in page if t.feedback_item_id is not None}
    feedbacks: dict[uuid.UUID, FeedbackItem] = {}
    if feedback_ids:
        rows = (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.id.in_(feedback_ids),
                    FeedbackItem.organization_id == org.id,
                )
            )
        ).scalars().all()
        feedbacks = {f.id: f for f in rows}

    items: list[dict[str, Any]] = []
    for t in page:
        contact = contacts.get(t.contact_id) if t.contact_id else None
        health, band = _health_for(contact, last_by_contact.get(t.contact_id), now)
        fb_preview = _feedback_preview(feedbacks.get(t.feedback_item_id)) if t.feedback_item_id else None
        items.append(
            _out(
                t,
                contact,
                playbook_names.get(t.playbook_id) if t.playbook_id else None,
                health,
                band,
                feedback_preview=fb_preview,
            )
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
    """Tarefa manual (sem playbook). Exige contact_id; título obrigatório.

    `feedback_id` (opcional) vincula a tarefa a um FeedbackItem da org (coluna
    dedicada cs_tasks.feedback_item_id) — ex.: "abordar o cliente sobre este NPS".
    """

    contact_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)
    priority: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    feedback_id: str | None = None


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

    # Vínculo opcional a um FeedbackItem da org (coluna dedicada feedback_item_id).
    feedback: Optional[FeedbackItem] = None
    if body.feedback_id is not None:
        try:
            fid = uuid.UUID(body.feedback_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="feedback_id inválido")
        feedback = (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.id == fid, FeedbackItem.organization_id == org.id
                )
            )
        ).scalar_one_or_none()
        if feedback is None:
            raise HTTPException(status_code=404, detail="feedback não encontrado")

    task = CsTask(
        organization_id=org.id,
        contact_id=contact.id,
        playbook_id=None,
        feedback_item_id=feedback.id if feedback else None,
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
    return _out(task, contact, None, health, band, feedback_preview=_feedback_preview(feedback))


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
    força status=adiada. 422 em status/priority inválidos.

    Esteira (Fase D, atrás da feature `esteira_enabled` por org): quando este PATCH conclui a
    tarefa (status=concluida) e ela tem feedback_item_id, o FeedbackItem vinculado
    (mesma org) passa a action_status='resolvido', salvo se já estiver terminal
    (resolvido/descartado). Best-effort e idempotente. O retorno ganha o booleano
    `feedback_resolvido` (True só quando ESTA chamada resolveu o feedback agora)."""
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
    # Esteira (REGRA 1): estado ANTES das mutações, p/ disparar só na TRANSIÇÃO real
    # para 'concluida' (re-PATCH de uma tarefa já concluída não re-resolve o feedback,
    # preservando uma eventual reabertura manual do feedback). Espelha o `was_delivered`
    # da REGRA 2.
    was_concluida = task.status == "concluida"

    # Adiar: setar snoozed_until força status=adiada (mesmo que o corpo não mande status).
    if "snoozed_until" in sent:
        task.snoozed_until = body.snoozed_until
        if body.snoozed_until is not None:
            task.status = "adiada"

    # Esteira (Fase D, REGRA 1): este PATCH está concluindo a tarefa AGORA?
    # (transição real p/ "concluida" — não já estava concluída). Guardado p/ pós-commit.
    concluiu_agora = "status" in sent and body.status == "concluida" and not was_concluida

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

    # Esteira (Fase D, REGRA 1): concluir a tarefa resolve o feedback vinculado.
    # Best-effort (não derruba o PATCH se o feedback sumiu/erro) e idempotente: só mexe
    # quando o action_status NÃO está num estado terminal. `feedback_resolvido` é True
    # SÓ quando esta chamada resolveu de fato (no-op se já estava resolvido/descartado,
    # se a flag está OFF, se a tarefa não tem feedback ou se o status != concluida).
    feedback_resolvido = False
    if concluiu_agora and feature_enabled(org, "esteira_enabled") and task.feedback_item_id is not None:
        try:
            fb = (
                await session.execute(
                    select(FeedbackItem).where(
                        FeedbackItem.id == task.feedback_item_id,
                        FeedbackItem.organization_id == org.id,
                    )
                )
            ).scalar_one_or_none()
            if fb is not None and fb.action_status not in _FEEDBACK_TERMINAL_STATUSES:
                fb.action_status = "resolvido"
                await session.commit()
                feedback_resolvido = True
        except Exception:  # noqa: BLE001 — esteira é best-effort; nunca derruba o PATCH
            logger.exception("esteira: falha ao resolver feedback %s da tarefa %s", task.feedback_item_id, task.id)
            await session.rollback()
            # rollback EXPIRA os objetos da sessão; recarrega o task in-context para a
            # serialização abaixo não disparar lazy-load síncrono (MissingGreenlet/500).
            try:
                await session.refresh(task)
            except Exception:  # noqa: BLE001
                pass

    contact = None
    if task.contact_id is not None:
        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.id == task.contact_id, Contact.organization_id == org.id
                )
            )
        ).scalar_one_or_none()
    playbook_nome = None
    if task.playbook_id is not None:
        playbook_nome = (
            await session.execute(
                select(Playbook.name).where(
                    Playbook.id == task.playbook_id, Playbook.organization_id == org.id
                )
            )
        ).scalar_one_or_none()
    last = (await _last_feedback_by_contact(session, org.id)).get(task.contact_id) if task.contact_id else None
    health, band = _health_for(contact, last, now)
    out = _out(task, contact, playbook_nome, health, band)
    out["feedback_resolvido"] = feedback_resolvido
    return out


class GerarDeFeedbacksIn(BaseModel):
    """Filtros da geração em lote (todos opcionais, defaults sensatos).

    Seleciona FeedbackItems da org que casam os filtros enviados E que AINDA NÃO têm
    uma CsTask vinculada (idempotente). Campos com valor `None` NÃO filtram aquela coluna.
    """

    tipo: str | None = Field(default="churn")               # FeedbackItem.type
    sentimento: str | None = Field(default="negativo")      # FeedbackItem.sentiment
    action_status: str | None = Field(default=None)         # FeedbackItem.action_status (ex.: "novo")
    limite: int = Field(default=50, ge=1, le=500)


@router.post("/tarefas/gerar-de-feedbacks", status_code=201)
async def gerar_de_feedbacks(
    body: GerarDeFeedbacksIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Gera CsTasks em lote a partir de feedbacks acionáveis (operador clica; fora do
    hot-path de ingestão).

    Seleciona FeedbackItems da org que casam os filtros (`tipo`/`sentimento`/`action_status`,
    cada um opcional) E que ainda não têm tarefa vinculada — idempotente: rodar de novo não
    duplica. Para cada um, cria uma CsTask vinculada (cs_tasks.feedback_item_id), com título
    derivado e status inicial "aberta".

    Retorno: {"criadas": N, "ja_existiam": M, "tarefas": [...]} (só as criadas nesta chamada).
    """
    org = await _get_org(session)

    # IDs de feedbacks da org que JÁ têm tarefa vinculada — uma varredura só (sem N+1).
    linked_subq = (
        select(CsTask.feedback_item_id)
        .where(
            CsTask.organization_id == org.id,
            CsTask.feedback_item_id.is_not(None),
        )
        .scalar_subquery()
    )

    # Base com os filtros do corpo, reutilizada p/ os candidatos E p/ contar os já vinculados.
    matched = select(FeedbackItem.id).where(FeedbackItem.organization_id == org.id)
    if body.tipo is not None:
        matched = matched.where(FeedbackItem.type == body.tipo)
    if body.sentimento is not None:
        matched = matched.where(FeedbackItem.sentiment == body.sentimento)
    if body.action_status is not None:
        matched = matched.where(FeedbackItem.action_status == body.action_status)
    matched_subq = matched.subquery()

    # Quantos feedbacks do filtro JÁ tinham tarefa (idempotência: roda 2x e M sobe, N=0).
    ja_existiam = (
        await session.execute(
            select(func.count())
            .select_from(matched_subq)
            .where(matched_subq.c.id.in_(linked_subq))
        )
    ).scalar_one()

    # Candidatos: do filtro, os que AINDA NÃO têm tarefa vinculada. Mais antigos primeiro
    # (occurred/created) — atacar a dor mais "esquecida" antes.
    stmt = (
        select(FeedbackItem)
        .where(
            FeedbackItem.id.in_(select(matched_subq.c.id)),
            FeedbackItem.id.not_in(linked_subq),
        )
        .order_by(func.coalesce(FeedbackItem.occurred_at, FeedbackItem.created_at).asc())
        .limit(body.limite)
    )

    feedbacks = (await session.execute(stmt)).scalars().all()

    if not feedbacks:
        return {"criadas": 0, "ja_existiam": int(ja_existiam), "tarefas": []}

    # Junta os contatos dos feedbacks numa varredura (título derivado usa nome/telefone).
    contact_ids = {fb.contact_id for fb in feedbacks if fb.contact_id is not None}
    contacts: dict[uuid.UUID, Contact] = {}
    if contact_ids:
        rows = (
            await session.execute(
                select(Contact).where(
                    Contact.id.in_(contact_ids), Contact.organization_id == org.id
                )
            )
        ).scalars().all()
        contacts = {c.id: c for c in rows}

    new_tasks: list[tuple[CsTask, Optional[Contact], FeedbackItem]] = []
    for fb in feedbacks:
        contact = contacts.get(fb.contact_id) if fb.contact_id else None
        task = CsTask(
            organization_id=org.id,
            contact_id=fb.contact_id,
            playbook_id=None,
            feedback_item_id=fb.id,
            # Trava de idempotência no banco (UNIQUE org+dedup_key): além do
            # NOT IN linked_subq (read-before-write), garante que rodadas concorrentes
            # não criem 2 tarefas para o mesmo feedback.
            dedup_key=f"feedback:{fb.id}",
            title=_derived_title(fb, contact),
            status="aberta",
            priority="normal",
        )
        session.add(task)
        new_tasks.append((task, contact, fb))

    await session.commit()

    # Recência por contato p/ recomputar health (uma varredura, fora do loop).
    now = datetime.now(timezone.utc)
    last_by_contact = await _last_feedback_by_contact(session, org.id) if contact_ids else {}

    tarefas: list[dict[str, Any]] = []
    for task, contact, fb in new_tasks:
        await session.refresh(task)  # materializa created_at/updated_at do banco
        health, band = _health_for(contact, last_by_contact.get(task.contact_id), now)
        tarefas.append(
            _out(task, contact, None, health, band, feedback_preview=_feedback_preview(fb))
        )

    return {"criadas": len(tarefas), "ja_existiam": int(ja_existiam), "tarefas": tarefas}
