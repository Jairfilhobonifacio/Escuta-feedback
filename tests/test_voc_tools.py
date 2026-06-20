"""As 7 tools do Agente VoC — sobre a sessão SQLite in-memory (fixture `session`).

Sem rede, sem LLM: chamamos os executores via o registry (build_default_registry) ou
direto. Cobre cada tool e, com atenção, a tool de WhatsApp: NO-OP com a flag OFF e os
3 gates (opt-in, cooldown, alcançável) com a flag ON.

A flag `settings.voc_whatsapp_tool_enabled` mora num dataclass `frozen` — não dá para
monkeypatchar por setattr. Trocamos a REFERÊNCIA `settings` importada no módulo
`app.domain.voc.tools` por um `dataclasses.replace(...)` (mesmo padrão de outros testes).
"""
from __future__ import annotations

import dataclasses
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import config  # noqa: E402
from app.domain.voc import tools as tools_mod  # noqa: E402
from app.domain.voc.tools import VoCToolContext, build_default_registry  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
from app.models.playbook import CsTask  # noqa: E402
from app.models.survey import Message  # noqa: E402
from app.services.llm import ToolCall  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
MOBILE = "5531999990001"  # celular BR válido (alcançável)


def _enable_whatsapp(monkeypatch, *, enabled: bool, cooldown_hours: int = 20):
    """Liga/desliga a tool de WhatsApp trocando a `settings` lida pelo módulo tools."""
    monkeypatch.setattr(
        tools_mod,
        "settings",
        dataclasses.replace(
            config.settings,
            voc_whatsapp_tool_enabled=enabled,
            notify_cooldown_hours=cooldown_hours,
        ),
    )


async def _org(session) -> Organization:
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _contact(session, org, *, phone=MOBILE, name="Ana", opt_in=True, partner=None) -> Contact:
    c = Contact(
        organization_id=org.id,
        phone=phone,
        name=name,
        opt_in=opt_in,
        profile_data=({"partner": partner} if partner else {}),
    )
    session.add(c)
    await session.commit()
    return c


async def _feedback(session, org, contact=None, **kw) -> FeedbackItem:
    f = FeedbackItem(
        organization_id=org.id,
        contact_id=(contact.id if contact else None),
        source=kw.pop("source", "whatsapp"),
        type=kw.pop("type", "nps"),
        text=kw.pop("text", "achei caro"),
        score=kw.pop("score", 3),
        nps_bucket=kw.pop("nps_bucket", "detractor"),
        **kw,
    )
    session.add(f)
    await session.commit()
    return f


def _ctx(session, org, *, messaging=None) -> VoCToolContext:
    return VoCToolContext(
        session=session, org_id=org.id, messaging=messaging, waha_session="default", now=lambda: NOW
    )


# --- (1) registrar abordagem ------------------------------------------------------


@pytest.mark.asyncio
async def test_registrar_abordagem(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))

    out = await reg.dispatch(
        ToolCall(id="1", name="registrar_abordagem", arguments={"feedback_id": str(f.id), "nota": "liguei"})
    )
    assert '"ok": true' in out
    await session.refresh(f)
    assert f.abordado is True
    assert f.abordado_em is not None
    assert f.action_note == "liguei"


@pytest.mark.asyncio
async def test_registrar_abordagem_feedback_inexistente(session):
    org = await _org(session)
    reg = build_default_registry(_ctx(session, org))
    import uuid as _uuid

    out = await reg.dispatch(
        ToolCall(id="1", name="registrar_abordagem", arguments={"feedback_id": str(_uuid.uuid4())})
    )
    assert '"ok": false' in out


# --- (2) aplicar selo / tag -------------------------------------------------------


@pytest.mark.asyncio
async def test_aplicar_selo(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))

    out = await reg.dispatch(
        ToolCall(
            id="1",
            name="aplicar_selo",
            arguments={"feedback_id": str(f.id), "team_tag": "produto", "assignee": "felipe"},
        )
    )
    assert '"ok": true' in out
    await session.refresh(f)
    assert f.team_tag == "produto"
    assert f.assignee == "felipe"


@pytest.mark.asyncio
async def test_aplicar_selo_sem_campos_falha(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))
    out = await reg.dispatch(
        ToolCall(id="1", name="aplicar_selo", arguments={"feedback_id": str(f.id)})
    )
    assert '"ok": false' in out


# --- (3) criar tarefa -------------------------------------------------------------


@pytest.mark.asyncio
async def test_criar_tarefa(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))

    out = await reg.dispatch(
        ToolCall(
            id="1",
            name="criar_tarefa",
            arguments={
                "title": "Ligar para Ana",
                "contact_id": str(c.id),
                "feedback_id": str(f.id),
                "priority": "alta",
                "sla_hours": 24,
                "reason": "detratora",
            },
        )
    )
    assert '"ok": true' in out
    tasks = (await session.execute(select(CsTask))).scalars().all()
    assert len(tasks) == 1
    t = tasks[0]
    assert t.title == "Ligar para Ana"
    assert t.priority == "alta"
    assert t.contact_id == c.id
    assert t.feedback_item_id == f.id
    assert t.playbook_id is None
    assert t.dedup_key is None
    # SQLite devolve datetime naive; compara o instante ignorando tzinfo.
    assert t.due_at.replace(tzinfo=None) == (NOW + timedelta(hours=24)).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_criar_tarefa_sem_title_falha(session):
    org = await _org(session)
    reg = build_default_registry(_ctx(session, org))
    out = await reg.dispatch(ToolCall(id="1", name="criar_tarefa", arguments={"reason": "x"}))
    assert '"ok": false' in out
    assert (await session.execute(select(CsTask))).scalars().all() == []


