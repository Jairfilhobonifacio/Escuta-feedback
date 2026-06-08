# Backend Bizzu — Análise Profunda (para integração com o Escuta)

> Exploração profunda em 08/06/2026. Clone local: `~/Documents/Projetos/bizzu-repos/backend`.
> Repo: `gabarita-ai/backend` (org GitHub `gabarita-ai`). NestJS 10, ~946 arquivos `.ts` em `src/`, 156 migrations.
> Esta versão **substitui** o relatório raso anterior. Convenção: caminhos relativos à raiz do backend; sempre que possível `arquivo:linha`.

---

## 0. Resumo executivo (o que mais importa para Escuta ↔ Bizzu)

1. **A integração JÁ EXISTE no backend e está mais avançada do que o relatório antigo sugeria.** Há `src/escuta/escuta.service.ts` (adapter HTTP fire-and-forget + HMAC-SHA256) e `src/escuta/escuta.module.ts` (`@Global`), montados em `app.module.ts:54,95`. O endpoint de destino é **`POST {ESCUTA_API_URL}/api/events/bizzu`** com headers `X-Escuta-Timestamp` + `X-Escuta-Signature` (`escuta.service.ts:98-107`).
2. **Três ganchos de ciclo de vida estão plugados e em produção** (todos `captureForUser`, nunca lançam/bloqueiam):
   - `subscription_cancelled` em **3 caminhos distintos** de churn: webhook de pagamento (`payments/webhook.service.ts:225`), cancelamento manual pelo usuário (`payments/subscription.service.ts:487`) e cron de inadimplência Asaas (`payments/asaas-overdue-cancellation.service.ts:78`). `event_id` estável `sub:<externalSubscriptionId>` → Escuta deduplica os 3.
   - `topic_completed` e `goal_completed` ao concluir tarefa/meta do plano de estudos (`plano-estudo-ia/plano-estudo-ia.service.ts:2050` e `:2066`), chamados de 4 pontos (`:344`, `:376`, `:1005`, `:2558`).
3. **Consentimento de WhatsApp dedicado já foi criado** (não é mais proxy de `marketingOptOut`): colunas `usuarios.whatsappOptIn`/`whatsappOptInAt` (`users/user.model.ts:133-146`, migration `20260607130000-add-whatsapp-opt-in-to-usuarios.js`), capturado no signup (`auth/dto/signup.dto.ts:19-22`, `auth/auth.service.ts:46-48`) e no `PATCH /user/me` (`users/users.service.ts:529-549`). O payload do evento envia `user.whatsapp_opt_in` ao Escuta (`escuta.service.ts:88`), mas **o backend NÃO filtra por opt-in** — quem decide disparar/respeitar consentimento é o Escuta.
4. **O telefone é resolvido no backend**: `EscutaService.send()` busca o `User` por id, monta `name`/`phone`, e **pula o evento se o usuário não tem `phoneNumber`** (`escuta.service.ts:75-78`). Eventos viajam por **userId**, não por telefone.
5. **Ganchos que FALTAM**: `signup` (cadastro — só dispara cart-abandonment hoje, sem evento Escuta: `auth.service.ts:53`), `plano gerado` (geração do plano IA, sem hook), `nps_submitted` (NPS é independente; nenhum evento sai p/ Escuta: `nps/nps.service.ts:101`), `payment_recovered`/`reactivated`, e **aprovação em concurso (não existe no modelo de dados)**.
6. **Não há WhatsApp em lugar nenhum do backend Bizzu** (confirmado por grep): o único canal outbound é **email via SendGrid**. Suporte (`atendimentos`) é por email (SendGrid Inbound Parse). O WhatsApp é 100% responsabilidade do Escuta. Isso valida o desenho: Escuta é o canal de voz-do-cliente; Bizzu só emite eventos.
7. **Dunning/winback já existem do lado Bizzu por EMAIL** (`subscription-recovery`, fila BullMQ, 3 toques cada). O Escuta sobrepõe-se nisso com WhatsApp — atenção a **double-touch** (Bizzu manda email de winback E Escuta manda survey de churn no mesmo cancelamento). Coordenar cadência/cooldown.
8. **Gap de configuração**: `ESCUTA_API_URL` e `ESCUTA_WEBHOOK_SECRET` **não estão no `.env.example`** (só no `.env` real). Documentar para não quebrar deploy de outra instância. Quando ausentes, o service só loga um warn e fica inerte (`escuta.service.ts:34-38`).

---

## 1. Stack & build

| Item | Detalhe | Fonte |
|---|---|---|
| Framework | **NestJS 10.4** (`@nestjs/common` 10.4.15, core 10.4.15) | `package.json:49-56` |
| Linguagem | TypeScript 5.7, Node **>= 22.22** | `package.json:6,120` |
| ORM | **Sequelize 6.37** + `sequelize-typescript` 2.1 + `@nestjs/sequelize` 10 | `package.json:55,83-85` |
| Banco | **PostgreSQL** (`pg` 8.13, `pg-hstore`). SSL `rejectUnauthorized:false` em prod | `app.module.ts:121,136-140` |
| Pool DB | max 40 / min 2 / acquire 30s / idle 10s | `app.module.ts:130-135` |
| Fila/Jobs | **BullMQ 5.71** + `@nestjs/bullmq` 11 sobre **Redis** (`ioredis` 5.10) | `package.json:48,60,64`; conexão `app.module.ts:77-91` |
| Scheduler | `@nestjs/schedule` 6.1 (`@Cron`) — `ScheduleModule.forRoot()` | `app.module.ts:71` |
| Auth | `@nestjs/jwt` + `passport` (jwt, local, google-oauth20, facebook) | `package.json:52-72` |
| LLM SDKs | `@google/genai` 1.43 (Gemini). OpenAI/Anthropic via `fetch` direto | `package.json:47`; `ai/ai.service.ts:36-37` |
| Pagamentos | `stripe` 20.4, `mercadopago` 2.12. **Asaas (Pix) via fetch/HTTP** | `package.json:65,86` |
| Email | **SendGrid** (`fetch` direto à API `/v3/mail/send`); SendKit legado | `atendimentos/atendimentos.service.ts:112`; `.env.example:90-95` |
| Analytics | **PostHog** server-side (`posthog-node` 5.29) | `package.json:79`; `tracking/posthog-tracking.service.ts` |
| Storage | AWS S3 (`@aws-sdk/client-s3`), Secrets Manager (`@aws-sdk/client-secrets-manager`) | `package.json:45-46` |
| Logging | **Pino 10** + `nestjs-pino` 4.6 (`pino-http`) | `package.json:67,77-78` |
| HTML/PDF | `pdf-lib`, `pdfkit`, `sanitize-html`, `striptags`, `adm-zip` | `package.json:57-87` |

