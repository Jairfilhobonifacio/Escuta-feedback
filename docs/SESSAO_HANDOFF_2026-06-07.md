# Handoff de Sessão — 07/06/2026 (madrugada)

> Sessão Claude Code `21352788-4d04-488e-a73a-29faf92a27af` (retomar: `claude --resume 21352788-4d04-488e-a73a-29faf92a27af`).
> Projeto: **Escuta** (`~/Documents/Projetos/escuta`) + stack local da **Bizzu** (`~/Documents/Projetos/bizzu-repos`).

## ✅ O que foi CONCLUÍDO nesta sessão

### 1. Funil NPS validado E2E 100% REAL 🏆
WhatsApp do Jair (self-chat) → WAHA (Podman) → webhook FastAPI → Supabase → resposta automática.
Resultado no banco: `closed, score=9, bucket=promoter, text='cagada'`.
**5 bugs de integração corrigidos no caminho** (nenhum aparecia com mock):
1. uvicorn bindava `127.0.0.1` → `--host 0.0.0.0`
2. `host.containers.internal` do Podman QUEBRADO → `WHATSAPP_HOOK_URL=http://172.31.176.1:8000/...` (IP do gateway WSL; ⚠️ **dinâmico** — se webhook falhar após reboot: `podman machine ssh "ip route"` e recriar container)
3. WEBJS devolve `id` como dict → normalizado `_serialized` no dispatcher
4. Self-chat usa **LID** (`from=...@c.us` / `to=...@lid`, MESMO número) → `resolve_lid` + `_LID_CACHE` + `self_check_to`
5. **O vilão:** parser só aceitava `event=="message"`; o real é `message.any` → whitelist corrigida
- Modo `SELF_CHAT_TEST=1` (supressão de eco; **NUNCA em prod**)
- ⚠️ Pegadinha Windows: py.exe órfão + double-bind silencioso na 8000 → antes de subir: `netstat -ano | grep :8000` + `taskkill //F //PID`

### 2. Política SEM MOCKS
Banco limpo (`scripts/cleanup_mock_data.py`): contatos fictícios e response mock removidos; contato real renomeado "Jair Filho". `mock_waha.py` DELETADO. `seed_bizzu.py` exige `--phones`. Guard `--force` do dispatch mantido.

### 3. Git inicializado — 3 commits
`7b5cd4c` (Fase 0) → `f9f1ffb` (API painel) → `7366d54` (frontend+docs). `.gitignore` protege `.env`/`waha_qr.png`/`_painel_*.png`. **SEM remote ainda.**

### 4. Painel web do Escuta NO AR
- **API admin** (`app/api/admin.py`, 22 testes): `/api/dashboard`, `/api/surveys` (criação dinâmica), `/api/contacts`, `/api/surveys/{id}/dispatch` (real, opt-in, `get_messaging` injetável). CORS p/ 3001.
- **Frontend Next.js 15** em `frontend/` (porta **3001**; 3000 é do WAHA): Dashboard (NPS/funil/distribuição/recentes, refresh 30s) + Pesquisas (criar/disparar) + Contatos. CSS tokens próprio (verde-floresta + acento WA), sem Tailwind, system fonts.
- Validado visualmente (Edge headless `--virtual-time-budget=10000`) com dados reais.

### 5. Bizzu explorada por 5 agentes (6 repos clonados)
Clones em `~/Documents/Projetos/bizzu-repos/` (org GitHub `gabarita-ai`; **leitura pura, nada modificado/enviado**).
- Consolidado: **`docs/INTEGRACAO_BIZZU.md`**
- Relatórios íntegros: **`docs/analise-bizzu/{backend,frontend,radar-editais,infra,site-landing}.md`**
- Descobertas-chave: NestJS+Sequelize+BullMQ na AWS (Terraform); `usuarios.telefone` JÁ existe; NPS in-app básico JÁ existe; SEM webhooks OUT; ganchos de ouro: churn `webhook.service.ts:193` 🥇, tópico `plano-estudo-ia.service.ts:327` 🥈, NPS `nps.service.ts:101` 🥉; **central de atendimentos** (módulo `atendimentos`, schema `suporte`): tickets por EMAIL via SendGrid Inbound Parse (`suporte.bizzu.ai` → `/webhooks/email-inbound`), equipe responde em `/gestao/atendimentos` — é help desk, NÃO CRM completo; sem WhatsApp em NADA.

## 🟡 ONDE PAROU EXATAMENTE: subindo a stack da Bizzu local

