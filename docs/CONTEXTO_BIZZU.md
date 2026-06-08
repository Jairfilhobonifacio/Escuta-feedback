# CONTEXTO BIZZU — visão consolidada do ecossistema

> Síntese da análise profunda dos **6 repositórios** da org GitHub `gabarita-ai`
> (todos privados), feita por 6 agentes em 08/06/2026. Os relatórios detalhados
> por repo estão em `docs/analise-bizzu/{backend,frontend,infra,radar-editais,site,landing-pages}.md`.
> Este documento é a leitura de cima — o "mapa" do ecossistema e das oportunidades para o Escuta.

---

## 1. O que é a Bizzu

Edtech de **planejamento de estudos para concursos públicos com IA**. Posicionamento explícito:
**não é curso, não vende aulas** — organiza o estudo cruzando o edital do aluno com dados reais
de **600 mil+ questões**. Produto central: **Raio X da Prova** (ranking de tópicos por prioridade,
por banca + cargo + órgão). App em `plataforma.bizzu.ai`; site em `bizzu.ai`.

**Estágio:** lançamento recente. Preço (declarado no site): **R$ 10/mês ou R$ 60/ano** (promo de
lançamento "até 20/05", já vencida; cheio R$ 60/mês ou R$ 650/ano), **garantia de 7 dias, sem
fidelidade**. As *landing-pages* de campanha não repetem preço.

---

## 2. O ecossistema — 6 repos e como se conectam

```
        ┌─────────────┐         ┌──────────────┐        ┌─────────────────┐
        │ site (bizzu  │  CTA →  │  frontend    │  HTTP  │   backend       │
        │ .ai) Next16  │ signup  │ (app web)    │◄──────►│ (NestJS API)    │
        │ + landings   │         │ Vite/React   │  JWT   │ api.bizzu.ai    │
        └─────────────┘         └──────────────┘        └────────┬────────┘
          captação só email                                      │
          (Google Forms)                          ┌──────────────┼───────────────┐
                                                   ▼              ▼               ▼
                                            ┌──────────┐  ┌────────────┐  ┌──────────────┐
                                            │ RDS PG    │  │ BullMQ/    │  │ radar-editais │
                                            │ (Sequelize)│  │ Redis jobs │  │ (FastAPI,     │
                                            └──────────┘  └────────────┘  │ PG próprio    │
                                                                          │ :5434, 1x/dia)│
        ┌──────────────────────────────────────────┐                     └──────────────┘
        │ infra (Terraform/AWS us-east-1, 11 módulos)│  ← provisiona tudo acima + onde o Escuta entra
        └──────────────────────────────────────────┘
```

| Repo | Stack | Papel |
|------|-------|-------|
| **backend** | NestJS 10 + Sequelize 6 + Postgres + BullMQ/Redis | o cérebro: API, monetização, IA, NPS, suporte |
| **frontend** | Vite 6 + React 18.3 + Tailwind v4 + React Router 7 (sem TS) | o app web do aluno + painel `/gestao` |
| **radar-editais** | FastAPI + Postgres próprio (:5434) + Gemini + S3 | detecta editais novos diariamente |
| **infra** | Terraform ≥1.0 + AWS us-east-1 (state S3) | provisiona EC2/RDS/rede/secrets/DNS |
| **site** | Next.js 16 + React 19 + TS | institucional + páginas de edital (SEO) |
| **landing-pages** | HTML estático | campanhas + relatórios "Raio X" públicos |

---

## 3. Jornada do usuário (do lead ao churn)

```
lead (site/landing)            aluno ativo                              risco
   │  só email,                   │  estuda                               │
   │  zero WhatsApp               │                                       │
   ▼                              ▼                                       ▼
/signup → /checkout → /onboarding → núcleo de estudo → /minha-conta → CANCELAMENTO
(auto-login,  (Stripe/   (edital+    (plano-de-estudo,   (assinatura)   (window.confirm
 telefone     Pix)       cargo →     raio-x, questões,                    SECO, sem
 opcional)               rotina)     caderno, revisões)                   exit survey)
                                          │
                                    NPS in-app (modal 0-10) nos marcos
                                    FIRST_SESSION / GOAL_HALF / GOAL_COMPLETE
```

