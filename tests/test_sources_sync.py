"""Testes do serviço de sync da Central de Fontes — `app/domain/sources/sync.py`.

Exercita `run_bizzu_sync` com um FakeBizzuPartnerClient (NÃO toca a rede): dedup por
variante de telefone, enrich no shape `partner.subscription.state/planType` + `partner.
profile`, fail-soft por cliente e estado final pollável. O serviço cria a PRÓPRIA sessão
via `app.db.SessionLocal`; monkeypatchamos esse símbolo por um sessionmaker de um engine
SQLite in-memory compartilhado (StaticPool), espelhando o conftest.
"""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.sources import sync_state  # noqa: E402
from app.domain.sources.sync import run_bizzu_sync  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402

# --- Clientes fake (async iterators, sem rede) ---------------------------------


class FakeBizzuPartnerClient:
    """Rende uma lista fixa de PartnerCustomers (mesmo contrato do iter_all_customers real)."""

    def __init__(self, customers: list[dict]):
        self._customers = customers

    async def iter_all_customers(self, page_size: int = 100, **kwargs):
        for c in self._customers:
            yield c


class AuthErrorClient:
    """Estoura BizzuPartnerAuthError na 1ª página (simula chave ausente) — erro GLOBAL."""

    async def iter_all_customers(self, page_size: int = 100, **kwargs):
        from app.integrations.bizzu_partner import BizzuPartnerAuthError

        raise BizzuPartnerAuthError("BIZZU_PARTNER_API_KEY ausente")
        if False:  # pragma: no cover — torna a função um async generator
            yield


# Cliente válido: active_paying, plano mensal, NPS 10 -> perfil 'ativo_promotor'.
CUSTOMER_OK = {
    "id": "c-1",
    "name": "Maria Silva",
    "whatsapp": "5531999998888",
    "subscription": {"state": "active_paying", "planType": "mensal", "active": True},
    "nps": {"voted": True, "score": 10, "respondedAt": "2026-06-01T00:00:00+00:00"},
}
# Mesmo cliente, telefone SEM DDI (variante) e snapshot diferente -> deve casar e ATUALIZAR.
CUSTOMER_OK_VARIANT = {
    "id": "c-1",
    "name": "Maria Silva",
    "whatsapp": "31999998888",
    "subscription": {"state": "active_paying", "planType": "anual", "active": True},
    "nps": {"voted": True, "score": 8},
}
# Sem telefone válido -> conta como erro/pulo.
CUSTOMER_SEM_FONE = {"id": "c-2", "name": "Sem Fone", "whatsapp": "", "subscription": {}, "nps": {}}
# subscription malformado (str) -> classify_profile explode -> fail-soft (errors++, segue).
CUSTOMER_BOOM = {"id": "c-3", "name": "Boom", "whatsapp": "11988887777", "subscription": "boom"}


@pytest_asyncio.fixture
async def db_maker(monkeypatch):
    """Engine SQLite in-memory COMPARTILHADO (StaticPool) + SessionLocal monkeypatchado.

    StaticPool garante que as várias sessões (a do seed, a interna do serviço, a da
    verificação) enxergam o MESMO banco in-memory.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.db.SessionLocal", maker)
    try:
        yield maker
    finally:
        await engine.dispose()


async def _seed_org(maker) -> object:
    async with maker() as s:
        org = Organization(slug="bizzu", name="Bizzu", settings={})
        s.add(org)
        await s.commit()
        return org.id


async def _reload_org(maker, org_id):
    async with maker() as s:
        return (
            await s.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one()


async def _contacts(maker, org_id):
    async with maker() as s:
        return (
            await s.execute(select(Contact).where(Contact.organization_id == org_id))
        ).scalars().all()


@pytest.mark.asyncio
async def test_sync_cria_enrich_e_failsoft(db_maker):
    """1 cria (enrich correto) + 2 erros (sem-fone e explode) — lote não derruba; estado 'done'."""
    org_id = await _seed_org(db_maker)
    client = FakeBizzuPartnerClient([CUSTOMER_OK, CUSTOMER_SEM_FONE, CUSTOMER_BOOM])

    await run_bizzu_sync(org_id, page_size=100, client=client)

    contacts = await _contacts(db_maker, org_id)
    assert len(contacts) == 1  # só o válido virou contato
    c = contacts[0]
    assert c.phone == "5531999998888"  # gravado CANÔNICO
    assert c.opt_in is False
    partner = c.profile_data["partner"]
    assert partner["profile"] == "ativo_promotor"
    assert partner["subscription"]["state"] == "active_paying"
    assert partner["subscription"]["planType"] == "mensal"
    assert partner["nps"]["score"] == 10

    org = await _reload_org(db_maker, org_id)
    st = sync_state(org, "bizzu_partner")
    assert st["status"] == "done"
    assert st["processed"] == 3 and st["total"] == 3
    assert st["created"] == 1
    assert st["errors"] == 2  # sem-fone + explode
    assert st["updated"] == 0
    assert st["finished_at"] is not None
    assert st["error_msg"] is None


@pytest.mark.asyncio
async def test_sync_dedup_por_variante_atualiza(db_maker):
    """Re-sync com o telefone numa variante (sem DDI) casa o mesmo contato: atualiza, não duplica."""
    org_id = await _seed_org(db_maker)

    await run_bizzu_sync(org_id, client=FakeBizzuPartnerClient([CUSTOMER_OK]))
    assert len(await _contacts(db_maker, org_id)) == 1

    await run_bizzu_sync(org_id, client=FakeBizzuPartnerClient([CUSTOMER_OK_VARIANT]))
    contacts = await _contacts(db_maker, org_id)
    assert len(contacts) == 1  # NÃO duplicou
    partner = contacts[0].profile_data["partner"]
    # snapshot refrescado a partir da 2ª passada (plano anual, NPS 8 -> ativo_passivo)
    assert partner["subscription"]["planType"] == "anual"
    assert partner["nps"]["score"] == 8
    assert partner["profile"] == "ativo_passivo"

    org = await _reload_org(db_maker, org_id)
    st = sync_state(org, "bizzu_partner")
    assert st["status"] == "done"
    assert st["created"] == 0
    assert st["updated"] == 1


@pytest.mark.asyncio
async def test_sync_erro_global_vira_status_error(db_maker):
    """Falha global (auth) -> status='error' com mensagem curta (sem PII/chave); processed=0."""
    org_id = await _seed_org(db_maker)

    await run_bizzu_sync(org_id, client=AuthErrorClient())

    assert await _contacts(db_maker, org_id) == []
    org = await _reload_org(db_maker, org_id)
    st = sync_state(org, "bizzu_partner")
    assert st["status"] == "error"
    assert st["processed"] == 0
    assert st["error_msg"] and "Partner" in st["error_msg"]
    assert st["finished_at"] is not None
