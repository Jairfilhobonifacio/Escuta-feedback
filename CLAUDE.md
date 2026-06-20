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

## 🔭 Backlog ativo + perguntas em aberto (2026-06-20)
**Leia `docs/FEEDBACK_DONO_2026-06-20.md`** — backlog completo do feedback do dono (com as 4 imagens e
minhas ideias por item). Estado: reforma "terminar e simplificar" feita (3 commits na `master`); base
limpa (grupos + conversa-lixo removidos); stack no ar. **Repo ainda SEM remote** → subir para repositório
novo (decidir host/nome; `gh` não está instalado nesta máquina).

**Perguntas/decisões em aberto (o dono quer retomar por aqui):**
1. **Por onde começar as melhorias?** Ordem sugerida: P0 bugs (selos bugado + ficha do contato quebrada)
   → P1 design (Clientes WhatsApp/e-mail/abordados · Board "Trello de verdade" · Pesquisas redesign) →
   P1 dados (timeline com assinatura + **status customizáveis**) → P2 (tipos/origem · "Temas"→"Mapeamento"
   · apagar dados pela UI · monitoramento inteligente) → pesquisa de benchmark de CS.
2. **Deploy:** subir API FastAPI no **Modal** + front no **Vercel**; o gargalo é o **WAHA** (stateful,
   não serverless → precisa VPS/Docker host) + secrets + HOOK_URL público. Detalhe no FEEDBACK_DONO.
3. **Repositório novo:** criar (privado, por conter dados de cliente) e dar `git push` dos 3 commits.
