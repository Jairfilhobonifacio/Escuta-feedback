"""Webhook do WAHA — porta de entrada das mensagens inbound do WhatsApp.

Fase 0: liga a mensagem inbound diretamente ao SurveyContextResolver. Quando a
mensagem é resposta de uma pesquisa pendente, responde via WAHA e fecha o loop.
Quando não há pesquisa pendente, apenas confirma (Fase 1: cai no orchestrator/agente).

Princípio inegociável: o webhook do WAHA NUNCA pode ser derrubado. Toda exceção é
logada e devolvemos 200 — o gateway não deve reenviar nem entrar em retry/backoff.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._security import require_waha_webhook_secret
from app.config import settings
from app.db import get_session
from app.domain.survey.brain import OPT_OUT_CONFIRM_MSG, SurveyBrain
from app.domain.survey.message_handler import InboundMessageHandler
from app.domain.survey.resolver import (
    DEFAULT_REASON_PROMPT,
    DEFAULT_RETRY_MSG,
    DEFAULT_THANKS_MSG,
    SurveyContextResolver,
)
from app.models.core import Contact, Organization
from app.models.survey import Message
from app.services.embeddings import EmbeddingService, get_embedder
from app.services.llm import GroqLLM
from app.services.waha import WAHAService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

# Índice único parcial que faz o dedup atômico do transcript (ver models/survey.py).
# Só uma violação DESTE índice é "turno duplicado"; qualquer outra (FK, NOT NULL,
# outro UNIQUE) é erro de verdade e NÃO pode ser silenciada como duplicata.
_DEDUP_INDEX = "uq_messages_org_channel_msg_id"


def _is_dedup_violation(exc: IntegrityError) -> bool:
    """True só se o IntegrityError for da colisão no índice de dedup do transcript.

    Inspeciona a exceção do driver (`exc.orig`) de forma defensiva, cobrindo os dois
    backends do projeto:
      - Postgres/asyncpg: a exceção carrega `constraint_name` (== nome do índice).
      - SQLite/aiosqlite (testes): a mensagem é "UNIQUE constraint failed:
        messages.organization_id, messages.channel_msg_id" — sem o nome do índice;
        casamos pelas colunas (org + channel_msg_id na tabela messages).
    Em dúvida, retorna False (re-levanta) — é mais seguro reprocessar/logar como erro
    do que perder uma mensagem tratando outra violação como duplicata.
    """
    orig = getattr(exc, "orig", None)
    # Caminho Postgres/asyncpg: nome da constraint/índice exposto diretamente.
    constraint = getattr(orig, "constraint_name", None)
    if constraint:
        return constraint == _DEDUP_INDEX
    text = str(orig or exc).lower()
    if _DEDUP_INDEX in text:
        return True
    # Caminho SQLite (sem nome de índice na mensagem): casa pelas colunas do índice.
    return (
        "unique constraint failed" in text
        and "messages.organization_id" in text
        and "messages.channel_msg_id" in text
    )


# Textos que o próprio sistema envia — usados para suprimir eco no modo self-chat.
# (Respostas dinâmicas do brain são cobertas pelo filtro source=="api".)
_SYSTEM_TEXTS = {DEFAULT_REASON_PROMPT, DEFAULT_THANKS_MSG, DEFAULT_RETRY_MSG, OPT_OUT_CONFIRM_MSG}


def _make_brain() -> SurveyBrain | None:
    """SurveyBrain quando o LLM está configurado; None = fluxo determinístico puro."""
    if not settings.llm_enabled or not settings.groq_api_key:
        return None
    return SurveyBrain(
        GroqLLM(
            settings.groq_api_key,
            settings.groq_model,
            fallback_model=settings.groq_fallback_model or None,
        )
    )


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


def _extract_waha_session(payload: dict[str, Any]) -> str | None:
    """Nome da sessão WAHA que recebeu o evento, ou None.

    O WAHA carimba a sessão no topo do envelope (`{"event":..,"session":"default",..}`).
    Alguns formatos a repetem dentro de `payload`/`data` — cobrimos os três, sem nunca
    levantar. É a CHAVE multi-tenant: cada org liga seu número/sessão WAHA própria, e a
    resolução abaixo casa essa sessão com a org dona.
    """
    if not isinstance(payload, dict):
        return None
    for container in (payload, payload.get("payload"), payload.get("data")):
        if isinstance(container, dict):
            sess = container.get("session")
            if isinstance(sess, str) and sess.strip():
                return sess.strip()
    return None


async def _resolve_org_for_inbound(
    session: AsyncSession, waha_session: str | None
) -> Organization | None:
    """Resolve a ORGANIZAÇÃO dona da mensagem inbound a partir da sessão WAHA.

    🔑 PONTO DE GO-LIVE MULTI-TENANT. Cada org liga seu próprio número/sessão WAHA e
    grava o nome dessa sessão em `Organization.settings["waha_session"]`. Aqui casamos a
    sessão que recebeu o evento com a org dona — assim mensagens de números diferentes
    caem em orgs diferentes (sem isso, todo inbound vai para uma única org hardcoded e
    dados de tenants distintos se misturam).

    COMPATIBILIDADE COM O PILOTO SINGLE-ORG: se a sessão não casa nenhuma org (caso do
    piloto, que ainda não preencheu `settings["waha_session"]`), FALLBACK para a org do
    `default_org_slug` — comportamento idêntico ao anterior. Retorna None só quando nem a
    resolução por sessão nem o fallback acham uma org (banco sem a org default).
    """
    # 1) Resolução multi-tenant: org cuja settings["waha_session"] == sessão do evento.
    if waha_session:
        # Filtra no banco pela chave JSON `waha_session` (JSON path portável PG+SQLite).
        # Em dúvida sobre o dialeto, cai para varredura em Python logo abaixo.
        candidatas = (
            (await session.execute(select(Organization))).scalars().all()
        )
        for org in candidatas:
            if (org.settings or {}).get("waha_session") == waha_session:
                return org

    # 2) Fallback single-org (piloto): a org do slug default. Mantém o comportamento atual.
    return (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()


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
    if not sender:
        return None

    # Detecta ÁUDIO (voz): WAHA manda type 'audio'/'ptt'/'voice' e/ou media com
    # mimetype 'audio/...'. Nesses casos não há body de texto — transcrevemos depois.
    mtype = str(msg.get("type") or "").lower()
    media = msg.get("media") if isinstance(msg.get("media"), dict) else {}
    is_audio = mtype in ("audio", "ptt", "voice") or str(media.get("mimetype") or "").startswith("audio")

    body = str(msg.get("body") or "").strip()
    if not is_audio and not body:
        return None  # nem texto nem áudio: ignora

    # 5524999214290@c.us -> 5524999214290
    phone = str(sender).split("@", 1)[0]
    # `from_raw` preserva o domínio (@c.us/@lid) — o handler precisa dele para
    # resolver LIDs (self-chat e alguns contatos chegam como '...@lid').
    out = {
        "from": phone,
        "from_raw": str(sender),
        "body": body,
        "message_id": msg.get("id"),
        "media_type": "audio" if is_audio else None,
        "media_url": media.get("url") if is_audio else None,
        "media_data": media.get("data") if is_audio else None,
        "media_mimetype": media.get("mimetype") if is_audio else None,
    }
    if self_check_to is not None:
        out["self_check_to"] = self_check_to
    return out


# A captura na Mega Central da inbound SEM pesquisa pendente (antes inline aqui como
# `_capturar_resposta_central` + `_contato_eh_churn`) mora agora em
# app/domain/survey/message_handler.py (InboundMessageHandler) — funil próprio,
# best-effort, gated e testável, no espírito do SurveyContextResolver.


@router.post("/webhook/waha")
async def waha_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_waha_webhook_secret),
) -> dict[str, Any]:
    """Recebe um evento do WAHA. SEMPRE responde 200 rápido.

    Autenticação de ORIGEM via `require_waha_webhook_secret` (header X-Webhook-Secret):
    quando WAHA_WEBHOOK_SECRET está setado, header ausente/errado é rejeitado com 401
    ANTES de chegar aqui (fail-closed). Sem o segredo configurado, libera + WARN — o
    piloto que ainda não configurou segue funcionando. ⚠️ Setar em produção.
    """
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

    # Dedup por waha_message_id é feito adiante (após resolver o contato), via
    # Message.channel_msg_id — curto-circuita retries do gateway.

    # Sessão WAHA que recebeu o evento (chave multi-tenant) — lida do envelope bruto.
    waha_session = _extract_waha_session(raw)

    try:
        # --- Resolução da organização --------------------------------------
        # 🔑 GO-LIVE MULTI-TENANT: resolve a org dona pela sessão/número WAHA do evento
        # (Organization.settings["waha_session"]). Sem casamento (piloto single-org),
        # FALLBACK para a org do default_org_slug — comportamento idêntico ao anterior.
        org = await _resolve_org_for_inbound(session, waha_session)
        if org is None:
            logger.warning(
                "WAHA webhook: org não resolvida (waha_session=%r, default=%r)",
                waha_session, settings.default_org_slug,
            )
            return {"status": "no_org"}

        # Sessão WAHA de SAÍDA: responde pela sessão da PRÓPRIA org (chave multi-tenant),
        # com fallback p/ a sessão default (piloto single-org → idêntico ao anterior).
        org_waha_session = (org.settings or {}).get("waha_session") or settings.waha_session

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

        # --- dedup por id de mensagem do WAHA --------------------------------
        # Em retry do gateway o MESMO message_id chega de novo. Se já gravamos
        # esse turno (Message.channel_msg_id), encerramos: não reprocessa a
        # pesquisa (evita reenviar a resposta), não recaptura o feedback e não
        # duplica o transcript. Best-effort: sem id, segue (não dá pra deduplicar).
        if message_id is not None:
            ja_visto = (
                await session.execute(
                    select(Message.id).where(
                        Message.organization_id == org.id,
                        Message.contact_id == contact.id,
                        Message.channel_msg_id == str(message_id),
                    )
                )
            ).first()
            if ja_visto is not None:
                await session.commit()
                return {"status": "duplicate"}

        # --- áudio: transcreve (Groq Whisper) e segue como se fosse texto ----
        audio_failed = False
        if inbound.get("media_type") == "audio":
            from app.services.audio import transcribe_audio

            transcribed = await transcribe_audio(
                url=inbound.get("media_url"),
                data_b64=inbound.get("media_data"),
                mimetype=inbound.get("media_mimetype"),
                waha_api_key=settings.waha_api_key,
                groq_api_key=settings.groq_api_key,
                groq_model=settings.groq_whisper_model,
            )
            if transcribed:
                body = transcribed
                logger.info("WAHA webhook: áudio de %s transcrito (%d chars)", phone, len(body))
            else:
                body = "[áudio recebido — não transcrito]"
                audio_failed = True

        # --- memória da conversa: grava a mensagem inbound (transcript) -----
        # Insert ATÔMICO/IDEMPOTENTE: o índice único parcial
        # uq_messages_org_channel_msg_id barra um 2º turno com o MESMO
        # (org, channel_msg_id). Em retry concorrente do gateway o SELECT de dedup
        # acima pode não ver a 1ª gravação (corrida) — então blindamos no banco:
        # tenta inserir num savepoint e, se o índice acusar duplicata, absorve o
        # IntegrityError (rollback do savepoint) e encerra como 'duplicate' em vez
        # de quebrar. msg_metadata montado por copia-edita-reatribui (nunca in-place).
        from app.schemas.messages import MessageMetadata

        msg_meta = MessageMetadata(
            source_event="message",
            media_type="audio" if inbound.get("media_type") == "audio" else None,
            transcribed=True if inbound.get("media_type") == "audio" else None,
        ).to_jsonb()
        try:
            async with session.begin_nested():
                session.add(
                    Message(
                        organization_id=org.id,
                        contact_id=contact.id,
                        direction="inbound",
                        body=body,
                        channel_msg_id=str(message_id) if message_id is not None else None,
                        msg_metadata=msg_meta or None,
                    )
                )
                await session.flush()
        except IntegrityError as exc:
            # SÓ trata como duplicata se a violação for do índice de dedup. Qualquer
            # outra IntegrityError (FK, NOT NULL, outro UNIQUE) NÃO pode ser silenciada
            # como "duplicata" — antes esse except largo perdia a mensagem sem retry.
            # Re-levanta para cair no `except Exception` externo (logger.exception +
            # rollback + status 'error'). O savepoint já fez rollback do insert.
            if not _is_dedup_violation(exc):
                logger.error(
                    "WAHA webhook: IntegrityError NÃO-dedup ao gravar transcript "
                    "(channel_msg_id=%s) — re-levantando",
                    message_id,
                )
                raise
            # Duplicata absorvida pelo índice único parcial — o savepoint já fez
            # rollback do insert; não reprocessa nada e não duplica o transcript.
            logger.info(
                "WAHA webhook: turno duplicado (channel_msg_id=%s) absorvido pelo índice único",
                message_id,
            )
            await session.commit()
            return {"status": "duplicate"}

        # Áudio que não transcreveu: acolhe e encerra (não joga marcador no resolver).
        if audio_failed:
            waha = WAHAService(settings.waha_base_url, settings.waha_api_key, org_waha_session)
            try:
                await waha.send_text(
                    chat_id=phone, text="recebi seu áudio 🎧 vou ouvir com calma e já te respondo!"
                )
            except Exception:  # noqa: BLE001
                logger.warning("WAHA webhook: falha ao responder áudio não transcrito", exc_info=True)
            await session.commit()
            return {"status": "audio_not_transcribed"}

        # --- hand-off: contato em atendimento humano → o bot PAUSA ----------
        if contact.needs_human_handoff:
            await session.commit()  # guarda a mensagem; um humano responde manualmente
            return {"status": "human_handoff"}

        # --- resolução de pesquisa -----------------------------------------
        waha = WAHAService(
            settings.waha_base_url, settings.waha_api_key, org_waha_session
        )
        resolver = SurveyContextResolver(
            session, org.id,
            brain=_make_brain(), embedder=_make_embedder(),
            messaging=waha, waha_session=org_waha_session,
        )
        reply = await resolver.resolve(contact.id, body)

        if reply is not None:
            await waha.send_text(chat_id=phone, text=reply.text)
            # memória da conversa: grava a resposta outbound do bot.
            session.add(
                Message(
                    organization_id=org.id,
                    contact_id=contact.id,
                    survey_response_id=uuid.UUID(reply.survey_response_id),
                    direction="outbound",
                    body=reply.text,
                )
            )
            await session.commit()
            return {"status": "survey_reply", "closed": reply.closed}

        # Sem pesquisa pendente: cai no funil de inbound sem-pesquisa, que CAPTURA
        # na Mega Central para o lead não sumir (best-effort, gated, NÃO dispara
        # WhatsApp). (áudio-falho e hand-off já retornaram acima; aqui `body` é
        # texto válido — transcrito ou digitado.) Fase 1: o handler ganha o
        # encaminhamento ao orchestrator/agente.
        handler = InboundMessageHandler(session, org.id)
        outcome = await handler.handle(contact, body, message_id)
        await session.commit()
        return {"status": outcome.status}

    except Exception:  # noqa: BLE001 — webhook do WAHA não pode cair; loga e devolve 200.
        logger.exception("WAHA webhook: erro ao processar mensagem de %s", phone)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("WAHA webhook: rollback falhou")
        return {"status": "error"}
