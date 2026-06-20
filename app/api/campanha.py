"""API da CAMADA DE CAMPANHA WIN-BACK.

Tudo sem migration e sem tocar o schema: persiste SOMENTE em JSON já existente.
- Catálogo de selos: `Organization.settings["selos_catalogo"]` = lista de {nome, cor}.
- Selos aplicados a um contato: `Contact.profile_data["selos"]` = lista de nomes.
- Histórico de abordagens 1:1: `Contact.profile_data["abordagens"]` = lista de
  {at(iso), canal, mensagem, oferta, status, por}.

Padrão obrigatório COPIA-EDITA-REATRIBUI para marcar o JSONB como sujo (sem isso o
SQLAlchemy não detecta a mutação in-place e o commit não persiste a mudança):

    p = dict(contact.profile_data or {})
    p["selos"] = nova_lista
    contact.profile_data = p

Mesma filosofia do admin.py: org única resolvida pelo slug default (`_get_org`),
todos os endpoints filtram por `organization_id`. O router é montado com prefixo
/api no main.py, então as rotas são declaradas SEM o /api.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _get_org
from app.db import get_session
from app.domain.contacts.whatsapp import alcance as _wa_alcance
from app.domain.contacts.whatsapp import sem_whatsapp as _wa_sem
from app.domain.survey.parsers import nps_bucket
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem

router = APIRouter(tags=["campanha"])

# Cor default de um selo recém-criado (token --indigo do design system do painel).
_COR_DEFAULT = "#6366f1"

# Canais aceitos numa abordagem (validado só por presença/string; vocabulário pode
# crescer, sem CHECK no banco — mesma filosofia de ACTION_STATUSES do admin.py).
_CANAIS = ("whatsapp", "ligacao", "email", "presencial", "outro")

# Selos "de sistema" da campanha win-back (usados pelas stats do funil). São selos
# comuns no catálogo — estas constantes só dão nome às etapas computadas.
SELO_CONTATADO = "contatado"
SELO_RESPONDEU = "respondeu"
SELO_CORTESIA = "cortesia"
SELO_REATIVOU = "reativou"


# --- helpers de catálogo/aplicação de selos (copia-edita-reatribui) -----------


def _catalogo(org: Organization) -> list[dict[str, Any]]:
    """Catálogo de selos da org (lista de {nome, cor}), tolerante a None/sujeira."""
    raw = (org.settings or {}).get("selos_catalogo")
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict) and it.get("nome"):
                out.append({"nome": str(it["nome"]), "cor": str(it.get("cor") or _COR_DEFAULT)})
    return out


def _set_catalogo(org: Organization, catalogo: list[dict[str, Any]]) -> None:
    """Reatribui o catálogo no settings (marca o JSONB como sujo)."""
    s = dict(org.settings or {})
    s["selos_catalogo"] = catalogo
    org.settings = s


def _selos_do_contato(contact: Contact) -> list[str]:
    """Selos aplicados ao contato (lista de nomes), tolerante a None/sujeira."""
    raw = (contact.profile_data or {}).get("selos")
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    return []


def _set_selos_do_contato(contact: Contact, selos: list[str]) -> None:
    """Reatribui os selos no profile_data (marca o JSONB como sujo)."""
    p = dict(contact.profile_data or {})
    p["selos"] = selos
    contact.profile_data = p


# Origens válidas de um evento de selo (campo `origem` no log). Vocabulário fechado
# por contrato (≠ ACTION_STATUSES, que é aberto) — quem grava no log DEVE usar uma
# destas. Não há CHECK no banco; a constante é a fonte da verdade do contrato.
SELO_ORIGENS = (
    "manual",          # operador no painel (POST/DELETE /selos)
    "whatsapp_enviado",  # envio 1:1 saiu (whatsapp.py)
    "abordagem",       # registrar abordagem (add_outreach)
    "form",            # import de formulário (forms_import)
    "inbound",         # cliente respondeu no WhatsApp (webhook.py)
    "regra",           # automação/playbook
    "ia",              # decisão do agente/LLM
)


def _selos_log_do_contato(contact: Contact) -> list[dict[str, Any]]:
    """Log de eventos de selo do contato (append-only), tolerante a None/sujeira."""
    raw = (contact.profile_data or {}).get("selos_log")
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    return []


def _append_selo_log(
    contact: Contact, *, selo: str, acao: str, origem: str, por: str | None
) -> None:
    """Faz append de UM evento no log `profile_data["selos_log"]`.

    Formato EXATO do evento (contrato com central.py/admin.py/frontend):
    `{"selo": str, "acao": "aplicado"|"removido", "at": <ISO8601 UTC>, "por": str|None,
    "origem": str}`. Copia-edita-reatribui o profile_data inteiro p/ marcar o JSONB sujo.
    """
    evento = {
        "selo": selo,
        "acao": acao,
        "at": datetime.now(timezone.utc).isoformat(),
        "por": por,
        "origem": origem,
    }
    p = dict(contact.profile_data or {})
    p["selos_log"] = [*_selos_log_do_contato(contact), evento]
    contact.profile_data = p


def aplicar_selo(
    contact: Contact,
    nome: str,
    *,
    origem: str,
    por: str | None = None,
    org: Organization | None = None,
) -> bool:
    """Aplica um selo a um contato, idempotente, registrando no log COM origem.

    - Idempotente: se o selo JÁ estava aplicado, NÃO faz nada e NÃO registra evento
      (não duplica no log). Retorna False nesse caso, True quando de fato aplicou.
    - Quando `org` é passado, garante o selo no catálogo (`_upsert_catalogo`) — assim
      o board e os stats concordam. Sem `org`, só mexe no contato (caller já cuidou
      do catálogo, ou não há org à mão — ex.: inbound em sessão multi-tenant).
    - Marca o JSONB sujo via copia-edita-reatribui (em `_set_selos_do_contato` e no
      append do log). NÃO faz commit — o caller é dono da transação.
    """
    if org is not None:
        _upsert_catalogo(org, nome, None)
    selos = _selos_do_contato(contact)
    if nome in selos:
        return False  # já estava no estado-alvo: idempotente, sem evento no log.
    _set_selos_do_contato(contact, [*selos, nome])
    _append_selo_log(contact, selo=nome, acao="aplicado", origem=origem, por=por)
    return True


def remover_selo(
    contact: Contact,
    nome: str,
    *,
    origem: str,
    por: str | None = None,
) -> bool:
    """Remove um selo de um contato, idempotente, registrando no log COM origem.

    - Idempotente: se o selo NÃO estava aplicado, NÃO faz nada e NÃO registra evento.
      Retorna False nesse caso, True quando de fato removeu.
    - NÃO mexe no catálogo (remover de um contato ≠ tirar do catálogo da org).
    - Marca o JSONB sujo via copia-edita-reatribui. NÃO faz commit.
    """
    selos = _selos_do_contato(contact)
    if nome not in selos:
        return False  # já estava no estado-alvo: idempotente, sem evento no log.
    _set_selos_do_contato(contact, [s for s in selos if s != nome])
    _append_selo_log(contact, selo=nome, acao="removido", origem=origem, por=por)
    return True


def _abordagens_do_contato(contact: Contact) -> list[dict[str, Any]]:
    """Histórico de abordagens do contato, tolerante a None/sujeira."""
    raw = (contact.profile_data or {}).get("abordagens")
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, dict)]
    return []


def _set_abordagens_do_contato(contact: Contact, abordagens: list[dict[str, Any]]) -> None:
    """Reatribui as abordagens no profile_data (marca o JSONB como sujo)."""
    p = dict(contact.profile_data or {})
    p["abordagens"] = abordagens
    contact.profile_data = p


def _upsert_catalogo(org: Organization, nome: str, cor: str | None) -> None:
    """Insere/atualiza um selo no catálogo (idempotente por nome; cor atualiza)."""
    catalogo = _catalogo(org)
    for it in catalogo:
        if it["nome"] == nome:
            if cor:
                it["cor"] = cor
            _set_catalogo(org, catalogo)
            return
    catalogo.append({"nome": nome, "cor": cor or _COR_DEFAULT})
    _set_catalogo(org, catalogo)


async def _get_contact(session: AsyncSession, org: Organization, contact_id: str) -> Contact:
    """Carrega um contato da org por id (422 id inválido, 404 inexistente)."""
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
    return contact


# --- SELOS: catálogo + uso ----------------------------------------------------


class SeloIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cor: str | None = Field(default=None, max_length=32)


class SeloApplyIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cor: str | None = Field(default=None, max_length=32)


@router.get("/selos")
async def list_selos(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Catálogo de selos da org + uso (quantos contatos têm cada selo).

    Retorno: {"catalogo": [{"nome","cor"}], "uso": {"<nome>": <n_contatos>}}.
    O uso conta TODOS os contatos da org (não só os que estão no catálogo) — um
    selo aplicado mas removido do catálogo ainda aparece no uso com sua contagem.
    """
    org = await _get_org(session)
    catalogo = _catalogo(org)

    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars()
        .all()
    )
    uso: dict[str, int] = {}
    for c in contacts:
        for nome in _selos_do_contato(c):
            uso[nome] = uso.get(nome, 0) + 1

    return {"catalogo": catalogo, "uso": uso}


