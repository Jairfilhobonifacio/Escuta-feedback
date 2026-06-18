"""Parametrização do modelo de embedding (EMBEDDING_MODEL_NAME) — sem rede/sem MiniLM.

Invariantes:
- `embedding_model_name=""` (default) ⇒ o EmbeddingService carrega EXATAMENTE o
  modelo histórico (all-MiniLM-L6-v2, 384d). ZERO regressão.
- `embedding_model_name="...multilingual..."` ⇒ o singleton passa esse nome adiante.
- A dimensão alvo (EMBED_DIM) continua 384 → coluna vector(384) intacta (sem migration).

Nada baixa modelo: o `SentenceTransformer` é substituído por um dublê que só registra
o nome recebido. O singleton `get_embedder` é cacheado (lru_cache) — limpamos o cache
em cada caso para reler a flag.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.services import embeddings as emb  # noqa: E402
from app.services.embeddings import (  # noqa: E402
    EMBED_DIM,
    EMBED_MODEL,
    MULTILINGUAL_MODEL,
    EmbeddingService,
    get_embedder,
)


class _FakeST:
    """Dublê de SentenceTransformer: NÃO baixa nada, só guarda o nome do modelo."""

    last_name: str | None = None

    def __init__(self, name: str):
        self.name = name
        _FakeST.last_name = name

    def encode(self, texts, normalize_embeddings=True):  # pragma: no cover - não usado aqui
        import numpy as np

        return np.zeros((len(texts), EMBED_DIM), dtype="float32")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Cada teste começa com o singleton limpo e o SentenceTransformer dublado."""
    get_embedder.cache_clear()
    _FakeST.last_name = None
    # Intercepta o import tardio `from sentence_transformers import SentenceTransformer`.
    import types

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    yield
    get_embedder.cache_clear()


def _set_model(monkeypatch, value: str) -> None:
    """Troca settings.embedding_model_name. `settings` é um dataclass FROZEN, então
    substituímos a instância inteira por uma cópia (`dataclasses.replace`) — o mesmo
    objeto que `_resolve_model_name` lê via `from app.config import settings`."""
    import dataclasses

    import app.config as config

    monkeypatch.setattr(
        config, "settings", dataclasses.replace(config.settings, embedding_model_name=value)
    )


def test_default_vazio_usa_minilm_historico(monkeypatch):
    _set_model(monkeypatch, "")
    svc = get_embedder()
    assert isinstance(svc, EmbeddingService)
    # Força o load lazy (singleton) e confere o nome que chegou ao SentenceTransformer.
    svc._load()
    assert _FakeST.last_name == EMBED_MODEL == "all-MiniLM-L6-v2"


def test_resolve_model_name_vazio_cai_no_default(monkeypatch):
    _set_model(monkeypatch, "")
    assert emb._resolve_model_name() == EMBED_MODEL


def test_resolve_model_name_so_espacos_cai_no_default(monkeypatch):
    _set_model(monkeypatch, "   ")
    assert emb._resolve_model_name() == EMBED_MODEL


def test_flag_setada_usa_modelo_multilingue(monkeypatch):
    _set_model(monkeypatch, MULTILINGUAL_MODEL)
    svc = get_embedder()
    svc._load()
    assert _FakeST.last_name == MULTILINGUAL_MODEL
    assert "multilingual" in MULTILINGUAL_MODEL  # o recomendado p/ PT


def test_flag_setada_valor_arbitrario_eh_repassado(monkeypatch):
    _set_model(monkeypatch, "algum/outro-modelo-384d")
    assert emb._resolve_model_name() == "algum/outro-modelo-384d"
    get_embedder()._load()
    assert _FakeST.last_name == "algum/outro-modelo-384d"


def test_dimensao_alvo_continua_384():
    # O multilíngue recomendado também é 384d → NÃO muda a coluna vector(384).
    assert EMBED_DIM == 384


def test_construtor_direto_default_inalterado():
    # Instanciação direta (clustering/inline) NÃO depende da flag: default histórico.
    assert EmbeddingService()._model_name == EMBED_MODEL
