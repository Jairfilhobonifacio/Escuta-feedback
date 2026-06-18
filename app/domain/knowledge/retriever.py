"""KnowledgeBase — busca por similaridade no corpus (pgvector), com opção híbrida.

Recupera os trechos mais próximos da pergunta do contato, filtrando por
organização e por um piso de similaridade (groundedness): se nada passa do
piso, devolve lista vazia → o brain não tem contexto → cai no fallback honesto
("vou encaminhar ao time"), em vez de alucinar.

Por default a busca é PURAMENTE semântica (pgvector), igual desde sempre. Atrás
de `settings.rag_hybrid_enabled` (OFF por default) ela vira HÍBRIDA: soma à busca
semântica uma busca LEXICAL (ILIKE no texto dos chunks) e funde os dois conjuntos
por Reciprocal Rank Fusion (RRF). Isso melhora o recall em PORTUGUÊS enquanto o
embedding ainda é treinado em inglês (acha o chunk por palavra-chave mesmo quando
o vetor erra a nuance). A assinatura pública (`search`) NÃO muda — a hibridização
é interna; quem chama (resolver/brain) não percebe.

SQL cru de propósito: a coluna `embedding` é pgvector, fora do ORM (ver
app/models/knowledge.py). Postgres-only; os testes usam dublês.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings import EmbeddingService, to_pgvector

logger = logging.getLogger(__name__)

DEFAULT_K = 4
# Piso de similaridade de cosseno (0..1). MiniLM costuma dar ~0.4-0.7 em match
# bom de FAQ; abaixo de ~0.30 quase sempre é ruído. Conservador de propósito.
DEFAULT_MIN_SCORE = 0.30
# RRF: constante de amortecimento do rank (padrão da literatura). Quanto maior, mais
# plano o peso entre as primeiras posições; 60 é o valor canônico.
RRF_K = 60
# Híbrido: quantos candidatos puxar de CADA perna (semântica e lexical) antes de
# fundir e cortar em `k`. Um pouco mais que `k` para o RRF ter o que reordenar.
HYBRID_FETCH = 12


@dataclass
class RetrievedChunk:
    title: str
    content: str
    score: float


class KnowledgeBase:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID, embedder: EmbeddingService):
        self.session = session
        self.org_id = organization_id
        self.embedder = embedder

    async def search(
        self, query: str, k: int = DEFAULT_K, min_score: float = DEFAULT_MIN_SCORE
    ) -> list[RetrievedChunk]:
        """Trechos mais relevantes para `query` (semântica por default; híbrida se a
        flag estiver ON). Filtra pelo piso `min_score` e devolve no máx. `k`.

        Lê a flag por indireção (`_hybrid_enabled()`) para os testes alternarem o
        caminho via monkeypatch sem mexer no `settings` (que é frozen).
        """
        if _hybrid_enabled():
            return await self._search_hybrid(query, k, min_score)
        return await self._search_semantic(query, k, min_score)

    async def _search_semantic(
        self, query: str, k: int, min_score: float
    ) -> list[RetrievedChunk]:
        """Busca semântica pura (pgvector) — comportamento histórico, byte-a-byte."""
        qvec = to_pgvector(await self.embedder.embed_one(query))
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT title, content,
                           1 - (embedding <=> CAST(:q AS vector)) AS score
                    FROM knowledge_chunks
                    WHERE organization_id = :org AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:q AS vector)
                    LIMIT :k
                    """
                ),
                {"q": qvec, "org": str(self.org_id), "k": k},
            )
        ).all()
        return [
            RetrievedChunk(title=r.title, content=r.content, score=float(r.score))
            for r in rows
            if float(r.score) >= min_score
        ]

    async def _search_hybrid(
        self, query: str, k: int, min_score: float
    ) -> list[RetrievedChunk]:
        """Híbrido = semântica (pgvector) ∪ lexical (ILIKE), fundidos por RRF.

        Cada perna traz até HYBRID_FETCH candidatos JÁ ordenados (semântica por
        distância de cosseno; lexical por score de cosseno entre os matches textuais).
        Funde por id com RRF — um chunk que aparece bem colocado nas DUAS pernas
        sobe; lexical resgata chunks que o vetor (inglês) não pega em PT. O piso
        `min_score` continua valendo: descarta candidatos cujo MELHOR sinal semântico
        fica abaixo do piso (mantém o fallback honesto intacto). Devolve no máx. `k`.
        """
        qvec = to_pgvector(await self.embedder.embed_one(query))
        like = f"%{_escape_like(query.strip())}%"

        # Perna semântica: id + texto + score de cosseno, ordenado por distância.
        sem_rows = (
            await self.session.execute(
                text(
                    """
                    SELECT id, title, content,
                           1 - (embedding <=> CAST(:q AS vector)) AS score
                    FROM knowledge_chunks
                    WHERE organization_id = :org AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:q AS vector)
                    LIMIT :fetch
                    """
                ),
                {"q": qvec, "org": str(self.org_id), "fetch": HYBRID_FETCH},
            )
        ).all()

        # Perna lexical: chunks cujo título/conteúdo casa o termo (ILIKE, case-insensitive
        # e acento-sensível — limitação do ILIKE). Reaproveita o cosseno como score para
        # aplicar o mesmo piso; ordena por similaridade textual (ILIKE não ranqueia, então
        # ordenamos pelo próprio cosseno disponível, caindo no texto como desempate).
        lex_rows = (
            await self.session.execute(
                text(
                    """
                    SELECT id, title, content,
                           CASE WHEN embedding IS NULL THEN NULL
                                ELSE 1 - (embedding <=> CAST(:q AS vector)) END AS score
                    FROM knowledge_chunks
                    WHERE organization_id = :org
                      AND (content ILIKE :like ESCAPE '\\' OR title ILIKE :like ESCAPE '\\')
                    ORDER BY score DESC NULLS LAST
                    LIMIT :fetch
                    """
                ),
                {"q": qvec, "org": str(self.org_id), "like": like, "fetch": HYBRID_FETCH},
            )
        ).all()

        # Fusão RRF por id. Guarda, por chunk, o melhor score semântico visto (para o
        # piso) e os ranks em cada perna (para o RRF).
        fused: dict = {}
        for rank, r in enumerate(sem_rows):
            _fuse(fused, r, rank, "sem")
        for rank, r in enumerate(lex_rows):
            _fuse(fused, r, rank, "lex")

        ranked = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)
        out: list[RetrievedChunk] = []
        for e in ranked:
            # Piso de groundedness: só corta quem TEM sinal semântico abaixo do piso.
            # Match lexical de chunk sem embedding (score None) passa — o termo bateu
            # no texto, é relevante por construção (e o brain ainda valida a resposta).
            if e["score"] is not None and e["score"] < min_score:
                continue
            out.append(RetrievedChunk(title=e["title"], content=e["content"], score=e["score_out"]))
            if len(out) >= k:
                break
        return out


