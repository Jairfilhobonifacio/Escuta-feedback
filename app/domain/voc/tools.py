"""As 7 tools do Agente VoC — function-calling sobre os models JÁ existentes.

Cada tool opera direto na `AsyncSession` (sem tocar `app/api/`), replicando a lógica
que os endpoints atuais usam:

  1. registrar_abordagem  — marca um FeedbackItem como "abordado" (Felipe falou com o cliente).
  2. aplicar_selo         — roteia o feedback por time/responsável (team_tag / assignee).
  3. criar_tarefa         — cria uma CsTask manual na fila de CS.
  4. vincular_melhoria    — liga um FeedbackItem a uma Improvement do roadmap ("fechar o loop").
  5. atualizar_feedback   — muda action_status / assignee / team_tag / nota interna do FeedbackItem.
  6. enviar_whatsapp      — manda mensagem ao contato; atrás de flag + 3 gates; NO-OP com flag OFF.
  7. ler_perfil_contato   — visão consolidada do contato (igual em espírito à ficha 360).

Contrato de cada executor: recebe um dict de argumentos (o registry já parseia) e
devolve um dict serializável SEMPRE com a chave booleana "ok". NUNCA precisa levantar:
erros de validação viram {"ok": false, "error": ...} (o registry também blinda, mas as
tools preferem mensagens claras que o modelo entenda e possa corrigir). Não faz commit:
a sessão é gerida por quem chama (o resolver dá flush no fim do turno), igual às demais
operações do resolver — exceto enviar_whatsapp, que grava o outbound como o /notify faz.

Sem schema novo, sem migration: tudo cabe nos models de feedback/playbook/improvement/core.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.contacts.whatsapp import tem_whatsapp
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.voc.registry import VoCToolRegistry
from app.models.core import Contact
from app.models.feedback import FeedbackItem
from app.models.improvement import Improvement
from app.models.playbook import CsTask
from app.models.survey import Message, SurveyResponse

logger = logging.getLogger(__name__)

# Vocabulários validados na API (fonte da verdade espelhada de app/api/admin.py e
# app/domain/cs/engine.py). Replicados aqui para não importar de app/api/ (fora da
# fronteira e criaria ciclo). Mantidos em sincronia conscientemente.
ACTION_STATUSES: frozenset[str] = frozenset(
    {"novo", "em_analise", "planejado", "resolvido", "descartado"}
)
PRIORITIES: frozenset[str] = frozenset({"baixa", "normal", "alta", "urgente"})


@dataclass
class VoCToolContext:
    """Tudo que as tools precisam para operar — capturado em closure por tool.

    `now` é injetável (testes determinísticos). `messaging` pode ser None (a tool de
    WhatsApp vira NO-OP sem canal, além dos outros gates).
    """

    session: AsyncSession
    org_id: uuid.UUID
    messaging: Optional[IMessagingService] = None
    waha_session: str = "default"
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


# --- helpers de lookup (sempre escopados por org — multi-tenant) -----------------


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def _get_feedback(ctx: VoCToolContext, raw_id: Any) -> Optional[FeedbackItem]:
    fid = _as_uuid(raw_id)
    if fid is None:
        return None
    return (
        await ctx.session.execute(
            select(FeedbackItem).where(
                FeedbackItem.id == fid,
                FeedbackItem.organization_id == ctx.org_id,
            )
        )
    ).scalar_one_or_none()


async def _get_contact(ctx: VoCToolContext, raw_id: Any) -> Optional[Contact]:
    cid = _as_uuid(raw_id)
    if cid is None:
        return None
    return (
        await ctx.session.execute(
            select(Contact).where(
                Contact.id == cid,
                Contact.organization_id == ctx.org_id,
            )
        )
    ).scalar_one_or_none()


async def _get_improvement(ctx: VoCToolContext, raw_id: Any) -> Optional[Improvement]:
    iid = _as_uuid(raw_id)
    if iid is None:
        return None
    return (
        await ctx.session.execute(
            select(Improvement).where(
                Improvement.id == iid,
                Improvement.organization_id == ctx.org_id,
            )
        )
    ).scalar_one_or_none()


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite devolve datetime naive; trata como UTC para subtração não estourar."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# --- (1) registrar abordagem ------------------------------------------------------


async def _registrar_abordagem(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Marca um FeedbackItem como 'abordado' (Felipe já falou com o cliente).

    Espelha PATCH /api/feedbacks/{id} {abordado:true}: seta abordado=True e carimba
    abordado_em=now; opcionalmente registra uma nota interna (action_note).
    """
    feedback = await _get_feedback(ctx, args.get("feedback_id"))
    if feedback is None:
        return {"ok": False, "error": "feedback não encontrado nesta organização"}
    feedback.abordado = True
    feedback.abordado_em = ctx.now()
    nota = args.get("nota")
    if nota and str(nota).strip():
        feedback.action_note = str(nota).strip()[:2000]
    await ctx.session.flush()
    return {
        "ok": True,
        "feedback_id": str(feedback.id),
        "abordado": True,
        "abordado_em": feedback.abordado_em.isoformat(),
    }


