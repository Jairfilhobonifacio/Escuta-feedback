# 🧠 BIZZU × ESCUTA — Documento-Mestre (contexto de "braço direito")

> **Para que serve este arquivo:** é o briefing único e auto-contido do ecossistema **Bizzu**
> (edtech de concursos, org GitHub `gabarita-ai`, 6 repos) e do produto **Escuta** (Central de Voz
> do Cliente no WhatsApp que integra na Bizzu como cliente-piloto). Foi escrito para que **qualquer
> sessão do Claude** (Claude Code, Claude.ai ou Desktop) leia ISTO primeiro e já tenha todo o
> contexto para agir como braço direito — sem precisar revasculhar 137 sessões.
>
> **Fonte:** análise profunda dos 6 repos clonados em `~/Documents/Projetos/bizzu-repos/`, validada
> arquivo-a-arquivo contra o código real em 08–09/06/2026. Substitui leituras antigas onde houver
> conflito. Docs irmãos: `CONTEXTO_BIZZU.md` (ecossistema), `INTEGRACAO_BIZZU.md` (integração),
> `analise-bizzu/*.md` (por repo), `corpus_bizzu/*.md` (RAG), `SESSAO_HANDOFF_*.md` (estado).
>
> **Última atualização:** 2026-06-10 (auditoria de código dos 8 repos + feedback nativo revalidado).

---

## 0. Como o Claude deve usar este documento (modo "braço direito")

1. **Leia este arquivo inteiro antes de agir** em qualquer coisa de Bizzu ou Escuta.
2. **Trate os fatos abaixo como verdade verificada** (têm `arquivo:linha`). Se o código divergir, o
   código vence — e atualize este doc.
3. **Bizzu = leitura.** Os 6 repos em `bizzu-repos/` são clones para entender e gerar *patches* — não
   commitar neles. Toda mudança no lado Bizzu vira `.patch` em `escuta/docs/patches/`.
4. **Escuta = onde construímos.** É o produto do usuário; aqui se escreve código de verdade.
5. **Segredos:** este doc nunca traz valores de chave/senha — só o **caminho** (`~/.secrets/...`) e o
   **nome da env**. Nunca cole segredo em arquivo versionável.
6. **Antes de tocar em WhatsApp real**: confirmar com o usuário (WAHA viola ToS, risco de ban).

---

## 1. TL;DR estratégico (a tese em 6 linhas)

A **Bizzu** é um produto sólido de **conteúdo+IA para concursos** (organiza estudo cruzando o edital
do aluno com 600 mil+ questões; carro-chefe = **Raio X da Prova**). Mas **toda a relação com o cliente
fora do app é por e-mail ou inexistente**: captação só e-mail, suporte só e-mail, **churn sem pergunta**,
NPS preso no app, **zero WhatsApp em todo o ecossistema**. O **Escuta** ocupa exatamente esse vão:
camada conversacional WhatsApp + IA (cérebro, classificação, RAG, digest) + gestão de feedback. Já
está **integrado nos 2 eventos de maior valor (churn + CSAT de tópico)** e tem 4 frentes baratas de
expansão. Risco operacional nº1: **double-touch de churn** (e-mail winback da Bizzu + survey WhatsApp do
Escuta no mesmo cancelamento).

---

## 2. O ecossistema Bizzu — mapa de como tudo se encaixa

