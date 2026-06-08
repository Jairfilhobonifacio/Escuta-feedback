"""Quebra de documentos markdown do corpus em chunks recuperáveis.

Lógica pura (sem I/O) — fácil de testar. Cada arquivo do corpus tem um
frontmatter YAML simples (title/source/tags) e seções `## Heading`. Cada
seção vira um chunk autossuficiente: título = "<doc title> — <heading>",
conteúdo = o texto da seção. Seções muito longas são fatiadas por parágrafo
respeitando um teto de caracteres.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_CHARS = 1200  # teto por chunk (~300 tokens); seções maiores são fatiadas


@dataclass
class Chunk:
    title: str
    content: str
    tags: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extrai um frontmatter YAML mínimo (k: v e listas inline [a, b]). Sem PyYAML."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
        else:
            meta[key] = val.strip("'\"")
    return meta, body


def _split_long(title: str, body: str, tags: list[str]) -> list[Chunk]:
    """Fatia um corpo grande por parágrafos, agrupando até MAX_CHARS."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[Chunk] = []
    buf: list[str] = []
    size = 0
    for p in paras:
        if size + len(p) > MAX_CHARS and buf:
            chunks.append(Chunk(title=title, content="\n\n".join(buf), tags=tags))
            buf, size = [], 0
        buf.append(p)
        size += len(p) + 2
    if buf:
        chunks.append(Chunk(title=title, content="\n\n".join(buf), tags=tags))
    return chunks


def chunk_markdown(text: str) -> list[Chunk]:
    """Documento markdown → lista de chunks (1 por seção '## ', fatiando longas)."""
    meta, body = _parse_frontmatter(text)
    doc_title = meta.get("title") or "Bizzu"
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []

    # Quebra por headings de nível 2. O texto antes do 1º '## ' (intro) vira
    # uma seção própria se tiver conteúdo.
    parts = re.split(r"(?m)^##\s+(.+)$", body)
    chunks: list[Chunk] = []

    intro = parts[0].strip()
    if intro:
        chunks.extend(_split_long(doc_title, intro, tags))

    # parts: [intro, head1, body1, head2, body2, ...]
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        section_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not section_body:
            continue
        title = f"{doc_title} — {heading}"
        chunks.extend(_split_long(title, section_body, tags))

    return chunks
