"""RAG híbrido no KnowledgeBase (semântica ∪ lexical) — sem Supabase/pgvector.

Estratégia (mesma linha de test_clustering/test_rag_honest_fallback):
- A `AsyncSession` é dublada: `.execute()` inspeciona o SQL (`text()`) e devolve
  linhas canadas. Distingo a perna SEMÂNTICA da LEXICAL pela presença de `ILIKE`
  no statement. Zero pgvector, zero rede.
- O embedder é dublado (`embed_one` devolve vetor fixo) — não carrega MiniLM.
- A flag é alternada por monkeypatch de `retriever._hybrid_enabled` (settings é
  frozen; é o mesmo padrão de `_no_kb_fallback_enabled` do brain).

Invariantes provadas:
- OFF (default): roda SÓ a query semântica (1 execute), SEM ILIKE → comportamento atual.
- ON: une as duas pernas; um chunk que casa só no LÉXICO entra no resultado.
- ON: o piso `min_score` continua cortando candidato com cosseno fraco.
- ON: chunk presente nas DUAS pernas é fundido (não duplica) e sobe pelo RRF.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.knowledge import retriever as retr  # noqa: E402
from app.domain.knowledge.retriever import KnowledgeBase, RetrievedChunk  # noqa: E402


# --- dublês ------------------------------------------------------------------


class _Row:
    def __init__(self, **kw):
        self.__dict__.setdefault("id", uuid.uuid4())
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Sessão dublada: roteia por tipo de query (semântica vs lexical via ILIKE).

    `semantic_rows` / `lexical_rows` são o que cada perna retorna. Registra cada SQL
    executado em `self.statements` para asserts (quantas queries, se houve ILIKE).
    """

    def __init__(self, *, semantic_rows=None, lexical_rows=None):
        self.semantic_rows = semantic_rows or []
        self.lexical_rows = lexical_rows or []
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "ILIKE" in sql.upper():
            return _Result(self.lexical_rows)
        return _Result(self.semantic_rows)


class _FakeEmbedder:
    async def embed_one(self, text):
        return [0.1] * 8  # vetor fixo curto; o pgvector é dublado, dim não importa


def _kb(session) -> KnowledgeBase:
    return KnowledgeBase(session, uuid.uuid4(), _FakeEmbedder())


# --- OFF: comportamento atual (só semântica) ---------------------------------


@pytest.mark.asyncio
async def test_off_so_semantica_uma_query_sem_ilike(monkeypatch):
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: False)
    rows = [
        _Row(title="Planos", content="plano mensal e anual", score=0.80),
        _Row(title="Garantia", content="7 dias", score=0.55),
    ]
    sess = _FakeSession(semantic_rows=rows)
    out = await _kb(sess).search("planos?", k=4, min_score=0.30)

    assert [c.title for c in out] == ["Planos", "Garantia"]
    assert all(isinstance(c, RetrievedChunk) for c in out)
    # Exatamente UMA query e NENHUM ILIKE → caminho histórico intacto.
    assert len(sess.statements) == 1
    assert "ILIKE" not in sess.statements[0].upper()


@pytest.mark.asyncio
async def test_off_aplica_piso_min_score(monkeypatch):
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: False)
    rows = [
        _Row(title="Bom", content="relevante", score=0.62),
        _Row(title="Fraco", content="ruído", score=0.10),  # abaixo do piso 0.30
    ]
    sess = _FakeSession(semantic_rows=rows)
    out = await _kb(sess).search("x", k=4, min_score=0.30)
    assert [c.title for c in out] == ["Bom"]


# --- ON: híbrido (semântica ∪ lexical) ---------------------------------------


@pytest.mark.asyncio
async def test_on_inclui_match_so_lexical(monkeypatch):
    """Chunk que o vetor NÃO trouxe, mas o termo bate no texto (ILIKE), entra."""
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: True)
    semantic = [_Row(title="Outro", content="assunto diferente", score=0.40)]
    # Lexical traz um chunk com bom cosseno que a perna semântica (top-k) não listou.
    lex_id = uuid.uuid4()
    lexical = [_Row(id=lex_id, title="Boleto", content="como pagar por boleto", score=0.45)]
    sess = _FakeSession(semantic_rows=semantic, lexical_rows=lexical)

    out = await _kb(sess).search("boleto", k=4, min_score=0.30)
    titles = {c.title for c in out}
    assert "Boleto" in titles          # resgatado pela perna lexical
    assert "Outro" in titles           # semântica preservada
    # Duas pernas → duas queries; a 2ª usa ILIKE.
    assert len(sess.statements) == 2
    assert any("ILIKE" in s.upper() for s in sess.statements)


