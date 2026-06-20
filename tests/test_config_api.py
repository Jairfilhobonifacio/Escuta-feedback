"""Testes de GET/PUT /api/config — vocabulários configuráveis (status/tipos/origens).

Mesma infra de test_monitoring_api.py: app real + SQLite in-memory (override de
get_session) + messaging fake. Nenhum teste toca Supabase/WAHA/Groq.

Cobre: as 3 listas efetivas no GET (defaults presentes); PUT salva SÓ os customizados
em Organization.settings (defaults intocados); custom vira válido nas validações
(move/PATCH); colisão de key custom com default = 422; idempotência + remoção de custom;
zero regressão (sem custom o comportamento é idêntico ao anterior).
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

from app.api.admin import (  # noqa: E402
    ACTION_STATUSES,
    DEFAULT_ORIGINS,
    FEEDBACK_TYPES,
    get_messaging,
)
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


@pytest.mark.asyncio
async def test_get_config_retorna_defaults_efetivos(client, org):
    """GET /api/config: as 3 listas efetivas com defaults (key/label/cor) e nada custom."""
    data = (await client.get("/api/config")).json()
    assert set(data.keys()) == {"action_statuses", "feedback_types", "feedback_origins"}

    # Status: defaults na MESMA ordem de ACTION_STATUSES, item = {key,label,cor}.
    st = data["action_statuses"]
    assert [s["key"] for s in st] == list(ACTION_STATUSES)
    assert all(set(s.keys()) == {"key", "label", "cor"} for s in st)
    assert st[0] == {"key": "novo", "label": "Novo", "cor": "#6366f1"}

    # Tipos e origens: {key,label}, contêm todos os defaults.
    tp = data["feedback_types"]
    assert all(set(t.keys()) == {"key", "label"} for t in tp)
    assert {t["key"] for t in tp} == set(FEEDBACK_TYPES)

    org_ = data["feedback_origins"]
    assert all(set(o.keys()) == {"key", "label"} for o in org_)
    assert {o["key"] for o in org_} == set(DEFAULT_ORIGINS)


@pytest.mark.asyncio
async def test_put_config_adiciona_custom_e_persiste_so_custom(client, org, session):
    """PUT salva SÓ os customizados em settings; defaults seguem na frente e intactos."""
    body = {
        "action_statuses": [{"key": "aguardando_cliente", "label": "Aguardando cliente", "cor": "#ff0000"}],
        "feedback_types": [{"key": "incidente"}],  # label default derivado da key
        "feedback_origins": [{"key": "instagram", "label": "Instagram"}],
    }
    resp = await client.put("/api/config", json=body)
    assert resp.status_code == 200
    data = resp.json()

    # Efetivo = defaults (na frente) + custom (no fim). Defaults nunca somem.
    st_keys = [s["key"] for s in data["action_statuses"]]
    assert st_keys[: len(ACTION_STATUSES)] == list(ACTION_STATUSES)
    assert st_keys[-1] == "aguardando_cliente"
    assert data["action_statuses"][-1]["cor"] == "#ff0000"

    tp_keys = [t["key"] for t in data["feedback_types"]]
    assert set(FEEDBACK_TYPES).issubset(set(tp_keys)) and tp_keys[-1] == "incidente"
    # label default derivado da key quando não enviado.
    assert data["feedback_types"][-1]["label"] == "Incidente"

    assert [o["key"] for o in data["feedback_origins"]][-1] == "instagram"

    # Settings guarda SÓ os customizados (não os defaults) — preserva dados existentes.
    await session.refresh(org)
    assert org.settings["action_statuses"] == [
        {"key": "aguardando_cliente", "label": "Aguardando cliente", "cor": "#ff0000"}
    ]
    assert org.settings["feedback_types"] == [{"key": "incidente", "label": "Incidente"}]
    assert org.settings["feedback_origins"] == [{"key": "instagram", "label": "Instagram"}]

    # GET reflete o que foi salvo (round-trip).
    again = (await client.get("/api/config")).json()
    assert again == data


@pytest.mark.asyncio
async def test_put_config_rejeita_colisao_com_default(client, org, session):
    """Key custom que colide com um default => 422; nada é salvo."""
    resp = await client.put("/api/config", json={"action_statuses": [{"key": "novo", "label": "X"}]})
    assert resp.status_code == 422
    assert "novo" in resp.json()["detail"]

    # Settings intocado (nenhum custom salvo).
    await session.refresh(org)
    assert "action_statuses" not in (org.settings or {})


@pytest.mark.asyncio
async def test_custom_status_aceito_em_move_e_patch(client, org, session):
    """Status custom passa a ser ACEITO pelas validações de move/PATCH (e o default segue ok)."""
    # Cadastra o status custom.
    await client.put("/api/config", json={"action_statuses": [{"key": "aguardando_cliente"}]})

    contato = Contact(organization_id=org.id, phone="5531900000001", name="Cli", opt_in=True, profile_data={})
    session.add(contato)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=contato.id, source="manual", type="nps",
        external_id="x:1", score=5, occurred_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
    )
    session.add(fb)
    await session.commit()

    # move para o status CUSTOM -> 200 (antes seria 422).
    mv = await client.post(f"/api/feedbacks/{fb.id}/move", json={"status": "aguardando_cliente"})
    assert mv.status_code == 200, mv.text
    assert mv.json()["action_status"] == "aguardando_cliente"

    # status fora do vocabulário efetivo (não default, não custom) -> 422.
    bad = await client.post(f"/api/feedbacks/{fb.id}/move", json={"status": "inexistente"})
    assert bad.status_code == 422

    # PATCH para um status DEFAULT continua valendo (zero regressão).
    pt = await client.patch(f"/api/feedbacks/{fb.id}", json={"action_status": "resolvido"})
    assert pt.status_code == 200 and pt.json()["action_status"] == "resolvido"

    # O board de triagem agora tem uma coluna para o status custom.
    board = (await client.get("/api/feedbacks/board")).json()
    assert "aguardando_cliente" in board["columns"]
    # E os defaults seguem todos presentes.
    assert set(ACTION_STATUSES).issubset(set(board["columns"].keys()))


@pytest.mark.asyncio
async def test_put_config_idempotente_e_remove_custom(client, org, session):
    """Reenviar a mesma lista é estável; mandar [] remove os customizados (defaults ficam)."""
    body = {"action_statuses": [{"key": "triagem_extra", "label": "Triagem extra", "cor": "#123456"}]}
    first = (await client.put("/api/config", json=body)).json()
    second = (await client.put("/api/config", json=body)).json()
    assert first == second  # idempotente

    # Remove o custom (lista vazia) sem mexer nos outros vocabulários (ausentes no corpo).
    cleared = (await client.put("/api/config", json={"action_statuses": []})).json()
    assert [s["key"] for s in cleared["action_statuses"]] == list(ACTION_STATUSES)
    await session.refresh(org)
    assert org.settings["action_statuses"] == []
    # Tipos/origens não enviados continuam só com os defaults.
    assert {t["key"] for t in cleared["feedback_types"]} == set(FEEDBACK_TYPES)
