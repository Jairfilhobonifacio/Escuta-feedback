"""Testes da Central de Monitoramento — /api/clientes, /api/feedbacks, PATCH.

Mesma infra de test_admin_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import compute_urgencia, get_brain, get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


class FakeClassifyLLM:
    """Dublê de GroqLLM só para classify_feedback: devolve um JSON fixo de tags.

    Aceita o mesmo `chat_json(system, user, **kw)` que o brain chama. Nenhum teste
    toca a Groq — a auto-classificação é exercida com este fake injetado em get_brain.
    """

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def chat_json(self, system, user, **kwargs):
        self.calls += 1
        return self.payload


def _brain_override(payload):
    """Override de get_brain → SurveyBrain(FakeClassifyLLM(payload))."""
    return lambda: SurveyBrain(FakeClassifyLLM(payload))

# Chaves exatas do item do feed (`_feedback_out`). Inclui `urgencia` (score 0-100),
# `assignee`/`team_tag` (Camada 2 — Board de Gestão) e `selos` (status de campanha
# do contato no inbox — camada win-back).
_ITEM_KEYS = {
    "id", "contato_id", "contato_nome", "contato_whatsapp", "selos", "source", "type",
    "score", "nps_bucket", "sentiment", "themes", "text", "urgencia",
    "action_status", "action_note", "assignee", "team_tag", "improvement_id",
    "abordado", "abordado_em", "occurred_em", "created_em",
}


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


# --- /api/clientes -----------------------------------------------------------


@pytest.mark.asyncio
async def test_clientes_enriquece_e_agrega(client, org, session):
    """Lista de clientes traz campos do snapshot partner + agregação de feedbacks,
    com as chaves exatas do contrato, e ordena por último feedback desc."""
    ana = Contact(
        organization_id=org.id, phone="5531900000001", name="Ana Promotora", opt_in=True,
        profile_data={
            "partner": {
                "profile": "ativo_promotor",
                "subscription": {
                    "planName": "Plano Anual",
                    "planType": "anual",
                    "currentPeriodEnd": "2999-01-01T00:00:00Z",
                },
                "nps": {"score": 9, "voted": True},
            }
        },
    )
    # Bia sem snapshot partner -> campos derivados ficam None.
    bia = Contact(organization_id=org.id, phone="5531900000002", name="Bia Sem Snapshot", opt_in=False, profile_data={})
    session.add_all([ana, bia])
    await session.flush()

    # Ana: 2 feedbacks (último = churn em 2026-06-05). Bia: nenhum.
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
                external_id="a:nps", score=9, nps_bucket="promoter", occurred_at=_dt(2026, 5, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
                external_id="a:churn", text="caro", occurred_at=_dt(2026, 6, 5),
            ),
        ]
    )
    await session.commit()

    data = (await client.get("/api/clientes")).json()
    assert len(data) == 2

    # Chaves exatas do contrato (inclui `selos` desde a camada de campanha win-back,
    # e `tem_whatsapp`/`estado` desde a correção do universo de churn).
    assert set(data[0].keys()) == {
        "id", "nome", "whatsapp", "opt_in", "tem_whatsapp", "estado", "selos",
        "perfil", "plano", "plan_type", "nps_score", "dias_para_renovar",
        "ultimo_feedback_em", "ultimo_feedback_tipo", "total_feedbacks",
        "health", "health_band", "health_factors", "criado_em",
    }

    by_name = {r["nome"]: r for r in data}
    a = by_name["Ana Promotora"]
    # tem WhatsApp real; sem state no snapshot -> estado None.
    assert a["tem_whatsapp"] is True
    assert a["estado"] is None
    assert a["perfil"] == "ativo_promotor"
    assert a["plano"] == "Plano Anual"  # planName preferido
    assert a["plan_type"] == "anual"
    assert a["nps_score"] == 9
    assert a["dias_para_renovar"] is not None and a["dias_para_renovar"] > 0
    assert a["total_feedbacks"] == 2
    assert a["ultimo_feedback_tipo"] == "churn"
    assert a["ultimo_feedback_em"].startswith("2026-06-05")
    # Health Score (Fase 1 CS): promotora NPS 9 + perfil ativo_promotor = saudável.
    assert a["health"] >= 70 and a["health_band"] == "healthy"
    assert isinstance(a["health_factors"], list) and len(a["health_factors"]) > 0

    b = by_name["Bia Sem Snapshot"]
    assert b["perfil"] is None and b["plano"] is None and b["nps_score"] is None
    assert b["dias_para_renovar"] is None
    assert b["total_feedbacks"] == 0
    assert b["ultimo_feedback_em"] is None and b["ultimo_feedback_tipo"] is None

    # Ordem: Ana (tem feedback) antes de Bia (nulls por último).
    assert data[0]["nome"] == "Ana Promotora"


@pytest.mark.asyncio
async def test_clientes_tem_whatsapp_e_estado(client, org, session):
    """`tem_whatsapp` False p/ placeholder 'nowa-' (ou phone vazio); `estado` vem do snapshot."""
    # Churn sem WhatsApp: phone placeholder 'nowa-' + state cancelled no snapshot.
    sem_wa = Contact(
        organization_id=org.id, phone="nowa-42", name="Sem Whats", opt_in=False,
        profile_data={
            "sem_whatsapp": True,
            "partner": {"profile": "churn_pos_uso", "subscription": {"state": "cancelled"}},
        },
    )
    # Cliente com WhatsApp real + state active_paying.
    com_wa = Contact(
        organization_id=org.id, phone="5531900000010", name="Com Whats", opt_in=True,
        profile_data={"partner": {"subscription": {"state": "active_paying"}}},
    )
    session.add_all([sem_wa, com_wa])
    await session.commit()

    data = (await client.get("/api/clientes")).json()
    by_name = {r["nome"]: r for r in data}
    assert by_name["Sem Whats"]["tem_whatsapp"] is False
    assert by_name["Sem Whats"]["estado"] == "cancelled"
    assert by_name["Com Whats"]["tem_whatsapp"] is True
    assert by_name["Com Whats"]["estado"] == "active_paying"


@pytest.mark.asyncio
async def test_clientes_filtros(client, org, session):
    ana = Contact(
        organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True,
        profile_data={"partner": {"profile": "ativo_promotor", "subscription": {"planType": "anual"}}},
    )
    bob = Contact(
        organization_id=org.id, phone="5531900000099", name="Bob", opt_in=True,
        profile_data={"partner": {"profile": "churn_pos_uso", "subscription": {"planType": "mensal"}}},
    )
    session.add_all([ana, bob])
    await session.commit()

    # search por nome
    r = (await client.get("/api/clientes", params={"search": "ana"})).json()
    assert [c["nome"] for c in r] == ["Ana"]
    # search por whatsapp (trecho)
    r = (await client.get("/api/clientes", params={"search": "000099"})).json()
    assert [c["nome"] for c in r] == ["Bob"]
    # perfil
    r = (await client.get("/api/clientes", params={"perfil": "churn_pos_uso"})).json()
    assert [c["nome"] for c in r] == ["Bob"]
    # plan_type
    r = (await client.get("/api/clientes", params={"plan_type": "anual"})).json()
    assert [c["nome"] for c in r] == ["Ana"]


@pytest.mark.asyncio
async def test_clientes_tem_whatsapp_real_fixo_vs_celular(client, org, session):
    """`tem_whatsapp` usa o validador real: FIXO (12 díg, sem o 9) -> False; celular -> True."""
    # Fixo real do piloto: a heurística antiga contava como WhatsApp; o validador não.
    fixo = Contact(
        organization_id=org.id, phone="553192973323", name="Fixo Cliente", opt_in=True, profile_data={}
    )
    cel = Contact(
        organization_id=org.id, phone="5531987654321", name="Celular Cliente", opt_in=True, profile_data={}
    )
    # Grupo (JID) também não é WhatsApp alcançável.
    grupo = Contact(
        organization_id=org.id, phone="120363247633739480", name="Grupo", opt_in=True, profile_data={}
    )
    session.add_all([fixo, cel, grupo])
    await session.commit()

    data = (await client.get("/api/clientes")).json()
    by_name = {r["nome"]: r for r in data}
    assert by_name["Fixo Cliente"]["tem_whatsapp"] is False
    assert by_name["Celular Cliente"]["tem_whatsapp"] is True
    assert by_name["Grupo"]["tem_whatsapp"] is False


@pytest.mark.asyncio
async def test_clientes_filtros_por_tipo_de_cliente(client, org, session):
    """Filtros novos de /api/clientes: estado, nps_bucket, health_band, tem_whatsapp."""
    # Cancelado, detrator (nps 3), fixo -> sem whatsapp.
    cancel_det_fixo = Contact(
        organization_id=org.id, phone="553192973323", name="Cancel Det Fixo", opt_in=False,
        profile_data={"partner": {
            "profile": "churn_pos_uso",
            "subscription": {"state": "cancelled"},
            "nps": {"score": 3},
        }},
    )
    # Ativo pagante, promotor (nps 10), celular -> com whatsapp + saudável.
    ativo_promo = Contact(
        organization_id=org.id, phone="5531987654321", name="Ativo Promo", opt_in=True,
        profile_data={"partner": {
            "profile": "ativo_promotor",
            "subscription": {"state": "active_paying"},
            "nps": {"score": 10},
        }},
    )
    # Ativo, neutro (nps 8), celular.
    ativo_neutro = Contact(
        organization_id=org.id, phone="5531999998888", name="Ativo Neutro", opt_in=True,
        profile_data={"partner": {
            "subscription": {"state": "active_paying"},
            "nps": {"score": 8},
        }},
    )
    session.add_all([cancel_det_fixo, ativo_promo, ativo_neutro])
    await session.commit()

    # estado (SQL JSON path)
    r = (await client.get("/api/clientes", params={"estado": "cancelled"})).json()
    assert [c["nome"] for c in r] == ["Cancel Det Fixo"]

    # nps_bucket (post-filter): promotor / neutro / detrator
    r = (await client.get("/api/clientes", params={"nps_bucket": "promotor"})).json()
    assert [c["nome"] for c in r] == ["Ativo Promo"]
    r = (await client.get("/api/clientes", params={"nps_bucket": "neutro"})).json()
    assert [c["nome"] for c in r] == ["Ativo Neutro"]
    r = (await client.get("/api/clientes", params={"nps_bucket": "detrator"})).json()
    assert [c["nome"] for c in r] == ["Cancel Det Fixo"]

    # tem_whatsapp (post-filter via validador): celular sim, fixo nao
    r = (await client.get("/api/clientes", params={"tem_whatsapp": "sim"})).json()
    assert {c["nome"] for c in r} == {"Ativo Promo", "Ativo Neutro"}
    r = (await client.get("/api/clientes", params={"tem_whatsapp": "nao"})).json()
    assert [c["nome"] for c in r] == ["Cancel Det Fixo"]

    # health_band (post-filter sobre a banda calculada): o promotor ativo é healthy.
    healthy = (await client.get("/api/clientes", params={"health_band": "healthy"})).json()
    nomes_healthy = {c["nome"] for c in healthy}
    assert "Ativo Promo" in nomes_healthy
    # cada item retornado de fato está na banda pedida.
    assert all(c["health_band"] == "healthy" for c in healthy)
    # banda inexistente -> lista vazia (post-filter não casa nada).
    vazio = (await client.get("/api/clientes", params={"health_band": "inexistente"})).json()
    assert vazio == []

    # combinação: estado + tem_whatsapp coerentes (cancelado é o único fixo)
    r = (await client.get("/api/clientes", params={"estado": "active_paying", "tem_whatsapp": "sim"})).json()
    assert {c["nome"] for c in r} == {"Ativo Promo", "Ativo Neutro"}


@pytest.mark.asyncio
async def test_clientes_filtro_abordado(client, org, session):
    """Filtro `abordado=sim|nao` com a MESMA semântica de /central/overview:
    abordado = selo 'contatado' OU abordagens não-vazias OU FeedbackItem.abordado==True."""
    # Abordado via selo 'contatado'.
    por_selo = Contact(
        organization_id=org.id, phone="5531900000001", name="PorSelo", opt_in=True,
        profile_data={"selos": ["contatado"]},
    )
    # Abordado via histórico de abordagens.
    por_abordagem = Contact(
        organization_id=org.id, phone="5531900000002", name="PorAbordagem", opt_in=True,
        profile_data={"abordagens": [{"canal": "whatsapp"}]},
    )
    # Abordado via FeedbackItem.abordado==True (sem selo/abordagem).
    por_feedback = Contact(
        organization_id=org.id, phone="5531900000003", name="PorFeedback", opt_in=True,
        profile_data={},
    )
    # NÃO abordado: tem feedback, mas abordado=False; sem selo/abordagem.
    nao_abordado = Contact(
        organization_id=org.id, phone="5531900000004", name="NaoAbordado", opt_in=True,
        profile_data={},
    )
    session.add_all([por_selo, por_abordagem, por_feedback, nao_abordado])
    await session.flush()
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=por_feedback.id, source="manual", type="churn",
                external_id="ab1", text="x", abordado=True, occurred_at=_dt(2026, 6, 5),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=nao_abordado.id, source="manual", type="churn",
                external_id="ab2", text="y", abordado=False, occurred_at=_dt(2026, 6, 5),
            ),
        ]
    )
    await session.commit()

    # abordado=sim: os 3 abordados (selo, abordagem, feedback.abordado).
    r = (await client.get("/api/clientes", params={"abordado": "sim"})).json()
    assert {c["nome"] for c in r} == {"PorSelo", "PorAbordagem", "PorFeedback"}

    # abordado=nao: o complemento (só o NaoAbordado).
    r = (await client.get("/api/clientes", params={"abordado": "nao"})).json()
    assert {c["nome"] for c in r} == {"NaoAbordado"}

    # sem o param: todos os 4 (comportamento idêntico ao anterior).
    r = (await client.get("/api/clientes")).json()
    assert {c["nome"] for c in r} == {"PorSelo", "PorAbordagem", "PorFeedback", "NaoAbordado"}


# --- /api/feedbacks ----------------------------------------------------------


@pytest.mark.asyncio
async def test_feedbacks_feed_e_filtro(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()

    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
                external_id="f1", score=3, nps_bucket="detractor", text="ruim", sentiment="negativo",
                themes=["preço"], occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="bizzu_billing", type="churn",
                external_id="f2", text="cancelei", sentiment="negativo", occurred_at=_dt(2026, 6, 10),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=None, source="bizzu_app", type="nps",
                external_id="f3", score=10, nps_bucket="promoter", text="amei", sentiment="positivo",
                occurred_at=_dt(2026, 6, 5),
            ),
        ]
    )
    await session.commit()

    # Feed completo: formato + ordem cronológica (sort=recente) + total + counts.
    data = (await client.get("/api/feedbacks", params={"sort": "recente"})).json()
    assert set(data.keys()) == {"items", "total", "counts_by_status"}
    assert data["total"] == 3
    assert data["counts_by_status"] == {
        "a_abordar": 3, "aguardando_retorno": 0, "em_acompanhamento": 0,
        "resolvido": 0, "sem_retorno": 0, "descartado": 0,
    }
    assert [i["external_id"] if False else i["type"] for i in data["items"]] == ["churn", "nps", "nps"]
    # ordem desc por occurred: f2 (06-10) > f3 (06-05) > f1 (06-01)
    assert data["items"][0]["text"] == "cancelei"
    assert data["items"][1]["text"] == "amei"

    # Chaves exatas do item (agora inclui `urgencia`).
    assert set(data["items"][0].keys()) == _ITEM_KEYS
    # contato juntado (f2 tem contato; f3 não)
    f2 = data["items"][0]
    assert f2["contato_nome"] == "Ana" and f2["contato_whatsapp"] == "5531900000001"
    f3 = data["items"][1]
    assert f3["contato_id"] is None and f3["contato_nome"] is None

    # Filtro por type
    only_nps = (await client.get("/api/feedbacks", params={"type": "nps"})).json()
    assert only_nps["total"] == 2
    assert all(i["type"] == "nps" for i in only_nps["items"])

    # Filtro por sentiment + search no texto
    r = (await client.get("/api/feedbacks", params={"sentiment": "negativo", "search": "cancel"})).json()
    assert r["total"] == 1 and r["items"][0]["text"] == "cancelei"

    # limit/offset não muda o total
    paged = (await client.get("/api/feedbacks", params={"limit": 1, "offset": 0})).json()
    assert paged["total"] == 3 and len(paged["items"]) == 1


@pytest.mark.asyncio
async def test_feedbacks_filtros_por_tipo_de_cliente(client, org, session):
    """Filtros novos de /api/feedbacks (sobre o CONTATO juntado): estado, perfil,
    plan_type, tem_whatsapp, nps_bucket — aplicados ao feed E às contagens (total bate)."""
    # Cliente A: cancelado, perfil churn, plano anual, celular, detrator (nps 3).
    a = Contact(
        organization_id=org.id, phone="5531987654321", name="Cliente A", opt_in=True,
        profile_data={"partner": {
            "profile": "churn_pos_uso",
            "subscription": {"state": "cancelled", "planType": "anual"},
            "nps": {"score": 3},
        }},
    )
    # Cliente B: ativo, perfil promotor, plano mensal, FIXO (sem whatsapp), promotor (nps 10).
    b = Contact(
        organization_id=org.id, phone="553192973323", name="Cliente B", opt_in=True,
        profile_data={"partner": {
            "profile": "ativo_promotor",
            "subscription": {"state": "active_paying", "planType": "mensal"},
            "nps": {"score": 10},
        }},
    )
    session.add_all([a, b])
    await session.flush()

    # 2 feedbacks p/ A (ambos 'novo'), 1 p/ B.
    session.add_all([
        FeedbackItem(
            organization_id=org.id, contact_id=a.id, source="bizzu_app", type="churn",
            external_id="ta1", text="cancelei A1", occurred_at=_dt(2026, 6, 1),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=a.id, source="bizzu_app", type="nps",
            external_id="ta2", score=3, nps_bucket="detractor", text="ruim A2", occurred_at=_dt(2026, 6, 2),
        ),
        FeedbackItem(
            organization_id=org.id, contact_id=b.id, source="bizzu_app", type="nps",
            external_id="tb1", score=10, nps_bucket="promoter", text="amei B1", occurred_at=_dt(2026, 6, 3),
        ),
    ])
    await session.commit()

    todos = (await client.get("/api/feedbacks")).json()
    assert todos["total"] == 3

    # estado=cancelled -> só os 2 feedbacks de A; counts batem com o total filtrado.
    r = (await client.get("/api/feedbacks", params={"estado": "cancelled"})).json()
    assert r["total"] == 2
    assert all(i["contato_nome"] == "Cliente A" for i in r["items"])
    assert sum(r["counts_by_status"].values()) == r["total"]

    # perfil=ativo_promotor -> só B (1).
    r = (await client.get("/api/feedbacks", params={"perfil": "ativo_promotor"})).json()
    assert r["total"] == 1 and r["items"][0]["contato_nome"] == "Cliente B"
    assert sum(r["counts_by_status"].values()) == 1

    # plan_type=anual -> só A (2).
    r = (await client.get("/api/feedbacks", params={"plan_type": "anual"})).json()
    assert r["total"] == 2 and all(i["contato_nome"] == "Cliente A" for i in r["items"])

    # tem_whatsapp=sim -> A (celular, 2 feedbacks); tem_whatsapp=nao -> B (fixo, 1).
    r = (await client.get("/api/feedbacks", params={"tem_whatsapp": "sim"})).json()
    assert r["total"] == 2 and all(i["contato_nome"] == "Cliente A" for i in r["items"])
    assert sum(r["counts_by_status"].values()) == 2
    r = (await client.get("/api/feedbacks", params={"tem_whatsapp": "nao"})).json()
    assert r["total"] == 1 and r["items"][0]["contato_nome"] == "Cliente B"
    assert sum(r["counts_by_status"].values()) == 1

    # nps_bucket=detrator -> A (nps 3, 2 feedbacks); promotor -> B (nps 10, 1).
    r = (await client.get("/api/feedbacks", params={"nps_bucket": "detrator"})).json()
    assert r["total"] == 2 and all(i["contato_nome"] == "Cliente A" for i in r["items"])
    r = (await client.get("/api/feedbacks", params={"nps_bucket": "promotor"})).json()
    assert r["total"] == 1 and r["items"][0]["contato_nome"] == "Cliente B"

    # combinação coerente: cancelled + plano anual = A (2).
    r = (await client.get("/api/feedbacks", params={"estado": "cancelled", "plan_type": "anual"})).json()
    assert r["total"] == 2


# --- PATCH /api/feedbacks/{id} ----------------------------------------------


@pytest.mark.asyncio
async def test_patch_feedback_status_e_nota(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
        external_id="p1", score=2, nps_bucket="detractor", text="péssimo", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(
        f"/api/feedbacks/{fb.id}",
        json={"action_status": "em_acompanhamento", "action_note": "Felipe vai ligar"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action_status"] == "em_acompanhamento"
    assert out["action_note"] == "Felipe vai ligar"
    # mesmo formato do feed
    assert set(out.keys()) == _ITEM_KEYS
    assert out["contato_nome"] == "Ana"

    # reflete no feed + counts
    feed = (await client.get("/api/feedbacks")).json()
    assert feed["counts_by_status"]["em_acompanhamento"] == 1
    assert feed["counts_by_status"]["a_abordar"] == 0


@pytest.mark.asyncio
async def test_patch_status_invalido_422(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="bizzu_app", type="nps",
        external_id="p2", score=2, text="x", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"action_status": "resolvendo"})
    assert r.status_code == 422
    # nada mudou (segue no default de acompanhamento)
    feed = (await client.get("/api/feedbacks")).json()
    assert feed["items"][0]["action_status"] == "a_abordar"


@pytest.mark.asyncio
async def test_patch_feedback_inexistente_404(client, org):
    import uuid

    r = await client.patch(f"/api/feedbacks/{uuid.uuid4()}", json={"action_status": "resolvido"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_id_invalido_422(client, org):
    r = await client.patch("/api/feedbacks/nao-e-uuid", json={"action_status": "resolvido"})
    assert r.status_code == 422


# --- POST /api/feedbacks (criar feedback manual) -----------------------------


@pytest.mark.asyncio
async def test_post_feedback_contato_existente(client, org, session):
    """POST com contato_id existente: cria o item, deriva nps_bucket, formato do feed."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()

    r = await client.post(
        "/api/feedbacks",
        json={
            "contato_id": str(ana.id),
            "type": "nps",
            "score": 9,
            "text": "atendimento excelente",
            "sentiment": "positivo",
            "themes": ["atendimento"],
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert set(out.keys()) == _ITEM_KEYS
    assert out["contato_id"] == str(ana.id)
    assert out["contato_nome"] == "Ana"
    assert out["contato_whatsapp"] == "5531900000001"
    assert out["source"] == "manual"  # default
    assert out["type"] == "nps"
    assert out["score"] == 9
    assert out["nps_bucket"] == "promoter"  # derivado
    assert out["sentiment"] == "positivo"
    assert out["themes"] == ["atendimento"]
    assert out["text"] == "atendimento excelente"
    assert out["action_status"] == "a_abordar"
    assert out["abordado"] is False
    assert out["abordado_em"] is None
    assert out["occurred_em"] is not None  # occurred_at = agora

    # aparece no feed
    feed = (await client.get("/api/feedbacks")).json()
    assert feed["total"] == 1
    assert feed["items"][0]["id"] == out["id"]


@pytest.mark.asyncio
async def test_post_feedback_cria_contato_por_whatsapp(client, org, session):
    """POST sem contato_id: acha/cria contato por whatsapp (só dígitos), opt_in=False."""
    r = await client.post(
        "/api/feedbacks",
        json={
            "contato_whatsapp": "+55 (31) 90000-0123",
            "contato_nome": "Carlos Novo",
            "type": "elogio",
            "text": "muito bom",
            "abordado": True,
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["contato_nome"] == "Carlos Novo"
    assert out["contato_whatsapp"] == "5531900000123"  # só dígitos
    assert out["type"] == "elogio"
    assert out["score"] is None and out["nps_bucket"] is None
    # abordado=True no create grava abordado_em
    assert out["abordado"] is True
    assert out["abordado_em"] is not None

    # contato foi criado sem opt-in (consentimento não vem de registro interno)
    contact = (
        await session.execute(select(Contact).where(Contact.phone == "5531900000123"))
    ).scalar_one()
    assert contact.opt_in is False
    assert contact.name == "Carlos Novo"

    # 2º feedback no mesmo whatsapp reusa o contato (não duplica)
    r2 = await client.post(
        "/api/feedbacks",
        json={"contato_whatsapp": "5531900000123", "type": "bug", "text": "travou"},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["contato_id"] == out["contato_id"]


@pytest.mark.asyncio
async def test_post_feedback_sem_contato_422(client, org):
    r = await client.post("/api/feedbacks", json={"type": "nps"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_feedback_type_invalido_422(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()
    r = await client.post("/api/feedbacks", json={"contato_id": str(ana.id), "type": "reclamacao"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_feedback_score_fora_de_faixa_422(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()
    r = await client.post("/api/feedbacks", json={"contato_id": str(ana.id), "type": "nps", "score": 11})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_feedback_whatsapp_invalido_422(client, org):
    r = await client.post("/api/feedbacks", json={"contato_whatsapp": "123", "type": "nps"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_feedback_contato_inexistente_404(client, org):
    import uuid

    r = await client.post("/api/feedbacks", json={"contato_id": str(uuid.uuid4()), "type": "nps"})
    assert r.status_code == 404


# --- PATCH edição completa ---------------------------------------------------


async def _make_feedback(session, org, **kw):
    c = kw.pop("contact", None)
    fb = FeedbackItem(
        organization_id=org.id,
        contact_id=(c.id if c else None),
        source=kw.pop("source", "manual"),
        type=kw.pop("type", "nps"),
        occurred_at=_dt(2026, 6, 1),
        **kw,
    )
    session.add(fb)
    await session.commit()
    return fb


@pytest.mark.asyncio
async def test_patch_marca_abordado_grava_abordado_em(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, nps_bucket="detractor", text="ruim")
    assert fb.abordado is False

    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"abordado": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["abordado"] is True
    assert out["abordado_em"] is not None

    # desmarcar zera abordado_em
    r2 = await client.patch(f"/api/feedbacks/{fb.id}", json={"abordado": False})
    out2 = r2.json()
    assert out2["abordado"] is False
    assert out2["abordado_em"] is None


@pytest.mark.asyncio
async def test_patch_abordado_em_nao_muda_se_ja_abordado(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, text="ruim")
    r1 = await client.patch(f"/api/feedbacks/{fb.id}", json={"abordado": True})
    first_em = r1.json()["abordado_em"]
    # re-marcar True não reescreve abordado_em
    r2 = await client.patch(f"/api/feedbacks/{fb.id}", json={"abordado": True, "action_status": "em_acompanhamento"})
    assert r2.json()["abordado_em"] == first_em


@pytest.mark.asyncio
async def test_patch_edita_conteudo_e_revalida_bucket(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, nps_bucket="detractor", text="ruim")

    # edita text/sentiment/themes e sobe o score → bucket revalida p/ promoter
    r = await client.patch(
        f"/api/feedbacks/{fb.id}",
        json={"text": "melhorou muito", "score": 10, "sentiment": "positivo", "themes": ["produto"]},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["text"] == "melhorou muito"
    assert out["score"] == 10
    assert out["nps_bucket"] == "promoter"
    assert out["sentiment"] == "positivo"
    assert out["themes"] == ["produto"]


@pytest.mark.asyncio
async def test_patch_muda_type_para_nao_nps_limpa_bucket(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=9, nps_bucket="promoter", text="x")
    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"type": "elogio"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["type"] == "elogio"
    assert out["nps_bucket"] is None  # type não-nps → sem bucket


@pytest.mark.asyncio
async def test_patch_type_invalido_422(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, text="x")
    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"type": "reclamacao"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_sentiment_invalido_422(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, text="x")
    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"sentiment": "ótimo"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_score_fora_de_faixa_422(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, text="x")
    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"score": 99})
    assert r.status_code == 422


# --- GET /api/feedbacks?abordado=... -----------------------------------------


@pytest.mark.asyncio
async def test_feedbacks_filtro_abordado(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    await _make_feedback(session, org, contact=ana, type="nps", score=3, text="a", external_id="x1", abordado=True)
    await _make_feedback(session, org, contact=ana, type="nps", score=4, text="b", external_id="x2", abordado=False)
    await _make_feedback(session, org, contact=ana, type="nps", score=5, text="c", external_id="x3", abordado=False)

    todos = (await client.get("/api/feedbacks")).json()
    assert todos["total"] == 3

    abordados = (await client.get("/api/feedbacks", params={"abordado": "true"})).json()
    assert abordados["total"] == 1
    assert all(i["abordado"] is True for i in abordados["items"])

    nao = (await client.get("/api/feedbacks", params={"abordado": "false"})).json()
    assert nao["total"] == 2
    assert all(i["abordado"] is False for i in nao["items"])


@pytest.mark.asyncio
async def test_feedbacks_filtro_abordado_periodo(client, org, session):
    """?abordado_periodo recorta os já abordados por carimbo `abordado_em`."""
    ana = Contact(organization_id=org.id, phone="5531900000009", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()

    agora = datetime.now(timezone.utc)
    dez_dias = agora - timedelta(days=10)
    await _make_feedback(
        session, org, contact=ana, type="nps", score=3, text="hoje",
        external_id="ap1", abordado=True, abordado_em=agora,
    )
    await _make_feedback(
        session, org, contact=ana, type="nps", score=4, text="antigo",
        external_id="ap2", abordado=True, abordado_em=dez_dias,
    )

    so_hoje = (await client.get("/api/feedbacks", params={"abordado_periodo": "hoje"})).json()
    assert so_hoje["total"] == 1
    assert {i["text"] for i in so_hoje["items"]} == {"hoje"}

    ultimos_30 = (await client.get("/api/feedbacks", params={"abordado_periodo": "30d"})).json()
    assert ultimos_30["total"] == 2
    assert {i["text"] for i in ultimos_30["items"]} == {"hoje", "antigo"}


# --- DELETE /api/feedbacks/{id} ----------------------------------------------


@pytest.mark.asyncio
async def test_delete_feedback_204(client, org, session):
    fb = await _make_feedback(session, org, type="nps", score=2, text="x")
    r = await client.delete(f"/api/feedbacks/{fb.id}")
    assert r.status_code == 204
    assert r.content == b""
    feed = (await client.get("/api/feedbacks")).json()
    assert feed["total"] == 0


@pytest.mark.asyncio
async def test_delete_feedback_inexistente_404(client, org):
    import uuid

    r = await client.delete(f"/api/feedbacks/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_feedback_de_outra_org_404(client, org, session):
    """Feedback de OUTRA org não pode ser deletado pela org atual (isolamento)."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    fb = FeedbackItem(
        organization_id=other.id, contact_id=None, source="manual", type="nps",
        score=1, text="alheio", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.delete(f"/api/feedbacks/{fb.id}")
    assert r.status_code == 404


# --- smoke E2E: criar -> editar -> abordar -> deletar ------------------------


@pytest.mark.asyncio
async def test_smoke_crud_completo(client, org, session):
    # criar
    r = await client.post(
        "/api/feedbacks",
        json={"contato_whatsapp": "5531988887777", "contato_nome": "Smoke", "type": "sugestao", "text": "ideia"},
    )
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    # editar conteúdo
    r = await client.patch(f"/api/feedbacks/{fid}", json={"type": "nps", "score": 8, "text": "ideia revisada"})
    assert r.status_code == 200, r.text
    assert r.json()["nps_bucket"] == "passive"

    # marcar abordado
    r = await client.patch(f"/api/feedbacks/{fid}", json={"abordado": True, "action_status": "resolvido"})
    assert r.status_code == 200, r.text
    assert r.json()["abordado"] is True and r.json()["abordado_em"] is not None

    # deletar
    r = await client.delete(f"/api/feedbacks/{fid}")
    assert r.status_code == 204
    feed = (await client.get("/api/feedbacks")).json()
    assert feed["total"] == 0


# --- Auto-classificação por IA no POST (brain dublado) -----------------------


@pytest.mark.asyncio
async def test_post_feedback_auto_classifica_quando_falta(client, org, session):
    """POST com text e SEM sentiment/themes: a IA preenche; ai_meta registra a autoria."""
    app.dependency_overrides[get_brain] = _brain_override(
        {"sentiment": "negativo", "themes": ["estabilidade"], "urgency": "alta"}
    )
    try:
        ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
        session.add(ana)
        await session.commit()

        r = await client.post(
            "/api/feedbacks",
            json={"contato_id": str(ana.id), "type": "outro", "text": "o app trava direto, péssimo"},
        )
        assert r.status_code == 201, r.text
        out = r.json()
        # campos vazios preenchidos pela IA
        assert out["sentiment"] == "negativo"
        assert out["themes"] == ["estabilidade"]
        # persistido no banco com ai_meta marcando a IA
        item = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == uuid.UUID(out["id"])))).scalar_one()
        assert item.ai_meta is not None
        assert item.ai_meta.get("classified_by") == "ai"
        assert item.ai_meta.get("urgency") == "alta"
    finally:
        app.dependency_overrides.pop(get_brain, None)


@pytest.mark.asyncio
async def test_post_feedback_nao_sobrescreve_o_que_felipe_informou(client, org, session):
    """Se o operador já informou sentiment/themes, a IA NÃO sobrescreve."""
    app.dependency_overrides[get_brain] = _brain_override(
        {"sentiment": "negativo", "themes": ["ia_tema"], "urgency": "alta"}
    )
    try:
        ana = Contact(organization_id=org.id, phone="5531900000002", name="Bia", opt_in=True, profile_data={})
        session.add(ana)
        await session.commit()

        r = await client.post(
            "/api/feedbacks",
            json={
                "contato_id": str(ana.id), "type": "elogio", "text": "adorei",
                "sentiment": "positivo", "themes": ["atendimento"],
            },
        )
        assert r.status_code == 201, r.text
        out = r.json()
        # mantém o que o operador disse (não vira 'negativo'/'ia_tema')
        assert out["sentiment"] == "positivo"
        assert out["themes"] == ["atendimento"]
    finally:
        app.dependency_overrides.pop(get_brain, None)


@pytest.mark.asyncio
async def test_post_feedback_sem_texto_nao_chama_ia(client, org, session):
    """Sem text não há o que classificar: nenhuma chamada à IA, sem ai_meta."""
    fake = FakeClassifyLLM({"sentiment": "negativo", "themes": ["x"], "urgency": "alta"})
    app.dependency_overrides[get_brain] = lambda: SurveyBrain(fake)
    try:
        ana = Contact(organization_id=org.id, phone="5531900000003", name="Cao", opt_in=True, profile_data={})
        session.add(ana)
        await session.commit()

        r = await client.post("/api/feedbacks", json={"contato_id": str(ana.id), "type": "bug"})
        assert r.status_code == 201, r.text
        assert fake.calls == 0  # IA não foi chamada
        item = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == uuid.UUID(r.json()["id"])))).scalar_one()
        assert item.ai_meta is None
    finally:
        app.dependency_overrides.pop(get_brain, None)


@pytest.mark.asyncio
async def test_post_feedback_degrada_com_llm_off(client, org, session):
    """get_brain=None (LLM OFF): feedback é criado mesmo assim, sem tags de IA."""
    app.dependency_overrides[get_brain] = lambda: None
    try:
        ana = Contact(organization_id=org.id, phone="5531900000004", name="Did", opt_in=True, profile_data={})
        session.add(ana)
        await session.commit()

        r = await client.post(
            "/api/feedbacks",
            json={"contato_id": str(ana.id), "type": "outro", "text": "qualquer coisa"},
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["sentiment"] is None and out["themes"] is None
        item = (await session.execute(select(FeedbackItem).where(FeedbackItem.id == uuid.UUID(out["id"])))).scalar_one()
        assert item.ai_meta is None
    finally:
        app.dependency_overrides.pop(get_brain, None)


# --- Score de urgência + ordenação -------------------------------------------


def test_compute_urgencia_prioriza_sinais_de_acao():
    """Unidade da fórmula: detrator/churn/negativo/em-risco/anual sobem; promotor abordado cai."""
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)

    # Pior caso: churn + negativo + detrator + em risco + anual + não abordado + recente.
    alto = compute_urgencia(
        sentiment="negativo", type_="churn", score=2, nps_bucket_value="detractor",
        abordado=False, occurred_at=now, created_at=now,
        partner={"profile": "ativo_em_risco", "subscription": {"planType": "anual"}}, now=now,
    )
    # Melhor caso: promotor, positivo, abordado, antigo, sem partner.
    baixo = compute_urgencia(
        sentiment="positivo", type_="nps", score=10, nps_bucket_value="promoter",
        abordado=True, occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc), partner=None, now=now,
    )
    assert alto == 100  # satura no teto
    assert baixo == 0
    assert alto > baixo

    # Detrator por NOTA (<=6) sem bucket também pontua.
    so_nota_baixa = compute_urgencia(
        sentiment=None, type_="nps", score=4, nps_bucket_value=None,
        abordado=True, occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc), partner=None, now=now,
    )
    assert so_nota_baixa == 20  # só o +20 de detração (abordado, antigo, sem mais sinais)


@pytest.mark.asyncio
async def test_feedbacks_sort_urgencia_default_coloca_critico_no_topo(client, org, session):
    """DEFAULT (sem sort): detrator/churn/em-risco no topo; promotor abordado no fim."""
    risco = Contact(
        organization_id=org.id, phone="5531900000001", name="Risco", opt_in=True,
        profile_data={"partner": {"profile": "ativo_em_risco", "subscription": {"planType": "anual"}}},
    )
    feliz = Contact(organization_id=org.id, phone="5531900000002", name="Feliz", opt_in=True, profile_data={})
    session.add_all([risco, feliz])
    await session.flush()

    session.add_all(
        [
            # promotor satisfeito, abordado, antigo → urgência baixa
            FeedbackItem(
                organization_id=org.id, contact_id=feliz.id, source="manual", type="nps",
                external_id="u_promo", score=10, nps_bucket="promoter", text="amei",
                sentiment="positivo", abordado=True, occurred_at=_dt(2026, 6, 11),
            ),
            # detrator + churn + negativo + em risco + anual + não abordado → urgência alta
            FeedbackItem(
                organization_id=org.id, contact_id=risco.id, source="manual", type="churn",
                external_id="u_churn", score=2, nps_bucket="detractor", text="cancelei tudo",
                sentiment="negativo", abordado=False, occurred_at=_dt(2026, 6, 1),
            ),
            # neutro, sem nota, não abordado → urgência média-baixa
            FeedbackItem(
                organization_id=org.id, contact_id=None, source="manual", type="sugestao",
                external_id="u_sug", text="seria bom ter modo escuro", abordado=False,
                occurred_at=_dt(2026, 6, 10),
            ),
        ]
    )
    await session.commit()

    data = (await client.get("/api/feedbacks")).json()
    textos = [i["text"] for i in data["items"]]
    # o churn crítico vem PRIMEIRO mesmo sendo o mais ANTIGO (urgência > recência)
    assert textos[0] == "cancelei tudo"
    # o promotor abordado vem por ÚLTIMO
    assert textos[-1] == "amei"
    # urgencia é monotonicamente não-crescente (feed ordenado por urgência desc)
    urg = [i["urgencia"] for i in data["items"]]
    assert urg == sorted(urg, reverse=True)
    assert all(0 <= u <= 100 for u in urg)


@pytest.mark.asyncio
async def test_feedbacks_sort_recente_mantem_cronologico(client, org, session):
    """sort=recente: ordem é occurred desc, ignorando urgência."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="churn",
                external_id="r1", text="antigo critico", sentiment="negativo", abordado=False,
                occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="elogio",
                external_id="r2", text="novo elogio", sentiment="positivo", abordado=True,
                occurred_at=_dt(2026, 6, 10),
            ),
        ]
    )
    await session.commit()

    data = (await client.get("/api/feedbacks", params={"sort": "recente"})).json()
    # cronológico: o mais novo (06-10) primeiro, apesar de menos urgente
    assert [i["text"] for i in data["items"]] == ["novo elogio", "antigo critico"]


@pytest.mark.asyncio
async def test_feedbacks_sort_urgencia_pagina_corretamente(client, org, session):
    """Paginação por urgência: limit/offset cortam DEPOIS do ranqueamento, total intacto."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    # 3 itens com urgências distintas e decrescentes por construção.
    session.add_all(
        [
            FeedbackItem(  # mais urgente
                organization_id=org.id, contact_id=ana.id, source="manual", type="churn",
                external_id="p1", score=1, nps_bucket="detractor", text="A", sentiment="negativo",
                abordado=False, occurred_at=_dt(2026, 6, 5),
            ),
            FeedbackItem(  # média
                organization_id=org.id, contact_id=ana.id, source="manual", type="nps",
                external_id="p2", score=4, nps_bucket="detractor", text="B", abordado=False,
                occurred_at=_dt(2026, 6, 5),
            ),
            FeedbackItem(  # menos urgente
                organization_id=org.id, contact_id=ana.id, source="manual", type="elogio",
                external_id="p3", text="C", sentiment="positivo", abordado=True,
                occurred_at=_dt(2026, 6, 5),
            ),
        ]
    )
    await session.commit()

    page1 = (await client.get("/api/feedbacks", params={"limit": 1, "offset": 0})).json()
    assert page1["total"] == 3 and len(page1["items"]) == 1
    assert page1["items"][0]["text"] == "A"  # o mais urgente

    page2 = (await client.get("/api/feedbacks", params={"limit": 1, "offset": 1})).json()
    assert page2["total"] == 3 and len(page2["items"]) == 1
    assert page2["items"][0]["text"] == "B"  # o segundo mais urgente

    page3 = (await client.get("/api/feedbacks", params={"limit": 1, "offset": 2})).json()
    assert page3["items"][0]["text"] == "C"  # o menos urgente
