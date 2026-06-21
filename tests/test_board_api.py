"""Testes do Board de Gestão (Camada 2) — GET /api/feedbacks/board, POST .../move,
e os campos novos (assignee/team_tag) no feed/PATCH.

Mesma infra de test_monitoring_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA/Groq.
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

from app.api.admin import ACTION_STATUSES, get_messaging  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from app.models.improvement import Improvement  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402

# Chaves exatas do item do feed após a Camada 2 (inclui assignee/team_tag) + `selos`
# (status de campanha do contato no inbox — camada win-back).
_ITEM_KEYS = {
    "id", "contato_id", "contato_nome", "contato_whatsapp", "selos", "source", "type",
    "score", "nps_bucket", "sentiment", "themes", "text", "urgencia",
    "action_status", "action_note", "assignee", "team_tag", "improvement_id",
    "abordado", "abordado_em", "follow_up_at", "occurred_em", "created_em",
    # Auditoria do "quem editou" (hardening) — null quando nunca editado.
    "editado_por", "editado_em",
    # Feature 1 (IA mais inteligente): confiança/incerteza derivadas de ai_meta.
    "confianca", "incerto", "sentiment_sugerido",
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


# --- GET /api/feedbacks/board ------------------------------------------------


@pytest.mark.asyncio
async def test_board_agrupa_por_status_e_conta(client, org, session):
    """O board separa os feedbacks por coluna de ação, com todas as colunas sempre
    presentes (zeros inclusos) e `count` = total real da coluna."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()

    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="nps",
                external_id="b1", score=3, nps_bucket="detractor", text="ruim",
                sentiment="negativo", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="churn",
                external_id="b2", text="cancelei", sentiment="negativo",
                action_status="a_abordar", occurred_at=_dt(2026, 6, 2),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=None, source="manual", type="sugestao",
                external_id="b3", text="modo escuro", action_status="em_acompanhamento",
                occurred_at=_dt(2026, 6, 3),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="elogio",
                external_id="b4", text="amei", sentiment="positivo",
                action_status="resolvido", abordado=True, occurred_at=_dt(2026, 6, 4),
            ),
        ]
    )
    await session.commit()

    data = (await client.get("/api/feedbacks/board")).json()
    assert set(data.keys()) == {"columns"}
    cols = data["columns"]
    # Todas as colunas sempre presentes, na ordem do funil de acompanhamento.
    assert list(cols.keys()) == list(ACTION_STATUSES)

    assert cols["a_abordar"]["count"] == 2
    assert cols["em_acompanhamento"]["count"] == 1
    assert cols["aguardando_retorno"]["count"] == 0
    assert cols["resolvido"]["count"] == 1
    assert cols["descartado"]["count"] == 0

    # itens são objetos no formato do feed.
    assert cols["em_acompanhamento"]["items"][0]["text"] == "modo escuro"
    assert set(cols["a_abordar"]["items"][0].keys()) == _ITEM_KEYS

    # coluna vazia traz items=[]
    assert cols["aguardando_retorno"]["items"] == []


@pytest.mark.asyncio
async def test_board_ordena_itens_por_urgencia_na_coluna(client, org, session):
    """Dentro de uma coluna, os cards vêm por urgência desc (o crítico no topo)."""
    risco = Contact(
        organization_id=org.id, phone="5531900000001", name="Risco", opt_in=True,
        profile_data={"partner": {"profile": "ativo_em_risco", "subscription": {"planType": "anual"}}},
    )
    feliz = Contact(organization_id=org.id, phone="5531900000002", name="Feliz", opt_in=True, profile_data={})
    session.add_all([risco, feliz])
    await session.flush()

    session.add_all(
        [
            # promotor satisfeito, abordado, antigo → urgência baixa (mesma coluna 'novo')
            FeedbackItem(
                organization_id=org.id, contact_id=feliz.id, source="manual", type="nps",
                external_id="o1", score=10, nps_bucket="promoter", text="tranquilo",
                sentiment="positivo", abordado=True, action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
            ),
            # detrator + churn + negativo + em risco + anual + não abordado → urgência alta
            FeedbackItem(
                organization_id=org.id, contact_id=risco.id, source="manual", type="churn",
                external_id="o2", score=2, nps_bucket="detractor", text="cancelei tudo",
                sentiment="negativo", abordado=False, action_status="a_abordar", occurred_at=_dt(2026, 6, 2),
            ),
        ]
    )
    await session.commit()

    cols = (await client.get("/api/feedbacks/board")).json()["columns"]
    novo = cols["a_abordar"]["items"]
    assert [i["text"] for i in novo] == ["cancelei tudo", "tranquilo"]
    urg = [i["urgencia"] for i in novo]
    assert urg == sorted(urg, reverse=True)


