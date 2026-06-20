"""API do painel (Fase 1) — dashboard, surveys, contatos e disparo.

Mesma filosofia do webhook da Fase 0: org única resolvida pelo slug default
(multi-tenant pleno fica para quando houver auth). Todos os endpoints filtram
por `organization_id`.

Sem mocks: o disparo usa o WAHA real via `get_messaging` (injetável nos testes).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Integer, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import logging

from app.config import settings
from app.db import get_session
from app.domain.clustering.inline import maybe_schedule_embed
from app.domain.contacts.whatsapp import sem_whatsapp, tem_whatsapp
# Alias: dentro de list_clientes o query param chama-se `tem_whatsapp` (str) e
# sombreia a função homônima; usamos este alias para o validador lá dentro.
from app.domain.contacts.whatsapp import tem_whatsapp as tem_whatsapp_fn
from app.domain.digest.aggregator import aggregate_themes
from app.domain.interfaces.messaging_service import IMessagingService
from app.domain.survey.brain import SurveyBrain
from app.domain.survey.dispatcher import SurveyDispatcher
from app.domain.survey.parsers import nps_bucket
from app.models.cluster import FeedbackCluster
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem
from app.models.improvement import Improvement
from app.models.survey import (
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_INGESTED,
    Message,
    Survey,
    SurveyResponse,
    SurveyRun,
)
from app.services.llm import GroqLLM
from app.services.waha import WAHAService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def get_messaging() -> IMessagingService:
    """Canal de envio real (WAHA). Substituível via dependency_overrides nos testes."""
    return WAHAService(settings.waha_base_url, settings.waha_api_key, settings.waha_session)


def get_brain() -> SurveyBrain | None:
    """SurveyBrain (Groq) quando o LLM está configurado; None = sem auto-classificação.

    Mesma checagem dos outros pontos de classificação do projeto (events/ingest):
    `llm_enabled` (que já exige `GROQ_API_KEY`). Injetável via dependency_overrides
    nos testes — assim a auto-classificação é testada com um FakeLLM, sem tocar a Groq.
    """
    if not (settings.llm_enabled and settings.groq_api_key):
        return None
    return SurveyBrain(
        GroqLLM(
            settings.groq_api_key,
            settings.groq_model,
            fallback_model=settings.groq_fallback_model or None,
        )
    )


async def _get_org(session: AsyncSession) -> Organization:
    org = (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail=f"org '{settings.default_org_slug}' não encontrada (rode o seed)")
    return org


def _abordado_inicio(periodo: str) -> datetime | None:
    """Início (em UTC) do recorte "abordados por período" para filtrar `abordado_em`.

    - "hoje": meia-noite de HOJE no fuso America/Sao_Paulo, convertida para UTC. Se
      zoneinfo/tzdata estiver indisponível, faz fallback para meia-noite UTC.
    - "7d"/"30d": agora (UTC) menos 7 ou 30 dias.
    - qualquer outro valor: None (sem recorte por período).
    """
    if periodo == "hoje":
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("America/Sao_Paulo")
            agora_local = datetime.now(tz)
            inicio_local = agora_local.replace(hour=0, minute=0, second=0, microsecond=0)
            return inicio_local.astimezone(timezone.utc)
        except Exception:
            # Sem zoneinfo/tzdata: fallback para meia-noite UTC de hoje.
            agora = datetime.now(timezone.utc)
            return agora.replace(hour=0, minute=0, second=0, microsecond=0)
    if periodo == "7d":
        return datetime.now(timezone.utc) - timedelta(days=7)
    if periodo == "30d":
        return datetime.now(timezone.utc) - timedelta(days=30)
    return None


# --- Dashboard -------------------------------------------------------------


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Dashboard segmentado por tipo de survey.

    - bloco `nps`: KPIs calculados APENAS sobre responses de surveys type='nps'
      (`kpis` é mantido como alias retrocompatível do mesmo bloco).
    - bloco `exit`: contadores + últimos motivos das exit surveys (churn) —
      sem nota, `answer_score` fica NULL nesse tipo.
    - `recent`: lista geral, cada item ganha `survey_type` e `survey_name`.
    """
    org = await _get_org(session)

    nps_sent = (
        await session.execute(
            select(func.count())
            .select_from(SurveyResponse)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(SurveyResponse.organization_id == org.id, Survey.type == "nps")
        )
    ).scalar_one()

    by_bucket = dict(
        (
            await session.execute(
                select(SurveyResponse.nps_bucket, func.count())
                .select_from(SurveyResponse)
                .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
                .join(Survey, Survey.id == SurveyRun.survey_id)
                .where(
                    SurveyResponse.organization_id == org.id,
                    SurveyResponse.answer_score.is_not(None),
                    Survey.type == "nps",
                )
                .group_by(SurveyResponse.nps_bucket)
            )
        ).all()
    )
    promoters = by_bucket.get("promoter", 0)
    passives = by_bucket.get("passive", 0)
    detractors = by_bucket.get("detractor", 0)
    answered = promoters + passives + detractors

    nps_closed = (
        await session.execute(
            select(func.count())
            .select_from(SurveyResponse)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(
                SurveyResponse.organization_id == org.id,
                SurveyResponse.status == "closed",
                Survey.type == "nps",
            )
        )
    ).scalar_one()

    nps = round(((promoters - detractors) / answered) * 100) if answered else None

    # --- exit surveys (churn): sem nota; "respondida" = closed com motivo ----
    exit_sent = (
        await session.execute(
            select(func.count())
            .select_from(SurveyResponse)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(SurveyResponse.organization_id == org.id, Survey.type == "exit")
        )
    ).scalar_one()

    exit_answered = (
        await session.execute(
            select(func.count())
            .select_from(SurveyResponse)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(
                SurveyResponse.organization_id == org.id,
                Survey.type == "exit",
                SurveyResponse.status == "closed",
                SurveyResponse.answer_text.is_not(None),
            )
        )
    ).scalar_one()

    exit_recent_rows = (
        await session.execute(
            select(SurveyResponse, Contact)
            .join(Contact, Contact.id == SurveyResponse.contact_id)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(
                SurveyResponse.organization_id == org.id,
                Survey.type == "exit",
                SurveyResponse.status == "closed",
                SurveyResponse.answer_text.is_not(None),
            )
            .order_by(SurveyResponse.closed_at.desc())
            .limit(10)
        )
    ).all()

    recent_rows = (
        await session.execute(
            select(SurveyResponse, Contact, Survey)
            .join(Contact, Contact.id == SurveyResponse.contact_id)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(SurveyResponse.organization_id == org.id)
            .order_by(SurveyResponse.sent_at.desc())
            .limit(20)
        )
    ).all()

    nps_kpis = {
        "sent": nps_sent,
        "answered": answered,
        "closed": nps_closed,
        "response_rate": round(answered / nps_sent * 100) if nps_sent else None,
        "nps": nps,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
    }

    return {
        "org": {"slug": org.slug, "name": org.name},
        # `kpis` = alias retrocompatível do bloco `nps` (mesmo conteúdo).
        "kpis": nps_kpis,
        "nps": nps_kpis,
        "exit": {
            "sent": exit_sent,
            "answered": exit_answered,
            "recent": [
                {
                    "contact_name": c.name,
                    "text": r.answer_text,
                    "sentiment": r.sentiment,
                    "themes": r.themes,
                    "closed_at": r.closed_at.isoformat() if r.closed_at else None,
                }
                for r, c in exit_recent_rows
            ],
        },
        "recent": [
            {
                "id": str(r.id),
                "contact_name": c.name,
                "contact_phone": c.phone,
                "status": r.status,
                "score": r.answer_score,
                "bucket": r.nps_bucket,
                "text": r.answer_text,
                "survey_type": s.type,
                "survey_name": s.name,
                "sentiment": r.sentiment,
                "themes": r.themes,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            }
            for r, c, s in recent_rows
        ],
    }


# --- Surveys ----------------------------------------------------------------


class SurveyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # 'nps': nota 0-10 + motivo. 'exit': só a pergunta aberta (ex.: exit survey
    # de churn) — nps_question é ignorada nesse caso.
    type: Literal["nps", "exit"] = "nps"
    nps_question: str | None = Field(default=None, min_length=1, max_length=500)
    reason_prompt: str = Field(min_length=1, max_length=500)
    thanks_message: str | None = Field(default=None, min_length=1, max_length=500)
    # Evento que dispara a survey automaticamente via /api/events/* (ex.:
    # 'subscription_cancelled'). None = apenas disparo manual.
    trigger_event: str | None = Field(default=None, max_length=120)


