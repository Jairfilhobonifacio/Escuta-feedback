"""Webhook do WAHA — porta de entrada das mensagens inbound do WhatsApp.

Fase 0: liga a mensagem inbound diretamente ao SurveyContextResolver. Quando a
mensagem é resposta de uma pesquisa pendente, responde via WAHA e fecha o loop.
Quando não há pesquisa pendente, apenas confirma (Fase 1: cai no orchestrator/agente).

Princípio inegociável: o webhook do WAHA NUNCA pode ser derrubado. Toda exceção é
logada e devolvemos 200 — o gateway não deve reenviar nem entrar em retry/backoff.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.domain.survey.brain import OPT_OUT_CONFIRM_MSG, SurveyBrain
from app.domain.survey.resolver import (
    DEFAULT_REASON_PROMPT,
    DEFAULT_RETRY_MSG,
    DEFAULT_THANKS_MSG,
    SurveyContextResolver,
)
from app.models.core import Contact, Organization
from app.services.embeddings import EmbeddingService, get_embedder
from app.services.llm import GroqLLM
from app.services.waha import WAHAService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

# Textos que o próprio sistema envia — usados para suprimir eco no modo self-chat.
# (Respostas dinâmicas do brain são cobertas pelo filtro source=="api".)
_SYSTEM_TEXTS = {DEFAULT_REASON_PROMPT, DEFAULT_THANKS_MSG, DEFAULT_RETRY_MSG, OPT_OUT_CONFIRM_MSG}


def _make_brain() -> SurveyBrain | None:
    """SurveyBrain quando o LLM está configurado; None = fluxo determinístico puro."""
    if not settings.llm_enabled or not settings.groq_api_key:
        return None
    return SurveyBrain(GroqLLM(settings.groq_api_key, settings.groq_model))


def _make_embedder() -> EmbeddingService | None:
    """Embedder (RAG) quando o LLM está ligado; singleton lazy de processo."""
    if not settings.llm_enabled:
        return None
    return get_embedder()

# Cache de processo LID -> telefone (mapeamento estável; evita 1 GET por mensagem).
_LID_CACHE: dict[str, str] = {}


async def _resolve_chat_phone(raw_id: str) -> str | None:
    """'55...@c.us' -> '55...'; '...@lid' -> telefone real via WAHA (com cache)."""
    if not raw_id.endswith("@lid"):
        return raw_id.split("@", 1)[0] or None
    cached = _LID_CACHE.get(raw_id)
    if cached:
        return cached
    waha = WAHAService(settings.waha_base_url, settings.waha_api_key, settings.waha_session)
    resolved = await waha.resolve_lid(raw_id)
    if resolved:
        _LID_CACHE[raw_id] = resolved
    return resolved


def _is_system_echo(body: str) -> bool:
    """True se o texto é (quase certamente) eco de mensagem enviada por nós."""
    if body in _SYSTEM_TEXTS:
        return True
    # Pergunta NPS renderizada pelo dispatcher: "Oi <nome>! <pergunta com 0 a 10>".
    return body.startswith("Oi") and "0 a 10" in body


def _extract_inbound(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza os dois formatos de payload inbound do WAHA num dict simples.

    Formato A (Nexus): {"event":"message","data":{"messages":[{...}]}}
    Formato B:         {"event":"message","payload":{"from":"...","body":"..."}}

    Retorna {"from","body","message_id"} para mensagens inbound válidas, ou None
    para qualquer coisa que devamos ignorar (não-mensagem, fromMe, sem body...).
    """
    if not isinstance(payload, dict):
        return None

    # Só nos interessam eventos de mensagem. `message.any` é o evento do WAHA
    # que cobre todas as mensagens (inclusive fromMe — necessário p/ self-chat);
    # `message` é o evento clássico só-inbound.
    if payload.get("event") not in (None, "message", "message.any"):
        return None

    # Formato A: data.messages[] — pegamos a primeira mensagem inbound.
    data = payload.get("data")
    msg: dict[str, Any] | None = None
    if isinstance(data, dict):
        messages = data.get("messages")
        if isinstance(messages, list):
            for m in messages:
                if isinstance(m, dict) and not m.get("fromMe"):
                    msg = m
                    break

    # Formato B: payload{} direto.
    if msg is None:
        inner = payload.get("payload")
        if isinstance(inner, dict):
            msg = inner

    if not isinstance(msg, dict):
        return None

    # Ignora mensagens enviadas por nós — exceto, em modo de teste, o "chat
    # consigo mesmo" (from == to), que viabiliza o E2E com um único número
    # (a resposta digitada no celular conectado chega com fromMe=true; o WAHA
    # só a entrega via evento `message.any`). Mesmo nesse modo, ecos das
    # mensagens que o próprio bot envia precisam ser descartados — senão a
    # retry_msg entra em loop infinito (eco → retry → eco...). Dois filtros:
    # `source == "api"` (mensagem criada via API do WAHA) e, como fallback
    # para engines que não preenchem `source`, os textos conhecidos do sistema.
    self_check_to: str | None = None
    if msg.get("fromMe"):
        if not settings.self_chat_test:
            return None
        sender_raw = str(msg.get("from") or "")
        to_raw = str(msg.get("to") or "")
        if not sender_raw or not to_raw:
            return None
        if msg.get("source") == "api":
            return None
        echo_body = str(msg.get("body") or "").strip()
        if not echo_body or _is_system_echo(echo_body):
            return None
        if sender_raw != to_raw:
            # O WhatsApp mistura formatos no self-chat (ex.: from='55...@c.us',
            # to='...@lid' — o MESMO número). Sem @lid envolvido, ids diferentes
            # são outro chat: descarta. Com @lid, só dá pra confirmar resolvendo
            # o LID (I/O) — marcamos para o handler verificar.
            if not (sender_raw.endswith("@lid") or to_raw.endswith("@lid")):
                return None
            self_check_to = to_raw

    sender = msg.get("from")
    body = msg.get("body")
    if not sender or body is None:
        return None

    body = str(body).strip()
    if not body:
        return None

    # 5524999214290@c.us -> 5524999214290
    phone = str(sender).split("@", 1)[0]
    # `from_raw` preserva o domínio (@c.us/@lid) — o handler precisa dele para
    # resolver LIDs (self-chat e alguns contatos chegam como '...@lid').
    out = {"from": phone, "from_raw": str(sender), "body": body, "message_id": msg.get("id")}
    if self_check_to is not None:
        out["self_check_to"] = self_check_to
    return out


