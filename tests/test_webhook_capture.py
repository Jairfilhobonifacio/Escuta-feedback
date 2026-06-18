"""Testes da CAPTURA do webhook — POST /api/webhook/waha registra na Mega Central a
resposta inbound que NÃO casa com pesquisa pendente (fecha o gap "lead respondeu no
WhatsApp mas a central não registra").

Mesma infra de test_campanha.py: app real + SQLite in-memory (override de get_session).
NENHUM disparo real de WhatsApp: no ramo sem-pesquisa o handler não chama o WAHA
(reply é None), e o LLM fica desligado em teste (sem GROQ_API_KEY) -> sentiment=None.

Cenários:
(a) contato com selo 'contatado'  -> FeedbackItem source='whatsapp' type='churn' + selo 'respondeu'
(b) contato fora da campanha       -> FeedbackItem type='outro', NÃO aplica 'respondeu'
(c) idempotência: reenviar o mesmo message_id NÃO duplica o feedback
"""
from __future__ import annotations

import dataclasses
import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import app.domain.feedback.ingest as _ingest  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    """Desliga o LLM no ingestor: a captura roca 100% offline e sentiment fica None
    de forma DETERMINÍSTICA (independe de a máquina ter GROQ_API_KEY no .env). A
    captura nunca dispara WhatsApp; aqui garantimos que também não chama o Groq."""
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
    # slug 'bizzu' == settings.default_org_slug (o webhook resolve a org por ele).
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _contact(session, org, phone, name, **kw):
    c = Contact(
        organization_id=org.id,
        phone=phone,
        name=name,
        opt_in=kw.pop("opt_in", True),
        profile_data=kw.pop("profile_data", {}),
    )
    session.add(c)
    await session.flush()
    return c


def _payload(*, from_, body, msg_id):
    """Payload inbound de TEXTO (Formato B do WAHA), de terceiro (fromMe ausente)."""
    return {
        "event": "message",
        "payload": {"from": f"{from_}@c.us", "body": body, "id": msg_id, "fromMe": False},
    }


# --- (a) contato com selo 'contatado' -> churn + aplica 'respondeu' -----------


@pytest.mark.asyncio
async def test_captura_contato_contatado_cria_feedback_e_aplica_respondeu(client, org, session):
    phone = "5531999990001"
    contato = await _contact(
        session, org, phone, "Lead Abordado", profile_data={"selos": ["contatado"]}
    )
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_=phone, body="parei porque achei caro demais", msg_id="wamid.AAA"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "no_pending_survey"

    # FeedbackItem criado na central: source='whatsapp', type='churn' (universo win-back),
    # external_id estável, action_status='novo', sentiment=None (LLM off em teste).
    items = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.source == "whatsapp")))
        .scalars().all()
    )
    assert len(items) == 1
    it = items[0]
    assert it.source == "whatsapp"
    assert it.type == "churn"
    assert it.text == "parei porque achei caro demais"
    assert it.contact_id == contato.id
    assert it.external_id == "wa:wamid.AAA"
    assert it.action_status == "novo"
    assert it.occurred_at is not None
    assert it.sentiment is None  # sem GROQ_API_KEY em teste -> não inventa sentimento

    # Selo 'respondeu' aplicado (idempotente) ao contato abordado + 'contatado' mantido.
    c = (await session.execute(select(Contact).where(Contact.id == contato.id))).scalar_one()
    selos = c.profile_data.get("selos") or []
    assert "respondeu" in selos
    assert "contatado" in selos

    # Selo 'respondeu' garantido no catálogo da org.
    cat = (await client.get("/api/selos")).json()
    assert any(s["nome"] == "respondeu" for s in cat["catalogo"])

    # O transcript (Message) continua sendo gravado como antes.
    from app.models.survey import Message  # import local p/ não poluir o topo
    msgs = (
        (await session.execute(select(Message).where(Message.contact_id == contato.id)))
        .scalars().all()
    )
    assert any(m.direction == "inbound" and m.body == "parei porque achei caro demais" for m in msgs)


# --- (b) contato fora da campanha -> type 'outro', NÃO aplica 'respondeu' ------


