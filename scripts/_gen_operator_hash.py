"""Gera o HASH bcrypt da senha do operador do Escuta (ESCUTA_OPERATOR_PASSWORD_HASH).

Regra de ouro: a senha NUNCA passa por argv (cairia no histórico/no chat). Lemos por
getpass (não ecoa) ou por stdin (pipe). Imprimimos SÓ o hash — nada da senha em claro.

Uso (da raiz do escuta):
    py scripts/_gen_operator_hash.py
    # digite a senha (não aparece); confirme. Cole o hash em ~/.secrets / no .env:
    py scripts/_gen_operator_hash.py > ~/.secrets/escuta_operator_hash.txt

Pipe (CI/automação — evita o prompt):
    printf '%s' "$SENHA" | py scripts/_gen_operator_hash.py --stdin
"""
from __future__ import annotations

import getpass
import sys

import bcrypt


def _read_password() -> str:
    if "--stdin" in sys.argv[1:]:
        # Lê a senha de stdin (sem newline final). Para pipes/automação.
        pw = sys.stdin.readline().rstrip("\n")
        if not pw:
            print("ERRO: senha vazia em stdin.", file=sys.stderr)
            raise SystemExit(2)
        return pw

    pw = getpass.getpass("Senha do operador: ")
    if not pw:
        print("ERRO: senha vazia.", file=sys.stderr)
        raise SystemExit(2)
    confirm = getpass.getpass("Confirme a senha: ")
    if pw != confirm:
        print("ERRO: as senhas não conferem.", file=sys.stderr)
        raise SystemExit(2)
    return pw


def main() -> int:
    pw = _read_password()
    h = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    # SÓ o hash no stdout (para poder redirecionar p/ arquivo). Dica vai no stderr.
    print(h)
    print(
        "\nCole este hash em ESCUTA_OPERATOR_PASSWORD_HASH "
        "(.env local ou ~/.secrets/escuta_operator_hash.txt).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