| Peça | Estado |
|---|---|
| `bizzu-postgres` (Podman, 5432, senha `bizzu_dev_2026`, db `plataforma`) | ✅ UP |
| `bizzu-redis` (Podman, 6379) | ✅ UP |
| Migrations Sequelize | ✅ aplicadas (até 20260605) |
| `backend/.env` (criado por nós) | ✅ PORT=**3100** (3000=WAHA!), placeholders |
| `frontend/.env.local` | ✅ `VITE_API_URL=http://localhost:3100` |
| Frontend Vite | ✅ NO AR em **http://localhost:5173** |
| **API NestJS (3100)** | 🟡 **4ª tentativa de boot em andamento** |

### A novela do boot da API (cada erro = 1 env exigida; ia corrigindo e relançando)
1. ❌ `NODE_ENV=x nest start` não roda no Windows/cmd → rodar via git-bash: `export NODE_ENV=development && node_modules/.bin/nest start --watch`
2. ❌ Stripe exige key no construtor → `STRIPE_SECRET_KEY=sk_test_dev_local_placeholder`
3. ❌ `ENCRYPTION_KEY must be a 64-char hex string` → hex 64 colocado
4. ❌ `OAuth2Strategy requires a clientID` → GOOGLE_CLIENT_ID/FACEBOOK_APP_ID placeholders (callback ajustado p/ 3100)
5. 🟡 4ª tentativa relançada — **conferir o log**; pode aparecer NOVA env obrigatória (mesmo padrão: ler erro → placeholder no `.env` → relançar)

### Comandos para retomar (se a máquina reiniciou)
```bash
# containers (restart=unless-stopped, devem voltar sozinhos)
podman start bizzu-postgres bizzu-redis waha

# API Bizzu (3100)
cd ~/Documents/Projetos/bizzu-repos/backend
export NODE_ENV=development && export NODE_OPTIONS=--use-system-ca
node_modules/.bin/nest start --watch

# Frontend Bizzu (5173)
cd ~/Documents/Projetos/bizzu-repos/frontend && NODE_OPTIONS=--use-system-ca npm run dev

# --- Stack Escuta ---
# API Escuta (8000) — ANTES: netstat -ano | grep :8000 e matar órfãos!
cd ~/Documents/Projetos/escuta
export PYTHONUTF8=1 && set -a && source .env && set +a && export SELF_CHAT_TEST=1
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning

# Painel Escuta (3001)
cd ~/Documents/Projetos/escuta/frontend && NODE_OPTIONS=--use-system-ca npm run dev

# WAHA: container `waha` (sessão WhatsApp persiste no volume waha_sessions)
```

### Validação pendente da stack Bizzu (assim que a API subir)
1. `curl http://localhost:3100/health`
2. Abrir http://localhost:5173 → criar conta de teste (signup) → login
3. Explorar telas (inclusive `/gestao/atendimentos` exige role MANAGER — promover usuário no banco: `UPDATE usuarios SET role='MANAGER' WHERE email='...'`)
4. Limitações conhecidas do dev local: IA OFF (sem chaves LLM), banco de questões VAZIO (seeds dependem de SQLite externo), pagamentos/OAuth/email não funcionam (placeholders)

## 🗺️ Mapa de portas da máquina
| Porta | Serviço |
|---|---|
| 3000 | WAHA (WhatsApp gateway — Escuta) |
| 3001 | Painel Escuta (Next.js) |
| 3100 | API Bizzu local (NestJS) |
| 5173 | Frontend Bizzu local (Vite) |
| 5432 | bizzu-postgres |
| 6379 | bizzu-redis |
| 8000 | API Escuta (FastAPI) |

## ⏭️ Próximos passos (ordem sugerida)
1. **Terminar boot da API Bizzu** (novela das envs) + signup/login de teste
2. **PoC do gancho de churn**: `EscutaService` no NestJS deles + `POST /api/events/bizzu` no Escuta → exit survey no WhatsApp
3. Campo `whatsappOptIn` + checkbox no Signup deles (`Signup.jsx` ~L299)
4. Sync de contatos Bizzu→Escuta (usuários com telefone + opt-in)
5. Integração detrator→atendimento (criar ticket na central deles)
6. Remote do git do Escuta (GitHub) + rotação das credenciais WAHA
7. Fase 1 do produto: clusters/digest/agente IA

## 🔑 Credenciais/refs rápidas (dev local)
- WAHA: `localhost:3000`, API key `c08468a7d78b4ee1acaf9fb51d775786`, dashboard `admin`/`40107e99f4974e51ac8f0bbada89c8ee`
- Postgres Bizzu local: `postgres`/`bizzu_dev_2026` @ localhost:5432/plataforma
- Supabase Escuta: ref `nlqeargxkidygbrahkbk` (PAT em `~\.secrets\supabase_pat_escuta.txt`)
- Conta WhatsApp pareada: 5524998365809 (Jair) — pareamento persiste no volume `waha_sessions`