Pontos de contato com o aluno hoje: **e-mail** (winback, suporte) e **modal in-app** (NPS).
**Nenhum WhatsApp em ponto algum do ecossistema** — esse é o vão que o Escuta ocupa.

---

## 4. Monetização & churn (backend)

- **Pagamentos:** Stripe (cartão) + Asaas (Pix) + MercadoPago. Webhooks de pagamento processam o
  ciclo `active → past_due → cancelled`; reembolso dentro da garantia de 7 dias.
- **Recuperação:** dunning + **winback por e-mail** (módulo `subscription-recovery`) no cancelamento.
- **Cancelamento acontece em 3 caminhos:** webhook de pagamento, cancelamento manual do usuário,
  e cron de inadimplência do Asaas — **os 3 já emitem `subscription_cancelled` para o Escuta** (ver §6).

---

## 5. Feedback & suporte HOJE — o que o Escuta complementa

| Capacidade | Onde vive | Estado | O que falta |
|------------|-----------|--------|-------------|
| **NPS in-app** | `backend/src/nps` + `frontend useNpsCheck/NpsModal` | coleta 0-10 nos marcos, painel `/gestao/nps` | só armazena — **sem análise, sem evento p/ Escuta** |
| **Suporte** | `backend/src/atendimentos` (`/gestao/atendimentos`) | tickets por **e-mail** (SendGrid Inbound Parse, `suporte.bizzu.ai`) | sem WhatsApp, sem IA |
| **Exit survey (churn)** | — | **não existe** (cancelamento é `window.confirm` seco) | tudo — maior oportunidade |
| **Captação de lead** | site/landing | **só e-mail** (Google Forms) | telefone/WhatsApp, follow-up |

**Conclusão:** a Bizzu coleta satisfação (NPS) e atende (e-mail), mas **não tem (a) canal WhatsApp,
(b) inteligência sobre o feedback, (c) captura de motivo de churn.** É exatamente o tripé do Escuta.

---

## 6. Integração Escuta ↔ Bizzu — o que JÁ está plugado

Construído nas sessões anteriores (no clone local do backend; **patches** em `docs/patches/`):

- **`backend/src/escuta/`** — `EscutaService` (`@Global`) fire-and-forget, **HMAC-SHA256**,
  `POST {ESCUTA_API_URL}/api/events/bizzu`. Pula quem não tem telefone; consentimento viaja no payload.
- **`subscription_cancelled`** nos **3 caminhos de churn**, `event_id` estável `sub:<extSubId>`
  (o Escuta deduplica): `payments/webhook.service.ts:225`, `payments/subscription.service.ts:487`,
  `asaas-overdue-cancellation.service.ts:78`.
- **`topic_completed` + `goal_completed`** ao concluir tarefa/meta do plano IA
  (`plano-estudo-ia.service.ts:2050,2066`, chamados de 4 pontos).
- **Opt-in WhatsApp dedicado**: colunas `usuarios.whatsappOptIn`/`whatsappOptInAt`
  (migration `20260607130000`), checkbox no `Signup.jsx` + toggle em `MinhaContaPage`,
  persistidos via `PATCH /user/me`.

Do lado Escuta, esses eventos casam com surveys por `trigger_event` (Exit Bizzu, CSAT Tópico) e
disparam via WhatsApp com cérebro + RAG + classificação.

---

## 7. Mapa de oportunidades (priorizado)