@pytest.mark.asyncio
async def test_on_fusao_dedup_por_id_e_sobe_no_rrf(monkeypatch):
    """Chunk nas DUAS pernas não duplica e fica à frente de um que está em só uma."""
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: True)
    shared = uuid.uuid4()
    other = uuid.uuid4()
    # 'Comum' aparece bem nas duas pernas; 'SoSemantica' só na semântica (rank pior).
    semantic = [
        _Row(id=other, title="SoSemantica", content="só no vetor", score=0.50),
        _Row(id=shared, title="Comum", content="está nos dois", score=0.50),
    ]
    lexical = [
        _Row(id=shared, title="Comum", content="está nos dois", score=0.50),
    ]
    sess = _FakeSession(semantic_rows=semantic, lexical_rows=lexical)

    out = await _kb(sess).search("comum", k=4, min_score=0.30)
    titles = [c.title for c in out]
    assert titles.count("Comum") == 1          # dedupe por id (não duplica)
    assert set(titles) == {"Comum", "SoSemantica"}
    assert titles[0] == "Comum"                # nas duas pernas ⇒ RRF maior ⇒ primeiro


@pytest.mark.asyncio
async def test_on_aplica_piso_min_score_em_chunk_com_embedding(monkeypatch):
    """Candidato com cosseno abaixo do piso é cortado mesmo na busca híbrida."""
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: True)
    semantic = [_Row(title="Forte", content="muito relevante", score=0.70)]
    lexical = [_Row(title="FracoLex", content="bate o termo mas cosseno baixo", score=0.05)]
    sess = _FakeSession(semantic_rows=semantic, lexical_rows=lexical)

    out = await _kb(sess).search("relevante", k=4, min_score=0.30)
    titles = {c.title for c in out}
    assert "Forte" in titles
    assert "FracoLex" not in titles  # cosseno 0.05 < piso 0.30 → cortado


@pytest.mark.asyncio
async def test_on_match_lexical_sem_embedding_passa_o_piso(monkeypatch):
    """Chunk sem embedding (score None) casado só por texto NÃO é cortado pelo piso
    (o termo bateu no conteúdo — é relevante por construção)."""
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: True)
    semantic = []  # nada veio do vetor
    lexical = [_Row(title="SemVetor", content="contém o termo exato", score=None)]
    sess = _FakeSession(semantic_rows=semantic, lexical_rows=lexical)

    out = await _kb(sess).search("termo", k=4, min_score=0.30)
    assert [c.title for c in out] == ["SemVetor"]
    assert out[0].score == 0.0  # sem cosseno → score reportado 0.0


@pytest.mark.asyncio
async def test_on_respeita_k(monkeypatch):
    monkeypatch.setattr(retr, "_hybrid_enabled", lambda: True)
    semantic = [_Row(title=f"S{i}", content="c", score=0.9 - i * 0.05) for i in range(6)]
    sess = _FakeSession(semantic_rows=semantic, lexical_rows=[])
    out = await _kb(sess).search("q", k=3, min_score=0.30)
    assert len(out) == 3


# --- a flag liga/desliga pelo settings (indireção real) ----------------------


def test_hybrid_enabled_le_settings(monkeypatch):
    # `settings` é frozen → troca a instância por uma cópia (dataclasses.replace).
    import dataclasses

    import app.config as config

    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, rag_hybrid_enabled=True))
    assert retr._hybrid_enabled() is True
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, rag_hybrid_enabled=False))
    assert retr._hybrid_enabled() is False


def test_escape_like_neutraliza_curingas():
    assert retr._escape_like("100%") == r"100\%"
    assert retr._escape_like("a_b") == r"a\_b"
    assert retr._escape_like("c\\d") == "c\\\\d"