@router.post("/webhook/waha")
async def waha_webhook(request: Request, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Recebe um evento do WAHA. SEMPRE responde 200 rápido."""
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001 — corpo inválido/não-JSON: ignora sem derrubar.
        logger.warning("WAHA webhook: corpo inválido (não-JSON)")
        return {"status": "ignored"}

    inbound = _extract_inbound(raw)
    if inbound is None:
        if settings.self_chat_test:
            # Modo de teste é verboso de propósito: dá visibilidade do que foi descartado.
            import json as _json

            logger.warning(
                "[self-chat-test] descartado; raw=%s",
                _json.dumps(raw, ensure_ascii=False, default=str)[:1500],
            )
        return {"status": "ignored"}

    phone = inbound["from"]
    body = inbound["body"]
    message_id = inbound["message_id"]

    # Chats identificados por LID (self-chat incluso): resolve para o telefone
    # real via WAHA, com cache de processo (o mapeamento LID<->número é estável).
    if inbound["from_raw"].endswith("@lid"):
        resolved = await _resolve_chat_phone(inbound["from_raw"])
        if resolved:
            phone = resolved
        else:
            logger.warning("WAHA webhook: LID %s não resolvido; usando bruto", inbound["from_raw"])

    # Self-chat com from/to em formatos distintos (c.us vs lid): confirma que os
    # dois lados apontam para o MESMO número; caso contrário é mensagem nossa
    # para outro chat e deve ser ignorada.
    self_check_to = inbound.get("self_check_to")
    if self_check_to is not None:
        to_phone = await _resolve_chat_phone(self_check_to)
        if to_phone is None or to_phone != phone:
            if settings.self_chat_test:
                logger.warning(
                    "[self-chat-test] descartado (from!=to após resolução): from=%s to=%s",
                    phone, to_phone,
                )
            return {"status": "ignored"}

    if settings.self_chat_test:
        logger.warning("[self-chat-test] aceito: phone=%s body=%.60r", phone, body)

    # TODO(Fase 1): dedup por waha_message_id (model Message só existe na Fase 1).
    # Hoje não há onde gravar o id processado; aceitamos reprocessar em caso de retry.
    _ = message_id

    try:
        # --- Resolução da organização --------------------------------------
        # Fase 0: org única do piloto, pelo slug default.
        # TODO(Fase 1): resolver via canal/WhatsAppChannel pelo número de destino.
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == settings.default_org_slug)
            )
        ).scalar_one_or_none()
        if org is None:
            logger.warning("WAHA webhook: org '%s' não encontrada", settings.default_org_slug)
            return {"status": "no_org"}

        # --- get-or-create do contato --------------------------------------
        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.organization_id == org.id,
                    Contact.phone == phone,
                )
            )
        ).scalar_one_or_none()
        if contact is None:
            contact = Contact(organization_id=org.id, phone=phone, opt_in=False)
            session.add(contact)
            await session.flush()  # materializa contact.id para o resolver.

        # --- resolução de pesquisa -----------------------------------------
        resolver = SurveyContextResolver(
            session, org.id, brain=_make_brain(), embedder=_make_embedder()
        )
        reply = await resolver.resolve(contact.id, body)

        if reply is not None:
            waha = WAHAService(
                settings.waha_base_url,
                settings.waha_api_key,
                settings.waha_session,
            )
            await waha.send_text(chat_id=phone, text=reply.text)
            await session.commit()
            return {"status": "survey_reply", "closed": reply.closed}

        # Sem pesquisa pendente.
        # TODO(Fase 1): encaminhar ao orchestrator/agente (RAG + LLM) aqui.
        await session.commit()
        return {"status": "no_pending_survey"}

    except Exception:  # noqa: BLE001 — webhook do WAHA não pode cair; loga e devolve 200.
        logger.exception("WAHA webhook: erro ao processar mensagem de %s", phone)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("WAHA webhook: rollback falhou")
        return {"status": "error"}