_REGISTRAR_ABORDAGEM_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback_id": {
            "type": "string",
            "description": "ID (UUID) do FeedbackItem que foi abordado.",
        },
        "nota": {
            "type": "string",
            "description": "Nota interna opcional sobre a abordagem (o que foi dito/combinado).",
        },
    },
    "required": ["feedback_id"],
}


# --- (2) aplicar selo / tag (roteamento por time) --------------------------------


async def _aplicar_selo(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Aplica selo/tag de roteamento ao FeedbackItem: team_tag e/ou assignee.

    Espelha o roteamento do Board (PATCH do feedback): team_tag = produto/suporte/
    comercial/cs; assignee = quem do time cuida. Pelo menos um dos dois é obrigatório.
    """
    feedback = await _get_feedback(ctx, args.get("feedback_id"))
    if feedback is None:
        return {"ok": False, "error": "feedback não encontrado nesta organização"}
    team_tag = args.get("team_tag")
    assignee = args.get("assignee")
    if not (team_tag and str(team_tag).strip()) and not (assignee and str(assignee).strip()):
        return {"ok": False, "error": "informe team_tag e/ou assignee"}
    if team_tag and str(team_tag).strip():
        feedback.team_tag = str(team_tag).strip()[:60]
    if assignee and str(assignee).strip():
        feedback.assignee = str(assignee).strip()[:120]
    await ctx.session.flush()
    return {
        "ok": True,
        "feedback_id": str(feedback.id),
        "team_tag": feedback.team_tag,
        "assignee": feedback.assignee,
    }


_APLICAR_SELO_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback_id": {"type": "string", "description": "ID (UUID) do FeedbackItem."},
        "team_tag": {
            "type": "string",
            "description": "Time responsável: produto | suporte | comercial | cs (roteamento).",
        },
        "assignee": {
            "type": "string",
            "description": "Pessoa do time que vai cuidar (slug/email/nome).",
        },
    },
    "required": ["feedback_id"],
}


# --- (3) criar tarefa (CsTask manual) --------------------------------------------


def _normalize_priority(value: Any) -> str:
    return value if value in PRIORITIES else "normal"


async def _criar_tarefa(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Cria uma CsTask manual (playbook_id NULL) na fila de CS.

    Espelha _do_create_task do motor de playbooks, porém manual: dedup_key fica NULL
    (tarefas manuais não deduplicam — múltiplos NULL convivem no UNIQUE). title é
    obrigatório; priority validada (default 'normal'); pode amarrar a um contato e/ou
    a um feedback (contexto). sla_hours opcional vira due_at = now + sla_hours.
    """
    title = args.get("title")
    if not title or not str(title).strip():
        return {"ok": False, "error": "title é obrigatório"}

    contact_id: Optional[uuid.UUID] = None
    if args.get("contact_id"):
        contact = await _get_contact(ctx, args.get("contact_id"))
        if contact is None:
            return {"ok": False, "error": "contato não encontrado nesta organização"}
        contact_id = contact.id

    feedback_item_id: Optional[uuid.UUID] = None
    if args.get("feedback_id"):
        feedback = await _get_feedback(ctx, args.get("feedback_id"))
        if feedback is None:
            return {"ok": False, "error": "feedback não encontrado nesta organização"}
        feedback_item_id = feedback.id

    now = ctx.now()
    due_at: Optional[datetime] = None
    sla_hours = args.get("sla_hours")
    if sla_hours is not None:
        try:
            due_at = now + timedelta(hours=float(sla_hours))
        except (TypeError, ValueError):
            due_at = None

    task = CsTask(
        organization_id=ctx.org_id,
        contact_id=contact_id,
        playbook_id=None,
        feedback_item_id=feedback_item_id,
        title=str(title).strip()[:300],
        reason=(str(args["reason"]).strip()[:2000] if args.get("reason") else None),
        status="aberta",
        priority=_normalize_priority(args.get("priority")),
        owner=(str(args["owner"]).strip()[:120] if args.get("owner") else None),
        due_at=due_at,
        dedup_key=None,
    )
    ctx.session.add(task)
    await ctx.session.flush()
    return {
        "ok": True,
        "task_id": str(task.id),
        "title": task.title,
        "priority": task.priority,
        "status": task.status,
        "due_at": task.due_at.isoformat() if task.due_at else None,
    }


_CRIAR_TAREFA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Título da tarefa (o que fazer)."},
        "contact_id": {"type": "string", "description": "ID (UUID) do contato alvo (opcional)."},
        "feedback_id": {
            "type": "string",
            "description": "ID (UUID) do FeedbackItem que motivou a tarefa (opcional).",
        },
        "reason": {"type": "string", "description": "Contexto/motivo da tarefa (opcional)."},
        "priority": {
            "type": "string",
            "enum": ["baixa", "normal", "alta", "urgente"],
            "description": "Prioridade (default normal).",
        },
        "owner": {"type": "string", "description": "Responsável pela tarefa (opcional)."},
        "sla_hours": {
            "type": "number",
            "description": "Prazo em horas a partir de agora (vira due_at). Opcional.",
        },
    },
    "required": ["title"],
}