**Entrypoints**: dois processos.
- **API** — `src/main.ts`: `bootstrapEnv()` → `NestFactory.create(AppModule)`. `bodyParser:false` + `json()` custom com `verify` que guarda `req.rawBody` (necessário p/ verificar assinatura de webhooks Stripe). CORS por `CORS_ORIGINS` (CSV). `ValidationPipe({whitelist:true})` global. Porta `PORT` (default 3000). (`main.ts:14-43`)
- **Worker** — `src/worker.ts`: `NestFactory.createApplicationContext(AppModule)` (sem HTTP). É o processo que roda os `@Processor` BullMQ. `bootstrapEnv(resolve(__dirname,'../..'))`. (`worker.ts:8-24`)

**Scripts** (`package.json:8-42`):
- `npm run dev` → `concurrently` api (`start:dev:env`, watch) + worker (`start:worker:dev`, `WORKER_ENABLED=true`).
- `build` → `nest build && nest build worker` (dois bundles); `start:prod` → `node dist/main`.
- **Migrations** (Sequelize CLI, **NÃO** synchronize em prod): `db:migrate` / `db:migrate:undo` via `sequelize.config.cjs` + pasta `migrations/`.
- PM2: `ecosystem.config.js`.
- Muitos `seed:*` (importam do SQLite legado: matérias, cargos, áreas, bancas, questões, editais) + `migration:etl`, `radar:cutover`, `parity:*`.

**Migrations** (`migrations/`, 156 arquivos): base `20250101*` (schema inicial: orgaos→questoes→plano-estudo→subscriptions→payment_attempts→refunds→webhook_events→study-plans). Recentes relevantes: `20260527140000-add-complimentary-to-subscriptions`, `20260525120000-add-past-due-at-to-subscriptions`, `20260522100000-create-mensagem-templates`, `20260523120000-create-subscription-reconcile-runs`, e a mais nova **`20260607130000-add-whatsapp-opt-in-to-usuarios`** (colunas de consentimento WhatsApp para o Escuta).

---

## 2. Mapa de módulos (`app.module.ts` importa ~70)

### Auth / Usuários / Conta
- **auth** — login/signup local + Google/Facebook OAuth, JWT (`{sub,email,planId,role}`, 30d), reset de senha, guards (`JwtAuthGuard`, `ManagerAuthGuard`, `ActiveSubscriptionGuard`). `auth/auth.service.ts`.
- **users** — modelo `usuarios`, perfil (`/user/me`), troca de plano (intent), rotina de estudo (`user-study-routine`), agregados de assinante. `users/users.service.ts`.
- **crypto** — `@Global`, criptografia de CPF (`cpfEncrypted`). `crypto/`.

### Monetização
- **payments** — núcleo financeiro: subscriptions, payment_attempts, refunds, webhook_events, providers (stripe/mercadopago/asaas), checkout, webhooks, reconciliação, renovação Pix, cancelamento por inadimplência. (detalhe §4)
- **planos** — catálogo de planos + histórico de preço/garantia/regra de reembolso (`plan-*-history`). `planos/`.
- **price-change-campaigns** — campanhas de mudança de preço (grandfathering/migração), com fila `PRICE_CHANGE_QUEUE`. `price-change-campaigns/`.
- **subscription-recovery** — **dunning** (cobrança de inadimplente) + **winback** (recuperação pós-churn) por EMAIL, fila BullMQ com 3 toques. `subscription-recovery/`. (§4)
- **cart-abandonment** — sequência de 4 emails pós-signup sem pagamento (`CART_ABANDONMENT_QUEUE`). `cart-abandonment/`.
- **gestao** — back-office do MANAGER (dashboard, usuários, marketing-email em massa, reconcile). Filas `MARKETING_EMAIL_QUEUE`, `SUBSCRIPTION_RECONCILE_QUEUE`. `gestao/`.

