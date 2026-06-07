"""Testes do POST /api/events/bizzu (gancho de churn da Bizzu).

Cobrem autenticação HMAC (segredo ausente/assinatura/timestamp), o casamento
evento→survey via trigger_event, opt-in, idempotência por event_id, cooldown
de 7 dias e o fluxo completo: evento → exit survey no canal → resposta do
contato fecha com answer_text (via SurveyContextResolver, mesmo caminho do
webhook WAHA).

Mesma infra dos testes do admin: httpx ASGITransport + SQLite in-memory +
FakeMessagingService. O segredo é injetado na dataclass frozen de settings
via object.__setattr__ (restaurado no teardown).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import get_messaging  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse, SurveyRun  # noqa: E402
from sqlalchemy import select  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402

SECRET = "test-secret-bizzu"

JAIR = {"id": "user-123", "name": "Jair Filho", "phone": "+55 (24) 99836-5809", "whatsapp_opt_in": True}
JAIR_DIGITS = "5524998365809"


def _signed_headers(body: bytes, *, secret: str = SECRET, ts: int | None = None) -> dict[str, str]:
    ts = int(time.time()) if ts is None else ts
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Escuta-Timestamp": str(ts),
        "X-Escuta-Signature": sig,
    }


def _event_body(
    event: str = "subscription_cancelled",
    event_id: str | None = None,
    user: dict | None = None,
    **properties,
) -> bytes:
    payload = {
        "event": event,
        "event_id": event_id or str(uuid.uuid4()),
        "user": user or dict(JAIR),
        "properties": properties or {"plan_id": "plan-1", "reason": "USER_CANCEL", "days_subscribed": 42},
    }
    return json.dumps(payload).encode()


async def _post_event(client: AsyncClient, body: bytes, **hdr_kwargs):
    return await client.post("/api/events/bizzu", content=body, headers=_signed_headers(body, **hdr_kwargs))


@pytest_asyncio.fixture
async def client(session):
    """Client com banco SQLite, messaging fake e BIZZU_WEBHOOK_SECRET de teste."""
    fake = FakeMessagingService()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_messaging] = lambda: fake

    original_secret = settings.bizzu_webhook_secret
    object.__setattr__(settings, "bizzu_webhook_secret", SECRET)  # dataclass frozen
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.fake_messaging = fake  # type: ignore[attr-defined]
            yield c
    finally:
        object.__setattr__(settings, "bizzu_webhook_secret", original_secret)
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


@pytest_asyncio.fixture
async def exit_survey(session, org):
    s = Survey(
        organization_id=org.id,
        name="Exit Bizzu",
        type="exit",
        status="active",
        trigger_event="subscription_cancelled",
        questions=[
            {"key": "reason", "kind": "open", "text": "O que pesou na decisão de cancelar?"},
            {"key": "thanks", "kind": "thanks", "text": "Obrigado pela sinceridade! 💙"},
        ],
    )
    session.add(s)
    await session.commit()
    return s


# --- Autenticação -------------------------------------------------------------


@pytest.mark.asyncio
async def test_sem_secret_configurado_503(client, exit_survey):
    object.__setattr__(settings, "bizzu_webhook_secret", None)
    body = _event_body()
    r = await client.post("/api/events/bizzu", content=body, headers=_signed_headers(body))
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_sem_headers_401(client, exit_survey):
    r = await client.post("/api/events/bizzu", content=_event_body())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_assinatura_invalida_401(client, exit_survey):
    body = _event_body()
    r = await client.post(
        "/api/events/bizzu", content=body, headers=_signed_headers(body, secret="outro-segredo")
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_timestamp_velho_401(client, exit_survey):
    body = _event_body()
    r = await _post_event(client, body, ts=int(time.time()) - 3600)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_corpo_adulterado_401(client, exit_survey):
    body = _event_body()
    headers = _signed_headers(body)
    tampered = body.replace(b"USER_CANCEL", b"PAYMENT_FAILED")
    assert tampered != body  # garante que a adulteração realmente mudou bytes
    r = await client.post("/api/events/bizzu", content=tampered, headers=headers)
    assert r.status_code == 401


# --- Regras de negócio ----------------------------------------------------------


@pytest.mark.asyncio
async def test_evento_sem_survey_no_survey(client, org):
    r = await _post_event(client, _event_body(event="topic_completed"))
    assert r.status_code == 202
    assert r.json() == {"dispatched": False, "reason": "no_survey", "event": "topic_completed"}


@pytest.mark.asyncio
async def test_happy_path_dispara_exit_survey(client, session, org, exit_survey):
    body = _event_body(event_id="evt-1")
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["dispatched"] is True
    assert data["survey"] == "Exit Bizzu"
    assert data["phone"] == JAIR_DIGITS

    # mensagem enviada é a pergunta aberta (não a de NPS)
    assert len(client.fake_messaging.sent) == 1
    sent = client.fake_messaging.sent[0]
    assert sent["chat_id"] == JAIR_DIGITS
    assert "cancelar" in sent["text"]

    # contato criado com opt-in e vínculo ao user da Bizzu
    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    assert contact.opt_in is True
    assert contact.profile_data.get("bizzu_user_id") == "user-123"
    assert contact.name == "Jair Filho"

    # response nasce aguardando o texto (exit não tem etapa de nota)
    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "awaiting_reason"

    # run carrega o trigger idempotente
    run = await session.get(SurveyRun, resp.survey_run_id)
    assert run.trigger == "bizzu:subscription_cancelled:evt-1"


@pytest.mark.asyncio
async def test_event_id_repetido_duplicate(client, org, exit_survey):
    body = _event_body(event_id="evt-dup")
    r1 = await _post_event(client, body)
    assert r1.json()["dispatched"] is True

    r2 = await _post_event(client, body)
    assert r2.status_code == 202
    assert r2.json()["reason"] == "duplicate"
    assert len(client.fake_messaging.sent) == 1  # nenhum reenvio


@pytest.mark.asyncio
async def test_sem_opt_in_nao_dispara_mas_persiste_contato(client, session, org, exit_survey):
    user = dict(JAIR, whatsapp_opt_in=False, phone="+5531988887777")
    r = await _post_event(client, _event_body(user=user))
    assert r.status_code == 202
    assert r.json()["reason"] == "no_opt_in"
    assert client.fake_messaging.sent == []

    contact = (
        await session.execute(select(Contact).where(Contact.phone == "5531988887777"))
    ).scalar_one()
    assert contact.opt_in is False


@pytest.mark.asyncio
async def test_opt_in_do_payload_eleva_contato_existente(client, session, org, exit_survey):
    session.add(
        Contact(organization_id=org.id, phone=JAIR_DIGITS, name="Jair", opt_in=False, profile_data={})
    )
    await session.commit()

    r = await _post_event(client, _event_body(event_id="evt-eleva"))
    assert r.json()["dispatched"] is True

    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    assert contact.opt_in is True


@pytest.mark.asyncio
async def test_cooldown_7_dias(client, org, exit_survey):
    r1 = await _post_event(client, _event_body(event_id="evt-a"))
    assert r1.json()["dispatched"] is True

    # mesmo contato, outro event_id, logo em seguida → cooldown segura
    r2 = await _post_event(client, _event_body(event_id="evt-b"))
    assert r2.status_code == 202
    assert r2.json()["reason"] == "cooldown"
    assert len(client.fake_messaging.sent) == 1


@pytest.mark.asyncio
async def test_telefone_invalido_422(client, org, exit_survey):
    user = dict(JAIR, phone="123")
    r = await _post_event(client, _event_body(user=user))
    assert r.status_code == 422


# --- Fluxo completo: evento → pergunta → resposta fecha -------------------------


@pytest.mark.asyncio
async def test_resposta_do_contato_fecha_com_motivo(client, session, org, exit_survey):
    r = await _post_event(client, _event_body(event_id="evt-flow"))
    assert r.json()["dispatched"] is True

    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()

    # contato responde no WhatsApp (mesmo caminho do webhook WAHA)
    resolver = SurveyContextResolver(session, org.id)
    reply = await resolver.resolve(contact.id, "Achei caro e estou sem tempo de estudar")
    await session.commit()

    assert reply is not None
    assert reply.closed is True
    assert reply.text == "Obrigado pela sinceridade! 💙"  # thanks custom (kind='thanks')

    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "closed"
    assert resp.answer_text == "Achei caro e estou sem tempo de estudar"
    assert resp.answer_score is None  # exit não tem nota
    assert resp.closed_at is not None


# --- Criação de survey exit via API do painel ------------------------------------


@pytest.mark.asyncio
async def test_criar_survey_exit_via_admin_e_disparar(client, session, org):
    r = await client.post(
        "/api/surveys",
        json={
            "name": "Exit churn",
            "type": "exit",
            "reason_prompt": "O que te levou a cancelar?",
            "thanks_message": "Valeu! 💙",
            "trigger_event": "subscription_cancelled",
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["type"] == "exit"
    assert out["trigger_event"] == "subscription_cancelled"
    assert out["nps_question"] is None

    # NPS sem nps_question → 422
    r = await client.post(
        "/api/surveys",
        json={"name": "NPS sem pergunta", "reason_prompt": "Por quê?"},
    )
    assert r.status_code == 422

    # segundo trigger_event igual → 409
    r = await client.post(
        "/api/surveys",
        json={
            "name": "Outra exit",
            "type": "exit",
            "reason_prompt": "x",
            "trigger_event": "subscription_cancelled",
        },
    )
    assert r.status_code == 409

    # o evento usa a survey criada via API
    r = await _post_event(client, _event_body(event_id="evt-api"))
    assert r.json()["dispatched"] is True
    assert r.json()["survey"] == "Exit churn"
