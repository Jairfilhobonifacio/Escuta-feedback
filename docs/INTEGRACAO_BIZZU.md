# Integração Escuta ↔ Bizzu — Mapa Consolidado

> Gerado em 07/06/2026 a partir da exploração dos 6 repositórios da org `gabarita-ai`
> (frontend, backend, radar-editais, infra, site, landing-pages) por 5 agentes em paralelo.
> Clones locais em `~/Documents/Projetos/bizzu-repos/`.

## TL;DR

- **Backend Bizzu = NestJS 10 + Sequelize/Postgres (RDS) + BullMQ/Redis, AWS us-east-1, Terraform.**
- **Telefone do usuário JÁ existe** (`usuarios.telefone`, capturado no signup com validação) e
  **consentimento geral JÁ existe** (`marketingOptOut`). Falta opt-in específico de WhatsApp.
- **A Bizzu JÁ TEM NPS in-app** (modelo `NpsResponse`, `GET /nps/check` + `POST /nps`,
  modal no frontend, triggers `FIRST_SESSION` / `GOAL_HALF` / `GOAL_COMPLETE`) — básico, sem
  análise. O Escuta entra como **camada conversacional WhatsApp + gestão/insight**, não como
  substituto imediato.
- **Não há webhooks OUT** na Bizzu (só IN, de pagamento). A integração exige criar um
  `EscutaService` (adapter) no NestJS que faça POST pros nossos endpoints.
- Eles **não notificam usuários por WhatsApp em nada hoje** — nem o radar-editais (que detecta
  edital novo diariamente e seria um canal de altíssimo valor percebido).

## Os 3 ganchos de maior valor no backend (arquivo:linha)

| # | Evento | Onde plugar | Dados disponíveis |
|---|--------|-------------|-------------------|
| 🥇 | **Churn** (assinatura cancelada) | `src/payments/webhook.service.ts:193` (após `clearUserPlan`) — cobre Stripe/Asaas/MercadoPago; manual em `subscription.service.ts` | userId, planId, daysSubscribed, reason (PAYMENT_FAILED/USER_CANCEL) → **exit survey ouro p/ churn** |
| 🥈 | **Tópico/meta concluído** | `src/plano-estudo-ia/plano-estudo-ia.service.ts:327` (após `task.save()` + `checkGoalCompletion`) | userId, taskId, goalProgress %, status CONCLUIDA → CSAT de qualidade do conteúdo |
| 🥉 | **NPS in-app respondido** | `src/nps/nps.service.ts:101` (create/update do NpsResponse) | userId, trigger, score, comment → espelhar no Escuta p/ análise unificada |

Outros ganchos mapeados: signup (`auth.service.ts:48`), plano gerado
(`plano-estudo-ia.service.ts:177`). **"Aprovação em concurso" NÃO existe** no código — seria
fluxo novo (valioso p/ depoimentos reais: hoje os do site são hardcoded/fake).

## Padrão de integração recomendado

```
Bizzu NestJS ──(novo EscutaService: POST + HMAC)──▶ Escuta FastAPI /api/events/bizzu
                                                        │
                                              regra: evento → survey certa
                                                        │
                                              SurveyDispatcher → WAHA → WhatsApp
```

1. Criar `src/escuta/escuta.service.ts` no backend deles (módulo NestJS, HTTP POST com
   assinatura HMAC, fire-and-forget com fila BullMQ que já existe).
2. No Escuta: endpoint `POST /api/events/bizzu` que mapeia `event` → survey → dispatch.
3. Opt-in: adicionar campo específico (`whatsappOptIn`) — hoje só há `marketingOptOut` genérico.

## Opt-in WhatsApp — onde capturar (frontend Vite/React 18)

| Local | Arquivo | Nota |
|---|---|---|
| **Signup** (melhor taxa) | `src/pages/Signup.jsx` ~linha 299 (já captura telefone c/ `react-phone-number-input`) | checkbox ao lado do telefone |
| **Pós-pagamento** (melhor contexto) | `src/pages/PagamentoSucessoPage.jsx` | card CTA "ativar WhatsApp" |
| **Minha Conta** (melhor qualidade) | `src/pages/MinhaContaPage.jsx` (seção Dados Cadastrais) | toggles de preferência |

Frontend já tem: `NpsModal.jsx` + `useNpsCheck.js` (modal NPS in-app) e exit survey no
cancelamento (`MinhaAssinaturaPage.jsx:101-140`).