### Conteúdo / Concursos (núcleo do produto)
- **orgaos, bancas, areas, especialidades, cargos, cargos-especialidades** — catálogo-base de concursos.
- **materias, topicos** — taxonomia de matérias/tópicos.
- **editais, editais-garimpados** — editais (upload manual) e editais raspados de planilha Google Sheets (`radar-sync`).
- **edital-cargos, edital-cargos-materias-topicos (ECMT), edital-cargos-organization-groups/-items** — relação edital↔cargo↔matéria↔tópico, com prioridade/rank (o "Raio-X").
- **edital-concurso** — revisões estruturadas de edital (vagas, fases, cronograma, lotação) — muitos `*-revision-*` models.
- **edital-extractor** — pipeline de extração de PDF de edital via LLM (filas `EXTRACTION`/`ORGANIZATION`/`PRIORITIZATION`).
- **edital-link-finder, edital-solicitacoes** — busca de link de edital (Tavily) e solicitações de edital por leads.
- **radar-sync, editais-garimpados** — integração com "Radar de Editais" (`pci_mcp`), cron diário + redis-lock single-flight.
- **auto-pipeline** — orquestrador que processa cargos pós-edital automaticamente (cron a cada 15s, gate `AUTO_PIPELINE_ENABLED`).
- **provas** — provas + mapa prova↔questão.
- **questoes, questoes-imagens, question-report** — banco de questões, imagens (S3), report de erro em questão (alerta p/ staff).
- **questoes-comentarios, questoes-comentarios-votos** — comentários de usuários em questões + votos.
- **questoes-favoritas-listas** — favoritar questões e montar listas.
- **caderno** — anotações do usuário em tópico (`user-topico-nota`) e "bizzus salvos" (`user-topico-bizzu-salvo`).
- **site-content, leads-api** — conteúdo de SEO por banca/edital e **API server-to-server** (`X-API-Key`) que alimenta a landing/site com concursos, raio-X, bizzus, bancas. `leads-api/leads-api.service.ts`.
- **user-editais** — vínculo usuário↔edital-cargo escolhido ("minha meta/concurso").

### Camada de IA
- **ai** — **gateway único de LLM** (Gemini default + OpenAI gpt-5-nano + Claude), retry, semáforo de concorrência, trace. `ai/ai.service.ts`. (§5)
- **llm-traces** — persiste toda chamada LLM (`llm_traces`): tokens, custo, latência, status. Cron de limpeza diária.
- **plano-estudo-ia** — **motor do plano de estudos IA**: gera plano (goals+tasks), snapshots, templates, reselect de questões, profiles de complexidade/tópico, documentos normativos. ~30 models. **É aqui que vivem os ganchos `topic_completed`/`goal_completed`.** (§5, §7)
- **plano-estudo** — plano de estudo "clássico" (anotações, questões resolvidas) — coexiste com o IA.
- **seletor-questoes-ia** — pipeline IA que seleciona/filtra questões por recorte semântico (caches de subject-match/topic-scope/eval, fila `selector`).
- **questoes-comentarios-ia, qcia-geracao-batches** — geração de comentário-IA de questão em lote (fila `questao-comentario-ia`).
- **question-enrichments, enriquecimento-questoes, questao-extracao, trap-tags** — enriquecimento/extração de metadados de questões (knowledge type, trap tags) via IA, com poller cron.

### Suporte / Feedback (CRÍTICO p/ Escuta)
- **nps** — pesquisa NPS in-app, simples, sem retry/contexto/análise. `nps/`. (§6)
- **atendimentos** — **tickets de suporte por EMAIL** (SendGrid Inbound Parse), schema PG `suporte`. `atendimentos/`. (§6)
- **contact** — formulário de contato → cria atendimento. `contact/`.
- **mensagem-templates** — templates de mensagem reutilizáveis (`mensagem_templates`).
- **escuta** — **adapter de eventos de ciclo de vida → Central de Feedbacks (Escuta) via WhatsApp.** `escuta/`. (§7)

### Infra / Observabilidade
- **health, version** — healthcheck e versão.
- **logging** — `@Global`, Pino + hooks de exceção de processo.
- **tracking** — `@Global`, PostHog server-side (`captureForUser`-like). `tracking/`.
- **redis-lock** — `@Global`, lock distribuído (single-flight de crons). `redis-lock/`.
- **config, setup, platform-config** — config de banco/env, seed/setup, config de plataforma key-value (`platform_config`).
- **dashboard** — métricas para o painel.
- **migration-etl** — ETL do SQLite legado → Postgres (+ shadows de paridade), upload S3.
- **email** — `EmailService` (SendGrid) + `email_log` + templates (dunning, winback, boas-vindas, etc.).
- **external-libraries, utils, types** — wrappers (ex.: `google-genai`), helpers, tipos.

---

## 3. Modelo de dados (entidades Sequelize centrais)

> Padrão: `@Table` com `paranoid:true` (soft-delete via `deletedAt`) na maioria. `underscored` varia por tabela.

### `usuarios` — `users/user.model.ts`
- PK `id` UUID (`:23-29`); `primeiroNome`/`ultimoNome` TEXT (`:31-43`); `email` unique (`:45-50`).
- **`phoneNumber`** → coluna física **`telefone`** (`:52-57`) — **campo que o Escuta usa**.
- `passwordHash` (nullable p/ OAuth), `googleId` unique, `photoUrl`, `resetPasswordToken(+ExpiresAt)`.
- `planoId` FK (plano ATIVO/pago) (`:85-94`); **`pendingPlanoId`** FK (plano escolhido mas não pago — intent) (`:102-111`). **Usar `planoId` para "tem acesso", não `pendingPlanoId`.**
- `role` ENUM `CANDIDATE|MANAGER` (`:113-118`).
- `marketingOptOut` BOOL + `marketingOptOutAt` (opt-out genérico de email) (`:120-131`).
- **`whatsappOptIn` BOOL NOT NULL default false + `whatsappOptInAt`** (`:133-146`) — **consentimento dedicado p/ Escuta** (LGPD). Default false: ninguém entra retroativamente.
- `cpfEncrypted`, `asaasCustomerId`.
- `@DefaultScope` exclui `passwordHash`/`resetPasswordToken*` (`:15-17`).