@pytest.mark.asyncio
async def test_criar_tarefa_priority_invalida_vira_normal(session):
    org = await _org(session)
    reg = build_default_registry(_ctx(session, org))
    await reg.dispatch(
        ToolCall(id="1", name="criar_tarefa", arguments={"title": "T", "priority": "altíssima"})
    )
    t = (await session.execute(select(CsTask))).scalars().one()
    assert t.priority == "normal"


# --- (4) vincular melhoria --------------------------------------------------------


@pytest.mark.asyncio
async def test_vincular_melhoria(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    imp = Improvement(organization_id=org.id, title="App mais rápido", status="planejada")
    session.add(imp)
    await session.commit()
    reg = build_default_registry(_ctx(session, org))

    out = await reg.dispatch(
        ToolCall(
            id="1",
            name="vincular_melhoria",
            arguments={"feedback_id": str(f.id), "improvement_id": str(imp.id)},
        )
    )
    assert '"ok": true' in out
    await session.refresh(f)
    assert f.improvement_id == imp.id


@pytest.mark.asyncio
async def test_vincular_melhoria_inexistente_falha(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))
    import uuid as _uuid

    out = await reg.dispatch(
        ToolCall(
            id="1",
            name="vincular_melhoria",
            arguments={"feedback_id": str(f.id), "improvement_id": str(_uuid.uuid4())},
        )
    )
    assert '"ok": false' in out


# --- (5) atualizar feedback -------------------------------------------------------


@pytest.mark.asyncio
async def test_atualizar_feedback(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))

    out = await reg.dispatch(
        ToolCall(
            id="1",
            name="atualizar_feedback",
            arguments={
                "feedback_id": str(f.id),
                "action_status": "em_acompanhamento",
                "assignee": "carla",
                "action_note": "investigando",
            },
        )
    )
    assert '"ok": true' in out
    await session.refresh(f)
    assert f.action_status == "em_acompanhamento"
    assert f.assignee == "carla"
    assert f.action_note == "investigando"


@pytest.mark.asyncio
async def test_atualizar_feedback_status_invalido_falha(session):
    org = await _org(session)
    c = await _contact(session, org)
    f = await _feedback(session, org, c)
    reg = build_default_registry(_ctx(session, org))
    out = await reg.dispatch(
        ToolCall(
            id="1",
            name="atualizar_feedback",
            arguments={"feedback_id": str(f.id), "action_status": "inventado"},
        )
    )
    assert '"ok": false' in out
    await session.refresh(f)
    assert f.action_status == "a_abordar"  # inalterado (default de acompanhamento)


# --- (6) enviar WhatsApp: flag OFF = NO-OP ----------------------------------------


@pytest.mark.asyncio
async def test_enviar_whatsapp_flag_off_no_op(session, monkeypatch):
    _enable_whatsapp(monkeypatch, enabled=False)
    org = await _org(session)
    c = await _contact(session, org)
    fake = FakeMessagingService()
    reg = build_default_registry(_ctx(session, org, messaging=fake))

    out = await reg.dispatch(
        ToolCall(id="1", name="enviar_whatsapp", arguments={"contact_id": str(c.id), "mensagem": "oi"})
    )
    assert '"sent": false' in out
    assert "tool_desligada" in out
    # Nada enviado e nada gravado no transcript.
    assert fake.sent == []
    msgs = (await session.execute(select(Message))).scalars().all()
    assert msgs == []


# --- (6) enviar WhatsApp: flag ON + 3 gates ---------------------------------------


@pytest.mark.asyncio
async def test_enviar_whatsapp_flag_on_envia_quando_passa_os_gates(session, monkeypatch):
    _enable_whatsapp(monkeypatch, enabled=True)
    org = await _org(session)
    c = await _contact(session, org, opt_in=True, phone=MOBILE)
    fake = FakeMessagingService()
    reg = build_default_registry(_ctx(session, org, messaging=fake))

    out = await reg.dispatch(
        ToolCall(id="1", name="enviar_whatsapp", arguments={"contact_id": str(c.id), "mensagem": "Olá Ana!"})
    )
    assert '"sent": true' in out
    assert len(fake.sent) == 1
    assert fake.sent[0]["chat_id"] == MOBILE
    assert fake.sent[0]["text"] == "Olá Ana!"
    # Gravou o outbound (alimenta o cooldown).
    msgs = (await session.execute(select(Message))).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].direction == "outbound"


