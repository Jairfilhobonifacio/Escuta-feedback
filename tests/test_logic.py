"""Testes da lógica pura do resolver (decide_next) — stdlib, sem banco.

Rodar: python tests/test_logic.py   (ou: pytest tests/test_logic.py)
"""
import os
import sys

# permite rodar standalone (sem instalar o pacote)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.survey.logic import decide_next, Decision  # noqa: E402
from app.domain.survey.constants import (  # noqa: E402
    STATUS_SENT,
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
)

REASON = "por quê?"
THANKS = "valeu!"
RETRY = "manda um número de 0 a 10"


def _decide(status, msg):
    return decide_next(status, msg, reason_prompt=REASON, thanks_msg=THANKS, retry_msg=RETRY)


def test_nps_valido_promotor():
    d = _decide(STATUS_SENT, "9")
    assert d == Decision(reply_text=REASON, new_status=STATUS_AWAITING_REASON, answer_score=9, nps_bucket="promoter")


def test_nps_valido_detrator_em_frase():
    d = _decide(STATUS_SENT, "daria uns 5 no máximo")
    assert d.answer_score == 5 and d.nps_bucket == "detractor" and d.new_status == STATUS_AWAITING_REASON


def test_nps_invalido_pede_numero():
    d = _decide(STATUS_SENT, "oi tudo bem?")
    assert d == Decision(reply_text=RETRY, new_status=STATUS_SENT)
    assert d.answer_score is None


def test_motivo_fecha():
    d = _decide(STATUS_AWAITING_REASON, "porque os resumos são ótimos")
    assert d.new_status == STATUS_CLOSED
    assert d.answer_text == "porque os resumos são ótimos"
    assert d.reply_text == THANKS


def test_sem_pesquisa_pendente_retorna_none():
    assert _decide(STATUS_CLOSED, "9") is None
    assert _decide("qualquer_outro", "9") is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}  -> {e!r}")
    print(f"\n{len(tests)-failed}/{len(tests)} verdes" + (" ✅" if not failed else " ❌"))
    raise SystemExit(1 if failed else 0)
