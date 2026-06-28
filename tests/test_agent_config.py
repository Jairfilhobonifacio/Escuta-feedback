"""Testes da Central de Controle do Agente — Fase 1 (feature flags por org em runtime).

Cobre `app/domain/features.py` (semântica safe vs. dangerous) e os endpoints
GET/PUT /api/agent-config. Flags frozen → mutadas in place via object.__setattr__
(mesmo padrão de test_ai_smarter/test_events_bizzu). Nenhum teste toca rede.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.config import settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.domain.features import (  # noqa: E402
    FEATURES,
    agent_config_view,
    feature_enabled,
    feature_locked,
    set_feature,
)
from app.main import app  # noqa: E402
from app.models.core import Organization  # noqa: E402

ALL_KEYS = [f["key"] for f in FEATURES]
CONTRATO_KEYS = {"key", "label", "grupo", "descricao", "enabled", "locked"}


def _set_flag(name: str, value: bool) -> None:
    object.__setattr__(settings, name, value)


def _org(features: dict | None = None) -> SimpleNamespace:
    """Org fake (só precisa de `.settings`) para os testes de unidade de feature_enabled."""
    return SimpleNamespace(settings=({"features": features} if features is not None else {}))


@pytest.fixture
def reset_flags():
    """Salva/restaura TODAS as flags do catálogo (estado frozen compartilhado)."""
    saved = {k: getattr(settings, k) for k in ALL_KEYS}
    try:
        yield
    finally:
        for k, v in saved.items():
            _set_flag(k, v)


# === Unidade: feature_enabled / set_feature =====================================


def test_feature_enabled_safe_override_vence(reset_flags):
    """SEGURA: o painel manda — override vence o env nos dois sentidos."""
    _set_flag("response_suggestion_enabled", False)
    # env OFF + override ON => ON (o dono consegue LIGAR com o deploy off)
    assert feature_enabled(_org({"response_suggestion_enabled": True}), "response_suggestion_enabled") is True
    # env OFF + sem override => OFF (cai no default do env)
    assert feature_enabled(_org(), "response_suggestion_enabled") is False
    _set_flag("response_suggestion_enabled", True)
    # env ON + override OFF => OFF (o painel também desliga)
    assert feature_enabled(_org({"response_suggestion_enabled": False}), "response_suggestion_enabled") is False
    # env ON + sem override => ON
    assert feature_enabled(_org(), "response_suggestion_enabled") is True


def test_feature_enabled_dangerous_env_piso(reset_flags):
    """PERIGOSA: o env é PISO/kill-switch — o painel NUNCA liga o que o deploy desligou."""
    _set_flag("voc_agent_enabled", False)
    # env OFF: nem com override ON liga; e a feature aparece travada.
    assert feature_enabled(_org({"voc_agent_enabled": True}), "voc_agent_enabled") is False
    assert feature_locked("voc_agent_enabled") is True
    _set_flag("voc_agent_enabled", True)
    # env ON: segue o default e o override pode desligar (mas não pode "super-ligar").
    assert feature_enabled(_org(), "voc_agent_enabled") is True
    assert feature_enabled(_org({"voc_agent_enabled": False}), "voc_agent_enabled") is False
    assert feature_locked("voc_agent_enabled") is False


def test_set_feature_key_invalida_levanta(reset_flags):
    with pytest.raises(KeyError):
        set_feature(_org(), "feature_que_nao_existe", True)


def test_set_feature_locked_nao_altera(reset_flags):
    """PERIGOSA + env OFF (locked): set_feature é no-op — nada é gravado."""
    _set_flag("voc_agent_enabled", False)
    org = _org()
    set_feature(org, "voc_agent_enabled", True)
    assert (org.settings or {}).get("features", {}).get("voc_agent_enabled") is None


def test_set_feature_safe_persiste(reset_flags):
    _set_flag("clustering_inline_enabled", False)
    org = _org()
    set_feature(org, "clustering_inline_enabled", True)
    assert org.settings["features"]["clustering_inline_enabled"] is True
    # idempotente / reversível
    set_feature(org, "clustering_inline_enabled", False)
    assert org.settings["features"]["clustering_inline_enabled"] is False


def test_agent_config_view_contrato(reset_flags):
    _set_flag("voc_agent_enabled", False)
    _set_flag("voc_whatsapp_tool_enabled", False)
    view = agent_config_view(_org())
    assert [f["key"] for f in view] == ALL_KEYS
    for f in view:
        assert set(f) == CONTRATO_KEYS
    locked = {f["key"]: f["locked"] for f in view}
    assert locked["voc_agent_enabled"] is True
    assert locked["voc_whatsapp_tool_enabled"] is True
    assert locked["response_suggestion_enabled"] is False


# === Endpoints GET/PUT /api/agent-config ========================================


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
        app.dependency_overrides.pop(get_session, None)


async def _seed_org(session) -> Organization:
    o = Organization(slug=settings.default_org_slug, name="Bizzu", settings={})
    session.add(o)
    await session.commit()
    return o


async def _reload_org(session) -> Organization:
    return (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_get_lista_features(client, session, reset_flags):
    _set_flag("voc_agent_enabled", False)
    _set_flag("voc_whatsapp_tool_enabled", False)
    await _seed_org(session)
    r = await client.get("/api/agent-config")
    assert r.status_code == 200, r.text
    feats = r.json()["features"]
    assert {f["key"] for f in feats} == set(ALL_KEYS)
    for f in feats:
        assert set(f) == CONTRATO_KEYS
    # perigosas com o deploy off => locked
    travadas = {f["key"]: f["locked"] for f in feats}
    assert travadas["voc_agent_enabled"] is True
    assert travadas["voc_whatsapp_tool_enabled"] is True


@pytest.mark.asyncio
async def test_put_liga_e_persiste(client, session, reset_flags):
    """PUT numa segura com o env OFF LIGA mesmo assim (painel manda) e persiste no JSONB."""
    _set_flag("response_suggestion_enabled", False)
    await _seed_org(session)
    r = await client.put(
        "/api/agent-config", json={"key": "response_suggestion_enabled", "enabled": True}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"key": "response_suggestion_enabled", "enabled": True, "locked": False}
    # persistiu em settings["features"]
    org = await _reload_org(session)
    assert org.settings["features"]["response_suggestion_enabled"] is True
    # GET reflete
    g = await client.get("/api/agent-config")
    item = next(f for f in g.json()["features"] if f["key"] == "response_suggestion_enabled")
    assert item["enabled"] is True


@pytest.mark.asyncio
async def test_put_desliga_segura_com_env_on(client, session, reset_flags):
    """PUT pode DESLIGAR uma segura mesmo com o env ON (override vence)."""
    _set_flag("esteira_enabled", True)
    await _seed_org(session)
    r = await client.put("/api/agent-config", json={"key": "esteira_enabled", "enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    org = await _reload_org(session)
    assert org.settings["features"]["esteira_enabled"] is False


@pytest.mark.asyncio
async def test_put_perigosa_locked_nao_altera(client, session, reset_flags):
    """PERIGOSA + env OFF: PUT é no-op (locked=True, enabled=False, nada gravado)."""
    _set_flag("voc_agent_enabled", False)
    await _seed_org(session)
    r = await client.put("/api/agent-config", json={"key": "voc_agent_enabled", "enabled": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"key": "voc_agent_enabled", "enabled": False, "locked": True}
    org = await _reload_org(session)
    assert (org.settings or {}).get("features", {}).get("voc_agent_enabled") is None


@pytest.mark.asyncio
async def test_put_key_invalida_422(client, session, reset_flags):
    await _seed_org(session)
    r = await client.put("/api/agent-config", json={"key": "feature_inexistente", "enabled": True})
    assert r.status_code == 422
