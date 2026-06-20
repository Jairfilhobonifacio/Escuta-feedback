"""Testes da CAMADA DE SELOS COM LOG — aplicar_selo/remover_selo + trigger inbound.

Cobre o contrato `profile_data["selos_log"] = [{selo, acao, at, por, origem}]`:
- aplicar/remover registra UM evento no log com a origem certa;
- idempotência: re-aplicar/re-remover NÃO duplica evento;
- integração do webhook: inbound de cliente já cadastrado ganha 'respondeu',
  perde 'nao_respondeu' e o log marca origem="inbound".

Mesma infra de test_campanha.py / test_webhook_phone_match.py: app real + SQLite
in-memory (override de get_session), LLM desligado, NENHUM disparo real de WhatsApp.
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
from app.api.campanha import (  # noqa: E402
    SELO_RESPONDEU,
    _selos_do_contato,
    _selos_log_do_contato,
    aplicar_selo,
    remover_selo,
)
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Message  # noqa: E402


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    """Desliga o LLM no caminho de captura inbound (sem rede)."""
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
    return {
        "event": "message",
        "payload": {"from": f"{from_}@c.us", "body": body, "id": msg_id, "fromMe": False},
    }


_LOG_KEYS = {"selo", "acao", "at", "por", "origem"}


# --- CAMADA: aplicar_selo / remover_selo registram no log com origem ----------


@pytest.mark.asyncio
async def test_aplicar_selo_registra_no_log_com_origem(session, org):
    """aplicar_selo aplica o selo E faz append de UM evento no log com origem/por."""
    ana = await _contact(session, org, "5531900000001", "Ana")

    aplicou = aplicar_selo(ana, "respondeu", origem="inbound", por="bot")
    assert aplicou is True
    assert "respondeu" in _selos_do_contato(ana)

    log = _selos_log_do_contato(ana)
    assert len(log) == 1
    ev = log[0]
    assert set(ev.keys()) == _LOG_KEYS
    assert ev["selo"] == "respondeu"
    assert ev["acao"] == "aplicado"
    assert ev["origem"] == "inbound"
    assert ev["por"] == "bot"
    # `at` é ISO8601 UTC (sufixo +00:00 do datetime.now(timezone.utc).isoformat()).
    assert isinstance(ev["at"], str) and ev["at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_remover_selo_registra_no_log_com_origem(session, org):
    """remover_selo tira o selo E registra evento acao='removido' com a origem."""
    ana = await _contact(session, org, "5531900000001", "Ana", profile_data={"selos": ["nao_respondeu"]})

    removeu = remover_selo(ana, "nao_respondeu", origem="inbound")
    assert removeu is True
    assert "nao_respondeu" not in _selos_do_contato(ana)

    log = _selos_log_do_contato(ana)
    assert len(log) == 1
    ev = log[0]
    assert set(ev.keys()) == _LOG_KEYS
    assert ev["selo"] == "nao_respondeu"
    assert ev["acao"] == "removido"
    assert ev["origem"] == "inbound"
    assert ev["por"] is None


@pytest.mark.asyncio
async def test_aplicar_selo_idempotente_nao_duplica_log(session, org):
    """Re-aplicar um selo já presente: NÃO altera selos e NÃO adiciona evento."""
    ana = await _contact(session, org, "5531900000001", "Ana")

    assert aplicar_selo(ana, "respondeu", origem="inbound") is True
    # 2ª e 3ª chamadas: idempotentes, retornam False e não tocam o log.
    assert aplicar_selo(ana, "respondeu", origem="inbound") is False
    assert aplicar_selo(ana, "respondeu", origem="manual") is False

    assert _selos_do_contato(ana) == ["respondeu"]
    assert len(_selos_log_do_contato(ana)) == 1


@pytest.mark.asyncio
async def test_remover_selo_idempotente_nao_duplica_log(session, org):
    """Remover um selo ausente: no-op, sem evento; remover o presente loga 1x só."""
    ana = await _contact(session, org, "5531900000001", "Ana", profile_data={"selos": ["respondeu"]})

    # Selo ausente -> no-op (False), sem evento.
    assert remover_selo(ana, "nao_respondeu", origem="inbound") is False
    assert _selos_log_do_contato(ana) == []

    # Selo presente -> remove (True), 1 evento; re-remover é no-op.
    assert remover_selo(ana, "respondeu", origem="inbound") is True
    assert remover_selo(ana, "respondeu", origem="inbound") is False
    assert _selos_do_contato(ana) == []
    assert len(_selos_log_do_contato(ana)) == 1


@pytest.mark.asyncio
async def test_aplicar_selo_com_org_garante_catalogo(session, org):
    """Passando `org`, o selo entra no catálogo da org (board/stats concordam)."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    aplicar_selo(ana, "vip", origem="regra", org=org)
    catalogo = (org.settings or {}).get("selos_catalogo") or []
    assert any(it.get("nome") == "vip" for it in catalogo)


