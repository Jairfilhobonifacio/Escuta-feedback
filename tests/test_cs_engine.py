"""Motor de Playbooks (Fase 2) — engine.run_playbooks.

Integração com SQLite in-memory (fixture `session` do conftest), sem rede. Cobre:
- dry_run=True não grava nada (só relata);
- idempotência por dedup_key (rodar 2x não duplica);
- cada gatilho resolve seus candidatos a partir do snapshot/feedback;
- a condição (trigger_config) é avaliada por comparação de chaves (sem eval);
- alert_owner só envia com dry_run=False + messaging + owner_phone.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.cs.engine import run_playbooks  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.playbook import CsTask, Playbook  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402

NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


async def _org(session, *, owner_phone: str | None = None):
    o = Organization(slug="bizzu", name="Bizzu", settings=({"owner_phone": owner_phone} if owner_phone else {}))
    session.add(o)
    await session.commit()
    return o


def _detractor_contact(org, phone="5531900000001", name="Ana", score=3):
    return Contact(
        organization_id=org.id, phone=phone, name=name, opt_in=True,
        profile_data={"partner": {"nps": {"score": score, "voted": True}}},
    )


async def _playbook(session, org, **kw):
    pb = Playbook(
        organization_id=org.id,
        name=kw.pop("name", "PB"),
        trigger_type=kw.pop("trigger_type", "nps_detractor"),
        trigger_config=kw.pop("trigger_config", {}),
        action_type=kw.pop("action_type", "create_task"),
        action_config=kw.pop("action_config", {"title": "Abordar {nome}", "sla_hours": 24}),
        enabled=kw.pop("enabled", True),
    )
    session.add(pb)
    await session.commit()
    return pb


# --- dry_run ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_nao_grava_nada(session):
    org = await _org(session)
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor", action_config={"title": "Abordar {nome}"})

    report = await run_playbooks(session, org.id, dry_run=True)
    assert report.dry_run is True
    assert report.evaluated == 1
    assert report.playbooks_run == 1
    assert len(report.tasks_would_create) == 1
    assert report.tasks_created == 0
    # Nada gravado.
    tasks = (await session.execute(select(CsTask))).scalars().all()
    assert tasks == []
    # O título interpolado já aparece no plano.
    assert report.tasks_would_create[0]["title"] == "Abordar Ana"
    assert report.tasks_would_create[0]["contato_nome"] == "Ana"


@pytest.mark.asyncio
async def test_wet_run_cria_tarefa_com_meta_e_due(session):
    org = await _org(session)
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(
        session, org, trigger_type="nps_detractor",
        action_config={"title": "Abordar {nome}", "priority": "alta", "sla_hours": 24, "owner": "cs"},
    )

    report = await run_playbooks(session, org.id, dry_run=False, now=NOW)
    assert report.tasks_created == 1
    task = (await session.execute(select(CsTask))).scalar_one()
    assert task.title == "Abordar Ana"
    assert task.priority == "alta"
    assert task.owner == "cs"
    assert task.status == "aberta"
    # SQLite descarta o tzinfo no round-trip; compara o valor naïve (UTC implícito).
    expected_due = (NOW + timedelta(hours=24)).replace(tzinfo=None)
    assert task.due_at.replace(tzinfo=None) == expected_due
    assert task.dedup_key == f"nps_detractor:{task.contact_id}:2026-06"
    # meta com snapshot do gatilho.
    assert task.meta["trigger_type"] == "nps_detractor"
    assert task.meta["nps_score"] == 3
    assert "health" in task.meta and "health_band" in task.meta


# --- idempotência -------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotente_por_dedup_key(session):
    org = await _org(session)
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor")

    r1 = await run_playbooks(session, org.id, dry_run=False, now=NOW)
    assert r1.tasks_created == 1
    # Segunda rodada no MESMO mês não duplica.
    r2 = await run_playbooks(session, org.id, dry_run=False, now=NOW)
    assert r2.tasks_created == 0
    assert r2.skipped_duplicate == 1
    assert len(r2.tasks_would_create) == 0
    tasks = (await session.execute(select(CsTask))).scalars().all()
    assert len(tasks) == 1


@pytest.mark.asyncio
async def test_mes_seguinte_cria_nova_tarefa(session):
    org = await _org(session)
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor")

    await run_playbooks(session, org.id, dry_run=False, now=datetime(2026, 6, 13, tzinfo=timezone.utc))
    await run_playbooks(session, org.id, dry_run=False, now=datetime(2026, 7, 1, tzinfo=timezone.utc))
    tasks = (await session.execute(select(CsTask))).scalars().all()
    assert len(tasks) == 2  # uma por mês (dedup_key inclui YYYY-MM)


# --- cada gatilho -------------------------------------------------------------


@pytest.mark.asyncio
async def test_nps_detractor_respeita_max_score(session):
    org = await _org(session)
    # score 6 entra (<=6 default); score 7 não.
    session.add_all([
        _detractor_contact(org, phone="5531900000001", name="Seis", score=6),
        _detractor_contact(org, phone="5531900000002", name="Sete", score=7),
    ])
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor")

    report = await run_playbooks(session, org.id, dry_run=False, now=NOW)
    nomes = {t["contato_nome"] for t in report.tasks_would_create}
    assert nomes == {"Seis"}
    assert report.tasks_created == 1


@pytest.mark.asyncio
async def test_nps_detractor_condicao_customizada_sem_eval(session):
    """trigger_config={'max_score':4}: comparação de chaves, não eval. 3 entra, 5 não."""
    org = await _org(session)
    session.add_all([
        _detractor_contact(org, phone="5531900000001", name="Tres", score=3),
        _detractor_contact(org, phone="5531900000002", name="Cinco", score=5),
    ])
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor", trigger_config={"max_score": 4})

    report = await run_playbooks(session, org.id, dry_run=True, now=NOW)
    assert {t["contato_nome"] for t in report.tasks_would_create} == {"Tres"}


@pytest.mark.asyncio
async def test_health_at_risk_usa_compute_health(session):
    org = await _org(session)
    # Detrator + churn → banda at_risk; promotor → healthy (não entra).
    risco = Contact(
        organization_id=org.id, phone="5531900000001", name="Risco", opt_in=True,
        profile_data={"partner": {"profile": "churn_rapido", "nps": {"score": 2},
                                   "subscription": {"state": "cancelled"}}},
    )
    feliz = Contact(
        organization_id=org.id, phone="5531900000002", name="Feliz", opt_in=True,
        profile_data={"partner": {"profile": "ativo_promotor", "nps": {"score": 10},
                                   "subscription": {"state": "active"}}},
    )
    session.add_all([risco, feliz])
    await session.commit()
    await _playbook(session, org, trigger_type="health_at_risk", trigger_config={"band": "at_risk"})

    report = await run_playbooks(session, org.id, dry_run=True, now=NOW)
    nomes = {t["contato_nome"] for t in report.tasks_would_create}
    assert "Risco" in nomes and "Feliz" not in nomes


@pytest.mark.asyncio
async def test_inactive_days_pega_sem_feedback_e_antigos(session):
    org = await _org(session)
    quieto = Contact(organization_id=org.id, phone="5531900000001", name="Quieto", opt_in=True, profile_data={})
    ativo = Contact(organization_id=org.id, phone="5531900000002", name="Ativo", opt_in=True, profile_data={})
    session.add_all([quieto, ativo])
    await session.flush()
    # Ativo deu feedback ontem; Quieto nunca.
    session.add(FeedbackItem(
        organization_id=org.id, contact_id=ativo.id, source="manual", type="nps",
        external_id="a1", score=8, occurred_at=NOW - timedelta(days=1),
    ))
    await session.commit()
    await _playbook(session, org, trigger_type="inactive_days", trigger_config={"days": 14})

    report = await run_playbooks(session, org.id, dry_run=True, now=NOW)
    nomes = {t["contato_nome"] for t in report.tasks_would_create}
    assert nomes == {"Quieto"}  # ativo (1d) fica de fora


@pytest.mark.asyncio
async def test_renewal_soon_janela_dias(session):
    org = await _org(session)
    # renova em 5 dias (entra, <=7); renova em 30 dias (não entra).
    perto = Contact(
        organization_id=org.id, phone="5531900000001", name="Perto", opt_in=True,
        profile_data={"partner": {"subscription": {"currentPeriodEnd": (NOW + timedelta(days=5)).isoformat()}}},
    )
    longe = Contact(
        organization_id=org.id, phone="5531900000002", name="Longe", opt_in=True,
        profile_data={"partner": {"subscription": {"currentPeriodEnd": (NOW + timedelta(days=30)).isoformat()}}},
    )
    session.add_all([perto, longe])
    await session.commit()
    await _playbook(session, org, trigger_type="renewal_soon", trigger_config={"days_before": 7})

    report = await run_playbooks(session, org.id, dry_run=True, now=NOW)
    assert {t["contato_nome"] for t in report.tasks_would_create} == {"Perto"}


@pytest.mark.asyncio
async def test_churn_detected_vincula_feedback_e_nao_repete(session):
    org = await _org(session)
    c = Contact(organization_id=org.id, phone="5531900000001", name="Cancelou", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=c.id, source="bizzu_billing", type="churn",
        external_id="ch1", text="muito caro", occurred_at=NOW - timedelta(days=1),
    )
    session.add(fb)
    await session.commit()
    await _playbook(session, org, trigger_type="churn_detected")

    r1 = await run_playbooks(session, org.id, dry_run=False, now=NOW)
    assert r1.tasks_created == 1
    task = (await session.execute(select(CsTask))).scalar_one()
    assert task.feedback_item_id == fb.id
    assert "caro" in (task.reason or "")
    # Já vinculado → não recria mesmo em mês diferente.
    r2 = await run_playbooks(session, org.id, dry_run=False, now=datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert r2.tasks_created == 0


# --- filtro de triggers + enabled --------------------------------------------


@pytest.mark.asyncio
async def test_so_avalia_enabled_e_filtra_por_triggers(session):
    org = await _org(session)
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(session, org, name="ativo", trigger_type="nps_detractor", enabled=True)
    await _playbook(session, org, name="off", trigger_type="nps_detractor", enabled=False)
    await _playbook(session, org, name="outro_gatilho", trigger_type="inactive_days", enabled=True)

    # Sem filtro: avalia os 2 enabled (nps_detractor + inactive_days), não o disabled.
    full = await run_playbooks(session, org.id, dry_run=True, now=NOW)
    assert full.evaluated == 2
    # Filtrando por trigger: só o nps_detractor ativo.
    filtered = await run_playbooks(session, org.id, triggers=["nps_detractor"], dry_run=True, now=NOW)
    assert filtered.evaluated == 1
    assert all(t["trigger_type"] == "nps_detractor" for t in filtered.tasks_would_create)


# --- alert_owner --------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_owner_so_envia_com_wet_run_e_owner_phone(session):
    org = await _org(session, owner_phone="5531999999999")
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor", action_type="alert_owner",
                    action_config={"title": "Olha o detrator {nome}"})

    fake = FakeMessagingService()
    # dry_run: não envia.
    r_dry = await run_playbooks(session, org.id, dry_run=True, messaging=fake, now=NOW)
    assert fake.sent == []
    assert len(r_dry.tasks_would_create) == 1  # ainda relata o que faria
    assert r_dry.tasks_created == 0

    # wet_run com owner_phone + messaging: envia 1 alerta, NÃO cria CsTask.
    r_wet = await run_playbooks(session, org.id, dry_run=False, messaging=fake, now=NOW)
    assert r_wet.alerts_sent == 1
    assert len(fake.sent) == 1
    assert fake.sent[0]["chat_id"] == "5531999999999"
    assert "Olha o detrator Ana" in fake.sent[0]["text"]
    assert r_wet.tasks_created == 0
    assert (await session.execute(select(CsTask))).scalars().all() == []


@pytest.mark.asyncio
async def test_alert_owner_sem_owner_phone_nao_envia(session):
    org = await _org(session)  # sem owner_phone
    session.add(_detractor_contact(org))
    await session.commit()
    await _playbook(session, org, trigger_type="nps_detractor", action_type="alert_owner")

    fake = FakeMessagingService()
    report = await run_playbooks(session, org.id, dry_run=False, messaging=fake, now=NOW)
    assert report.alerts_sent == 0
    assert fake.sent == []


@pytest.mark.asyncio
async def test_org_isolada(session):
    """Playbook/contatos de uma org não acionam tarefa em outra."""
    org_a = await _org(session)
    org_b = Organization(slug="outra", name="Outra", settings={})
    session.add(org_b)
    await session.flush()
    # contato detrator na org_b, playbook na org_a.
    session.add(Contact(
        organization_id=org_b.id, phone="5531900000099", name="Alheio", opt_in=True,
        profile_data={"partner": {"nps": {"score": 1}}},
    ))
    await session.commit()
    await _playbook(session, org_a, trigger_type="nps_detractor")

    report = await run_playbooks(session, org_a.id, dry_run=False, now=NOW)
    assert report.tasks_created == 0  # o detrator é da org_b
