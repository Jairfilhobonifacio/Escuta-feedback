"""Agregação dos números da semana para o digest (Voz do Cliente).

Uma query traz as responses das últimas 2 semanas (joins com survey/contact);
a contagem é feita em Python — volume pequeno (1 org / 1 semana) e lógica
testável sem depender de SQL específico de dialeto (roda igual em SQLite/PG).

A semana anterior entra só para o delta de NPS (a narrativa fica mais útil
quando diz "subiu/caiu X pontos").
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Contact
from app.models.survey import Survey, SurveyResponse, SurveyRun


@dataclass
class ChurnReason:
    contact_name: Optional[str]
    text: str
    sentiment: Optional[str]


@dataclass
class UrgentItem:
    contact_name: Optional[str]
    text: str
    themes: list[str]


@dataclass
class ThemeAggregate:
    """Agregado de UM tema no período: contagem + distribuição de sentimento."""
    theme: str
    count: int = 0
    sentiment_breakdown: dict = field(
        default_factory=lambda: {"positivo": 0, "neutro": 0, "negativo": 0}
    )


@dataclass
class DigestData:
    org_name: str
    period_days: int
    sent: int = 0
    answered: int = 0
    nps: Optional[int] = None
    nps_prev: Optional[int] = None
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    sentiment: dict = field(default_factory=lambda: {"positivo": 0, "neutro": 0, "negativo": 0})
    top_themes: list[tuple[str, int]] = field(default_factory=list)
    urgent: list[UrgentItem] = field(default_factory=list)
    churn: list[ChurnReason] = field(default_factory=list)

    @property
    def has_activity(self) -> bool:
        return self.sent > 0 or self.answered > 0

    @property
    def nps_delta(self) -> Optional[int]:
        if self.nps is None or self.nps_prev is None:
            return None
        return self.nps - self.nps_prev

    def as_dict(self) -> dict:
        return {
            "org_name": self.org_name,
            "period_days": self.period_days,
            "sent": self.sent,
            "answered": self.answered,
            "nps": self.nps,
            "nps_prev": self.nps_prev,
            "nps_delta": self.nps_delta,
            "promoters": self.promoters,
            "passives": self.passives,
            "detractors": self.detractors,
            "sentiment": self.sentiment,
            "top_themes": [{"theme": t, "count": c} for t, c in self.top_themes],
            "urgent": [{"contact": u.contact_name, "text": u.text, "themes": u.themes} for u in self.urgent],
            "churn": [{"contact": c.contact_name, "text": c.text, "sentiment": c.sentiment} for c in self.churn],
        }


def _nps_from_buckets(promo: int, passive: int, detr: int) -> Optional[int]:
    total = promo + passive + detr
    return round(((promo - detr) / total) * 100) if total else None


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Normaliza para UTC-aware. O SQLite (testes) devolve naive; o Postgres,
    aware — comparar os dois lança TypeError. Assumimos UTC quando faltar tz."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def aggregate(session: AsyncSession, organization_id: uuid.UUID, days: int = 7) -> DigestData:
    now = datetime.now(timezone.utc)
    cur_start = now - timedelta(days=days)
    prev_start = now - timedelta(days=2 * days)

    from app.models.core import Organization

    org = await session.get(Organization, organization_id)
    data = DigestData(org_name=org.name if org else "sua empresa", period_days=days)

    # Uma passada: tudo que teve atividade nas 2 semanas (enviado OU fechado).
    rows = (
        await session.execute(
            select(SurveyResponse, Survey.type, Contact.name)
            .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
            .join(Survey, Survey.id == SurveyRun.survey_id)
            .join(Contact, Contact.id == SurveyResponse.contact_id)
            .where(
                SurveyResponse.organization_id == organization_id,
                (SurveyResponse.sent_at >= prev_start) | (SurveyResponse.closed_at >= prev_start),
            )
        )
    ).all()

    cur_p = cur_pa = cur_d = 0
    prev_p = prev_pa = prev_d = 0
    theme_counter: Counter = Counter()

    for resp, stype, contact_name in rows:
        answered_at = _aware(resp.answered_at or resp.closed_at)
        sent_at = _aware(resp.sent_at)
        closed_at = _aware(resp.closed_at)

        # Enviadas / respondidas na semana atual
        if sent_at is not None and sent_at >= cur_start:
            data.sent += 1
        if answered_at is not None and answered_at >= cur_start and resp.answer_score is not None:
            data.answered += 1

        # NPS por bucket — semana atual e anterior (para o delta)
        if resp.nps_bucket and answered_at is not None:
            if answered_at >= cur_start:
                cur_p += resp.nps_bucket == "promoter"
                cur_pa += resp.nps_bucket == "passive"
                cur_d += resp.nps_bucket == "detractor"
            elif prev_start <= answered_at < cur_start:
                prev_p += resp.nps_bucket == "promoter"
                prev_pa += resp.nps_bucket == "passive"
                prev_d += resp.nps_bucket == "detractor"

        # Demais sinais: só do que FECHOU na semana atual
        if closed_at is None or closed_at < cur_start:
            continue

        if resp.sentiment in data.sentiment:
            data.sentiment[resp.sentiment] += 1

        for t in (resp.themes or []):
            theme_counter[str(t)] += 1

        urgency = (resp.ai_meta or {}).get("urgency")
        if urgency == "alta" and resp.answer_text:
            data.urgent.append(
                UrgentItem(contact_name=contact_name, text=resp.answer_text, themes=list(resp.themes or []))
            )

        if stype == "exit" and resp.answer_text:
            data.churn.append(
                ChurnReason(contact_name=contact_name, text=resp.answer_text, sentiment=resp.sentiment)
            )

    data.promoters, data.passives, data.detractors = cur_p, cur_pa, cur_d
    data.nps = _nps_from_buckets(cur_p, cur_pa, cur_d)
    data.nps_prev = _nps_from_buckets(prev_p, prev_pa, prev_d)
    data.top_themes = theme_counter.most_common(5)
    return data


async def aggregate_themes(
    session: AsyncSession, organization_id: uuid.UUID, days: int = 7
) -> list[ThemeAggregate]:
    """Clustering v1: agrega os temas (já normalizados pela IA) de SurveyResponse +
    FeedbackItem no período, com distribuição de sentimento. Lógica em Python
    (filtro de tempo via _aware, igual ao aggregate, p/ rodar em SQLite e PG).

    v2 (futuro): clustering semântico (pgvector) p/ juntar sinônimos (preço/valor/custo).
    """
    from app.models.feedback import FeedbackItem

    cur_start = datetime.now(timezone.utc) - timedelta(days=days)

    survey_rows = (
        await session.execute(
            select(SurveyResponse.themes, SurveyResponse.sentiment, SurveyResponse.closed_at).where(
                SurveyResponse.organization_id == organization_id,
                SurveyResponse.themes.is_not(None),
            )
        )
    ).all()
    feedback_rows = (
        await session.execute(
            select(FeedbackItem.themes, FeedbackItem.sentiment, FeedbackItem.created_at).where(
                FeedbackItem.organization_id == organization_id,
                FeedbackItem.themes.is_not(None),
            )
        )
    ).all()

    by_theme: dict[str, ThemeAggregate] = {}
    for themes_list, sentiment, ts in [*survey_rows, *feedback_rows]:
        ts = _aware(ts)
        if ts is None or ts < cur_start:
            continue
        for theme in (themes_list or []):
            key = str(theme).strip().lower()
            if not key:
                continue
            agg = by_theme.get(key)
            if agg is None:
                agg = by_theme[key] = ThemeAggregate(theme=key)
            agg.count += 1
            if sentiment in agg.sentiment_breakdown:
                agg.sentiment_breakdown[sentiment] += 1

    return sorted(by_theme.values(), key=lambda a: a.count, reverse=True)[:10]
