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


def _digits(phone: str | None) -> str:
    """Só os dígitos do telefone (descarta '+', espaços, parênteses, '-')."""
    return re.sub(r"\D", "", str(phone or ""))


def _nacional(digits: str) -> str:
    """Parte nacional: remove o DDI 55 quando presente (>=12 díg). Espelha classify_phone."""
    return digits[2:] if digits.startswith("55") and len(digits) >= 12 else digits


def phone_key(phone: str | None) -> str | None:
    """Forma CANÔNICA E.164 (sem '+') p/ GRAVAR o contato: `55` + parte nacional.

    Canoniza um telefone BR para uma forma estável de armazenamento:

      - celular  -> `55` + DDD(2) + `9` + 8 díg (13)   ex.: 8599058955 -> 5585999058955
      - fixo     -> `55` + DDD(2) + 8 díg (12)          ex.: 3132973323 -> 553132973323

    Regras:
      - remove tudo que não é dígito; DDI `55` é opcional na entrada;
      - insere o 9º dígito SÓ quando vier SEM DDI, com 10 díg (DDD + 8), e o assinante
        começa na faixa de CELULAR (6/7/8/9). NÃO promove fixo real (assinante 2-5) e,
        com DDI presente, NÃO promove cegamente um 12-díg (DDI+DDD+8) — seria
        indistinguível de um fixo real (ex.: 553192973323). É o que une as grafias
        para o dedup é a match-key, não a forma canônica;
      - entrada já-canônica (11 díg móvel com o 9 / 12-13 com DDI) passa idêntica;
      - grupo/placeholder/vazio/inválido -> None (não há telefone canônico a gravar).

    É a forma a usar ao CRIAR um Contact; para BUSCAR um já-existente em formato
    divergente use `phone_match_key` / `phone_variants`.
    """
    digits = _digits(phone)
    if not digits or str(phone or "").strip().startswith("nowa-"):
        return None
    # Grupos/JIDs e lixo: sem telefone canônico.
    if digits.startswith("120363") or len(digits) > 13:
        return None

    tem_ddi = digits.startswith("55") and len(digits) >= 12
    nac = _nacional(digits)

    # Celular já completo (DDD + 9 + 8 = 11, 3º == '9'): canônico = 55 + nac.
    if len(nac) == 11 and nac[2] == "9":
        return "55" + nac

    if len(nac) == 10:
        # DDD(2) + assinante(8). Ambíguo SÓ quando NÃO veio DDI: aí o início do
        # assinante decide a faixa (Anatel) — 6-9 = CELULAR sem o 9 (insere o 9),
        # 2-5 = FIXO (mantém). COM DDI, o comprimento já fixou que é fixo (DDI+DDD+8):
        # NÃO promovemos cegamente, mesmo que o assinante comece em 9
        # (ex.: 553192973323 é fixo, não vira celular).
        if not tem_ddi and nac[2] in "6789":
            return "55" + nac[:2] + "9" + nac[2:]
        return "55" + nac  # fixo
    return None


def phone_match_key(phone: str | None) -> str | None:
    """Chave TOLERANTE p/ casar telefones: DDD(2) + últimos 8 dígitos.

    Ignora o DDI `55` e o 9º dígito do celular — então os MESMOS números escritos
    com/sem DDI e com/sem o 9 colidem na mesma chave. Usada para ACHAR um contato já
    cadastrado num formato divergente (evita duplicata), não para gravar.

      5585999058955 | 85999058955 | 558599058955 | 8599058955  -> '8599058955'

    Grupo/placeholder/vazio/inválido -> None (nada a casar).
    """
    digits = _digits(phone)
    if not digits or str(phone or "").strip().startswith("nowa-"):
        return None
    if digits.startswith("120363") or len(digits) > 13:
        return None
    nac = _nacional(digits)
    # Remove o 9 inicial do assinante (só quando há 9 díg de assinante: DDD + 9 + 8).
    if len(nac) == 11 and nac[2] == "9":
        nac = nac[:2] + nac[3:]
    if len(nac) != 10:
        return None  # curto/comprido demais p/ formar DDD + 8.
    return nac  # DDD(2) + 8 dígitos


def phone_variants(phone: str | None) -> list[str]:
    """Variantes plausíveis de um telefone p/ um SELECT por igualdade em `Contact.phone`.

    Cobre as 4 combinações com/sem DDI × com/sem o 9 do celular, mais a forma como
    chegou (digits crus) e a canônica — assim achamos um contato gravado em QUALQUER
    desses formatos. Ordem estável, sem duplicatas; lista vazia p/ grupo/lixo/vazio.

      8599058955 -> ['8599058955','558599058955','85999058955','5585999058955',...]
    """
    key = phone_match_key(phone)
    if key is None:
        return []
    ddd, assinante = key[:2], key[2:]
    cands = [
        key,                                  # DDD + 8 (sem DDI, sem 9)
        "55" + key,                           # DDI + DDD + 8
        ddd + "9" + assinante,                # DDD + 9 + 8
        "55" + ddd + "9" + assinante,         # DDI + DDD + 9 + 8
    ]
    # Inclui a forma crua recebida e a canônica (cobre fixo, que não ganha o 9).
    raw = _digits(phone)
    if raw:
        cands.append(raw)
    canon = phone_key(phone)
    if canon:
        cands.append(canon)
    # Dedup preservando a ordem.
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def tem_whatsapp(phone: str | None) -> bool:
    """True só se for um celular BR válido (alcançável no WhatsApp)."""
    return classify_phone(phone) == "mobile"


def sem_whatsapp(phone: str | None) -> bool:
    """Negação de tem_whatsapp (fixo, grupo, placeholder, vazio ou inválido)."""
    return not tem_whatsapp(phone)


def alcance(phone: str | None) -> str:
    """Bucket legível p/ os stats: whatsapp | so_email | fixo | grupo | sem_contato | invalido."""
    return ALCANCE_LABEL[classify_phone(phone)]