@pytest.mark.asyncio
async def test_captura_contato_fora_campanha_type_outro_sem_respondeu(client, org, session):
    phone = "5531999990002"
    contato = await _contact(session, org, phone, "Lead Qualquer")  # sem selos, sem partner
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_=phone, body="vcs tem material de TI?", msg_id="wamid.BBB"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "no_pending_survey"

    items = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.source == "whatsapp")))
        .scalars().all()
    )
    assert len(items) == 1
    it = items[0]
    assert it.type == "outro"  # fora do universo de churn
    assert it.text == "vcs tem material de TI?"
    assert it.external_id == "wa:wamid.BBB"
    assert it.contact_id == contato.id

    # NÃO aplica 'respondeu' (contato não foi abordado na campanha).
    c = (await session.execute(select(Contact).where(Contact.id == contato.id))).scalar_one()
    assert "respondeu" not in (c.profile_data.get("selos") or [])


# --- (c) idempotência: mesmo message_id NÃO duplica --------------------------


@pytest.mark.asyncio
async def test_captura_idempotente_mesmo_message_id(client, org, session):
    phone = "5531999990003"
    await _contact(session, org, phone, "Lead Retry", profile_data={"selos": ["contatado"]})
    await session.commit()

    body = "to pensando em voltar"
    p = _payload(from_=phone, body=body, msg_id="wamid.CCC")

    r1 = await client.post("/api/webhook/waha", json=p)
    assert r1.status_code == 200
    r2 = await client.post("/api/webhook/waha", json=p)  # reenvio (retry do gateway)
    assert r2.status_code == 200

    # Um único FeedbackItem para o mesmo message_id (dedup por external_id 'wa:<id>').
    items = (
        (await session.execute(
            select(FeedbackItem).where(FeedbackItem.external_id == "wa:wamid.CCC")
        ))
        .scalars().all()
    )
    assert len(items) == 1
    assert items[0].text == body


# --- (e) dedup por message_id: retry curto-circuita e NÃO duplica o transcript ----


@pytest.mark.asyncio
async def test_retry_mesmo_message_id_status_duplicate_sem_duplicar_transcript(client, org, session):
    """Regressão: em retry do WAHA com o MESMO message_id, o handler curto-circuita
    (status 'duplicate') e NÃO grava um 2º Message (transcript) nem reprocessa nada."""
    from app.models.survey import Message

    phone = "5531999990005"
    contato = await _contact(session, org, phone, "Lead Dup", profile_data={"selos": ["contatado"]})
    await session.commit()

    p = _payload(from_=phone, body="oi, ainda tenho desconto?", msg_id="wamid.EEE")

    r1 = await client.post("/api/webhook/waha", json=p)
    assert r1.status_code == 200
    assert r1.json()["status"] == "no_pending_survey"

    r2 = await client.post("/api/webhook/waha", json=p)  # retry do gateway
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"  # curto-circuitou pelo channel_msg_id

    # Só UM transcript inbound para esse turno (não duplicou).
    msgs = (
        (await session.execute(
            select(Message).where(
                Message.contact_id == contato.id,
                Message.channel_msg_id == "wamid.EEE",
            )
        ))
        .scalars().all()
    )
    assert len(msgs) == 1

    # E só UM FeedbackItem.
    items = (
        (await session.execute(
            select(FeedbackItem).where(FeedbackItem.external_id == "wa:wamid.EEE")
        ))
        .scalars().all()
    )
    assert len(items) == 1


# --- (d) churn por subscription.state (sem selo) -> type 'churn', sem 'respondeu' --


@pytest.mark.asyncio
async def test_captura_churn_por_subscription_state_sem_respondeu(client, org, session):
    phone = "5531999990004"
    contato = await _contact(
        session, org, phone, "Cancelado",
        profile_data={"partner": {"subscription": {"state": "cancelled"}}},
    )
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_=phone, body="cancelei mas to com saudade", msg_id="wamid.DDD"),
    )
    assert r.status_code == 200

    it = (
        (await session.execute(
            select(FeedbackItem).where(FeedbackItem.external_id == "wa:wamid.DDD")
        ))
        .scalars().one()
    )
    assert it.type == "churn"  # churn pelo state, mesmo sem selo 'contatado'

    # Não foi abordado (sem selo 'contatado') -> não ganha 'respondeu'.
    c = (await session.execute(select(Contact).where(Contact.id == contato.id))).scalar_one()
    assert "respondeu" not in (c.profile_data.get("selos") or [])
