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
    phone_key,
    phone_match_key,
    phone_variants,
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


# --- normalização canônica BR: phone_key / phone_match_key / phone_variants -----

# As 4 grafias do MESMO celular (85 99058955): com/sem DDI 55, com/sem o 9º dígito.
_MESMO_CELULAR = ["5585999058955", "85999058955", "558599058955", "8599058955"]


@pytest.mark.parametrize("phone", _MESMO_CELULAR)
def test_match_key_celular_colide_entre_formatos(phone):
    """As 4 grafias do mesmo celular casam na MESMA match-key (DDD + últimos 8)."""
    assert phone_match_key(phone) == "8599058955"


def test_phone_key_canoniza_por_formato():
    """phone_key insere o 9 só quando há base segura p/ isso (entrada COM o 9, ou
    bare 10 díg de faixa móvel) — NUNCA promove um 12-díg DDI cegamente (seria
    indistinguível de um fixo real; o que unifica as grafias é a match-key)."""
    # Já tem o 9 (com/sem DDI) -> 13 díg canônico.
    assert phone_key("5585999058955") == "5585999058955"
    assert phone_key("85999058955") == "5585999058955"
    # Bare 10 díg, assinante na faixa móvel (9...) -> insere o 9.
    assert phone_key("8599058955") == "5585999058955"
    # 12 díg com DDI, sem o 9: fica como veio (NÃO promove — vide fixo homólogo).
    assert phone_key("558599058955") == "558599058955"


def test_match_key_unifica_as_quatro_grafias_do_celular():
    """A garantia que mata a duplicata: as 4 grafias colidem numa ÚNICA match-key."""
    assert len({phone_match_key(p) for p in _MESMO_CELULAR}) == 1
    assert phone_match_key("558599058955") == phone_match_key("5585999058955")


def test_fixo_nao_vira_celular():
    """Fixo (DDD + 8, assinante começa em 2-5) NÃO ganha o 9 — preserva classify_phone."""
    # 10 díg, sem DDI: canônico = 55 + os 10 díg (continua fixo, 12 díg).
    assert phone_key("3132973323") == "553132973323"
    assert classify_phone(phone_key("3132973323")) == "landline"
    # já com DDI (12 díg): idêntico, sem promover.
    assert phone_key("553192973323") == "553192973323"
    assert classify_phone(phone_key("553192973323")) == "landline"
    # match-key do fixo é DDD + 8 e NÃO colide com um celular de mesmo final.
    assert phone_match_key("3132973323") == "3132973323"


def test_celular_de_10_digitos_ganha_o_9():
    """10 díg cujo assinante começa em 6-9 é CELULAR sem o 9 -> insere o 9 no canônico."""
    assert phone_key("8599058955") == "5585999058955"  # assinante começa em '9'
    assert phone_key("1186543210") == "5511986543210"  # assinante começa em '8'
    assert classify_phone(phone_key("8599058955")) == "mobile"


def test_phone_key_e_match_key_descartam_grupo_e_placeholder():
    for ruim in ["120363247633739480", "553193398851-1603107298", "nowa-42", "", None, "12"]:
        assert phone_key(ruim) is None
        assert phone_match_key(ruim) is None
        assert phone_variants(ruim) == []


def test_variants_incluem_as_quatro_formas_do_celular():
    vs = phone_variants("8599058955")
    # As 4 grafias canônicas precisam estar entre as variantes buscáveis.
    for esperado in _MESMO_CELULAR:
        assert esperado in vs, (esperado, vs)
    # Sem duplicatas.
    assert len(vs) == len(set(vs))


def test_variants_de_qualquer_grafia_cobrem_a_canonica():
    """Buscar por QUALQUER grafia inclui a forma canônica (e a forma como chegou)."""
    for p in _MESMO_CELULAR:
        vs = phone_variants(p)
        assert "5585999058955" in vs
        assert "".join(c for c in p if c.isdigit()) in vs