@router.post("/selos", status_code=201)
async def create_selo(body: SeloIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Upsert de um selo no catálogo (idempotente por nome; cor atualiza). 201."""
    org = await _get_org(session)
    nome = body.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome do selo não pode ser vazio")
    cor = (body.cor or "").strip() or None
    _upsert_catalogo(org, nome, cor)
    await session.commit()
    return {"catalogo": _catalogo(org)}


@router.delete("/selos/{nome}", status_code=200)
async def delete_selo(nome: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Remove o selo do catálogo E de TODOS os contatos que o têm."""
    org = await _get_org(session)
    alvo = (nome or "").strip()

    # Remove do catálogo (se estiver lá).
    catalogo = [it for it in _catalogo(org) if it["nome"] != alvo]
    _set_catalogo(org, catalogo)

    # Remove de todos os contatos que o aplicaram.
    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars()
        .all()
    )
    removidos = 0
    for c in contacts:
        selos = _selos_do_contato(c)
        if alvo in selos:
            _set_selos_do_contato(c, [s for s in selos if s != alvo])
            removidos += 1

    await session.commit()
    return {"removido": alvo, "contatos_afetados": removidos, "catalogo": catalogo}


@router.post("/contacts/{contact_id}/selos", status_code=201)
async def apply_selo(
    contact_id: str, body: SeloApplyIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Aplica um selo a um contato (cria no catálogo se for novo; idempotente)."""
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)
    nome = body.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome do selo não pode ser vazio")
    cor = (body.cor or "").strip() or None

    # Garante o selo no catálogo (cria/atualiza cor) — `aplicar_selo` faz upsert sem
    # cor, então fazemos o upsert COM a cor aqui (manual pode definir cor).
    _upsert_catalogo(org, nome, cor)

    # Camada com LOG: aplica + registra origem="manual" (idempotente).
    aplicar_selo(contact, nome, origem="manual")

    await session.commit()
    return {"contato_id": str(contact.id), "selos": _selos_do_contato(contact)}


@router.delete("/contacts/{contact_id}/selos/{nome}", status_code=200)
async def remove_selo(
    contact_id: str, nome: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Remove o selo daquele contato (não mexe no catálogo)."""
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)
    alvo = (nome or "").strip()

    # Camada com LOG: remove + registra origem="manual" (idempotente; só commita se
    # de fato removeu, mantendo o comportamento anterior de não commitar à toa).
    if remover_selo(contact, alvo, origem="manual"):
        await session.commit()

    return {"contato_id": str(contact.id), "selos": _selos_do_contato(contact)}


