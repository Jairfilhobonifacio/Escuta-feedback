# Handoff de Sessão — 08/06/2026

> Projeto **Escuta** (`C:\Users\jboni\Documents\Projetos\escuta`) — Central de Voz do
> Cliente no WhatsApp. Cliente-piloto: **Bizzu** (edtech de concursos, org GitHub `gabarita-ai`).
> Stack local da Bizzu em `C:\Users\jboni\Documents\Projetos\bizzu-repos` (6 repos clonados).
> Continuação do `SESSAO_HANDOFF_2026-06-07.md`. Sessão Claude: `325c6b65-...`.

---

## 🟢 Estado atual (tudo no ar)

| Serviço | Porta | Estado |
|---|---|---|
| API Escuta (FastAPI) | 8000 | no ar, **IA + RAG + digest ativos** |
| Painel Escuta (Next.js) | 3001 | no ar (badges de sentimento/temas) |
| WAHA (WhatsApp) | 3000 | no ar, sessão **WORKING** (número Jair 5524998365809) |
| API Bizzu (NestJS) local | 3100 | (pode estar fora — religar se for testar integração) |
| Frontend Bizzu (Vite) | 5173 | (deixado fora; religar só se for testar UI) |
| Containers Podman | — | waha + bizzu-postgres + bizzu-redis UP |

**Git limpo** no commit `6004166`. Branch sem remote ainda.

---

## ✅ O que foi construído (esta leva, commits em ordem)

`0953558` → `f20257f` → `47297b7` → `15568d8` → `acacbbe` → `2fe982b` → `6cb57f7` → `990908b` → `d926534` → `6004166`

### As 4 camadas de IA (todas no ar, com fallback determinístico total)
1. **SurveyBrain** (`app/domain/survey/brain.py`, Groq): resposta natural vira nota; opt-out desliga contato; pergunta é respondida; feedback classificado.
2. **Classificação**: `classify_feedback` → `sentiment`/`themes`/`urgency` em `survey_responses` (migration `20260607_ai_fields`).
3. **RAG** (`app/domain/knowledge/` + `brain.answer_from_context`): pergunta do contato → busca corpus (pgvector, embeddings locais MiniLM offline) → resposta grounded com **gating duplo** (similaridade + LLM recusa se não cobre). Corpus em `docs/corpus_bizzu/` (33 chunks). Re-ingerir: `py scripts/ingest_knowledge.py`.
4. **Digest semanal** (`app/domain/digest/`): conta a semana (NPS+delta, temas, urgências, churn) → LLM narra → WhatsApp do dono (`org.settings.owner_phone`). Script `scripts/send_digest.py --send`; endpoints `GET /api/digest/preview` + `POST /api/digest/run` (pronto p/ cron).

### Integração Escuta ↔ Bizzu (camadas anteriores, patches em `docs/patches/`)
- `EscutaService` (NestJS) → `POST /api/events/bizzu` (HMAC). Ganchos: `subscription_cancelled` (3 caminhos), `topic_completed`/`goal_completed`. Opt-in WhatsApp dedicado (Signup + MinhaConta).

### Análise profunda dos 6 repos Bizzu (commit `6004166`)
- 6 relatórios em `docs/analise-bizzu/*.md` (~15.700 palavras, com arquivo:linha)
- **Síntese: `docs/CONTEXTO_BIZZU.md`** ← leitura canônica do ecossistema

### Qualidade
- **66 testes** Escuta (`py -m pytest tests/ -q`) + **12** harness E2E (`py scripts/smoke_all.py`) + **191** specs Bizzu — todos verdes.

---

## 🟡 ONDE PARAMOS / próximos passos (priorizados)

### Decisões que dependem do usuário
1. **Rotação WAHA** (credenciais novas JÁ geradas em `~/.secrets/waha_api_key.txt` + `waha_dashboard_pass.txt`) — bloqueada pelo classificador, precisa "pode rotacionar". Receita: recriar container `waha` (mesmo volume `waha_sessions`, HOOK `http://172.31.176.1:8000/api/webhook/waha`, `WHATSAPP_HOOK_EVENTS=message.any`, WEBJS) com as novas key/senha + atualizar `WAHA_API_KEY` no `.env` + restart 8000 + smoke.
2. **Remote do git** — `gh` CLI não instalado. Decidir conta/nome/visibilidade (instalar `gh` + `gh auth login`, ou criar repo e passar URL).
3. **Teste NPS interativo** ainda aberto no WhatsApp do Jair (24h) — responder com pergunta/nota em texto p/ ver cérebro+RAG ao vivo.

