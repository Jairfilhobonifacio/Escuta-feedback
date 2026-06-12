"""Parsers de resposta de pesquisa.

Fase 0: apenas NPS (0-10). Função pura, sem I/O, testável isoladamente.
Decisão: extrai o PRIMEIRO inteiro 0-10 do texto (dígito tem prioridade sobre
palavra). Cobre casos comuns em pt-BR ("9", "nota 9", "daria um 8", "10/10",
"nota dez"). Texto sem número válido -> None (o resolver então pede um número).
"""
from __future__ import annotations

import re
from typing import Optional

# Palavras-número pt-BR de 0 a 10 (fallback quando não há dígito).
# "um/uma" foram REMOVIDOS de propósito: são artigos comuns ("quero falar com uma
# pessoa") e capturá-los como nota 1 gera falso-positivo que mascara hand-off/dúvida.
# Quem dá nota 1 escreve o dígito. O brain cobre os casos por extenso ambíguos.
_WORDS = {
    "zero": 0, "dois": 2, "duas": 2, "tres": 3, "três": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}

# \b...\b garante token isolado: "2024" não casa; "10" e "9" sim.
_DIGIT_RE = re.compile(r"\b(10|[0-9])\b")
_WORD_RE = re.compile(r"\b(" + "|".join(_WORDS) + r")\b")


def parse_nps(text: Optional[str]) -> Optional[int]:
    """Retorna um inteiro 0-10 extraído do texto, ou None se não houver."""
    if not text:
        return None
    t = text.strip().lower()

    m = _DIGIT_RE.search(t)
    if m:
        return int(m.group(1))

    wm = _WORD_RE.search(t)
    if wm:
        return _WORDS[wm.group(1)]

    return None


def nps_bucket(score: Optional[int]) -> Optional[str]:
    """Classifica o NPS: 0-6 detrator, 7-8 passivo, 9-10 promotor."""
    if score is None:
        return None
    if score <= 6:
        return "detractor"
    if score <= 8:
        return "passive"
    return "promoter"


if __name__ == "__main__":
    # Auto-teste (rodar: python app/domain/survey/parsers.py)
    cases = {
        "9": 9, "10": 10, "0": 0, "nota 9": 9, "daria um 8": 8,
        "10/10": 10, "uns 8 ou 9": 8, "nota dez": 10, "zero, horrível": 0,
        "oi tudo bem?": None, "": None, "2024": None, "nota 11": 11,  # 11 capturado? não: \b11\b não casa 0-10
    }
    # ajuste esperado: "nota 11" -> _DIGIT_RE casa "1"? não, \b(10|[0-9])\b sobre "11" -> não casa token "11";
    # casa o "1"? "11" é um token só -> \b11\b, então (10|[0-9]) não casa -> None.
    expected_overrides = {"nota 11": None}
    cases.update(expected_overrides)

    buckets = {0: "detractor", 6: "detractor", 7: "passive", 8: "passive", 9: "promoter", 10: "promoter"}

    ok = True
    for txt, exp in cases.items():
        got = parse_nps(txt)
        flag = "✓" if got == exp else "✗"
        if got != exp:
            ok = False
        print(f"  {flag} parse_nps({txt!r}) = {got}  (esperado {exp})")
    for score, exp in buckets.items():
        got = nps_bucket(score)
        flag = "✓" if got == exp else "✗"
        if got != exp:
            ok = False
        print(f"  {flag} nps_bucket({score}) = {got}  (esperado {exp})")

    print("\nTODOS VERDES ✅" if ok else "\nFALHOU ❌")
    raise SystemExit(0 if ok else 1)