```
                          ┌──────────────────────── bizzu.ai (institucional) ────────────────────────┐
   VISITANTE  ───────────▶│  site (Next 16, EC2)         landing-pages (HTML, lp.bizzu.ai)           │
                          │  CTAs diretos, 0 captura     Google Forms (só e-mail) + relatórios RaioX  │
                          └───────────────┬───────────────────────────────┬──────────────────────────┘
                                          │ CTA ?plano= / ?editalSlug=     │ (lead e-mail → planilha)
                                          ▼                                ▼
                          ┌──────────── plataforma.bizzu.ai (app do aluno) ───────────┐
   ALUNO  ───────────────▶│  frontend (Vite 6 + React 18.3, SPA, CloudFront/S3)        │
                          │  signup · checkout · onboarding · Raio X · Plano IA ·      │
                          │  questões · caderno · NPS in-app · /minha-conta            │
                          └───────────────────────────┬───────────────────────────────┘
                                          HTTP + JWT   │   (VITE_API_URL → api.bizzu.ai)
                                                       ▼
                          ┌──────────────────── api.bizzu.ai (cérebro) ───────────────┐
                          │  backend (NestJS 10 + TS, ALB+ASG)                          │
                          │  auth · payments(Stripe/Asaas/MP) · plano-estudo-ia ·       │
                          │  questões · editais · nps · atendimentos(e-mail) ·          │
                          │  subscription-recovery(winback e-mail) · escuta(adapter)    │
                          └───────┬───────────────┬───────────────┬───────────────┬────┘
                                  ▼               ▼               ▼               ▼
                          ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────────┐
                          │ RDS Postgres│  │ Redis/BullMQ│  │ SendGrid    │  │  ESCUTA (nosso)  │
                          │ (Sequelize) │  │ (worker ASG)│  │ (e-mail)    │  │  POST /events    │◀── HMAC
                          └────────────┘  └────────────┘  └────────────┘  └──────────────────┘
                                                                                   ▲
   radar-editais.bizzu.ai  ┌─────────────────────────────────────────────┐        │ (futuro: "saiu seu edital")
   (FastAPI :7400, EC2) ──▶│ radar-editais: detecta edital novo 1×/dia,    │────────┘
                          │ PG próprio :5434, Gemini, S3. Export → Sheet   │
                          └─────────────────────────────────────────────┘

   infra (Terraform/AWS us-east-1, 11 módulos) ── provisiona TUDO acima + onde o Escuta vai morar
```

**Leitura do diagrama:** o visitante entra pelo **site/landing** (institucional) e é jogado para
`plataforma.bizzu.ai` (o **frontend**/app). O app conversa só com o **backend** (`api.bizzu.ai`) via
HTTP+JWT. O backend é o único que fala com banco (RDS), filas (Redis/BullMQ), e-mail (SendGrid) e com o
**Escuta** (HTTP+HMAC). O **radar-editais** roda à parte, com banco próprio, e hoje não notifica
ninguém. Tudo é provisionado pelo repo **infra**.

---

## 3. Os 6 repos — ficha rápida

| Repo | Stack (verificado) | Onde roda / domínio | Porta | Papel |
|------|--------------------|----------------------|-------|-------|
| **backend** | NestJS 10.4 + **TypeScript** 5.7 + Sequelize 6 + BullMQ/Redis · Node ≥22.22 | ALB + **ASG** t4g.small ×2-4 · `api.bizzu.ai` | `PORT` (3000) | API + worker: o cérebro (auth, pagamentos, IA, NPS, suporte) |
| **frontend** | Vite 6 + React 18.3 + Tailwind v4 + RR7 · **sem TS** | CloudFront/S3 · `plataforma.bizzu.ai` | 5173 (dev) | App web do aluno + painel `/gestao` |
| **site** | **Next.js 16.1.6** + React 19 + TS · Vercel | EC2 (Caddy) · `bizzu.ai` | 3001 | Institucional + páginas de edital (SEO long-tail) |
| **landing-pages** | HTML/CSS/JS estático puro | CloudFront/S3 · `lp.bizzu.ai` | — | Waitlist + relatórios "Raio X" públicos (isca) |
| **radar-editais** | FastAPI + Python + SQLAlchemy async + Gemini | EC2 (Caddy) · `radar-editais.bizzu.ai` | 7400 | Detecta editais novos 1×/dia (PG próprio :5434) |
| **infra** | Terraform ≥1.0 + AWS provider ~>5.0 | AWS `us-east-1` | — | Provisiona todo o resto (state S3 `bizzu-terraform-state-633146206248`) |

> ⚠️ **Correções vs. notas antigas:** o **backend é TypeScript** (quem é "sem TS" é o **frontend**). O
> **site NÃO capta lead** — só CTAs diretos; **quem usa Google Forms é o landing-pages**. A API roda em
> **ALB+ASG** (não EC2 única). Radar é **:7400 / PG :5434** (não 8000).

---

