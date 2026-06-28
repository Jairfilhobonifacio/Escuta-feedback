"""Testes da API de envio 1:1 no WhatsApp (app/api/whatsapp.py).

Mesma infra dos demais testes de API: app real + SQLite in-memory (override de
get_session) + WAHA fake (override de get_waha). NENHUM teste toca rede nem chama
o envio real contra a Bizzu — o FakeWAHA registra o que SERIA enviado e o controle
de "conectado" é injetado.

Cobertura:
- PREVIEW (sem confirm): preview=true, não chama envio, reflete waha_conectado,
  e expõe alcancavel/is_grupo.
- confirm=true com WAHA DESCONECTADO -> 409 (e nada enviado).
- confirm=true com telefone NÃO-celular E SEM inbound -> 422 (e nada enviado).
- confirm=true com telefone NÃO-celular MAS COM inbound -> passa do gate (alcançável):
  envia (fake) — dá pra responder quem te escreveu.
- confirm=true para GRUPO (mesmo com inbound) -> 422 (grupo não recebe 1:1).
- confirm=true caminho feliz: envia (fake), registra abordagem + selo 'contatado'
  + Message outbound.
- conversations expõe is_grupo e respeita excluir_grupos.
- thread expõe alcancavel/is_grupo no contato.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.whatsapp import get_waha  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Message  # noqa: E402


class FakeWAHA:
    """Dublê do WAHAService: controla 'conectado' e registra o que SERIA enviado.

    `is_connected` devolve o flag injetado (sem rede). `send_text` apenas guarda o
    envio em `self.sent` e devolve um id fixo — nunca toca a rede/Bizzu.
    """

    def __init__(self, connected: bool = True, msg_id: str = "fake-wa-1") -> None:
        self.connected = connected
        self.msg_id = msg_id
        self.sent: List[Dict[str, Any]] = []
        self.chats: List[Dict[str, Any]] = []
        self.messages_by_chat: Dict[str, List[Dict[str, Any]]] = {}
        self.lid_map: Dict[str, str] = {}

    async def is_connected(self, session: str = None) -> bool:
        return self.connected

    async def get_session_status(self, session: str = None) -> Optional[str]:
        return "WORKING" if self.connected else None

    async def send_text(self, chat_id: str, text: str, session: str = None) -> Dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "text": text, "session": session})
        return {"success": True, "data": {"id": self.msg_id}}

    async def get_chats(self, session: str = None, limit: int = 1000) -> List[Dict[str, Any]]:
        return self.chats[:limit]

    async def get_chat_messages(
        self,
        chat_id: str,
        session: str = None,
        limit: int = 100,
        download_media: bool = False,
    ) -> List[Dict[str, Any]]:
        return self.messages_by_chat.get(chat_id, [])[:limit]

    async def resolve_lid(self, lid: str, session: str = None) -> Optional[str]:
        return self.lid_map.get(lid)


@pytest_asyncio.fixture
async def make_client(session):
    """Fábrica de client com um FakeWAHA injetável (conectado/desconectado)."""

    async def _session_override():
        yield session

    def _build(fake: FakeWAHA) -> AsyncClient:
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_waha] = lambda: fake
        transport = ASGITransport(app=app)
        c = AsyncClient(transport=transport, base_url="http://test")
        c.fake_waha = fake  # type: ignore[attr-defined]
        return c

    try:
        yield _build
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _contact(session, org, phone, name="Cliente", **kw):
    c = Contact(
        organization_id=org.id,
        phone=phone,
        name=name,
        opt_in=kw.pop("opt_in", True),
        profile_data=kw.pop("profile_data", {}),
    )
    session.add(c)
    await session.flush()
    await session.commit()
    return c


# DDI+DDD+9+8 = celular BR válido (classe 'mobile' do validador).
_CEL = "5524999214290"
# Fixo (sem o 9) -> NÃO é celular válido.
_FIXO = "552433221100"
# JID de grupo do WhatsApp (classe 'group' do validador) -> nunca recebe 1:1.
_GRUPO = "120363041234567890"


@pytest.mark.asyncio
async def test_preview_nao_envia(make_client, org, session):
    """Sem confirm: preview=true, NÃO chama send_text, e reflete waha_conectado."""
    contact = await _contact(session, org, _CEL)
    fake = FakeWAHA(connected=True)
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "Oi! Tudo bem?"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preview"] is True
    assert data["para"] == _CEL
    assert data["tem_whatsapp"] is True
    # Celular válido -> alcançável; não é grupo.
    assert data["alcancavel"] is True
    assert data["is_grupo"] is False
    assert data["texto"] == "Oi! Tudo bem?"
    assert data["waha_conectado"] is True
    # Nada foi enviado.
    assert fake.sent == []
    # Nenhuma Message gravada.
    msgs = (await session.execute(select(Message))).scalars().all()
    assert msgs == []


@pytest.mark.asyncio
async def test_preview_reflete_waha_desconectado(make_client, org, session):
    """Preview com WAHA off: waha_conectado=false, ainda assim não envia."""
    contact = await _contact(session, org, _CEL)
    fake = FakeWAHA(connected=False)
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "Oi!"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preview"] is True
    assert data["waha_conectado"] is False
    assert fake.sent == []


@pytest.mark.asyncio
async def test_confirm_waha_desconectado_409(make_client, org, session):
    """confirm=true com WAHA desconectado -> 409 e NADA enviado."""
    contact = await _contact(session, org, _CEL)
    fake = FakeWAHA(connected=False)
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "Oi!", "confirm": True},
        )
    assert r.status_code == 409, r.text
    assert "não conectado" in r.json()["detail"].lower()
    assert fake.sent == []
    msgs = (await session.execute(select(Message))).scalars().all()
    assert msgs == []


@pytest.mark.asyncio
async def test_confirm_telefone_nao_celular_sem_inbound_422(make_client, org, session):
    """confirm=true com telefone NÃO-celular E SEM inbound -> 422; NADA enviado (WAHA on).

    Fixo, sem prova de WhatsApp (nenhuma mensagem recebida) -> não-alcançável.
    """
    contact = await _contact(session, org, _FIXO)
    fake = FakeWAHA(connected=True)
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "Oi!", "confirm": True},
        )
    assert r.status_code == 422, r.text
    assert fake.sent == []
    msgs = (await session.execute(select(Message))).scalars().all()
    assert msgs == []


@pytest.mark.asyncio
async def test_confirm_sem_celular_mas_com_inbound_envia(make_client, org, session):
    """confirm=true: telefone NÃO-celular MAS COM >=1 inbound -> alcançável: NÃO dá 422.

    Prova de que está no WhatsApp (ele te escreveu) destrava a resposta 1:1 mesmo
    com telefone em formato antigo. Com FakeWAHA conectado, envia de verdade (fake).
    """
    contact = await _contact(session, org, _FIXO)
    # Inbound prévio = prova de WhatsApp -> torna o contato alcançável.
    session.add(
        Message(
            organization_id=org.id,
            contact_id=contact.id,
            direction="inbound",
            body="oi, vi a promo",
        )
    )
    await session.commit()

    fake = FakeWAHA(connected=True)
    # PREVIEW reflete alcancavel=true mesmo sem celular válido.
    async with make_client(fake) as client:
        prev = (
            await client.post(
                f"/api/contacts/{contact.id}/whatsapp/send",
                json={"texto": "oi de volta"},
            )
        ).json()
    assert prev["tem_whatsapp"] is False
    assert prev["alcancavel"] is True
    assert prev["is_grupo"] is False

    # ENVIO passa do gate (não dá 422) e envia.
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "oi de volta", "confirm": True},
        )
    assert r.status_code == 200, r.text
    assert r.json()["enviado"] is True
    assert len(fake.sent) == 1
    out = (
        await session.execute(select(Message).where(Message.direction == "outbound"))
    ).scalars().all()
    assert len(out) == 1 and out[0].body == "oi de volta"


@pytest.mark.asyncio
async def test_confirm_grupo_com_inbound_422(make_client, org, session):
    """confirm=true para GRUPO -> 422 mesmo COM inbound (grupo não recebe 1:1)."""
    contact = await _contact(session, org, _GRUPO, name="Turma TI")
    # Mesmo havendo inbound (mensagem no grupo), grupo nunca é alcançável 1:1.
    session.add(
        Message(
            organization_id=org.id,
            contact_id=contact.id,
            direction="inbound",
            body="alguém tem o material?",
        )
    )
    await session.commit()

    fake = FakeWAHA(connected=True)
    # PREVIEW marca is_grupo=true e alcancavel=false.
    async with make_client(fake) as client:
        prev = (
            await client.post(
                f"/api/contacts/{contact.id}/whatsapp/send",
                json={"texto": "oi"},
            )
        ).json()
    assert prev["is_grupo"] is True
    assert prev["alcancavel"] is False

    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "oi", "confirm": True},
        )
    assert r.status_code == 422, r.text
    assert "grupo" in r.json()["detail"].lower()
    assert fake.sent == []
    out = (
        await session.execute(select(Message).where(Message.direction == "outbound"))
    ).scalars().all()
    assert out == []


@pytest.mark.asyncio
async def test_confirm_envia_e_registra(make_client, org, session):
    """confirm=true + WAHA on + celular válido: envia (fake), registra abordagem,
    aplica selo 'contatado' e grava Message outbound."""
    contact = await _contact(session, org, _CEL)
    fake = FakeWAHA(connected=True)
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/send",
            json={"texto": "Volta pra gente!", "oferta": "30% off", "por": "Felipe", "confirm": True},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enviado"] is True
    assert data["para"] == _CEL
    assert "contatado" in data["selos"]
    assert data["abordagem"]["canal"] == "whatsapp"
    assert data["abordagem"]["oferta"] == "30% off"

    # O envio (fake) foi registrado uma vez, com o texto certo.
    assert len(fake.sent) == 1
    assert fake.sent[0]["text"] == "Volta pra gente!"

    # Persistência: abordagem + selo no profile_data; Message outbound gravada.
    await session.refresh(contact)
    abordagens = (contact.profile_data or {}).get("abordagens") or []
    assert len(abordagens) == 1
    assert "contatado" in ((contact.profile_data or {}).get("selos") or [])

    msgs = (await session.execute(select(Message))).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].direction == "outbound"
    assert msgs[0].body == "Volta pra gente!"
    assert msgs[0].channel_msg_id == "fake-wa-1"


# --- LEITURA: conversas + thread (painel de chat) ----------------------------


def _dt(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


async def _msg(session, org, contact, direction, body, at):
    session.add(
        Message(
            organization_id=org.id,
            contact_id=contact.id,
            direction=direction,
            body=body,
            created_at=at,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_conversations_ordena_por_ultima_mensagem(make_client, org, session):
    """GET /whatsapp/conversations: 1 item por contato com mensagem, ordenado pela
    última mensagem desc; traz preview, direção e total."""
    ana = await _contact(session, org, _CEL, "Ana", profile_data={"selos": ["contatado"]})
    bob = await _contact(session, org, "5531988887777", "Bob")
    # Ana: 2 msgs (a última é a mais nova de todas). Bob: 1 msg no meio.
    await _msg(session, org, ana, "inbound", "oi, cancelei", _dt(2026, 6, 10))
    await _msg(session, org, bob, "inbound", "tenho material de TI?", _dt(2026, 6, 11))
    await _msg(session, org, ana, "outbound", "que pena! posso ajudar?", _dt(2026, 6, 12))
    await session.commit()

    fake = FakeWAHA(connected=False)
    async with make_client(fake) as client:
        data = (await client.get("/api/whatsapp/conversations")).json()

    assert data["total"] == 2
    convs = data["conversations"]
    # Ana primeiro (última mensagem 12/06 > Bob 11/06).
    assert convs[0]["nome"] == "Ana"
    assert convs[0]["total"] == 2
    assert convs[0]["ultima_mensagem"] == "que pena! posso ajudar?"
    assert convs[0]["ultima_direction"] == "outbound"
    assert convs[0]["tem_whatsapp"] is True
    assert "contatado" in convs[0]["selos"]
    assert convs[1]["nome"] == "Bob"
    assert convs[1]["total"] == 1
    # is_grupo presente em cada item (Ana e Bob são leads 1:1).
    assert convs[0]["is_grupo"] is False
    assert convs[1]["is_grupo"] is False

    # search filtra por nome.
    async with make_client(fake) as client:
        data = (await client.get("/api/whatsapp/conversations", params={"search": "bob"})).json()
    assert data["total"] == 1 and data["conversations"][0]["nome"] == "Bob"


@pytest.mark.asyncio
async def test_conversations_excluir_grupos(make_client, org, session):
    """conversations?excluir_grupos=true tira os contatos cujo phone é classe 'group'."""
    ana = await _contact(session, org, _CEL, "Ana")
    turma = await _contact(session, org, _GRUPO, "Turma TI")
    await _msg(session, org, ana, "inbound", "oi", _dt(2026, 6, 10))
    await _msg(session, org, turma, "inbound", "alguém tem material?", _dt(2026, 6, 11))
    await session.commit()

    fake = FakeWAHA(connected=False)
    # excluir_grupos=false (explícito): os dois aparecem; o grupo vem marcado
    # is_grupo=true. (O default agora é TRUE — grupos saem por padrão; este caso
    # pede explicitamente para incluí-los.)
    async with make_client(fake) as client:
        data = (
            await client.get(
                "/api/whatsapp/conversations", params={"excluir_grupos": "false"}
            )
        ).json()
    assert data["total"] == 2
    by_name = {c["nome"]: c for c in data["conversations"]}
    assert by_name["Turma TI"]["is_grupo"] is True
    assert by_name["Ana"]["is_grupo"] is False

    # Default (sem param) já exclui grupos: o grupo some, só sobra a Ana.
    async with make_client(fake) as client:
        data = (await client.get("/api/whatsapp/conversations")).json()
    assert data["total"] == 1
    assert data["conversations"][0]["nome"] == "Ana"

    # E com excluir_grupos=true explícito: idem (grupo fora).
    async with make_client(fake) as client:
        data = (
            await client.get(
                "/api/whatsapp/conversations", params={"excluir_grupos": "true"}
            )
        ).json()
    assert data["total"] == 1
    assert data["conversations"][0]["nome"] == "Ana"


@pytest.mark.asyncio
async def test_thread_cronologica(make_client, org, session):
    """GET /contacts/{id}/whatsapp/thread: mensagens em ordem cronológica asc + contato."""
    ana = await _contact(session, org, _CEL, "Ana")
    await _msg(session, org, ana, "inbound", "primeira", _dt(2026, 6, 10, 9))
    await _msg(session, org, ana, "outbound", "segunda", _dt(2026, 6, 10, 10))
    await _msg(session, org, ana, "inbound", "terceira", _dt(2026, 6, 10, 11))
    await session.commit()

    fake = FakeWAHA(connected=False)
    async with make_client(fake) as client:
        data = (await client.get(f"/api/contacts/{ana.id}/whatsapp/thread")).json()

    assert data["contact"]["nome"] == "Ana"
    assert data["contact"]["tem_whatsapp"] is True
    # Celular válido -> alcançável; não é grupo.
    assert data["contact"]["alcancavel"] is True
    assert data["contact"]["is_grupo"] is False
    bodies = [m["body"] for m in data["mensagens"]]
    assert bodies == ["primeira", "segunda", "terceira"]  # cronológico asc
    assert data["mensagens"][0]["direction"] == "inbound"
    assert data["mensagens"][1]["direction"] == "outbound"


# --- IMPORTAÇÃO MANUAL DE HISTÓRICO WAHA ------------------------------------


def _waha_chat(chat_id: str) -> Dict[str, Any]:
    return {"id": {"_serialized": chat_id}, "timestamp": 1782560000}


def _waha_msg(msg_id: str, body: str, *, from_me: bool, ts: int) -> Dict[str, Any]:
    return {
        "id": {"_serialized": msg_id},
        "body": body,
        "fromMe": from_me,
        "timestamp": ts,
    }


@pytest.mark.asyncio
async def test_import_history_preview_nao_grava_e_resolve_lid(make_client, org, session):
    """Preview encontra chat @lid do contato, calcula novas e não grava transcript."""
    contact = await _contact(session, org, _CEL, "Ana")
    lid = "243026479857818@lid"
    fake = FakeWAHA(connected=True)
    fake.chats = [_waha_chat(lid)]
    fake.lid_map[lid] = _CEL
    fake.messages_by_chat[lid] = [
        _waha_msg("wamid.1", "Oi, tenho uma sugestão", from_me=False, ts=1782560000),
        _waha_msg("wamid.2", "Pode mandar", from_me=True, ts=1782560060),
    ]

    async with make_client(fake) as client:
        r = await client.post(f"/api/contacts/{contact.id}/whatsapp/import", json={"limit": 10})

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preview"] is True
    assert data["imported"] is False
    assert data["chat_id"] == lid
    assert data["resolved_phone"] == _CEL
    assert data["found"] == 2
    assert data["new"] == 2
    assert data["already_imported"] == 0
    assert data["messages"][0]["body"] == "Oi, tenho uma sugestão"

    msgs = (await session.execute(select(Message))).scalars().all()
    assert msgs == []


@pytest.mark.asyncio
async def test_import_history_confirm_grava_somente_novas(make_client, org, session):
    """Confirmação grava só mensagens ainda não importadas, preservando direção e id."""
    contact = await _contact(session, org, _CEL, "Ana")
    # Mensagem já importada antes: deve ser pulada.
    session.add(
        Message(
            organization_id=org.id,
            contact_id=contact.id,
            direction="inbound",
            body="antiga",
            channel_msg_id="wamid.OLD",
        )
    )
    await session.commit()

    lid = "243026479857818@lid"
    fake = FakeWAHA(connected=True)
    fake.chats = [_waha_chat(lid)]
    fake.lid_map[lid] = _CEL
    fake.messages_by_chat[lid] = [
        _waha_msg("wamid.OLD", "antiga", from_me=False, ts=1782560000),
        _waha_msg("wamid.NEW1", "Cliente respondeu", from_me=False, ts=1782560060),
        _waha_msg("wamid.NEW2", "Operador respondeu", from_me=True, ts=1782560120),
    ]

    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/import",
            json={"limit": 10, "confirm": True},
        )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preview"] is False
    assert data["imported"] is True
    assert data["found"] == 3
    assert data["new"] == 2
    assert data["already_imported"] == 1

    msgs = (
        await session.execute(select(Message).where(Message.contact_id == contact.id))
    ).scalars().all()
    by_id = {m.channel_msg_id: m for m in msgs}
    assert set(by_id) == {"wamid.OLD", "wamid.NEW1", "wamid.NEW2"}
    assert by_id["wamid.NEW1"].direction == "inbound"
    assert by_id["wamid.NEW2"].direction == "outbound"
    assert by_id["wamid.NEW1"].msg_metadata["source_event"] == "waha_history_import"


@pytest.mark.asyncio
async def test_import_history_waha_desconectado_409(make_client, org, session):
    contact = await _contact(session, org, _CEL, "Ana")
    fake = FakeWAHA(connected=False)
    async with make_client(fake) as client:
        r = await client.post(f"/api/contacts/{contact.id}/whatsapp/import", json={})
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_handoff_pausa_e_devolve(make_client, org, session):
    """POST /whatsapp/handoff liga/desliga needs_human_handoff do contato (idempotente).
    Quando true, o webhook pausa o bot (operador assume pelo Chat)."""
    contact = await _contact(session, org, _CEL)
    fake = FakeWAHA(connected=True)
    async with make_client(fake) as client:
        r = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/handoff", json={"ativar": True}
        )
        assert r.status_code == 200, r.text
        assert r.json()["needs_human_handoff"] is True
        # devolve ao fluxo automático
        r2 = await client.post(
            f"/api/contacts/{contact.id}/whatsapp/handoff", json={"ativar": False}
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["needs_human_handoff"] is False
