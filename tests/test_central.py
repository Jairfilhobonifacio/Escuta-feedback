"""Testes da API de AGREGAÇÃO da Central de Feedbacks (/api/central/*).

Mesma infra dos outros testes de API: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA/Groq.

A org default ('bizzu') é "quem está logado" no painel (via _get_org). Para o
isolamento, criamos também uma 2ª org ('rival') e provamos que seus dados NÃO
entram em nenhum dos agregados.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.admin import get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.cluster import FeedbackCluster  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
from app.models.survey import Survey, SurveyResponse, SurveyRun  # noqa: E402
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
async def orgs(session):
    """A = default ('bizzu', logada no painel); B = 'rival' (dados invisíveis a A)."""
    a = Organization(slug="bizzu", name="Bizzu", settings={})
    b = Organization(slug="rival", name="Rival", settings={})
    session.add_all([a, b])
    await session.commit()
    return a, b


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def _partner(state=None, **extra):
    sub = {}
    if state is not None:
        sub["state"] = state
    return {"partner": {"subscription": sub, **extra}}


async def _survey_response(session, org, contact, *, score, text=None, status="closed", source="whatsapp", bucket=None):
    """Cria Survey/SurveyRun/SurveyResponse mínimos p/ uma nota NPS coletada."""
    survey = Survey(organization_id=org.id, name=f"NPS {uuid.uuid4().hex[:6]}", type="nps", questions=[])
    session.add(survey)
    await session.flush()
    run = SurveyRun(survey_id=survey.id, organization_id=org.id)
    session.add(run)
    await session.flush()
    resp = SurveyResponse(
        survey_run_id=run.id,
        contact_id=contact.id,
        organization_id=org.id,
        status=status,
        answer_score=score,
        nps_bucket=bucket,
        answer_text=text,
        source=source,
        answered_at=_dt(2026, 6, 10),
        closed_at=_dt(2026, 6, 10) if status == "closed" else None,
    )
    session.add(resp)
    await session.flush()
    return resp


# --- /central/overview -------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_estrutura_e_isolamento(client, orgs, session):
    """Contrato completo do overview + prova que dados da org B não vazam."""
    a, b = orgs
    # Org A: dados ricos.
    ana = Contact(organization_id=a.id, phone="5531900000001", name="Ana", opt_in=True, profile_data=_partner("active_paying"))
    bob = Contact(organization_id=a.id, phone="5531900000002", name="Bob", opt_in=True, profile_data=_partner("cancelled"))
    session.add_all([ana, bob])
    await session.flush()

    # NPS via survey (Ana promotora) + via feedback_item (Bob detrator).
    await _survey_response(session, a, ana, score=10, text="amei", source="whatsapp")
    session.add(
        FeedbackItem(
            organization_id=a.id, contact_id=bob.id, source="bizzu_app", type="nps",
            external_id="b:nps", score=3, nps_bucket="detractor", text="ruim", sentiment="negativo",
            occurred_at=_dt(2026, 6, 5),
        )
    )
    # Feedback escrito extra (churn, sem nota).
    session.add(
        FeedbackItem(
            organization_id=a.id, contact_id=bob.id, source="bizzu_billing", type="churn",
            external_id="b:churn", text="cancelei", sentiment="negativo", occurred_at=_dt(2026, 6, 6),
        )
    )

    # Org B: ruído que NÃO pode aparecer nos agregados de A.
    rb = Contact(organization_id=b.id, phone="5531911111111", name="Rival", opt_in=True, profile_data=_partner("active_paying"))
    session.add(rb)
    await session.flush()
    await _survey_response(session, b, rb, score=1, text="lixo")
    session.add(
        FeedbackItem(
            organization_id=b.id, contact_id=rb.id, source="bizzu_app", type="nps",
            external_id="r:nps", score=2, text="da rival", occurred_at=_dt(2026, 6, 5),
        )
    )
    await session.commit()

    data = (await client.get("/api/central/overview")).json()

    # Estrutura top-level (metricas é ADITIVO — não quebra os 4 blocos originais).
    assert set(data.keys()) == {"nps", "feedbacks", "abordagem", "segmentos", "metricas"}
    assert set(data["metricas"].keys()) == {
        "taxa_resolucao", "loops_fechados", "tempo_1a_abordagem", "nps_por_tema"
    }
    assert set(data["nps"].keys()) == {
        "deram", "media", "promotores", "neutros", "detratores", "sem_resposta"
    }
    assert set(data["feedbacks"].keys()) == {"total", "com_texto", "por_fonte", "por_sentimento"}
    assert set(data["abordagem"].keys()) == {
        "contatos_total", "abordados", "responderam", "nao_responderam"
    }
    assert set(data["segmentos"].keys()) == {"churn", "ativos"}

    # NPS: 2 notas (10 da survey de A + 3 do feedback de A); a nota 1/2 da rival NÃO entra.
    nps = data["nps"]
    assert nps["deram"] == 2
    assert nps["media"] == 6.5  # (10 + 3) / 2
    assert nps["promotores"] == 1
    assert nps["detratores"] == 1
    assert nps["neutros"] == 0

    # Feedbacks: só os 2 de A (o da rival fica de fora). por_fonte só com fontes de A.
    fb = data["feedbacks"]
    assert fb["total"] == 2
    assert fb["com_texto"] == 2
    assert "bizzu_app" in fb["por_fonte"] and "bizzu_billing" in fb["por_fonte"]
    assert sum(fb["por_fonte"].values()) == 2
    assert fb["por_sentimento"]["negativo"] == 2

    # Segmentos têm o rótulo fixo do contrato.
    assert data["segmentos"]["churn"]["rotulo"] == "Cancelaram"
    assert data["segmentos"]["ativos"]["rotulo"] == "Ativos"
    # contatos_total só conta os 2 de A.
    assert data["abordagem"]["contatos_total"] == 2


@pytest.mark.asyncio
async def test_overview_abordagem_e_segmentos(client, orgs, session):
    """abordados/responderam/nao_responderam + recorte churn x ativos."""
    a, _b = orgs
    # Churn abordado E respondeu (selos).
    c1 = Contact(
        organization_id=a.id, phone="5531900000001", name="C1", opt_in=False,
        profile_data={"partner": {"subscription": {"state": "cancelled"}}, "selos": ["contatado", "respondeu"]},
    )
    # Churn abordado mas NÃO respondeu (só selo contatado).
    c2 = Contact(
        organization_id=a.id, phone="5531900000002", name="C2", opt_in=False,
        profile_data={"partner": {"subscription": {"state": "cancelled"}}, "selos": ["contatado"]},
    )
    # Churn nem abordado nem respondeu.
    c3 = Contact(
        organization_id=a.id, phone="5531900000003", name="C3", opt_in=False,
        profile_data=_partner("cancelled"),
    )
    # Ativo abordado via `abordagens` e respondeu via SurveyResponse closed.
    a1 = Contact(
        organization_id=a.id, phone="5531900000004", name="A1", opt_in=True,
        profile_data={"partner": {"subscription": {"state": "active_paying"}}, "abordagens": [{"canal": "whatsapp"}]},
    )
    session.add_all([c1, c2, c3, a1])
    await session.flush()
    await _survey_response(session, a, a1, score=9, status="closed")
    await session.commit()

    data = (await client.get("/api/central/overview")).json()

    # Geral: 4 contatos; abordados = c1,c2,a1 (3); responderam = c1,a1 (2).
    ab = data["abordagem"]
    assert ab["contatos_total"] == 4
    assert ab["abordados"] == 3
    assert ab["responderam"] == 2
    assert ab["nao_responderam"] == 1

    churn = data["segmentos"]["churn"]
    assert churn["total"] == 3  # c1, c2, c3
    assert churn["abordados"] == 2  # c1, c2
    assert churn["responderam"] == 1  # c1
    assert churn["nao_responderam"] == 1

    ativos = data["segmentos"]["ativos"]
    assert ativos["total"] == 1  # a1
    assert ativos["abordados"] == 1
    assert ativos["responderam"] == 1
    assert ativos["nao_responderam"] == 0


@pytest.mark.asyncio
async def test_overview_respondeu_implica_abordado(client, orgs, session):
    """Quem respondeu (selo 'respondeu') mas não tem selo 'contatado'/abordagens ainda
    conta como abordado — a tela nunca mostra responderam > abordados. (Ter feedback
    ingerido NÃO conta como 'respondeu' — é sinal da Bizzu, não resposta à abordagem.)"""
    a, _b = orgs
    pd = {**_partner("active_paying"), "selos": ["respondeu"]}
    c = Contact(organization_id=a.id, phone="5531900000001", name="C", opt_in=True, profile_data=pd)
    session.add(c)
    await session.commit()

    data = (await client.get("/api/central/overview")).json()
    ab = data["abordagem"]
    assert ab["responderam"] == 1
    assert ab["abordados"] == 1  # respondeu => também abordado
    assert ab["nao_responderam"] == 0


@pytest.mark.asyncio
async def test_overview_vazio(client, orgs, session):
    """Org sem dados: tudo zerado, média None, dicionários vazios (não quebra)."""
    data = (await client.get("/api/central/overview")).json()
    assert data["nps"] == {
        "deram": 0, "media": None, "promotores": 0, "neutros": 0, "detratores": 0, "sem_resposta": 0
    }
    assert data["feedbacks"]["total"] == 0
    assert data["feedbacks"]["por_fonte"] == {}
    assert data["feedbacks"]["por_sentimento"] == {"positivo": 0, "neutro": 0, "negativo": 0, "sem": 0}
    assert data["abordagem"]["contatos_total"] == 0
    assert data["segmentos"]["churn"]["total"] == 0


@pytest.mark.asyncio
async def test_overview_sem_resposta_conta_contatos_sem_nota(client, orgs, session):
    """sem_resposta = contatos da org sem NENHUMA nota (nas duas fontes)."""
    a, _b = orgs
    com_nota = Contact(organization_id=a.id, phone="5531900000001", name="ComNota", opt_in=True, profile_data={})
    sem_nota1 = Contact(organization_id=a.id, phone="5531900000002", name="SemNota1", opt_in=True, profile_data={})
    sem_nota2 = Contact(organization_id=a.id, phone="5531900000003", name="SemNota2", opt_in=True, profile_data={})
    session.add_all([com_nota, sem_nota1, sem_nota2])
    await session.flush()
    await _survey_response(session, a, com_nota, score=8)
    await session.commit()

    nps = (await client.get("/api/central/overview")).json()["nps"]
    assert nps["deram"] == 1
    assert nps["neutros"] == 1  # nota 8 = passive
    assert nps["sem_resposta"] == 2


# --- /central/nps ------------------------------------------------------------


@pytest.mark.asyncio
async def test_nps_lista_duas_fontes_ordenada(client, orgs, session):
    """/central/nps une survey_responses + feedback_items nps, ordena por data desc."""
    a, b = orgs
    ana = Contact(organization_id=a.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    bob = Contact(organization_id=a.id, phone="5531900000002", name="Bob", opt_in=True, profile_data={})
    session.add_all([ana, bob])
    await session.flush()

    # Survey (Ana, mais nova) + feedback (Bob, mais antigo).
    resp = await _survey_response(session, a, ana, score=9, text="recomendo", source="whatsapp")
    resp.answered_at = _dt(2026, 6, 20)
    resp.closed_at = _dt(2026, 6, 20)
    session.add(
        FeedbackItem(
            organization_id=a.id, contact_id=bob.id, source="bizzu_app", type="nps",
            external_id="b:nps", score=4, nps_bucket="detractor", text="fraco", occurred_at=_dt(2026, 6, 1),
        )
    )
    # Ruído de B: NÃO entra.
    rb = Contact(organization_id=b.id, phone="5531911111111", name="Rival", opt_in=True, profile_data={})
    session.add(rb)
    await session.flush()
    await _survey_response(session, b, rb, score=1)
    await session.commit()

    data = (await client.get("/api/central/nps")).json()
    assert set(data.keys()) == {"media", "items"}
    assert data["media"] == 6.5  # (9 + 4) / 2
    assert len(data["items"]) == 2

    # Chaves exatas do item do contrato.
    assert set(data["items"][0].keys()) == {
        "contact_id", "nome", "telefone", "score", "bucket", "motivo", "fonte", "em"
    }
    # Ordem desc por data: Ana (06-20) antes de Bob (06-01).
    assert data["items"][0]["nome"] == "Ana"
    assert data["items"][0]["fonte"] == "whatsapp"
    assert data["items"][0]["motivo"] == "recomendo"
    assert data["items"][1]["nome"] == "Bob"
    assert data["items"][1]["fonte"] == "bizzu_app"
    assert data["items"][1]["bucket"] == "detractor"


@pytest.mark.asyncio
async def test_nps_bucket_derivado_quando_ausente(client, orgs, session):
    """Quando nps_bucket não foi gravado, ele é derivado do score."""
    a, _b = orgs
    c = Contact(organization_id=a.id, phone="5531900000001", name="C", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    # Survey sem bucket gravado (score 10) + feedback sem bucket (score 5).
    await _survey_response(session, a, c, score=10, bucket=None)
    session.add(
        FeedbackItem(
            organization_id=a.id, contact_id=c.id, source="bizzu_app", type="nps",
            external_id="x", score=5, nps_bucket=None, text="meh", occurred_at=_dt(2026, 6, 1),
        )
    )
    await session.commit()

    items = (await client.get("/api/central/nps")).json()["items"]
    by_score = {i["score"]: i for i in items}
    assert by_score[10]["bucket"] == "promoter"
    assert by_score[5]["bucket"] == "detractor"


@pytest.mark.asyncio
async def test_nps_vazio(client, orgs, session):
    data = (await client.get("/api/central/nps")).json()
    assert data == {"media": None, "items": []}


# --- /central/feedbacks ------------------------------------------------------


@pytest.mark.asyncio
async def test_feedbacks_so_escritos_e_filtros(client, orgs, session):
    """Só feedbacks com texto; filtros por sentimento/fonte/abordado; isolamento."""
    a, b = orgs
    ana = Contact(organization_id=a.id, phone="5531900000001", name="Ana", opt_in=True, profile_data=_partner("cancelled"))
    session.add(ana)
    await session.flush()

    session.add_all(
        [
            FeedbackItem(
                organization_id=a.id, contact_id=ana.id, source="whatsapp", type="churn",
                external_id="f1", text="cancelei", sentiment="negativo", abordado=True,
                occurred_at=_dt(2026, 6, 10),
            ),
            FeedbackItem(
                organization_id=a.id, contact_id=ana.id, source="bizzu_app", type="elogio",
                external_id="f2", text="amei", sentiment="positivo", abordado=False,
                occurred_at=_dt(2026, 6, 5),
            ),
            # SEM texto: não aparece.
            FeedbackItem(
                organization_id=a.id, contact_id=ana.id, source="bizzu_app", type="nps",
                external_id="f3", score=9, text=None, occurred_at=_dt(2026, 6, 7),
            ),
            # Texto só com espaços: também não aparece.
            FeedbackItem(
                organization_id=a.id, contact_id=ana.id, source="bizzu_app", type="outro",
                external_id="f4", text="   ", occurred_at=_dt(2026, 6, 8),
            ),
        ]
    )
    # Ruído de B com texto: NÃO entra.
    rb = Contact(organization_id=b.id, phone="5531911111111", name="Rival", opt_in=True, profile_data={})
    session.add(rb)
    await session.flush()
    session.add(
        FeedbackItem(
            organization_id=b.id, contact_id=rb.id, source="whatsapp", type="churn",
            external_id="rf", text="da rival", sentiment="negativo", occurred_at=_dt(2026, 6, 9),
        )
    )
    await session.commit()

    # Sem filtro: só os 2 escritos de A, ordenados por data desc.
    data = (await client.get("/api/central/feedbacks")).json()
    assert set(data.keys()) == {"total", "items"}
    assert data["total"] == 2
    assert set(data["items"][0].keys()) == {
        "contato_id", "nome", "fonte", "sentimento", "tipo", "texto", "abordado", "em", "estado"
    }
    assert [i["texto"] for i in data["items"]] == ["cancelei", "amei"]
    # estado vem do snapshot partner do contato.
    assert data["items"][0]["estado"] == "cancelled"

    # Filtro sentimento.
    r = (await client.get("/api/central/feedbacks", params={"sentimento": "positivo"})).json()
    assert r["total"] == 1 and r["items"][0]["texto"] == "amei"

    # Filtro fonte.
    r = (await client.get("/api/central/feedbacks", params={"fonte": "whatsapp"})).json()
    assert r["total"] == 1 and r["items"][0]["texto"] == "cancelei"

    # Filtro abordado.
    r = (await client.get("/api/central/feedbacks", params={"abordado": "true"})).json()
    assert r["total"] == 1 and r["items"][0]["abordado"] is True
    r = (await client.get("/api/central/feedbacks", params={"abordado": "false"})).json()
    assert r["total"] == 1 and r["items"][0]["abordado"] is False

    # Combinação: sentimento + fonte coerentes.
    r = (await client.get("/api/central/feedbacks", params={"sentimento": "negativo", "fonte": "whatsapp"})).json()
    assert r["total"] == 1 and r["items"][0]["texto"] == "cancelei"
    # Combinação sem match.
    r = (await client.get("/api/central/feedbacks", params={"sentimento": "positivo", "fonte": "whatsapp"})).json()
    assert r["total"] == 0


@pytest.mark.asyncio
async def test_feedbacks_vazio(client, orgs, session):
    data = (await client.get("/api/central/feedbacks")).json()
    assert data == {"total": 0, "items": []}


# --- /central/overview · metricas (bloco ADITIVO) ----------------------------


def _dth(y, m, d, h):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_metricas_vazio(client, orgs, session):
    """Org sem dados: métricas zeradas/None, sem quebrar (sem 0/0)."""
    m = (await client.get("/api/central/overview")).json()["metricas"]
    assert m["taxa_resolucao"] == {"fechados": 0, "total": 0, "percentual": None}
    assert m["loops_fechados"] == {"melhorias_avisadas": 0, "clientes_avisados": 0}
    assert m["tempo_1a_abordagem"] == {"amostra": 0, "media_dias": None, "mediana_dias": None}
    assert m["nps_por_tema"] == []


@pytest.mark.asyncio
async def test_metricas_taxa_resolucao(client, orgs, session):
    """taxa_resolucao = feedbacks em status terminal / total (org-scoped)."""
    a, b = orgs
    c = Contact(organization_id=a.id, phone="5531900000001", name="C", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    # 4 feedbacks de A: 2 terminais (resolvido, descartado) + 2 abertos.
    session.add_all([
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="t1", text="x", action_status="resolvido", occurred_at=_dt(2026, 6, 1)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="t2", text="y", action_status="descartado", occurred_at=_dt(2026, 6, 2)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="t3", text="z", action_status="a_abordar", occurred_at=_dt(2026, 6, 3)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="t4", text="w", action_status="em_acompanhamento", occurred_at=_dt(2026, 6, 4)),
    ])
    # Ruído de B (todos terminais) NÃO entra.
    rb = Contact(organization_id=b.id, phone="5531911111111", name="R", opt_in=True, profile_data={})
    session.add(rb)
    await session.flush()
    session.add(FeedbackItem(organization_id=b.id, contact_id=rb.id, source="whatsapp", type="churn",
                             external_id="rb1", text="r", action_status="resolvido", occurred_at=_dt(2026, 6, 1)))
    await session.commit()

    tr = (await client.get("/api/central/overview")).json()["metricas"]["taxa_resolucao"]
    assert tr == {"fechados": 2, "total": 4, "percentual": 50.0}


@pytest.mark.asyncio
async def test_metricas_loops_fechados(client, orgs, session):
    """loops_fechados conta melhorias com notified_at e clientes distintos avisados."""
    a, _b = orgs
    c1 = Contact(organization_id=a.id, phone="5531900000001", name="C1", opt_in=True, profile_data={})
    c2 = Contact(organization_id=a.id, phone="5531900000002", name="C2", opt_in=True, profile_data={})
    session.add_all([c1, c2])
    await session.flush()
    # Melhoria AVISADA (notified_at set) com 2 feedbacks de contatos distintos.
    imp_ok = Improvement(organization_id=a.id, title="Avisada", status="entregue",
                         delivered_at=_dt(2026, 6, 9), notified_at=_dt(2026, 6, 10))
    # Melhoria entregue mas NÃO avisada (notified_at None) — não conta.
    imp_sem = Improvement(organization_id=a.id, title="SemAviso", status="entregue", delivered_at=_dt(2026, 6, 9))
    session.add_all([imp_ok, imp_sem])
    await session.flush()
    session.add_all([
        FeedbackItem(organization_id=a.id, contact_id=c1.id, source="whatsapp", type="churn",
                     external_id="l1", text="a", improvement_id=imp_ok.id, occurred_at=_dt(2026, 6, 1)),
        FeedbackItem(organization_id=a.id, contact_id=c2.id, source="whatsapp", type="churn",
                     external_id="l2", text="b", improvement_id=imp_ok.id, occurred_at=_dt(2026, 6, 2)),
        # Mesmo contato c1 de novo na mesma melhoria: NÃO duplica cliente.
        FeedbackItem(organization_id=a.id, contact_id=c1.id, source="whatsapp", type="churn",
                     external_id="l3", text="c", improvement_id=imp_ok.id, occurred_at=_dt(2026, 6, 3)),
        # Feedback ligado à melhoria SEM aviso: não conta cliente.
        FeedbackItem(organization_id=a.id, contact_id=c2.id, source="whatsapp", type="churn",
                     external_id="l4", text="d", improvement_id=imp_sem.id, occurred_at=_dt(2026, 6, 4)),
    ])
    await session.commit()

    lf = (await client.get("/api/central/overview")).json()["metricas"]["loops_fechados"]
    assert lf == {"melhorias_avisadas": 1, "clientes_avisados": 2}  # c1 e c2, sem duplicar c1


@pytest.mark.asyncio
async def test_metricas_tempo_1a_abordagem(client, orgs, session):
    """media/mediana de dias created_at->abordado_em dos feedbacks abordados."""
    a, _b = orgs
    c = Contact(organization_id=a.id, phone="5531900000001", name="C", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    # Abordados: 2 dias, 4 dias, 6 dias -> media 4.0, mediana 4.0.
    session.add_all([
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="d1", text="x", abordado=True,
                     created_at=_dth(2026, 6, 1, 12), abordado_em=_dth(2026, 6, 3, 12), occurred_at=_dt(2026, 6, 1)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="d2", text="y", abordado=True,
                     created_at=_dth(2026, 6, 1, 12), abordado_em=_dth(2026, 6, 5, 12), occurred_at=_dt(2026, 6, 1)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="d3", text="z", abordado=True,
                     created_at=_dth(2026, 6, 1, 12), abordado_em=_dth(2026, 6, 7, 12), occurred_at=_dt(2026, 6, 1)),
        # Abordado SEM abordado_em: ignorado.
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="d4", text="w", abordado=True,
                     created_at=_dth(2026, 6, 1, 12), occurred_at=_dt(2026, 6, 1)),
        # NÃO abordado: ignorado.
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="whatsapp", type="churn",
                     external_id="d5", text="v", abordado=False,
                     created_at=_dth(2026, 6, 1, 12), occurred_at=_dt(2026, 6, 1)),
    ])
    await session.commit()

    t = (await client.get("/api/central/overview")).json()["metricas"]["tempo_1a_abordagem"]
    assert t == {"amostra": 3, "media_dias": 4.0, "mediana_dias": 4.0}


@pytest.mark.asyncio
async def test_metricas_nps_por_tema(client, orgs, session):
    """nps_por_tema: clusters da org com média de nota dos itens + sentimento, por volume."""
    a, b = orgs
    c = Contact(organization_id=a.id, phone="5531900000001", name="C", opt_in=True, profile_data={})
    session.add(c)
    await session.flush()
    big = FeedbackCluster(organization_id=a.id, label="Acesso", dominant_sentiment="negativo", item_count=5)
    small = FeedbackCluster(organization_id=a.id, label="Conteudo", dominant_sentiment="positivo", item_count=2)
    # Cluster de B: NÃO entra.
    rcl = FeedbackCluster(organization_id=b.id, label="Rival", dominant_sentiment="neutro", item_count=9)
    session.add_all([big, small, rcl])
    await session.flush()
    session.add_all([
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="bizzu_app", type="nps",
                     external_id="n1", score=2, cluster_id=big.id, occurred_at=_dt(2026, 6, 1)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="bizzu_app", type="nps",
                     external_id="n2", score=4, cluster_id=big.id, occurred_at=_dt(2026, 6, 2)),
        FeedbackItem(organization_id=a.id, contact_id=c.id, source="bizzu_app", type="nps",
                     external_id="n3", score=9, cluster_id=small.id, occurred_at=_dt(2026, 6, 3)),
    ])
    await session.commit()

    temas = (await client.get("/api/central/overview")).json()["metricas"]["nps_por_tema"]
    assert [t["tema"] for t in temas] == ["Acesso", "Conteudo"]  # por volume desc
    assert set(temas[0].keys()) == {"cluster_id", "tema", "volume", "com_nota", "media", "sentimento"}
    assert temas[0] == {
        "cluster_id": str(big.id), "tema": "Acesso", "volume": 5,
        "com_nota": 2, "media": 3.0, "sentimento": "negativo",  # (2+4)/2
    }
    assert temas[1]["media"] == 9.0 and temas[1]["sentimento"] == "positivo"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