### `subscriptions` — `payments/subscription.model.ts`
- PK `id`; `userId` FK, `planId` FK.
- **`status` ENUM `ACTIVE|CANCELLED|EXPIRED|REFUNDED|PAST_DUE`** default ACTIVE (`:51-56`).
- `startedAt`, `currentPeriodEnd`, `externalSubscriptionId`, `externalPaymentId`.
- `provider` ENUM `stripe|mercadopago` (`:87`).
- `cancelledAt`, `pastDueAt`, `pixRenewalNotifiedAt`.
- **`isComplimentary`** BOOL (brinde manual sem gateway) + `grantedByUserId` + `grantNote` (`:103-122`).
- **`cancellationReason` ENUM `GUARANTEE_REFUND|USER_CANCEL|PAYMENT_FAILED|OTHER`** (`:124-129`) — **enriquece o motivo de churn** que vai pro Escuta.
- `refundAmountCentavos`, `refundPercentageApplied`, `campaignId` FK.
- `HasMany` PaymentAttempt, Refund.

### `payment_attempts` — `payments/payment-attempt.model.ts`
- PK `id`; `userId`/`planId` FK; `amountCentavos`.
- `status` ENUM `PENDING|APPROVED|REJECTED|CANCELLED|REFUNDED` (`:57-62`).
- `externalPaymentId`/`externalReferenceId`/`externalSubscriptionId`; `provider` ENUM `stripe|pix` (`:85`); `subscriptionId` FK; `rawResponse` JSONB.

### `refunds` — `payments/refund.model.ts`
- `paymentAttemptId`/`subscriptionId`/`userId` FK; `amountCentavos`; **`type` ENUM `FULL|PARTIAL`** (`:66-70`); `reason`; `externalRefundId`; `provider stripe|pix`; **`requestedBy` ENUM `USER|MANAGER`** (`:95-100`).

### `webhook_events` — `payments/webhook-event.model.ts`
- Idempotência de webhook: `externalEventId` unique, `eventType`, `processedAt`. Garante que cada evento de gateway é processado 1x (`webhook.service.ts:74-88`).

### `planos` — `planos/plano.model.ts`
- `nome`, `descricao`, **`tipo` ENUM `mensal|anual|vitalicio`** (`:28-33`), `valorCentavos`.
- **`guaranteeDays`** (dias de garantia/reembolso) + **`refundPercentageCancel`** (`:41-55`) — base da política de reembolso/dunning.
- `externalPlanId`/`externalMpPlanId`, `provider stripe|pix`, `status ACTIVE|ARCHIVED`, `badge`, `features` JSONB.

### `nps_responses` — `nps/nps-response.model.ts`
- PK `id`; `userId` FK; **`trigger` STRING(100)** unique-com-user (`nps_responses_user_id_trigger_unique`, `:25-27`); `score` INT 1-10 nullable; `comment` TEXT nullable. Dedup por par `(userId, trigger)`.

### `atendimentos` — `atendimentos/atendimento.model.ts` (schema **`suporte`**)
- PK `id`; `ticketNumber` STRING(16) (hex de 10 chars, `service.ts:68`); `userId` nullable; `nome`/`email`/`telefone`/`assunto`.
- **`tipo` ENUM `duvida|erro|reclamacao|sugestao|outro`** (`:31-36`); **`status` ENUM `aberto|em_atendimento|resolvido|fechado`** (`:38-43`); **`prioridade` ENUM `baixa|normal|alta|urgente`** (`:45-50`).
- `ip`, `notasInternas`. `HasMany` `AtendimentoMensagem` (que tem `AtendimentoMensagemAnexo` → S3).

### `study_plan_snapshot_*` — `plano-estudo-ia/models/`
- `study-plan-snapshot.model.ts` / `-goal.model.ts` / `-task.model.ts`: snapshot imutável do plano gerado (goals com `goalNumber`, tasks com `status`, `taskType`, `subjectName`, `primaryTopic`, `blockStatusJson`). É a fonte dos triggers de NPS e dos eventos `topic_completed`/`goal_completed`.

---

## 4. Monetização (assinaturas, pagamentos, ciclo de vida)

**Provedores** (`payments/providers/`, registrados em `PaymentProviderRegistry`): **Stripe** (cartão/assinatura), **Asaas** (Pix — ATIVO), **MercadoPago**. Cada um implementa `parseWebhookEvent()` → `NormalizedWebhookEvent`.

**Webhooks IN** — `payments/webhook.controller.ts`:
- `POST /webhooks/payments` (Stripe), `POST /webhooks/mercadopago`, `POST /webhooks/asaas`. Cada um passa `rawBody` + headers para `WebhookService.handleWebhook(provider, payload, headers)`.

**Roteamento de webhook** — `payments/webhook.service.ts:44-72`:
1. `provider.parseWebhookEvent()` normaliza.
2. **Idempotência**: `isEventProcessed(stripeEventId)` consulta `webhook_events` (`:74-88`).
3. Despacha por tipo: `payment` → `handlePaymentEvent` (`:90`); `subscription` → `handleSubscriptionEvent` (`:129`); `pix_billing` → `handlePixBillingCreated`.
4. `markEventProcessed`.

**Ciclo de vida da assinatura** (`handleSubscriptionEvent`, `:129-149`):
- `ACTIVE` → `handleSubscriptionActive` (`:151`): renova `currentPeriodEnd`/limpa `pastDueAt`, ou ativa via `activateFromPaymentAttemptId`.
- `PAST_DUE` → `handleSubscriptionPastDue` (`:176`): marca `pastDueAt` e **`enqueueDunning(sub.id)`** (`:181`).
- `CANCELLED` → **`handleSubscriptionCancelled`** (`:185`): seta `status=CANCELLED`, `cancellationReason='PAYMENT_FAILED'`, `clearUserPlan(userId)`, calcula `daysSubscribed`, dispara PostHog **e Escuta** (`:225`), `enqueueWinback(sub.id)` (`:232`).
  - ⚠️ Hoje o motivo é **hardcoded `PAYMENT_FAILED`** para todo cancelamento via webhook (TODO em `:207-211`): cobre tanto falha de fatura quanto `customer.subscription.deleted` do dashboard. O `properties.source='payment_webhook'` distingue do cancel manual.

