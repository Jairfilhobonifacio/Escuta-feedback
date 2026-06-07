# Relatório do agente — Backend Bizzu (gabarita-ai/backend)

> Exploração automática em 07/06/2026. Clone local: `~/Documents/Projetos/bizzu-repos/backend`.
> Consolidação executiva em `../INTEGRACAO_BIZZU.md`.

## 1. Stack técnico

**Linguagem & Framework:** TypeScript + NestJS 10.4
**Banco de Dados:** PostgreSQL (Sequelize 6.37 ORM)
**Filas & Jobs:** BullMQ 5.71 + Redis (ioredis 5.10)
**Porta:** 3000 (configurável via `PORT` env var)
**Pagamento:** Stripe + Asaas (Pix) + MercadoPago
**Analytics:** PostHog (server-side)
**Email:** SendGrid (principal) + SendKit (legado, migrado mai/2026)
**Logging:** Pino 10.3 + nestjs-pino

**Entrypoint:** `src/main.ts` – bootstraps com `bootstrapEnv()` → NestFactory.create(AppModule)

**Variáveis de ambiente principais (sem valores):**
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`
- `JWT_SECRET`, `JWT_EXPIRES_IN`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `ASAAS_API_KEY` (Pix payments)
- `SENDGRID_API_KEY`
- `REDIS_URL` (ou `REDIS_HOST`/`REDIS_PORT`)
- `LEADS_API_KEY` (static key para Leads API server-to-server)
- `CORS_ORIGINS`, `FRONTEND_URL`, `APP_URL`

## 2. Modelo de usuário

**Tabela:** `usuarios` (Sequelize model em `src/users/user.model.ts`)

Campos relevantes para o Escuta:
```
- id: UUID (primary key)
- primeiroNome, ultimoNome: string
- email: string (unique)
- telefone: string | null            ✓ CAMPO JÁ EXISTE
- planoId: UUID | null (plano ativo)
- pendingPlanoId: UUID | null (escolhido mas não pago)
- role: CANDIDATE | MANAGER
- marketingOptOut: boolean           ✓ CONSENTIMENTO JÁ EXISTE (genérico)
- marketingOptOutAt: Date | null
- googleId, passwordHash, cpfEncrypted
- asaasCustomerId
- createdAt, updatedAt, deletedAt (paranoid=true)
```

Observações:
- Não há coluna específica de opt-in WhatsApp — só `marketingOptOut` (booleano geral)
- LGPD via `marketingOptOut` + unsubscribe SendGrid

## 3. Eventos de ciclo de vida (pontos exatos de hook)

### (a) Usuário se cadastra
- **Arquivo:** `src/auth/auth.service.ts:24-53` — `AuthService.signup()`
- L48: `user.save()`; L49-51: `CartAbandonmentService.enqueueSequence()`
- **Hook:** após L48. Dados: userId, email, nome, telefone (se fornecido)

### (b) Plano de estudos é gerado
- **Arquivo:** `src/plano-estudo-ia/plano-estudo-ia.service.ts:145-180` — `generatePlan()`
- L177: `persistSnapshot()` cria StudyPlanSnapshot + goals + tasks
- **Hook:** após L177. Dados: userId, userEditalId, editalCargoId

### (c) Tópico/meta concluído
- **Arquivo:** `src/plano-estudo-ia/plano-estudo-ia.service.ts:308-337` — `updateTaskStatus()`
- L327: `task.save()`; L329: `checkGoalCompletion(task)`
- Status: `EM_PROGRESSO`, `PULADA`, `CONCLUIDA`
- **Hook:** após L327. Dados: userId, taskId, newStatus, goalId, completionPercentage

### (d) Assinatura cancelada (churn)
- **Arquivo:** `src/payments/webhook.service.ts:183-223` — `handleSubscriptionCancelled()`
- L188-192: `subscription.update({status:'CANCELLED',...})`; L193: `clearUserPlan(userId)`; L221: `subscriptionRecovery.enqueueWinback()`
- **Hook:** após L193. Dados: userId, subscriptionId, planId, daysSubscribed, cancelledAt, reason (PAYMENT_FAILED|USER_CANCEL)
- Alternativas: cancel manual em `subscription.service.ts`; overdue em `asaas-overdue-cancellation.service.ts:82`

### (e) Aprovação em concurso
- ❌ NÃO EXISTE no código (sem ExamResult/ApprovalRegistry). Seria fluxo novo.

## 4. Notificações existentes

**Email (SendGrid):** sendBoasVindas (pós-pagamento), sendPasswordResetEmail, sendMarketingEmail, sendPixCobrancaEmail, sendEditalSolicitacaoAlert (staff), sendQuestionReportAlert (staff)

**Filas BullMQ:**
1. `CART_ABANDONMENT_QUEUE` — pós-signup (recuperação de carrinho)
2. `MARKETING_EMAIL_QUEUE`
3. `BIZZU_QUEUE_NAME` — geração de resumos IA
4. `SUBSCRIPTION_RECONCILE_QUEUE` — reconciliação Stripe/Asaas
5. `SUBSCRIPTION_RECOVERY_QUEUE` — dunning & win-back pós-churn

**Webhooks IN:** `POST /webhooks/payments` (Stripe), `/webhooks/mercadopago`, `/webhooks/asaas`
**Webhooks OUT:** ❌ nenhum — sistema não envia webhooks a terceiros (PostHog capture apenas)

## 5. Pagamentos

Stripe + Asaas (Pix) + MercadoPago. Fluxo: gateway → `POST /webhooks/{provider}` → `WebhookService.handleWebhook()` normaliza → `handleSubscriptionCancelled()`/`handleSubscriptionActive()`.
Tabelas: `subscriptions` (ACTIVE/CANCELLED/EXPIRED/REFUNDED/PAST_DUE), `payment_attempts`, `refunds`.

## 6. API

REST JSON (NestJS). Auth JWT (`{sub, email, planId, role}`, 30 dias). Sem API key admin pública (JWT role=MANAGER). `LEADS_API_KEY` para `/leads/*` server-to-server.

| Endpoint | Método | Auth |
|---|---|---|
| `/auth/signup` | POST | — |
| `/auth/login` | POST | — |
| `/plano-estudo-ia/gerar` | POST | JWT |
| `/plano-estudo-ia/tasks/:taskId/status` | PATCH | JWT |
| `/user/subscription` | GET | JWT |
| `/user/subscription/cancel` | POST | JWT |
| `/nps/check` | GET | JWT |
| `/nps` | POST | JWT |
| `/leads/*` | GET | API Key |
| `/webhooks/*` | POST | assinatura |

## 7. NPS existente

**Modelo:** `NpsResponse` (`src/nps/nps-response.model.ts`) — tabela `nps_responses`:
`id, userId, trigger (dedup por user+trigger), score (1-10|null), comment (text|null)`

**Triggers:** `FIRST_SESSION`, `GOAL_HALF:${goalId}`, `GOAL_COMPLETE:${goalId}`
**Endpoints:** `GET /nps/check` → `{trigger}|null`; `POST /nps` → 204

É básico (sem contexto/retry/análise) — ideal pra integrar/espelhar no Escuta.

## Os 3 pontos de integração de maior valor

1. 🥇 **Churn** — `webhook.service.ts:193` (já estruturado; dados ricos; exit survey ouro)
2. 🥈 **Tópico concluído** — `plano-estudo-ia.service.ts:327` (alta frequência, engajamento)
3. 🥉 **NPS submitted** — `nps.service.ts:101` (trivial, dados estruturados, análise unificada)

**Próximos passos:** criar `src/escuta/escuta.service.ts` (adapter HTTP POST + HMAC) injetado em PaymentsModule/PlanoEstudoIaModule/NpsModule; endpoint de eventos no Escuta; batch sync de usuários (bootstrap de contatos).
