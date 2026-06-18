"""Classificação de telefone p/ saber quem é REALMENTE alcançável no WhatsApp.

A heurística antiga ("tem telefone e não começa com 'nowa-'") contava FIXO, ID de
GRUPO/comunidade e número malformado como "com WhatsApp" — dado incorreto. Aqui
classificamos pelo FORMATO do número (NÃO consulta a rede do WhatsApp; para a
verificação definitiva número-a-número seria preciso o check-exists do WAHA, que
depende de OK do usuário e da sessão ligada):

- mobile      celular BR válido: 55 + DDD(2) + 9 + 8 díg (13)  ou  DDD(2) + 9 + 8 (11)
- landline    fixo: DDD(2)+8 (10) ou 55+DDD+8 (12) — sem o 9 inicial do assinante
- group       ID de grupo/comunidade do WhatsApp (JID 120363...; ou > 13 dígitos, que
              é o caso dos JIDs legados '<phone>-<timestamp>')
- placeholder placeholder 'nowa-...' que o sync grava p/ churn SÓ-E-MAIL (sem telefone)
- empty       vazio / None
- invalid     o resto (curto demais; 11 díg mas 3º não é 9; etc.)

`tem_whatsapp(phone)` == classe 'mobile'. SÓ celular BR válido é alcançável no WhatsApp.
"""
from __future__ import annotations

import re
from typing import Literal

PhoneClass = Literal["mobile", "landline", "group", "placeholder", "empty", "invalid"]

# Rótulo coarse p/ os stats de alcance (uma classe -> um bucket legível).
ALCANCE_LABEL: dict[str, str] = {
    "mobile": "whatsapp",
    "placeholder": "so_email",
    "landline": "fixo",
    "group": "grupo",
    "empty": "sem_contato",
    "invalid": "invalido",
}


def classify_phone(phone: str | None) -> PhoneClass:
    """Classe estrutural do telefone (só formato; não consulta o WhatsApp)."""
    if phone is None:
        return "empty"
    p = str(phone).strip()
    if not p:
        return "empty"
    if p.startswith("nowa-"):
        return "placeholder"

    digits = re.sub(r"\D", "", p)
    if not digits:
        return "invalid"
    # IDs de grupo/comunidade: JID novo (120363...) ou qualquer coisa com mais dígitos
    # do que um número BR com DDI (13). Os grupos legados '<phone>-<ts>' caem aqui pelo
    # comprimento, então não precisamos tratar o '-' à parte (e assim não confundimos um
    # celular formatado '99999-9999' com grupo).
    if digits.startswith("120363") or len(digits) > 13:
        return "group"

    # Normaliza o DDI 55 (quando presente) para olhar só a parte nacional.
    nac = digits[2:] if digits.startswith("55") and len(digits) >= 12 else digits
    if len(nac) == 11 and nac[2] == "9":
        return "mobile"
    if len(nac) == 10:
        return "landline"
    return "invalid"


def tem_whatsapp(phone: str | None) -> bool:
    """True só se for um celular BR válido (alcançável no WhatsApp)."""
    return classify_phone(phone) == "mobile"


def sem_whatsapp(phone: str | None) -> bool:
    """Negação de tem_whatsapp (fixo, grupo, placeholder, vazio ou inválido)."""
    return not tem_whatsapp(phone)


def alcance(phone: str | None) -> str:
    """Bucket legível p/ os stats: whatsapp | so_email | fixo | grupo | sem_contato | invalido."""
    return ALCANCE_LABEL[classify_phone(phone)]