**Cancelamento manual (usuário)** — `payments/subscription.service.ts`:
- `finishCancel()` (`:461-499`): aplica reembolso (FULL/PARTIAL conforme `guaranteeDays`/`refundPercentageCancel`), seta status/reason/refund, calcula `daysSubscribed` e dispara Escuta com `source='user_cancel_flow'` (`:487-498`). `reason` aqui pode ser `USER_CANCEL`/`GUARANTEE_REFUND` (mais rico que o webhook).

**Cancelamento por inadimplência (Asaas)** — `payments/asaas-overdue-cancellation.service.ts` (cron `EVERY_DAY_AT_9AM`, gate `CRON_ENABLED`):
- Para assinaturas Asaas vencidas: cancela, `clearUserPlan`, PostHog + **Escuta** com `source='overdue_cron'` (`:78-89`), `enqueueWinback`.

**Reembolso / garantia**: política por plano (`planos.guaranteeDays`, `refundPercentageCancel`); execução em `subscription.service.ts` (`refundSubscription`, `finishCancel`); registros em `refunds`. Histórico de regra em `plan_refund_rule_history`, `plan_guarantee_history`.

**Recuperação (dunning/winback)** — `subscription-recovery/`:
- `SubscriptionRecoveryService.enqueueDunning/enqueueWinback` → fila `SUBSCRIPTION_RECOVERY_QUEUE`, 3 toques cada com `delay` em dias (`DUNNING_DELAYS_DAYS`/`WINBACK_DELAYS_DAYS`), `jobId` `${sequence}:${subId}:${step}` (idempotente) (`service.ts:30-49`).
- `SubscriptionRecoveryProcessor.process` (`processor.ts:49-136`): **respeita `user.marketingOptOut`** (`:67`); aborta se a assinatura já recuperou (dunning→ACTIVE, winback→reativada) e emite `subscription_recovery_succeeded`; senão **manda EMAIL** (`buildDunningEmail`/`buildWinbackEmail`) via `sendMarketingEmail`, grava `email_log`, PostHog `subscription_recovery_email_sent`. **Canal é email, não WhatsApp.**

**Reconciliação** — `payments/subscription-reconciliation.service.ts`: crons (`EVERY_DAY_AT_3AM` reconcilia Stripe/Asaas; `EVERY_HOUR` outros), fila `SUBSCRIPTION_RECONCILE_QUEUE`, tabela `subscription_reconcile_runs`. **Renovação Pix**: `pix-renewal.job.ts` (cron `EVERY_DAY_AT_8AM`) + `pix-renewal.service.ts` (`pix_renewals`).

---

## 5. Camada de IA

**Gateway único**: `ai/ai.service.ts` (1451 linhas) — toda IA passa aqui. Doc interna em `ai/ai.md`.

**Provedores (3) e roteamento por prefixo de modelo** (`ai.service.ts:1350-1356`):
- `model.startsWith('claude-')` → **Anthropic** (`fetch` a `https://api.anthropic.com/v1/messages`, `anthropic-version: 2023-06-01`, `x-api-key`) (`:36,915-941`). Usa prompt caching (`cache_control: ephemeral`) (`:772-783`).
- `gpt-`/`o1-`/`o3-` → **OpenAI** (`fetch` a `/v1/chat/completions`, structured output via `json_schema strict`) (`:37,1221-1246`).
- senão → **Google Gemini** (SDK `@google/genai`, `client.models.generateContent`) — **default** (`:213-224`).

**Modelos default** (`:29-32`): `DEFAULT_MODEL = 'gemini-3.1-flash-lite'`; seletor semântico `DEFAULT_SELECTOR_SEMANTIC_MODEL = 'gpt-5-nano'`; priorização `gemini-3.1-flash-lite`. `resolveModel(step)` permite override por env `MODEL_<STEP>` / `GEMINI_MODEL_<STEP>` (`:144-167`, exemplos em `.env.example:48-67`).

**Robustez**: retry com backoff exponencial respeitando `Retry-After` (`generateWithRetry`, `:978-1006`); **semáforo global** `AsyncSemaphore` cap `LLM_GLOBAL_CONCURRENCY` (default 20, prod 40) p/ proteger quota Gemini (`:94,134-141`); **trace de toda chamada** em `llm_traces` via `LlmTraceService.record` (tokens, custo, latência, status) (`:1111-1156`).

**Onde a IA é usada** (cross-módulo, `ai.md:58-60`): `seletor-questoes-ia` (seleção de questões), `questoes-comentarios-ia` (comentário de questão), **`plano-estudo-ia` (geração do plano de estudos)**, `edital-extractor` (extração de PDF de edital), priorização ECMT, `questao-extracao`, `enriquecimento-questoes`. Também context cache + file search do Gemini (PDF de edital). Chaves: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (`.env.example:34-37`).

---

## 6. Feedback & suporte (crítico p/ Escuta)

### NPS (`nps/`)
- **Modelo**: `NpsResponse` (`nps-response.model.ts`) — tabela `nps_responses`, dedup por `(userId, trigger)`.
- **Triggers calculados server-side** em `NpsService.check(userId)` (`nps.service.ts:34-89`):
  - `FIRST_SESSION` — primeira sessão de questões (externa `ExternalQuestionSession` ou interna `PlanoEstudoQuestao`).
  - `GOAL_HALF:<goalId>` — meta ≥ 50% concluída (tasks `CONCLUIDA|PULADA`, ignorando `REVISAO`).
  - `GOAL_COMPLETE:<goalId>` — meta 100%.
  - A lógica varre `userEditais` → snapshot goals → tasks, e retorna **o primeiro trigger ainda não respondido**.