@pytest.mark.asyncio
async def test_board_limita_12_itens_por_coluna_mas_count_e_total(client, org, session):
    """`count` reflete o total da coluna; `items` traz no máximo 12 (os mais urgentes)."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    # 15 itens 'novo' na mesma coluna.
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="sugestao",
                external_id=f"m{i}", text=f"ideia {i}", action_status="a_abordar",
                occurred_at=_dt(2026, 6, 1),
            )
            for i in range(15)
        ]
    )
    await session.commit()

    cols = (await client.get("/api/feedbacks/board")).json()["columns"]
    assert cols["a_abordar"]["count"] == 15
    assert len(cols["a_abordar"]["items"]) == 12


@pytest.mark.asyncio
async def test_board_filtra_por_team_tag(client, org, session):
    """O filtro team_tag restringe o board ao time escolhido (count e items)."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="bug",
                external_id="t1", text="bug do produto", action_status="a_abordar",
                team_tag="produto", occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="sugestao",
                external_id="t2", text="dúvida de cobrança", action_status="a_abordar",
                team_tag="suporte", occurred_at=_dt(2026, 6, 2),
            ),
        ]
    )
    await session.commit()

    cols = (await client.get("/api/feedbacks/board", params={"team_tag": "produto"})).json()["columns"]
    assert cols["a_abordar"]["count"] == 1
    assert cols["a_abordar"]["items"][0]["text"] == "bug do produto"
    assert cols["a_abordar"]["items"][0]["team_tag"] == "produto"


@pytest.mark.asyncio
async def test_board_filtra_por_assignee(client, org, session):
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="bug",
                external_id="a1", text="meu", action_status="em_acompanhamento",
                assignee="felipe", occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=org.id, contact_id=ana.id, source="manual", type="bug",
                external_id="a2", text="da outra", action_status="em_acompanhamento",
                assignee="marina", occurred_at=_dt(2026, 6, 2),
            ),
        ]
    )
    await session.commit()

    cols = (await client.get("/api/feedbacks/board", params={"assignee": "felipe"})).json()["columns"]
    assert cols["em_acompanhamento"]["count"] == 1
    assert cols["em_acompanhamento"]["items"][0]["assignee"] == "felipe"