| Pri | Oportunidade | Onde plugar | Esforço | Valor |
|-----|--------------|-------------|---------|-------|
| 🥇 | ~~Exit survey de churn~~ ✅ **feito** | 3 caminhos de cancelamento | — | ouro p/ churn |
| 🥈 | ~~CSAT de tópico/meta~~ ✅ **feito** | `plano-estudo-ia.service.ts` | — | qualidade do conteúdo |
| 🥉 | **Espelhar NPS in-app** → análise unificada | `nps.service.ts:101` → evento `nps_submitted` | baixo (call-site óbvio) | unifica feedback in-app + WhatsApp |
| 4 | **Radar → "saiu seu edital" no WhatsApp** | `radar-editais/pipeline.py:297-327` (<50 linhas) | baixo | canal de valor altíssimo, hoje inexistente |
| 5 | **Captura WhatsApp na captação** | site (hero, `/editais/[slug]`, `/exemplo`) + landings (Google Forms) | baixo | lead já chega "conversável" |
| 6 | Eventos faltantes: `signup`, `plano_gerado` | call-sites mapeados no `backend.md §7` | baixo | mais momentos de ativação |

---

## 8. Pontos de atenção / riscos (descobertos na análise)

1. **Double-touch no churn** ⚠️: no mesmo cancelamento, a Bizzu já manda **e-mail de winback** e o
   Escuta manda **exit survey por WhatsApp** — o cliente leva 2 toques. Coordenar (cadência/ownership).
2. **`reason` empobrecido**: `webhook.service.ts:207` hardcoda `reason=PAYMENT_FAILED` em todo
   cancelamento — o exit survey recebe "falha de pagamento" mesmo em cancelamento voluntário. Suja o dado.
3. **`ESCUTA_API_URL`/`ESCUTA_WEBHOOK_SECRET` fora do `.env.example`**: sem eles o `EscutaService`
   vira **no-op silencioso** — risco de "parou e ninguém viu". Documentar.
4. **Radar 1×/dia (07h), systemd já visto inativo**: alertas não são tempo-real; monitorar o timer.
5. **`ReportarErroPage` é stub** ("em construção") — o gancho de "erro no comentário" (dupla-conferência
   de gabarito) ainda não tem fluxo no front.
6. **Segurança** (documentada nos relatórios, não introduzida por nós): há `rejectUnauthorized:false`
   e segredos a revisar no backend — ver `backend.md §9`. (No Escuta, rotação WAHA ainda pendente.)

---

## 9. Infra — onde o Escuta vai morar

AWS `us-east-1`, Terraform (state S3 `bizzu-terraform-state-633146206248`), 11 módulos. **Existe um
molde quase idêntico ao Escuta**: `modules/radar-editais-ec2/` (EC2 + Caddy/TLS + Route53 + IAM + systemd).

Caminho concreto (detalhe em `infra.md`):
1. Clonar p/ `modules/escuta-ec2/` — `subdomain="escuta"`, +Docker no `user_data.sh` p/ o WAHA,
   systemd p/ FastAPI (8000) + WAHA.
2. `infra/escuta-secrets.tf` com path `prod/escuta/*` (Supabase, WAHA_API_KEY, HOOK_SECRET).
3. Referenciar no `main.tf` (vpc/subnet/zone).

O **wildcard ACM `*.bizzu.ai` já cobre `escuta.bizzu.ai`**. O **Supabase do Escuta fica separado**
do RDS deles (sem SG rule nova). Custo ~**$12-16/mês** (`t4g.small` ARM + EIP).

---

## 10. Identidade visual (para materiais white-label)

- Indigo **#6C5CE7** (primária) · Gold **#F5A623** (acento) · dark `#0c0b10`
- Fontes: **Space Grotesk** (títulos) + **DM Sans** (corpo); tokens em `frontend/theme/brand-tokens.css`
- Telemetria do ecossistema: **PostHog + Google Analytics** (GA4 `G-6WFC2DE7VE` no site)

---

## TL;DR estratégico

A Bizzu é um produto sólido de conteúdo/IA para concursos, mas **toda a relação com o cliente fora do
app é por e-mail ou inexistente**: captação só e-mail, suporte por e-mail, churn sem pergunta, NPS
preso no app. O Escuta já está integrado nos dois eventos de maior valor (churn + CSAT de tópico) e
tem 4 frentes de expansão baratas e óbvias (espelhar NPS, radar→WhatsApp, captura na captação, eventos
de ativação). O risco operacional nº1 a resolver junto é o **double-touch de churn** (e-mail winback +
WhatsApp survey ao mesmo tempo).