# --- OUTREACH: histórico de abordagens 1:1 ------------------------------------


class OutreachIn(BaseModel):
    canal: str = Field(min_length=1, max_length=40)
    mensagem: str | None = Field(default=None, max_length=4000)
    oferta: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=40)
    por: str | None = Field(default=None, max_length=120)


@router.post("/contacts/{contact_id}/outreach", status_code=201)
async def add_outreach(
    contact_id: str, body: OutreachIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Registra uma abordagem 1:1 a um contato.

    Faz append na lista `profile_data["abordagens"]`, aplica o selo 'contatado'
    (idempotente, p/ o board de clientes e os stats baterem) E marca `abordado=True` +
    `abordado_em` (quando ainda nulo) em TODOS os FeedbackItem do contato — assim o
    inbox de monitoramento reflete que o cliente já foi contatado nesta campanha.
    201 com {"abordagem": {...}}.
    """
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)

    canal = body.canal.strip()
    if not canal:
        raise HTTPException(status_code=422, detail="canal não pode ser vazio")

    now = datetime.now(timezone.utc)
    abordagem = {
        "at": now.isoformat(),
        "canal": canal,
        "mensagem": (body.mensagem.strip() or None) if body.mensagem else None,
        "oferta": (body.oferta.strip() or None) if body.oferta else None,
        "status": (body.status.strip() or None) if body.status else None,
        "por": (body.por.strip() or None) if body.por else None,
    }

    abordagens = [*_abordagens_do_contato(contact), abordagem]
    _set_abordagens_do_contato(contact, abordagens)

    # Aplica o selo 'contatado' (idempotente) + garante no catálogo: assim o board de
    # clientes (coluna "Contatado") e os stats concordam — registrar uma abordagem já
    # coloca o cliente na coluna, sem precisar marcar o selo à mão. Camada com LOG,
    # origem="abordagem" (registra `por` da abordagem quando informado).
    aplicar_selo(contact, SELO_CONTATADO, origem="abordagem", por=abordagem.get("por"), org=org)

    # Marca abordado=True + abordado_em (se nulo) em TODOS os feedbacks do contato.
    feedbacks = (
        (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.contact_id == contact.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for f in feedbacks:
        f.abordado = True
        if f.abordado_em is None:
            f.abordado_em = now

    await session.commit()
    return {"abordagem": abordagem}


@router.get("/contacts/{contact_id}/outreach")
async def list_outreach(
    contact_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Lista as abordagens do contato, mais recente primeiro (por `at` desc)."""
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)
    abordagens = list(_abordagens_do_contato(contact))
    abordagens.sort(key=lambda a: a.get("at") or "", reverse=True)
    return abordagens


