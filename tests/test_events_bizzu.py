"""Testes do POST /api/events/bizzu (ganchos de evento da Bizzu).

Cobrem autenticação HMAC (segredo ausente/assinatura/timestamp), o casamento
evento→survey via trigger_event, opt-in, idempotência por event_id, cooldown
de 7 dias e os fluxos completos: churn → exit survey → resposta fecha com
answer_text; e 'topic_completed' → CSAT no motor NPS 0-10 (nota → motivo →
closed), ambos via SurveyContextResolver (mesmo caminho do webhook WAHA).

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
from app.models.feedback import FeedbackItem  # noqa: E402
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


# Textos da survey CSAT (mesmos do scripts/seed_bizzu.py)
CSAT_NPS_QUESTION = (
    "acabou de concluir mais um tópico! 🎯 De 0 a 10, que nota "
    "você dá pra qualidade do conteúdo (resumo e questões) desse tópico?"
)
CSAT_REASON_PROMPT = "Valeu! O que faria essa nota virar 10? (pode responder em texto)"
CSAT_THANKS = "Anotado! 💙 Obrigado por ajudar a melhorar o Bizzu — bons estudos!"


@pytest_asyncio.fixture
async def csat_survey(session, org):
    """CSAT de tópico: reusa o motor NPS 0-10 (escala única do produto)."""
    s = Survey(
        organization_id=org.id,
        name="CSAT Tópico Bizzu",
        type="nps",
        status="active",
        trigger_event="topic_completed",
        questions=[
            {"key": "nps", "kind": "nps", "text": CSAT_NPS_QUESTION},
            {"key": "reason", "kind": "open", "text": CSAT_REASON_PROMPT},
            {"key": "thanks", "kind": "thanks", "text": CSAT_THANKS},
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


# --- CSAT 'topic_completed' (motor NPS 0-10 reusado) -----------------------------


@pytest.mark.asyncio
async def test_topic_completed_dispara_csat_nps(client, session, org, csat_survey):
    """Evento 'topic_completed' → survey CSAT disparada com a pergunta de NOTA
    (kind='nps') e response nascendo 'sent' (fluxo NPS normal, ≠ exit)."""
    body = _event_body(event="topic_completed", event_id="evt-topic-1")
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["dispatched"] is True
    assert data["survey"] == "CSAT Tópico Bizzu"
    assert data["phone"] == JAIR_DIGITS

    # mensagem enviada é a pergunta de nota (kind='nps'), não a aberta
    assert len(client.fake_messaging.sent) == 1
    sent = client.fake_messaging.sent[0]
    assert sent["chat_id"] == JAIR_DIGITS
    assert CSAT_NPS_QUESTION in sent["text"]

    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "sent"  # NPS aguarda a nota (exit nasceria 'awaiting_reason')

    run = await session.get(SurveyRun, resp.survey_run_id)
    assert run.trigger == "bizzu:topic_completed:evt-topic-1"


@pytest.mark.asyncio
async def test_fluxo_csat_nota_e_motivo_fecha(client, session, org, csat_survey):
    """Fluxo completo: evento → '8' vira awaiting_reason c/ answer_score=8 →
    texto livre fecha (closed), via SurveyContextResolver (caminho do webhook)."""
    r = await _post_event(client, _event_body(event="topic_completed", event_id="evt-topic-flow"))
    assert r.json()["dispatched"] is True

    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    resolver = SurveyContextResolver(session, org.id)

    # 1ª resposta: a nota
    reply = await resolver.resolve(contact.id, "8")
    await session.commit()
    assert reply is not None
    assert reply.closed is False
    assert reply.text == CSAT_REASON_PROMPT  # pede o "por quê" custom da survey

    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "awaiting_reason"
    assert resp.answer_score == 8
    assert resp.nps_bucket == "passive"

    # 2ª resposta: o motivo em texto → fecha
    reply2 = await resolver.resolve(contact.id, "Mais questões comentadas no resumo")
    await session.commit()
    assert reply2 is not None
    assert reply2.closed is True
    assert reply2.text == CSAT_THANKS

    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "closed"
    assert resp.answer_score == 8
    assert resp.answer_text == "Mais questões comentadas no resumo"
    assert resp.closed_at is not None


@pytest.mark.asyncio
async def test_dois_topic_completed_seguidos_cooldown(client, org, csat_survey):
    """Dois 'topic_completed' (event_ids distintos) em sequência → o 2º cai no
    cooldown de 7 dias (não viram spam a cada tópico concluído)."""
    r1 = await _post_event(client, _event_body(event="topic_completed", event_id="evt-topic-a"))
    assert r1.json()["dispatched"] is True

    r2 = await _post_event(client, _event_body(event="topic_completed", event_id="evt-topic-b"))
    assert r2.status_code == 202
    assert r2.json()["reason"] == "cooldown"
    assert len(client.fake_messaging.sent) == 1  # só a 1ª pergunta foi enviada


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


# --- NPS in-app espelhado (ingest_mode: registra SEM disparar WhatsApp) ----------


@pytest_asyncio.fixture
async def nps_ingest_survey(session, org):
    """NPS in-app espelhado: ingest_mode=True — registra a resposta já dada no app
    (sem disparo WA). Disparada pelo evento 'nps_submitted'."""
    s = Survey(
        organization_id=org.id,
        name="NPS Bizzu (ingest)",
        type="nps",
        status="active",
        trigger_event="nps_submitted",
        ingest_mode=True,
        questions=[
            {"key": "nps", "kind": "nps", "text": "De 0 a 10, recomendaria o Bizzu?"},
            {"key": "reason", "kind": "open", "text": "Por quê?"},
        ],
    )
    session.add(s)
    await session.commit()
    return s


@pytest.mark.asyncio
async def test_nps_ingest_registra_sem_disparar(client, session, org, nps_ingest_survey):
    body = _event_body(
        event="nps_submitted",
        event_id="nps:resp-1",
        trigger="FIRST_SESSION",
        score=9,
        comment="Conteúdo excelente, gabaritos certeiros",
    )
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["dispatched"] is False
    assert data["ingested"] is True
    assert data["survey"] == "NPS Bizzu (ingest)"
    assert data["phone"] == JAIR_DIGITS

    # NADA enviado pro WhatsApp — a marca registrada do modo ingest
    assert client.fake_messaging.sent == []

    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "ingested"
    assert resp.answer_score == 9
    assert resp.nps_bucket == "promoter"
    assert resp.answer_text == "Conteúdo excelente, gabaritos certeiros"
    assert resp.source == "in_app"
    assert resp.closed_at is not None


@pytest.mark.asyncio
async def test_nps_ingest_sem_opt_in_registra_mesmo_assim(client, session, org, nps_ingest_survey):
    """Ingest não envia WA → não exige opt-in: registra um detrator sem opt-in."""
    user = dict(JAIR, whatsapp_opt_in=False, phone="+5531977776666")
    r = await _post_event(client, _event_body(
        event="nps_submitted", event_id="nps:resp-2", user=user,
        trigger="GOAL_HALF:g1", score=3, comment="achei caro",
    ))
    assert r.status_code == 202
    assert r.json()["ingested"] is True
    assert client.fake_messaging.sent == []

    contact = (
        await session.execute(select(Contact).where(Contact.phone == "5531977776666"))
    ).scalar_one()
    assert contact.opt_in is False  # não exigido nem elevado
    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.status == "ingested"
    assert resp.nps_bucket == "detractor"


@pytest.mark.asyncio
async def test_nps_ingest_sem_comment(client, session, org, nps_ingest_survey):
    r = await _post_event(client, _event_body(
        event="nps_submitted", event_id="nps:resp-3",
        trigger="GOAL_COMPLETE:g2", score=10,
    ))
    assert r.json()["ingested"] is True
    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    assert resp.answer_text is None
    assert resp.answer_score == 10
    assert resp.nps_bucket == "promoter"


@pytest.mark.asyncio
async def test_nps_ingest_event_id_repetido_duplicate(client, nps_ingest_survey):
    body = _event_body(event="nps_submitted", event_id="nps:dup", trigger="FIRST_SESSION", score=8)
    r1 = await _post_event(client, body)
    assert r1.json()["ingested"] is True
    r2 = await _post_event(client, body)
    assert r2.status_code == 202
    assert r2.json()["reason"] == "duplicate"


@pytest.mark.asyncio
async def test_nps_ingest_nao_aparece_como_pendente(client, session, org, nps_ingest_survey):
    """Uma response 'ingested' nunca é tratada como pendente pelo resolver: o bot
    não tenta 'resolver' algo que já veio respondido do app."""
    r = await _post_event(client, _event_body(
        event="nps_submitted", event_id="nps:resp-5",
        trigger="FIRST_SESSION", score=7, comment="ok",
    ))
    assert r.json()["ingested"] is True
    contact = (
        await session.execute(select(Contact).where(Contact.phone == JAIR_DIGITS))
    ).scalar_one()
    resolver = SurveyContextResolver(session, org.id)
    reply = await resolver.resolve(contact.id, "qualquer mensagem depois")
    assert reply is None


# --- Eventos genéricos → FeedbackItem na mega central (report/edital/ticket) -----


@pytest.mark.asyncio
async def test_question_reported_vira_feedback_item(client, session, org):
    body = _event_body(
        event="question_reported",
        event_id="report:u1:q1",
        tipo="GABARITO_ERRADO",
        observacao="A alternativa C está errada, o certo é D.",
        materia_nome="Direito Administrativo",
        topico_nome="Atos administrativos",
    )
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["ingested"] is True
    assert data["source"] == "bizzu_app"
    assert data["type"] == "report"
    assert client.fake_messaging.sent == []  # NUNCA dispara WhatsApp

    item = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.organization_id == org.id))
    ).scalar_one()
    assert item.type == "report"
    assert item.text == "A alternativa C está errada, o certo é D."
    assert item.extra["tipo"] == "GABARITO_ERRADO"
    assert item.extra["materia_nome"] == "Direito Administrativo"
    assert item.external_id == "bizzu:question_reported:report:u1:q1"


@pytest.mark.asyncio
async def test_edital_requested_vira_feedback_item(client, session, org):
    body = _event_body(
        event="edital_requested",
        event_id="edital_req:42",
        edital_nome="TRT 1 2026",
        cargo_nome="Analista Judiciário",
        banca="FCC",
    )
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    assert r.json()["type"] == "edital_request"
    item = (
        await session.execute(select(FeedbackItem).where(FeedbackItem.organization_id == org.id))
    ).scalar_one()
    assert item.source == "bizzu_platform"
    assert item.extra["edital_nome"] == "TRT 1 2026"
    assert item.extra["banca"] == "FCC"


@pytest.mark.asyncio
async def test_generic_event_dedup(client, org):
    body = _event_body(event="question_reported", event_id="report:dup", tipo="OUTRO", observacao="x")
    r1 = await _post_event(client, body)
    assert r1.json()["ingested"] is True
    r2 = await _post_event(client, body)
    assert r2.status_code == 202
    assert r2.json()["reason"] == "duplicate"


@pytest.mark.asyncio
async def test_generic_event_sem_opt_in_registra(client, session, org):
    """Evento genérico não envia WhatsApp → não exige opt-in: registra mesmo assim."""
    user = dict(JAIR, whatsapp_opt_in=False, phone="+5531977770000")
    body = _event_body(
        event="question_reported", event_id="report:noopt", user=user,
        tipo="OUTRO", observacao="sem opt-in",
    )
    r = await _post_event(client, body)
    assert r.json()["ingested"] is True
    assert client.fake_messaging.sent == []
    item = (
        await session.execute(
            select(FeedbackItem).where(FeedbackItem.external_id == "bizzu:question_reported:report:noopt")
        )
    ).scalar_one()
    assert item.type == "report"


# --- Atendimentos: ticket_created → FeedbackItem; ticket_resolved → CSAT survey ----


@pytest_asyncio.fixture
async def csat_atendimento_survey(session, org):
    s = Survey(
        organization_id=org.id,
        name="CSAT Atendimento Bizzu",
        type="nps",
        status="active",
        trigger_event="ticket_resolved",
        questions=[
            {"key": "nps", "kind": "nps", "text": "De 0 a 10, satisfeito com o atendimento?"},
            {"key": "reason", "kind": "open", "text": "Por quê?"},
        ],
    )
    session.add(s)
    await session.commit()
    return s


@pytest.mark.asyncio
async def test_ticket_created_sem_userid_vira_feedback_item(client, session, org):
    """Ticket de contato PÚBLICO (sem userId) → FeedbackItem, sem disparo WhatsApp."""
    user = {"name": "Cliente Público", "phone": "+5531966660000", "whatsapp_opt_in": False}
    body = _event_body(
        event="ticket_created", event_id="ticket:abc:created", user=user,
        tipo="erro", assunto="Não consigo logar na plataforma",
    )
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["ingested"] is True
    assert data["type"] == "ticket"
    assert client.fake_messaging.sent == []

    item = (
        await session.execute(
            select(FeedbackItem).where(FeedbackItem.external_id == "bizzu:ticket_created:ticket:abc:created")
        )
    ).scalar_one()
    assert item.source == "bizzu_support"
    assert item.contact_id is not None  # contato criado pelo telefone
    assert item.extra["assunto"] == "Não consigo logar na plataforma"
    assert item.extra["tipo"] == "erro"


@pytest.mark.asyncio
async def test_ticket_resolved_dispara_csat(client, session, org, csat_atendimento_survey):
    """ticket_resolved NÃO vira FeedbackItem: dispara a survey CSAT por WhatsApp."""
    body = _event_body(
        event="ticket_resolved", event_id="ticket:xyz:resolved",
        tipo="erro", assunto="resolvido",
    )
    r = await _post_event(client, body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["dispatched"] is True
    assert data["survey"] == "CSAT Atendimento Bizzu"
    assert len(client.fake_messaging.sent) == 1  # CSAT enviado no WhatsApp (JAIR tem opt-in)