@pytest.mark.asyncio
async def test_board_isola_por_org(client, org, session):
    """Feedbacks de OUTRA org não aparecem no board (isolamento por organization_id)."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    session.add_all(
        [
            FeedbackItem(
                organization_id=org.id, contact_id=None, source="manual", type="nps",
                external_id="meu", score=5, text="meu", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
            ),
            FeedbackItem(
                organization_id=other.id, contact_id=None, source="manual", type="nps",
                external_id="alheio", score=5, text="alheio", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
            ),
        ]
    )
    await session.commit()

    cols = (await client.get("/api/feedbacks/board")).json()["columns"]
    assert cols["a_abordar"]["count"] == 1
    assert cols["a_abordar"]["items"][0]["text"] == "meu"


# --- POST /api/feedbacks/{id}/move -------------------------------------------


@pytest.mark.asyncio
async def test_move_muda_status(client, org, session):
    """Mover um card troca o action_status e devolve o item no formato do feed."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="manual", type="nps",
        external_id="mv1", score=3, nps_bucket="detractor", text="ruim", action_status="a_abordar",
        occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.post(f"/api/feedbacks/{fb.id}/move", json={"status": "em_acompanhamento"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action_status"] == "em_acompanhamento"
    assert set(out.keys()) == _ITEM_KEYS
    assert out["contato_nome"] == "Ana"

    # reflete no board
    cols = (await client.get("/api/feedbacks/board")).json()["columns"]
    assert cols["em_acompanhamento"]["count"] == 1
    assert cols["a_abordar"]["count"] == 0


@pytest.mark.asyncio
async def test_move_status_invalido_422(client, org, session):
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="nps",
        external_id="mv2", score=3, text="x", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.post(f"/api/feedbacks/{fb.id}/move", json={"status": "fazendo"})
    assert r.status_code == 422
    # nada mudou
    cols = (await client.get("/api/feedbacks/board")).json()["columns"]
    assert cols["a_abordar"]["count"] == 1


@pytest.mark.asyncio
async def test_move_para_planejado_vincula_melhoria(client, org, session):
    """Mover para 'planejado' com improvement_id válido vincula o feedback à melhoria."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    imp = Improvement(organization_id=org.id, title="Modo escuro", status="ideia")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="manual", type="sugestao",
        external_id="mv3", text="queria modo escuro", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add_all([imp, fb])
    await session.commit()

    r = await client.post(
        f"/api/feedbacks/{fb.id}/move",
        json={"status": "em_acompanhamento", "improvement_id": str(imp.id), "assignee": "felipe"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action_status"] == "em_acompanhamento"
    assert out["assignee"] == "felipe"

    # o vínculo aparece na contagem da melhoria
    imps = (await client.get("/api/improvements")).json()
    linked = next(i for i in imps if i["id"] == str(imp.id))
    assert linked["feedback_count"] == 1


@pytest.mark.asyncio
async def test_move_planejado_improvement_de_outra_org_404(client, org, session):
    """Melhoria de OUTRA org não pode ser vinculada: 404 e nada é alterado."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    imp_alheia = Improvement(organization_id=other.id, title="Alheia", status="ideia")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="sugestao",
        external_id="mv4", text="x", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add_all([imp_alheia, fb])
    await session.commit()

    r = await client.post(
        f"/api/feedbacks/{fb.id}/move",
        json={"status": "em_acompanhamento", "improvement_id": str(imp_alheia.id)},
    )
    assert r.status_code == 404
    # status NÃO mudou (rollback do request) — segue 'novo' no board
    cols = (await client.get("/api/feedbacks/board")).json()["columns"]
    assert cols["a_abordar"]["count"] == 1
    assert cols["em_acompanhamento"]["count"] == 0


@pytest.mark.asyncio
async def test_move_feedback_inexistente_404(client, org):
    r = await client.post(f"/api/feedbacks/{uuid.uuid4()}/move", json={"status": "resolvido"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_move_id_invalido_422(client, org):
    r = await client.post("/api/feedbacks/nao-e-uuid/move", json={"status": "resolvido"})
    assert r.status_code == 422


# --- assignee/team_tag no feed e no PATCH ------------------------------------


@pytest.mark.asyncio
async def test_patch_aplica_assignee_e_team_tag(client, org, session):
    """PATCH parcial atribui assignee/team_tag; o feed os expõe e filtra por eles."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=ana.id, source="manual", type="bug",
        external_id="pt1", text="bug", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(
        f"/api/feedbacks/{fb.id}", json={"assignee": "felipe", "team_tag": "produto"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["assignee"] == "felipe"
    assert out["team_tag"] == "produto"
    assert set(out.keys()) == _ITEM_KEYS

    # filtros do feed por assignee/team_tag
    r1 = (await client.get("/api/feedbacks", params={"assignee": "felipe"})).json()
    assert r1["total"] == 1 and r1["items"][0]["id"] == str(fb.id)
    r2 = (await client.get("/api/feedbacks", params={"team_tag": "produto"})).json()
    assert r2["total"] == 1
    r3 = (await client.get("/api/feedbacks", params={"team_tag": "suporte"})).json()
    assert r3["total"] == 0


@pytest.mark.asyncio
async def test_post_feedback_aceita_assignee_e_team_tag(client, org, session):
    """POST manual aceita assignee/team_tag e os devolve no item criado."""
    ana = Contact(organization_id=org.id, phone="5531900000001", name="Ana", opt_in=True, profile_data={})
    session.add(ana)
    await session.commit()

    r = await client.post(
        "/api/feedbacks",
        json={
            "contato_id": str(ana.id), "type": "bug", "text": "travou",
            "assignee": "marina", "team_tag": "suporte",
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["assignee"] == "marina"
    assert out["team_tag"] == "suporte"


# --- improvement_id no PATCH (vincular/desvincular melhoria) ------------------


@pytest.mark.asyncio
async def test_patch_vincula_improvement_id_sem_mexer_no_status(client, org, session):
    """PATCH com improvement_id válido vincula a melhoria e devolve no card, SEM
    alterar o action_status (o vínculo é independente da esteira)."""
    imp = Improvement(organization_id=org.id, title="Modo escuro", status="ideia")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="sugestao",
        external_id="lk1", text="queria modo escuro", action_status="a_abordar",
        occurred_at=_dt(2026, 6, 1),
    )
    session.add_all([imp, fb])
    await session.commit()

    r = await client.patch(
        f"/api/feedbacks/{fb.id}", json={"improvement_id": str(imp.id)}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["improvement_id"] == str(imp.id)
    # vincular NÃO mexe no action_status
    assert out["action_status"] == "a_abordar"
    assert set(out.keys()) == _ITEM_KEYS

    # o vínculo é persistido (some no GET) e conta na melhoria
    fresh = (await client.get("/api/feedbacks")).json()["items"][0]
    assert fresh["improvement_id"] == str(imp.id)
    imps = (await client.get("/api/improvements")).json()
    linked = next(i for i in imps if i["id"] == str(imp.id))
    assert linked["feedback_count"] == 1


@pytest.mark.asyncio
async def test_patch_improvement_id_null_desvincula(client, org, session):
    """PATCH com improvement_id=null desvincula a melhoria (não toca no resto)."""
    imp = Improvement(organization_id=org.id, title="X", status="ideia")
    session.add(imp)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="sugestao",
        external_id="lk2", text="x", action_status="em_acompanhamento",
        improvement_id=imp.id, occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"improvement_id": None})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["improvement_id"] is None
    # action_status preservado
    assert out["action_status"] == "em_acompanhamento"

    imps = (await client.get("/api/improvements")).json()
    linked = next(i for i in imps if i["id"] == str(imp.id))
    assert linked["feedback_count"] == 0


@pytest.mark.asyncio
async def test_patch_improvement_id_inexistente_404(client, org, session):
    """improvement_id que não existe na org -> 404 e nada é alterado."""
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="sugestao",
        external_id="lk3", text="x", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(
        f"/api/feedbacks/{fb.id}", json={"improvement_id": str(uuid.uuid4())}
    )
    assert r.status_code == 404
    # nada vinculou
    fresh = (await client.get("/api/feedbacks")).json()["items"][0]
    assert fresh["improvement_id"] is None


@pytest.mark.asyncio
async def test_patch_improvement_de_outra_org_404(client, org, session):
    """Melhoria de OUTRA org não pode ser vinculada via PATCH: 404, nada muda."""
    other = Organization(slug="outra", name="Outra", settings={})
    session.add(other)
    await session.flush()
    imp_alheia = Improvement(organization_id=other.id, title="Alheia", status="ideia")
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="sugestao",
        external_id="lk4", text="x", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add_all([imp_alheia, fb])
    await session.commit()

    r = await client.patch(
        f"/api/feedbacks/{fb.id}", json={"improvement_id": str(imp_alheia.id)}
    )
    assert r.status_code == 404
    fresh = (await client.get("/api/feedbacks")).json()["items"][0]
    assert fresh["improvement_id"] is None


@pytest.mark.asyncio
async def test_patch_improvement_id_invalido_422(client, org, session):
    """improvement_id que não é UUID -> 422 (validação do _get_improvement)."""
    fb = FeedbackItem(
        organization_id=org.id, contact_id=None, source="manual", type="sugestao",
        external_id="lk5", text="x", action_status="a_abordar", occurred_at=_dt(2026, 6, 1),
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(
        f"/api/feedbacks/{fb.id}", json={"improvement_id": "nao-e-uuid"}
    )
    assert r.status_code == 422
