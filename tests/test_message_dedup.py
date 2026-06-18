"""Testes do DEDUP atômico do transcript (messages) — Fase 1 (webhook + dedup).

Cobre as três garantias da migration 20260618_message_dedup_metadata + do webhook:

(1) ÍNDICE ÚNICO PARCIAL no banco: inserir a MESMA mensagem 2x (mesmo
    organization_id + channel_msg_id) gera UMA linha; a 2ª levanta IntegrityError.
(2) PARCIAL de verdade: linhas com channel_msg_id NULL (outbound do bot) NÃO
    colidem entre si — o WHERE channel_msg_id IS NOT NULL deixa passar.
(3) O WEBHOOK absorve a corrida: mesmo se o SELECT de dedup não vê a 1ª gravação,
    o insert atômico (savepoint + try/except IntegrityError) NÃO devolve 500 —
    devolve 200 'duplicate' e não duplica o transcript.

Infra: SQLite in-memory async (fixture `session` do conftest) — o índice único
parcial renderiza nativo no SQLite (CREATE UNIQUE INDEX ... WHERE ...).
NENHUM disparo real de WhatsApp.
"""
from __future__ import annotations

import dataclasses
import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

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
    """LLM OFF no ingestor: dedup roda 100% offline e determinístico."""
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


async def _contact(session, org, phone):
    c = Contact(organization_id=org.id, phone=phone, name="Lead", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    return c


def _payload(*, from_, body, msg_id):
    return {
        "event": "message",
        "payload": {"from": f"{from_}@c.us", "body": body, "id": msg_id, "fromMe": False},
    }


# --- (1) índice único parcial barra a 2ª inserção do mesmo turno -----------------


@pytest.mark.asyncio
async def test_indice_unico_barra_segunda_insercao_mesmo_channel_msg_id(session, org):
    """Inserir 2x a MESMA (org, channel_msg_id) -> IntegrityError na 2ª; 1 linha só.

    A 2ª inserção vai num SAVEPOINT (begin_nested) — exatamente como o webhook faz —
    para que o IntegrityError não envenene a transação externa e a contagem seguinte
    funcione. Captura org_id/contato_id em locais ANTES do erro (pós-rollback do
    savepoint os objetos podem expirar)."""
    contato = await _contact(session, org, "5531900000001")
    await session.flush()
    org_id = org.id
    contato_id = contato.id

    session.add(
        Message(
            organization_id=org_id, contact_id=contato_id,
            direction="inbound", body="primeira", channel_msg_id="wamid.UNIQ",
        )
    )
    await session.flush()

    # 2ª com o MESMO channel_msg_id na MESMA org: o índice único parcial barra.
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                Message(
                    organization_id=org_id, contact_id=contato_id,
                    direction="inbound", body="duplicada", channel_msg_id="wamid.UNIQ",
                )
            )
            await session.flush()

    # Sobrou exatamente UMA linha p/ aquele channel_msg_id.
    n = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.organization_id == org_id, Message.channel_msg_id == "wamid.UNIQ")
        )
    ).scalar_one()
    assert n == 1


# --- (2) PARCIAL: channel_msg_id NULL não colide (outbound do bot) ---------------


@pytest.mark.asyncio
async def test_partial_permite_multiplos_channel_msg_id_null(session, org):
    """Várias mensagens SEM channel_msg_id (ex.: outbound do bot) convivem — o índice
    é PARCIAL (WHERE channel_msg_id IS NOT NULL), então NULLs não disputam unicidade."""
    contato = await _contact(session, org, "5531900000002")
    await session.flush()

    for i in range(3):
        session.add(
            Message(
                organization_id=org.id, contact_id=contato.id,
                direction="outbound", body=f"resposta {i}", channel_msg_id=None,
            )
        )
    await session.flush()  # não deve levantar — NULLs não colidem no índice parcial

    n = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.organization_id == org.id, Message.channel_msg_id.is_(None))
        )
    ).scalar_one()
    assert n == 3


# --- (3) o webhook absorve o IntegrityError (corrida) sem 500 -------------------


@pytest.mark.asyncio
async def test_webhook_retry_mesmo_msg_id_status_duplicate_sem_500(client, org, session):
    """Caminho primário (SELECT de dedup): reenviar o MESMO message_id 2x devolve
    200 'duplicate' nas duas, sem 500 e sem duplicar o transcript."""
    contato = await _contact(session, org, "5531900000003")
    await session.commit()

    p = _payload(from_=contato.phone, body="oi", msg_id="wamid.RACE")

    r1 = await client.post("/api/webhook/waha", json=p)
    assert r1.status_code == 200, r1.text
    # 1ª: sem pesquisa pendente, registra o turno e cai no funil de inbound.
    assert r1.json()["status"] == "no_pending_survey"

    # Reenvio (retry do gateway): 200 'duplicate', sem 500 e sem duplicar.
    r2 = await client.post("/api/webhook/waha", json=p)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "duplicate"

    n = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.organization_id == org.id, Message.channel_msg_id == "wamid.RACE")
        )
    ).scalar_one()
    assert n == 1  # nunca duplicou o transcript


# --- (3b) corrida REAL: SELECT cego -> insert atômico colide -> absorve ----------


@pytest.mark.asyncio
async def test_insert_atomico_absorve_quando_select_dedup_nao_ve(client, org, session, monkeypatch):
    """Corrida de verdade: neutraliza o SELECT de dedup por channel_msg_id (faz o
    webhook 'não ver' a 1ª gravação) para EXERCITAR o insert atômico. Pré-gravamos o
    turno; com o SELECT cego, o handler tenta inserir de novo, bate no índice único e
    o try/except IntegrityError absorve -> 200 'duplicate', 1 linha só, sem 500."""
    contato = await _contact(session, org, "5531900000004")
    session.add(
        Message(
            organization_id=org.id, contact_id=contato.id,
            direction="inbound", body="ola", channel_msg_id="wamid.RACE2",
        )
    )
    await session.commit()

    # Cega só o caminho de dedup por channel_msg_id: troca o método que monta a
    # cláusula. Mais simples e robusto: monkeypatcha Message.channel_msg_id.__eq__?
    # Inviável. Em vez disso, forçamos o SELECT de dedup a retornar vazio via um
    # wrapper no session.execute do webhook que zera o resultado APENAS da query de
    # dedup por channel_msg_id, deixando o resto intacto.
    real_execute = session.execute

    async def _fake_execute(statement, *args, **kwargs):
        result = await real_execute(statement, *args, **kwargs)
        txt = str(statement).lower()
        if "channel_msg_id" in txt and "messages.id" in txt and "select" in txt:
            # É a query de dedup (select Message.id where channel_msg_id == ...).
            class _Empty:
                def first(self_inner):
                    return None
            return _Empty()
        return result

    monkeypatch.setattr(session, "execute", _fake_execute)

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_=contato.phone, body="ola", msg_id="wamid.RACE2"),
    )
    # O insert atômico colidiu no índice único e o webhook ABSORVEU: 200, não 500.
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "duplicate"

    monkeypatch.undo()
    n = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.organization_id == org.id, Message.channel_msg_id == "wamid.RACE2")
        )
    ).scalar_one()
    assert n == 1
