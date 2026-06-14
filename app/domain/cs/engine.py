"""Motor de Playbooks (Fase 2) — gatilho → ação, função quase-pura.

Lê os playbooks `enabled` de uma org, resolve os CANDIDATOS de cada gatilho a partir
dos dados que JÁ temos (snapshot `partner` do contato + FeedbackItem + Health Score da
Fase 1) e, para cada candidato, executa a ação do playbook:

- `create_task`: cria uma `CsTask` na fila de CS (idempotente por `dedup_key`).
- `alert_owner`: avisa o dono no WhatsApp (reusa `owner_phone` + canal injetado),
  SÓ quando `dry_run=False` E `messaging` presente E `owner_phone` configurado.

Princípios (ver docs/FASE2_PLAYBOOKS_SPEC.md §3):
- Sem rede salvo a ação `alert_owner`. Sem `eval`: a condição (`trigger_config`) é
  avaliada por COMPARAÇÃO DE CHAVES, explícita por gatilho.
- `dry_run=True` (default) não grava NADA — só relata o que faria (`tasks_would_create`).
- Idempotência: `dedup_key = f"{trigger_type}:{contact_id}:{YYYY-MM}"`; rodar de novo no
  mesmo mês não duplica (conta como `skipped_duplicate`).
- Reaproveita `compute_health` (Fase 1) e a leitura do snapshot `partner` do contato.

NUNCA lança por causa de um playbook ruim: cada playbook roda isolado; erro só conta.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cs.health import compute_health
from app.domain.interfaces.messaging_service import IMessagingService
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem
from app.models.playbook import CsTask, Playbook

logger = logging.getLogger(__name__)

# Gatilhos suportados (validados também na API). Fonte da verdade do vocabulário.
TRIGGER_TYPES: tuple[str, ...] = (
    "nps_detractor",
    "health_at_risk",
    "inactive_days",
    "renewal_soon",
    "churn_detected",
)
ACTION_TYPES: tuple[str, ...] = ("create_task", "alert_owner")
PRIORITIES: tuple[str, ...] = ("baixa", "normal", "alta", "urgente")

# Defaults de condição por gatilho (espelham os exemplos da spec).
DEFAULT_MAX_SCORE = 6          # nps_detractor: score <= 6
DEFAULT_BAND = "at_risk"       # health_at_risk
DEFAULT_INACTIVE_DAYS = 14     # inactive_days
DEFAULT_DAYS_BEFORE = 7        # renewal_soon


@dataclass
class Candidate:
    """Um alvo resolvido por um gatilho: o contato + o snapshot que motivou a regra."""

    contact: Contact
    snapshot: dict[str, Any]
    reason: str
    feedback_item_id: Optional[uuid.UUID] = None


@dataclass
class RunReport:
    """Resultado de uma rodada do motor (formato do POST /api/playbooks/run)."""

    evaluated: int = 0                # playbooks avaliados (enabled, no filtro)
    playbooks_run: int = 0            # playbooks que resolveram >=1 candidato
    tasks_would_create: list[dict[str, Any]] = field(default_factory=list)
    tasks_created: int = 0
    skipped_duplicate: int = 0
    alerts_sent: int = 0
    dry_run: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "playbooks_run": self.playbooks_run,
            "tasks_would_create": self.tasks_would_create,
            "tasks_created": self.tasks_created,
            "skipped_duplicate": self.skipped_duplicate,
            "alerts_sent": self.alerts_sent,
            "dry_run": self.dry_run,
        }


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite devolve datetime naive; trata como UTC pra subtração não estourar."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _partner(contact: Contact) -> dict[str, Any]:
    return ((contact.profile_data or {}).get("partner")) or {}


def _nps_score(contact: Contact) -> Optional[int]:
    nps = _partner(contact).get("nps") or {}
    score = nps.get("score")
    return int(score) if isinstance(score, (int, float)) else None


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    """ISO-8601 (str do snapshot, com 'Z') -> datetime aware; tolera None/inválido."""
    if not value:
        return None
    if isinstance(value, datetime):
        return _aware(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _snapshot(contact: Contact, trigger_type: str, *, last_feedback_at: Optional[datetime] = None,
              now: datetime) -> dict[str, Any]:
    """Snapshot do gatilho gravado em `CsTask.meta` (health/banda/nps/perfil/trigger)."""
    partner = _partner(contact)
    nps_score = _nps_score(contact)
    sub_state = (partner.get("subscription") or {}).get("state")
    health = compute_health(
        nps_score=nps_score,
        perfil=partner.get("profile"),
        last_feedback_at=last_feedback_at,
        subscription_state=sub_state,
        now=now,
    )
    return {
        "trigger_type": trigger_type,
        "health": health.score,
        "health_band": health.band,
        "nps_score": nps_score,
        "perfil": partner.get("profile"),
    }


# --- Resolução de candidatos por gatilho -------------------------------------


async def _candidates_nps_detractor(
    session: AsyncSession, org_id: uuid.UUID, config: dict, now: datetime
) -> list[Candidate]:
    """Contatos cujo NPS do snapshot `partner` é <= max_score (default 6)."""
    max_score = config.get("max_score", DEFAULT_MAX_SCORE)
    try:
        max_score = int(max_score)
    except (TypeError, ValueError):
        max_score = DEFAULT_MAX_SCORE
    contacts = (
        await session.execute(select(Contact).where(Contact.organization_id == org_id))
    ).scalars().all()
    out: list[Candidate] = []
    for c in contacts:
        score = _nps_score(c)
        if score is not None and score <= max_score:
            out.append(
                Candidate(
                    contact=c,
                    snapshot=_snapshot(c, "nps_detractor", now=now),
                    reason=f"NPS {score} (<= {max_score})",
                )
            )
    return out


async def _candidates_health_at_risk(
    session: AsyncSession, org_id: uuid.UUID, config: dict, now: datetime
) -> list[Candidate]:
    """Contatos cujo Health Score (Fase 1) cai na banda alvo (default 'at_risk')."""
    band = config.get("band", DEFAULT_BAND)
    contacts = (
        await session.execute(select(Contact).where(Contact.organization_id == org_id))
    ).scalars().all()
    # Último feedback por contato (recência pesa no Health Score).
    last_by_contact = await _last_feedback_by_contact(session, org_id)
    out: list[Candidate] = []
    for c in contacts:
        last = last_by_contact.get(c.id)
        snap = _snapshot(c, "health_at_risk", last_feedback_at=last, now=now)
        if snap["health_band"] == band:
            out.append(
                Candidate(
                    contact=c,
                    snapshot=snap,
                    reason=f"Health {snap['health']} (banda {snap['health_band']})",
                )
            )
    return out


async def _candidates_inactive_days(
    session: AsyncSession, org_id: uuid.UUID, config: dict, now: datetime
) -> list[Candidate]:
    """Contatos cujo último FeedbackItem é mais antigo que `days` (ou que nunca tiveram)."""
    days = config.get("days", DEFAULT_INACTIVE_DAYS)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = DEFAULT_INACTIVE_DAYS
    contacts = (
        await session.execute(select(Contact).where(Contact.organization_id == org_id))
    ).scalars().all()
    last_by_contact = await _last_feedback_by_contact(session, org_id)
    out: list[Candidate] = []
    for c in contacts:
        last = _aware(last_by_contact.get(c.id))
        if last is None:
            reason = f"sem feedback (inativo >= {days}d)"
            inactive = True
        else:
            elapsed = (now - last).days
            inactive = elapsed >= days
            reason = f"sem feedback há {elapsed} dias (>= {days})"
        if inactive:
            out.append(
                Candidate(
                    contact=c,
                    snapshot=_snapshot(c, "inactive_days", last_feedback_at=last, now=now),
                    reason=reason,
                )
            )
    return out


async def _candidates_renewal_soon(
    session: AsyncSession, org_id: uuid.UUID, config: dict, now: datetime
) -> list[Candidate]:
    """Contatos cuja renovação (`subscription.currentPeriodEnd`) cai em <= days_before dias."""
    days_before = config.get("days_before", DEFAULT_DAYS_BEFORE)
    try:
        days_before = int(days_before)
    except (TypeError, ValueError):
        days_before = DEFAULT_DAYS_BEFORE
    contacts = (
        await session.execute(select(Contact).where(Contact.organization_id == org_id))
    ).scalars().all()
    out: list[Candidate] = []
    for c in contacts:
        sub = _partner(c).get("subscription") or {}
        renova = _parse_iso_dt(sub.get("currentPeriodEnd"))
        if renova is None:
            continue
        dias = (renova.date() - now.date()).days
        if 0 <= dias <= days_before:
            out.append(
                Candidate(
                    contact=c,
                    snapshot=_snapshot(c, "renewal_soon", now=now),
                    reason=f"renova em {dias} dia(s) (<= {days_before})",
                )
            )
    return out


async def _candidates_churn_detected(
    session: AsyncSession, org_id: uuid.UUID, config: dict, now: datetime
) -> list[Candidate]:
    """Contatos com FeedbackItem(type='churn') ainda NÃO vinculado a uma tarefa.

    "Não vinculado a tarefa ainda" = não existe CsTask apontando para aquele
    feedback_item_id (evita re-abrir tarefa para um churn já tratado). Resolve um
    candidato por feedback de churn pendente.
    """
    churns = (
        await session.execute(
            select(FeedbackItem).where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.type == "churn",
                FeedbackItem.contact_id.is_not(None),
            )
        )
    ).scalars().all()
    if not churns:
        return []

    # feedback_item_ids que já têm tarefa (não recriar).
    linked = set(
        (
            await session.execute(
                select(CsTask.feedback_item_id).where(
                    CsTask.organization_id == org_id,
                    CsTask.feedback_item_id.is_not(None),
                )
            )
        ).scalars().all()
    )

    contacts_by_id = {
        c.id: c
        for c in (
            await session.execute(select(Contact).where(Contact.organization_id == org_id))
        ).scalars().all()
    }

    out: list[Candidate] = []
    for f in churns:
        if f.id in linked:
            continue
        contact = contacts_by_id.get(f.contact_id)
        if contact is None:
            continue
        snap = _snapshot(contact, "churn_detected", now=now)
        motivo = (f.text or "").strip() or "sem motivo informado"
        out.append(
            Candidate(
                contact=contact,
                snapshot=snap,
                reason=f"churn detectado: {motivo[:160]}",
                feedback_item_id=f.id,
            )
        )
    return out


async def _last_feedback_by_contact(
    session: AsyncSession, org_id: uuid.UUID
) -> dict[uuid.UUID, datetime]:
    """Último occurred/created de FeedbackItem por contato (recência p/ o Health Score)."""
    rows = (
        await session.execute(
            select(FeedbackItem.contact_id, FeedbackItem.occurred_at, FeedbackItem.created_at).where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.contact_id.is_not(None),
            )
        )
    ).all()
    best: dict[uuid.UUID, datetime] = {}
    for cid, occ, created in rows:
        when = _aware(occ) or _aware(created)
        if when is None:
            continue
        if cid not in best or when > best[cid]:
            best[cid] = when
    return best


_RESOLVERS = {
    "nps_detractor": _candidates_nps_detractor,
    "health_at_risk": _candidates_health_at_risk,
    "inactive_days": _candidates_inactive_days,
    "renewal_soon": _candidates_renewal_soon,
    "churn_detected": _candidates_churn_detected,
}


# --- Ações --------------------------------------------------------------------


def _interpolate(template: str, contact: Contact) -> str:
    """Interpola {nome} (e {whatsapp}) no título da tarefa. Sem nome -> 'cliente'."""
    nome = (contact.name or "").strip() or "cliente"
    try:
        return template.format(nome=nome, whatsapp=contact.phone)
    except (KeyError, IndexError, ValueError):
        # Template com placeholder desconhecido: devolve cru (best-effort, nunca quebra).
        return template


def _dedup_key(trigger_type: str, contact_id: Optional[uuid.UUID], now: datetime) -> Optional[str]:
    """f"{trigger_type}:{contact_id}:{YYYY-MM}". Sem contato => None (sem dedup)."""
    if contact_id is None:
        return None
    return f"{trigger_type}:{contact_id}:{now:%Y-%m}"


def _normalize_priority(value: Any) -> str:
    return value if value in PRIORITIES else "normal"


async def _owner_phone(session: AsyncSession, org_id: uuid.UUID) -> Optional[str]:
    org = await session.get(Organization, org_id)
    return (org.settings or {}).get("owner_phone") if org else None


async def run_playbooks(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    triggers: Optional[Sequence[str]] = None,
    dry_run: bool = True,
    messaging: Optional[IMessagingService] = None,
    now: Optional[datetime] = None,
) -> RunReport:
    """Roda os playbooks `enabled` da org e devolve um RunReport.

    - `triggers`: se dado, só avalia playbooks cujo `trigger_type` está na lista.
    - `dry_run=True` (default): NÃO grava nada — só relata o que faria.
    - `messaging`: canal para a ação `alert_owner` (só usado com `dry_run=False`).
    - `now`: instante de referência (injetável nos testes).
    """
    now = now or datetime.now(timezone.utc)
    report = RunReport(dry_run=dry_run)

    stmt = select(Playbook).where(
        Playbook.organization_id == org_id, Playbook.enabled.is_(True)
    )
    if triggers:
        stmt = stmt.where(Playbook.trigger_type.in_(list(triggers)))
    playbooks = (await session.execute(stmt.order_by(Playbook.created_at))).scalars().all()

    # Telefone do dono (carregado 1x; só importa para alert_owner com dry_run=False).
    owner_phone: Optional[str] = None
    if not dry_run and messaging is not None:
        owner_phone = await _owner_phone(session, org_id)

    for pb in playbooks:
        report.evaluated += 1
        resolver = _RESOLVERS.get(pb.trigger_type)
        if resolver is None:
            logger.warning("playbook %s: trigger_type desconhecido '%s' — ignorado", pb.id, pb.trigger_type)
            continue
        try:
            candidates = await resolver(session, org_id, pb.trigger_config or {}, now)
        except Exception:  # noqa: BLE001 — um playbook ruim nunca derruba os outros.
            logger.warning("playbook %s: falha resolvendo candidatos", pb.id, exc_info=True)
            continue

        if candidates:
            report.playbooks_run += 1

        for cand in candidates:
            if pb.action_type == "alert_owner":
                await _do_alert_owner(report, pb, cand, messaging, owner_phone, dry_run)
            else:  # create_task (default)
                await _do_create_task(session, report, pb, cand, now, dry_run)

    if not dry_run:
        await session.commit()
    return report


async def _do_create_task(
    session: AsyncSession,
    report: RunReport,
    pb: Playbook,
    cand: Candidate,
    now: datetime,
    dry_run: bool,
) -> None:
    """Cria (ou planeja) uma CsTask para o candidato. Idempotente por dedup_key."""
    config = pb.action_config or {}
    title = _interpolate(str(config.get("title") or f"Abordar {{nome}}"), cand.contact)
    priority = _normalize_priority(config.get("priority"))
    owner = config.get("owner")
    sla_hours = config.get("sla_hours")
    due_at: Optional[datetime] = None
    if sla_hours is not None:
        try:
            from datetime import timedelta

            due_at = now + timedelta(hours=float(sla_hours))
        except (TypeError, ValueError):
            due_at = None

    dedup_key = _dedup_key(pb.trigger_type, cand.contact.id, now)

    # Idempotência: já existe tarefa com este (org, dedup_key)? Conta como duplicata.
    if dedup_key is not None:
        existing = (
            await session.execute(
                select(CsTask.id).where(
                    CsTask.organization_id == pb.organization_id,
                    CsTask.dedup_key == dedup_key,
                )
            )
        ).first()
        if existing is not None:
            report.skipped_duplicate += 1
            return

    planned = {
        "playbook_id": str(pb.id),
        "playbook_nome": pb.name,
        "trigger_type": pb.trigger_type,
        "contato_id": str(cand.contact.id),
        "contato_nome": cand.contact.name,
        "title": title,
        "reason": cand.reason,
        "priority": priority,
        "owner": owner,
        "due_at": due_at.isoformat() if due_at else None,
        "dedup_key": dedup_key,
    }
    report.tasks_would_create.append(planned)

    if dry_run:
        return

    task = CsTask(
        organization_id=pb.organization_id,
        contact_id=cand.contact.id,
        playbook_id=pb.id,
        feedback_item_id=cand.feedback_item_id,
        title=title,
        reason=cand.reason,
        status="aberta",
        priority=priority,
        owner=owner,
        due_at=due_at,
        meta=cand.snapshot,
        dedup_key=dedup_key,
    )
    session.add(task)
    # Flush isola a violação de UNIQUE numa corrida (dedup concorrente) sem matar a rodada.
    try:
        await session.flush()
    except Exception:  # noqa: BLE001 — corrida no dedup: outro processo já criou.
        await session.rollback()
        report.tasks_would_create.pop()
        report.skipped_duplicate += 1
        logger.warning("create_task: colisão de dedup_key '%s' — pulando", dedup_key, exc_info=True)
        return
    report.tasks_created += 1


async def _do_alert_owner(
    report: RunReport,
    pb: Playbook,
    cand: Candidate,
    messaging: Optional[IMessagingService],
    owner_phone: Optional[str],
    dry_run: bool,
) -> None:
    """Alerta o dono no WhatsApp. SÓ envia com dry_run=False E messaging E owner_phone."""
    planned = {
        "playbook_id": str(pb.id),
        "playbook_nome": pb.name,
        "trigger_type": pb.trigger_type,
        "contato_id": str(cand.contact.id),
        "contato_nome": cand.contact.name,
        "action": "alert_owner",
        "reason": cand.reason,
    }
    report.tasks_would_create.append(planned)

    if dry_run or messaging is None or not owner_phone:
        return

    nome = (cand.contact.name or cand.contact.phone)
    config = pb.action_config or {}
    titulo = _interpolate(str(config.get("title") or "Conta pede atenção"), cand.contact)
    alert = (
        f"🔔 Playbook: {pb.name}\n"
        f"{titulo}\n"
        f"Contato: {nome} ({cand.contact.phone})\n"
        f"Motivo: {cand.reason}"
    )
    try:
        await messaging.send_text(chat_id=owner_phone, text=alert)
        report.alerts_sent += 1
    except Exception:  # noqa: BLE001 — alerta best-effort, nunca derruba a rodada.
        logger.warning("alert_owner: falha ao enviar alerta ao dono", exc_info=True)
