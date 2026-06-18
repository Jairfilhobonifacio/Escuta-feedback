"""Testes do classificador de telefone (app/domain/contacts/whatsapp.py).

Casos espelham os DADOS REAIS achados no piloto (diag de telefones): celular válido,
fixo (contado errado como WhatsApp pela heurística antiga), ID de grupo (120363... e
legado '<phone>-<ts>'), placeholder 'nowa-', vazio e malformado.
"""
from __future__ import annotations

import pytest

from app.domain.contacts.whatsapp import (
    alcance,
    classify_phone,
    sem_whatsapp,
    tem_whatsapp,
)


@pytest.mark.parametrize(
    "phone,classe",
    [
        # celular BR válido (13 díg com DDI) -> alcançável no WhatsApp
        ("5531987654321", "mobile"),
        # celular sem DDI (11 díg, DDD+9+8)
        ("31987654321", "mobile"),
        # celular formatado (o '-' NÃO pode virar 'group')
        ("+55 (31) 98765-4321", "mobile"),
        # FIXO real do piloto (12 díg, sem o 9): heurística antiga contava como WhatsApp
        ("553192973323", "landline"),
        ("552140404640", "landline"),
        # fixo sem DDI (10 díg)
        ("3132973323", "landline"),
        # IDs de GRUPO/comunidade do WhatsApp ingeridos como contato
        ("120363247633739480", "group"),
        ("120363026312907000", "group"),
        ("141837100662997", "group"),
        # JID de grupo LEGADO '<phone>-<timestamp>' (vira >13 díg ao limpar)
        ("553193398851-1603107298", "group"),
        # placeholder do sync (churn só-e-mail)
        ("nowa-42", "placeholder"),
        ("nowa-", "placeholder"),
        # vazio / None
        ("", "empty"),
        ("   ", "empty"),
        (None, "empty"),
        # malformado: curto, ou 11 díg com 3º != 9
        ("123", "invalid"),
        ("3112345678", "landline"),  # 10 díg -> fixo
        ("31812345678", "invalid"),  # 11 díg, 3º='8' (não é 9) -> inválido
    ],
)
def test_classify_phone(phone, classe):
    assert classify_phone(phone) == classe


def test_tem_whatsapp_so_celular():
    assert tem_whatsapp("5531987654321") is True
    assert tem_whatsapp("31987654321") is True
    # fixo, grupo, placeholder, vazio, inválido -> NÃO é WhatsApp
    for p in ["553192973323", "120363247633739480", "nowa-9", "", None, "123"]:
        assert tem_whatsapp(p) is False
        assert sem_whatsapp(p) is True


def test_alcance_buckets():
    assert alcance("5531987654321") == "whatsapp"
    assert alcance("nowa-9") == "so_email"
    assert alcance("553192973323") == "fixo"
    assert alcance("120363247633739480") == "grupo"
    assert alcance("") == "sem_contato"
    assert alcance("123") == "invalido"
