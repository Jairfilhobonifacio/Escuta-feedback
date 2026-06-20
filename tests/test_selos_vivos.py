"""Testes dos SELOS VIVOS (derivados do estado, read-only).

Duas frentes:
- `selos_vivos(...)` puro: deriva VIP/Detrator/Em risco/Novo/Renovação próxima dos
  campos REAIS do snapshot partner + health (HealthResult), sem tocar o banco.
- GET /api/contacts/{id}/360: expõe `contact.selos_vivos` e inclui itens kind="selo"
  na timeline quando há `profile_data["selos_log"]` (degrada p/ [] sem o log).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.db import get_session  # noqa: E402
from app.domain.cs.health import HealthResult, compute_health  # noqa: E402
from app.domain.selos_vivos import selos_vivos  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def _by_nome(selos: list[dict]) -> dict[str, dict]:
    return {s["nome"]: s for s in selos}


# --- selos_vivos (puro) ------------------------------------------------------


def test_vip_nps9():
    partner = {"nps": {"voted": True, "score": 9}, "subscription": {"state": "active_paying"}}
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert "VIP" in out
    assert out["VIP"]["cor"] == "#10b981"
    assert out["VIP"]["icone"] == "⭐"
    assert out["VIP"]["motivo"] == "NPS 9"
    assert "Detrator" not in out


def test_detrator_nps5():
    partner = {"nps": {"voted": True, "score": 5}, "subscription": {"state": "active_paying"}}
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert "Detrator" in out
    assert out["Detrator"]["cor"] == "#ef4444"
    assert out["Detrator"]["icone"] == "⚠️"
    assert out["Detrator"]["motivo"] == "NPS 5"
    assert "VIP" not in out


def test_detrator_so_se_votou():
    # Nota baixa mas não votou (voted False e sem score numérico) -> sem Detrator.
    partner = {"nps": {"voted": False}, "subscription": {}}
    assert _by_nome(selos_vivos(None, partner, None, now=NOW)) == {}


def test_em_risco_churn_cancelada():
    # Assinatura cancelada (cancelled True) dispara "Em risco" mesmo sem health.
    partner = {"subscription": {"state": "cancelled", "cancelled": True}}
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert "Em risco" in out
    assert out["Em risco"]["cor"] == "#f59e0b"
    assert out["Em risco"]["icone"] == "🔻"
    assert out["Em risco"]["motivo"] == "Assinatura cancelada"


def test_em_risco_por_health_band():
    # Health band at_risk dispara "Em risco" mesmo com assinatura não cancelada.
    partner = {"subscription": {"state": "active_paying"}}
    health = HealthResult(score=20, band="at_risk")
    out = _by_nome(selos_vivos(None, partner, health, now=NOW))
    assert out["Em risco"]["motivo"] == "Health em risco"


def test_novo_dias_menor_igual_30():
    partner = {"subscription": {"state": "active_paying", "daysAsSubscriber": 30}}
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert "Novo" in out
    assert out["Novo"]["cor"] == "#6366f1"
    assert out["Novo"]["icone"] == "🌱"
    assert out["Novo"]["motivo"] == "30 dias de casa"


def test_nao_novo_acima_de_30():
    partner = {"subscription": {"state": "active_paying", "daysAsSubscriber": 31}}
    assert "Novo" not in _by_nome(selos_vivos(None, partner, None, now=NOW))


def test_renovacao_proxima_15_dias_e_ativo():
    renova = (NOW + timedelta(days=10)).isoformat()
    partner = {"subscription": {"state": "active_paying", "currentPeriodEnd": renova}}
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert "Renovação próxima" in out
    assert out["Renovação próxima"]["cor"] == "#8b5cf6"
    assert out["Renovação próxima"]["icone"] == "🔁"
    assert out["Renovação próxima"]["motivo"] == "renova em 10 dias"


def test_renovacao_nao_dispara_se_cancelada():
    # Renova em 10 dias MAS cancelada -> não é "renovação próxima" (e vira "Em risco").
    renova = (NOW + timedelta(days=10)).isoformat()
    partner = {"subscription": {"state": "cancelled", "cancelled": True, "currentPeriodEnd": renova}}
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert "Renovação próxima" not in out
    assert "Em risco" in out


def test_renovacao_fora_da_janela():
    renova = (NOW + timedelta(days=40)).isoformat()
    partner = {"subscription": {"state": "active_paying", "currentPeriodEnd": renova}}
    assert "Renovação próxima" not in _by_nome(selos_vivos(None, partner, None, now=NOW))


def test_acumula_varios_selos():
    # VIP + Novo + Renovação próxima ao mesmo tempo (cliente novo, promotor, renovando).
    renova = (NOW + timedelta(days=5)).isoformat()
    partner = {
        "nps": {"voted": True, "score": 10},
        "subscription": {"state": "active_paying", "daysAsSubscriber": 12, "currentPeriodEnd": renova},
    }
    out = _by_nome(selos_vivos(None, partner, None, now=NOW))
    assert set(out) == {"VIP", "Novo", "Renovação próxima"}


def test_sem_partner_nao_quebra():
    assert selos_vivos(None, None, None, now=NOW) == []
    assert selos_vivos(None, {}, None, now=NOW) == []
    # snapshot sujo (tipos errados) também não quebra.
    assert selos_vivos(None, {"nps": "x", "subscription": 5}, None, now=NOW) == []


# --- /api/contacts/{id}/360 --------------------------------------------------


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


@pytest_asyncio.fixture
async def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_360_expoe_selos_vivos_e_timeline_selo(client, session, org):
    """Contato promotor com histórico de selo: contact.selos_vivos traz VIP e a
    timeline inclui o evento kind="selo" ordenado por data desc."""
    contact = Contact(
        organization_id=org.id,
        phone="5531988887777",
        name="Maria",
        opt_in=True,
        profile_data={
            "partner": {"profile": "ativo_promotor", "nps": {"voted": True, "score": 10},
                        "subscription": {"state": "active_paying"}},
            "selos": ["contatado"],
            "selos_log": [
                {"selo": "contatado", "acao": "aplicado", "at": "2026-06-10T09:00:00+00:00",
                 "por": "operador", "origem": "manual"},
                {"selo": "cortesia", "acao": "removido", "at": "2026-06-12T09:00:00+00:00",
                 "por": None, "origem": "campanha"},
            ],
        },
    )
    session.add(contact)
    await session.commit()

    r = await client.get(f"/api/contacts/{contact.id}/360")
    assert r.status_code == 200, r.text
    data = r.json()

    # selos_vivos no bloco contact (VIP por NPS 10).
    nomes = {s["nome"] for s in data["contact"]["selos_vivos"]}
    assert "VIP" in nomes

    # timeline ganha itens kind="selo" com o contrato exato.
    selo_items = [t for t in data["timeline"] if t["kind"] == "selo"]
    assert len(selo_items) == 2
    primeiro = selo_items[0]
    assert set(primeiro) == {"kind", "selo", "acao", "at", "por", "origem"}
    # Ordenado por data desc: o evento de 06-12 (cortesia/removido) vem antes do de 06-10.
    assert selo_items[0]["selo"] == "cortesia" and selo_items[0]["acao"] == "removido"
    assert selo_items[1]["selo"] == "contatado"


@pytest.mark.asyncio
async def test_360_sem_selos_log_nao_quebra(client, session, org):
    """Sem profile_data['selos_log']: timeline não tem itens kind='selo', selos_vivos=[]
    quando não há snapshot que dispare nada."""
    contact = Contact(
        organization_id=org.id, phone="5531911112222", name="Joao", opt_in=True,
        profile_data={},
    )
    session.add(contact)
    await session.commit()

    r = await client.get(f"/api/contacts/{contact.id}/360")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["contact"]["selos_vivos"] == []
    assert [t for t in data["timeline"] if t["kind"] == "selo"] == []


# --- coerência health x selo "Em risco" --------------------------------------


def test_health_at_risk_consistente_com_selo():
    """Um churn real (perfil churn_pos_uso + cancelled) cai em band at_risk e o selo
    'Em risco' dispara — provando o uso conjunto health+partner do contrato."""
    health = compute_health(
        nps_score=8, perfil="churn_pos_uso", subscription_state="cancelled", now=NOW,
    )
    assert health.band == "at_risk"
    partner = {"profile": "churn_pos_uso",
               "subscription": {"state": "cancelled", "cancelled": True}, "nps": {"voted": True, "score": 8}}
    out = _by_nome(selos_vivos(None, partner, health, now=NOW))
    assert "Em risco" in out