## 4. Repo a repo — o essencial para operar

### 4.1 backend (`api.bizzu.ai`) — o cérebro
- **Dois processos, mesmo `AppModule`:** API HTTP (`src/main.ts`, porta `PORT`) e worker BullMQ
  (`src/worker.ts`, `WORKER_ENABLED=true`). Dev: `npm run dev` sobe os dois.
- **Módulos-chave** (`src/`): `auth/` (JWT 30d + OAuth Google/Facebook) · `payments/` (Stripe cartão +
  **Asaas Pix, principal** + MercadoPago; ciclo `ACTIVE→PAST_DUE→CANCELLED`) · `plano-estudo-ia/`
  (motor do plano IA; emite `topic_completed`/`goal_completed`) · `nps/` (NPS in-app) · `atendimentos/`
  (tickets por e-mail via SendGrid Inbound Parse, `suporte.bizzu.ai`) · `subscription-recovery/`
  (dunning + **winback por e-mail**) · `escuta/` (**adapter → Escuta, HMAC**) · `leads-api/` (server-
  to-server `X-API-Key`) · `radar-sync/` (consome o radar).
- **Persistência:** RDS Postgres (Sequelize, 156 migrations) + Redis/BullMQ (≈13 filas).
- **Pagamentos & churn:** webhooks em `/webhooks/payments|mercadopago|asaas`. Churn dispara por **3
  caminhos** (webhook, cancelamento manual, cron de inadimplência Asaas) — os 3 já chamam o Escuta.
- **Riscos:** `rejectUnauthorized:false` no SSL do PG (`app.module.ts:138`); `reason='PAYMENT_FAILED'`
  **hardcoded** em todo cancelamento via webhook (`webhook.service.ts:193,207`); `ESCUTA_API_URL` e
  `ESCUTA_WEBHOOK_SECRET` **fora do `.env.example`** → sem elas o adapter vira **no-op silencioso**.

### 4.2 frontend (`plataforma.bizzu.ai`) — o app do aluno
- **Gating em cascata:** `RequireAuth → RequirePlan → OnboardingGate → RequireCurrentEdital →
  RequireStudyRoutine`.
- **Jornada:** `/signup` (telefone opcional + **checkbox `whatsappOptIn`**) → `/checkout` (Stripe ou Pix
  c/ QR) → `/onboarding` (edital+cargo) → `/onboarding/rotina` → **`/raio-x-da-prova`** (diferencial) →
  **`/plano-de-estudo`** (hub diário; **único lugar onde o `NpsModal` aparece**) → `/questoes` →
  `/caderno` → `/minha-conta` (toggle `whatsappOptIn`; **cancelamento é `window.confirm` seco, sem
  survey** — maior lacuna de feedback).
- **Contrato:** base `VITE_API_URL`; **JWT em `localStorage`**; `getAuthHeaders()` em
  `src/utils/planoEstudoApi.js`. Sem TS → drift de contrato só pega em runtime.
- **NPS in-app:** o front nunca decide quando perguntar — chama `GET /nps/check` (`useNpsCheck.js`),
  triggers `FIRST_SESSION`/`GOAL_HALF`/`GOAL_COMPLETE`, envia `POST /nps`. Painel em `/gestao/nps`.

### 4.3 site (`bizzu.ai`) — institucional + SEO
- **Home = HTML estático** servido por route handler (`app/route.ts` lê `public/landing-page.html`).
- **Motor de SEO:** `/editais/[slug]` (SSG/ISR, FAQ+metadata dinâmicos por edital) e `/bancas/[slug]`.
- **Captação = ZERO.** Todos os CTAs são links diretos para `plataforma.bizzu.ai/signup?plano=...` ou
  `?editalSlug=...`. As classes `.hero-form`/`.cta-form` existem no CSS mas **sem `<form>` no HTML**.
- **Preço (fallback):** R$ 10/mês ou R$ 60/ano (promo "até 20/05" **vencida**); cheio R$ 60/mês ou R$
  650/ano. ⚠️ JSON-LD inconsistente (`9.90` nas páginas React vs `10.00` na home).
