"""Testes do _extract_inbound do webhook — foco no modo self-chat de teste.

Rodar: python tests/test_webhook_extract.py   (ou: pytest tests/test_webhook_extract.py)
"""
import dataclasses
import os
import sys

# permite rodar standalone (sem instalar o pacote)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.api.webhook as webhook  # noqa: E402
from app.api.webhook import _extract_inbound  # noqa: E402
from app.domain.survey.resolver import DEFAULT_RETRY_MSG  # noqa: E402

ME = "5524998365809@c.us"
OTHER = "5531999990001@c.us"


def _payload(body, *, from_=ME, to=ME, from_me=True, source=None, msg_id="m1", event="message.any"):
    """Default `message.any`: é o evento que o WAHA real emite (cobre fromMe)."""
    msg = {"from": from_, "to": to, "body": body, "fromMe": from_me, "id": msg_id}
    if source is not None:
        msg["source"] = source
    return {"event": event, "payload": msg}


def _with_flag(value: bool):
    """Troca settings.self_chat_test no módulo do webhook (dataclass é frozen)."""
    webhook.settings = dataclasses.replace(webhook.settings, self_chat_test=value)


def test_inbound_normal_de_terceiro_continua_passando():
    _with_flag(False)
    got = _extract_inbound(_payload("9", from_=OTHER, to=ME, from_me=False))
    assert got == {"from": "5531999990001", "from_raw": OTHER, "body": "9", "message_id": "m1"}


def test_fromme_descartado_com_flag_off():
    _with_flag(False)
    assert _extract_inbound(_payload("9")) is None


def test_self_chat_resposta_do_celular_passa_com_flag_on():
    _with_flag(True)
    got = _extract_inbound(_payload("9", source="app"))
    assert got == {"from": "5524998365809", "from_raw": ME, "body": "9", "message_id": "m1"}


def test_self_chat_via_lid_preserva_from_raw():
    """Self-chat identificado por LID: from_raw mantém o @lid p/ o handler resolver."""
    _with_flag(True)
    lid = "77052233408626@lid"
    got = _extract_inbound(_payload("9", from_=lid, to=lid))
    assert got == {"from": "77052233408626", "from_raw": lid, "body": "9", "message_id": "m1"}


def test_self_chat_sem_source_tambem_passa():
    _with_flag(True)
    got = _extract_inbound(_payload("o material é ótimo"))
    assert got is not None and got["body"] == "o material é ótimo"


def test_eco_via_api_descartado():
    _with_flag(True)
    assert _extract_inbound(_payload("qualquer texto", source="api")) is None


def test_eco_por_texto_do_sistema_descartado():
    _with_flag(True)
    assert _extract_inbound(_payload(DEFAULT_RETRY_MSG)) is None


def test_eco_da_pergunta_nps_renderizada_descartado():
    _with_flag(True)
    pergunta = "Oi Concurseiro! De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"
    assert _extract_inbound(_payload(pergunta)) is None


def test_fromme_para_outro_numero_descartado_mesmo_com_flag_on():
    _with_flag(True)
    assert _extract_inbound(_payload("9", from_=ME, to=OTHER)) is None


def test_evento_message_classico_continua_aceito():
    _with_flag(False)
    got = _extract_inbound(_payload("9", from_=OTHER, to=ME, from_me=False, event="message"))
    assert got is not None and got["body"] == "9"


def test_evento_desconhecido_descartado():
    _with_flag(True)
    assert _extract_inbound(_payload("9", event="message.ack")) is None


def test_self_chat_formato_misto_marca_self_check():
    """Caso real: from='55...@c.us', to='...@lid' (mesmo número em formatos
    distintos). O extract não decide sozinho — marca p/ o handler resolver."""
    _with_flag(True)
    lid = "77052233408626@lid"
    got = _extract_inbound(_payload("9", from_=ME, to=lid, source="app"))
    assert got is not None
    assert got["from"] == "5524998365809"
    assert got["self_check_to"] == lid


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