def _survey_out(s: Survey, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    nps_q = next((q.get("text") for q in (s.questions or []) if q.get("kind") == "nps"), None)
    reason_q = next((q.get("text") for q in (s.questions or []) if q.get("kind") == "open"), None)
    st = stats or {}
    return {
        "id": str(s.id),
        "name": s.name,
        "type": s.type,
        "status": s.status,
        "nps_question": nps_q,
        "reason_prompt": reason_q,
        "trigger_event": s.trigger_event,
        # Acompanhamento (0 quando a survey nunca disparou). answered = deu nota
        # (status awaiting_reason/closed/ingested OU answer_score preenchido);
        # pending = enviados - respondidos.
        "sent_count": int(st.get("sent_count", 0)),
        "answered_count": int(st.get("answered_count", 0)),
        "pending_count": int(st.get("pending_count", 0)),
        "last_run_at": st.get("last_run_at"),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/surveys")
async def list_surveys(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    org = await _get_org(session)
    rows = (
        (
            await session.execute(
                select(Survey).where(Survey.organization_id == org.id).order_by(Survey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    # Acompanhamento por pesquisa numa única passada agregada sobre as respostas
    # (sent/answered) juntando o run pai para chegar na survey. "Respondido" = deu
    # nota (status já avançou de 'sent'/'expired' OU tem answer_score). pending é
    # derivado (sent - answered) para não depender de um status específico.
    answered_pred = or_(
        SurveyResponse.answer_score.is_not(None),
        SurveyResponse.status.in_(
            [STATUS_AWAITING_REASON, STATUS_CLOSED, STATUS_INGESTED]
        ),
    )
    stat_rows = (
        await session.execute(
            select(
                SurveyRun.survey_id,
                func.count(SurveyResponse.id).label("sent"),
                func.sum(case((answered_pred, 1), else_=0)).label("answered"),
            )
            .select_from(SurveyResponse)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .where(SurveyResponse.organization_id == org.id)
            .group_by(SurveyRun.survey_id)
        )
    ).all()
    # last_run_at por survey (independe de haver respostas).
    run_rows = (
        await session.execute(
            select(SurveyRun.survey_id, func.max(SurveyRun.created_at))
            .where(SurveyRun.organization_id == org.id)
            .group_by(SurveyRun.survey_id)
        )
    ).all()
    last_run: dict[Any, Any] = {sid: ts for sid, ts in run_rows}
    stats: dict[Any, dict[str, Any]] = {}
    for sid, sent, answered in stat_rows:
        sent_i = int(sent or 0)
        ans_i = int(answered or 0)
        ts = last_run.get(sid)
        stats[sid] = {
            "sent_count": sent_i,
            "answered_count": ans_i,
            "pending_count": max(sent_i - ans_i, 0),
            "last_run_at": ts.isoformat() if ts is not None else None,
        }
    # Surveys com run mas sem nenhuma resposta ainda (last_run_at só).
    for sid, ts in last_run.items():
        if sid not in stats:
            stats[sid] = {
                "sent_count": 0,
                "answered_count": 0,
                "pending_count": 0,
                "last_run_at": ts.isoformat() if ts is not None else None,
            }

    return [_survey_out(s, stats.get(s.id)) for s in rows]


@router.post("/surveys", status_code=201)
async def create_survey(body: SurveyIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _get_org(session)
    exists = (
        await session.execute(
            select(Survey).where(Survey.organization_id == org.id, Survey.name == body.name)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"já existe uma pesquisa chamada '{body.name}'")

    if body.type == "nps" and not body.nps_question:
        raise HTTPException(status_code=422, detail="pesquisa NPS exige nps_question")

    if body.trigger_event:
        trigger_taken = (
            await session.execute(
                select(Survey).where(
                    Survey.organization_id == org.id,
                    Survey.trigger_event == body.trigger_event,
                    Survey.status == "active",
                )
            )
        ).scalar_one_or_none()
        if trigger_taken is not None:
            raise HTTPException(
                status_code=409,
                detail=f"o evento '{body.trigger_event}' já dispara a pesquisa '{trigger_taken.name}'",
            )

    questions: list[dict[str, str]] = []
    if body.type == "nps":
        questions.append({"key": "nps", "kind": "nps", "text": body.nps_question})
    questions.append({"key": "reason", "kind": "open", "text": body.reason_prompt})
    if body.thanks_message:
        questions.append({"key": "thanks", "kind": "thanks", "text": body.thanks_message})

    survey = Survey(
        organization_id=org.id,
        name=body.name,
        type=body.type,
        status="active",
        questions=questions,
        trigger_event=body.trigger_event,
    )
    session.add(survey)
    await session.commit()
    return _survey_out(survey)


# --- Contatos ----------------------------------------------------------------


class ContactIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    name: str | None = Field(default=None, max_length=120)


@router.get("/contacts")
async def list_contacts(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    org = await _get_org(session)
    rows = (
        (
            await session.execute(
                select(Contact).where(Contact.organization_id == org.id).order_by(Contact.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(c.id),
            "phone": c.phone,
            "name": c.name,
            "opt_in": c.opt_in,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.post("/contacts", status_code=201)
async def create_contact(body: ContactIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    org = await _get_org(session)
    phone = re.sub(r"\D", "", body.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="telefone inválido — use DDI+DDD+número, só dígitos")

    exists = (
        await session.execute(
            select(Contact).where(Contact.organization_id == org.id, Contact.phone == phone)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"contato {phone} já existe")

    contact = Contact(
        organization_id=org.id,
        phone=phone,
        name=(body.name or "").strip() or None,
        opt_in=True,
        profile_data={},
    )
    session.add(contact)
    await session.commit()
    return {"id": str(contact.id), "phone": contact.phone, "name": contact.name, "opt_in": contact.opt_in}


# --- Visão 360 (Mega Central de Dados) ---------------------------------------


@router.get("/contacts/{contact_id}/360")
async def contact_360(contact_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Visão 360 do cliente: junta o snapshot da API de Clientes (profile_data),
    os sinais ingeridos de fontes externas (FeedbackItem) e as respostas coletadas
    pelo Escuta no WhatsApp (SurveyResponse) numa única timeline por contato."""
    org = await _get_org(session)
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    contact = (
        await session.execute(
            select(Contact).where(Contact.id == cid, Contact.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="contato não encontrado")

    partner = (contact.profile_data or {}).get("partner")

    fitems = (
        (
            await session.execute(
                select(FeedbackItem)
                .where(FeedbackItem.organization_id == org.id, FeedbackItem.contact_id == cid)
                .order_by(FeedbackItem.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    sresp = (
        await session.execute(
            select(SurveyResponse, Survey)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .where(SurveyResponse.organization_id == org.id, SurveyResponse.contact_id == cid)
            .order_by(SurveyResponse.sent_at.desc())
        )
    ).all()

    # Selos de campanha do contato (win-back, persistidos em profile_data["selos"]).
    # Inline (e não importando do campanha.py) porque campanha.py importa deste módulo —
    # importar de volta criaria ciclo.
    raw_selos = (contact.profile_data or {}).get("selos")
    selos: list[str] = [str(x) for x in raw_selos if x] if isinstance(raw_selos, list) else []
    # "Sem WhatsApp real": usa o validador canônico (celular BR válido = alcançável).
    # Fixo/grupo/inválido/placeholder/vazio contam como sem WhatsApp.
    sem_wa = sem_whatsapp(contact.phone)

    timeline: list[dict[str, Any]] = []
    for f in fitems:
        when = f.occurred_at or f.created_at
        timeline.append(
            {
                "kind": "feedback_item",
                # `id`/`action_status`/`abordado` permitem a ficha 360 editar o item
                # in-place (PATCH /api/feedbacks/{id}). Itens vindos de survey não têm.
                "id": str(f.id),
                "source": f.source,
                "type": f.type,
                "score": f.score,
                "bucket": f.nps_bucket,
                "text": f.text,
                "sentiment": f.sentiment,
                "themes": f.themes,
                "action_status": f.action_status,
                # Nota interna do operador — editável na 360 (PATCH action_note).
                "action_note": f.action_note,
                "abordado": f.abordado,
                "at": when.isoformat() if when else None,
            }
        )
    for r, s in sresp:
        when = r.closed_at or r.answered_at or r.sent_at
        timeline.append(
            {
                "kind": "survey",
                "source": "whatsapp",
                "type": s.type,
                "survey_name": s.name,
                "score": r.answer_score,
                "bucket": r.nps_bucket,
                "text": r.answer_text,
                "status": r.status,
                "sentiment": r.sentiment,
                "themes": r.themes,
                "at": when.isoformat() if when else None,
            }
        )
    timeline.sort(key=lambda x: x["at"] or "", reverse=True)

    return {
        "contact": {
            "id": str(contact.id),
            "name": contact.name,
            "phone": contact.phone,
            "opt_in": contact.opt_in,
            # Selos de campanha aplicados ao contato (chips editáveis na ficha 360).
            "selos": selos,
            # Sem WhatsApp real? (validador: só celular BR válido é alcançável) — chip na ficha.
            "sem_whatsapp": sem_wa,
        },
        "partner": partner,
        "summary": {
            "total": len(fitems) + len(sresp),
            "feedback_items": len(fitems),
            "survey_responses": len(sresp),
        },
        "timeline": timeline,
    }


# --- Central de Monitoramento (clientes + feed de feedbacks) ------------------

# Estados válidos da AÇÃO sobre um feedback (workflow do operador). A ordem é a
# do funil — usada também para o cabeçalho de contagem do feed.
ACTION_STATUSES: tuple[str, ...] = ("novo", "em_analise", "planejado", "resolvido", "descartado")
# Esteira (Fase D): estados TERMINAIS de action_status — a esteira não os reabre nem
# os re-resolve (idempotência). 'resolvido' (fechado com tratativa) e 'descartado'
# (fechado sem ação) são fins de linha do funil.
_FEEDBACK_TERMINAL_STATUSES: frozenset[str] = frozenset({"resolvido", "descartado"})

# Tipos de feedback aceitos no registro manual (Felipe registra o que o cliente
# deixou por qualquer canal). Mesmo espírito do ACTION_STATUSES: validado na API,
# sem CHECK no banco (vocabulário pode crescer). 'nota'/'abordagem' são os tipos da
# linha do tempo editável da ficha 360 (registro à mão de um evento do cliente).
FEEDBACK_TYPES: tuple[str, ...] = (
    "nps", "churn", "elogio", "sugestao", "bug", "nota", "abordagem", "outro"
)
# Sentimentos aceitos (espelha a semântica da IA). None = sem classificação.
SENTIMENTS: tuple[str, ...] = ("positivo", "neutro", "negativo")
# Tipos que derivam nps_bucket a partir do score (0-10).
_BUCKET_TYPES: tuple[str, ...] = ("nps",)

# Origens (FeedbackItem.source) que o sistema já produz hoje — viram os DEFAULTS de
# origem configuráveis (o dono pode ADICIONAR as dele). NÃO restringem a escrita de
# `source` (FeedbackCreateIn.source aceita qualquer string ≤120): servem ao /api/config
# como vocabulário-base para a UI montar filtros/labels. São os literais REAIS gravados
# por: registro manual ('manual'); coleta WhatsApp (from_survey/resolver/message_handler);
# eventos do app (events.py: 'bizzu_app'/'bizzu_support'/'bizzu_platform'/'in_app') e o
# snapshot da API de Clientes (partner_map: 'bizzu_app'/'bizzu_billing'); respostas de
# formulário ('forms', campanha.py).
DEFAULT_ORIGINS: tuple[str, ...] = (
    "manual", "whatsapp", "bizzu_app", "bizzu_billing", "bizzu_support",
    "bizzu_platform", "in_app", "forms",
)

# --- Vocabulários CONFIGURÁVEIS por org (status/tipos/origens) -----------------
# Os 3 vocabulários acima (ACTION_STATUSES/FEEDBACK_TYPES/DEFAULT_ORIGINS) são os
# DEFAULTS imutáveis. Uma org pode ADICIONAR itens customizados em Organization.settings
# (sem migration — mesmo padrão copia-edita-reatribui dos boards). A lista EFETIVA usada
# nas validações e no board de triagem é sempre `defaults ∪ custom`; os defaults NUNCA
# somem (preservam os dados existentes). Item de status = {key,label,cor}; tipos/origens
# = {key,label}. Sem custom => comportamento IDÊNTICO ao anterior (zero regressão).

_COR_STATUS_DEFAULT = "#6366f1"  # token --indigo do painel (mesmo de boards._COR_DEFAULT).

# Chaves dos settings onde vivem os customizados (só os ADICIONAIS, nunca os defaults).
_SETTINGS_KEY_STATUSES = "action_statuses"
_SETTINGS_KEY_TYPES = "feedback_types"
_SETTINGS_KEY_ORIGINS = "feedback_origins"


def _label_humano(key: str) -> str:
    """Label default amigável a partir da key (snake_case -> 'Snake case')."""
    return key.replace("_", " ").strip().capitalize() or key


def _status_default_items() -> list[dict[str, str]]:
    """Os ACTION_STATUSES como itens {key,label,cor} — base imutável dos status."""
    return [
        {"key": s, "label": _label_humano(s), "cor": _COR_STATUS_DEFAULT}
        for s in ACTION_STATUSES
    ]


def _type_default_items() -> list[dict[str, str]]:
    """Os FEEDBACK_TYPES como itens {key,label} — base imutável dos tipos."""
    return [{"key": t, "label": _label_humano(t)} for t in FEEDBACK_TYPES]


def _origin_default_items() -> list[dict[str, str]]:
    """As DEFAULT_ORIGINS como itens {key,label} — base imutável das origens."""
    return [{"key": o, "label": _label_humano(o)} for o in DEFAULT_ORIGINS]


def _normalize_custom_status(raw: Any) -> dict[str, str] | None:
    """Normaliza um status custom {key,label,cor?} dos settings; None se inválido."""
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or "").strip()
    if not key:
        return None
    label = str(raw.get("label") or "").strip() or _label_humano(key)
    cor = str(raw.get("cor") or "").strip() or _COR_STATUS_DEFAULT
    return {"key": key, "label": label, "cor": cor}


def _normalize_custom_kv(raw: Any) -> dict[str, str] | None:
    """Normaliza um item custom {key,label?} (tipos/origens) dos settings; None se inválido."""
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or "").strip()
    if not key:
        return None
    label = str(raw.get("label") or "").strip() or _label_humano(key)
    return {"key": key, "label": label}


def _custom_items(org: Organization, settings_key: str, *, is_status: bool) -> list[dict[str, str]]:
    """Itens customizados da org sob `settings_key` (normalizados, dedup por key). [] se nenhum."""
    raw = (org.settings or {}).get(settings_key)
    out: list[dict[str, str]] = []
    vistos: set[str] = set()
    if isinstance(raw, list):
        for it in raw:
            norm = _normalize_custom_status(it) if is_status else _normalize_custom_kv(it)
            if norm is None or norm["key"] in vistos:
                continue
            vistos.add(norm["key"])
            out.append(norm)
    return out


def _merge_defaults_custom(
    defaults: list[dict[str, str]], custom: list[dict[str, str]]
) -> list[dict[str, str]]:
    """defaults ∪ custom (defaults primeiro). Um custom cuja key colide com um default é
    descartado (o default vence — defaults nunca somem nem são sobrescritos)."""
    default_keys = {d["key"] for d in defaults}
    out = list(defaults)
    for c in custom:
        if c["key"] not in default_keys:
            out.append(c)
    return out


def effective_statuses(org: Organization) -> list[dict[str, str]]:
    """Lista EFETIVA de status da org = defaults {key,label,cor} ∪ custom da org."""
    return _merge_defaults_custom(
        _status_default_items(), _custom_items(org, _SETTINGS_KEY_STATUSES, is_status=True)
    )


def effective_types(org: Organization) -> list[dict[str, str]]:
    """Lista EFETIVA de tipos de feedback da org = defaults {key,label} ∪ custom da org."""
    return _merge_defaults_custom(
        _type_default_items(), _custom_items(org, _SETTINGS_KEY_TYPES, is_status=False)
    )


def effective_origins(org: Organization) -> list[dict[str, str]]:
    """Lista EFETIVA de origens da org = defaults {key,label} ∪ custom da org."""
    return _merge_defaults_custom(
        _origin_default_items(), _custom_items(org, _SETTINGS_KEY_ORIGINS, is_status=False)
    )


def effective_status_keys(org: Organization) -> list[str]:
    """Só as keys da lista efetiva de status (ordem: defaults, depois custom)."""
    return [it["key"] for it in effective_statuses(org)]


def effective_type_keys(org: Organization) -> set[str]:
    """Conjunto de keys da lista efetiva de tipos (para validação O(1))."""
    return {it["key"] for it in effective_types(org)}

# Score de urgência: faixa fixa 0-100. A fórmula soma sinais independentes e satura
# (clamp) em 100, para o feed priorizar sozinho o que mais pede ação. Pesos abaixo.
URGENCIA_MIN = 0
URGENCIA_MAX = 100
# Recência: meia-vida em dias (peso de recência decai pela metade a cada N dias).
_URGENCIA_RECENCIA_MEIA_VIDA_DIAS = 14.0
_URGENCIA_RECENCIA_PESO = 20  # contribuição máxima da recência (feedback recém-chegado)


def _theme_match_clause(theme: str, dialect: str):
    """Predicado SQL portável: `FeedbackItem.themes` (array JSON) CONTÉM `theme` (exato).

    O array é JSONB no Postgres (Supabase) e JSON genérico no SQLite (testes). Cada
    dialeto expressa "array contém este elemento" de um jeito — o caller passa o nome
    do dialeto (`session.bind.dialect.name`) e devolvemos o clause certo:

    - Postgres: `themes @> '["<theme>"]'::jsonb` (operador de contenção do JSONB; usa
      índice GIN quando houver). Match EXATO do elemento (não substring).
    - SQLite:   `EXISTS (SELECT 1 FROM json_each(themes) WHERE value = :theme)`.

    O valor é SEMPRE vinculado por bind param (nunca f-string em SQL — regra do
    projeto). Devolve um ColumnElement booleano para encaixar em `.where(...)`.
    """
    from sqlalchemy import cast, text
    from sqlalchemy.dialects.postgresql import JSONB

    if dialect == "postgresql":
        # Contenção de array JSONB: `themes @> '["<theme>"]'`. Passamos uma LISTA
        # Python para `cast(..., JSONB)` — o tipo serializa para um array JSON de
        # verdade. (cast de uma string json.dumps cairia num escalar JSON string,
        # que NÃO casa com `@>` — bug pego no smoke contra o PG real.)
        return FeedbackItem.themes.op("@>")(cast([theme], JSONB))
    # SQLite (e demais com json1): json_each expande o array; igualamos o elemento.
    return text(
        "EXISTS (SELECT 1 FROM json_each(feedback_items.themes) "
        "WHERE json_each.value = :theme)"
    ).bindparams(theme=theme)


def _selo_match_clause(selo: str, dialect: str):
    """Predicado SQL portável: o CONTATO juntado tem `selo` em profile_data["selos"].

    Os selos de campanha vivem em `Contact.profile_data["selos"]` (array JSON) — ver
    campanha.py. Mesma estratégia do `_theme_match_clause`, mas sobre o JSON do contato:

    - Postgres: `contacts.profile_data['selos'] @> '["<selo>"]'::jsonb` (contenção JSONB,
      match exato do elemento). O `->` na coluna JSONB devolve o sub-array como jsonb.
    - SQLite:   `EXISTS (SELECT 1 FROM json_each(contacts.profile_data, '$.selos')
      WHERE value = :selo)`.

    Valor SEMPRE por bind param (nunca f-string em SQL). Devolve um ColumnElement
    booleano para encaixar em `.where(...)` num SELECT que já junta `Contact`.
    """
    from sqlalchemy import cast, text
    from sqlalchemy.dialects.postgresql import JSONB

    if dialect == "postgresql":
        return Contact.profile_data["selos"].op("@>")(cast([selo], JSONB))
    # SQLite com json1: json_each percorre o sub-array '$.selos'; igualamos o elemento.
    return text(
        "EXISTS (SELECT 1 FROM json_each(contacts.profile_data, '$.selos') "
        "WHERE json_each.value = :selo)"
    ).bindparams(selo=selo)


def _coerce_dt(value: Any) -> datetime | None:
    """datetime aware a partir de datetime/str ISO; None/inválido -> None. Tudo em UTC."""
    dt = value if isinstance(value, datetime) else _parse_iso_dt(value)
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_urgencia(
    *,
    sentiment: str | None,
    type_: str | None,
    score: int | None,
    nps_bucket_value: str | None,
    abordado: bool,
    occurred_at: datetime | None,
    created_at: datetime | None,
    partner: dict | None,
    now: datetime,
) -> int:
    """Score de urgência 0-100 — quanto MAIOR, mais o feedback pede ação humana agora.

    Combina sinais que JÁ temos no item + no snapshot do contato (partner). É uma soma
    ponderada saturada em [0,100] (não probabilística): existe para ORDENAR o inbox, não
    para ser uma métrica calibrada. Sinais e pesos:

      +40  sentimento negativo
      +25  type == 'churn' (cancelamento é sempre prioridade)
      +20  detrator: nps_bucket == 'detractor' OU score <= 6  (não soma duas vezes)
      +20  contato em risco: partner.profile contém 'risco' (ex.: 'ativo_em_risco')
      +10  plano anual (planType/planName == 'anual'): perder um anual dói mais
      +15  ainda NÃO abordado (abordado=False) — o que falta tratar sobe
      +0..20  recência: decaimento exponencial (meia-vida 14d) sobre o mais novo

    Tudo best-effort: campo ausente/None simplesmente não soma. Resultado é clampado
    em [0,100]. Itens sem nenhum sinal e antigos tendem a ~0; um detrator de churn
    negativo, em risco, recém-chegado e não abordado satura em 100.
    """
    score_v = 0

    if sentiment == "negativo":
        score_v += 40

    if type_ == "churn":
        score_v += 25

    # Detrator: por bucket OU por nota baixa — conta uma vez só.
    if nps_bucket_value == "detractor" or (score is not None and score <= 6):
        score_v += 20

    partner = partner or {}
    perfil = partner.get("profile")
    if isinstance(perfil, str) and "risco" in perfil.lower():
        score_v += 20

    sub = partner.get("subscription") or {}
    plano = str(sub.get("planType") or sub.get("planName") or "").lower()
    if "anual" in plano:
        score_v += 10

    if not abordado:
        score_v += 15

    # Recência: meia-vida exponencial sobre occurred_at (fallback created_at).
    when = _coerce_dt(occurred_at) or _coerce_dt(created_at)
    if when is not None:
        idade_dias = max(0.0, (now - when).total_seconds() / 86400.0)
        fator = 0.5 ** (idade_dias / _URGENCIA_RECENCIA_MEIA_VIDA_DIAS)
        score_v += round(_URGENCIA_RECENCIA_PESO * fator)

    return max(URGENCIA_MIN, min(URGENCIA_MAX, int(score_v)))


def _parse_iso_dt(value: Any) -> datetime | None:
    """ISO-8601 (str do snapshot, com 'Z') -> datetime aware; tolera None/inválido."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _nps_bucket_label(nps_score: int | None) -> str | None:
    """Faixa NPS em PT-BR a partir do score 0-10 (filtro de clientes do painel):
    'promotor' (>=9) | 'neutro' (7-8) | 'detrator' (<=6). None quando não há score
    (cliente sem nota nunca casa nenhum bucket)."""
    if nps_score is None:
        return None
    if nps_score >= 9:
        return "promotor"
    if nps_score >= 7:
        return "neutro"
    return "detrator"


def _partner_fields(contact: Contact, now: datetime) -> dict[str, Any]:
    """Deriva perfil/plano/plan_type/nps_score/dias_para_renovar do snapshot partner.

    Tudo best-effort: campo ausente/malformado vira None. `plano` prefere o nome
    legível (planName) e cai no planType; `dias_para_renovar` é (currentPeriodEnd -
    hoje).days quando >= 0, espelhando o cálculo do dispatch_by_profile.
    """
    partner = (contact.profile_data or {}).get("partner") or {}
    sub = partner.get("subscription") or {}
    nps = partner.get("nps") or {}

    plan_type = sub.get("planType")
    plano = sub.get("planName") or plan_type

    score = nps.get("score")
    nps_score = int(score) if isinstance(score, (int, float)) else None

    dias = None
    renova = _parse_iso_dt(sub.get("currentPeriodEnd"))
    if renova is not None:
        restante = (renova.date() - now.date()).days
        if restante >= 0:
            dias = restante

    return {
        "perfil": partner.get("profile"),
        "plano": plano,
        "plan_type": plan_type,
        "nps_score": nps_score,
        "dias_para_renovar": dias,
    }


@router.get("/clientes")
async def list_clientes(
    search: str | None = None,
    perfil: str | None = None,
    plan_type: str | None = None,
    estado: str | None = None,
    nps_bucket: str | None = None,
    health_band: str | None = None,
    tem_whatsapp: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Lista rica de clientes contatáveis da org (Contact + snapshot partner +
    agregação de feedback_items). Ordem: último feedback desc (nulls por último).

    Filtros opcionais (ausentes = comportamento idêntico ao anterior):
    - search: trecho no nome OU no whatsapp.
    - perfil: partner.profile (SQL JSON path), ex.: 'ativo_promotor', 'churn_pos_uso'.
    - plan_type: partner.subscription.planType (SQL JSON path), 'mensal' | 'anual'.
    - estado: partner.subscription.state (SQL JSON path), ex.: 'cancelled',
      'paid_without_access', 'active_paying', 'complimentary', 'past_due'.
    - nps_bucket: 'promotor' (score>=9) | 'neutro' (7-8) | 'detrator' (<=6) — POST-FILTER
      sobre nps_score (None nunca casa).
    - health_band: 'healthy' | 'watch' | 'at_risk' — POST-FILTER sobre o health.band.
    - tem_whatsapp: 'sim' | 'nao' — POST-FILTER usando o validador (celular BR válido)."""
    from app.domain.cs.health import compute_health

    org = await _get_org(session)

    # Agregação por contato em feedback_items: total + último occurred/created + tipo.
    last_at = func.max(func.coalesce(FeedbackItem.occurred_at, FeedbackItem.created_at))
    agg_rows = (
        await session.execute(
            select(
                FeedbackItem.contact_id,
                func.count().label("total"),
                last_at.label("last_at"),
            )
            .where(FeedbackItem.organization_id == org.id, FeedbackItem.contact_id.is_not(None))
            .group_by(FeedbackItem.contact_id)
        )
    ).all()
    agg: dict[Any, dict[str, Any]] = {
        cid: {"total": total, "last_at": last_at_v} for cid, total, last_at_v in agg_rows
    }
    # Tipo do último feedback (mais recente por occurred/created) por contato.
    last_type: dict[Any, str] = {}
    type_rows = (
        await session.execute(
            select(FeedbackItem.contact_id, FeedbackItem.type, FeedbackItem.occurred_at, FeedbackItem.created_at)
            .where(FeedbackItem.organization_id == org.id, FeedbackItem.contact_id.is_not(None))
        )
    ).all()
    best_when: dict[Any, Any] = {}
    for cid, ftype, occ, created in type_rows:
        when = occ or created
        if cid not in best_when or (when is not None and (best_when[cid] is None or when >= best_when[cid])):
            best_when[cid] = when
            last_type[cid] = ftype

    # Sentimento acumulado por contato (negativos/positivos) — sinal do Health Score.
    sent: dict[Any, dict[str, int]] = {}
    sent_rows = (
        await session.execute(
            select(FeedbackItem.contact_id, FeedbackItem.sentiment, func.count())
            .where(FeedbackItem.organization_id == org.id, FeedbackItem.contact_id.is_not(None))
            .group_by(FeedbackItem.contact_id, FeedbackItem.sentiment)
        )
    ).all()
    for cid, s, n in sent_rows:
        d = sent.setdefault(cid, {"neg": 0, "pos": 0})
        if s == "negativo":
            d["neg"] += n
        elif s == "positivo":
            d["pos"] += n

    # Contatos (com filtros SQL portáveis: search no nome/phone; perfil/plan_type no JSON).
    stmt = select(Contact).where(Contact.organization_id == org.id)
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(Contact.name, "")).like(term),
                Contact.phone.like(f"%{re.sub(r'%', '', search.strip())}%"),
            )
        )
    if perfil:
        stmt = stmt.where(Contact.profile_data["partner"]["profile"].as_string() == perfil)
    if plan_type:
        stmt = stmt.where(
            Contact.profile_data["partner"]["subscription"]["planType"].as_string() == plan_type
        )
    if estado:
        stmt = stmt.where(
            Contact.profile_data["partner"]["subscription"]["state"].as_string() == estado
        )

    contacts = (await session.execute(stmt)).scalars().all()

    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for c in contacts:
        a = agg.get(c.id, {})
        last = a.get("last_at")
        pf = _partner_fields(c, now)
        sc = sent.get(c.id, {})
        sub_state = (
            ((c.profile_data or {}).get("partner") or {}).get("subscription") or {}
        ).get("state")
        health = compute_health(
            nps_score=pf["nps_score"],
            perfil=pf["perfil"],
            last_feedback_at=last,
            neg_count=sc.get("neg", 0),
            pos_count=sc.get("pos", 0),
            subscription_state=sub_state,
            now=now,
        )
        # POST-FILTERS (em Python, pois dependem de campos calculados/validados):
        # nps_bucket (faixa do nps_score), health_band (banda já calculada) e
        # tem_whatsapp (validador). None/sem-match descarta o cliente da lista.
        if nps_bucket and _nps_bucket_label(pf["nps_score"]) != nps_bucket:
            continue
        if health_band and health.band != health_band:
            continue
        if tem_whatsapp in ("sim", "nao"):
            quer_wa = tem_whatsapp == "sim"
            if tem_whatsapp_fn(c.phone) != quer_wa:
                continue
        out.append(
            {
                "id": str(c.id),
                "nome": c.name,
                "whatsapp": c.phone,
                "opt_in": c.opt_in,
                # Tem WhatsApp REAL? Validador canônico: só celular BR válido é alcançável.
                # Fixo/grupo/inválido/placeholder('nowa-')/vazio -> False. (alias porque o
                # query param `tem_whatsapp` sombreia a função homônima neste escopo.)
                "tem_whatsapp": tem_whatsapp_fn(c.phone),
                # Estado da assinatura no snapshot partner (ex.: 'cancelled',
                # 'active_paying'); None quando não há snapshot.
                "estado": sub_state,
                # Selos de campanha aplicados ao contato (camada win-back; persistidos
                # em profile_data["selos"]). Lista de nomes, [] quando não há.
                "selos": ((c.profile_data or {}).get("selos", []) or []),
                **pf,
                "ultimo_feedback_em": last.isoformat() if last else None,
                "ultimo_feedback_tipo": last_type.get(c.id),
                "total_feedbacks": a.get("total", 0),
                "health": health.score,
                "health_band": health.band,
                "health_factors": health.factors,
                "criado_em": c.created_at.isoformat() if c.created_at else None,
            }
        )

    # Ordena por último feedback desc, nulls por último (estável por nome de desempate).
    out.sort(key=lambda r: (r["ultimo_feedback_em"] is not None, r["ultimo_feedback_em"] or ""), reverse=True)
    return out


async def _resolve_contact_for_feedback(
    session: AsyncSession,
    org: Organization,
    contato_id: str | None,
    contato_whatsapp: str | None,
    contato_nome: str | None,
) -> Contact:
    """Resolve o contato do feedback manual: por id (deve existir na org) OU
    get-or-create por whatsapp (só dígitos). Segue o padrão de opt-in do projeto:
    contato CRIADO aqui nasce sem opt-in (o consentimento de envio vem da fonte
    do cliente, nunca de um registro interno de feedback)."""
    if contato_id is not None:
        try:
            cid = uuid.UUID(contato_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="contato_id inválido")
        contact = (
            await session.execute(
                select(Contact).where(Contact.id == cid, Contact.organization_id == org.id)
            )
        ).scalar_one_or_none()
        if contact is None:
            raise HTTPException(status_code=404, detail="contato não encontrado")
        return contact

    phone = re.sub(r"\D", "", contato_whatsapp or "")
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="contato_whatsapp inválido — use DDI+DDD+número, só dígitos")
    contact = (
        await session.execute(
            select(Contact).where(Contact.organization_id == org.id, Contact.phone == phone)
        )
    ).scalar_one_or_none()
    if contact is None:
        contact = Contact(
            organization_id=org.id,
            phone=phone,
            name=(contato_nome or "").strip() or None,
            opt_in=False,
            profile_data={},
        )
        session.add(contact)
        await session.flush()
    elif contato_nome and not contact.name:
        contact.name = contato_nome.strip() or None
    return contact


class FeedbackCreateIn(BaseModel):
    """Feedback manual: o operador registra o que o cliente deixou por qualquer canal.

    Exige `contato_id` OU `contato_whatsapp` (validado no endpoint para dar 422 com
    mensagem clara). `type` é obrigatório; demais campos opcionais."""

    contato_id: str | None = None
    contato_whatsapp: str | None = Field(default=None, max_length=32)
    contato_nome: str | None = Field(default=None, max_length=200)
    source: str = Field(default="manual", min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=60)
    score: int | None = Field(default=None, ge=0, le=10)
    text: str | None = Field(default=None, max_length=4000)
    sentiment: str | None = None
    themes: list[str] | None = None
    assignee: str | None = Field(default=None, max_length=120)
    team_tag: str | None = Field(default=None, max_length=60)
    abordado: bool = False
    # Data do evento na linha do tempo (quando o cliente disse/aconteceu). None = agora.
    # Aceita ISO-8601 (com ou sem fuso) ou só a data ('YYYY-MM-DD'); normalizada p/ UTC.
    occurred_at: datetime | None = None


async def _auto_classify_feedback(
    brain: SurveyBrain | None,
    *,
    text: str | None,
    type_: str,
    sentiment: str | None,
    themes: list[str] | None,
) -> dict[str, Any] | None:
    """Auto-classifica um feedback manual via IA quando faltam tags — best-effort.

    Roda SÓ quando há `text` e algo a preencher (sentiment/themes ausentes OU type
    genérico/'outro'). NUNCA sobrescreve o que o operador informou: devolve apenas os
    campos que vieram vazios + um `ai_meta` registrando a autoria da IA. Retorna None
    quando não há nada a fazer ou a IA está indisponível/falhou (o endpoint segue sem
    tags). NUNCA lança — IA é enriquecedor, jamais ponto de falha (regra de ouro).
    """
    if brain is None or not text:
        return None
    # Só vale chamar a IA se há buraco a preencher: sentimento, temas ou tipo genérico.
    needs = (sentiment is None) or (not themes) or (type_ in (None, "outro"))
    if not needs:
        return None

    try:
        tags = await brain.classify_feedback(text, None, "feedback manual")
    except Exception:  # noqa: BLE001 — IA é enriquecedor, nunca ponto de falha.
        logger.warning("auto-classify feedback falhou — seguindo sem tags", exc_info=True)
        return None
    if tags is None:
        return None

    out: dict[str, Any] = {}
    # Preenche só o que o operador NÃO informou (não sobrescreve nada explícito).
    if sentiment is None and tags.sentiment in SENTIMENTS:
        out["sentiment"] = tags.sentiment
    if not themes and tags.themes:
        out["themes"] = tags.themes
    out["ai_meta"] = {
        "classified_by": "ai",
        "model": settings.groq_model,
        "urgency": tags.urgency,
        "sentiment": tags.sentiment,
        "themes": tags.themes,
    }
    return out


@router.post("/feedbacks", status_code=201)
async def create_feedback(
    body: FeedbackCreateIn,
    session: AsyncSession = Depends(get_session),
    brain: SurveyBrain | None = Depends(get_brain),
) -> dict[str, Any]:
    """Registra um feedback manual na mega central. Exige contato (id OU whatsapp).

    Se vier `text` e faltar classificação (sentiment/themes ausentes OU type genérico),
    a IA (`SurveyBrain.classify_feedback`) preenche os campos vazios — sem nunca
    sobrescrever o que o operador informou. A classificação é best-effort: se a Groq
    estiver OFF/falhar, o feedback é criado mesmo assim (degrada com segurança).
    Retorna 201 com o item no MESMO formato do feed (`_feedback_out`)."""
    org = await _get_org(session)

    if body.contato_id is None and not body.contato_whatsapp:
        raise HTTPException(status_code=422, detail="informe contato_id OU contato_whatsapp")
    type_keys = effective_type_keys(org)
    if body.type not in type_keys:
        raise HTTPException(
            status_code=422,
            detail=f"type inválido: '{body.type}' (use {', '.join(sorted(type_keys))})",
        )
    if body.sentiment is not None and body.sentiment not in SENTIMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"sentiment inválido: '{body.sentiment}' (use {', '.join(SENTIMENTS)})",
        )

    contact = await _resolve_contact_for_feedback(
        session, org, body.contato_id, body.contato_whatsapp, body.contato_nome
    )

    now = datetime.now(timezone.utc)
    # Data do evento na linha do tempo: a informada (normalizada p/ UTC) ou agora.
    # Futuro é rejeitado (uma "memória" do cliente não acontece amanhã).
    occurred = _coerce_dt(body.occurred_at) or now
    if occurred > now:
        raise HTTPException(status_code=422, detail="a data do evento não pode estar no futuro")
    text = (body.text.strip() or None) if body.text else None
    bucket = nps_bucket(body.score) if (body.type in _BUCKET_TYPES and body.score is not None) else None

    sentiment = body.sentiment
    themes = body.themes
    ai_meta: dict[str, Any] | None = None
    enriched = await _auto_classify_feedback(
        brain, text=text, type_=body.type, sentiment=sentiment, themes=themes
    )
    if enriched is not None:
        sentiment = enriched.get("sentiment", sentiment)
        themes = enriched.get("themes", themes)
        ai_meta = enriched.get("ai_meta")

    item = FeedbackItem(
        organization_id=org.id,
        contact_id=contact.id,
        source=body.source,
        type=body.type,
        score=body.score,
        nps_bucket=bucket,
        text=text,
        sentiment=sentiment,
        themes=themes,
        ai_meta=ai_meta,
        assignee=(body.assignee.strip() or None) if body.assignee else None,
        team_tag=(body.team_tag.strip() or None) if body.team_tag else None,
        occurred_at=occurred,
        abordado=body.abordado,
        abordado_em=now if body.abordado else None,
    )
    session.add(item)
    await session.commit()
    # Camada 1: gera o embedding em background (fire-and-forget) SE a flag estiver ON.
    # Best-effort — não bloqueia nem pode derrubar a resposta. Off (default) = no-op.
    maybe_schedule_embed(item.id, org.id, text)
    return _feedback_out(item, contact)


def _feedback_out(
    f: FeedbackItem, contact: Contact | None, now: datetime | None = None
) -> dict[str, Any]:
    """Serializa um FeedbackItem com os dados do contato juntados (formato do feed).

    Inclui `urgencia` (int 0-100, ver `compute_urgencia`): combina sentimento, type,
    detração, perfil/plano do contato (snapshot partner), recência e flag abordado.
    `now` é injetável para a ordenação calcular a página inteira no MESMO instante.
    """
    when = f.occurred_at or f.created_at
    now = now or datetime.now(timezone.utc)
    partner = (contact.profile_data or {}).get("partner") if contact else None
    urgencia = compute_urgencia(
        sentiment=f.sentiment,
        type_=f.type,
        score=f.score,
        nps_bucket_value=f.nps_bucket,
        abordado=f.abordado,
        occurred_at=f.occurred_at,
        created_at=f.created_at,
        partner=partner if isinstance(partner, dict) else None,
        now=now,
    )
    # Selos de campanha aplicados ao CONTATO (camada win-back, persistidos em
    # profile_data["selos"]). Lista de nomes, [] quando não há contato/selos. Inline
    # aqui (e não importando do campanha.py) porque campanha.py importa deste módulo —
    # importar de volta criaria ciclo.
    selos: list[str] = []
    if contact is not None:
        raw_selos = (contact.profile_data or {}).get("selos")
        if isinstance(raw_selos, list):
            selos = [str(x) for x in raw_selos if x]
    return {
        "id": str(f.id),
        "contato_id": str(f.contact_id) if f.contact_id else None,
        "contato_nome": contact.name if contact else None,
        "contato_whatsapp": contact.phone if contact else None,
        "selos": selos,
        "source": f.source,
        "type": f.type,
        "score": f.score,
        "nps_bucket": f.nps_bucket,
        "sentiment": f.sentiment,
        "themes": f.themes,
        "text": f.text,
        "urgencia": urgencia,
        "action_status": f.action_status,
        "action_note": f.action_note,
        "assignee": f.assignee,
        "team_tag": f.team_tag,
        "improvement_id": str(f.improvement_id) if f.improvement_id else None,
        "abordado": f.abordado,
        "abordado_em": f.abordado_em.isoformat() if f.abordado_em else None,
        "occurred_em": when.isoformat() if when else None,
        "created_em": f.created_at.isoformat() if f.created_at else None,
    }


# Regex p/ celular BR válido na coluna phone: 11 díg (DDD+9+8) OU 13 com DDI 55. É a
# aproximação SQL do validador `tem_whatsapp` (classe 'mobile'). Match = celular.
_WA_MOBILE_REGEX = r"^(55)?[0-9]{2}9[0-9]{8}$"
# Mesma intenção em sintaxe GLOB do SQLite (json1 não tem regex): 11 ou 13 dígitos com
# o '9' do celular na posição certa. GLOB usa [0-9] como classe (igual ao regex) e é
# case-sensitive. Dois padrões: sem DDI (11) e com DDI 55 (13).
_WA_MOBILE_GLOB_11 = "[0-9][0-9]9[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]"
_WA_MOBILE_GLOB_13 = "55[0-9][0-9]9[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]"


def _wa_mobile_clause(dialect: str):
    """Predicado SQL portável "Contact.phone é celular BR válido" (≈ validador 'mobile').

    - Postgres: regex `phone ~ '^(55)?\\d{2}9\\d{8}$'` (aproximação do validador).
    - SQLite (testes, sem regex no json1): `phone GLOB <11díg> OR phone GLOB <13díg c/ 55>`,
      ambos ancorados naturalmente (GLOB casa a string inteira). Mesma semântica do regex
      para os formatos só-dígitos do piloto."""
    if dialect == "postgresql":
        return Contact.phone.op("~")(_WA_MOBILE_REGEX)
    return or_(
        Contact.phone.op("GLOB")(_WA_MOBILE_GLOB_11),
        Contact.phone.op("GLOB")(_WA_MOBILE_GLOB_13),
    )


def _apply_contact_filters(stmt, dialect, *, estado, perfil, plan_type, tem_whatsapp, nps_bucket_):
    """Aplica os filtros "por tipo de cliente" sobre um SELECT que JÁ junta `Contact`.

    Reusado por `base` E `counts_stmt` do feed para o total/contagens baterem com a lista.
    - estado/perfil/plan_type/nps_bucket: JSON path no snapshot partner (mesma técnica de
      list_clientes). `nps_bucket` recebe o rótulo PT ('promotor'/'neutro'/'detrator') e
      vira faixa numérica sobre partner.nps.score (>=9 / 7-8 / <=6).
    - tem_whatsapp ('sim'/'nao'): clause portável `_wa_mobile_clause` (regex no PG / GLOB no
      SQLite), aproximação do validador (celular = match; 'nao' = NOT match, pega
      fixo/grupo/placeholder/vazio).
    Filtros None/desconhecidos são no-op (comportamento idêntico ao anterior)."""
    if perfil:
        stmt = stmt.where(Contact.profile_data["partner"]["profile"].as_string() == perfil)
    if plan_type:
        stmt = stmt.where(
            Contact.profile_data["partner"]["subscription"]["planType"].as_string() == plan_type
        )
    if estado:
        stmt = stmt.where(
            Contact.profile_data["partner"]["subscription"]["state"].as_string() == estado
        )
    if tem_whatsapp in ("sim", "nao"):
        match = _wa_mobile_clause(dialect)
        stmt = stmt.where(match if tem_whatsapp == "sim" else ~match)
    if nps_bucket_ in ("promotor", "neutro", "detrator"):
        score = func.cast(
            Contact.profile_data["partner"]["nps"]["score"].as_string(), Integer
        )
        if nps_bucket_ == "promotor":
            stmt = stmt.where(score >= 9)
        elif nps_bucket_ == "neutro":
            stmt = stmt.where(score >= 7, score <= 8)
        else:
            stmt = stmt.where(score <= 6)
    return stmt


@router.get("/feedbacks")
async def list_feedbacks(
    status: str | None = None,
    type: str | None = None,
    source: str | None = None,
    sentiment: str | None = None,
    theme: str | None = None,
    selo: str | None = None,
    cluster_id: str | None = None,
    assignee: str | None = None,
    team_tag: str | None = None,
    abordado: bool | None = None,
    abordado_periodo: str | None = None,
    estado: str | None = None,
    perfil: str | None = None,
    plan_type: str | None = None,
    tem_whatsapp: str | None = None,
    nps_bucket: str | None = None,
    search: str | None = None,
    sort: Literal["urgencia", "recente"] = "urgencia",
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Feed de monitoramento: feedback_items da org + contato juntado.

    Retorno: {"items": [...], "total": N, "counts_by_status": {"novo": x, ...}}.
    `total` = total do filtro aplicado (ignora limit/offset). `counts_by_status`
    cobre os 5 estados (zeros inclusos) sob o MESMO filtro, exceto o próprio
    `status` (para o frontend montar abas com contagem).

    Filtro `theme`: drill-down da tela Temas — mantém só os feedbacks cujo array
    `themes` CONTÉM exatamente aquele tema (match exato do elemento, não substring;
    JSONB `@>` no PG / `json_each` no SQLite). Combina com os demais filtros.

    Filtro `selo`: status de campanha no inbox — mantém só os feedbacks de CONTATOS
    com aquele selo aplicado (`Contact.profile_data["selos"]`, ver campanha.py). Cada
    item já traz `selos` (lista de nomes do contato) para a tela mostrar o estágio.

    Filtros "por tipo de cliente" (sobre o CONTATO juntado; aplicados ao feed E às
    contagens para o total bater) — todos opcionais e no-op quando ausentes:
    - estado: partner.subscription.state (JSON path), ex.: 'cancelled', 'active_paying'.
    - perfil: partner.profile (JSON path), ex.: 'ativo_promotor', 'churn_pos_uso'.
    - plan_type: partner.subscription.planType (JSON path), 'mensal' | 'anual'.
    - tem_whatsapp: 'sim' | 'nao' — regex/GLOB SQL na coluna phone (≈ validador 'mobile'):
      celular BR de 11 ou 13 díg com o '9' na posição certa. 'nao' = NÃO casa (fixo/grupo/
      placeholder/vazio).
    - nps_bucket: 'promotor' (score>=9) | 'neutro' (7-8) | 'detrator' (<=6) sobre o JSON
      partner.nps.score.

    Ordenação (`sort`):
    - `urgencia` (DEFAULT): score de urgência desc (ver `compute_urgencia`); empate
      por recência (occurred desc). O inbox prioriza sozinho — detrator/churn/em-risco
      sobem ao topo. Calculado em Python sobre o conjunto FILTRADO inteiro (o
      score combina campos JSON do contato + decaimento por recência, inviável em SQL
      portável), depois paginado — a paginação continua correta (piloto ~70 itens).
    - `recente`: occurred desc (fallback created) — cronológico, paginado em SQL."""
    org = await _get_org(session)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    # Dialeto do bind para o filtro de tema (JSONB @> no PG / json_each no SQLite).
    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"

    base = (
        select(FeedbackItem, Contact)
        .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
        .where(FeedbackItem.organization_id == org.id)
    )
    if status:
        base = base.where(FeedbackItem.action_status == status)
    if type:
        base = base.where(FeedbackItem.type == type)
    if source:
        base = base.where(FeedbackItem.source == source)
    if sentiment:
        base = base.where(FeedbackItem.sentiment == sentiment)
    if theme:
        base = base.where(_theme_match_clause(theme, dialect))
    if selo:
        # Só feedbacks de contatos com este selo de campanha (status de campanha no inbox).
        base = base.where(_selo_match_clause(selo, dialect))
    if cluster_id:
        base = base.where(FeedbackItem.cluster_id == uuid.UUID(cluster_id))
    if assignee:
        base = base.where(FeedbackItem.assignee == assignee)
    if team_tag:
        base = base.where(FeedbackItem.team_tag == team_tag)
    if abordado is not None:
        base = base.where(FeedbackItem.abordado == abordado)
    if abordado_periodo is not None:
        inicio = _abordado_inicio(abordado_periodo)
        if inicio is not None:
            # "Abordados no período": só os já abordados cujo carimbo cai no recorte.
            base = base.where(
                FeedbackItem.abordado.is_(True),
                FeedbackItem.abordado_em >= inicio,
            )
    if search:
        term = f"%{search.strip().lower()}%"
        base = base.where(
            or_(
                func.lower(func.coalesce(FeedbackItem.text, "")).like(term),
                func.lower(func.coalesce(Contact.name, "")).like(term),
            )
        )
    # Filtros "por tipo de cliente" (snapshot partner do CONTATO juntado): estado/perfil/
    # plan_type/tem_whatsapp/nps_bucket. Aplicados ao `base` E ao `counts_stmt` p/ bater.
    base = _apply_contact_filters(
        base, dialect, estado=estado, perfil=perfil, plan_type=plan_type,
        tem_whatsapp=tem_whatsapp, nps_bucket_=nps_bucket,
    )

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    order_key = func.coalesce(FeedbackItem.occurred_at, FeedbackItem.created_at)
    now = datetime.now(timezone.utc)
    if sort == "recente":
        # Cronológico: pagina direto no SQL (eficiente, comportamento original).
        rows = (
            await session.execute(base.order_by(order_key.desc()).limit(limit).offset(offset))
        ).all()
        items = [_feedback_out(f, c, now) for f, c in rows]
    else:
        # Urgência: precisa do conjunto filtrado inteiro (score em Python sobre JSON do
        # contato + recência). Ordena por occurred desc no SQL como desempate estável,
        # serializa todos (urgencia já calculada no MESMO `now`), ordena por urgencia e
        # então pagina. Para ~70 itens do piloto é trivial; o LIMIT/OFFSET no SQL não
        # serve aqui porque cortaria ANTES do ranqueamento por urgência.
        rows = (await session.execute(base.order_by(order_key.desc()))).all()
        all_items = [_feedback_out(f, c, now) for f, c in rows]
        # rows já vêm por recência desc → sort estável por urgência mantém isso no empate.
        all_items.sort(key=lambda it: it["urgencia"], reverse=True)
        items = all_items[offset : offset + limit]

    # counts_by_status: mesmo filtro, MENOS o próprio status (abas de status no front).
    counts_stmt = (
        select(FeedbackItem.action_status, func.count())
        .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
        .where(FeedbackItem.organization_id == org.id)
    )
    if type:
        counts_stmt = counts_stmt.where(FeedbackItem.type == type)
    if source:
        counts_stmt = counts_stmt.where(FeedbackItem.source == source)
    if sentiment:
        counts_stmt = counts_stmt.where(FeedbackItem.sentiment == sentiment)
    if theme:
        counts_stmt = counts_stmt.where(_theme_match_clause(theme, dialect))
    if selo:
        counts_stmt = counts_stmt.where(_selo_match_clause(selo, dialect))
    if cluster_id:
        counts_stmt = counts_stmt.where(FeedbackItem.cluster_id == uuid.UUID(cluster_id))
    if assignee:
        counts_stmt = counts_stmt.where(FeedbackItem.assignee == assignee)
    if team_tag:
        counts_stmt = counts_stmt.where(FeedbackItem.team_tag == team_tag)
    if abordado is not None:
        counts_stmt = counts_stmt.where(FeedbackItem.abordado == abordado)
    if abordado_periodo is not None:
        inicio = _abordado_inicio(abordado_periodo)
        if inicio is not None:
            counts_stmt = counts_stmt.where(
                FeedbackItem.abordado.is_(True),
                FeedbackItem.abordado_em >= inicio,
            )
    if search:
        term = f"%{search.strip().lower()}%"
        counts_stmt = counts_stmt.where(
            or_(
                func.lower(func.coalesce(FeedbackItem.text, "")).like(term),
                func.lower(func.coalesce(Contact.name, "")).like(term),
            )
        )
    # Mesmos filtros "por tipo de cliente" do `base` (total/contagens coerentes com a lista).
    counts_stmt = _apply_contact_filters(
        counts_stmt, dialect, estado=estado, perfil=perfil, plan_type=plan_type,
        tem_whatsapp=tem_whatsapp, nps_bucket_=nps_bucket,
    )
    counts_raw = dict((await session.execute(counts_stmt.group_by(FeedbackItem.action_status))).all())
    # Itera a lista EFETIVA de status (defaults ∪ custom da org). Sem custom => idêntico a
    # ACTION_STATUSES (mesma ordem). Os defaults sempre presentes (zeros inclusos).
    counts_by_status = {s: int(counts_raw.get(s, 0)) for s in effective_status_keys(org)}

    return {
        "items": items,
        "total": int(total),
        "counts_by_status": counts_by_status,
    }


# Quantos cards mostrar por coluna do board (os mais urgentes). O `count` reflete o
# total real da coluna; `items` é o recorte priorizado para a tela não estourar.
BOARD_ITEMS_PER_COLUMN = 12


@router.get("/feedbacks/board")
async def feedbacks_board(
    team_tag: str | None = None,
    assignee: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Board de Gestão (Kanban): os feedbacks da org agrupados por coluna de ação.

    Retorno: {"columns": {"novo": {"count": N, "items": [...top 12 por urgência...]},
    "em_analise": {...}, "planejado": {...}, "resolvido": {...}, "descartado": {...}}}.
    Todas as 5 colunas de ACTION_STATUSES sempre presentes (zeros inclusos). `count` =
    total da coluna sob o filtro; `items` = os `BOARD_ITEMS_PER_COLUMN` mais urgentes
    (mesmo `compute_urgencia`+`_feedback_out` do feed).

    Filtros opcionais `team_tag`/`assignee` (roteamento por time). UMA query (carrega o
    conjunto filtrado + contato juntado), agrupa/ordena em Python — o board do piloto
    tem dezenas de itens, então é trivial (mesma estratégia do sort por urgência do feed).
    """
    org = await _get_org(session)

    base = (
        select(FeedbackItem, Contact)
        .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
        .where(FeedbackItem.organization_id == org.id)
    )
    if team_tag:
        base = base.where(FeedbackItem.team_tag == team_tag)
    if assignee:
        base = base.where(FeedbackItem.assignee == assignee)

    rows = (await session.execute(base)).all()

    now = datetime.now(timezone.utc)
    # Colunas = lista EFETIVA de status (defaults ∪ custom da org). Sem custom => idêntico
    # a ACTION_STATUSES (mesma ordem). Itens com status fora do vocabulário efetivo são
    # ignorados no board (não há coluna pra eles) — raro na prática (a escrita valida).
    status_keys = effective_status_keys(org)
    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in status_keys}
    for f, c in rows:
        if f.action_status in grouped:
            grouped[f.action_status].append(_feedback_out(f, c, now))

    columns: dict[str, dict[str, Any]] = {}
    for s in status_keys:
        col = grouped[s]
        col.sort(key=lambda it: it["urgencia"], reverse=True)
        columns[s] = {"count": len(col), "items": col[:BOARD_ITEMS_PER_COLUMN]}

    return {"columns": columns}


class FeedbackMoveIn(BaseModel):
    """Drag-and-drop de um card no board: muda a coluna (`status` = action_status).

    `improvement_id` (opcional): ao mover para 'planejado', vincula o feedback àquela
    melhoria (valida que pertence à org). `assignee` (opcional): atribui o responsável
    no mesmo movimento. Vocabulário de `status` validado no endpoint (= ACTION_STATUSES).
    """

    status: str
    improvement_id: str | None = None
    assignee: str | None = Field(default=None, max_length=120)


@router.post("/feedbacks/{feedback_id}/move")
async def move_feedback(
    feedback_id: str,
    body: FeedbackMoveIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Move um card no board: troca o `action_status` (valida o vocabulário). Se
    `status=='planejado'` e vier `improvement_id`, vincula o feedback à melhoria (404 se
    a melhoria não existir/for de outra org). Aplica `assignee` se enviado. Retorna o
    item no formato do feed (`_feedback_out`). É 1 request por card movido."""
    org = await _get_org(session)
    try:
        fid = uuid.UUID(feedback_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    status_keys = effective_status_keys(org)
    if body.status not in status_keys:
        raise HTTPException(
            status_code=422,
            detail=f"status inválido: '{body.status}' (use {', '.join(status_keys)})",
        )

    feedback = (
        await session.execute(
            select(FeedbackItem).where(
                FeedbackItem.id == fid, FeedbackItem.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="feedback não encontrado")

    # Valida a melhoria ANTES de mexer no feedback (validar-depois-mutar): assim um 404 de
    # melhoria de outra org não deixa uma mudança de status meia-aplicada na sessão.
    # Se vier improvement_id, valida e aplica em QUALQUER status (não ignora em silêncio);
    # para desvincular, use o PATCH /feedbacks/{id} com improvement_id=null.
    imp = None
    if body.improvement_id:
        imp = await _get_improvement(session, org, body.improvement_id)

    feedback.action_status = body.status
    if imp is not None:
        feedback.improvement_id = imp.id

    sent = body.model_fields_set
    if "assignee" in sent:
        feedback.assignee = (body.assignee.strip() or None) if body.assignee else None

    await session.commit()

    contact = None
    if feedback.contact_id is not None:
        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.id == feedback.contact_id,
                    Contact.organization_id == org.id,
                )
            )
        ).scalar_one_or_none()
    return _feedback_out(feedback, contact)


class FeedbackActionIn(BaseModel):
    """PATCH parcial do feedback: ação (status/nota), flag `abordado`, atribuição
    (assignee/team_tag), vínculo de melhoria (improvement_id) e edição de conteúdo
    (text/type/score/sentiment/themes). Todos opcionais — só o que vier no corpo é
    tocado. `model_fields_set` distingue "não enviado" de "enviado como null"
    (ex.: `improvement_id=null` DESVINCULA; ausente = mantém o vínculo atual).
    """

    action_status: str | None = None
    action_note: str | None = None
    abordado: bool | None = None
    text: str | None = Field(default=None, max_length=4000)
    type: str | None = Field(default=None, min_length=1, max_length=60)
    score: int | None = Field(default=None, ge=0, le=10)
    sentiment: str | None = None
    themes: list[str] | None = None
    assignee: str | None = Field(default=None, max_length=120)
    team_tag: str | None = Field(default=None, max_length=60)
    improvement_id: str | None = None


@router.patch("/feedbacks/{feedback_id}")
async def update_feedback_action(
    feedback_id: str,
    body: FeedbackActionIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Edição parcial de um feedback: ação (status/nota), flag `abordado` (ao virar
    True grava `abordado_em`=agora se vazio; ao virar False zera), atribuição
    (assignee/team_tag), vínculo de melhoria (improvement_id; 404/422 se a melhoria
    não existir/for de outra org, `null` desvincula — NÃO mexe no action_status) e
    conteúdo (text/type/score/sentiment/themes). Revalida `nps_bucket` quando
    type/score mudam. Retorna o item no formato do feed. 422 em valores inválidos."""
    org = await _get_org(session)
    try:
        fid = uuid.UUID(feedback_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    sent = body.model_fields_set

    status_keys = effective_status_keys(org)
    if body.action_status is not None and body.action_status not in status_keys:
        raise HTTPException(
            status_code=422,
            detail=f"action_status inválido: '{body.action_status}' (use {', '.join(status_keys)})",
        )
    type_keys = effective_type_keys(org)
    if "type" in sent and (body.type is None or body.type not in type_keys):
        raise HTTPException(
            status_code=422,
            detail=f"type inválido: '{body.type}' (use {', '.join(sorted(type_keys))})",
        )
    if "sentiment" in sent and body.sentiment is not None and body.sentiment not in SENTIMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"sentiment inválido: '{body.sentiment}' (use {', '.join(SENTIMENTS)})",
        )

    # Vínculo de melhoria: valida ANTES de mutar (validar-depois-mutar). `null` desvincula.
    # `_get_improvement` levanta 422 (uuid inválido) / 404 (não é da org). NÃO mexemos no
    # action_status aqui — o vínculo é independente da esteira (decisão do operador depois).
    imp_to_link: Improvement | None = None
    if "improvement_id" in sent and body.improvement_id is not None:
        imp_to_link = await _get_improvement(session, org, body.improvement_id)

    feedback = (
        await session.execute(
            select(FeedbackItem).where(
                FeedbackItem.id == fid, FeedbackItem.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="feedback não encontrado")

    if body.action_status is not None:
        feedback.action_status = body.action_status
    if body.action_note is not None:
        feedback.action_note = (body.action_note.strip() or None)

    if "abordado" in sent and body.abordado is not None:
        feedback.abordado = body.abordado
        if body.abordado:
            if feedback.abordado_em is None:
                feedback.abordado_em = datetime.now(timezone.utc)
        else:
            feedback.abordado_em = None

    if "text" in sent:
        feedback.text = (body.text.strip() or None) if body.text else None
    if "type" in sent:
        feedback.type = body.type
    if "sentiment" in sent:
        feedback.sentiment = body.sentiment
    if "themes" in sent:
        feedback.themes = body.themes
    if "score" in sent:
        feedback.score = body.score
    if "assignee" in sent:
        feedback.assignee = (body.assignee.strip() or None) if body.assignee else None
    if "team_tag" in sent:
        feedback.team_tag = (body.team_tag.strip() or None) if body.team_tag else None
    if "improvement_id" in sent:
        # imp_to_link já validado acima; None quando body.improvement_id é null (desvincula).
        feedback.improvement_id = imp_to_link.id if imp_to_link is not None else None

    # Revalida o bucket se type ou score mudaram (ou se algum foi enviado).
    if ("score" in sent) or ("type" in sent):
        feedback.nps_bucket = (
            nps_bucket(feedback.score)
            if (feedback.type in _BUCKET_TYPES and feedback.score is not None)
            else None
        )

    await session.commit()

    contact = None
    if feedback.contact_id is not None:
        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.id == feedback.contact_id,
                    Contact.organization_id == org.id,
                )
            )
        ).scalar_one_or_none()
    return _feedback_out(feedback, contact)


@router.delete("/feedbacks/{feedback_id}", status_code=204)
async def delete_feedback(
    feedback_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove um feedback da org. 404 se não pertencer à org. 204 sem corpo."""
    org = await _get_org(session)
    try:
        fid = uuid.UUID(feedback_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    feedback = (
        await session.execute(
            select(FeedbackItem).where(
                FeedbackItem.id == fid, FeedbackItem.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="feedback não encontrado")

    await session.delete(feedback)
    await session.commit()


# --- Clustering de temas (Fase 2) --------------------------------------------


@router.get("/themes/aggregate")
async def themes_aggregate(days: int = 7, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Temas mais citados no período (survey + feedback), com sentimento — clustering v1."""
    org = await _get_org(session)
    themes = await aggregate_themes(session, org.id, days=days)
    return {
        "period_days": days,
        "total": sum(t.count for t in themes),
        "themes": [
            {"name": t.theme, "count": t.count, "sentiment": t.sentiment_breakdown}
            for t in themes
        ],
    }


# --- Melhorias do roadmap ("Fechar o loop") ----------------------------------

# Estágios de uma melhoria no roadmap. Ordem = funil (ideia → entregue). Validado
# na API (sem CHECK no banco — vocabulário pode crescer, igual ACTION_STATUSES).
IMPROVEMENT_STATUSES: tuple[str, ...] = (
    "ideia",
    "planejada",
    "em_andamento",
    "entregue",
    "descartada",
)

# Esforço estimado de uma melhoria (camisa). Validado na API (sem CHECK no banco).
IMPROVEMENT_EFFORTS: tuple[str, ...] = ("P", "M", "G", "XG")


def _improvement_out(imp: Improvement, feedback_count: int = 0) -> dict[str, Any]:
    """Serializa uma melhoria com a contagem de feedbacks vinculados."""
    return {
        "id": str(imp.id),
        "title": imp.title,
        "description": imp.description,
        "status": imp.status,
        "cluster_id": str(imp.cluster_id) if imp.cluster_id else None,
        "effort": imp.effort,
        "target_date": imp.target_date.isoformat() if imp.target_date else None,
        "feedback_count": int(feedback_count),
        "created_em": imp.created_at.isoformat() if imp.created_at else None,
        "delivered_em": imp.delivered_at.isoformat() if imp.delivered_at else None,
        "notified_em": imp.notified_at.isoformat() if imp.notified_at else None,
    }


def _first_name(contact: Contact) -> str:
    """Primeiro nome do contato para a saudação (vazio se não houver nome)."""
    return (contact.name or "").split(" ")[0].strip() if contact.name else ""


def _pick_theme(feedbacks: list[FeedbackItem]) -> str | None:
    """Tema representativo do conjunto de feedbacks vinculados (o mais citado).

    Junta os arrays `themes` de todos os feedbacks da melhoria e devolve o mais
    frequente, para a mensagem dizer "você comentou sobre {tema}". None quando
    nenhum feedback tem tema (a mensagem usa um fallback genérico).
    """
    from collections import Counter

    counter: Counter = Counter()
    for f in feedbacks:
        for t in (f.themes or []):
            key = str(t).strip()
            if key:
                counter[key] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _notify_message(contact: Contact, theme: str | None, org: Organization) -> str:
    """Mensagem "você pediu, a gente fez" — calorosa, curta, on-brand (sem travessão).

    Personaliza com o primeiro nome e o tema citado quando há. {org.name} é a marca
    (ex.: Bizzu). Sem o caractere '—' (travessão), conforme a identidade da marca.
    """
    nome = _first_name(contact)
    saudacao = f"Oi {nome}! " if nome else "Oi! "
    marca = org.name or "a gente"
    if theme:
        miolo = (
            f"Lembra que você comentou sobre {theme}? "
            f"A gente acabou de melhorar isso na {marca} 💜 "
            "obrigado por ajudar a construir."
        )
    else:
        miolo = (
            f"Você deixou um feedback pra gente e a gente acabou de melhorar isso na {marca} 💜 "
            "obrigado por ajudar a construir."
        )
    return saudacao + miolo


async def _recent_outbound_at(
    session: AsyncSession, org_id: uuid.UUID, contact_id: uuid.UUID
) -> datetime | None:
    """Instante do último outbound para o contato (tabela `messages`) ou None.

    Base do cooldown: se a última mensagem proativa é recente demais, não mandamos
    de novo. Usa o transcript append-only que o resto do projeto já alimenta.
    """
    return (
        await session.execute(
            select(func.max(Message.created_at)).where(
                Message.organization_id == org_id,
                Message.contact_id == contact_id,
                Message.direction == "outbound",
            )
        )
    ).scalar_one_or_none()


class ImprovementIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    cluster_id: str | None = None
    effort: str | None = None
    target_date: datetime | None = None


class ImprovementPatchIn(BaseModel):
    """PATCH parcial: title/description/status/cluster_id/effort/target_date.
    `model_fields_set` distingue "não enviado" de "enviado como null"."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    cluster_id: str | None = None
    effort: str | None = None
    target_date: datetime | None = None


class ImprovementLinkIn(BaseModel):
    feedback_ids: list[str] = Field(min_length=1)


class ImprovementFromClusterIn(BaseModel):
    cluster_id: str
    title: str | None = Field(default=None, max_length=200)


async def _resolve_cluster_id(
    session: AsyncSession, org: Organization, raw: str
) -> uuid.UUID:
    """Valida um cluster_id (UUID + pertence à org) e devolve o UUID. 422/404 senão."""
    try:
        cid = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="cluster_id inválido")
    exists = (
        await session.execute(
            select(FeedbackCluster.id).where(
                FeedbackCluster.id == cid, FeedbackCluster.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="cluster (dor) não encontrado")
    return cid


def _validate_effort(value: str | None) -> str | None:
    """Normaliza/valida o esforço (P/M/G/XG). None/'' -> None; inválido -> 422."""
    if value is None:
        return None
    eff = value.strip().upper()
    if not eff:
        return None
    if eff not in IMPROVEMENT_EFFORTS:
        raise HTTPException(
            status_code=422,
            detail=f"effort inválido: '{value}' (use {', '.join(IMPROVEMENT_EFFORTS)})",
        )
    return eff


@router.post("/improvements", status_code=201)
async def create_improvement(
    body: ImprovementIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Cria uma melhoria do roadmap (title obrigatório). Nasce com status 'ideia'
    e sem feedbacks vinculados. Aceita opcionalmente cluster_id (valida que pertence
    à org), effort (P/M/G/XG) e target_date. 201 com o item no formato de
    `_improvement_out`."""
    org = await _get_org(session)
    cluster_id = (
        await _resolve_cluster_id(session, org, body.cluster_id) if body.cluster_id else None
    )
    imp = Improvement(
        organization_id=org.id,
        title=body.title.strip(),
        description=(body.description.strip() or None) if body.description else None,
        status="ideia",
        cluster_id=cluster_id,
        effort=_validate_effort(body.effort),
        target_date=body.target_date,
    )
    session.add(imp)
    await session.commit()
    return _improvement_out(imp, feedback_count=0)


@router.get("/improvements")
async def list_improvements(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Lista as melhorias da org, cada uma com `feedback_count` (feedbacks vinculados)
    e `status`. Ordem: mais recentes primeiro (created desc)."""
    org = await _get_org(session)
    rows = (
        (
            await session.execute(
                select(Improvement)
                .where(Improvement.organization_id == org.id)
                .order_by(Improvement.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    # Contagem de feedbacks por melhoria (uma query agregada para toda a lista).
    counts = dict(
        (
            await session.execute(
                select(FeedbackItem.improvement_id, func.count())
                .where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.improvement_id.is_not(None),
                )
                .group_by(FeedbackItem.improvement_id)
            )
        ).all()
    )
    return [_improvement_out(imp, counts.get(imp.id, 0)) for imp in rows]


@router.get("/improvements/roadmap")
async def roadmap_improvements(
    status: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Roadmap priorizado: as melhorias da org ordenadas por `priority_score` desc.

    Para cada melhoria, além dos campos de `_improvement_out`:
    - `feedback_count`: nº de feedbacks vinculados (uma query agregada).
    - `urgencia_media`: média do `compute_urgencia` sobre os feedbacks vinculados.
      Calculada com UMA query em lote (`improvement_id IN (...)`), agrupando em
      Python — sem N+1. 0 quando a melhoria não tem feedbacks.
    - `cluster_label` / `cluster_neg_fraction`: do cluster (dor) de origem, se houver
      `cluster_id` (uma query de labels + uma de frações negativas, ambas em lote).

    `priority_score = feedback_count * max(urgencia_media, 1) * (1 + cluster_neg_fraction)`.
    O `?status=` filtra por estágio (ex.: só 'planejada').
    """
    org = await _get_org(session)

    q = select(Improvement).where(Improvement.organization_id == org.id)
    if status is not None:
        q = q.where(Improvement.status == status)
    rows = (await session.execute(q.order_by(Improvement.created_at.desc()))).scalars().all()

    if not rows:
        return []

    imp_ids = [imp.id for imp in rows]

    # feedback_count por melhoria (uma query agregada).
    counts = dict(
        (
            await session.execute(
                select(FeedbackItem.improvement_id, func.count())
                .where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.improvement_id.in_(imp_ids),
                )
                .group_by(FeedbackItem.improvement_id)
            )
        ).all()
    )

    # urgencia_media: UMA query em lote com todos os feedbacks vinculados a estas
    # melhorias. Agrupa por improvement_id em Python e tira a média do compute_urgencia.
    feedbacks = (
        (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.improvement_id.in_(imp_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    # Snapshot partner por contato (uma query em lote — evita N+1 ao computar urgência).
    fb_contact_ids = list(dict.fromkeys(f.contact_id for f in feedbacks if f.contact_id is not None))
    partners: dict[uuid.UUID, dict | None] = {}
    if fb_contact_ids:
        for c in (
            (
                await session.execute(
                    select(Contact).where(
                        Contact.id.in_(fb_contact_ids), Contact.organization_id == org.id
                    )
                )
            )
            .scalars()
            .all()
        ):
            partners[c.id] = (c.profile_data or {}).get("partner")

    now = datetime.now(timezone.utc)
    urg_sum: dict[uuid.UUID, int] = {}
    urg_n: dict[uuid.UUID, int] = {}
    for f in feedbacks:
        partner = partners.get(f.contact_id) if f.contact_id is not None else None
        u = compute_urgencia(
            sentiment=f.sentiment,
            type_=f.type,
            score=f.score,
            nps_bucket_value=f.nps_bucket,
            abordado=f.abordado,
            occurred_at=f.occurred_at,
            created_at=f.created_at,
            partner=partner if isinstance(partner, dict) else None,
            now=now,
        )
        urg_sum[f.improvement_id] = urg_sum.get(f.improvement_id, 0) + u
        urg_n[f.improvement_id] = urg_n.get(f.improvement_id, 0) + 1

    # Dados do cluster de origem (label + fração negativa) — em lote, só p/ quem tem cluster_id.
    cluster_ids = list(dict.fromkeys(imp.cluster_id for imp in rows if imp.cluster_id is not None))
    labels: dict[uuid.UUID, str | None] = {}
    neg_fraction: dict[uuid.UUID, float] = {}
    if cluster_ids:
        for cid, label in (
            await session.execute(
                select(FeedbackCluster.id, FeedbackCluster.label).where(
                    FeedbackCluster.organization_id == org.id,
                    FeedbackCluster.id.in_(cluster_ids),
                )
            )
        ).all():
            labels[cid] = label
        # Fração negativa = negativos / total dos feedbacks do cluster (uma query agregada).
        for cid, total, neg in (
            await session.execute(
                select(
                    FeedbackItem.cluster_id,
                    func.count(),
                    func.sum(
                        case((FeedbackItem.sentiment == "negativo", 1), else_=0)
                    ),
                )
                .where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.cluster_id.in_(cluster_ids),
                )
                .group_by(FeedbackItem.cluster_id)
            )
        ).all():
            neg_fraction[cid] = (int(neg or 0) / total) if total else 0.0

    out: list[dict[str, Any]] = []
    for imp in rows:
        fc = int(counts.get(imp.id, 0))
        n = urg_n.get(imp.id, 0)
        urgencia_media = (urg_sum.get(imp.id, 0) / n) if n else 0.0
        neg = neg_fraction.get(imp.cluster_id, 0.0) if imp.cluster_id is not None else 0.0
        priority_score = fc * max(urgencia_media, 1.0) * (1.0 + neg)
        item = _improvement_out(imp, fc)
        item["urgencia_media"] = round(urgencia_media, 1)
        item["cluster_label"] = labels.get(imp.cluster_id) if imp.cluster_id is not None else None
        item["cluster_neg_fraction"] = round(neg, 3)
        item["priority_score"] = round(priority_score, 2)
        out.append(item)

    out.sort(key=lambda it: it["priority_score"], reverse=True)
    return out


@router.post("/improvements/from-cluster", status_code=201)
async def improvement_from_cluster(
    body: ImprovementFromClusterIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Cria uma melhoria A PARTIR de uma dor (cluster) e vincula seus feedbacks.

    - `title` = o título dado OU o `label` do cluster (fallback genérico se ambos NULL).
    - status nasce 'ideia'; seta `improvement.cluster_id` E `cluster.improvement_id`;
      faz bulk-link de TODOS os `FeedbackItem` do cluster (`improvement_id = nova.id`).
    - IDEMPOTENTE: se o cluster já tem `improvement_id`, devolve a melhoria existente
      (não duplica, não re-vincula). 201 com o `_improvement_out` + `feedback_count`.
    """
    org = await _get_org(session)
    cid = await _resolve_cluster_id(session, org, body.cluster_id)
    cluster = (
        await session.execute(
            select(FeedbackCluster).where(
                FeedbackCluster.id == cid, FeedbackCluster.organization_id == org.id
            )
        )
    ).scalar_one()

    # Idempotência: o cluster já virou melhoria -> devolve a existente, sem duplicar.
    if cluster.improvement_id is not None:
        existing = (
            await session.execute(
                select(Improvement).where(
                    Improvement.id == cluster.improvement_id,
                    Improvement.organization_id == org.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            count = await _feedback_count(session, org.id, existing.id)
            return _improvement_out(existing, count)

    title = (body.title or "").strip() or (cluster.label or "").strip() or "Melhoria (sem título)"
    imp = Improvement(
        organization_id=org.id,
        title=title,
        status="ideia",
        cluster_id=cluster.id,
    )
    session.add(imp)
    await session.flush()  # garante imp.id antes de vincular

    cluster.improvement_id = imp.id

    # bulk-link: todos os feedbacks daquela dor passam a pertencer à nova melhoria.
    feedbacks = (
        (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.cluster_id == cluster.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for f in feedbacks:
        f.improvement_id = imp.id

    await session.commit()
    count = await _feedback_count(session, org.id, imp.id)
    return _improvement_out(imp, count)


async def _get_improvement(session: AsyncSession, org: Organization, improvement_id: str) -> Improvement:
    try:
        iid = uuid.UUID(improvement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")
    imp = (
        await session.execute(
            select(Improvement).where(
                Improvement.id == iid, Improvement.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if imp is None:
        raise HTTPException(status_code=404, detail="melhoria não encontrada")
    return imp


async def _feedback_count(session: AsyncSession, org_id: uuid.UUID, improvement_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(FeedbackItem)
            .where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.improvement_id == improvement_id,
            )
        )
    ).scalar_one()


# --- Configuração de vocabulários (status/tipos/origens) por org --------------
# O dono cria os PRÓPRIOS status (os fixos "não fazem sentido"), tipos de feedback e
# origens. Tudo em Organization.settings (sem migration; mesmo padrão copia-edita-
# reatribui dos boards). As listas EFETIVAS = DEFAULTS (imutáveis, preservam dados
# existentes) ∪ customizados da org. O PUT salva SÓ os customizados; uma key custom
# NÃO pode colidir com um default (422). Idempotente: reenviar a mesma lista é no-op
# de efeito; mandar uma lista sem um item antes salvo = REMOVE aquele custom.


class _StatusConfigIn(BaseModel):
    """Status customizado no corpo do PUT /api/config. `key` obrigatória."""

    key: str = Field(min_length=1, max_length=60)
    label: str | None = Field(default=None, max_length=80)
    cor: str | None = Field(default=None, max_length=32)


class _KVConfigIn(BaseModel):
    """Tipo/origem customizado no corpo do PUT /api/config. `key` obrigatória."""

    key: str = Field(min_length=1, max_length=60)
    label: str | None = Field(default=None, max_length=80)


class ConfigIn(BaseModel):
    """Corpo do PUT /api/config: SÓ os customizados de cada vocabulário.

    Campo ausente (não enviado) => aquele vocabulário fica intocado. Campo enviado
    (mesmo `[]`) => substitui o conjunto de customizados daquele vocabulário (logo
    `[]` limpa todos os customizados dele). `model_fields_set` distingue ausente de [].
    """

    action_statuses: list[_StatusConfigIn] | None = None
    feedback_types: list[_KVConfigIn] | None = None
    feedback_origins: list[_KVConfigIn] | None = None


def _config_payload(org: Organization) -> dict[str, Any]:
    """As 3 listas EFETIVAS (defaults ∪ custom) no contrato {key,label[,cor]}."""
    return {
        "action_statuses": effective_statuses(org),  # [{key,label,cor}]
        "feedback_types": effective_types(org),       # [{key,label}]
        "feedback_origins": effective_origins(org),   # [{key,label}]
    }


def _custom_from_in_status(items: list[_StatusConfigIn]) -> list[dict[str, str]]:
    """Normaliza status customizados do corpo (dedup por key, mantém a 1ª)."""
    out: list[dict[str, str]] = []
    vistos: set[str] = set()
    for it in items:
        key = it.key.strip()
        if not key or key in vistos:
            continue
        vistos.add(key)
        out.append(
            {
                "key": key,
                "label": (it.label or "").strip() or _label_humano(key),
                "cor": (it.cor or "").strip() or _COR_STATUS_DEFAULT,
            }
        )
    return out


def _custom_from_in_kv(items: list[_KVConfigIn]) -> list[dict[str, str]]:
    """Normaliza tipos/origens customizados do corpo (dedup por key, mantém a 1ª)."""
    out: list[dict[str, str]] = []
    vistos: set[str] = set()
    for it in items:
        key = it.key.strip()
        if not key or key in vistos:
            continue
        vistos.add(key)
        out.append({"key": key, "label": (it.label or "").strip() or _label_humano(key)})
    return out


def _reject_default_collisions(custom: list[dict[str, str]], defaults: tuple[str, ...], rotulo: str) -> None:
    """422 se algum custom usa uma key reservada por um default (defaults são imutáveis)."""
    reservadas = set(defaults)
    colisoes = [c["key"] for c in custom if c["key"] in reservadas]
    if colisoes:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{rotulo}: a(s) key(s) {', '.join(sorted(set(colisoes)))} já é(são) padrão "
                f"e não pode(m) ser redefinida(s)"
            ),
        )


@router.get("/config")
async def get_config(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Vocabulários configuráveis da org: as 3 listas EFETIVAS (defaults ∪ custom).

    Retorno: {"action_statuses": [{key,label,cor}, ...], "feedback_types": [{key,label},
    ...], "feedback_origins": [{key,label}, ...]}. Os defaults vêm sempre primeiro e nunca
    somem; os customizados da org seguem na ordem em que foram salvos."""
    org = await _get_org(session)
    return _config_payload(org)


@router.put("/config")
async def put_config(body: ConfigIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Salva SÓ os vocabulários CUSTOMIZADOS da org em settings (defaults nunca tocados).

    Para cada campo ENVIADO no corpo, substitui o conjunto de customizados daquele
    vocabulário (lista vazia limpa todos). Campo ausente = vocabulário intocado. Uma key
    custom NÃO pode colidir com um default (422). Idempotente e padrão boards (copia-edita-
    reatribui o JSONB). Retorna as 3 listas EFETIVAS já atualizadas (mesmo shape do GET)."""
    org = await _get_org(session)
    sent = body.model_fields_set
    s = dict(org.settings or {})

    if "action_statuses" in sent and body.action_statuses is not None:
        custom = _custom_from_in_status(body.action_statuses)
        _reject_default_collisions(custom, ACTION_STATUSES, "action_statuses")
        s[_SETTINGS_KEY_STATUSES] = custom
    if "feedback_types" in sent and body.feedback_types is not None:
        custom = _custom_from_in_kv(body.feedback_types)
        _reject_default_collisions(custom, FEEDBACK_TYPES, "feedback_types")
        s[_SETTINGS_KEY_TYPES] = custom
    if "feedback_origins" in sent and body.feedback_origins is not None:
        custom = _custom_from_in_kv(body.feedback_origins)
        _reject_default_collisions(custom, DEFAULT_ORIGINS, "feedback_origins")
        s[_SETTINGS_KEY_ORIGINS] = custom

    org.settings = s  # reatribui p/ marcar o JSONB como sujo (padrão boards/campanha).
    await session.commit()
    return _config_payload(org)


@router.patch("/improvements/{improvement_id}")
async def update_improvement(
    improvement_id: str,
    body: ImprovementPatchIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Edita title/description/status de uma melhoria (parcial). Ao status virar
    'entregue', grava `delivered_at` (uma vez; não re-carimba se já estava entregue).
    422 em status inválido. Retorna o item com `feedback_count`.

    Esteira (Fase D, atrás de settings.esteira_enabled): quando este PATCH ENTREGA a
    melhoria (status=entregue, e ela ainda não estava entregue), TODOS os FeedbackItem
    vinculados (improvement_id == imp.id) com action_status não-terminal passam a
    'resolvido' num UPDATE em lote. Best-effort (não derruba o PATCH) e idempotente.
    Prepara o 'fechar o loop' — o aviso ao cliente segue manual via /notify."""
    org = await _get_org(session)
    sent = body.model_fields_set

    if "status" in sent and (body.status is None or body.status not in IMPROVEMENT_STATUSES):
        raise HTTPException(
            status_code=422,
            detail=f"status inválido: '{body.status}' (use {', '.join(IMPROVEMENT_STATUSES)})",
        )

    imp = await _get_improvement(session, org, improvement_id)

    # Esteira: este PATCH está ENTREGANDO a melhoria AGORA? (status=entregue e ainda
    # não estava entregue). Guardado p/ disparar o bulk-resolve pós-commit.
    entregou_agora = False
    if "title" in sent and body.title is not None:
        imp.title = body.title.strip()
    if "description" in sent:
        imp.description = (body.description.strip() or None) if body.description else None
    if "status" in sent and body.status is not None:
        was_delivered = imp.status == "entregue"
        imp.status = body.status
        if body.status == "entregue" and not was_delivered:
            imp.delivered_at = datetime.now(timezone.utc)
            entregou_agora = True
    if "cluster_id" in sent:
        imp.cluster_id = (
            await _resolve_cluster_id(session, org, body.cluster_id) if body.cluster_id else None
        )
    if "effort" in sent:
        imp.effort = _validate_effort(body.effort)
    if "target_date" in sent:
        imp.target_date = body.target_date

    await session.commit()

    # Esteira (Fase D, REGRA 2): melhoria entregue resolve os feedbacks vinculados.
    # UPDATE em lote: action_status='resolvido' em TODO FeedbackItem com improvement_id
    # == imp.id cujo action_status NÃO seja terminal (resolvido/descartado). Idempotente
    # e best-effort — nunca derruba o PATCH.
    if entregou_agora and settings.esteira_enabled:
        try:
            await session.execute(
                update(FeedbackItem)
                .where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.improvement_id == imp.id,
                    FeedbackItem.action_status.not_in(_FEEDBACK_TERMINAL_STATUSES),
                )
                .values(action_status="resolvido")
            )
            await session.commit()
        except Exception:  # noqa: BLE001 — esteira é best-effort; nunca derruba o PATCH
            logger.exception("esteira: falha ao resolver feedbacks da melhoria %s", imp.id)
            await session.rollback()
            # rollback EXPIRA `imp`; recarrega in-context p/ a serialização abaixo não
            # disparar lazy-load síncrono (MissingGreenlet/500).
            try:
                await session.refresh(imp)
            except Exception:  # noqa: BLE001
                pass

    count = await _feedback_count(session, org.id, imp.id)
    return _improvement_out(imp, count)


@router.post("/improvements/{improvement_id}/link")
async def link_feedbacks(
    improvement_id: str,
    body: ImprovementLinkIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Vincula feedbacks a esta melhoria (seta `improvement_id` em cada um). Valida
    que TODOS os feedbacks pertencem à org (404 se algum não existir/for de outra
    org). Idempotente: re-vincular o mesmo feedback não duplica. Retorna a melhoria
    com `feedback_count` atualizado e a lista de ids vinculados."""
    org = await _get_org(session)
    imp = await _get_improvement(session, org, improvement_id)

    try:
        fids = [uuid.UUID(f) for f in body.feedback_ids]
    except ValueError:
        raise HTTPException(status_code=422, detail="feedback_id inválido")
    fids = list(dict.fromkeys(fids))  # dedup preservando ordem

    feedbacks = (
        (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.id.in_(fids), FeedbackItem.organization_id == org.id
                )
            )
        )
        .scalars()
        .all()
    )
    if len(feedbacks) != len(fids):
        raise HTTPException(status_code=404, detail="um ou mais feedbacks não encontrados")

    for f in feedbacks:
        f.improvement_id = imp.id
    await session.commit()

    count = await _feedback_count(session, org.id, imp.id)
    return {
        "improvement": _improvement_out(imp, count),
        "linked": [str(f.id) for f in feedbacks],
    }


@router.post("/improvements/{improvement_id}/notify")
async def notify_improvement(
    improvement_id: str,
    confirm: bool = False,
    session: AsyncSession = Depends(get_session),
    messaging: IMessagingService = Depends(get_messaging),
) -> dict[str, Any]:
    """Avisa os clientes que pediram a melhoria ("você pediu, a gente fez").

    Destinatários = contatos dos feedbacks vinculados que têm whatsapp E opt_in,
    fora do cooldown. A mensagem é calorosa, curta e on-brand (sem travessão),
    personalizada com o tema mais citado nos feedbacks da melhoria.

    SALVAGUARDA (regra de ouro — WhatsApp real só com OK explícito):
    - DEFAULT (`confirm` ausente/false) = PREVIEW. Retorna o que SERIA enviado
      (`would_send`) e quem ficou de fora (`skipped`), SEM enviar nada e SEM
      gravar `notified_at`.
    - `?confirm=true` = ENVIA de verdade via o messaging, grava o outbound no
      transcript (alimenta o cooldown) e carimba `notified_at`. Mesmo com confirm,
      contatos sem opt_in / sem whatsapp / em cooldown continuam pulados.

    `skipped` traz `reason` por contato: 'sem_whatsapp' | 'sem_opt_in' | 'cooldown'.
    """
    org = await _get_org(session)
    imp = await _get_improvement(session, org, improvement_id)

    # Feedbacks vinculados (para o tema) + seus contatos distintos.
    feedbacks = (
        (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.improvement_id == imp.id,
                )
            )
        )
        .scalars()
        .all()
    )
    theme = _pick_theme(feedbacks)

    contact_ids = list(dict.fromkeys(f.contact_id for f in feedbacks if f.contact_id is not None))
    contacts: dict[uuid.UUID, Contact] = {}
    if contact_ids:
        rows = (
            (
                await session.execute(
                    select(Contact).where(
                        Contact.id.in_(contact_ids), Contact.organization_id == org.id
                    )
                )
            )
            .scalars()
            .all()
        )
        contacts = {c.id: c for c in rows}

    now = datetime.now(timezone.utc)
    cooldown = timedelta(hours=settings.notify_cooldown_hours) if settings.notify_cooldown_hours else None

    would_send: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for cid in contact_ids:
        contact = contacts.get(cid)
        if contact is None:
            continue
        base_info = {
            "contato_id": str(cid),
            "contato_nome": contact.name,
            "contato_whatsapp": contact.phone,
        }
        # Regra canônica de "sem WhatsApp" (idem ficha 360): validador — só celular BR
        # válido é alcançável. Fixo/grupo/inválido/placeholder/vazio são pulados no envio.
        if sem_whatsapp(contact.phone):
            skipped.append({**base_info, "reason": "sem_whatsapp"})
            continue
        if not contact.opt_in:
            skipped.append({**base_info, "reason": "sem_opt_in"})
            continue
        if cooldown is not None:
            last = _coerce_dt(await _recent_outbound_at(session, org.id, cid))
            if last is not None and (now - last) < cooldown:
                skipped.append({**base_info, "reason": "cooldown"})
                continue
        would_send.append({**base_info, "mensagem": _notify_message(contact, theme, org)})

    result: dict[str, Any] = {
        "improvement_id": str(imp.id),
        "preview": not confirm,
        "sent": False,
        "theme": theme,
        "would_send": would_send,
        "skipped": skipped,
    }

    if not confirm:
        # PREVIEW: não envia, não grava nada. Só mostra.
        return result

    # ENVIO REAL (confirmado): manda cada mensagem, grava outbound + notified_at.
    sent_count = 0
    for item in would_send:
        cid = uuid.UUID(item["contato_id"])
        contact = contacts[cid]
        await messaging.send_text(
            chat_id=contact.phone,
            text=item["mensagem"],
            session=settings.waha_session,
        )
        # Transcript (alimenta o cooldown e dá histórico ao humano).
        session.add(
            Message(
                organization_id=org.id,
                contact_id=cid,
                direction="outbound",
                body=item["mensagem"],
            )
        )
        sent_count += 1

    imp.notified_at = now
    await session.commit()

    result["sent"] = True
    result["sent_count"] = sent_count
    result["notified_em"] = imp.notified_at.isoformat() if imp.notified_at else None
    return result


# --- Disparo ------------------------------------------------------------------


class DispatchIn(BaseModel):
    contact_ids: list[str] = Field(min_length=1)


@router.post("/surveys/{survey_id}/dispatch")
async def dispatch_survey(
    survey_id: str,
    body: DispatchIn,
    session: AsyncSession = Depends(get_session),
    messaging: IMessagingService = Depends(get_messaging),
) -> dict[str, Any]:
    org = await _get_org(session)

    try:
        sid = uuid.UUID(survey_id)
        cids = [uuid.UUID(c) for c in body.contact_ids]
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    survey = (
        await session.execute(
            select(Survey).where(Survey.id == sid, Survey.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if survey is None:
        raise HTTPException(status_code=404, detail="pesquisa não encontrada")
    if survey.status != "active":
        raise HTTPException(status_code=409, detail=f"pesquisa está '{survey.status}', não 'active'")

    contacts = (
        (
            await session.execute(
                select(Contact).where(Contact.id.in_(cids), Contact.organization_id == org.id)
            )
        )
        .scalars()
        .all()
    )
    if len(contacts) != len(cids):
        raise HTTPException(status_code=404, detail="um ou mais contatos não encontrados")
    no_opt_in = [c.phone for c in contacts if not c.opt_in]
    if no_opt_in:
        raise HTTPException(status_code=409, detail=f"sem opt-in: {', '.join(no_opt_in)}")

    dispatcher = SurveyDispatcher(
        session, org.id, messaging, whatsapp_session=settings.waha_session, delay_seconds=1.0
    )
    run = await dispatcher.dispatch(survey, contacts)
    await session.commit()

    return {
        "run_id": str(run.id),
        "survey": survey.name,
        "dispatched_to": [{"phone": c.phone, "name": c.name} for c in contacts],
        "count": len(contacts),
    }