- **Analytics:** GA4 `G-6WFC2DE7VE` + PostHog `cross_subdomain_cookie` (compartilha sessão com a
  plataforma).

### 4.4 landing-pages (`lp.bizzu.ai`) — campanhas
- 5 páginas: waitlist + 3 relatórios "Raio X" públicos (SEFAZ-SP, SEFAZ-RN, Câmara) + redirect.
- **Captação só e-mail** via Google Forms único: form `1FAIpQLSe...wnkA`, campo `entry.19628127` →
  planilha. `fetch` `mode:'no-cors'`, sem CRM, sem telefone/WhatsApp.
- **Risco:** relatórios são URLs públicas — o "e-mail para acessar" é 100% contornável.

### 4.5 radar-editais (`radar-editais.bizzu.ai`) — fonte de editais
- **Pipeline 1×/dia (~15 min):** DISCOVER (MCP do PCI Concursos) → FILTER (blocklist/allowlist/Gemini)
  → NORMALIZE → DIFF (`novo/atualizado/mesmo/encerrado`) → ENRICH+PERSIST (Crawl4AI + Gemini extrai 13
  campos + PDFs → S3). Flag de negócio: **`interesse_bizzu`**.
- **Isolado:** banco próprio Postgres :5434, **não** compartilha o RDS. Integração com a plataforma é por
  **export → Google Sheet** (passo manual/externo, não no código).
- **Riscos:** systemd timer **já visto inativo** (editais param sem ninguém ver); não é tempo-real.

### 4.6 infra — onde tudo (e o Escuta) mora
- **11 módulos** (`modules/`): `networking` (VPC, sem NAT) · `dns-cert` (Route53 `bizzu.ai` + ACM
  **wildcard `*.bizzu.ai`**) · `s3-cloudfront` (plataforma + lp) · `rds` (PG db.t3.small **Multi-AZ**) ·
  `elasticache` (Redis) · `api-alb` + `api-asg` (backend ×2-4) · `worker-asg` (BullMQ ×1-3) · `api-ec2`
  (site Next via Caddy) · `radar-editais-ec2` (FastAPI via Caddy).
- **DNS:** `api.bizzu.ai` é **CNAME no Cloudflare** (fora do Terraform!); o resto em Route53.
- **Secrets:** Secrets Manager namespace `prod/<serviço>/<recurso>`; policy cobre só `prod/plataforma/*`
  e `prod/site/*`.

---

## 4.7 Sistema de feedback NATIVO da Bizzu (pré-Escuta) — leitura essencial

> A Bizzu **não era surda**: já coletava voz do cliente em **5 frentes** antes do Escuta. Entender isso é
> o que evita o Escuta **duplicar** o que já existe. Inventário completo (com `arquivo:linha`) em
> **`docs/analise-bizzu/feedback-nativo.md`**.

| Família | Mecanismo nativo | O que a Bizzu faz | Lacuna | Escuta |
|---------|------------------|-------------------|--------|--------|
| **A. Satisfação proativa** | **NPS in-app** (`src/nps`, `NpsModal`) — nota 1-10 + comentário em 3 gatilhos (FIRST_SESSION/GOAL_HALF/GOAL_COMPLETE); painel `/gestao/nps` (gauge, por-gatilho, evolução) | calcula NPS; só armazena comentário | sem sentimento/tema; só na pág. do Plano; sem cooldown | **espelhar** (🥉), não substituir |
| **B. Suporte reativo** | **Atendimentos** (`src/atendimentos`) — helpdesk e-mail completo (threading via SendGrid Inbound Parse, status/prioridade/anexos S3, `/gestao/atendimentos`) + **Contato** (`/contato`) | triagem e resposta por e-mail | **sem CSAT pós-atendimento**; sem WhatsApp | complementar (CSAT futuro); não virar helpdesk |
| **C. Qualidade de conteúdo** | **Report de questão** (`QuestaoReportModal` → `POST /questoes/:id/report`, **ativo**, valida gabarito c/ IA Gemini no painel) + **Comentários/votos** por questão + **Comentário-IA detector** (`needsReview` quando IA discorda do gabarito) | painéis de triagem/moderação | sem threshold automático; aluno não vê status | **deixar nativo** |
| **D. Churn / sinais passivos** | **`cancellationReason`** automático (`GUARANTEE_REFUND\|USER_CANCEL\|PAYMENT_FAILED\|OTHER`) — **nunca pergunta o porquê** (cancel é `window.confirm` seco) + **PostHog** server-side | filtra winback; análise externa | **motivo real do churn não é capturado** | 🥇 **exit survey WhatsApp = o ouro** (✅ plugado) |
| **E. Demanda** | **Solicitação de edital** (`src/edital-solicitacoes`) | fila + notifica quando sai | sem priorização por volume | radar→WhatsApp (futuro) |

