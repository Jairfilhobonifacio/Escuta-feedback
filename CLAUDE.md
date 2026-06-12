# CLAUDE.md — Projeto Escuta (× Bizzu)

> **Antes de qualquer coisa, leia `docs/BIZZU_ESCUTA_MASTER.md`.** É o briefing único e auto-contido
> de todo o ecossistema (Bizzu = 6 repos + Escuta + integração + estado + como retomar). Tudo o que
> você precisa para agir como braço direito do usuário neste projeto está lá.

## O que é este projeto
**Escuta** — Central de Voz do Cliente no WhatsApp (FastAPI + Supabase/pgvector + WAHA + painel Next.js,
LLM via Groq). Cliente-piloto: **Bizzu** (edtech de concursos, org GitHub `gabarita-ai`). Os 6 repos da
Bizzu estão clonados em `../bizzu-repos/` **para leitura** (gerar patches, não commitar).

## Regras de ouro
1. **Bizzu = leitura.** Mudanças no lado Bizzu viram `.patch` em `docs/patches/` — nunca commit nos clones.
2. **Escuta = onde construímos.** Aqui se escreve código de verdade.
3. **Segredos:** referencie por caminho (`~/.secrets/...`) e nome de env; nunca cole valores em arquivo
   versionável. NÃO desabilite verificação TLS — a máquina usa `truststore.inject_into_ssl()` (trust
   store do sistema), que já está no `app/main.py`.
4. **WhatsApp real só com OK do usuário** (WAHA viola ToS; risco de ban).
5. **Banco:** `DATABASE_SYNCHRONIZE=false` no NestJS local; matar `py.exe` órfão antes de subir a 8000.

## Atalhos (skills, a partir de `Documents/Projetos`)
- `/bizzu-escuta` — carrega todo o contexto e entra em modo braço-direito.
- `/escuta-stack` — sobe/religa/checa a stack local (8000 / 3001 / 3000 + Podman).
- `/escuta-handoff` — lê o último handoff (onde paramos) ou gera um novo ao fim da sessão.

## Docs canônicos (em `docs/`)
`BIZZU_ESCUTA_MASTER.md` (mestre) · `CONTEXTO_BIZZU.md` (ecossistema) · `INTEGRACAO_BIZZU.md`
(integração) · `analise-bizzu/*.md` (por repo) · `corpus_bizzu/*.md` (RAG) · `SESSAO_HANDOFF_*.md`
(estado mais recente) · `PRD_FASE0.md` (gênese do tracer bullet).