## radar-editais — sinergia de canal

Monitor diário de concursos (FastAPI + Postgres próprio porta 5434 + Gemini + S3), flag
`interesse_bizzu`, **sem nenhuma notificação a usuários hoje**. Gancho: `pipeline.py` fase
ENRICH+PERSIST → evento `novo_edital` → WhatsApp "saiu edital do seu concurso" (+ aproveita o
contato pra manter relação viva). Auth de serviço via `X-Radar-Api-Key` (HMAC) já existe.

## Site/landing — captação

Captam SÓ email via Google Forms (entry.19628127), **sem telefone/WhatsApp em lugar nenhum**,
sem link wa.me. Oportunidade: campo WhatsApp + opt-in na waitlist (lead já chega "conversável").
Depoimentos do site são hardcoded — fluxo "aprovado → review real" do Escuta substitui.

## Infra — onde o Escuta vai morar (quando sair do localhost)

AWS us-east-1, Terraform modular (`infra/modules/`), secrets no AWS Secrets Manager
(`prod/plataforma/*`), state em S3. Caminho natural: módulo `escuta-ec2` (t4g.small ARM),
`escuta.bizzu.ai` (wildcard ACM já cobre), SG próprio, secret `prod/escuta/*`. WAHA roda como
container na mesma instância. RDS deles ≠ nosso Supabase (mantemos separado; multi-tenant é nosso).

## Identidade visual Bizzu (p/ materiais white-label)

- Indigo `#6C5CE7` (primária) · Gold `#F5A623` (acento) · dark-first (`--void #09090B`/`#0c0b10`)
- Fontes: Space Grotesk (títulos) + Inter/DM Sans (corpo) + JetBrains Mono (dados)
- Gradiente assinatura: `#6C5CE7 → #A78BFA → #F5A623`

## ✅ PoC do gancho de churn — IMPLEMENTADO E VALIDADO E2E (07/06/2026)

Funil real comprovado em dev local: `POST /user/subscription/cancel` (API Bizzu 3100, JWT
real) → `finishCancel` → `EscutaService.captureForUser('subscription_cancelled')` →
`POST /api/events/bizzu` (HMAC ok) → survey "Exit Bizzu" → **mensagem entregue no
WhatsApp real** (channel_msg_id `..._out`).

**Lado Escuta** (commitado neste repo):
- `POST /api/events/bizzu` (`app/api/events.py`): HMAC-SHA256 (`{ts}.{body}`, tolerância
  5 min), get-or-create de contato (consentimento vem do emissor; nunca rebaixa),
  idempotência por `event_id` (`SurveyRun.trigger = bizzu:<event>:<event_id>`),
  cooldown 7 dias por contato+survey, respostas sempre 202 `{dispatched, reason}`.
- Survey type **'exit'**: 1ª pergunta `kind='open'`, response nasce `awaiting_reason`
  (resposta de texto fecha — zero mudança na máquina de estados). `surveys.trigger_event`
  liga evento→survey (migration `20260607_trigger_event`). Agradecimento custom via
  pergunta `kind='thanks'`.
- Env nova: `BIZZU_WEBHOOK_SECRET` (compartilhada com o backend Bizzu).

**Lado Bizzu** (NÃO commitado — clone é leitura; patch completo em
`docs/patches/bizzu-backend-escuta-churn-hook.patch`):
- `src/escuta/{escuta.module.ts,escuta.service.ts}` — módulo @Global espelhando o
  TrackingModule; `captureForUser` fire-and-forget, no-op sem envs (safe em prod),
  resolve telefone/nome via `User.findByPk`, `whatsapp_opt_in = !marketingOptOut`
  (proxy até existir o campo dedicado).
- Ganchos nos 3 cancelamentos: `webhook.service.ts` (PAYMENT_FAILED via provedor),
  `subscription.service.ts#finishCancel` (USER_CANCEL/GUARANTEE_REFUND) e
  `asaas-overdue-cancellation.service.ts` (cron de inadimplência). `event_id`
  estável `sub:<externalSubscriptionId|id>` → dedupe entre fluxo manual e eco do webhook.
- Specs atualizados (27/27 verdes): novo parâmetro posicional nos construtores.
- Envs novas: `ESCUTA_API_URL` + `ESCUTA_WEBHOOK_SECRET`.