> ⚠️ **Correção vs. notas antigas:** existem DOIS "reportar erro" — `ReportarErroPage` (`/reportar-problema`)
> é **stub**, mas o **report de questão** (`QuestaoReportModal`, na sessão) é **totalmente funcional**.
> E "exit survey de churn não existe nativamente" continua verdade — a Bizzu **categoriza** o churn
> sozinha, mas **nunca pergunta o motivo** ao usuário; é o Escuta que faz isso.

**Os 3 buracos que o Escuta preenche** (o resto é forte e nativo — não duplicar): **(1)** canal
conversacional WhatsApp (a Bizzu não tem nenhum); **(2)** inteligência sobre o feedback (NPS e
atendimentos só armazenam — ninguém classifica sentimento/tema); **(3)** o "porquê" do churn (capturado
ativamente, não derivado).

---

## 5. O Escuta — o produto do usuário

**O que é:** Central de Voz do Cliente no WhatsApp, multi-tenant, derivada do Nexus AI + Pulse. Recebe
eventos de ciclo de vida de clientes (piloto: Bizzu), dispara *surveys* via WhatsApp, interpreta a
resposta com IA, classifica e entrega insight ao dono.

- **Local:** `C:\Users\jboni\Documents\Projetos\escuta`. Git no commit `6004166` (branch sem remote).
- **Stack:** FastAPI (Python) + Supabase Postgres (pgvector) + WAHA (WhatsApp não-oficial) + painel
  Next.js. LLM via **Groq** (`llama-3.3-70b-versatile`). Embeddings **MiniLM offline** (384 dim).
- **As 4 camadas de IA** (todas com fallback determinístico):
  1. **SurveyBrain** (`app/domain/survey/brain.py`): interpreta resposta natural → nota; detecta
     opt-out; responde pergunta; classifica feedback.
  2. **Classificação:** `sentiment` / `themes` / `urgency` por resposta.
  3. **RAG** (`app/domain/knowledge/`): pergunta do contato → busca corpus (`corpus_bizzu/`, 33 chunks,
     pgvector) → resposta *grounded* com **gating duplo** (similaridade + LLM recusa se não cobre).
  4. **Digest semanal** (`app/domain/digest/`): resume a semana (NPS, temas, urgências, churn) → LLM
     narra → WhatsApp do dono. Endpoints `GET /api/digest/preview` + `POST /api/digest/run`.
- **Portas:** API `:8000` · painel `:3001` · WAHA `:3000`.
- **Qualidade:** 66 testes Escuta + 12 E2E (`scripts/smoke_all.py`) + 191 specs Bizzu — verdes.

---

## 6. A integração Escuta ↔ Bizzu — o que JÁ está plugado

**Protocolo:** backend Bizzu → `POST {ESCUTA_API_URL}/api/events/bizzu`, **HMAC-SHA256** sobre
`"{timestamp}.{body}"`, headers `X-Escuta-Timestamp` + `X-Escuta-Signature`, tolerância 5 min,
fire-and-forget (nunca bloqueia o fluxo da Bizzu). Idempotência por `event_id` (dedup no Escuta).

| Evento | `event_id` | Call-site (Bizzu) | Survey no Escuta |
|--------|-----------|-------------------|------------------|
| `subscription_cancelled` | `sub:<extSubId>` | `payments/webhook.service.ts:225` (webhook) · `payments/subscription.service.ts:487` (manual) · `asaas-overdue-cancellation.service.ts:78` (cron) | **Exit Bizzu** (type `exit`) |
| `topic_completed` | `task:<id>` | `plano-estudo-ia.service.ts:2050` (4 call-sites: `:344,376,1005,2558`) | **CSAT Tópico Bizzu** (type `nps`, id `b18a4736`) |
| `goal_completed` | `goal:<id>` | `plano-estudo-ia.service.ts:2066` | — |

- **Consentimento:** `usuarios.whatsappOptIn` + `whatsappOptInAt` (migration `20260607130000`). Checkbox
  no `Signup.jsx` + toggle em `MinhaContaPage`, via `PATCH /user/me`. O backend **envia** o flag no
  payload; **a filtragem por opt-in é do Escuta**.
- **Lado Escuta:** `POST /api/events/bizzu` (`app/api/events.py`) faz get-or-create de contato, dedup por
  `event_id`, cooldown 7 dias por contato+survey, liga evento→survey por `surveys.trigger_event`.
- **Patches Bizzu** (não commitados nos clones — o clone é leitura): `docs/patches/bizzu-backend-escuta-
  churn-hook.patch` (≈1017 linhas) e `docs/patches/bizzu-frontend-whatsapp-opt-in.patch` (≈127 linhas).

---

## 7. Mapa de oportunidades (o que falta — priorizado)

| Pri | Oportunidade | Onde plugar | Esforço | Status |
|-----|--------------|-------------|---------|--------|
| ✅ | Exit survey de churn | 3 caminhos de cancelamento | — | **feito** |
| ✅ | CSAT de tópico/meta | `plano-estudo-ia.service.ts` | — | **feito** |
| 🥉 | **Espelhar NPS in-app** → análise unificada | `nps.service.ts:101` → evento `nps_submitted` (modo "ingest sem disparo" no Escuta) | baixo | **código pronto+testado (10/06); pendente: migration `20260610_nps_ingest` + seed + patch `docs/patches/bizzu-backend-nps-escuta-ingest.patch` + deploy** |
| 🆕 | **Mega Central de Dados (Visão 360)** — unifica TODAS as fontes | `FeedbackItem` (model+migration `20260610b`) + ingest pull (API Clientes) e push (`GENERIC_EVENT_MAP` no `events.py`) + `GET /api/contacts/{id}/360` + **tela 360** (`frontend/app/contatos/[id]`) | médio | **COMPLETA e testada (129 testes, 10/06). 5 fontes unificadas: NPS, churn, report de questão, solicitação de edital, atendimentos (ticket→FeedbackItem; ticket_resolved→CSAT WhatsApp). 3 patches backend em `docs/patches/` (question-report, edital-requested, atendimentos). Falta só ATIVAR: aplicar os 4 patches no backend + migrations (`20260610_nps_ingest`, `20260610b_feedback_items`) + sync + deploy** |
| 🆕 | **Chatbot conversacional (aprofundamento + hand-off)** | `Message` (transcript, migration `20260610c`) + `brain.decide_followup`/intent `handoff` + resolver (`_maybe_followup`, `_handle_handoff`, `_notify_handoff`, `_open_support_ticket`); webhook grava inbound/outbound e pausa contato em hand-off | médio | **pronto+testado (10/06): guarda TODO o transcript; aprofunda até 2 (viés detrator, acumula motivo); hand-off marca+pausa+alerta o dono + abre ticket (patch `bizzu-backend-support-ticket-endpoint.patch`). Falta só ativar (migration `20260610c`)** |
| 🆕 | **Fase 2: clustering de temas + alertas de detrator** | `aggregate_themes` (`aggregator.py`) + `GET /api/themes/aggregate` · `resolver._notify_detractor_realtime` (detrator urgente/negativo → alerta o dono na hora) + parser robusto (`um/uma`) | médio | **pronto+testado (136 testes, 10/06). v2 (clustering semântico/pgvector + card de temas no painel) = futuro** |
| 4 | **Radar → "saiu seu edital" no WhatsApp** | `radar-editais/pipeline.py:317` (após `aplicar_interesse`, antes do `upsert`) | baixo (<50 ln) | canal de valor altíssimo |
| 5 | **Captura WhatsApp na captação** | site (hero, `/editais/[slug]`, `/exemplo`) + landings (Google Forms) | baixo | lead já chega "conversável" |
| 6 | Eventos `signup`, `plano_gerado` | `auth.service.ts:52`, `plano-estudo-ia.service.ts` | baixo | mais momentos de ativação |

