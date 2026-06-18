"""Testes da CAMADA DE CAMPANHA WIN-BACK — /api/selos, outreach, stats, forms.

Mesma infra de test_monitoring_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA. Tudo persiste em
JSON existente (Organization.settings / Contact.profile_data) — sem migration.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


@pytest_asyncio.fixture
async def client(session):
    fake = FakeMessagingService()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_messaging] = lambda: fake
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


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


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


# --- SELOS: catálogo + aplicação + remoção -----------------------------------


@pytest.mark.asyncio
async def test_selo_catalogo_upsert_idempotente(client, org, session):
    """POST /api/selos cria; re-POST com a mesma cor não duplica; cor atualiza."""
    r = await client.post("/api/selos", json={"nome": "cortesia", "cor": "#ffd700"})
    assert r.status_code == 201, r.text

    # GET reflete o catálogo + uso (ainda sem contatos com o selo).
    data = (await client.get("/api/selos")).json()
    assert set(data.keys()) == {"catalogo", "uso"}
    assert data["catalogo"] == [{"nome": "cortesia", "cor": "#ffd700"}]
    assert data["uso"] == {}

    # Re-POST com cor nova: idempotente por nome, atualiza a cor.
    await client.post("/api/selos", json={"nome": "cortesia", "cor": "#ff0000"})
    data = (await client.get("/api/selos")).json()
    assert data["catalogo"] == [{"nome": "cortesia", "cor": "#ff0000"}]


@pytest.mark.asyncio
async def test_aplicar_e_remover_selo_no_contato(client, org, session):
    """Aplica selo (cria no catálogo se novo), conta no uso, remove do contato."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    await session.commit()

    # Aplica um selo NOVO (não existia no catálogo) — deve criá-lo.
    r = await client.post(f"/api/contacts/{ana.id}/selos", json={"nome": "contatado", "cor": "#6366f1"})
    assert r.status_code == 201, r.text
    assert r.json()["selos"] == ["contatado"]

    # Catálogo passou a ter o selo; uso conta 1.
    data = (await client.get("/api/selos")).json()
    assert {"nome": "contatado", "cor": "#6366f1"} in data["catalogo"]
    assert data["uso"]["contatado"] == 1

    # Re-aplicar é idempotente (não duplica na lista do contato).
    await client.post(f"/api/contacts/{ana.id}/selos", json={"nome": "contatado"})
    sel = await session.execute(select(Contact).where(Contact.id == ana.id))
    assert sel.scalar_one().profile_data["selos"] == ["contatado"]

    # Remove o selo daquele contato (catálogo permanece).
    r = await client.delete(f"/api/contacts/{ana.id}/selos/contatado")
    assert r.status_code == 200, r.text
    assert r.json()["selos"] == []
    data = (await client.get("/api/selos")).json()
    assert data["uso"].get("contatado", 0) == 0
    assert any(it["nome"] == "contatado" for it in data["catalogo"])


