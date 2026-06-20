"""API de ENVIO 1:1 no WhatsApp (gated por confirmação) + status do WAHA.

Princípio inegociável (regra de ouro do projeto): WhatsApp real só com OK do
usuário E sessão ligada. Por isso o envio é GATED:

- SEM `confirm` (default): PREVIEW — devolve o que SERIA enviado (telefone, texto,
  se o número é celular válido, se é ALCANÇÁVEL, se é grupo, e se o WAHA está
  conectado) e NÃO envia nada.
- COM `confirm=true`: só envia se o WAHA estiver conectado (senão 409) e se o
  contato for ALCANÇÁVEL (senão 422). Ao enviar de verdade: chama
  WAHAService.send_text, registra a abordagem em profile_data["abordagens"], aplica
  o selo 'contatado' (idempotente) e grava Message(direction="outbound").

ALCANÇÁVEL (gate correto, sem afrouxar segurança): NÃO é grupo do WhatsApp E
(tem celular BR válido OU já mandou >=1 mensagem inbound). O inbound prova que o
contato está no WhatsApp — assim dá pra RESPONDER quem te escreveu mesmo que o
telefone esteja salvo em formato antigo; grupos (JID 120363...) nunca recebem 1:1.

Reusa os helpers de campanha (selos/abordagens) e de admin (_get_org/_get_contact),
e resolve o WAHAService a partir de settings (mesmo padrão do webhook.py). O router
é montado com prefixo /api no main.py, então as rotas são declaradas SEM o /api.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _get_org
from app.api.campanha import (
    SELO_CONTATADO,
    _abordagens_do_contato,
    _get_contact,
    _selos_do_contato,
    _set_abordagens_do_contato,
    aplicar_selo,
)
from app.config import settings
from app.db import get_session
from app.domain.contacts.whatsapp import classify_phone, tem_whatsapp
from app.domain.interfaces.messaging_service import IMessagingService
from app.models.core import Contact
from app.models.survey import Message
from app.services.waha import WAHAService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


def get_waha() -> WAHAService:
    """Canal WAHA real, resolvido de settings (mesmo padrão do webhook.py).

    Substituível via dependency_overrides nos testes — assim nada toca a rede.
    """
    return WAHAService(settings.waha_base_url, settings.waha_api_key, settings.waha_session)


@router.get("/whatsapp/status")
async def whatsapp_status(waha: WAHAService = Depends(get_waha)) -> dict[str, Any]:
    """Status do gateway WAHA (best-effort). NÃO expõe segredos (sem api_key).

    Retorna {"conectado": bool, "status": <str|None>, "session": <nome>,
    "base_url": <url>}. `status` é a string crua do WAHA (WORKING / SCAN_QR_CODE /
    STARTING / STOPPED / FAILED / None). `conectado` é True só quando a sessão está
    plenamente conectada ('WORKING'); WAHA off/erro -> conectado False + status None
    (o helper engole a exceção e devolve None).
    """
    status = await waha.get_session_status(settings.waha_session)
    return {
        "conectado": status == "WORKING",
        "status": status,
        "session": settings.waha_session,
        "base_url": settings.waha_base_url,
    }


@router.get("/whatsapp/qr")
async def whatsapp_qr(waha: WAHAService = Depends(get_waha)) -> dict[str, Any]:
    """QR Code do WAHA para parear o WhatsApp (best-effort).

    Retorna {"qr": <data-uri|null>, "status": <str|null>}. Se a sessão já está
    'WORKING' (pareada), devolve qr=null + status WORKING (não há QR a mostrar). Se
    o WAHA está off/erro, devolve {"qr": null, "status": null} — NUNCA 500.
    """
    status = await waha.get_session_status(settings.waha_session)
    # Já conectado: não há QR para exibir.
    if status == "WORKING":
        return {"qr": None, "status": status}
    res = await waha.get_qr_code(settings.waha_session)
    return {
        "qr": res.get("qr"),
        # Prefere o status que veio junto do QR; cai no lido acima.
        "status": res.get("status", status) or status,
    }


@router.post("/whatsapp/session/start")
async def whatsapp_session_start(waha: WAHAService = Depends(get_waha)) -> dict[str, Any]:
    """Inicia a sessão WAHA (pareamento). Best-effort: WAHA off -> {"ok": false}.

    Retorna {"ok": bool, "status": <str|null>}. NÃO é envio de mensagem — só liga a
    sessão para o operador escanear o QR. NUNCA 500.
    """
    res = await waha.start_session(settings.waha_session)
    return {"ok": bool(res.get("ok")), "status": res.get("status")}


@router.post("/whatsapp/session/stop")
async def whatsapp_session_stop(waha: WAHAService = Depends(get_waha)) -> dict[str, Any]:
    """Para a sessão WAHA. Best-effort: WAHA off -> {"ok": false}.

    Retorna {"ok": bool, "status": <str|null>}. NUNCA 500.
    """
    res = await waha.stop_session(settings.waha_session)
    return {"ok": bool(res.get("ok")), "status": res.get("status")}


@router.post("/whatsapp/session/restart")
async def whatsapp_session_restart(waha: WAHAService = Depends(get_waha)) -> dict[str, Any]:
    """Reinicia a sessão WAHA (stop + start). Best-effort: WAHA off -> {"ok": false}.

    Retorna {"ok": bool, "status": <str|null>}. NUNCA 500.
    """
    res = await waha.restart_session(settings.waha_session)
    return {"ok": bool(res.get("ok")), "status": res.get("status")}


def _is_grupo(phone: str | None) -> bool:
    """True se o telefone é um ID de grupo/comunidade do WhatsApp (não recebe 1:1)."""
    return classify_phone(phone) == "group"


async def _tem_inbound(session: AsyncSession, org_id: Any, contact_id: Any) -> bool:
    """True se existe >=1 Message inbound desse contato (prova de que está no WhatsApp).

    Query leve: EXISTS (não conta nem carrega linhas).
    """
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Message.organization_id == org_id,
                    Message.contact_id == contact_id,
                    Message.direction == "inbound",
                )
            )
        )
    )


async def _alcancavel(session: AsyncSession, org_id: Any, contact: Contact) -> bool:
    """ALCANÇÁVEL = NÃO é grupo E (celular BR válido OU já mandou >=1 inbound).

    O inbound prova que o contato está no WhatsApp (dá pra responder quem te
    escreveu mesmo com telefone em formato antigo). Grupo nunca é alcançável 1:1.
    """
    phone = contact.phone or ""
    if _is_grupo(phone):
        return False
    if tem_whatsapp(phone):
        return True
    return await _tem_inbound(session, org_id, contact.id)


class WhatsAppSendIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
    oferta: str | None = Field(default=None, max_length=200)
    por: str | None = Field(default=None, max_length=120)
    # Gate de segurança: sem confirm (default) é só PREVIEW; o envio real exige
    # confirm=true E WAHA conectado.
    confirm: bool = False


@router.post("/contacts/{contact_id}/whatsapp/send")
async def whatsapp_send(
    contact_id: str,
    body: WhatsAppSendIn,
    session: AsyncSession = Depends(get_session),
    waha: WAHAService = Depends(get_waha),
) -> dict[str, Any]:
    """Envia (ou pré-visualiza) uma mensagem 1:1 no WhatsApp para um contato.

    PREVIEW (sem confirm): devolve {"preview": true, "para", "tem_whatsapp",
    "alcancavel", "is_grupo", "texto", "waha_conectado"} e NÃO envia nada.

    ENVIO (confirm=true): exige WAHA conectado (senão 409) e contato ALCANÇÁVEL
    (senão 422 — grupo não recebe 1:1; contato sem WhatsApp e sem inbound não dá
    pra enviar). Envia via WAHAService.send_text, registra a abordagem (append em
    profile_data["abordagens"]), aplica o selo 'contatado' (idempotente) e grava
    Message(direction="outbound"). Devolve {"enviado": true, ...}.
    """
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)

    texto = body.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto não pode ser vazio")

    phone = contact.phone or ""
    eh_celular = tem_whatsapp(phone)
    is_grupo = _is_grupo(phone)
    alcancavel = await _alcancavel(session, org.id, contact)

    # --- PREVIEW (default): não envia nada, devolve o que SERIA enviado ----------
    if not body.confirm:
        conectado = await waha.is_connected(settings.waha_session)
        return {
            "preview": True,
            "para": phone,
            "tem_whatsapp": eh_celular,
            "alcancavel": alcancavel,
            "is_grupo": is_grupo,
            "texto": texto,
            "waha_conectado": bool(conectado),
        }

    # --- ENVIO REAL (confirm=true): gated por WAHA conectado + ALCANÇÁVEL --------
    conectado = await waha.is_connected(settings.waha_session)
    if not conectado:
        raise HTTPException(
            status_code=409, detail="WAHA não conectado — ligue a sessão e tente de novo"
        )
    if not alcancavel:
        detalhe = (
            "grupo do WhatsApp não recebe mensagem 1:1"
            if is_grupo
            else "contato sem WhatsApp (sem celular válido e sem mensagem recebida) — não dá para enviar"
        )
        raise HTTPException(status_code=422, detail=detalhe)

    now = datetime.now(timezone.utc)
    resultado = await waha.send_text(chat_id=phone, text=texto, session=settings.waha_session)
    # O WAHAService devolve {"success": True, "data": {...}} no sucesso e {"error": ...}
    # em falha (HTTP>=400 ou exceção). Se NÃO houve sucesso, aborta ANTES de registrar
    # abordagem/selo/Message — senão marcaríamos "contatado" para um envio que não saiu.
    if not (isinstance(resultado, dict) and resultado.get("success")):
        erro = (resultado or {}).get("error") if isinstance(resultado, dict) else "falha desconhecida"
        raise HTTPException(status_code=502, detail=f"WhatsApp não enviou: {erro}")
    channel_msg_id = ((resultado.get("data") or {}).get("id")) if isinstance(resultado.get("data"), dict) else None

    # Registra a abordagem 1:1 (append em profile_data["abordagens"]).
    abordagem = {
        "at": now.isoformat(),
        "canal": "whatsapp",
        "mensagem": texto,
        "oferta": (body.oferta.strip() or None) if body.oferta else None,
        "status": "enviado",
        "por": (body.por.strip() or None) if body.por else None,
    }
    _set_abordagens_do_contato(contact, [*_abordagens_do_contato(contact), abordagem])

    # Aplica o selo 'contatado' (idempotente) + garante no catálogo — camada com LOG,
    # origem="whatsapp_enviado" (registra `por` quando informado no envio).
    aplicar_selo(contact, SELO_CONTATADO, origem="whatsapp_enviado", por=abordagem.get("por"), org=org)

    # Grava a mensagem outbound no transcript.
    session.add(
        Message(
            organization_id=org.id,
            contact_id=contact.id,
            direction="outbound",
            body=texto,
            channel_msg_id=str(channel_msg_id) if channel_msg_id is not None else None,
        )
    )

    await session.commit()
    return {
        "enviado": True,
        "para": phone,
        "texto": texto,
        "abordagem": abordagem,
        "selos": _selos_do_contato(contact),
        "channel_msg_id": str(channel_msg_id) if channel_msg_id is not None else None,
    }


# --- LEITURA: conversas + thread (painel de chat) ----------------------------


def _estado_do_contato(contact: Contact) -> str | None:
    """Estado da assinatura no snapshot partner (ex.: 'cancelled'); None se ausente."""
    partner = (contact.profile_data or {}).get("partner") or {}
    return ((partner.get("subscription") or {}).get("state")) or None


@router.get("/whatsapp/conversations")
async def whatsapp_conversations(
    search: str | None = None,
    excluir_grupos: bool = True,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Lista as conversas (1 por contato que tem mensagem), ordenadas pela última
    mensagem desc — alimenta a coluna esquerda do painel de chat.

    Cada item: {contact_id, nome, whatsapp, tem_whatsapp, is_grupo, estado, selos,
    total, ultima_mensagem, ultima_em, ultima_direction}. `search` filtra
    nome/telefone. `excluir_grupos` (default TRUE): por padrão omite contatos cujo
    telefone é classe 'group' (JID de grupo/comunidade do WhatsApp) — a Central é de
    conversa 1:1. Passe `excluir_grupos=false` explicitamente para incluí-los.
    """
    org = await _get_org(session)
    # UMA query: mensagens + contato juntados, mais recentes primeiro. Agrupa em
    # Python (escala-piloto): 1ª ocorrência por contato = última mensagem; conta o total.
    rows = (
        await session.execute(
            select(Message, Contact)
            .join(Contact, Contact.id == Message.contact_id)
            .where(Message.organization_id == org.id)
            .order_by(Message.created_at.desc())
        )
    ).all()

    termo = (search or "").strip().lower()
    by_contact: dict[Any, dict[str, Any]] = {}
    for m, c in rows:
        cur = by_contact.get(c.id)
        if cur is None:
            nome = c.name or ""
            phone = c.phone or ""
            if termo and termo not in nome.lower() and termo not in phone.lower():
                # marca como filtrado-fora p/ não recontar; usa sentinela
                by_contact[c.id] = {"_skip": True}
                continue
            if excluir_grupos and _is_grupo(phone):
                # grupo do WhatsApp filtrado por opção; sentinela p/ não recontar.
                by_contact[c.id] = {"_skip": True}
                continue
            by_contact[c.id] = {
                "contact_id": str(c.id),
                "nome": c.name,
                "whatsapp": c.phone,
                "tem_whatsapp": tem_whatsapp(c.phone),
                "is_grupo": _is_grupo(c.phone),
                "estado": _estado_do_contato(c),
                "selos": _selos_do_contato(c),
                "ultima_mensagem": m.body,
                "ultima_em": m.created_at.isoformat() if m.created_at else None,
                "ultima_direction": m.direction,
                "total": 1,
            }
        elif not cur.get("_skip"):
            cur["total"] += 1

    conversas = [v for v in by_contact.values() if not v.get("_skip")]
    return {"conversations": conversas[: max(0, limit)], "total": len(conversas)}


@router.get("/contacts/{contact_id}/whatsapp/thread")
async def whatsapp_thread(
    contact_id: str,
    limit: int = 300,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Thread cronológica (mais antiga -> mais nova) das mensagens de um contato —
    alimenta os balões da direita do painel de chat.

    Retorna {contact: {..., tem_whatsapp, alcancavel, is_grupo}, mensagens:
    [{id, direction, body, at}]}.
    """
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)

    alcancavel = await _alcancavel(session, org.id, contact)

    msgs = (
        (
            await session.execute(
                select(Message)
                .where(
                    Message.organization_id == org.id,
                    Message.contact_id == contact.id,
                )
                .order_by(Message.created_at.asc())
                .limit(max(0, limit))
            )
        )
        .scalars()
        .all()
    )

    return {
        "contact": {
            "id": str(contact.id),
            "nome": contact.name,
            "whatsapp": contact.phone,
            "tem_whatsapp": tem_whatsapp(contact.phone),
            "alcancavel": alcancavel,
            "is_grupo": _is_grupo(contact.phone),
            "estado": _estado_do_contato(contact),
            "selos": _selos_do_contato(contact),
            "opt_in": contact.opt_in,
        },
        "mensagens": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "body": m.body,
                "at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }
