# Handoff de Sessão — 09/06/2026

> Projeto **Escuta** (retenção) + frente de **aquisição** (`bizzu_midia`). Jair = sócio de growth da
> Bizzu, 2 frentes. Continuação do `SESSAO_HANDOFF_2026-06-08.md`. Sessão longa de Claude Code.

## 🟢 Estado atual
- **Integração de RETENÇÃO fechada (código):** API de Clientes → 13 perfis → survey por perfil →
  `dispatch_by_profile` (dry-run). **Suíte 112 testes verde.** Sem disparo automático/real.
- **Aquisição (`bizzu_midia`):** clonado e destravado (deps instaladas).
- **Mega-contexto p/ Claude.ai Projects:** pacote pronto (`_context-pack/BIZZU_ESCUTA_CONTEXT_PACK.md`).

## ✅ O que foi construído (09/06)
**Retenção (Escuta):**
- `app/integrations/bizzu_partner.py` — cliente da API de Clientes (GET, X-API-Key).
- `app/domain/segmentation/profiles.py` — 13 perfis (`classify_profile`) · `profile_surveys.py` — mapa perfil→survey.
- `scripts/sync_partner_customers.py` — sync + classificação (`--dry-run`).
- `scripts/dispatch_by_profile.py` — `plan` (dry-run) / `dispatch --profile --force` (cooldown 7d, opt-in).
- `scripts/seed_bizzu.py` — +4 surveys (CSAT Onboarding, Escuta de Detrator, Retenção, Indicação).
- Testes: `test_partner_profiles.py` (40) + `test_profile_surveys.py` (6); suíte total **112 verde**.
**Docs/contexto:** `MISSAO_JAIR.md`, `INTEGRACAO_FEEDBACK.md`, `analise-bizzu/{api-clientes-partner, feedback-nativo, bizzu-midia}.md`, `TRELLO_BOARD.md`, `_context-pack/*`. Skills: `bizzu-escuta`, `escuta-stack`, `escuta-handoff`, `bizzu-context-pack`.
**Aquisição:** `bizzu_midia` clonado + `npm install` ok; `.env` posicionado.

## 🟡 Onde paramos / próximos passos
**Operar a retenção (com o Felipe — popula PII no banco do Escuta):**
1. `py scripts/seed_bizzu.py` — cria as 6 surveys no banco.
2. `py scripts/sync_partner_customers.py` (sem `--dry-run`) — cria/classifica os 233 contatos (**PII**).
3. `py scripts/dispatch_by_profile.py plan` — ver o plano (perfil→survey→nº elegíveis, não envia).
4. `... dispatch --profile <perfil> --limit 1 --force` — **teste Jair↔Felipe** antes de qualquer cliente.
5. Coordenar **double-touch de churn** (winback e-mail + WhatsApp) com o Felipe.
**Aquisição:** benchmark de concorrentes (Chrome ou pós-reset) → 3 templates base; ler brand-guidelines; avatar; homologar app Meta.
**Setup:** trocar `GEMINI_API_KEY` pela própria; acessos (Instagram/Telegram); confirmar preço (R$20/120); colar os cards do `TRELLO_BOARD.md`.

## 🔧 Como religar a stack
Ver skill **`escuta-stack`** (8000/3001/3000 + Podman). Não duplicar comandos aqui.

## ⚠️ Pegadinhas (novas desta sessão)
- `dispatch_by_profile`: `plan` = dry-run (não envia, sem PII); `dispatch` exige `--force` no WAHA `:3000`.
- O **sync real popula PII** (233 clientes) no banco do Escuta — fazer conscientemente, com o Felipe.
- `bizzu_midia`: 1 teste pré-existente falha (`extractArticleText` em `scraper.test.js`) — não bloqueia.

## 🔑 Refs rápidas
- API de Clientes: env `BIZZU_PARTNER_API_KEY` (no `.env`, segredo) — `https://api.bizzu.ai/partner/customers` (233).
- Distribuição: 100 silenciosos · 34 vai_expirar · 33 promotores · 27 churn_rapido · 11 passivo/outro · 6 involuntário · 5 detrator.
- Docs canônicos: `INTEGRACAO_FEEDBACK.md` (retenção), `MISSAO_JAIR.md` (missão), `api-clientes-partner.md` (perfis), `bizzu-midia.md` (aquisição).