@pytest.mark.asyncio
async def test_delete_selo_remove_do_catalogo_e_de_todos(client, org, session):
    """DELETE /api/selos/{nome} tira do catálogo E de todos os contatos."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    bob = await _contact(session, org, "5531900000002", "Bob")
    await session.commit()

    await client.post("/api/selos", json={"nome": "vip", "cor": "#abcdef"})
    await client.post(f"/api/contacts/{ana.id}/selos", json={"nome": "vip"})
    await client.post(f"/api/contacts/{bob.id}/selos", json={"nome": "vip"})

    data = (await client.get("/api/selos")).json()
    assert data["uso"]["vip"] == 2

    r = await client.delete("/api/selos/vip")
    assert r.status_code == 200, r.text
    assert r.json()["contatos_afetados"] == 2

    data = (await client.get("/api/selos")).json()
    assert all(it["nome"] != "vip" for it in data["catalogo"])
    assert data["uso"].get("vip", 0) == 0
    # Selo sumiu dos dois contatos.
    for cid in (ana.id, bob.id):
        c = (await session.execute(select(Contact).where(Contact.id == cid))).scalar_one()
        assert "vip" not in (c.profile_data.get("selos") or [])


@pytest.mark.asyncio
async def test_aplicar_selo_contato_inexistente_404(client, org):
    r = await client.post(f"/api/contacts/{uuid.uuid4()}/selos", json={"nome": "x"})
    assert r.status_code == 404


# --- OUTREACH: registrar abordagem -------------------------------------------


@pytest.mark.asyncio
async def test_outreach_grava_abordagem_e_marca_abordado(client, org, session):
    """POST outreach faz append na lista E marca abordado=True + abordado_em nos feedbacks."""
    ana = await _contact(session, org, "5531900000001", "Ana")
    fb1 = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
        external_id="c1", text="cancelei", abordado=False, occurred_at=_dt(2026, 6, 1),
    )
    fb2 = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
        external_id="c2", score=3, nps_bucket="detractor", text="ruim", abordado=False,
        occurred_at=_dt(2026, 6, 2),
    )
    session.add_all([fb1, fb2])
    await session.commit()

    r = await client.post(
        f"/api/contacts/{ana.id}/outreach",
        json={"canal": "whatsapp", "mensagem": "Oi Ana, tudo bem?", "oferta": "30% off", "por": "felipe"},
    )
    assert r.status_code == 201, r.text
    ab = r.json()["abordagem"]
    assert ab["canal"] == "whatsapp"
    assert ab["mensagem"] == "Oi Ana, tudo bem?"
    assert ab["oferta"] == "30% off"
    assert ab["por"] == "felipe"
    assert ab["at"] is not None

    # Gravou na lista de abordagens do contato.
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert len(c.profile_data["abordagens"]) == 1

    # Marcou abordado=True + abordado_em em TODOS os feedbacks do contato.
    fbs = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.contact_id == ana.id)))
        .scalars().all()
    )
    assert all(f.abordado is True and f.abordado_em is not None for f in fbs)

    # Aplicou o selo 'contatado' (board de clientes e stats batem) + garantiu no catálogo.
    assert c.profile_data["selos"] == ["contatado"]
    cat = (await client.get("/api/selos")).json()
    assert any(it["nome"] == "contatado" for it in cat["catalogo"])

    # GET retorna mais recente primeiro.
    await client.post(f"/api/contacts/{ana.id}/outreach", json={"canal": "ligacao"})
    lista = (await client.get(f"/api/contacts/{ana.id}/outreach")).json()
    assert len(lista) == 2
    assert lista[0]["canal"] == "ligacao"  # mais recente primeiro
    assert lista[1]["canal"] == "whatsapp"

    # Idempotente: 2ª abordagem não duplica o selo 'contatado'.
    c = (await session.execute(select(Contact).where(Contact.id == ana.id))).scalar_one()
    assert c.profile_data["selos"] == ["contatado"]


@pytest.mark.asyncio
async def test_outreach_contato_inexistente_404(client, org):
    r = await client.post(f"/api/contacts/{uuid.uuid4()}/outreach", json={"canal": "whatsapp"})
    assert r.status_code == 404


# --- CAMPANHA STATS ----------------------------------------------------------


@pytest.mark.asyncio
async def test_campanha_stats_universo_montado_a_mao(client, org, session):
    """Universo de churn com: 1 contatado (abordado), 1 com selo respondeu, 1 cortesia."""
    # churned1: churn por FeedbackItem, abordado (=contatado), com tema negativo.
    churn1 = await _contact(session, org, "5531900000001", "Churn Um")
    # churned2: churn por perfil do snapshot, com selo 'respondeu'.
    churn2 = await _contact(
        session, org, "5531900000002", "Churn Dois",
        profile_data={"partner": {"profile": "churn_pos_uso"}, "selos": ["respondeu"]},
    )
    # churned3: churn por FeedbackItem, com selo 'cortesia'.
    churn3 = await _contact(
        session, org, "5531900000003", "Churn Tres", profile_data={"selos": ["cortesia"]}
    )
    # nao_churn: NÃO entra no universo (promotor feliz).
    feliz = await _contact(session, org, "5531900000009", "Feliz")
    await session.flush()

    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=churn1.id, source="bizzu_billing", type="churn",
                external_id="s1", text="muito caro", sentiment="negativo", themes=["preço"],
                abordado=True, abordado_em=_dt(2026, 6, 2), occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=churn3.id, source="bizzu_billing", type="churn",
                external_id="s3", text="parei de usar", sentiment="negativo", themes=["uso", "preço"],
                abordado=False, occurred_at=_dt(2026, 6, 3),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=feliz.id, source="bizzu_app", type="nps",
                external_id="s9", score=10, nps_bucket="promoter", text="amei", sentiment="positivo",
                themes=["produto"], occurred_at=_dt(2026, 6, 4),
            ),
        ]
    )
    # Uma abordagem registrada para churn1 (por_canal).
    p = dict(churn1.profile_data or {})
    p["abordagens"] = [{"at": _dt(2026, 6, 2).isoformat(), "canal": "whatsapp"}]
    churn1.profile_data = p
    await session.commit()

    stats = (await client.get("/api/campanha/stats")).json()

    assert set(stats.keys()) == {
        "universo", "com_whatsapp", "sem_whatsapp", "por_alcance", "contatados",
        "responderam", "cortesia", "reativaram", "faltam", "por_canal", "por_selo",
        "funil", "insights",
    }
    # universo = churn1, churn2, churn3 (feliz fora)
    assert stats["universo"] == 3
    # todos os 3 do universo são celular BR válido -> com_whatsapp == universo, sem_whatsapp == 0
    assert stats["com_whatsapp"] == 3
    assert stats["sem_whatsapp"] == 0
    assert stats["com_whatsapp"] + stats["sem_whatsapp"] == stats["universo"]
    # por_alcance: os 3 são celulares válidos -> tudo no bucket 'whatsapp'.
    assert stats["por_alcance"] == {"whatsapp": 3}
    assert sum(stats["por_alcance"].values()) == stats["universo"]
    # Funil ANINHADO (cada etapa implica as anteriores):
    # contatados = churn1 (abordado) + churn2 (respondeu) + churn3 (cortesia⟹respondeu⟹contatado) = 3
    assert stats["contatados"] == 3
    # responderam = churn2 (selo respondeu) + churn3 (cortesia⟹respondeu) = 2
    assert stats["responderam"] == 2
    # cortesia = churn3 (selo cortesia)
    assert stats["cortesia"] == 1
    assert stats["reativaram"] == 0
    # faltam = universo(3) - contatados(3) = 0
    assert stats["faltam"] == 0

    assert stats["por_canal"] == {"whatsapp": 1}
    # por_selo conta os selos REALMENTE aplicados (não o funil aninhado)
    assert stats["por_selo"].get("respondeu") == 1
    assert stats["por_selo"].get("cortesia") == 1

    # funil cobre as 5 etapas na ordem.
    etapas = [f["etapa"] for f in stats["funil"]]
    assert etapas == ["a contatar", "contatado", "respondeu", "cortesia", "reativou"]
    counts = {f["etapa"]: f["count"] for f in stats["funil"]}
    assert counts["a contatar"] == 0 and counts["contatado"] == 3

    # insights: temas do universo (preço aparece em 2 feedbacks, ambos negativos).
    temas = {it["tema"]: it for it in stats["insights"]}
    assert "produto" not in temas  # tema do contato fora do universo
    assert temas["preço"]["count"] == 2 and temas["preço"]["neg"] == 2
    assert temas["uso"]["count"] == 1 and temas["uso"]["neg"] == 1


@pytest.mark.asyncio
async def test_campanha_stats_com_e_sem_whatsapp(client, org, session):
    """Universo por state + recorte com_whatsapp/sem_whatsapp via validador real.

    com_whatsapp = celular BR VÁLIDO (não basta "ter telefone"):
    - churn 'cancelled' com celular real -> com_whatsapp / por_alcance['whatsapp']
    - churn 'paid_without_access' com phone 'nowa-' -> sem_whatsapp / so_email
    - churn 'cancelled' com phone vazio -> sem_whatsapp / sem_contato
    - churn 'cancelled' com FIXO (10 díg, sem o 9) -> sem_whatsapp / por_alcance['fixo']
    - active_paying NÃO entra no universo
    """
    # cancelled + celular real (alcançável no WhatsApp)
    c1 = await _contact(
        session, org, "5531900000001", "Cancel Com WA",
        profile_data={"partner": {"subscription": {"state": "cancelled"}}},
    )
    # paid_without_access + placeholder nowa- (sem WhatsApp -> so_email)
    c2 = await _contact(
        session, org, "nowa-77", "Pwa Sem WA", opt_in=False,
        profile_data={
            "sem_whatsapp": True,
            "partner": {"subscription": {"state": "paid_without_access"}},
        },
    )
    # cancelled + phone vazio (sem WhatsApp -> sem_contato)
    c3 = await _contact(
        session, org, "", "Cancel Sem Phone", opt_in=False,
        profile_data={"partner": {"subscription": {"state": "cancelled"}}},
    )
    # cancelled + FIXO (DDD + 8 díg, sem o 9 inicial) -> sem WhatsApp / fixo
    c4 = await _contact(
        session, org, "553192973323", "Cancel Fixo", opt_in=False,
        profile_data={"partner": {"subscription": {"state": "cancelled"}}},
    )
    # active_paying -> fora do universo
    ativo = await _contact(
        session, org, "5531900000099", "Ativo",
        profile_data={"partner": {"subscription": {"state": "active_paying"}}},
    )
    await session.commit()

    stats = (await client.get("/api/campanha/stats")).json()
    # universo = c1, c2, c3, c4 (ativo fora)
    assert stats["universo"] == 4
    assert stats["com_whatsapp"] == 1  # só c1 (celular válido)
    assert stats["sem_whatsapp"] == 3  # c2 (nowa-) + c3 (vazio) + c4 (fixo)
    assert stats["com_whatsapp"] + stats["sem_whatsapp"] == stats["universo"]

    # por_alcance distribui o universo nos buckets do validador (soma == universo).
    assert stats["por_alcance"] == {
        "whatsapp": 1,   # c1 celular
        "so_email": 1,   # c2 nowa-
        "sem_contato": 1,  # c3 vazio
        "fixo": 1,       # c4 fixo
    }
    assert sum(stats["por_alcance"].values()) == stats["universo"]
    # FIXO conta como sem_whatsapp e cai em por_alcance['fixo']; celular em 'whatsapp'.
    assert stats["por_alcance"]["fixo"] == 1
    assert stats["por_alcance"]["whatsapp"] == stats["com_whatsapp"]


# --- FORMS IMPORT (idempotente) ----------------------------------------------


@pytest.mark.asyncio
async def test_forms_import_idempotente(client, org, session):
    """Importa respostas; rodar 2x NÃO duplica (dedup por external_id); aplica selo respondeu."""
    payload = {
        "rows": [
            {"whatsapp": "+55 (31) 90000-0001", "nome": "Ana Forms", "nota": 9, "texto": "ótimo"},
            {"nome": "Sem Whats", "nota": 3, "texto": "ruim"},  # dedup por nome
            {"email": "x@x.com"},  # sem whatsapp e sem nome -> skipped
        ]
    }

    r1 = (await client.post("/api/forms/import", json=payload)).json()
    assert r1 == {"created": 2, "updated": 0, "skipped": 1}

    # Criou 2 contatos + 2 feedbacks source='forms'.
    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars().all()
    )
    assert len(contacts) == 2
    forms_items = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.source == "forms")))
        .scalars().all()
    )
    assert len(forms_items) == 2
    # tipo derivado da nota: nota=9 -> nps; sem nota não há aqui (ambos têm nota)
    by_text = {f.text: f for f in forms_items}
    assert by_text["ótimo"].type == "nps" and by_text["ótimo"].nps_bucket == "promoter"
    assert by_text["ruim"].type == "nps" and by_text["ruim"].nps_bucket == "detractor"

    # Selo 'respondeu' aplicado aos contatos identificados + no catálogo.
    selos_cat = (await client.get("/api/selos")).json()
    assert any(it["nome"] == "respondeu" for it in selos_cat["catalogo"])
    assert selos_cat["uso"]["respondeu"] == 2

    # 2ª rodada idêntica: NÃO duplica (vira updated), sem novos contatos/feedbacks.
    r2 = (await client.post("/api/forms/import", json=payload)).json()
    assert r2 == {"created": 0, "updated": 2, "skipped": 1}

    contacts2 = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars().all()
    )
    assert len(contacts2) == 2
    forms_items2 = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.source == "forms")))
        .scalars().all()
    )
    assert len(forms_items2) == 2


@pytest.mark.asyncio
async def test_forms_import_sem_nota_vira_outro(client, org, session):
    """Linha sem nota: type='outro', score/bucket None; ainda aplica selo respondeu."""
    r = (
        await client.post(
            "/api/forms/import",
            json={"rows": [{"whatsapp": "5531988887777", "nome": "So Texto", "texto": "comentario"}]},
        )
    ).json()
    assert r == {"created": 1, "updated": 0, "skipped": 0}

    item = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.source == "forms")))
        .scalars().one()
    )
    assert item.type == "outro"
    assert item.score is None and item.nps_bucket is None
    assert item.text == "comentario"