@pytest.mark.asyncio
async def test_enviar_whatsapp_gate_opt_in(session, monkeypatch):
    _enable_whatsapp(monkeypatch, enabled=True)
    org = await _org(session)
    c = await _contact(session, org, opt_in=False, phone=MOBILE)
    fake = FakeMessagingService()
    reg = build_default_registry(_ctx(session, org, messaging=fake))

    out = await reg.dispatch(
        ToolCall(id="1", name="enviar_whatsapp", arguments={"contact_id": str(c.id), "mensagem": "oi"})
    )
    assert "sem_opt_in" in out
    assert fake.sent == []


@pytest.mark.asyncio
async def test_enviar_whatsapp_gate_alcancavel(session, monkeypatch):
    _enable_whatsapp(monkeypatch, enabled=True)
    org = await _org(session)
    # Fixo (não é celular BR válido) → não alcançável no WhatsApp.
    c = await _contact(session, org, opt_in=True, phone="553133334444")
    fake = FakeMessagingService()
    reg = build_default_registry(_ctx(session, org, messaging=fake))

    out = await reg.dispatch(
        ToolCall(id="1", name="enviar_whatsapp", arguments={"contact_id": str(c.id), "mensagem": "oi"})
    )
    assert "sem_whatsapp" in out
    assert fake.sent == []


@pytest.mark.asyncio
async def test_enviar_whatsapp_gate_cooldown(session, monkeypatch):
    _enable_whatsapp(monkeypatch, enabled=True, cooldown_hours=20)
    org = await _org(session)
    c = await _contact(session, org, opt_in=True, phone=MOBILE)
    # Outbound recente (1h atrás) → dentro do cooldown de 20h.
    session.add(
        Message(
            organization_id=org.id,
            contact_id=c.id,
            direction="outbound",
            body="msg anterior",
            created_at=NOW - timedelta(hours=1),
        )
    )
    await session.commit()
    fake = FakeMessagingService()
    reg = build_default_registry(_ctx(session, org, messaging=fake))

    out = await reg.dispatch(
        ToolCall(id="1", name="enviar_whatsapp", arguments={"contact_id": str(c.id), "mensagem": "oi"})
    )
    assert "cooldown" in out
    assert fake.sent == []


@pytest.mark.asyncio
async def test_enviar_whatsapp_cooldown_expirado_envia(session, monkeypatch):
    _enable_whatsapp(monkeypatch, enabled=True, cooldown_hours=20)
    org = await _org(session)
    c = await _contact(session, org, opt_in=True, phone=MOBILE)
    # Outbound antigo (30h atrás) → fora do cooldown de 20h.
    session.add(
        Message(
            organization_id=org.id,
            contact_id=c.id,
            direction="outbound",
            body="msg antiga",
            created_at=NOW - timedelta(hours=30),
        )
    )
    await session.commit()
    fake = FakeMessagingService()
    reg = build_default_registry(_ctx(session, org, messaging=fake))

    out = await reg.dispatch(
        ToolCall(id="1", name="enviar_whatsapp", arguments={"contact_id": str(c.id), "mensagem": "oi de novo"})
    )
    assert '"sent": true' in out
    assert len(fake.sent) == 1


# --- (7) ler perfil do contato ----------------------------------------------------


@pytest.mark.asyncio
async def test_ler_perfil_contato(session):
    org = await _org(session)
    c = await _contact(session, org, partner={"profile": "ativo_fiel", "nps": {"score": 3}})
    await _feedback(session, org, c, type="nps", text="achei caro", score=3)
    await _feedback(session, org, c, type="churn", text="cancelei", score=None, nps_bucket=None)
    reg = build_default_registry(_ctx(session, org))

    out = await reg.dispatch(
        ToolCall(id="1", name="ler_perfil_contato", arguments={"contact_id": str(c.id)})
    )
    import json

    data = json.loads(out)
    assert data["ok"] is True
    assert data["contact"]["name"] == "Ana"
    assert data["contact"]["alcancavel"] is True
    assert data["partner"]["profile"] == "ativo_fiel"
    assert data["summary"]["feedback_items"] == 2
    assert len(data["recent"]) >= 2


@pytest.mark.asyncio
async def test_ler_perfil_contato_inexistente(session):
    org = await _org(session)
    reg = build_default_registry(_ctx(session, org))
    import uuid as _uuid

    out = await reg.dispatch(
        ToolCall(id="1", name="ler_perfil_contato", arguments={"contact_id": str(_uuid.uuid4())})
    )
    assert '"ok": false' in out


# --- registry monta as 7 tools ----------------------------------------------------


def test_registry_tem_as_7_tools():
    import uuid as _uuid

    ctx = VoCToolContext(session=None, org_id=_uuid.uuid4())  # não executa nada aqui
    reg = build_default_registry(ctx)
    nomes = set(reg.names())
    assert nomes == {
        "registrar_abordagem",
        "aplicar_selo",
        "criar_tarefa",
        "vincular_melhoria",
        "atualizar_feedback",
        "enviar_whatsapp",
        "ler_perfil_contato",
    }
    # Cada tool exposta no formato Groq tem schema de objeto.
    for tool in reg.as_tools():
        assert tool["type"] == "function"
        assert tool["function"]["parameters"]["type"] == "object"
