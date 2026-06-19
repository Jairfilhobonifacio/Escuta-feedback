"""API de AGREGAÇÃO da Central de Feedbacks — visão consolidada p/ apresentação.

Camada SÓ-LEITURA: lê e agrega o que as outras camadas já gravaram (survey_responses,
feedback_items, contacts.profile_data) numa visão de cima — feita para a tela de
apresentação (Felipe -> Lucas). Não cria/edita nada, não dispara WhatsApp.

Mesma filosofia do admin.py/campanha.py: a org é resolvida pelo slug default via
`_get_org` (multi-tenant pleno fica para quando houver auth), TODA query filtra por
`organization_id == org.id`, e o router é montado com prefixo /api no main.py — logo
as rotas são declaradas SEM o /api.

Definições canônicas (reaproveitadas da campanha win-back, p/ os números baterem):
- NPS: une as DUAS fontes de nota — `survey_responses.answer_score` (coletado pelo
  Escuta no WhatsApp/in-app) E `feedback_items` type='nps' com `score` (sinal
  ingerido de fonte externa, ex.: NPS in-app do Bizzu). A média é sobre as duas.
- abordado: o operador JÁ falou com o cliente — selo 'contatado' OU
  `profile_data["abordagens"]` não-vazio OU algum FeedbackItem.abordado==True.
- respondeu: selo 'respondeu' OU o contato respondeu uma pesquisa (SurveyResponse
  'closed'). Ter FeedbackItem ingerido NÃO conta. responderam ⊆ abordados.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _get_org
from app.api.campanha import (
    SELO_CONTATADO,
    SELO_RESPONDEU,
    _abordagens_do_contato,
    _selos_do_contato,
)
from app.db import get_session
from app.models.core import Contact
from app.models.feedback import FeedbackItem
from app.models.survey import SurveyResponse

router = APIRouter(tags=["central"])

# Estados de assinatura (partner.subscription.state) por segmento de apresentação.
_STATE_CHURN = "cancelled"
_STATE_ATIVO = "active_paying"


def _partner_state(contact: Contact) -> str | None:
    """partner.subscription.state do snapshot (best-effort), ex.: 'cancelled'."""
    sub = (((contact.profile_data or {}).get("partner") or {}).get("subscription")) or {}
    state = sub.get("state")
    return str(state) if state else None


def _nps_bucket_of_score(score: int | None) -> str | None:
    """Faixa NPS canônica a partir do score 0-10: detractor/passive/promoter."""
    if score is None:
        return None
    if score <= 6:
        return "detractor"
    if score <= 8:
        return "passive"
    return "promoter"


async def _nps_rows(session: AsyncSession, org_id: uuid.UUID) -> list[dict[str, Any]]:
    """TODAS as notas NPS da org, das DUAS fontes, normalizadas e ordenadas (desc).

    Cada linha: contact_id, score, bucket, motivo, fonte ('whatsapp'|'in_app'|
    feedback source), em (iso), e o nome/telefone juntados quando há contato.
    Fonte do bucket: o gravado (survey/feedback) com fallback derivado do score.
    """
    # Fonte 1 — survey_responses respondidas (coletadas pelo Escuta).
    sr_rows = (
        await session.execute(
            select(SurveyResponse, Contact)
            .outerjoin(Contact, Contact.id == SurveyResponse.contact_id)
            .where(
                SurveyResponse.organization_id == org_id,
                SurveyResponse.answer_score.is_not(None),
            )
        )
    ).all()

    # Fonte 2 — feedback_items type='nps' com score (sinal ingerido externo).
    fi_rows = (
        await session.execute(
            select(FeedbackItem, Contact)
            .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
            .where(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.type == "nps",
                FeedbackItem.score.is_not(None),
            )
        )
    ).all()

    out: list[dict[str, Any]] = []
    for r, c in sr_rows:
        when = r.answered_at or r.closed_at or r.sent_at
        out.append(
            {
                "contact_id": str(r.contact_id) if r.contact_id else None,
                "nome": c.name if c else None,
                "telefone": c.phone if c else None,
                "score": r.answer_score,
                "bucket": r.nps_bucket or _nps_bucket_of_score(r.answer_score),
                "motivo": r.answer_text,
                "fonte": r.source or "whatsapp",
                "em": when.isoformat() if when else None,
            }
        )
    for f, c in fi_rows:
        when = f.occurred_at or f.created_at
        out.append(
            {
                "contact_id": str(f.contact_id) if f.contact_id else None,
                "nome": c.name if c else None,
                "telefone": c.phone if c else None,
                "score": f.score,
                "bucket": f.nps_bucket or _nps_bucket_of_score(f.score),
                "motivo": f.text,
                "fonte": f.source,
                "em": when.isoformat() if when else None,
            }
        )
    # Mais recentes primeiro; linhas sem data ('' ) por último.
    out.sort(key=lambda x: x["em"] or "", reverse=True)
    return out


def _media(scores: list[int]) -> float | None:
    """Média das notas arredondada a 1 casa, ou None quando não há nota."""
    return round(sum(scores) / len(scores), 1) if scores else None


@router.get("/central/overview")
async def central_overview(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Visão consolidada da Central p/ apresentação: NPS + feedbacks + abordagem +
    segmentos (churn x ativos). Tudo SÓ-LEITURA, escopado por organização.

    Blocos:
    - nps: das DUAS fontes (survey_responses respondidas + feedback_items nps com
      score). `deram` = quantas notas; `media` (1 casa); promotores/neutros/detratores
      por bucket; `sem_resposta` = contatos da org sem NENHUMA nota.
    - feedbacks: TODOS os feedback_items da org — total, com_texto, por_fonte
      (source) e por_sentimento (positivo/neutro/negativo/sem).
    - abordagem: sobre TODOS os contatos da org — abordados (falou com o cliente),
      responderam (cliente devolveu sinal) e nao_responderam (abordados - responderam).
    - segmentos: o MESMO recorte de abordagem filtrado por estado da assinatura:
      churn (state='cancelled') e ativos (state='active_paying').
    """
    org = await _get_org(session)

    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars()
        .all()
    )

    # --- NPS (duas fontes) ---------------------------------------------------
    nps_rows = await _nps_rows(session, org.id)
    scores = [r["score"] for r in nps_rows if r["score"] is not None]
    promotores = sum(1 for r in nps_rows if r["bucket"] == "promoter")
    neutros = sum(1 for r in nps_rows if r["bucket"] == "passive")
    detratores = sum(1 for r in nps_rows if r["bucket"] == "detractor")
    # "Sem resposta" = contatos da org que não deram NENHUMA nota (nas duas fontes).
    com_nota_ids = {r["contact_id"] for r in nps_rows if r["contact_id"]}
    sem_resposta = sum(1 for c in contacts if str(c.id) not in com_nota_ids)

    nps_block = {
        "deram": len(scores),
        "media": _media(scores),
        "promotores": promotores,
        "neutros": neutros,
        "detratores": detratores,
        "sem_resposta": sem_resposta,
    }

    # --- Feedbacks escritos/ingeridos ---------------------------------------
    feedbacks = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.organization_id == org.id)))
        .scalars()
        .all()
    )
    por_fonte: dict[str, int] = {}
    por_sentimento = {"positivo": 0, "neutro": 0, "negativo": 0, "sem": 0}
    com_texto = 0
    for f in feedbacks:
        por_fonte[f.source] = por_fonte.get(f.source, 0) + 1
        if (f.text or "").strip():
            com_texto += 1
        if f.sentiment in ("positivo", "neutro", "negativo"):
            por_sentimento[f.sentiment] += 1
        else:
            por_sentimento["sem"] += 1

    feedbacks_block = {
        "total": len(feedbacks),
        "com_texto": com_texto,
        "por_fonte": por_fonte,
        "por_sentimento": por_sentimento,
    }

    # --- Abordagem (geral + segmentos) --------------------------------------
    # Contatos com algum FeedbackItem.abordado==True (entra na regra de "abordado").
    contatos_abordados_fb: set[uuid.UUID] = {
        f.contact_id for f in feedbacks if f.contact_id is not None and f.abordado
    }
    # Contatos com alguma SurveyResponse 'closed' (respondeu via Escuta).
    closed_contact_ids = set(
        (
            await session.execute(
                select(SurveyResponse.contact_id).where(
                    SurveyResponse.organization_id == org.id,
                    SurveyResponse.status == "closed",
                )
            )
        )
        .scalars()
        .all()
    )

    def _abordado(c: Contact) -> bool:
        selos = set(_selos_do_contato(c))
        return (
            SELO_CONTATADO in selos
            or bool(_abordagens_do_contato(c))
            or c.id in contatos_abordados_fb
        )

    def _respondeu(c: Contact) -> bool:
        # "Respondeu" = devolveu sinal À ABORDAGEM: selo 'respondeu' (marcado pelo
        # operador) OU respondeu uma pesquisa do Escuta (SurveyResponse 'closed').
        # NÃO conta ter FeedbackItem ingerido (NPS in-app/churn code da Bizzu não é
        # resposta a uma abordagem) — senão "responderam" infla para == abordados.
        selos = set(_selos_do_contato(c))
        return SELO_RESPONDEU in selos or c.id in closed_contact_ids

    def _recorte(pool: list[Contact]) -> dict[str, int]:
        abordados = 0
        responderam = 0
        for c in pool:
            ab = _abordado(c)
            # responderam ⊆ abordados: quem respondeu conta como abordado (a tela
            # nunca mostra "respondeu > abordado"). nao_responderam = abordados - resp.
            re_ = _respondeu(c)
            if ab or re_:
                abordados += 1
            if re_:
                responderam += 1
        return {
            "total": len(pool),
            "abordados": abordados,
            "responderam": responderam,
            "nao_responderam": abordados - responderam,
        }

    abordagem_geral = _recorte(contacts)
    churn_pool = [c for c in contacts if _partner_state(c) == _STATE_CHURN]
    ativos_pool = [c for c in contacts if _partner_state(c) == _STATE_ATIVO]

    abordagem_block = {
        "contatos_total": abordagem_geral["total"],
        "abordados": abordagem_geral["abordados"],
        "responderam": abordagem_geral["responderam"],
        "nao_responderam": abordagem_geral["nao_responderam"],
    }

    return {
        "nps": nps_block,
        "feedbacks": feedbacks_block,
        "abordagem": abordagem_block,
        "segmentos": {
            "churn": {"rotulo": "Cancelaram", **_recorte(churn_pool)},
            "ativos": {"rotulo": "Ativos", **_recorte(ativos_pool)},
        },
    }