@pytest.mark.asyncio
async def test_log_acumula_eventos_em_ordem(session, org):
    """O log é append-only: vários eventos acumulam na ordem em que ocorreram."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    aplicar_selo(ana, "contatado", origem="abordagem", por="felipe")
    aplicar_selo(ana, "respondeu", origem="inbound")
    remover_selo(ana, "contatado", origem="manual")

    log = _selos_log_do_contato(ana)
    assert [(e["selo"], e["acao"], e["origem"]) for e in log] == [
        ("contatado", "aplicado", "abordagem"),
        ("respondeu", "aplicado", "inbound"),
        ("contatado", "removido", "manual"),
    ]


# --- TRIGGER manual via endpoint grava log com origem="manual" ----------------


@pytest.mark.asyncio
async def test_endpoint_manual_loga_origem_manual(client, org, session):
    """POST/DELETE /selos no contato registram no log com origem='manual'."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    await session.commit()

    r = await client.post(f"/api/contacts/{ana.id}/selos", json={"nome": "vip"})
    assert r.status_code == 201, r.text

    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    log = c.profile_data.get("selos_log") or []
    assert len(log) == 1
    assert log[0]["selo"] == "vip" and log[0]["acao"] == "aplicado" and log[0]["origem"] == "manual"

    r = await client.delete(f"/api/contacts/{ana.id}/selos/vip")
    assert r.status_code == 200, r.text
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    log = c.profile_data.get("selos_log") or []
    assert len(log) == 2
    assert log[1]["selo"] == "vip" and log[1]["acao"] == "removido" and log[1]["origem"] == "manual"


# --- TRIGGER INBOUND (o furo): webhook aplica 'respondeu' / remove 'nao_respondeu' ---


@pytest.mark.asyncio
async def test_webhook_inbound_aplica_respondeu_e_remove_nao_respondeu(client, org, session):
    """Inbound de cliente JÁ CADASTRADO (com 'nao_respondeu'): ganha 'respondeu',
    perde 'nao_respondeu', e o log registra ambos com origem='inbound'."""
    cadastrado = Contact(
        organization_id=org.id,
        phone="5585999058955",
        name="Cliente Antigo",
        opt_in=True,
        profile_data={"selos": ["contatado", "nao_respondeu"]},
    )
    session.add(cadastrado)
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_="5585999058955", body="oi, voltei!", msg_id="wamid.SELO1"),
    )
    assert r.status_code == 200, r.text

    # Não duplicou contato; a mensagem ligou ao existente.
    total = (
        await session.execute(
            select(func.count()).select_from(Contact).where(Contact.organization_id == org.id)
        )
    ).scalar_one()
    assert total == 1

    c = (await session.execute(select(Contact).where(Contact.id == cadastrado.id))).scalar_one()
    selos = set(c.profile_data.get("selos") or [])
    assert SELO_RESPONDEU in selos           # ganhou 'respondeu'
    assert "nao_respondeu" not in selos      # perdeu 'nao_respondeu'
    assert "contatado" in selos              # preserva os demais

    # Log tem os DOIS eventos com origem='inbound'.
    log = c.profile_data.get("selos_log") or []
    by = {(e["selo"], e["acao"]): e for e in log}
    assert ("respondeu", "aplicado") in by
    assert ("nao_respondeu", "removido") in by
    assert by[("respondeu", "aplicado")]["origem"] == "inbound"
    assert by[("nao_respondeu", "removido")]["origem"] == "inbound"

    # Gravou a mensagem inbound (sanidade do fluxo do webhook).
    msg = (
        await session.execute(
            select(Message).where(Message.channel_msg_id == "wamid.SELO1")
        )
    ).scalar_one()
    assert msg.direction == "inbound" and msg.contact_id == cadastrado.id


@pytest.mark.asyncio
async def test_webhook_inbound_idempotente_nao_duplica_log_em_retry(client, org, session):
    """Retry do gateway (mesmo message_id) NÃO reaplica o selo nem duplica o log."""
    cadastrado = Contact(
        organization_id=org.id, phone="5585999058955", name="Cliente",
        opt_in=True, profile_data={"selos": ["nao_respondeu"]},
    )
    session.add(cadastrado)
    await session.commit()

    body = _payload(from_="5585999058955", body="oi", msg_id="wamid.RETRY1")
    assert (await client.post("/api/webhook/waha", json=body)).status_code == 200
    # Mesmo turno de novo (retry): curto-circuita como duplicate, não mexe em selo.
    assert (await client.post("/api/webhook/waha", json=body)).status_code == 200

    c = (await session.execute(select(Contact).where(Contact.id == cadastrado.id))).scalar_one()
    log = c.profile_data.get("selos_log") or []
    # 1 'respondeu' aplicado + 1 'nao_respondeu' removido = 2 eventos, sem duplicar.
    assert len(log) == 2
    assert {(e["selo"], e["acao"]) for e in log} == {
        ("respondeu", "aplicado"),
        ("nao_respondeu", "removido"),
    }


@pytest.mark.asyncio
async def test_webhook_inbound_flag_desligada_nao_aplica_selo(client, org, session):
    """Com settings['selo_auto_inbound']=False na org, o inbound NÃO aplica selo."""
    s = dict(org.settings or {})
    s["selo_auto_inbound"] = False
    org.settings = s
    await session.commit()

    cadastrado = Contact(
        organization_id=org.id, phone="5585999058955", name="Cliente",
        opt_in=True, profile_data={"selos": ["nao_respondeu"]},
    )
    session.add(cadastrado)
    await session.commit()

    r = await client.post(
        "/api/webhook/waha",
        json=_payload(from_="5585999058955", body="oi", msg_id="wamid.OFF1"),
    )
    assert r.status_code == 200, r.text

    c = (await session.execute(select(Contact).where(Contact.id == cadastrado.id))).scalar_one()
    selos = set(c.profile_data.get("selos") or [])
    # Flag OFF: estado dos selos intacto, sem log de inbound.
    assert SELO_RESPONDEU not in selos
    assert "nao_respondeu" in selos
    assert (c.profile_data.get("selos_log") or []) == []
