"""Central de Fontes — config por ORGANIZAÇÃO das fontes externas de dados.

Módulo irmão de `app/domain/features.py`: mesmo padrão de catálogo + override por org
gravado em `Organization.settings` (copia-edita-reatribui o JSONB; SEM migration). Aqui a
unidade não é uma feature flag, mas uma FONTE de dados que o dono liga/desliga e dispara
um sync por ela.

Por fonte guardamos, em `settings["sources"][key]`:
  - `enabled`: override por org (default false) — o dono precisa LIGAR antes de sincronizar.
  - `sync`: estado do último/atual sync (pollável pelo painel), no formato `DEFAULT_SYNC`.

`available` NÃO mora no settings: é derivado do AMBIENTE (a chave da API está no deploy?).
Nunca expõe a chave — só um bool. O env é o piso: o painel não liga uma fonte indisponível.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations import bizzu_partner

# Estado-default do sync (também o shape do contrato com o frontend). status ∈
# idle|running|done|error; datas ISO-8601 ou null; contadores zerados.
DEFAULT_SYNC: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "total": 0,
    "created": 0,
    "updated": 0,
    "errors": 0,
    "error_msg": None,
}

# Um sync 'running' parado há >= 15 min é considerado travado (o processo provavelmente
# morreu antes de finalizar) e PODE ser redisparado — ver `sync_is_running`.
SYNC_STALE_AFTER = timedelta(minutes=15)

# Catálogo das fontes gerenciáveis — rótulos/descrições na LINGUAGEM DO DONO (análogo a
# FEATURES). Por ora só a base de clientes da Bizzu (API Partner).
SOURCES: list[dict[str, Any]] = [
    {
        "key": "bizzu_partner",
        "label": "Bizzu — Clientes (API Partner)",
        "descricao": (
            "Sincroniza a base de clientes da Bizzu (estado da assinatura, plano, perfil, "
            "NPS) e enriquece os contatos para os filtros do painel."
        ),
    },
]

_BY_KEY: dict[str, dict[str, Any]] = {s["key"]: s for s in SOURCES}


def source_known(key: str) -> bool:
    """A fonte `key` existe no catálogo? (o endpoint traduz False para 422)."""
    return key in _BY_KEY


def source_available(key: str) -> bool:
    """A fonte está DISPONÍVEL no ambiente (a chave da API está no deploy)?

    Mesmo critério de env do resto do repo: a constante `BIZZU_PARTNER_API_KEY` lida de
    `os.getenv` no import do cliente. Referencia o módulo (não o valor) p/ ser testável.
    NUNCA expõe a chave — só um bool.
    """
    if key == "bizzu_partner":
        return bool(bizzu_partner.BIZZU_PARTNER_API_KEY)
    return False


def _sources_settings(org: Any) -> dict[str, Any]:
    """Bloco settings["sources"] (cópia rasa) ou {} — leitura tolerante a ausência."""
    return dict((getattr(org, "settings", None) or {}).get("sources") or {})


def source_enabled(org: Any, key: str) -> bool:
    """Override por org de `key` (default False) — a fonte está LIGADA para esta org?"""
    entry = _sources_settings(org).get(key) or {}
    return bool(entry.get("enabled", False))


def sync_state(org: Any, key: str) -> dict[str, Any]:
    """Estado do sync DESTA org para `key` (default 'idle' se nunca rodou)."""
    entry = _sources_settings(org).get(key) or {}
    return {**DEFAULT_SYNC, **(entry.get("sync") or {})}


def _parse_iso(value: Any) -> datetime | None:
    """Parse tolerante de uma data ISO-8601 (aceita 'Z'); None se ausente/inválida."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def sync_is_running(state: dict[str, Any], now: datetime | None = None) -> bool:
    """Há um sync EM ANDAMENTO e ainda não travado (status='running' há < 15 min)?

    'running' há >= 15 min é considerado stale (provavelmente morreu) → False, p/ PERMITIR
    o redisparo. 'running' sem `started_at` confiável também conta como travado (não dá pra
    afirmar que começou há < 15 min).
    """
    if (state or {}).get("status") != "running":
        return False
    started = _parse_iso((state or {}).get("started_at"))
    if started is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - started) < SYNC_STALE_AFTER


def source_view(org: Any, key: str) -> dict[str, Any]:
    """Snapshot de UMA fonte p/ o painel (contrato do item): key/label/descricao +
    available/enabled/sync."""
    s = _BY_KEY[key]
    return {
        "key": s["key"],
        "label": s["label"],
        "descricao": s["descricao"],
        "available": source_available(key),
        "enabled": source_enabled(org, key),
        "sync": sync_state(org, key),
    }


def sources_view(org: Any) -> list[dict[str, Any]]:
    """Catálogo + estado por org (contrato do GET /sources)."""
    return [source_view(org, s["key"]) for s in SOURCES]


def _write_source(
    org: Any, key: str, *, enabled: bool | None = None, sync: dict[str, Any] | None = None
) -> None:
    """Grava enabled e/ou sync de `key` (copia-edita-reatribui o JSONB; SEM migration)."""
    s = dict(getattr(org, "settings", None) or {})
    sources = dict(s.get("sources") or {})
    entry = dict(sources.get(key) or {})
    if enabled is not None:
        entry["enabled"] = bool(enabled)
    if sync is not None:
        entry["sync"] = dict(sync)
    sources[key] = entry
    s["sources"] = sources
    org.settings = s  # reatribui p/ marcar o JSONB sujo (padrão features/boards/config).


def set_source_enabled(org: Any, key: str, enabled: bool) -> None:
    """Liga/desliga a fonte `key` para a org. `KeyError` se a key não existe (→ 422)."""
    if key not in _BY_KEY:
        raise KeyError(key)
    _write_source(org, key, enabled=enabled)


def write_sync(org: Any, key: str, sync: dict[str, Any]) -> None:
    """Persiste o estado do sync de `key` (usado pelo serviço de sync durante o progresso)."""
    _write_source(org, key, sync=sync)