# --- (4) vincular melhoria (fechar o loop) ---------------------------------------


async def _vincular_melhoria(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Liga um FeedbackItem a uma Improvement existente (FeedbackItem.improvement_id).

    Espelha o "fechar o loop": um feedback pertence a no máximo UMA melhoria. Ambos os
    ids são obrigatórios e precisam existir na org.
    """
    feedback = await _get_feedback(ctx, args.get("feedback_id"))
    if feedback is None:
        return {"ok": False, "error": "feedback não encontrado nesta organização"}
    improvement = await _get_improvement(ctx, args.get("improvement_id"))
    if improvement is None:
        return {"ok": False, "error": "melhoria não encontrada nesta organização"}
    feedback.improvement_id = improvement.id
    await ctx.session.flush()
    return {
        "ok": True,
        "feedback_id": str(feedback.id),
        "improvement_id": str(improvement.id),
        "improvement_title": improvement.title,
    }


_VINCULAR_MELHORIA_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback_id": {"type": "string", "description": "ID (UUID) do FeedbackItem."},
        "improvement_id": {"type": "string", "description": "ID (UUID) da Improvement (roadmap)."},
    },
    "required": ["feedback_id", "improvement_id"],
}


# --- (5) atualizar feedback (status / responsável / nota) ------------------------


async def _atualizar_feedback(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Atualiza campos de workflow do FeedbackItem: action_status, assignee, team_tag,
    action_note. Só altera o que vier; action_status é validado contra o vocabulário.
    """
    feedback = await _get_feedback(ctx, args.get("feedback_id"))
    if feedback is None:
        return {"ok": False, "error": "feedback não encontrado nesta organização"}

    changed: list[str] = []
    status = args.get("action_status")
    if status is not None:
        if status not in ACTION_STATUSES:
            return {
                "ok": False,
                "error": f"action_status inválido: {status!r} (use {sorted(ACTION_STATUSES)})",
            }
        feedback.action_status = status
        changed.append("action_status")
    if args.get("assignee") is not None:
        feedback.assignee = (str(args["assignee"]).strip()[:120] or None) if args["assignee"] else None
        changed.append("assignee")
    if args.get("team_tag") is not None:
        feedback.team_tag = (str(args["team_tag"]).strip()[:60] or None) if args["team_tag"] else None
        changed.append("team_tag")
    if args.get("action_note") is not None:
        feedback.action_note = (str(args["action_note"]).strip()[:2000] or None) if args["action_note"] else None
        changed.append("action_note")

    if not changed:
        return {"ok": False, "error": "nada para atualizar (informe ao menos um campo)"}
    await ctx.session.flush()
    return {
        "ok": True,
        "feedback_id": str(feedback.id),
        "updated": changed,
        "action_status": feedback.action_status,
    }


_ATUALIZAR_FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback_id": {"type": "string", "description": "ID (UUID) do FeedbackItem."},
        "action_status": {
            "type": "string",
            "enum": ["novo", "em_analise", "planejado", "resolvido", "descartado"],
            "description": "Estágio do tratamento interno.",
        },
        "assignee": {"type": "string", "description": "Responsável (vazio limpa)."},
        "team_tag": {"type": "string", "description": "Time (produto/suporte/comercial/cs; vazio limpa)."},
        "action_note": {"type": "string", "description": "Nota interna (vazio limpa)."},
    },
    "required": ["feedback_id"],
}


