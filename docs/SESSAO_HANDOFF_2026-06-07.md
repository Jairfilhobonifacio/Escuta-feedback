# Handoff de Sessão — 07/06/2026 (atualizado à noite)

> Sessões Claude Code: madrugada `21352788-...` (E2E NPS + painel + exploração) e
> tarde/noite `325c6b65-cd60-449e-813c-014659fd7bb3` (gancho de churn E2E + opt-in + sync).
> Projeto: **Escuta** (`~/Documents/Projetos/escuta`) + stack local da **Bizzu**
> (`~/Documents/Projetos/bizzu-repos`).

## 🏆 Estado: PoC churn→WhatsApp COMPLETO E VALIDADO E2E (zero mock)

```
POST /user/subscription/cancel (API Bizzu 3100, JWT real)
  → finishCancel → EscutaService.captureForUser('subscription_cancelled')
  → POST /api/events/bizzu (HMAC-SHA256 ✓, idempotente, cooldown 7d, opt-in ✓)
  → survey 'Exit Bizzu' → WAHA → WhatsApp real
  → resposta do usuário ("Cagada ?") → closed no Supabase (21:20:47 → 21:26:54)
```

## ✅ Feito nesta sessão (noite)

### 1. API Bizzu local NO AR (novela das envs ENCERRADA, 6ª tentativa)
- `DATABASE_SYNCHRONIZE=false` no `.env` (true fazia o Sequelize tentar `ALTER` de
  enum `enum_users_role→enum_usuarios_role` e crashar; migrations já aplicadas).
- **Pegadinha Podman pós-reboot**: forward de portas publicadas como `0.0.0.0`
  ficou IPv6-only (`[::1]` apenas) → `127.0.0.1` morto (ioredis ECONNREFUSED;
  Sequelize só conectava porque `localhost` resolve `::1` primeiro no Node).
  **Fix definitivo**: containers `bizzu-postgres`/`bizzu-redis` RECRIADOS com
  `-p 127.0.0.1:<porta>:<porta>` reaproveitando os MESMOS volumes (dados intactos).
- `GEMINI_API_KEY=dev-local-placeholder` (SDK lança com chave vazia no boot).

### 2. Gancho de churn (Escuta) — commit `0953558`
- `POST /api/events/bizzu` (`app/api/events.py`): HMAC do corpo cru
  (`hmac(secret, f"{ts}.{body}")`, headers `X-Escuta-Timestamp/Signature`,
  tolerância 5min), idempotência por event_id (`SurveyRun.trigger =
  bizzu:<event>:<event_id>`), cooldown 7d por contato+survey, opt-in do emissor
  (eleva, nunca rebaixa), respostas 202 `{dispatched, reason}`.
- Survey type **'exit'**: 1ª pergunta `kind='open'`, nasce `awaiting_reason` →
  resposta fecha (zero mudança na logic). `thanks` custom via `kind='thanks'`.
- `surveys.trigger_event` (migration `20260607_trigger_event` APLICADA no Supabase).
- Seed: survey 'Exit Bizzu' (`trigger_event='subscription_cancelled'`) criada.
- `.env` ganhou `BIZZU_WEBHOOK_SECRET` (compartilhado com o lado Bizzu).
- **Testes 36/36** (14 novos em `tests/test_events_bizzu.py`).

### 3. Lado Bizzu (NÃO commitado lá — patches em `docs/patches/`)
- `src/escuta/{escuta.module.ts,escuta.service.ts}`: @Global, espelho do
  TrackingModule; `captureForUser` fire-and-forget, no-op sem envs.
- Ganchos nos 3 cancelamentos: `webhook.service.ts`, `subscription.service.ts#finishCancel`,
  `asaas-overdue-cancellation.service.ts`. `event_id = sub:<externalSubscriptionId|id>`.
- **whatsappOptIn dedicado**: migration `20260607130000` (APLICADA local) +
  model + SignupDto + auth.service (carimbo `whatsappOptInAt`; exige telefone) +
  checkbox condicional no `Signup.jsx` (frontend) + EscutaService usa o campo.
- Specs deles: payments 27/27 + auth 21/21 (construtores posicionais atualizados).
- `.env` deles ganhou `ESCUTA_API_URL` + `ESCUTA_WEBHOOK_SECRET`.
- Patches: `bizzu-backend-escuta-churn-hook.patch` (485 linhas) +
  `bizzu-frontend-whatsapp-opt-in.patch` (45 linhas).

