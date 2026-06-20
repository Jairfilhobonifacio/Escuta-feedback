"""Áudio inbound: detecção no webhook (_extract_inbound) + serviço de transcrição.

Unit, sem rede: a transcrição real (Groq) é best-effort e retorna None sem chave/áudio.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.api.webhook import _extract_inbound  # noqa: E402
from app.services.audio import transcribe_audio  # noqa: E402


def test_extract_inbound_detecta_audio_ptt():
    payload = {"event": "message", "payload": {
        "from": "5531900000010@c.us", "type": "ptt", "id": "AAA",
        "media": {"url": "http://localhost:3000/api/files/x.ogg", "mimetype": "audio/ogg; codecs=opus"},
    }}
    out = _extract_inbound(payload)
    assert out is not None
    assert out["media_type"] == "audio"
    assert out["media_url"].endswith(".ogg")
    assert out["media_mimetype"].startswith("audio/")
    assert out["body"] == ""  # áudio não tem texto


def test_extract_inbound_audio_por_mimetype():
    payload = {"event": "message", "payload": {
        "from": "5531999990000@c.us", "type": "media",
        "media": {"url": "u", "mimetype": "audio/mpeg"},
    }}
    out = _extract_inbound(payload)
    assert out is not None and out["media_type"] == "audio"


def test_extract_inbound_texto_continua_funcionando():
    payload = {"event": "message", "payload": {"from": "5531999990000@c.us", "body": "nota 9", "id": "B"}}
    out = _extract_inbound(payload)
    assert out is not None
    assert out["body"] == "nota 9"
    assert out["media_type"] is None


def test_extract_inbound_vazio_ignora():
    payload = {"event": "message", "payload": {"from": "5531999990000@c.us", "body": "   "}}
    assert _extract_inbound(payload) is None


@pytest.mark.asyncio
async def test_transcribe_sem_chave_retorna_none():
    assert await transcribe_audio(url="http://x/a.ogg", groq_api_key=None) is None


@pytest.mark.asyncio
async def test_transcribe_sem_audio_retorna_none():
    assert await transcribe_audio(groq_api_key="k", url=None, data_b64=None) is None