# --- CAMPANHA STATS -----------------------------------------------------------


# Estados de assinatura (snapshot partner) que JÁ são churn por si só — o cliente
# perdeu/está perdendo o acesso. Espelha a doc da API de Clientes (api-clientes-
# partner.md §1): 'cancelled' = cancelado seco; 'paid_without_access' = pagou mas
# sem acesso (borda anômala que na prática é perda de cliente).
_CHURN_STATES = ("cancelled", "paid_without_access")


def _subscription_state(contact: Contact) -> str | None:
    """state da assinatura no snapshot partner (`partner.subscription.state`), ou None."""
    sub = (((contact.profile_data or {}).get("partner") or {}).get("subscription") or {})
    state = sub.get("state")
    return str(state) if state else None


def _sem_whatsapp(contact: Contact) -> bool:
    """Contato é SEM WhatsApp? Delega ao validador real (app.domain.contacts.whatsapp).

    SEM WhatsApp = NÃO é celular BR válido: fixo, ID de grupo, placeholder 'nowa-',
    vazio ou número malformado. Só celular BR válido é alcançável no WhatsApp — a
    heurística antiga ("vazio ou 'nowa-'") contava fixo/grupo/inválido como "com
    WhatsApp", o que era dado incorreto.
    """
    return _wa_sem(contact.phone)


