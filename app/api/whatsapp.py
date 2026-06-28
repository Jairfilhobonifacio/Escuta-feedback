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

import asyncio
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
from app.domain.contacts.whatsapp import classify_phone, phone_variants, tem_whatsapp
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


class WhatsAppImportIn(BaseModel):
    """Preview/importação manual de histórico do WhatsApp para um contato.

    Gate de segurança igual ao envio: sem `confirm` não grava nada. O operador vê
    o volume encontrado e decide. `limit` é limitado para evitar puxar conversas
    gigantes por engano.
    """

    confirm: bool = False
    limit: int = Field(default=100, ge=1, le=500)


class WhatsAppBatchImportIn(BaseModel):
    """Importação em lote do histórico WhatsApp para todos os contatos da org."""

    limit_per_contact: int = Field(default=200, ge=1, le=500)
    dry_run: bool = False


class HandoffIn(BaseModel):
    """Liga/desliga o hand-off humano de um contato (assumir/devolver a conversa)."""

    ativar: bool = True


@router.post("/contacts/{contact_id}/whatsapp/handoff")
async def whatsapp_handoff(
    contact_id: str,
    body: HandoffIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """ativar=true PAUSA o bot p/ este contato (o webhook respeita `needs_human_handoff`
    e NÃO auto-responde — o operador assume a conversa pelo Chat); ativar=false devolve ao
    fluxo automático. Idempotente. Retorna o estado atual do flag."""
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)
    contact.needs_human_handoff = bool(body.ativar)
    await session.commit()
    return {"contact_id": str(contact.id), "needs_human_handoff": contact.needs_human_handoff}


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


def _chat_id(chat: dict[str, Any]) -> str:
    raw = chat.get("id")
    if isinstance(raw, dict):
        return str(raw.get("_serialized") or raw.get("serialized") or "")
    return str(raw or "")


def _message_id(msg: dict[str, Any]) -> str | None:
    raw = msg.get("id")
    if isinstance(raw, dict):
        val = raw.get("_serialized") or raw.get("id") or raw.get("remote")
    else:
        val = raw or msg.get("messageId") or msg.get("message_id")
    return str(val) if val else None


def _message_body(msg: dict[str, Any]) -> str:
    body = msg.get("body") or msg.get("caption") or msg.get("text") or ""
    if body:
        return str(body)
    media_type = msg.get("type") or msg.get("mediaType")
    return f"[{media_type or 'mensagem'} sem texto]"


def _message_created_at(msg: dict[str, Any]) -> datetime | None:
    ts = msg.get("timestamp") or msg.get("t")
    try:
        if ts is None:
            return None
        n = float(ts)
        if n > 10_000_000_000:  # alguns payloads usam milissegundos.
            n = n / 1000
        return datetime.fromtimestamp(n, tz=timezone.utc)
    except Exception:  # noqa: BLE001 — timestamp ruim não bloqueia import.
        return None


async def _find_chat_for_contact(
    waha: WAHAService, contact: Contact, *, limit: int = 1000
) -> tuple[str | None, str | None]:
    """Encontra o chat WAHA que parece ser do contato, cruzando telefone e LID.

    O WhatsApp novo devolve muitos chats como `@lid`; quando isso acontece,
    resolvemos o LID para telefone e comparamos contra as variantes do telefone
    salvo no contato.
    """
    phone = contact.phone or ""
    variants = set(phone_variants(phone) or [])
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits:
        variants.add(digits)
    if not variants:
        return None, None

    direct_ids = [f"{v}@c.us" for v in variants]
    chats = await waha.get_chats(settings.waha_session, limit=limit)
    seen_direct = {_chat_id(c) for c in chats}
    for chat_id in direct_ids:
        if chat_id in seen_direct:
            return chat_id, chat_id.split("@", 1)[0]

    for chat in chats:
        chat_id = _chat_id(chat)
        if not chat_id or chat_id.endswith("@g.us"):
            continue
        if chat_id.endswith("@c.us"):
            phone_digits = chat_id.split("@", 1)[0]
        elif chat_id.endswith("@lid"):
            phone_digits = await waha.resolve_lid(chat_id, settings.waha_session)
        else:
            phone_digits = None
        if phone_digits and phone_digits in variants:
            return chat_id, phone_digits
    return None, None


