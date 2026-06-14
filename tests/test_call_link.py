"""Oferta de call: append_call_link só anexa o link quando há BIZZU_CALL_URL configurada."""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey.helpers import append_call_link  # noqa: E402


def test_sem_link_devolve_intacto():
    txt = "vou te conectar com o time 🙏"
    assert append_call_link(txt, None) == txt
    assert append_call_link(txt, "") == txt


def test_com_link_anexa_uma_vez():
    txt = "vou te conectar com o time 🙏"
    url = "https://cal.com/bizzu/15min"
    out = append_call_link(txt, url)
    assert url in out
    assert out.startswith(txt)
    # idempotente: não duplica o link
    assert append_call_link(out, url) == out
    assert out.count(url) == 1
