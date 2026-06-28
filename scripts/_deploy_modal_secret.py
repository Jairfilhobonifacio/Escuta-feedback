"""Cria o Modal Secret `escuta-prod` lendo os valores do .env local + a PANEL_API_KEY
de ~/.secrets/escuta_panel_key.txt. NÃO imprime valores. Idempotente (--force).

Roda o Modal CLI NO MESMO processo com truststore injetado (o TLS do antivirus nao
propaga a subprocess — ver scripts/_modal_tls.py). Os valores vem do .env, nunca do
comando.

Rodar (da raiz do escuta):  py scripts/_deploy_modal_secret.py
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import truststore  # noqa: E402

truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
KEY_FILE = Path.home() / ".secrets" / "escuta_panel_key.txt"
# Segredos de login lidos PREFERENCIALMENTE de ~/.secrets/ (nunca do comando/argv).
JWT_FILE = Path.home() / ".secrets" / "escuta_jwt_secret.txt"
OPERATOR_HASH_FILE = Path.home() / ".secrets" / "escuta_operator_hash.txt"


def _read_secret_file(path: Path) -> str:
    """Lê um arquivo de segredo (~/.secrets/...) se existir; "" caso contrário."""
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    if not ENV.exists():
        print(f"ERRO: {ENV} nao encontrado", file=sys.stderr)
        return 1
    if not KEY_FILE.exists():
        print(f"ERRO: {KEY_FILE} nao encontrado (gere a PANEL_API_KEY antes)", file=sys.stderr)
        return 1

    env = _load_env(ENV)
    panel_key = KEY_FILE.read_text(encoding="utf-8").strip()

    # APP_ENV: no Modal default = production (liga fail-CLOSED dos segredos + guards).
    app_env = env.get("APP_ENV", "production")
    # Segredos de login: ~/.secrets/ tem prioridade; cai no .env se o arquivo faltar.
    jwt_secret = _read_secret_file(JWT_FILE) or env.get("JWT_SECRET", "")
    operator_hash = _read_secret_file(OPERATOR_HASH_FILE) or env.get(
        "ESCUTA_OPERATOR_PASSWORD_HASH", ""
    )

    pairs = {
        "DATABASE_URL": env.get("DATABASE_URL", ""),
        "GROQ_API_KEY": env.get("GROQ_API_KEY", ""),
        "PANEL_API_KEY": panel_key,
        "DEFAULT_ORG_SLUG": env.get("DEFAULT_ORG_SLUG", "bizzu"),
        "BIZZU_PARTNER_API_URL": env.get("BIZZU_PARTNER_API_URL", ""),
        "BIZZU_PARTNER_API_KEY": env.get("BIZZU_PARTNER_API_KEY", ""),
        "BIZZU_WEBHOOK_SECRET": env.get("BIZZU_WEBHOOK_SECRET", ""),
        "EMBEDDING_MODEL_NAME": "",
        # --- Hardening de segurança (login de operador + CORS + ambiente) -----------
        "APP_ENV": app_env,
        "JWT_SECRET": jwt_secret,
        "ESCUTA_OPERATOR_USER": env.get("ESCUTA_OPERATOR_USER", ""),
        "ESCUTA_OPERATOR_PASSWORD_HASH": operator_hash,
        "WAHA_WEBHOOK_SECRET": env.get("WAHA_WEBHOOK_SECRET", ""),
        # WAHA hospedado (EC2): repassa o endereco/key p/ o Modal alcancar o WAHA em prod.
        "WAHA_BASE_URL": env.get("WAHA_BASE_URL", ""),
        "WAHA_API_KEY": env.get("WAHA_API_KEY", ""),
        "WAHA_SESSION": env.get("WAHA_SESSION", "default"),
        "CORS_ALLOWED_ORIGINS": env.get("CORS_ALLOWED_ORIGINS", ""),
        # Flags de IA Fase 2 — lidas do .env (default OFF "0"); ligar UMA por vez.
        # RAG_HYBRID/CLUSTERING_INLINE ficam inertes no Modal (sem torch/embeddings),
        # mas inofensivos; playbooks e VoC rodam no endpoint.
        "PLAYBOOKS_INLINE_ENABLED": env.get("PLAYBOOKS_INLINE_ENABLED", "0"),
        "VOC_AGENT_ENABLED": env.get("VOC_AGENT_ENABLED", "0"),
        "VOC_WHATSAPP_TOOL_ENABLED": env.get("VOC_WHATSAPP_TOOL_ENABLED", "0"),
        "RAG_HYBRID_ENABLED": env.get("RAG_HYBRID_ENABLED", "0"),
        "CLUSTERING_INLINE_ENABLED": env.get("CLUSTERING_INLINE_ENABLED", "0"),
        # 3 features de IA "mais inteligente" (motor = SÓ Groq; SEM torch/embeddings →
        # rodam normalmente no endpoint Modal). Default OFF "0"; ligar UMA por vez.
        "SENTIMENT_PT_V2_ENABLED": env.get("SENTIMENT_PT_V2_ENABLED", "0"),
        "CORRECTION_LOOP_ENABLED": env.get("CORRECTION_LOOP_ENABLED", "0"),
        "RESPONSE_SUGGESTION_ENABLED": env.get("RESPONSE_SUGGESTION_ENABLED", "0"),
    }
    obrigatorios = ["DATABASE_URL", "GROQ_API_KEY"]
    if app_env == "production":
        # Em produção, login só funciona com estes três (sem eles a API cai em 503).
        obrigatorios += [
            "JWT_SECRET",
            "ESCUTA_OPERATOR_USER",
            "ESCUTA_OPERATOR_PASSWORD_HASH",
            "CORS_ALLOWED_ORIGINS",
            "WAHA_WEBHOOK_SECRET",
        ]
    faltando = [k for k in obrigatorios if not pairs.get(k)]
    if faltando:
        print(
            f"ERRO: faltam (APP_ENV={app_env}): {faltando}\n"
            "  (segredos de login vêm de ~/.secrets/escuta_jwt_secret.txt e "
            "escuta_operator_hash.txt, ou do .env; gere o hash com "
            "scripts/_gen_operator_hash.py)",
            file=sys.stderr,
        )
        return 1

    print("Criando Modal Secret 'escuta-prod' com chaves:", list(pairs.keys()))
    sys.argv = (
        ["modal", "secret", "create", "escuta-prod"]
        + [f"{k}={v}" for k, v in pairs.items()]
        + ["--force"]
    )
    try:
        runpy.run_module("modal", run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        if code == 0:
            print("OK — secret 'escuta-prod' criado/atualizado.")
        return code
    print("OK — secret 'escuta-prod' criado/atualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
