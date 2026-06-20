"""Teste de integração: o webhook NÃO duplica contato quando o MESMO cliente
escreve de um número em formato diferente do cadastrado.

Cola direta com o bug original: o get-or-create casava `Contact.phone` por igualdade
EXATA, então um cliente cadastrado como '558599058955' (12 díg, sem o 9) que mandasse
mensagem de '5585999058955' (13 díg, com o 9 — o que o WhatsApp/WAHA entrega) criava
um 2º contato. Agora casamos por variantes (phone_variants) e a conversa liga ao
contato existente.

Mesma infra de test_webhook_capture.py: app real + SQLite in-memory (override de
get_session), LLM desligado, NENHUM disparo real de WhatsApp.
"""
from __future__ import annotations

import dataclasses
import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import app.domain.feedback.ingest as _ingest  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Message  # noqa: E402


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    monkeypatch.setattr(
        _ingest, "settings", dataclasses.replace(_ingest.settings, llm_enabled=False)
    )


@pytest_asyncio.fixture
async def client(session):
    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


def _payload(*, from_, body, msg_id):
    return {
        "event": "message",
        "payload": {"from": f"{from_}@c.us", "body": body, "id": msg_id, "fromMe": False},
    }


@pytest.mark.asyncio
async def test_inbound_de_formato_diferente_nao_cria_segundo_contato(client, org, session):
    """Cliente cadastrado SEM o 9 (12 díg) escreve do número COM o 9 (13 díg, como o
    WAHA entrega): liga ao contato existente e NÃO cria duplicata."""
    # Cadastrado em formato divergente do que o WhatsApp entrega.
    cadastrado = Contact(
        organization_id=org.id, phone="558599058955", name="Cliente Antigo",
        opt_in=True, profile_data={},
    )
    session.add(cadastrado)
    await session.commit()

    # Inbound chega no formato canônico do WAHA (com DDI + o 9).
    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_="5585999058955", body="oi, tudo certo com meu plano?", msg_id="wamid.PHN1"),
    )
    assert r.status_code == 200, r.text

    # Continua existindo UM único contato na org (não duplicou).
    total = (
        await session.execute(
            select(func.count()).select_from(Contact).where(Contact.organization_id == org.id)
        )
    ).scalar_one()
    assert total == 1, "inbound em formato diferente NÃO pode criar 2º contato"

    # A mensagem ligou ao contato pré-existente (mesmo id).
    msg = (
        await session.execute(
            select(Message).where(
                Message.contact_id == cadastrado.id,
                Message.channel_msg_id == "wamid.PHN1",
            )
        )
    ).scalar_one()
    assert msg.direction == "inbound"
    assert msg.body == "oi, tudo certo com meu plano?"


@pytest.mark.asyncio
async def test_contato_novo_gravado_na_forma_canonica(client, org, session):
    """Sem contato pré-existente, o webhook CRIA gravando a forma canônica E.164
    (13 díg p/ celular) mesmo recebendo um número sem o DDI/9."""
    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_="8599058955", body="quero saber dos editais", msg_id="wamid.PHN2"),
    )
    assert r.status_code == 200, r.text

    contatos = (
        await session.execute(select(Contact).where(Contact.organization_id == org.id))
    ).scalars().all()
    assert len(contatos) == 1
    assert contatos[0].phone == "5585999058955"  # canônico, não '8599058955'