Pegadinhas de dev local descobertas (detalhe no SESSAO_HANDOFF): `DATABASE_SYNCHRONIZE`
deve ser `false` (sync tenta ALTER de enum e crasha); forward de portas do Podman p/
binding `0.0.0.0` ficou IPv6-only após restart da machine → containers recriados com
`-p 127.0.0.1:<porta>:<porta>`; boot exige `GEMINI_API_KEY` não-vazia (placeholder).

## ✅ Opt-in dedicado + sync de contatos (07/06/2026, mesma sessão)

- **`usuarios.whatsappOptIn` + `whatsappOptInAt`** (migration `20260607130000`, aplicada
  local): consentimento específico de WhatsApp com carimbo p/ auditoria LGPD; espelha o
  par `marketingOptOut`/`At`. Signup só grava `true` se houver telefone. `EscutaService`
  passou a usar o campo dedicado (proxy `!marketingOptOut` aposentado). Specs auth 21/21.
- **Checkbox no Signup.jsx**: aparece quando o telefone digitado é válido; microcopy
  honesta ("sem spam, dá pra sair quando quiser"). Patch: `bizzu-frontend-whatsapp-opt-in.patch`.
- **`scripts/sync_bizzu_contacts.py`** (repo Escuta): upsert 1-sentido Bizzu→Escuta
  (telefone + whatsappOptIn + não-deletados): cria com opt_in, eleva opt_in, preenche
  nome/`bizzu_user_id` sem sobrescrever. Idempotente, `--dry-run` disponível, não
  dispara mensagens. Env `BIZZU_DATABASE_URL` (default = dev local).

## ✅ Rodada de 4 agentes paralelos (07/06/2026, noite — tudo verde)

1. **Toggle opt-in na MinhaConta** (`PATCH /user/me` reusado; ligar exige telefone,
   carimbo `whatsappOptInAt` só na transição OFF→ON p/ preservar a data original do
   consentimento; checkbox com estado desabilitado + dica sem telefone). Users specs
   58/58; validado ao vivo (desligou→religou→carimbo novo→estado restaurado).
2. **Gancho `topic_completed`** em `plano-estudo-ia.service.ts` via helper único
   `notifyEscutaOfTaskCompletion` nos **4 caminhos** onde task vira CONCLUIDA
   (updateTaskStatus L344, updateTaskBlockStatus L376, completeReviewTopicQuestions
   L1005, createExternalQuestionSession L2558) + **`goal_completed`** quando
   `checkGoalCompletion` retorna allFinal. `event_id=task:<id>`/`goal:<id>`.
   Properties: task_type, subject_name, topic, goal_progress, goal_completed.
   Specs plano-estudo-ia 275/275.
3. **Survey 'CSAT Tópico Bizzu'** no Escuta (type='nps' — escala 0-10 única do
   produto; trigger_event='topic_completed'; 3 perguntas c/ thanks custom). Seedada
   no Supabase (id b18a4736). Suíte 39→40 testes. **Smoke E2E real**: evento assinado
   → `dispatched=true` → pergunta entregue no WhatsApp.
4. **Dashboard segmentado por tipo**: KPIs NPS calculados SÓ sobre surveys type='nps'
   (bloco `nps`, alias `kpis` retrocompat); bloco `exit` novo {sent, answered,
   recent: últimos 10 motivos}; `recent` geral com `survey_type`/`survey_name` +
   badges no painel; card "Motivos de cancelamento". Validado visualmente com dados
   reais (screenshot `_painel_exit_check.png`).

## Próximos passos sugeridos (ordem)

1. ~~PoC do gancho de churn~~ ✅ · 2. ~~whatsappOptIn + Signup~~ ✅ ·
   3. ~~Sync de contatos~~ ✅ · 4. ~~Toggle MinhaConta~~ ✅ ·
   5. ~~Gancho CSAT tópico/meta~~ ✅ · 6. ~~Painel exit vs NPS~~ ✅
7. Espelho do NPS in-app (`nps.service.ts:101` → evento `nps_submitted`; exige
   modo "ingest sem disparo" no Escuta — registrar resposta vinda de outro canal).
8. radar-editais → notificação de edital novo (canal de valor, não pesquisa).
9. Apresentar os 2 patches ao time da Bizzu (PR nos repos deles) quando o piloto
   for aprovado — backend 1017 linhas, frontend 127 linhas, tudo com specs verdes.
10. Backend: desligar opt-in automaticamente se telefone for removido em request
    que não mencione whatsappOptIn (anotado pelo agente; sender já filtra por phone).
11. Infra: módulo Terraform `escuta-ec2` quando o piloto local validar.