def _is_churn(contact: Contact, feedbacks: list[FeedbackItem]) -> bool:
    """Contato é do universo de churn da campanha?

    True se QUALQUER um:
    - subscription.state do snapshot ∈ {cancelled, paid_without_access};
    - o perfil do snapshot (`partner.profile`) começa com 'churn';
    - tem ALGUM FeedbackItem.type=='churn'.
    """
    if _subscription_state(contact) in _CHURN_STATES:
        return True
    perfil = (((contact.profile_data or {}).get("partner") or {}).get("profile") or "")
    if isinstance(perfil, str) and perfil.lower().startswith("churn"):
        return True
    return any(f.type == "churn" for f in feedbacks)


@router.get("/campanha/stats")
async def campanha_stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Painel da campanha win-back: universo, funil e insights.

    `universo` = contatos da org que são churn (subscription.state ∈ {cancelled,
    paid_without_access} OU perfil do snapshot começando com 'churn' OU algum
    FeedbackItem.type=='churn'). Recortes do universo (via validador real em
    app.domain.contacts.whatsapp, pelo FORMATO do número):
    - `com_whatsapp`: celular BR VÁLIDO (alcançável no WhatsApp) — NÃO basta "ter
      telefone": fixo, ID de grupo, placeholder 'nowa-' e número malformado NÃO contam.
    - `sem_whatsapp`: todo o resto (fixo, grupo, 'nowa-', vazio ou inválido) — winback
      fora do WhatsApp. `com_whatsapp` + `sem_whatsapp` == `universo`.
    - `por_alcance`: contagem do universo por bucket de alcance (whatsapp, so_email,
      fixo, grupo, sem_contato, invalido) — só os buckets com contagem > 0. A soma de
      todos os buckets == `universo`; e por_alcance['whatsapp'] == `com_whatsapp`.

    A partir do universo:
    - contatados: algum FeedbackItem.abordado==True OU selo 'contatado' OU
      `abordagens` não-vazio.
    - responderam: selo 'respondeu' OU algum FeedbackItem.source=='forms'.
    - cortesia: selo 'cortesia'. reativaram: selo 'reativou'.
    - faltam: max(0, universo - contatados).
    - por_canal: contagem das abordagens (de TODO o universo) por canal.
    - por_selo: nº de contatos do universo por selo.
    - funil: etapas [a contatar, contatado, respondeu, cortesia, reativou] c/ counts.
    - insights: top ~8 temas dos FeedbackItem do universo, com count e nº de negativos.
    """
    org = await _get_org(session)

    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars()
        .all()
    )
    by_contact: dict[uuid.UUID, Contact] = {c.id: c for c in contacts}

    feedbacks = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.organization_id == org.id)))
        .scalars()
        .all()
    )
    fb_by_contact: dict[uuid.UUID, list[FeedbackItem]] = {}
    for f in feedbacks:
        if f.contact_id is not None:
            fb_by_contact.setdefault(f.contact_id, []).append(f)

    # Universo de churn.
    universo_ids: list[uuid.UUID] = [
        c.id for c in contacts if _is_churn(c, fb_by_contact.get(c.id, []))
    ]

    contatados = 0
    responderam = 0
    cortesia = 0
    reativaram = 0
    com_whatsapp = 0
    sem_whatsapp = 0
    por_alcance: dict[str, int] = {}
    por_canal: dict[str, int] = {}
    por_selo: dict[str, int] = {}
    tema_count: dict[str, int] = {}
    tema_neg: dict[str, int] = {}

    for cid in universo_ids:
        c = by_contact[cid]
        fbs = fb_by_contact.get(cid, [])
        selos = set(_selos_do_contato(c))
        abordagens = _abordagens_do_contato(c)

        # Recorte por alcance: WhatsApp real (celular BR válido) vs. resto.
        if _sem_whatsapp(c):
            sem_whatsapp += 1
        else:
            com_whatsapp += 1
        # Distribuição fina do universo por bucket de alcance (soma == universo).
        bucket = _wa_alcance(c.phone)
        por_alcance[bucket] = por_alcance.get(bucket, 0) + 1

        # Funil win-back monotônico: cada etapa implica TODAS as anteriores
        # (reativou ⊆ cortesia ⊆ respondeu ⊆ contatado ⊆ universo). Assim a cascata
        # da tela nunca cresce, não importa a ordem em que o operador marca os selos.
        reativou_flag = SELO_REATIVOU in selos
        cortesia_flag = (SELO_CORTESIA in selos) or reativou_flag
        respondeu_flag = (
            (SELO_RESPONDEU in selos) or any(f.source == "forms" for f in fbs) or cortesia_flag
        )
        contatado_flag = (
            any(f.abordado for f in fbs)
            or (SELO_CONTATADO in selos)
            or bool(abordagens)
            or respondeu_flag
        )
        if contatado_flag:
            contatados += 1
        if respondeu_flag:
            responderam += 1
        if cortesia_flag:
            cortesia += 1
        if reativou_flag:
            reativaram += 1

        # por_selo (contatos do universo por selo)
        for nome in selos:
            por_selo[nome] = por_selo.get(nome, 0) + 1

        # por_canal (todas as abordagens do universo)
        for a in abordagens:
            canal = str(a.get("canal") or "outro")
            por_canal[canal] = por_canal.get(canal, 0) + 1

        # insights (temas dos feedbacks do universo)
        for f in fbs:
            neg = f.sentiment == "negativo"
            for t in (f.themes or []):
                key = str(t).strip()
                if not key:
                    continue
                tema_count[key] = tema_count.get(key, 0) + 1
                if neg:
                    tema_neg[key] = tema_neg.get(key, 0) + 1

    universo = len(universo_ids)
    faltam = max(0, universo - contatados)

    funil = [
        {"etapa": "a contatar", "count": faltam},
        {"etapa": "contatado", "count": contatados},
        {"etapa": "respondeu", "count": responderam},
        {"etapa": "cortesia", "count": cortesia},
        {"etapa": "reativou", "count": reativaram},
    ]

    insights = sorted(
        (
            {"tema": tema, "count": count, "neg": tema_neg.get(tema, 0)}
            for tema, count in tema_count.items()
        ),
        key=lambda it: it["count"],
        reverse=True,
    )[:8]

    return {
        "universo": universo,
        "com_whatsapp": com_whatsapp,
        "sem_whatsapp": sem_whatsapp,
        "por_alcance": por_alcance,
        "contatados": contatados,
        "responderam": responderam,
        "cortesia": cortesia,
        "reativaram": reativaram,
        "faltam": faltam,
        "por_canal": por_canal,
        "por_selo": por_selo,
        "funil": funil,
        "insights": insights,
    }


# --- FORMS IMPORT (porta para os dados de formulário) -------------------------


class FormsRow(BaseModel):
    whatsapp: str | None = Field(default=None, max_length=32)
    nome: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    nota: int | None = Field(default=None, ge=0, le=10)
    texto: str | None = Field(default=None, max_length=4000)


class FormsImportIn(BaseModel):
    rows: list[FormsRow] = Field(default_factory=list)


async def _get_or_create_contact_forms(
    session: AsyncSession, org: Organization, whatsapp: str | None, nome: str | None
) -> Contact | None:
    """Get-or-create por whatsapp (só dígitos) ou, sem whatsapp, por nome.

    Retorna None quando não há nem whatsapp válido nem nome (linha sem identificação
    — o caller a conta como `skipped`). Contato CRIADO aqui nasce sem opt_in (o
    consentimento de envio nunca vem de um import interno — mesma regra do admin.py).
    """
    phone = re.sub(r"\D", "", whatsapp or "")
    nome_s = (nome or "").strip() or None

    if len(phone) >= 10:
        contact = (
            await session.execute(
                select(Contact).where(Contact.organization_id == org.id, Contact.phone == phone)
            )
        ).scalar_one_or_none()
        if contact is None:
            contact = Contact(
                organization_id=org.id, phone=phone, name=nome_s, opt_in=False, profile_data={}
            )
            session.add(contact)
            await session.flush()
        elif nome_s and not contact.name:
            contact.name = nome_s
        return contact

    if nome_s:
        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.organization_id == org.id,
                    func.lower(func.coalesce(Contact.name, "")) == nome_s.lower(),
                )
            )
        ).scalars().first()
        if contact is None:
            # Sem whatsapp: cria com um phone placeholder vazio (a coluna é NOT NULL no
            # model, mas aceita string vazia). O matching futuro continua por nome.
            contact = Contact(
                organization_id=org.id, phone="", name=nome_s, opt_in=False, profile_data={}
            )
            session.add(contact)
            await session.flush()
        return contact

    return None


@router.post("/forms/import")
async def forms_import(
    body: FormsImportIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Importa respostas de formulário (a porta; os dados reais chegam depois).

    Por linha: get-or-create Contact (por whatsapp só-dígitos; senão por nome), cria
    um FeedbackItem source='forms' type=('nps' se nota não-nula senão 'outro')
    score=nota text=texto, e aplica o selo 'respondeu' ao contato.

    IDEMPOTENTE por external_id = 'forms:' + (whatsapp_dígitos ou nome): re-rodar o
    mesmo lote não duplica (atualiza o item existente e reconta como `updated`).
    Linhas sem identificação (sem whatsapp válido e sem nome) entram em `skipped`.
    Retorna {created, updated, skipped}.
    """
    org = await _get_org(session)

    created = 0
    updated = 0
    skipped = 0

    for row in body.rows:
        phone = re.sub(r"\D", "", row.whatsapp or "")
        nome_s = (row.nome or "").strip() or None

        # Chave de dedup: prioriza whatsapp; senão nome. Sem nenhum -> skip.
        if len(phone) >= 10:
            external_id = f"forms:{phone}"
        elif nome_s:
            # casa com o get-or-create por nome (que compara em lowercase) — evita
            # 'João' vs 'joão' gerarem external_ids distintos e duplicarem o feedback.
            external_id = f"forms:{nome_s.lower()}"
        else:
            skipped += 1
            continue

        contact = await _get_or_create_contact_forms(session, org, row.whatsapp, row.nome)
        if contact is None:
            skipped += 1
            continue

        text = (row.texto.strip() or None) if row.texto else None
        ftype = "nps" if row.nota is not None else "outro"
        bucket = nps_bucket(row.nota) if row.nota is not None else None

        existing = (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.external_id == external_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            item = FeedbackItem(
                organization_id=org.id,
                contact_id=contact.id,
                source="forms",
                type=ftype,
                external_id=external_id,
                score=row.nota,
                nps_bucket=bucket,
                text=text,
                occurred_at=datetime.now(timezone.utc),
            )
            session.add(item)
            created += 1
        else:
            # Re-import: atualiza o snapshot (a resposta pode ter sido reenviada).
            existing.contact_id = contact.id
            existing.type = ftype
            existing.score = row.nota
            existing.nps_bucket = bucket
            existing.text = text
            updated += 1

        # Aplica o selo 'respondeu' (idempotente) — camada com LOG, origem="form".
        aplicar_selo(contact, SELO_RESPONDEU, origem="form", org=org)

    await session.commit()
    return {"created": created, "updated": updated, "skipped": skipped}