@router.get("/central/nps")
async def central_nps(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """TODAS as notas NPS da org (duas fontes), ordenadas por data desc.

    `media` = média (1 casa) sobre todas as notas. Cada item: contact_id, nome,
    telefone, score, bucket, motivo (answer_text/text), fonte e em (iso)."""
    org = await _get_org(session)
    rows = await _nps_rows(session, org.id)
    scores = [r["score"] for r in rows if r["score"] is not None]
    return {"media": _media(scores), "items": rows}


@router.get("/central/feedbacks")
async def central_feedbacks(
    sentimento: str | None = None,
    fonte: str | None = None,
    abordado: bool | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Feedbacks ESCRITOS da org (text não-vazio), filtráveis p/ a apresentação.

    Filtros (todos opcionais, no-op quando ausentes):
    - sentimento: 'positivo' | 'neutro' | 'negativo' (igualdade na coluna).
    - fonte: source do feedback ('whatsapp' | 'bizzu_app' | 'bizzu_billing' | ...).
    - abordado: true/false (flag do item).

    Cada item: contato_id, nome, fonte, sentimento, tipo, texto, abordado, em (iso),
    estado (partner.subscription.state do contato)."""
    org = await _get_org(session)

    stmt = (
        select(FeedbackItem, Contact)
        .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
        .where(
            FeedbackItem.organization_id == org.id,
            # "Escrito" = tem texto não-nulo e não-vazio (após trim no Python; aqui
            # garantimos não-nulo no SQL e refinamos abaixo p/ excluir só-espaços).
            FeedbackItem.text.is_not(None),
        )
    )
    if sentimento:
        stmt = stmt.where(FeedbackItem.sentiment == sentimento)
    if fonte:
        stmt = stmt.where(FeedbackItem.source == fonte)
    if abordado is not None:
        stmt = stmt.where(FeedbackItem.abordado == abordado)

    rows = (await session.execute(stmt)).all()

    items: list[dict[str, Any]] = []
    for f, c in rows:
        texto = (f.text or "").strip()
        if not texto:  # exclui textos só com espaços (text='' / '   ').
            continue
        when = f.occurred_at or f.created_at
        items.append(
            {
                "contato_id": str(f.contact_id) if f.contact_id else None,
                "nome": c.name if c else None,
                "fonte": f.source,
                "sentimento": f.sentiment,
                "tipo": f.type,
                "texto": texto,
                "abordado": f.abordado,
                "em": when.isoformat() if when else None,
                "estado": _partner_state(c) if c else None,
            }
        )
    # Mais recentes primeiro (consistente com /central/nps).
    items.sort(key=lambda x: x["em"] or "", reverse=True)
    return {"total": len(items), "items": items}