---

## 8. Riscos conhecidos (ordenar antes de escalar o piloto)

1. ⚠️ **Double-touch de churn** — no mesmo cancelamento a Bizzu manda **e-mail winback** e o Escuta
   manda **survey WhatsApp**. Definir cadência/ownership. (Risco nº1.)
2. 🐛 **`reason` hardcoded** `webhook.service.ts:207` (=PAYMENT_FAILED sempre) → suja o motivo de churn
   voluntário no exit survey.
2b. 🐛 **Churn voluntário fora do PostHog** (auditoria 10/06) — `finishCancel` (`subscription.service.ts:461`)
   não chama `tracking.capture`; só os webhooks (`webhook.service.ts:212`) e o cron asaas-overdue rastreiam
   `subscription_cancelled`. O cancelamento por vontade do usuário **some do PostHog**, mas **chega ao Escuta**.
3. 🔇 **`ESCUTA_*` fora do `.env.example`** do backend → deploy novo fica inerte sem aviso.
4. 🔑 **Rotação WAHA pendente** (credenciais novas já geradas em `~/.secrets/waha_*.txt`).
5. 📡 **Radar systemd inativo** em prod — monitorar o timer.
6. 🏷️ **Site:** promo "até 20/05" vencida no fallback + JSON-LD de preço inconsistente (9.90 vs 10.00).

---

## 9. Estado atual + como retomar a stack local

**Estado (handoff 08/06):** tudo no ar — API Escuta `:8000` (IA+RAG+digest), painel `:3001`, WAHA `:3000`
(sessão `WORKING`, número Jair `5524998365809`). API Bizzu local `:3100` e front Bizzu `:5173` ficam
desligados; religar só para testar integração. Containers Podman: `waha` + `bizzu-postgres` +
`bizzu-redis`.

```bash
# 1) Containers (restart=unless-stopped; devem voltar sozinhos)
podman start waha bizzu-postgres bizzu-redis

# 2) API Escuta (8000) — ANTES matar órfãos: netstat -ano | grep :8000 → taskkill //F //PID
cd ~/Documents/Projetos/escuta
export PYTHONUTF8=1 HF_HUB_OFFLINE=1 && set -a && source .env && set +a && export SELF_CHAT_TEST=1
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning

# 3) Painel Escuta (3001)
cd ~/Documents/Projetos/escuta/frontend && NODE_OPTIONS=--use-system-ca npm run dev

# 4) (opcional) API Bizzu (3100) — DATABASE_SYNCHRONIZE=false no .env!
cd ~/Documents/Projetos/bizzu-repos/backend
export NODE_ENV=development NODE_OPTIONS=--use-system-ca && node_modules/.bin/nest start --watch
```

**Pegadinhas desta máquina (já custaram tempo):**
- **TLS interceptado por antivírus** → HTTPS externo (Groq, GitHub) falha com `CERTIFICATE_VERIFY_FAILED`.
  Fix: `truststore.inject_into_ssl()` no topo (já em `app/main.py` e nos scripts que chamam a Groq).
- **Embeddings offline:** exige `HF_HUB_OFFLINE=1` + `all-MiniLM-L6-v2` no cache HF (herdado do Nexus).
- **Groq:** `/models` dá 403 (escopo), mas `/chat/completions` funciona — testar com chamada real.
- **Podman pós-reboot:** forward `0.0.0.0` pode virar IPv6-only → recriar com `-p 127.0.0.1:<porta>:<porta>`.
- **NestJS:** `DATABASE_SYNCHRONIZE=true` crasha o boot (ALTER de enum) → `false`.
- **Windows:** TaskStop deixa `py.exe` órfão segurando a 8000 → matar PIDs antes de subir.

---

## 10. Refs rápidas (sem valores de segredo — só caminhos/nomes)