# --- helpers de hibridização -------------------------------------------------


def _hybrid_enabled() -> bool:
    """Lê a flag no momento da chamada (indireção testável). settings é frozen; os
    testes monkeypatcham ESTA função para alternar o caminho híbrido."""
    from app.config import settings

    return settings.rag_hybrid_enabled


def _escape_like(s: str) -> str:
    r"""Neutraliza os curingas do LIKE (%, _) e a barra no termo do usuário. A query
    usa `ILIKE :like ESCAPE '\'`, então dobramos a barra e prefixamos %/_ com \\."""
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _fuse(fused: dict, row, rank: int, leg: str) -> None:
    """Acumula uma linha de uma perna no dicionário de fusão (chave = id do chunk).

    - `rrf`: soma das contribuições 1/(RRF_K + rank) de cada perna onde o chunk apareceu.
    - `score`: melhor cosseno visto (para o piso `min_score`); None se nunca houve.
    - `score_out`: score reportado ao chamador (o cosseno quando há; senão 0.0).
    """
    key = row.id
    contrib = 1.0 / (RRF_K + rank)
    score = None if getattr(row, "score", None) is None else float(row.score)
    entry = fused.get(key)
    if entry is None:
        fused[key] = {
            "title": row.title,
            "content": row.content,
            "score": score,
            "score_out": score if score is not None else 0.0,
            "rrf": contrib,
        }
        return
    entry["rrf"] += contrib
    if score is not None and (entry["score"] is None or score > entry["score"]):
        entry["score"] = score
        entry["score_out"] = score
