"""Testes do gerenciamento da SESSÃO do WhatsApp/WAHA (app/api/whatsapp.py).

Cobre os endpoints de PAREAMENTO (status enriquecido, QR, start/stop/restart) —
NÃO o envio de mensagem. Mesma infra dos demais testes de API: app real + WAHA
fake injetado via dependency_overrides[get_waha]. NENHUM teste toca a rede: o
FakeSessionWAHA simula tanto o WAHA ligado (com vários estados) quanto desligado
(off), provando que tudo responde gracioso (sem 500) quando o gateway some.

Cobertura:
- GET /whatsapp/status: inclui `status` (string crua) + conectado coerente.
- GET /whatsapp/qr: devolve {qr,status}; COM QR (data-uri) quando SCAN_QR_CODE;
  SEM QR (qr=null) quando WORKING; gracioso (qr=null,status=null) quando WAHA off.
- POST /whatsapp/session/{start,stop,restart}: chamam o método certo do serviço
  e devolvem {ok,status}; graciosos quando o fake simula WAHA off (ok=false).
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.whatsapp import get_waha  # noqa: E402
from app.main import app  # noqa: E402

_QR_DATA_URI = "data:image/png;base64,iVBORw0KGgoAAAANS"


class FakeSessionWAHA:
    """Dublê do WAHAService focado na SESSÃO — sem rede.

    Parametrizado por:
      - status: o que `get_session_status` devolve (None = WAHA off/erro).
      - off: quando True, simula WAHA indisponível — start/stop/restart devolvem
        ok=false e status=None; o QR sai como {"qr": None, "status": None}.

    Registra em `self.calls` cada método de sessão invocado, p/ provar o roteamento.
    """

    def __init__(self, status: Optional[str] = "WORKING", off: bool = False) -> None:
        self.status = None if off else status
        self.off = off
        self.calls: List[str] = []

    async def get_session_status(self, session: str = None) -> Optional[str]:
        return self.status

    async def get_qr_code(self, session: str = None) -> Dict[str, Any]:
        self.calls.append("get_qr_code")
        if self.off:
            return {"qr": None, "status": None}
        # WAHA não expõe QR quando já está WORKING.
        if self.status == "WORKING":
            return {"qr": None, "status": self.status}
        return {"qr": _QR_DATA_URI, "status": self.status}

    async def start_session(self, session: str = None) -> Dict[str, Any]:
        self.calls.append("start_session")
        if self.off:
            return {"ok": False, "status": None}
        self.status = "STARTING"
        return {"ok": True, "status": self.status}

    async def stop_session(self, session: str = None) -> Dict[str, Any]:
        self.calls.append("stop_session")
        if self.off:
            return {"ok": False, "status": None}
        self.status = "STOPPED"
        return {"ok": True, "status": self.status}

    async def restart_session(self, session: str = None) -> Dict[str, Any]:
        self.calls.append("restart_session")
        if self.off:
            return {"ok": False, "status": None}
        self.status = "STARTING"
        return {"ok": True, "status": self.status}


@pytest_asyncio.fixture
async def make_client():
    """Fábrica de client com um FakeSessionWAHA injetável (estado/off)."""

    def _build(fake: FakeSessionWAHA) -> AsyncClient:
        app.dependency_overrides[get_waha] = lambda: fake
        transport = ASGITransport(app=app)
        c = AsyncClient(transport=transport, base_url="http://test")
        c.fake_waha = fake  # type: ignore[attr-defined]
        return c

    try:
        yield _build
    finally:
        app.dependency_overrides.clear()


# --- GET /whatsapp/status ----------------------------------------------------


@pytest.mark.asyncio
async def test_status_inclui_status_string_working(make_client):
    """status WORKING -> conectado true + status 'WORKING' + session/base_url."""
    fake = FakeSessionWAHA(status="WORKING")
    async with make_client(fake) as client:
        r = await client.get("/api/whatsapp/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "WORKING"
    assert data["conectado"] is True
    assert "session" in data and "base_url" in data


@pytest.mark.asyncio
async def test_status_scan_qr_nao_conectado(make_client):
    """status SCAN_QR_CODE -> conectado false, mas status reflete o estado real."""
    fake = FakeSessionWAHA(status="SCAN_QR_CODE")
    async with make_client(fake) as client:
        r = await client.get("/api/whatsapp/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "SCAN_QR_CODE"
    assert data["conectado"] is False


@pytest.mark.asyncio
async def test_status_waha_off_gracioso(make_client):
    """WAHA off -> status null + conectado false, sem 500."""
    fake = FakeSessionWAHA(off=True)
    async with make_client(fake) as client:
        r = await client.get("/api/whatsapp/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] is None
    assert data["conectado"] is False


# --- GET /whatsapp/qr --------------------------------------------------------


@pytest.mark.asyncio
async def test_qr_com_qr_quando_scan(make_client):
    """SCAN_QR_CODE -> devolve o data-uri do QR + status SCAN_QR_CODE."""
    fake = FakeSessionWAHA(status="SCAN_QR_CODE")
    async with make_client(fake) as client:
        r = await client.get("/api/whatsapp/qr")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["qr"] == _QR_DATA_URI
    assert data["qr"].startswith("data:image/")
    assert data["status"] == "SCAN_QR_CODE"
    assert "get_qr_code" in fake.calls


@pytest.mark.asyncio
async def test_qr_sem_qr_quando_working(make_client):
    """Já WORKING -> qr=null + status WORKING, e NEM chama get_qr_code (não há QR)."""
    fake = FakeSessionWAHA(status="WORKING")
    async with make_client(fake) as client:
        r = await client.get("/api/whatsapp/qr")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["qr"] is None
    assert data["status"] == "WORKING"
    # Curto-circuito no endpoint: WORKING não pede QR ao serviço.
    assert "get_qr_code" not in fake.calls


@pytest.mark.asyncio
async def test_qr_waha_off_gracioso(make_client):
    """WAHA off -> {"qr": null, "status": null}, sem 500."""
    fake = FakeSessionWAHA(off=True)
    async with make_client(fake) as client:
        r = await client.get("/api/whatsapp/qr")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["qr"] is None
    assert data["status"] is None


# --- POST /whatsapp/session/{start,stop,restart} -----------------------------


@pytest.mark.asyncio
async def test_session_start_chama_metodo_e_retorna_ok(make_client):
    """start: chama start_session e devolve {ok:true, status}."""
    fake = FakeSessionWAHA(status="STOPPED")
    async with make_client(fake) as client:
        r = await client.post("/api/whatsapp/session/start")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == "STARTING"
    assert fake.calls == ["start_session"]


@pytest.mark.asyncio
async def test_session_stop_chama_metodo_e_retorna_ok(make_client):
    """stop: chama stop_session e devolve {ok:true, status STOPPED}."""
    fake = FakeSessionWAHA(status="WORKING")
    async with make_client(fake) as client:
        r = await client.post("/api/whatsapp/session/stop")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == "STOPPED"
    assert fake.calls == ["stop_session"]


@pytest.mark.asyncio
async def test_session_restart_chama_metodo_e_retorna_ok(make_client):
    """restart: chama restart_session (não start/stop direto) e devolve {ok,status}."""
    fake = FakeSessionWAHA(status="WORKING")
    async with make_client(fake) as client:
        r = await client.post("/api/whatsapp/session/restart")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == "STARTING"
    assert fake.calls == ["restart_session"]


@pytest.mark.asyncio
async def test_session_actions_graciosos_quando_waha_off(make_client):
    """WAHA off: start/stop/restart respondem 200 com {ok:false, status:null}."""
    for action in ("start", "stop", "restart"):
        fake = FakeSessionWAHA(off=True)
        async with make_client(fake) as client:
            r = await client.post(f"/api/whatsapp/session/{action}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is False, action
        assert data["status"] is None, action
        assert fake.calls == [f"{action}_session"]