- **Rotas** (`nps.controller.ts`, todas `JwtAuthGuard`):
  - `GET /nps/check` → `{trigger}` ou `{trigger:null}` (`:28-32`).
  - `POST /nps` (204) → `submit(userId, trigger, score?, comment?)` (`:34-43`); `score` 1-10, opcional; faz upsert (`service.ts:91-103`).
- **Como o front consome**: front chama `GET /nps/check` (ex.: ao abrir o app/dashboard); se vier trigger, mostra o widget; envia `POST /nps`. **NÃO há retry, contexto de canal, nem análise de sentimento** — é puramente armazenamento.
- ⚠️ **Nenhum evento sai do NPS para o Escuta hoje.** `submit()` só grava no banco (`:101`). Oportunidade clara (§7).

### Atendimentos (`atendimentos/`) — tickets por EMAIL
- **Canal**: **SendGrid Inbound Parse** (não WhatsApp). MX de `suporte.bizzu.ai` → `mx.sendgrid.net`; webhook `POST /webhooks/email-inbound` (`inbound-email.controller.ts:7-9,17`). Sempre responde 200 mesmo em erro (SendGrid exige).
- **Fluxo de entrada**: form de contato/`contact` → `create()` (`service.ts:65-96`) gera `ticketNumber` (hex 10), cria `Atendimento` (`status=aberto`, `prioridade=normal`, `tipo` via heurística `detectTipo` por palavras-chave) + 1ª `AtendimentoMensagem`.
- **Resposta do staff**: `reply()` (`:195-226`) cria mensagem `autorTipo=admin`, sobe status `aberto→em_atendimento`, manda email via SendGrid com `reply_to = suporte+<ticketNumber>@suporte.bizzu.ai`.
- **Resposta do usuário por email**: `processInboundEmail()` (`:228-281`) extrai `ticketNumber` do destinatário (`suporte+<hex10>@`), faz strip de citações (`>`), cria mensagem `autorTipo=usuario`, reabre se estava `resolvido/fechado`. Anexos → S3 (`saveAttachments`, expiram em 90 dias; cron de limpeza `0 3 * * *`, `:358`).
- **Status** (lifecycle): `aberto → em_atendimento → resolvido → fechado` (reabre para `aberto` se chega email novo). `updateStatus()` (`:184-193`). Estatísticas em `getStats()`.
- ⚠️ **Sem WhatsApp.** Suporte e voz-do-cliente por WhatsApp são exatamente o vazio que o Escuta preenche.

### Há WhatsApp em algum lugar? **Não.**
Grep por `whatsapp|waha` no backend só retorna: o consentimento `whatsappOptIn` (users/auth/escuta), o `EscutaService`, e docs de spec. Nenhum cliente WAHA, nenhuma API Meta, nenhum envio direto. O único outbound de mensagem é **email (SendGrid)**.

---

## 7. Ganchos de ciclo de vida (eventos para o Escuta ouvir)

### Infra do adapter — `escuta/escuta.service.ts` + `escuta.module.ts`
- `EscutaModule` é **`@Global`** (`escuta.module.ts:11`): qualquer service injeta `EscutaService` sem importar o módulo (mesmo padrão do `TrackingModule`). Importa `SequelizeModule.forFeature([User])`.
- **Config**: `ESCUTA_API_URL` + `ESCUTA_WEBHOOK_SECRET` (`escuta.service.ts:32-33`). Ausentes → loga warn e **desabilita graciosamente** (`captureForUser` vira no-op) (`:34-38,54-56`). ⚠️ **Não estão em `.env.example`** — só no `.env` real.
- **API**: `captureForUser(userId, event, eventId, properties)` (`:48-62`) — **fire-and-forget**: `void this.send(...).catch(warn)`. NUNCA lança nem bloqueia o caller (cancelar assinatura não pode falhar por telemetria).
- **`send()`** (`:64-123`):
  1. Resolve `User` por id; **pula** se não existe ou **se `!phoneNumber`** (`:70-78`).
  2. Monta body: `{event, event_id, user:{id,name,phone,whatsapp_opt_in}, properties}` (`:80-91`).
  3. **Assinatura HMAC-SHA256**: `signature = hmac(secret, `${timestamp}.${body}`)`, headers `X-Escuta-Timestamp`+`X-Escuta-Signature`, `POST {baseUrl}/api/events/bizzu`, timeout 5s (`:93-107`).
  4. Espera resposta `{dispatched?, reason?}` e loga (`:114-122`).
- **Idempotência**: via `event_id` estável; o Escuta deduplica. Cooldown/throttle é do lado do Escuta (comentário em `plano-estudo-ia.service.ts:2040-2042`: "dedupe por event_id + cooldown de 7 dias por contato+survey").

### Eventos JÁ plugados (em produção)

| Evento | `event_id` | Onde dispara | properties | Estado |
|---|---|---|---|---|
| **`subscription_cancelled`** | `sub:<extSubId>` | webhook pagamento `payments/webhook.service.ts:225` | `plan_id, reason='PAYMENT_FAILED', days_subscribed, provider, source='payment_webhook'` | ✅ |
| **`subscription_cancelled`** | `sub:<extSubId\|id>` | cancel manual `payments/subscription.service.ts:487` | `plan_id, reason(USER_CANCEL/GUARANTEE_REFUND/…), days_subscribed, provider, source='user_cancel_flow'` | ✅ |
| **`subscription_cancelled`** | `sub:<extSubId\|id>` | cron inadimplência `payments/asaas-overdue-cancellation.service.ts:78` | `plan_id, reason='PAYMENT_FAILED', days_subscribed, provider='asaas', source='overdue_cron'` | ✅ |
| **`topic_completed`** | `task:<taskId>` | `plano-estudo-ia/plano-estudo-ia.service.ts:2050` (via `notifyEscutaOfTaskCompletion`) | `task_id, task_type, subject_name, topic, goal_id, goal_progress(%), goal_completed` | ✅ |
| **`goal_completed`** | `goal:<goalId>` | `plano-estudo-ia/plano-estudo-ia.service.ts:2066` | `goal_id, goal_number, last_task_id, tasks_in_goal` | ✅ |