### 4. Sync de contatos — `scripts/sync_bizzu_contacts.py`
Upsert 1-sentido (Bizzu→Escuta) de usuários com telefone+whatsappOptIn:
cria/eleva opt_in/preenche `bizzu_user_id`. Idempotente, `--dry-run`. Rodado:
contato do Jair vinculado ao user da Bizzu.

## 🗺️ Stack local (tudo NO AR ao fim da sessão)
| Porta | Serviço | Como religar |
|---|---|---|
| 3000 | WAHA (`podman start waha`; sessão WhatsApp persiste) | start + `POST /api/sessions/default/start` se STOPPED |
| 3001 | Painel Escuta | `cd escuta/frontend && NODE_OPTIONS=--use-system-ca npm run dev` |
| 3100 | API Bizzu | `cd bizzu-repos/backend && export NODE_ENV=development NODE_OPTIONS=--use-system-ca && node_modules/.bin/nest start --watch` |
| 5173 | Frontend Bizzu | `cd bizzu-repos/frontend && NODE_OPTIONS=--use-system-ca npm run dev` |
| 5432/6379 | bizzu-postgres / bizzu-redis (binding 127.0.0.1 explícito) | `podman start bizzu-postgres bizzu-redis` |
| 8000 | API Escuta (matar órfãos antes! `netstat -ano \| grep :8000`) | `set -a && source .env && set +a && export SELF_CHAT_TEST=1 && py -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |

Dados de teste no postgres Bizzu local: user `jair.e2e@escuta.test` (senha
`SenhaForte!2026`, whatsappOptIn=t), plano 'Mensal Teste E2E Escuta', assinatura
CANCELLED (a do E2E). Usuário fictício `optin.e2e` REMOVIDO (sem-mock).

## ✅ Rodada de 4 agentes paralelos (noite, commit `47297b7`)
1. **Toggle MinhaConta** — PATCH /user/me; carimbo só OFF→ON; 58/58; validado ao vivo
2. **Gancho topic_completed** — 4 caminhos do plano-estudo-ia + goal_completed; 275/275
3. **Survey CSAT Tópico** — NPS 0-10, trigger topic_completed, no Supabase; smoke
   E2E real ENTREGUE no WhatsApp (vigia aguardando resposta do user)
4. **Dashboard segmentado** — KPIs NPS puros + bloco exit c/ motivos + badges; 40/40

## ⏭️ Próximos passos (ordem sugerida)
1. **Rotação WAHA** (credenciais novas JÁ em `~/.secrets/waha_*.txt`; troca do
   container precisa de OK explícito do user — receita: rm -f waha + run com
   mesma config/volume e WAHA_API_KEY/WAHA_DASHBOARD_PASSWORD novos + atualizar
   WAHA_API_KEY no .env do escuta + restart 8000 + smoke de envio)
2. Espelho do NPS in-app 🥉 (`nps.service.ts:101` → `nps_submitted`; exige modo
   "ingest sem disparo" no Escuta)
3. radar-editais → aviso de edital novo (canal de valor)
4. Remote do git do Escuta (gh CLI não instalado — decidir conta/nome/visibilidade)
5. Propor PR dos 2 patches ao time da Bizzu (org gabarita-ai) — 1017+127 linhas
6. Backend Bizzu: desligar optIn se telefone removido sem mencionar o campo (anotado)
7. Fase 1 do produto: clusters/digest/agente IA

## 🔑 Refs rápidas
- WAHA: `localhost:3000`, key `c08468a7d78b4ee1acaf9fb51d775786` (⚠️ rotacionar)
- Postgres Bizzu local: `postgres`/`bizzu_dev_2026` @ localhost:5432/plataforma
- Supabase Escuta: ref `nlqeargxkidygbrahkbk` (PAT em `~\.secrets\supabase_pat_escuta.txt`)
- WhatsApp pareado: 5524998365809 (Jair), self-chat com `SELF_CHAT_TEST=1` (NUNCA em prod)
- Segredo HMAC Bizzu↔Escuta: nos `.env` dos dois lados (`BIZZU_WEBHOOK_SECRET` / `ESCUTA_WEBHOOK_SECRET`)