| Item | Valor / Caminho |
|------|-----------------|
| Supabase Escuta | ref `nlqeargxkidygbrahkbk` (sa-east-1); PAT em `~/.secrets/supabase_pat_escuta.txt` |
| WAHA | `localhost:3000`; key em `.env` (`WAHA_API_KEY`) — **rotacionar**, novas em `~/.secrets/waha_*.txt` |
| Groq | `.env`: `GROQ_API_KEY` + `GROQ_MODEL=llama-3.3-70b-versatile`; `LLM_ENABLED=1` |
| Bizzu local (PG) | `postgres` / senha em `.env` @ `localhost:5432/plataforma`; user teste `jair.e2e@escuta.test` |
| HMAC Bizzu↔Escuta | `BIZZU_WEBHOOK_SECRET` (.env Escuta) == `ESCUTA_WEBHOOK_SECRET` (.env backend Bizzu) |
| Terraform state | bucket S3 `bizzu-terraform-state-633146206248`, key `infra/terraform.tfstate` |
| ACM wildcard | `*.bizzu.ai` (us-east-1) — já cobre `escuta.bizzu.ai` |
| Surveys Escuta | Exit Bizzu (type `exit`) · CSAT Tópico Bizzu (type `nps`, id `b18a4736`) |
| Identidade Bizzu | Indigo `#6C5CE7` · Gold `#F5A623` · dark `#0c0b10` · Space Grotesk + Inter/DM Sans + JetBrains Mono |

---

## 11. Onde o Escuta vai morar na AWS (quando sair do localhost)

Molde pronto: **`modules/radar-editais-ec2/`** (EC2 t4g.small ARM + EIP + Caddy + Route53 + IAM +
systemd). Receita:
1. Clonar p/ `modules/escuta-ec2/` — `subdomain="escuta"`, +`dnf install -y docker` no `user_data.sh`
   (p/ o WAHA), systemd p/ FastAPI (8000) + WAHA.
2. `escuta-secrets.tf` com secret `prod/escuta/app` (Supabase, WAHA_API_KEY, HOOK_SECRET); IAM role lê
   só `prod/escuta/*`.
3. Referenciar `module "escuta_ec2"` no `main.tf` (subnet pública + zone).
4. `escuta.bizzu.ai` já coberto pelo wildcard ACM. **Supabase do Escuta fica separado** do RDS (sem SG
   rule nova). Custo ~**$12–14/mês**.

---

## 12. Fatos canônicos para RAG / atendimento (verdadeiros)

- Bizzu é **planejamento de estudos com IA para concursos**, **não é curso** e não vende aulas/apostilas;
  complementa cursos. Base de **600 mil+ questões** das maiores bancas.
- Produto central: **Raio X da Prova** — ranking de tópicos (MUITO ALTA → MUITO BAIXA prioridade) por
  banca + cargo + órgão. Mais: Plano de Estudos IA, Questões Selecionadas/Comentadas, Caderno do Tópico.
- Preço: lançamento **R$ 10/mês ou R$ 60/ano**; cheio R$ 60/mês ou R$ 650/ano; **garantia 7 dias, sem
  fidelidade**, cancela a qualquer momento.
- Pagamento: **Asaas (Pix, principal)** + Stripe (cartão); webhooks idempotentes.
- O backend **não envia WhatsApp** — o único outbound de mensagem é e-mail (SendGrid). **WhatsApp é 100%
  do Escuta**, alimentado por eventos HTTP+HMAC.
- O radar coleta editais **1×/dia**; use sempre a flag `interesse_bizzu=true` (já embute blocklist + LLM).

---

## 13. Glossário

- **Raio X da Prova** — ranking de prioridade de tópicos por incidência real em questões do edital.
- **Survey** — pesquisa disparada pelo Escuta no WhatsApp (NPS, CSAT, Exit).
- **WAHA** — WhatsApp HTTP API não-oficial (viola ToS; só piloto pequeno).
- **Digest** — resumo semanal narrado por IA, enviado ao dono no WhatsApp.
- **Double-touch** — cliente recebe 2 contatos (e-mail Bizzu + WhatsApp Escuta) no mesmo evento.
- **gabarita-ai** — org GitHub onde vivem os 6 repos da Bizzu (privados).
```