- `notifyEscutaOfTaskCompletion` (`plano-estudo-ia.service.ts:2044-2073`) é chamado de **4 pontos**: `updateTaskStatus` (`:344`), `updateTaskBlockStatus` (`:376`), e dois outros caminhos de finalização (`:1005`, `:2558`). Dispara `topic_completed` só quando `task.status==='CONCLUIDA'` (PULADA não conta) e `goal_completed` quando `completion.allFinal`.
- Os 3 cancelamentos usam **`event_id` por assinatura** → se o provedor ecoar o cancelamento (webhook) depois de um cancel manual, o Escuta entrega só 1 survey.

### Consentimento (já implementado)
- **Signup**: `signup.dto.ts:19-22` aceita `whatsappOptIn`; `auth.service.ts:46-48` só liga se `telefone` informado, carimba `whatsappOptInAt`.
- **Perfil**: `users/users.service.ts:534-549` (`PATCH /user/me`) — ligar exige telefone; preserva data original em reenvios; desligar limpa o carimbo.
- Migration `20260607130000-add-whatsapp-opt-in-to-usuarios.js` (colunas `whatsappOptIn`/`whatsappOptInAt`).
- ⚠️ **O backend não filtra eventos por `whatsappOptIn`** — só envia o flag no payload (`escuta.service.ts:88`). **O Escuta é quem deve respeitar o opt-in** antes de disparar a mensagem.

### Eventos que FALTAM (oportunidades)

| Evento candidato | Existe gancho? | Onde plugar | Dados disponíveis |
|---|---|---|---|
| **`signup` / novo usuário** | ❌ (só cart-abandonment) | após `user.save()` em `auth.service.ts:52` (e OAuth `:191`) | userId, nome, email, telefone, whatsappOptIn |
| **`plano_gerado`** | ❌ | após persistir snapshot no `plano-estudo-ia` (geração do plano) | userId, userEditalId, editalCargoId, nº goals/tasks |
| **`nps_submitted`** | ❌ | `nps/nps.service.ts:101` (`submit`) | userId, trigger, score, comment — espelharia NPS no Escuta |
| **`payment_recovered` / `reactivated`** | ⚠️ só PostHog (`subscription-recovery.processor.ts:138`) | `captureSucceeded` | userId, sequence, subscriptionId |
| **`first_session` / engajamento inicial** | ⚠️ derivável (NPS já calcula) | onde `ExternalQuestionSession`/`PlanoEstudoQuestao` é criada | userId |
| **aprovação em concurso** | ❌ **não existe no modelo** | — | seria feature nova (sem `ExamResult`/registro de aprovação) |

---

## 8. Observabilidade / jobs

**Crons** (`@Cron`, quase todos com gate `CRON_ENABLED==='true'` + redis-lock single-flight):
- `payments/asaas-overdue-cancellation.job.ts:15` — `EVERY_DAY_AT_9AM` (cancela inadimplente Asaas → dispara Escuta + winback).
- `payments/pix-renewal.job.ts:15` — `EVERY_DAY_AT_8AM` (cobrança de renovação Pix).
- `payments/subscription-reconciliation.service.ts:61,177,233` — `EVERY_DAY_AT_3AM` + `EVERY_HOUR` (reconciliação Stripe/Asaas).
- `atendimentos/atendimentos.service.ts:358` — `0 3 * * *` (limpeza de anexos S3 expirados).
- `llm-traces/llm-trace.service.ts:183` — `0 3 * * *` (limpeza de traces).
- `radar-sync/radar-sync.orchestrator.ts:54` — default `0 5 * * *` (sync diário do Radar; gate `RADAR_SYNC_ENABLED`).
- `auto-pipeline/auto-pipeline.orchestrator.ts:50` — `*/15 * * * * *` (tick do orquestrador; gate `AUTO_PIPELINE_ENABLED`).
- `enriquecimento-questoes/engine/enrichment-poller.service.ts:129` — poller de enriquecimento.

**Filas BullMQ** (`@Processor`, rodam no `worker.ts`):
- `CART_ABANDONMENT_QUEUE` (4 emails pós-signup) — `cart-abandonment/`.
- `SUBSCRIPTION_RECOVERY_QUEUE` (dunning+winback, email) — `subscription-recovery/`.
- `MARKETING_EMAIL_QUEUE` + `SUBSCRIPTION_RECONCILE_QUEUE` — `gestao/` e `payments/`.
- `PRICE_CHANGE_QUEUE` — campanhas de preço.
- `bizzu-generation` (`BIZZU_QUEUE_NAME`) — geração de "bizzus"/resumos IA (concurrency 1, lock 300s).
- `selector` — seletor de questões IA (concurrency 2).
- `study-plan-reselect`, `study-plan-template-generation` — plano IA.
- `edital-extraction` / `edital-organization` / `prioritization` — pipeline de edital.
- `questao-comentario-ia`, `questao-extracao-queue`, `enrichment-questoes` — IA de questões.
- `site-content` — geração de conteúdo SEO.