@router.post("/contacts/{contact_id}/whatsapp/import")
async def whatsapp_import_history(
    contact_id: str,
    body: WhatsAppImportIn,
    session: AsyncSession = Depends(get_session),
    waha: WAHAService = Depends(get_waha),
) -> dict[str, Any]:
    """Puxa histórico WAHA de um contato já cadastrado, com preview obrigatório.

    - `confirm=false` (default): procura o chat e lista estatísticas; NÃO grava.
    - `confirm=true`: grava apenas mensagens novas no transcript (`Message`),
      deduplicando por `channel_msg_id`.

    Não classifica nem cria FeedbackItem ainda; primeiro passo é trazer a
    conversa para a central com controle humano.
    """
    org = await _get_org(session)
    contact = await _get_contact(session, org, contact_id)

    if _is_grupo(contact.phone):
        raise HTTPException(status_code=422, detail="grupo do WhatsApp não tem importação 1:1")

    conectado = await waha.is_connected(settings.waha_session)
    if not conectado:
        raise HTTPException(status_code=409, detail="WAHA não conectado — ligue a sessão e tente de novo")

    chat_id, resolved_phone = await _find_chat_for_contact(waha, contact)
    if not chat_id:
        return {
            "preview": not body.confirm,
            "imported": False,
            "chat_id": None,
            "resolved_phone": None,
            "found": 0,
            "new": 0,
            "already_imported": 0,
            "messages": [],
        }

    raw_messages = await waha.get_chat_messages(
        chat_id, settings.waha_session, limit=body.limit, download_media=False
    )
    parsed: list[dict[str, Any]] = []
    channel_ids: list[str] = []
    for msg in raw_messages:
        channel_id = _message_id(msg)
        direction = "outbound" if bool(msg.get("fromMe")) else "inbound"
        item = {
            "channel_msg_id": channel_id,
            "direction": direction,
            "body": _message_body(msg),
            "at": _message_created_at(msg),
            "from_me": bool(msg.get("fromMe")),
        }
        parsed.append(item)
        if channel_id:
            channel_ids.append(channel_id)

    existing: set[str] = set()
    if channel_ids:
        existing = set(
            (
                await session.execute(
                    select(Message.channel_msg_id).where(
                        Message.organization_id == org.id,
                        Message.channel_msg_id.in_(channel_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

    # Só importamos mensagens com id estável do WAHA; sem isso não há deduplicação
    # confiável em uma nova execução do mesmo import.
    new_items = [m for m in parsed if m["channel_msg_id"] and m["channel_msg_id"] not in existing]
    preview_messages = [
        {
            "direction": m["direction"],
            "body": m["body"],
            "at": m["at"].isoformat() if m["at"] else None,
            "already_imported": bool(m["channel_msg_id"] and m["channel_msg_id"] in existing),
        }
        for m in parsed[:10]
    ]

    if not body.confirm:
        return {
            "preview": True,
            "imported": False,
            "chat_id": chat_id,
            "resolved_phone": resolved_phone,
            "found": len(parsed),
            "new": len(new_items),
            "already_imported": len(parsed) - len(new_items),
            "messages": preview_messages,
        }

    for m in new_items:
        meta = {
            "source_event": "waha_history_import",
            "chat_id": chat_id,
            "resolved_phone": resolved_phone,
            "from_me": m["from_me"],
        }
        session.add(
            Message(
                organization_id=org.id,
                contact_id=contact.id,
                direction=m["direction"],
                body=m["body"],
                channel_msg_id=m["channel_msg_id"],
                msg_metadata=meta,
                created_at=m["at"] or datetime.now(timezone.utc),
            )
        )

    await session.commit()
    return {
        "preview": False,
        "imported": True,
        "chat_id": chat_id,
        "resolved_phone": resolved_phone,
        "found": len(parsed),
        "new": len(new_items),
        "already_imported": len(parsed) - len(new_items),
        "messages": preview_messages,
    }


# --- BATCH: import + análise IA em lote -------------------------------------


async def _build_waha_phone_map(
    waha: WAHAService, chats: list[dict[str, Any]]
) -> dict[str, str]:
    """Resolve lista de chats WAHA → {phone_digits: chat_id}.

    LIDs (@lid) são resolvidos em paralelo (semáforo 10). Grupos (@g.us) ignorados.
    Chamado uma vez por batch-import para evitar N chamadas a get_chats().
    """
    result: dict[str, str] = {}
    lid_chats: list[str] = []

    for chat in chats:
        chat_id = _chat_id(chat)
        if not chat_id or chat_id.endswith("@g.us"):
            continue
        if chat_id.endswith("@c.us"):
            result[chat_id.split("@", 1)[0]] = chat_id
        elif chat_id.endswith("@lid"):
            lid_chats.append(chat_id)

    if lid_chats:
        sem = asyncio.Semaphore(10)

        async def _resolve(lid: str) -> None:
            async with sem:
                phone = await waha.resolve_lid(lid, settings.waha_session)
                if phone:
                    result[phone] = lid

        await asyncio.gather(*[_resolve(lid) for lid in lid_chats])

    return result


def _match_contact_in_map(
    contact: Contact, phone_map: dict[str, str]
) -> tuple[str | None, str | None]:
    """Encontra (chat_id, phone_digits) usando o mapa pré-resolvido (sem WAHA)."""
    phone = contact.phone or ""
    variants = set(phone_variants(phone) or [])
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits:
        variants.add(digits)
    for v in variants:
        if v in phone_map:
            return phone_map[v], v
    return None, None


@router.post("/whatsapp/batch-import")
async def whatsapp_batch_import(
    body: WhatsAppBatchImportIn,
    session: AsyncSession = Depends(get_session),
    waha: WAHAService = Depends(get_waha),
) -> dict[str, Any]:
    """Importa histórico WhatsApp de TODOS os contatos da org de uma vez.

    Fluxo:
    1. Carrega todos os chats do WAHA (1 chamada) + resolve @lid em paralelo.
    2. Cruza cada contato (com telefone) contra o mapa.
    3. Para os que bateram: busca mensagens em paralelo (semáforo 8).
    4. Grava mensagens novas (dedup por channel_msg_id).

    dry_run=true → retorna o que SERIA importado sem gravar.
    """
    org = await _get_org(session)

    if not await waha.is_connected(settings.waha_session):
        raise HTTPException(status_code=409, detail="WAHA não conectado — ligue a sessão e tente de novo")

    all_chats = await waha.get_chats(settings.waha_session, limit=1000)
    phone_map = await _build_waha_phone_map(waha, all_chats)

    contacts = (
        await session.execute(
            select(Contact).where(
                Contact.organization_id == org.id,
                Contact.phone.isnot(None),
                Contact.phone != "",
            )
        )
    ).scalars().all()

    matched: list[tuple[Contact, str, str]] = []
    not_found_contacts: list[Contact] = []
    for contact in contacts:
        chat_id, phone_digits = _match_contact_in_map(contact, phone_map)
        if chat_id:
            matched.append((contact, chat_id, phone_digits or ""))
        else:
            not_found_contacts.append(contact)

    # Busca mensagens em paralelo (só WAHA, sem DB)
    fetch_sem = asyncio.Semaphore(8)

    async def _fetch(chat_id: str) -> list[dict[str, Any]]:
        async with fetch_sem:
            return await waha.get_chat_messages(
                chat_id, settings.waha_session,
                limit=body.limit_per_contact,
                download_media=False,
            )

    raw_results = await asyncio.gather(
        *[_fetch(cid) for _, cid, _ in matched],
        return_exceptions=True,
    )

    # Dedup + gravar (sequential — sessão única)
    details: list[dict[str, Any]] = []
    imported_total = 0
    errors = 0

    for (contact, chat_id, phone_digits), raw in zip(matched, raw_results):
        if isinstance(raw, Exception):
            errors += 1
            details.append({
                "contact_id": str(contact.id),
                "name": contact.name,
                "phone": contact.phone,
                "status": "error",
                "found": 0,
                "new": 0,
            })
            continue

        parsed: list[dict[str, Any]] = []
        channel_ids: list[str] = []
        for msg in raw:
            channel_id = _message_id(msg)
            parsed.append({
                "channel_msg_id": channel_id,
                "direction": "outbound" if bool(msg.get("fromMe")) else "inbound",
                "body": _message_body(msg),
                "at": _message_created_at(msg),
                "from_me": bool(msg.get("fromMe")),
            })
            if channel_id:
                channel_ids.append(channel_id)

        existing: set[str] = set()
        if channel_ids:
            existing = set(
                (
                    await session.execute(
                        select(Message.channel_msg_id).where(
                            Message.organization_id == org.id,
                            Message.channel_msg_id.in_(channel_ids),
                        )
                    )
                ).scalars().all()
            )

        new_items = [m for m in parsed if m["channel_msg_id"] and m["channel_msg_id"] not in existing]

        if not body.dry_run:
            for m in new_items:
                session.add(
                    Message(
                        organization_id=org.id,
                        contact_id=contact.id,
                        direction=m["direction"],
                        body=m["body"],
                        channel_msg_id=m["channel_msg_id"],
                        msg_metadata={
                            "source_event": "waha_history_import",
                            "chat_id": chat_id,
                            "resolved_phone": phone_digits,
                            "from_me": m["from_me"],
                        },
                        created_at=m["at"] or datetime.now(timezone.utc),
                    )
                )
            if new_items:
                await session.flush()

        imported_total += len(new_items)
        details.append({
            "contact_id": str(contact.id),
            "name": contact.name,
            "phone": contact.phone,
            "chat_id": chat_id,
            "status": "imported" if (new_items and not body.dry_run) else ("preview" if new_items else "already_done"),
            "found": len(parsed),
            "new": len(new_items),
        })

    for contact in not_found_contacts:
        details.append({
            "contact_id": str(contact.id),
            "name": contact.name,
            "phone": contact.phone,
            "status": "not_found",
            "found": 0,
            "new": 0,
        })

    if not body.dry_run and imported_total > 0:
        await session.commit()

    return {
        "dry_run": body.dry_run,
        "total_contacts": len(contacts),
        "matched": len(matched),
        "not_found": len(not_found_contacts),
        "imported": imported_total,
        "errors": errors,
        "details": details,
    }


@router.post("/whatsapp/batch-analyze")
async def whatsapp_batch_analyze(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Analisa conversas WhatsApp importadas e cria/atualiza FeedbackItems com IA.

    Para cada contato com mensagens inbound no transcript:
    - Agrega texto das últimas 50 mensagens recebidas (palavras do cliente).
    - Classifica via Groq (sentimento/temas/urgência).
    - Cria ou atualiza um FeedbackItem type='whatsapp_history' (dedup por external_id).

    Idempotente: re-executar atualiza o FeedbackItem existente com texto mais recente.
    """
    from app.domain.feedback.ingest import ingest_feedback_item
    from app.models.feedback import FeedbackItem as FI

    org = await _get_org(session)

    contact_ids: list[Any] = (
        await session.execute(
            select(Message.contact_id)
            .where(
                Message.organization_id == org.id,
                Message.direction == "inbound",
                Message.contact_id.isnot(None),
            )
            .distinct()
        )
    ).scalars().all()

    if not contact_ids:
        return {"analyzed": 0, "created": 0, "updated": 0, "errors": 0, "details": []}

    analyzed = 0
    created = 0
    updated = 0
    errors = 0
    details: list[dict[str, Any]] = []

    for contact_id in contact_ids:
        try:
            rows = (
                await session.execute(
                    select(Message.body, Message.created_at)
                    .where(
                        Message.organization_id == org.id,
                        Message.contact_id == contact_id,
                        Message.direction == "inbound",
                        Message.body.isnot(None),
                        Message.body != "",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(50)
                )
            ).all()

            if not rows:
                continue

            bodies = [r.body.strip() for r in reversed(rows) if r.body and r.body.strip()]
            text = " | ".join(bodies)
            if len(text) > 3000:
                text = text[-3000:]
            if not text:
                continue

            external_id = f"whatsapp_history:{contact_id}"
            existing_id = (
                await session.execute(
                    select(FI.id).where(
                        FI.organization_id == org.id,
                        FI.external_id == external_id,
                    )
                )
            ).scalar_one_or_none()

            await ingest_feedback_item(
                session,
                org.id,
                contact_id,
                {
                    "source": "whatsapp",
                    "type": "whatsapp_history",
                    "external_id": external_id,
                    "text": text,
                    "extra": {"msg_count": len(rows)},
                },
                classify=True,
            )
            await session.flush()

            analyzed += 1
            if existing_id:
                updated += 1
                details.append({"contact_id": str(contact_id), "status": "updated", "msg_count": len(rows)})
            else:
                created += 1
                details.append({"contact_id": str(contact_id), "status": "created", "msg_count": len(rows)})

        except Exception as exc:  # noqa: BLE001 — best-effort por contato.
            errors += 1
            logger.warning("batch_analyze erro para contato %s: %s", contact_id, exc)
            details.append({"contact_id": str(contact_id), "status": "error", "error": str(exc)[:100]})

    await session.commit()
    return {"analyzed": analyzed, "created": created, "updated": updated, "errors": errors, "details": details}


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
            "needs_human_handoff": contact.needs_human_handoff,
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