### Backlog técnico (do `CONTEXTO_BIZZU.md`, priorizado)
4. ⚠️ **Coordenar double-touch de churn**: Bizzu já manda email winback + Escuta manda exit survey no MESMO cancelamento. Definir cadência/ownership.
5. 🐛 **`reason` hardcoded** `webhook.service.ts:207` (=PAYMENT_FAILED sempre) suja o motivo de churn voluntário — corrigir no patch Bizzu.
6. 🔇 Adicionar `ESCUTA_API_URL`/`ESCUTA_WEBHOOK_SECRET` ao `.env.example` do backend Bizzu (hoje no-op silencioso sem eles).
7. 🥉 **Espelhar NPS in-app** (`nps.service.ts:101` → evento `nps_submitted`) — exige modo "ingest sem disparo" no Escuta (registrar resposta vinda de outro canal, sem mandar WhatsApp).
8. **Radar → "saiu seu edital" no WhatsApp** (`radar-editais/pipeline.py:297-327`, <50 linhas).
9. **Captura WhatsApp na captação** (site hero/`/editais/[slug]`/`/exemplo` + landings Google Forms).
10. `scripts/backfill_ai_tags.py` (reclassificar responses históricas sem sentiment).
11. **Agendar o digest** (cron Modal/n8n → `POST /api/digest/run`, semanal).
12. **Clusters de temas** (já temos `themes` por resposta → agrupar tendências).
13. Propor os **3 patches** à gabarita-ai (PR nos repos deles) quando o piloto for aprovado.
14. **Infra**: módulo `escuta-ec2` (clonar `modules/radar-editais-ec2/`, `escuta.bizzu.ai`, ~$12-16/mês) quando sair do localhost.

---

## 🔧 Como religar a stack (se a máquina reiniciou)

```bash
# Containers (restart=unless-stopped, devem voltar sozinhos)
podman start waha bizzu-postgres bizzu-redis
# Se a sessão WhatsApp cair: POST /api/sessions/default/start (header X-Api-Key)
# Se o gateway WSL mudar de IP (dinâmico!): podman machine ssh "ip route" e recriar o HOOK_URL

# API Escuta (8000) — ANTES: matar órfãos (netstat -ano | grep :8000 → taskkill //F //PID)
cd ~/Documents/Projetos/escuta
export PYTHONUTF8=1 HF_HUB_OFFLINE=1 && set -a && source .env && set +a && export SELF_CHAT_TEST=1
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning

# Painel Escuta (3001)
cd ~/Documents/Projetos/escuta/frontend && NODE_OPTIONS=--use-system-ca npm run dev

# (opcional) API Bizzu (3100) — DATABASE_SYNCHRONIZE=false no .env!
cd ~/Documents/Projetos/bizzu-repos/backend
export NODE_ENV=development NODE_OPTIONS=--use-system-ca && node_modules/.bin/nest start --watch
```

---

## ⚠️ Pegadinhas desta máquina (custaram tempo)
- **TLS interceptado pelo antivírus**: chamadas HTTPS externas (Groq, GitHub API) falham com `CERTIFICATE_VERIFY_FAILED`. Solução: `truststore.inject_into_ssl()` no topo (já está no `app/main.py` e nos scripts que chamam a Groq).
- **Embeddings offline**: `HF_HUB_OFFLINE=1` + modelo `all-MiniLM-L6-v2` precisa estar no cache HF (está, herdado do Nexus/Pulse). 1ª busca carrega o modelo (~1-2s, lazy).
- **Chave Groq**: `/models` dá **403** (escopo), mas `/chat/completions` funciona — testar com chamada real, não com `/models`. Chave reusada do voz-control.
- **Podman pós-reboot**: forward de porta `0.0.0.0` pode virar IPv6-only → recriar container com `-p 127.0.0.1:<porta>:<porta>`. `DATABASE_SYNCHRONIZE=true` crasha o boot do NestJS (ALTER de enum) → `false`.
- **Windows**: TaskStop deixa `py.exe` órfão segurando a 8000 (double-bind silencioso) → matar PIDs antes de subir.

---

## 🔑 Refs rápidas
- **Supabase Escuta**: ref `nlqeargxkidygbrahkbk` (sa-east-1); PAT em `~\.secrets\supabase_pat_escuta.txt`. 5 tabelas (+ pgvector). `db push` não usado — alembic.
- **WAHA**: `localhost:3000`, key atual `‹redigido — ver ~/.secrets/waha_api_key.txt›` (⚠️ rotacionar; novas em `~/.secrets/waha_*.txt`).
- **Groq**: `.env` `GROQ_API_KEY` + `GROQ_MODEL=llama-3.3-70b-versatile`. `LLM_ENABLED=1`.
- **Bizzu local**: postgres `postgres`/`‹redigido — ver ~/.secrets/waha_api_key.txt›` @ localhost:5432/plataforma. Usuário teste `jair.e2e@escuta.test`/`‹redigido — ver ~/.secrets/waha_api_key.txt›`.
- **HMAC Bizzu↔Escuta**: `BIZZU_WEBHOOK_SECRET` (.env Escuta) = `ESCUTA_WEBHOOK_SECRET` (.env backend Bizzu).
- **Docs canônicos**: `docs/CONTEXTO_BIZZU.md` (ecossistema) · `docs/INTEGRACAO_BIZZU.md` (integração) · `docs/analise-bizzu/*.md` (por repo) · `docs/corpus_bizzu/*.md` (RAG).

---

## 🧭 Sugestão de retomada
Comece relendo `docs/CONTEXTO_BIZZU.md` (visão) + este handoff (estado). O ganho mais barato e seguro é o **🥉 espelho do NPS in-app** (não mexe em infra viva); o risco mais urgente é o **double-touch de churn** (decisão de produto). Tudo o que toca WhatsApp real espera o teste interativo e/ou a rotação WAHA.