**Tracking (PostHog)** — `tracking/posthog-tracking.service.ts`: `@Global`, `capture({userId, event, properties})` fire-and-forget (`:27-42`), adiciona `source:'backend'`, desabilita sem `POSTHOG_PROJECT_TOKEN`. Eventos: `subscription_cancelled`, `subscription_recovery_email_sent`, `subscription_recovery_succeeded`, etc. **O Escuta espelha o mesmo padrão** (mesmo desenho de `capture` fire-and-forget) — convivem lado a lado nos mesmos call sites de churn.

**Logging** — Pino + `nestjs-pino` (`main.ts:22`), `LOG_LEVEL`/`LOG_PRETTY` (`.env.example:4-7`), hooks de exceção de processo (`logging/process-exception-hooks`).

**LLM observability** — tabela `llm_traces` (`llm-traces/`) com tokens/custo/latência/status de toda chamada de IA.

---

## 9. Segurança & dívida técnica

> **Sem valores reais de segredo abaixo — só localização.** Todas as chaves vêm de env / AWS Secrets Manager.

- **Segredos por env (não hardcoded no código-fonte):** `JWT_SECRET`, `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`, `ASAAS_API_KEY`, `SENDGRID_API_KEY`, `LEADS_API_KEY`, `GEMINI/OPENAI/ANTHROPIC_API_KEY`, `RADAR_SERVICE_API_KEY`, AWS keys, **`ESCUTA_WEBHOOK_SECRET`** — todos referenciados via `ConfigService`/`process.env` (`.env.example` documenta os nomes; prod usa AWS Secrets Manager, ver comentários `Secret prod: prod/plataforma/*` em `.env.example:87,91`).
- ⚠️ **`.env.example` não lista `ESCUTA_API_URL`/`ESCUTA_WEBHOOK_SECRET`** — risco de quebra silenciosa em novo deploy (o service só loga warn e fica inerte: `escuta/escuta.service.ts:34-38`). **Adicionar ao `.env.example`.**
- ⚠️ **`.env.example:21` traz `JWT_SECRET=super-secret-change-me`** como placeholder — garantir que prod não usa o default.
- ⚠️ **`DATABASE_SYNCHRONIZE` controlado por env** (`app.module.ts:113-115`): `.env.example:17` põe `true` em dev. Em prod deve ser **false** (migrations mandam). `synchronize:true` em prod pode alterar schema inadvertidamente.
- ⚠️ **SSL do Postgres em prod com `rejectUnauthorized:false`** (`app.module.ts:138`) — aceita cert não verificado (comum em RDS, mas é downgrade de segurança).
- **Webhooks de pagamento**: idempotência via `webhook_events.externalEventId` unique (`webhook.service.ts:74-88`) e verificação de assinatura delegada a cada provider (`parseWebhookEvent(payload, headers)` com `rawBody`). Bom. Eventos `unknown`/sem `externalId` são ignorados (`:52-54`).
- **TODO relevante**: `payments/webhook.service.ts:207-211` — motivo de cancelamento **hardcoded `PAYMENT_FAILED`** para todo cancel via webhook; não distingue involuntário vs voluntário. Afeta a qualidade do `reason` que chega ao Escuta (exit survey) e ao PostHog.
- **`captureExemploEmail`** (`leads-api/leads-api.service.ts:522-529`) faz INSERT com `:source` em coluna `editalNome` — uso de SQL cru, mas parametrizado (`replacements`), sem injeção. A LeadsApi inteira usa SQL cru parametrizado (ok).
- **Auth da LeadsApi**: header estático `X-API-Key` (`leads-api/api-key.guard.ts`) — server-to-server simples; rotacionar `LEADS_API_KEY` se vazar.
- **`atendimentos` aceita inbound de qualquer remetente** (SendGrid Inbound Parse) e casa por `ticketNumber` no destinatário (`suporte+<hex10>@`); conteúdo é texto (strip de `>`), anexos limitados a 5/10MB e mime allowlist (`service.ts:265-273`) — razoável; o `ticketNumber` hex de 10 chars é o "segredo" do thread.
- **PII em payload Escuta**: `name` + `phone` saem do backend para o Escuta a cada evento (`escuta.service.ts:80-91`) — fluxo legítimo, mas é dado pessoal cruzando serviço; o HMAC protege integridade/origem, **mas o canal precisa ser HTTPS** (garantir `ESCUTA_API_URL` https).

---

## 10. Pontos de integração de maior valor (recomendações)

1. 🥇 **Churn (já plugado, 3 caminhos)** — `subscription_cancelled` é o evento mais rico (motivo, dias de assinatura, plano, source). Garantir que o Escuta dispara o exit-survey **respeitando `whatsapp_opt_in`** e com cooldown para não colidir com o **email de winback** que o Bizzu já manda (`subscription-recovery`).
2. 🥈 **`nps_submitted` (falta)** — plugar `EscutaService.captureForUser` em `nps/nps.service.ts:101` unificaria a análise de NPS in-app com a voz-do-cliente no WhatsApp. Trivial e dados já estruturados (`trigger`, `score`, `comment`).
3. 🥉 **`signup` (falta)** — evento de boas-vindas/onboarding no Escuta a partir de `auth.service.ts:52` (e OAuth `:191`); já há telefone+opt-in no signup.
4. **`plano_gerado` (falta)** — sinaliza ativação real (aluno passou do cadastro ao plano IA); ótimo gatilho de pesquisa de expectativa.
5. **Bootstrap de contatos** — sync inicial de `usuarios` com `phoneNumber` + `whatsappOptIn=true` para o Escuta popular a base (hoje os eventos só carregam um contato por vez, sob demanda).
6. **Enriquecer `reason` do churn** (resolver TODO `webhook.service.ts:207`) para o exit-survey diferenciar "cartão falhou" de "cancelou de propósito".