# --- (6) enviar WhatsApp (atrás de flag + 3 gates) -------------------------------


async def _last_outbound_at(ctx: VoCToolContext, contact_id: uuid.UUID) -> Optional[datetime]:
    """Instante do último outbound para o contato (tabela messages). Base do cooldown.

    Espelha admin._recent_outbound_at — replicado aqui para não importar de app/api/.
    """
    return (
        await ctx.session.execute(
            select(func.max(Message.created_at)).where(
                Message.organization_id == ctx.org_id,
                Message.contact_id == contact_id,
                Message.direction == "outbound",
            )
        )
    ).scalar_one_or_none()


async def _enviar_whatsapp(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Envia uma mensagem de WhatsApp ao contato — DORMENTE por padrão.

    GATE 0 (flag): com `voc_whatsapp_tool_enabled` OFF (default), é NO-OP — NÃO envia
    nada e devolve {"sent": false, "reason": "tool_desligada"}. WhatsApp real só com OK
    explícito do dono.

    Mesmo com a flag ON, passa por 3 GATES (todos têm de valer p/ enviar):
      1. opt-in       — contact.opt_in tem de ser True (consentimento).
      2. cooldown     — sem outbound nas últimas notify_cooldown_hours (anti-spam).
      3. alcançável   — celular BR válido (tem_whatsapp), senão não há para onde mandar.

    Passando tudo: envia via messaging.send_text e grava o outbound em `messages`
    (alimenta o cooldown e dá histórico ao humano), igual ao /improvements/{id}/notify.
    Best-effort no envio: falha de rede vira {"sent": false, "reason": "erro_envio"}.
    """
    mensagem = args.get("mensagem") or args.get("text")
    if not mensagem or not str(mensagem).strip():
        return {"ok": False, "sent": False, "error": "mensagem vazia"}

    # GATE 0 — flag mestra. NO-OP explícito quando desligada.
    if not settings.voc_whatsapp_tool_enabled:
        return {
            "ok": True,
            "sent": False,
            "reason": "tool_desligada",
            "detail": "envio de WhatsApp está desligado (voc_whatsapp_tool_enabled=OFF)",
        }

    contact = await _get_contact(ctx, args.get("contact_id"))
    if contact is None:
        return {"ok": False, "sent": False, "error": "contato não encontrado nesta organização"}

    # GATE 1 — opt-in (consentimento do contato).
    if not contact.opt_in:
        return {"ok": True, "sent": False, "reason": "sem_opt_in"}

    # GATE 3 (estrutural) — alcançável: só celular BR válido tem WhatsApp.
    if not tem_whatsapp(contact.phone):
        return {"ok": True, "sent": False, "reason": "sem_whatsapp"}

    # GATE 2 — cooldown de outbound proativo.
    cooldown_hours = settings.notify_cooldown_hours
    if cooldown_hours:
        last = _aware(await _last_outbound_at(ctx, contact.id))
        if last is not None and (ctx.now() - last) < timedelta(hours=cooldown_hours):
            return {"ok": True, "sent": False, "reason": "cooldown"}

    # Sem canal injetado não há como enviar (gate implícito).
    if ctx.messaging is None:
        return {"ok": True, "sent": False, "reason": "sem_canal"}

    text = str(mensagem).strip()[:2000]
    try:
        await ctx.messaging.send_text(chat_id=contact.phone, text=text, session=ctx.waha_session)
    except Exception:  # noqa: BLE001 — envio best-effort, nunca derruba o agente.
        logger.warning("voc.enviar_whatsapp: falha ao enviar — seguindo", exc_info=True)
        return {"ok": False, "sent": False, "reason": "erro_envio"}

    # Grava o outbound no transcript (alimenta o cooldown e dá histórico ao humano).
    ctx.session.add(
        Message(
            organization_id=ctx.org_id,
            contact_id=contact.id,
            direction="outbound",
            body=text,
        )
    )
    await ctx.session.flush()
    return {"ok": True, "sent": True, "contact_id": str(contact.id)}


_ENVIAR_WHATSAPP_SCHEMA = {
    "type": "object",
    "properties": {
        "contact_id": {"type": "string", "description": "ID (UUID) do contato destinatário."},
        "mensagem": {"type": "string", "description": "Texto a enviar (caloroso, curto, sem markdown)."},
    },
    "required": ["contact_id", "mensagem"],
}


# --- (7) ler perfil do contato (visão consolidada) -------------------------------


async def _ler_perfil_contato(ctx: VoCToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Visão consolidada do contato (em espírito, a ficha 360 compacta para o agente).

    Junta: dados do contato (nome/telefone/opt-in/alcançável), snapshot da API de
    Clientes (profile_data['partner']) e agregados dos sinais (FeedbackItem) +
    respostas coletadas (SurveyResponse), com uma timeline curta dos itens recentes.
    """
    contact = await _get_contact(ctx, args.get("contact_id"))
    if contact is None:
        return {"ok": False, "error": "contato não encontrado nesta organização"}

    fitems = (
        await ctx.session.execute(
            select(FeedbackItem)
            .where(
                FeedbackItem.organization_id == ctx.org_id,
                FeedbackItem.contact_id == contact.id,
            )
            .order_by(FeedbackItem.created_at.desc())
        )
    ).scalars().all()

    sresps = (
        await ctx.session.execute(
            select(SurveyResponse)
            .where(
                SurveyResponse.organization_id == ctx.org_id,
                SurveyResponse.contact_id == contact.id,
            )
            .order_by(SurveyResponse.sent_at.desc())
        )
    ).scalars().all()

    recent: list[dict[str, Any]] = []
    for f in fitems[:5]:
        when = f.occurred_at or f.created_at
        recent.append(
            {
                "kind": "feedback_item",
                "id": str(f.id),
                "type": f.type,
                "source": f.source,
                "score": f.score,
                "bucket": f.nps_bucket,
                "text": (f.text or "")[:400] or None,
                "sentiment": f.sentiment,
                "themes": f.themes,
                "action_status": f.action_status,
                "abordado": f.abordado,
                "at": when.isoformat() if when else None,
            }
        )
    for r in sresps[:5]:
        when = r.closed_at or r.answered_at or r.sent_at
        recent.append(
            {
                "kind": "survey",
                "score": r.answer_score,
                "bucket": r.nps_bucket,
                "text": (r.answer_text or "")[:400] or None,
                "status": r.status,
                "sentiment": r.sentiment,
                "themes": r.themes,
                "at": when.isoformat() if when else None,
            }
        )
    recent.sort(key=lambda x: x["at"] or "", reverse=True)

    partner = (contact.profile_data or {}).get("partner")
    return {
        "ok": True,
        "contact": {
            "id": str(contact.id),
            "name": contact.name,
            "phone": contact.phone,
            "opt_in": contact.opt_in,
            "alcancavel": tem_whatsapp(contact.phone),
            "needs_human_handoff": contact.needs_human_handoff,
        },
        "partner": partner,
        "summary": {
            "total": len(fitems) + len(sresps),
            "feedback_items": len(fitems),
            "survey_responses": len(sresps),
        },
        "recent": recent[:8],
    }


_LER_PERFIL_SCHEMA = {
    "type": "object",
    "properties": {
        "contact_id": {"type": "string", "description": "ID (UUID) do contato a consultar."},
    },
    "required": ["contact_id"],
}


# --- montagem do registry --------------------------------------------------------


def build_default_registry(ctx: VoCToolContext) -> VoCToolRegistry:
    """Cria um VoCToolRegistry com as 7 tools, cada uma com `ctx` capturado em closure.

    O registry é genérico; aqui é onde as tools ganham acesso à sessão/org/canal. Um
    registry novo por turno (barato) — o contexto vive só enquanto o agente roda.
    """
    registry = VoCToolRegistry()

    registry.register(
        "registrar_abordagem",
        "Marca um feedback como ABORDADO (você/o time já falou com o cliente sobre ele). "
        "Use depois de entrar em contato com o cliente a respeito de um feedback.",
        _REGISTRAR_ABORDAGEM_SCHEMA,
        lambda args, _ctx=ctx: _registrar_abordagem(_ctx, args),
    )
    registry.register(
        "aplicar_selo",
        "Roteia um feedback para um time (team_tag: produto/suporte/comercial/cs) e/ou "
        "uma pessoa responsável (assignee). Use para encaminhar o feedback a quem deve tratá-lo.",
        _APLICAR_SELO_SCHEMA,
        lambda args, _ctx=ctx: _aplicar_selo(_ctx, args),
    )
    registry.register(
        "criar_tarefa",
        "Cria uma tarefa de Customer Success (CsTask) na fila do time. Use para registrar "
        "uma ação concreta a fazer (ex.: ligar para um cliente em risco). Pode amarrar a um "
        "contato e/ou a um feedback.",
        _CRIAR_TAREFA_SCHEMA,
        lambda args, _ctx=ctx: _criar_tarefa(_ctx, args),
    )
    registry.register(
        "vincular_melhoria",
        "Liga um feedback a uma melhoria do roadmap (Improvement), fechando o loop entre o "
        "que o cliente pediu e o que será entregue.",
        _VINCULAR_MELHORIA_SCHEMA,
        lambda args, _ctx=ctx: _vincular_melhoria(_ctx, args),
    )
    registry.register(
        "atualizar_feedback",
        "Atualiza o workflow de um feedback: estágio do tratamento (action_status), "
        "responsável (assignee), time (team_tag) e/ou nota interna (action_note).",
        _ATUALIZAR_FEEDBACK_SCHEMA,
        lambda args, _ctx=ctx: _atualizar_feedback(_ctx, args),
    )
    registry.register(
        "enviar_whatsapp",
        "Envia uma mensagem de WhatsApp ao contato. Pode estar DESLIGADO (não envia nada) ou "
        "ser bloqueado por opt-in, cooldown ou número não alcançável — a resposta diz se enviou "
        "(sent) e o motivo quando não. Use só quando fizer sentido falar diretamente com o cliente.",
        _ENVIAR_WHATSAPP_SCHEMA,
        lambda args, _ctx=ctx: _enviar_whatsapp(_ctx, args),
    )
    registry.register(
        "ler_perfil_contato",
        "Lê a visão consolidada de um contato: dados, perfil/plano (snapshot do parceiro) e os "
        "feedbacks/respostas recentes. Use para se contextualizar antes de agir.",
        _LER_PERFIL_SCHEMA,
        lambda args, _ctx=ctx: _ler_perfil_contato(_ctx, args),
    )
    return registry
