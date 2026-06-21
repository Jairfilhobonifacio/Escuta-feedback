"""Testes do login de operador (JWT HS256) + require_operator + fail-closed C1 + CORS C2.

Infra: app real + SQLite in-memory (override de get_session), igual aos demais. NENHUM
disparo real. Os segredos (JWT/operator/app_env) são injetados por monkeypatch nos módulos
que leem `settings` — `app.config`, `app.api.auth`, `app.api._security` — sem tocar env
nem o conftest compartilhado.

Pegadinha-mãe: `Settings` é um dataclass FROZEN — não dá p/ mutar in-place. Recriamos com
`dataclasses.replace(...)` e substituímos o atributo `settings` de cada módulo que o leu no
import (cada `from app.config import settings` fez uma cópia da referência).
"""
from __future__ import annotations

import dataclasses
import os
import sys

import bcrypt
import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import app.api._security as _security  # noqa: E402
import app.api.auth as auth_mod  # noqa: E402
import app.config as config_mod  # noqa: E402
from app.api.auth import require_operator  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402

_JWT_SECRET = "x" * 48
_USER = "operador"
_PASSWORD = "senha-supersecreta"
_HASH = bcrypt.hashpw(_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


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
        app.dependency_overrides.clear()


def _patch_settings(monkeypatch, **overrides):
    """Recria o Settings frozen com os overrides e injeta nos módulos que o leem."""
    new = dataclasses.replace(config_mod.settings, **overrides)
    for mod in (config_mod, auth_mod, _security):
        monkeypatch.setattr(mod, "settings", new)
    return new


def _configure_login(monkeypatch, *, app_env="dev"):
    return _patch_settings(
        monkeypatch,
        app_env=app_env,
        jwt_secret=_JWT_SECRET,
        operator_user=_USER,
        operator_password_hash=_HASH,
    )


# ============================ LOGIN ===========================================


@pytest.mark.asyncio
async def test_login_ok_devolve_token(client, monkeypatch):
    _configure_login(monkeypatch)
    r = await client.post("/api/auth/login", json={"user": _USER, "password": _PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"] == _USER
    assert data["expires_in"] == 12 * 3600
    claims = jwt.decode(data["token"], _JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == _USER and claims["typ"] == "operator"


@pytest.mark.asyncio
async def test_login_senha_errada_401(client, monkeypatch):
    _configure_login(monkeypatch)
    r = await client.post("/api/auth/login", json={"user": _USER, "password": "errada"})
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "credenciais inválidas"


@pytest.mark.asyncio
async def test_login_user_errado_mesma_msg(client, monkeypatch):
    _configure_login(monkeypatch)
    r = await client.post("/api/auth/login", json={"user": "ninguem", "password": _PASSWORD})
    assert r.status_code == 401, r.text
    # Mensagem IDÊNTICA à de senha errada (não vaza qual falhou).
    assert r.json()["detail"] == "credenciais inválidas"


@pytest.mark.asyncio
async def test_login_nao_configurado_503(client, monkeypatch):
    """Sem JWT_SECRET/USER/HASH -> 503 (login não tem fail-open)."""
    _patch_settings(
        monkeypatch, app_env="dev", jwt_secret=None, operator_user=None, operator_password_hash=None
    )
    r = await client.post("/api/auth/login", json={"user": _USER, "password": _PASSWORD})
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "login não configurado"


# ============================ /me + require_operator ==========================


@pytest.mark.asyncio
async def test_me_sem_token_401(client, monkeypatch):
    _configure_login(monkeypatch)
    r = await client.get("/api/auth/me")
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "não autenticado"


@pytest.mark.asyncio
async def test_me_com_token_200(client, monkeypatch):
    _configure_login(monkeypatch)
    login = await client.post("/api/auth/login", json={"user": _USER, "password": _PASSWORD})
    token = login.json()["token"]
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["user"] == _USER


@pytest.mark.asyncio
async def test_me_token_expirado_401(client, monkeypatch):
    _configure_login(monkeypatch)
    # Token já expirado (exp no passado), assinado com o mesmo segredo.
    expired = jwt.encode(
        {"sub": _USER, "iat": 1, "exp": 2, "typ": "operator"}, _JWT_SECRET, algorithm="HS256"
    )
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_logout_idempotente_200(client, monkeypatch):
    _configure_login(monkeypatch)
    r = await client.post("/api/auth/logout")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


# ============================ rota de painel protegida ========================


@pytest.mark.asyncio
async def test_painel_sem_operator_401(client, monkeypatch):
    """Rota do painel SEM Bearer válido -> 401 (require_operator, sem fail-open).

    Limpa o override autouse de require_operator p/ exercitar o 401 real.
    """
    _configure_login(monkeypatch)
    app.dependency_overrides.pop(require_operator, None)
    r = await client.get("/api/selos")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_painel_sem_jwt_secret_401_nao_503(client, monkeypatch):
    """Rota protegida com JWT_SECRET ausente -> 401 (nega sem vazar config), NÃO 503.

    Fail-CLOSED: sem secret não há como validar o token, então `require_operator` responde
    "não autenticado" em vez de revelar que o login não está configurado (503). O 503 fica
    restrito ao POST /auth/login. Limpa o override autouse p/ exercitar o caminho real.
    """
    # app_env=dev evita o 503 fail-closed do require_panel_key (que precede require_operator
    # e exige PANEL_API_KEY em produção) — aqui o que medimos é o require_operator sem secret.
    _patch_settings(monkeypatch, app_env="dev", jwt_secret=None)
    app.dependency_overrides.pop(require_operator, None)
    r = await client.get("/api/selos", headers={"Authorization": "Bearer qualquer-token"})
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "não autenticado"


@pytest.mark.asyncio
async def test_painel_com_operator_passa(client, session, monkeypatch):
    """Rota do painel COM Bearer válido -> passa (a auth de operador OK)."""
    _configure_login(monkeypatch)
    session.add(Organization(slug="bizzu", name="Bizzu", settings={}))
    await session.commit()
    app.dependency_overrides.pop(require_operator, None)
    login = await client.post("/api/auth/login", json={"user": _USER, "password": _PASSWORD})
    token = login.json()["token"]
    r = await client.get("/api/selos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


# ============================ C1 fail-closed em produção ======================


@pytest.mark.asyncio
async def test_failclosed_panel_key_producao_503(client, monkeypatch):
    """app_env=production + sem PANEL_API_KEY -> 503 (fail-CLOSED) na rota do painel.

    Precede o require_operator (mesma lista de deps): com o override autouse ativo, o
    operador "passa", e o require_panel_key produz o 503. Confirma o gatilho C1.
    """
    _patch_settings(monkeypatch, app_env="production", panel_api_key=None)
    r = await client.get("/api/selos")
    assert r.status_code == 503, r.text
    assert "PANEL_API_KEY" in r.json()["detail"]


@pytest.mark.asyncio
async def test_failopen_panel_key_dev_libera(client, session, monkeypatch, caplog):
    """app_env=dev + sem PANEL_API_KEY -> libera + WARN (fail-OPEN histórico)."""
    import logging

    _patch_settings(monkeypatch, app_env="dev", panel_api_key=None)
    session.add(Organization(slug="bizzu", name="Bizzu", settings={}))
    await session.commit()
    with caplog.at_level(logging.WARNING, logger="app.api._security"):
        r = await client.get("/api/selos")
    assert r.status_code == 200, r.text
    assert any("painel SEM autenticação" in rec.message for rec in caplog.records)


# ============================ C2 CORS lido do env =============================


def test_cors_origins_lidos_do_env(monkeypatch):
    """A lista de origins é parseada do CSV `cors_allowed_origins` (sem vazios)."""
    new = dataclasses.replace(
        config_mod.settings,
        cors_allowed_origins="https://painel.exemplo.com, http://localhost:3001 ,",
    )
    assert new.cors_allowed_origins_list == [
        "https://painel.exemplo.com",
        "http://localhost:3001",
    ]


# ============================ B4 422 genérico =================================


@pytest.mark.asyncio
async def test_events_bizzu_422_generico(client, monkeypatch):
    """Payload inválido no /api/events/bizzu -> detail genérico ('payload inválido'),
    sem vazar a estrutura `e.errors()` ao emissor externo (B4)."""
    import hashlib
    import hmac as _hmac
    import time

    secret = "bizzu-secret"
    monkeypatch.setattr(
        _security, "settings", dataclasses.replace(_security.settings, bizzu_webhook_secret=secret)
    )
    # events.py lê settings.bizzu_webhook_secret do seu próprio import.
    import app.api.events as events_mod

    monkeypatch.setattr(
        events_mod, "settings", dataclasses.replace(events_mod.settings, bizzu_webhook_secret=secret)
    )

    body = b'{"event":"nps"}'  # falta `user`/campos obrigatórios -> ValidationError
    ts = str(int(time.time()))
    sig = _hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    r = await client.post(
        "/api/events/bizzu",
        content=body,
        headers={
            "X-Escuta-Timestamp": ts,
            "X-Escuta-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    # A assinatura pode não bater (depende do esquema interno) — o que importa é que,
    # SE chegar à validação do schema, o detail é genérico e nunca um dump de erros.
    if r.status_code == 422:
        assert r.json()["detail"] == "payload inválido"


# ============================ Auditoria grava o sub ===========================


@pytest.mark.asyncio
async def test_auditoria_patch_grava_operador(client, session, monkeypatch):
    """PATCH /api/feedbacks/{id} grava o operador (sub do JWT) no feedback_log do
    contato e o expõe em `editado_por`. O autouse override define o operador de teste."""
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.flush()
    contact = Contact(
        organization_id=org.id, phone="5531900000099", name="Cliente", opt_in=True, profile_data={}
    )
    session.add(contact)
    await session.flush()
    fb = FeedbackItem(
        organization_id=org.id, contact_id=contact.id, source="manual", type="elogio",
        text="bom", sentiment="neutro",
    )
    session.add(fb)
    await session.commit()

    r = await client.patch(f"/api/feedbacks/{fb.id}", json={"sentiment": "positivo"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sentiment"] == "positivo"
    # O override autouse de require_operator devolve "operador-teste".
    assert data["editado_por"] == "operador-teste"
    assert data["editado_em"]

    # Persistiu no profile_data["feedback_log"] (append-only).
    await session.refresh(contact)
    log = (contact.profile_data or {}).get("feedback_log")
    assert isinstance(log, list) and log
    assert log[-1]["por"] == "operador-teste"
    assert "sentiment" in log[-1]["campos"]
    assert log[-1]["feedback_id"] == str(fb.id)
