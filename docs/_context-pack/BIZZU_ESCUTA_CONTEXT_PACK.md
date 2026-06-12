# BIZZU x ESCUTA - CONTEXT PACK (para a funcao Projetos do Claude.ai)

> Pacote unico de contexto, gerado automaticamente a partir do projeto Claude Code.
> Gerado em 2026-06-10 02:15. Suba ESTE arquivo no Project Knowledge do Claude.ai e cole as
> Custom Instructions de PROJECT_CUSTOM_INSTRUCTIONS.md. Regenere quando os docs mudarem.
> Segredos/PII foram redigidos automaticamente (procure por <REDACTED...>).

## Fontes incluidas neste pacote
- docs\MISSAO_JAIR.md
- docs\BIZZU_ESCUTA_MASTER.md
- docs\CONTEXTO_BIZZU.md
- docs\INTEGRACAO_BIZZU.md
- docs\INTEGRACAO_FEEDBACK.md
- docs\analise-bizzu\feedback-nativo.md
- docs\analise-bizzu\api-clientes-partner.md
- docs\analise-bizzu\bizzu-midia.md
- docs\analise-bizzu\backend.md
- docs\analise-bizzu\frontend.md
- docs\analise-bizzu\site.md
- docs\analise-bizzu\landing-pages.md
- docs\analise-bizzu\radar-editais.md
- docs\analise-bizzu\infra.md
- docs\corpus_bizzu\o-que-e-bizzu.md
- docs\corpus_bizzu\funcionalidades.md
- docs\corpus_bizzu\planos-e-precos.md
- docs\corpus_bizzu\cancelamento-e-garantia.md
- docs\corpus_bizzu\conta-e-suporte.md
- docs\SESSAO_HANDOFF_2026-06-09.md

================================================================
FONTE: docs\MISSAO_JAIR.md
================================================================

# 🎯 MISSÃO JAIR — Sócio de Growth da Bizzu (mapa de tudo)

> Briefing único da missão do **Jair** como sócio de mídia/growth da **Bizzu** (fundador técnico:
> **Felipe Lemes**). Escrito para que **qualquer chat do Claude** (Code, Claude.ai/Projects, Desktop)
> entenda o todo e ajude na missão. Fonte: reuniões 05/06 e 08/06 + análise dos repos.
> Atualizado 2026-06-09.

## 1. Quem é o Jair aqui
Sócio responsável por **growth**, em **2 frentes**. NÃO é dev do backend (isso é o Felipe). Vínculo:
**PJ**. Governança: **Trello** (tarefas) + reuniões semanais. Liberdade criativa alta; decisões de
produto/preço alinhar com o Felipe.

## 2. As 2 frentes (o coração da missão)

```
        ┌──────────── DADOS DA BIZZU (produção) ────────────┐
        │  api.bizzu.ai   ·   radar-editais.bizzu.ai          │
        └───────┬───────────────────────────┬────────────────┘
                ▼                            ▼
 ┌──────────────────────────┐   ┌──────────────────────────────┐
 │ FRENTE 1 — AQUISIÇÃO      │   │ FRENTE 2 — RETENÇÃO           │
 │ repo: bizzu_midia         │   │ produto: Escuta               │
 │ gerar artes/posts de      │   │ WhatsApp + IA: pesquisa,      │
 │ editais p/ Instagram,     │   │ ouvir feedback, reativar,     │
 │ prospecção (PDF)          │   │ segmentar por PERFIL          │
 └──────────────────────────┘   └──────────────────────────────┘
        traz gente                       segura gente
```

| | Frente 1 — Aquisição | Frente 2 — Retenção |
|---|---|---|
| **Repo/Produto** | `bizzu_midia` (clonado, `Documents/Projetos/bizzu_midia`) | `Escuta` (`Documents/Projetos/escuta`) |
| **O que faz** | Carrosséis de cargo/edital, Daily Editais, Notícias, e-mail, PDF de prospecção | Survey WhatsApp + cérebro IA + classificação + digest |
| **Consome** | API Bizzu (Raio-X) + Radar + Gemini + Miniflux | Eventos Bizzu (HMAC) + **API de Clientes** (perfis) |
| **Publicação/Disparo** | Instagram **manual** hoje (Meta API = a construir) | WhatsApp via WAHA (só com opt-in; teste antes de prod) |
| **Estado (09/06)** | ✅ deps instaladas, pronto p/ operar | ✅ churn/CSAT plugados; falta integrar perfis |

## 3. Acessos, chaves e ferramentas
- **Repos:** `bizzu_midia` (GitHub `felipelemes/bizzu_midia`, clonado) · `escuta` (local) · `bizzu-repos/`
  (6 repos da Bizzu, **leitura**).
- **Chaves (em `.env`, nunca commitar):** `GEMINI_API_KEY` (trocar pela própria, grátis em
  aistudio.google.com/apikey) · `BIZZU_API_KEY` (Leads/Raio-X) · `RADAR_SERVICE_API_KEY` (editais) ·
  **`BIZZU_PARTNER_API_KEY`** (API de Clientes — já no `.env` do Escuta).
- **A obter/combinar com o Felipe:** acesso ao **Instagram** (central de contas) · links de **Telegram** ·
  **Trello** (board) · app **Meta** para publicar via API oficial (homologação 4-7 dias).

## 4. Perfis de feedback (resumo)
A API de Clientes (233 clientes) permite segmentar em **9 perfis** por estado + tempo de casa + NPS +
motivo de saída, cada um com uma abordagem e uma survey. Detalhe completo + integração em
[`analise-bizzu/api-clientes-partner.md`](analise-bizzu/api-clientes-partner.md). Resumo:
Embaixador · Ativo recente · Ativo silencioso · Ativo em risco (detrator) · Vai expirar · Churn pós-uso ·
Churn rápido · Churn involuntário (⚠️ não duplicar com winback) · Cortesia.

## 5. Roadmap priorizado

**🟢 Frente 1 — Aquisição (bizzu_midia)**
1. ✅ Deps instaladas. Próximo: `npm start` → `localhost:3000` e rodar `node agents/daily-editais/run-daily-editais.js --date <hoje>`; revisar a arte em `output/`.
2. Ler `brand-guidelines-bizzu.html` (obrigatório) antes de gerar.
3. Validar/refinar os 3 templates do Daily + criar modelos de referência de estilo.
4. **Iniciar homologação do app Meta JÁ** (demora) — postar manual enquanto isso.
5. Definir avatar/mascote dentro da marca (objeto editorial recorrente; sem humanos/stock).
6. Melhorar o PDF de prospecção (perfil do concurseiro + comparativo + screenshot do Raio-X).

**🎧 Frente 2 — Retenção (Escuta + API de Clientes)**
7. ✅ API validada + chave guardada + perfis definidos.
8. Implementar `sync_partner_customers.py` (paginar 233 → classificar em perfil → upsert no contato, **sem disparar**) + `--dry-run` para auditar a distribuição.
9. Criar as surveys 🆕 (Indicação, CSAT Onboarding, Escuta de Detrator, Retenção) reusando o motor do Escuta.
10. Teste de disparo Jair↔Felipe antes de produção. Coordenar **double-touch de churn** com o Felipe.

**🗂️ Governança**
11. Preencher o **Trello** (tarefas das duas frentes).
12. Listar ferramentas/assinaturas p/ a Bizzu contratar.
13. Estudar mercado (`bizzu_midia/relatorio-perfil-concurseiro.md`) + entrar nos grupos de Telegram.

## 6. Pontos de atenção
- **Segredos:** as chaves são de produção; só em `.env` (gitignored), nunca em doc/Claude.ai/commit.
- **PII / LGPD:** a API de Clientes tem nome/e-mail/WhatsApp; disparo só com opt-in; não exportar a base.
- **Preço:** conteúdo novo usa **R$20/mês · R$120/ano**; site pode ter resíduo de R$10/R$60 — confirmar.
- **WhatsApp:** WAHA viola ToS — só teste pequeno; produção exige cuidado.

## 7. Ponteiros (docs canônicos em `escuta/docs/`)
`BIZZU_ESCUTA_MASTER.md` (ecossistema Bizzu + Escuta) · `analise-bizzu/api-clientes-partner.md` (API +
perfis) · `analise-bizzu/feedback-nativo.md` (o que a Bizzu já ouvia) · `analise-bizzu/<repo>.md` (cada
repo) · `_context-pack/` (pacote p/ Claude.ai Projects). bizzu_midia: ver `bizzu_midia/README.md` e
`bizzu_midia/CLAUDE.md`.


================================================================
FONTE: docs\BIZZU_ESCUTA_MASTER.md
================================================================

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
> **Última atualização:** 2026-06-09.

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
| 🥉 | **Espelhar NPS in-app** → análise unificada | `nps.service.ts:101` → evento `nps_submitted` (exige modo "ingest sem disparo" no Escuta) | baixo | **próximo, mais seguro** |
| 4 | **Radar → "saiu seu edital" no WhatsApp** | `radar-editais/pipeline.py:317` (após `aplicar_interesse`, antes do `upsert`) | baixo (<50 ln) | canal de valor altíssimo |
| 5 | **Captura WhatsApp na captação** | site (hero, `/editais/[slug]`, `/exemplo`) + landings (Google Forms) | baixo | lead já chega "conversável" |
| 6 | Eventos `signup`, `plano_gerado` | `auth.service.ts:52`, `plano-estudo-ia.service.ts` | baixo | mais momentos de ativação |

---

## 8. Riscos conhecidos (ordenar antes de escalar o piloto)

1. ⚠️ **Double-touch de churn** — no mesmo cancelamento a Bizzu manda **e-mail winback** e o Escuta
   manda **survey WhatsApp**. Definir cadência/ownership. (Risco nº1.)
2. 🐛 **`reason` hardcoded** `webhook.service.ts:207` (=PAYMENT_FAILED sempre) → suja o motivo de churn
   voluntário no exit survey.
3. 🔇 **`ESCUTA_*` fora do `.env.example`** do backend → deploy novo fica inerte sem aviso.
4. 🔑 **Rotação WAHA pendente** (credenciais novas já geradas em `~/.secrets/waha_*.txt`).
5. 📡 **Radar systemd inativo** em prod — monitorar o timer.
6. 🏷️ **Site:** promo "até 20/05" vencida no fallback + JSON-LD de preço inconsistente (9.90 vs 10.00).

---

## 9. Estado atual + como retomar a stack local

**Estado (handoff 08/06):** tudo no ar — API Escuta `:8000` (IA+RAG+digest), painel `:3001`, WAHA `:3000`
(sessão `WORKING`, número Jair `<REDACTED-PHONE>`). API Bizzu local `:3100` e front Bizzu `:5173` ficam
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


================================================================
FONTE: docs\CONTEXTO_BIZZU.md
================================================================

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


================================================================
FONTE: docs\INTEGRACAO_BIZZU.md
================================================================

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


================================================================
FONTE: docs\INTEGRACAO_FEEDBACK.md
================================================================

# Integração de Feedback (retenção) — contexto completo

> A cadeia de retenção do Escuta: **API de Clientes da Bizzu → 13 perfis → survey por perfil →
> disparo seletivo (em teste)**. Doc útil pro chat (estratégia) e referência da implementação.
> Atualizado 2026-06-09.

## 1. A cadeia (visão)
```
API de Clientes (233)  ──►  classify_profile (13 perfis)  ──►  PROFILE_TO_SURVEY  ──►  dispatch_by_profile
  bizzu_partner.py            profiles.py                       profile_surveys.py       (--dry-run / --force)
  (GET, X-API-Key)            grava em Contact.profile_data['partner']                   reusa SurveyDispatcher
```

## 2. O motor de survey do Escuta (já existente)
- **Modelos** (`app/models/survey.py`): `Survey(type 'nps'|'exit', questions[], trigger_event)`, `SurveyRun`, `SurveyResponse(status sent→awaiting_reason→closed; + score, nps_bucket, answer_text, sentiment/themes/ai_meta)`.
- **Tipos de survey:** `nps` = pergunta de nota 0-10 + follow-up aberto + thanks. `exit` = **só pergunta aberta** + thanks (nasce em `awaiting_reason`, a resposta de texto fecha).
- **Dispatcher** (`app/domain/survey/dispatcher.py`): `dispatch(survey, contacts, trigger)` cria a run + uma `SurveyResponse` por contato (idempotente) e envia a 1ª pergunta via WAHA. Saudação automática `Oi {primeiro_nome}!`.
- **Disparo automático por evento** (`/api/events/bizzu`): surveys com `trigger_event` (`subscription_cancelled` → Exit; `topic_completed` → CSAT Tópico) disparam sozinhas no evento.
- **Disparo manual** (`scripts/dispatch_nps.py`): `list` inspeciona; `dispatch --phone X --force` envia (o `--force` é exigido quando o WAHA é o real na `:3000` — fricção proposital).

## 3. Os 13 perfis → survey (mapeamento)
| Perfil | Qtd | Survey | Por quê |
|--------|----:|--------|---------|
| ativo_silencioso | 100 | **NPS Bizzu** | nunca opinou → coletar nota |
| vai_expirar | 34 | **Retenção Bizzu** 🆕 | reter antes de perder acesso |
| ativo_promotor | 33 | **Indicação Bizzu** 🆕 | fã → depoimento/indicação |
| churn_rapido | 27 | **Exit Bizzu** | o que não atendeu de cara |
| ativo_passivo | 11 | **NPS Bizzu** | empurrar de neutro p/ promotor |
| churn_outro | 11 | **Exit Bizzu** | exit genérico |
| churn_involuntario | 6 | **— (não contatar)** | já recebe winback por e-mail |
| ativo_em_risco | 5 | **Escuta de Detrator Bizzu** 🆕 | ouvir antes de virar churn |
| ativo_recente | 2 | **CSAT Onboarding Bizzu** 🆕 | 1ª impressão |
| indefinido | 2 | **— (não contatar)** | anômalo |
| cortesia | 1 | **NPS Bizzu** | feedback qualitativo |
| churn_pos_uso | 1 | **Exit Bizzu** | por que parou após usar |
| embaixador | 0 | **Indicação Bizzu** 🆕 | (surge com o tempo) |

## 4. Roteiros das surveys (copy on-brand)
**NPS Bizzu** *(nps, existe)* — "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?" → "Massa! 🙌 Por quê?"
**Exit Bizzu** *(exit, existe)* — "vi aqui que você cancelou sua assinatura do Bizzu 😕 Pode me contar em uma frase o que pesou na decisão? Sua resposta vai direto pro time."
**CSAT Onboarding Bizzu** 🆕 *(nps)* — "vi que você começou no Bizzu faz pouco tempo 👋 De 0 a 10, como tá sendo a experiência até agora?" → "O que faria essa nota subir?"
**Escuta de Detrator Bizzu** 🆕 *(exit)* — "vi que sua experiência com o Bizzu não tá sendo a melhor 😕 Pode me contar, em uma frase, o que mais tá te incomodando? Quero levar direto pro time."
**Retenção Bizzu** 🆕 *(exit)* — "vi que seu acesso ao Bizzu tá quase no fim ⏳ Antes de ir: tem alguma coisa que faria você continuar com a gente?"
**Indicação Bizzu** 🆕 *(exit)* — "que bom te ver curtindo o Bizzu! 🙌 Me conta em uma frase o que mais te ajudou — e, se topar, uso como depoimento (só com seu ok). Quer indicar um amigo? manda o contato. 💙"

## 5. Como operar (a partir da raiz `escuta/`)
1. **Classificar a base:** `py scripts/sync_partner_customers.py --dry-run` (audita) → sem flag faz o upsert dos perfis nos contatos.
2. **Criar/garantir as surveys:** `py scripts/seed_bizzu.py` (idempotente; cria as 4 novas).
3. **Ver o plano de disparo:** `py scripts/dispatch_by_profile.py plan` (mostra perfil → survey → nº elegíveis, **sem enviar**).
4. **Testar disparo real (controlado):** `py scripts/dispatch_by_profile.py dispatch --profile <perfil> --limit 1 --force` (só com opt-in e em teste Jair↔Felipe).

## 6. Segurança / regras
- **Disparo só com opt-in** (`Contact.opt_in`) **e** `should_contact=True` no perfil.
- **Cooldown 7 dias:** não reenviar se já há `SurveyResponse` recente p/ o mesmo contato+survey.
- **`churn_involuntario` e `indefinido` nunca recebem** (mapeiam para None).
- **Double-touch:** churn por pagamento já recebe winback por e-mail da Bizzu — coordenar com o Felipe.
- **WAHA real (`:3000`) exige `--force`**; WAHA viola ToS → só teste pequeno antes de produção.
- **PII:** o `plan`/dry-run só imprime contagens — nunca nome/e-mail/telefone.


================================================================
FONTE: docs\analise-bizzu\feedback-nativo.md
================================================================

# Sistema de feedback NATIVO da Bizzu (pré-Escuta) — inventário completo

> Levantamento fiel ao código (backend + frontend clonados em `bizzu-repos/`), feito por 2 agentes em
> 09/06/2026, com `arquivo:linha`. Responde: **o que a Bizzu já tinha para ouvir o cliente ANTES do
> Escuta** — para o Escuta complementar, não duplicar. Corrige simplificações de docs anteriores.

## Visão: a Bizzu já escuta o cliente em 5 frentes

A Bizzu **não era surda** — ela já coletava voz do cliente em 5 famílias. O que faltava era **(1) canal
conversacional (WhatsApp)**, **(2) inteligência sobre o que é coletado (sentimento/temas/clustering)** e
**(3) captura ativa do motivo de churn**. É exatamente aí que o Escuta entra.

| # | Família | Natureza | Mecanismos nativos |
|---|---------|----------|--------------------|
| A | **Satisfação proativa** | a Bizzu pergunta | NPS in-app |
| B | **Suporte reativo** | o cliente procura | Atendimentos (helpdesk e-mail) + Formulário de Contato |
| C | **Qualidade de conteúdo** | sobre as questões | Report de questão + Comentários/votos + Comentário-IA detector |
| D | **Sinais passivos / churn** | derivado/observado | `cancellationReason` automático + Tracking PostHog |
| E | **Demanda de produto** | pedido | Solicitação de edital |

---

## A. Satisfação proativa — NPS in-app

- **Onde:** `backend/src/nps/` (`nps-response.model.ts`, `nps.service.ts`, `nps.controller.ts`) ·
  `frontend` `NpsModal.jsx` + `useNpsCheck.js` + `npsApi.js`.
- **Como funciona:** o front chama `GET /nps/check`; o **motor de elegibilidade** (`nps.service.ts:34-88`)
  decide se mostra, por 3 gatilhos contextuais: `FIRST_SESSION` (1ª sessão de questões), `GOAL_HALF`
  (≥50% das tasks da meta), `GOAL_COMPLETE` (100%). Modal pergunta nota **1-10 + comentário livre** →
  `POST /nps`. Tabela `nps_responses` com **unique `(user_id, trigger)`** → 1 resposta por gatilho por
  vida (upsert).
- **O que a Bizzu faz:** painel `/gestao/nps` completo — gauge NPS, % promotor/passivo/detrator,
  distribuição 1-10, **NPS por gatilho**, evolução semanal, comentários paginados; score também no perfil
  do assinante.
- **Lacunas:** ⚠️ montado **só na `PlanoDeEstudoPage`** (quem não abre o plano nunca vê) · **sem cooldown
  temporal** (só dedup por gatilho) · **sem análise de sentimento/tema** nos comentários · **sem alerta de
  detrator** em tempo real · sem segmentação por plano.

## B. Suporte reativo — Atendimentos + Contato

- **Onde:** `backend/src/atendimentos/` (helpdesk) + `backend/src/contact/` (formulário) ·
  `frontend` `/contato` (`ContatoPage.jsx`) + `/gestao/atendimentos` (`GestaoAtendimentosPage.jsx`).
- **É um helpdesk de verdade** (eu tinha subestimado): tickets com `ticketNumber`, **threading por e-mail**
  via **SendGrid Inbound Parse** (`suporte+<ticket>@suporte.bizzu.ai`), `status` (aberto/em_atendimento/
  resolvido/fechado), `prioridade` (baixa→urgente), `tipo` (dúvida/erro/reclamação/sugestão/outro),
  **anexos em S3** (expiram 90d), notas internas. Schema Postgres `suporte`.
- **Fluxos de entrada:** (1) `POST /contact` (público) cria ticket + avisa `suporte@bizzu.ai`; (2) reply do
  usuário por e-mail → webhook `/webhooks/email-inbound` reabre/atualiza o ticket; (3) admin responde pelo
  painel com anexos.
- **O que a Bizzu faz:** painel two-panel (lista+thread), filtros, troca de status/prioridade, resposta
  por e-mail. Stats no dashboard.
- **Lacunas:** **sem CSAT pós-atendimento** (não pergunta se resolveu) · sem SLA/alerta de ticket parado ·
  auto-classificação de tipo é heurística de keyword · sem WhatsApp · aluno não vê nº de protocolo.

## C. Qualidade de conteúdo — 3 mecanismos sobre as questões

> ⚠️ **Correção importante:** existem DOIS "reportar erro". O `ReportarErroPage` (`/reportar-problema`) é
> **stub** ("em construção"). MAS o **report de questão** (`QuestaoReportModal`) é **totalmente
> funcional** — eu havia dito que report de erro era stub; estava incompleto.

1. **Report de questão** (ativo) — `frontend QuestaoReportModal.jsx` (botão "⚑ Reportar" na sessão de
   questões) → `POST /questoes/:id/report`. Backend `question-report.model.ts`: tipo (`GABARITO_ERRADO`,
   `IMAGEM_AUSENTE`, `TEMA_INCORRETO`, `OUTRO`) + observação + contexto (matéria/tópico/edital/cargo).
   Alerta imediato p/ `suporte@bizzu.ai`. Painel `/gestao/question-reports` agrupa por questão, **valida
   gabarito com IA (Gemini)** e notifica o usuário de volta.
2. **Comentários + votos por questão** — `frontend QuestaoComentarios.jsx` · backend
   `questoes-comentarios/`: fórum com threading (1 nível), **votos UP/DOWN** (score), flag de moderação
   (só MANAGER), soft-delete. Painel `/gestao/comentarios` modera flagados. É **feedback de conteúdo**
   (quais questões geram dúvida/discordância).
3. **Comentário-IA detector de divergência** — backend `questoes-comentarios-ia/`: a IA (solver→reconciler)
   marca `agreesWithGabarito=false` + `needsReview=true` quando discorda do gabarito oficial → fila de
   revisão da gestão. É um **detector automático de erro de gabarito** (mais preciso que report manual).
- **Lacunas:** sem threshold automático (N reports `GABARITO_ERRADO` → revisão urgente) · sem cruzamento
  report manual × detector-IA · aluno não vê status do report · nenhum rating/"foi útil?" sobre o
  comentário-IA · sem rating de conteúdo/plano (estrelas/like) em lugar nenhum.

## D. Sinais passivos / churn — derivados, não perguntados

- **Motivo de churn** (`backend/src/payments/subscription.model.ts:124-129`): `cancellationReason` é
  **preenchido automaticamente** pelo fluxo — **NUNCA perguntado ao usuário**. 4 categorias:
  `GUARANTEE_REFUND` · `USER_CANCEL` · `PAYMENT_FAILED` · `OTHER`. O endpoint
  `POST /user/subscription/cancel` **não aceita corpo** → no front é `window.confirm` seco, sem survey.
- **Consequência:** `USER_CANCEL` é monolítico — não distingue "caro" / "não preciso mais" / "insatisfeito"
  / "fui pro concorrente". `PAYMENT_FAILED` é hardcoded no webhook (suja churn voluntário). É a **maior
  lacuna de feedback da Bizzu** — e o ponto de maior valor do Escuta.
- **Tracking PostHog** (`backend/src/tracking/`): eventos server-side de ciclo de vida
  (`subscription_cancelled` com `reason`/`days_subscribed`, `checkout_payment_succeeded`,
  `subscription_plan_changed`...). Análise externa no PostHog; **sem signup nem eventos de engajamento de
  produto** capturados (esses só existem no Escuta).

## E. Demanda de produto — Solicitação de edital

- `backend/src/edital-solicitacoes/` + `frontend MissingEditalRequestPanel.jsx` (no checkout, quando o
  aluno não acha o edital): grava demanda → notifica o aluno quando o edital é adicionado. Sinal de **voz
  de produto** (quais concursos querem). Lacuna: sem agregação/priorização por volume de pedidos.

---

## Quadro-mestre: feedback nativo × como o Escuta se relaciona

| Mecanismo nativo | Captura | O que a Bizzu faz hoje | Lacuna-chave | Relação com o Escuta |
|---|---|---|---|---|
| **NPS in-app** | nota 1-10 + comentário, 3 gatilhos | painel NPS completo (gauge, por-gatilho, evolução) | sem sentimento/tema; só na pág. do plano | **Espelhar** (🥉 `nps.service.ts:101`→`nps_submitted`) p/ análise unificada + sentimento; **não substituir** |
| **Atendimentos (helpdesk e-mail)** | ticket texto livre, threading, anexos | triagem/resposta por e-mail no painel | sem CSAT pós-atendimento; sem WhatsApp | **Complementar**: CSAT pós-resolução via WhatsApp (futuro); não virar helpdesk |
| **Formulário de Contato** | nome/email/assunto/mensagem | vira ticket | sem protocolo ao aluno | canal alternativo; Escuta não toca |
| **Report de questão** (ativo) | erro de gabarito/imagem/tema | painel + validação IA Gemini + notifica | sem status p/ usuário | **deixar nativo**; é qualidade de conteúdo, não voz-do-cliente WhatsApp |
| **Comentários + votos** | discussão/UP-DOWN por questão | exibe + modera | sem análise de tendência | **deixar nativo** |
| **Comentário-IA detector** | divergência IA × gabarito | fila de revisão | sem cruzar c/ report manual | **deixar nativo** |
| **`cancellationReason`** | categoria automática (4) | filtra winback; mostra no painel | **nunca pergunta o porquê** | 🥇 **Exit survey WhatsApp** = o ouro do Escuta (✅ já plugado) |
| **CSAT de tópico/meta** | — (não existia) | — | inexistente | ✅ **criado pelo Escuta** (`topic_completed`) |
| **Tracking PostHog** | eventos de ciclo de vida | análise externa | sem engajamento de produto | Escuta capta engajamento (tópico/meta) que o PostHog não tinha |
| **Solicitação de edital** | demanda de concurso | fila + notifica | sem priorização | Escuta poderia avisar "saiu seu edital" (via radar) |

## Conclusão (a tese refinada)

A Bizzu tem **boa escuta reativa** (helpdesk maduro) e **de conteúdo** (report + fórum + detector-IA), e
**satisfação proativa básica** (NPS sem inteligência). Os **3 buracos reais** que o Escuta preenche:
1. **Canal conversacional (WhatsApp)** — a Bizzu não tem nenhum ponto de WhatsApp.
2. **Inteligência sobre o feedback** — NPS e atendimentos só **armazenam**; ninguém classifica
   sentimento/tema nem clusteriza. O Escuta faz cérebro + classificação + RAG + digest.
3. **Motivo de churn ativo** — a Bizzu **categoriza sozinha** mas **nunca pergunta**. O exit survey via
   WhatsApp (já plugado) é o maior ganho.

O Escuta **não deve duplicar** o helpdesk, o report de questão nem o fórum (são fortes e nativos). Deve
**espelhar** o NPS (unificar análise) e **adicionar** o que não existe: WhatsApp, inteligência e o
"porquê" do churn — sempre cuidando do **double-touch** (winback e-mail + exit survey ao mesmo tempo).


================================================================
FONTE: docs\analise-bizzu\api-clientes-partner.md
================================================================

# API de Clientes da Bizzu (Partner) + Perfis de Feedback

> A "API de dados de usuários" prometida nas reuniões (05/06 e 08/06). É o **combustível da
> segmentação por perfil** para a frente de retenção (Escuta). Somente leitura (GET).
> **Validada em 2026-06-09: 200 OK, 233 clientes, schema confere. Integração implementada
> e classificador refinado (13 perfis, distribuição real abaixo).**

## 1. A API (resumo técnico)

- **Base:** `https://api.bizzu.ai` · **Auth:** header `X-API-Key` (env `BIZZU_PARTNER_API_KEY` — **segredo**,
  já no `.env` do Escuta; nunca commitar nem colar em doc).
- **Endpoints:**
  - `GET /partner/customers?page=&pageSize=&search=` → `{ items[], total, page, pageSize }`. Paginar até
    items vazio (pageSize máx 500). **total atual = 233.**
  - `GET /partner/customers/by-email?email=` → 1 `PartnerCustomer` (404 se não for cliente).
- **`PartnerCustomer`:** `id, name, email, whatsapp, signedUpAt, nps{voted,score,comment,respondedAt},
  subscription{state, active, cancelled, complimentary, planName, planType, paymentMethod, startedAt,
  cancelledAt, cancellationReason, currentPeriodEnd, daysAsSubscriber, totalPaidCentavos, lastPaymentAt}`.
- **Quem NÃO aparece:** cadastrou e nunca pagou. Sem CPF/senha.
- **`state`:** `active_paying` · `complimentary` · `past_due` · `cancelled` · `cancelled_with_access` ·
  (borda) `access_without_subscription` / `paid_without_access`.

## 2. ⚠️ Privacidade / LGPD (regras antes de qualquer disparo)

1. **A API tem PII** (nome, e-mail, WhatsApp). Não exporte a base; não cole PII em doc/Claude.ai.
2. **Disparo só com opt-in** (`whatsappOptIn`, do sync da Bizzu). Esta API serve para **classificar e
   priorizar**, não para forçar contato.
3. **Coordenar double-touch:** `churn_involuntario` (PAYMENT_FAILED) já recebe **winback por e-mail** —
   por isso `should_contact=false` nesse perfil. Não duplicar com WhatsApp.
4. **Fase atual = entender + preparar.** O `--dry-run` só mostra contagens (sem PII, sem tocar banco).
   Disparo em produção vem depois, em teste (Jair ↔ Felipe).

## 3. Os 13 Perfis de Feedback + distribuição real (233 clientes, 2026-06-09)

Classificador puro em `app/domain/segmentation/profiles.py` (40 testes). Precedência: terminais
(cortesia → churns → vai_expirar) antes dos ativos. `should_contact=false` em churn_involuntário e
indefinido.

| Perfil | Critério (campos da API) | Qtd | % | Abordagem / survey |
|--------|--------------------------|----:|----:|--------------------|
| 🟢 **ativo_silencioso** | active_paying + nps.voted=false | 100 | 42.9% | maior balde: coletar NPS (✅ NPS Bizzu) |
| 🟡 **vai_expirar** | state cancelled_with_access/past_due | 34 | 14.6% | retenção urgente (janela curta) 🆕 |
| 🟢 **ativo_promotor** | active_paying + score≥9 (days<90) | 33 | 14.2% | pedir indicação/depoimento 🆕 |
| 🔴 **churn_rapido** | GUARANTEE_REFUND ou cancelou ≤7d | 27 | 11.6% | o que não atendeu de cara (✅ Exit) |
| 🟢 **ativo_passivo** | active_paying + score 7-8 | 11 | 4.7% | empurrar de passivo p/ promotor 🆕 |
| 🔴 **churn_outro** | cancelled fora dos casos acima (OTHER / 8-29d) | 11 | 4.7% | exit genérico (✅ Exit) 🆕 |
| 🔴 **churn_involuntario** | PAYMENT_FAILED | 6 | 2.6% | ⚠️ NÃO contatar (winback e-mail) |
| 🟡 **ativo_em_risco** | active_paying + score≤6 (detrator) | 5 | 2.1% | escuta prioritária antes do churn 🆕 |
| 🟢 **ativo_recente** | active_paying + days≤14 (sem nota) | 2 | 0.9% | CSAT onboarding 🆕 |
| ⚪ **indefinido** | anômalo residual (votou sem score) | 2 | 0.9% | nenhuma (should_contact=false) |
| 🎁 **cortesia** | complimentary | 1 | 0.4% | feedback qualitativo (✅ NPS) |
| 🔴 **churn_pos_uso** | USER_CANCEL + days≥30 | 1 | 0.4% | por que parou após usar (✅ Exit) |
| 🟢 **embaixador** | active_paying + days≥90 + score≥9 | 0 | 0% | (base nova; vai surgir) |

> Eixos de adaptação da mensagem: **estado** (`state`), **tempo de casa** (`daysAsSubscriber`),
> **plano** (`planType`), **satisfação** (`nps.score`), **motivo de saída** (`cancellationReason`).
> O refinamento de 09/06 zerou ~23% de "indefinido" (54→2), revelando 33 promotores e 11 passivos.

**Leitura de growth:** 3 alvos imediatos = (1) 100 silenciosos → coletar NPS (saúde da base);
(2) 34 "vai expirar" → reter antes de perder acesso; (3) 27 churn rápido → consertar a fricção de
entrada. Bônus: **33 promotores + futuros embaixadores = base de depoimentos reais** (o site hoje usa
depoimentos fake).

## 4. Como integra com o Escuta (já implementado, sem disparo)

Arquivos criados (workflow de 09/06, 40 testes, review PRONTO):
- `app/integrations/bizzu_partner.py` — cliente HTTP (GET-only, header X-API-Key, trata 401/404).
- `app/domain/segmentation/profiles.py` — `classify_profile()` puro (13 perfis).
- `scripts/sync_partner_customers.py` — `--dry-run` (só contagens, sem PII, sem banco); sem flag faz
  upsert do perfil em `Contact.profile_data["partner"]` (sem disparar WhatsApp).

Reaproveita o motor existente do Escuta (survey `trigger_event`, dispatcher, cooldown 7d, dedup). As
surveys 🆕 (Retenção, Indicação, CSAT Onboarding, Escuta de Detrator) reusam o mesmo motor. **Nenhum
disparo automático nesta fase** — só sync + classificação + preparação.

**Rodar:** `py scripts/sync_partner_customers.py --dry-run` (auditar) · sem `--dry-run` faz o upsert.


================================================================
FONTE: docs\analise-bizzu\bizzu-midia.md
================================================================

# bizzu_midia — a fábrica de conteúdo (frente de AQUISIÇÃO)

> O repo de marketing/conteúdo do Jair (GitHub `felipelemes/bizzu_midia`, clonado em
> `Documents/Projetos/bizzu_midia`; package name interno `bizzu_insta`). É a **frente de aquisição**
> que complementa o Escuta (retenção). Gera artes/posts de Instagram a partir de dados reais da Bizzu.
> Analisado e validado 2026-06-09.

## O que é + stack
Node (servidor `server.js`, HTTP nativo, porta **3000**) + **Playwright** (HTML→PNG 1080×1350) +
**Gemini** (texto + imagem "nano banana 2" `gemini-3-pro-image-preview`) + **Miniflux** (Docker, RSS de
notícias). Sem framework web. Opera **localmente** na máquina do Jair.

## Os 5 subsistemas
| Subsistema | Gera | Fonte | Como rodar |
|---|---|---|---|
| **Carrossel de Cargo** (10 agentes) | carrossel premium do Raio-X, capa com arte IA | API Bizzu (Raio-X) | `node agents/run-pipeline.js --cargo <id>` |
| **Carrossel de Edital** (6 agentes) | visão geral do concurso (cargos/vagas/salários) | API Bizzu pública | `node agents/run-edital-pipeline.js <slug>` |
| **Daily Editais / Radar** (5 agentes) | post "edital novo na praça" do dia | Radar (`radar-editais.bizzu.ai`) | `node agents/daily-editais/run-daily-editais.js --date ...` |
| **Notícias** (4 agentes) | post single-image de notícia curada | Miniflux (RSS) | `/noticias.html` ou CLI |
| **Email Generator + Relatórios PDF** | e-mail transacional + **PDF de prospecção** | API Bizzu | `npm start` → localhost:3000 |

**Pipeline de arte (não alucina texto):** `07-render` (Playwright renderiza o slide com o texto exato)
→ `08-artist` (Gemini gera a arte ao redor preservando o texto, 5 variações, escolhe a 1ª). Só a capa
tem arte IA; os demais slides são HTML/CSS puro.

## Integrações (env vars em `.env`, nunca commitar)
- **API Bizzu** (`BIZZU_API_KEY`): Raio-X, editais públicos, dados de cargo → `lib/bizzu-api.js`.
- **Radar** (`RADAR_API_URL` + `RADAR_SERVICE_API_KEY`): editais novos do dia → `lib/radar-client.js`.
- **Gemini** (`GEMINI_API_KEY`): copy + caption + imagem. (Trocar pela chave própria do Jair.)
- **Miniflux** (`MINIFLUX_*`, docker-compose): agrega RSS de sites de concurso (Trilha 2).
- **Instagram/Meta:** ⚠️ **publicação 100% MANUAL hoje** — não há integração com a Graph API. A
  construir após homologação do app Meta (4-7 dias).

## Marca (brand-guidelines-bizzu.html — mesma identidade do Escuta)
Indigo `#6C5CE7` · Gold `#F5A623` (ponto do logo "Bizzu.") · dark `#09090B`. Fontes: Space Grotesk
(títulos) + Inter (corpo) + JetBrains Mono (números). Voice "mentor estratégico": Problema + Insight com
dado real + Ação. Proibido: travessão (—), "aprovação garantida", "grátis/gratuito", números por extenso.
Preços: **R$20/mês · R$120/ano**.

## Estado do código
- ✅ Os 4 pipelines + Email/PDF prontos e testados; deps instaladas (09/06).
- ⚠️ Publicação manual (sem Meta API). Cron desligado (roda sob demanda). `radar_gui.py` tem bug no
  Windows (abrir pasta usa comando macOS). Sem mascote. Scripts `.sh/.command` são macOS — ignorar.

## Benchmark de concorrentes (do analise-mercado-instagram-concursos.md, 2026-03-27)
- **@victorconcursos** (222k) — notícia quente, "SAIU EDITAL", card único, velocidade.
- **@grancursosonline** (3,2M) — conversão em massa, meme, motivacional, CTA "comenta a palavra".
- **@gurujaconcursos** (94k) — nicho fiscal/policial, tom de consultoria/jornada.
- **Padrões do nicho:** gancho de urgência + números (vagas/salário/data) + texto grande; feed mistura
  notícia/meme/venda; legível em <1s no grid de busca.
- **Espaço da Bizzu:** *"saiu o concurso → o que importa → como começar"* (notícia + diagnóstico +
  plano). Vender **clareza/priorização/ação**, não hype. Fórmula sugerida de carrossel:
  slide 1 gancho de busca · slide 2 Raio-X do que pesa · slide 3 leitura estratégica · slide 4 como a
  Bizzu ajuda. ⚠️ Esse benchmark é de março — atualizar (ver card no TRELLO_BOARD.md).

## Próximos passos
Ler o brand-guidelines → atualizar o benchmark → criar os 3 templates base → rodar o Daily como baseline
→ avatar/mascote → publicação via Meta (pós-homologação) → melhorar o PDF de prospecção.


================================================================
FONTE: docs\analise-bizzu\backend.md
================================================================

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


================================================================
FONTE: docs\analise-bizzu\frontend.md
================================================================

# Bizzu — Frontend (app web do concurseiro)

Análise profunda do repositório `bizzu-repos/frontend`. Leitura apenas; nada foi modificado.
SPA React + Vite, dark-mode, em `https://plataforma.bizzu.ai`. ~442 arquivos `.js/.jsx` em `src/`, 82 arquivos de teste.

---

## 0. Resumo executivo (o que importa pro Escuta)

- **Já existe NPS in-app nativo** (`NpsModal` + `useNpsCheck`) que dispara dentro do **Plano de Estudo** em marcos de progresso (primeira sessão, 50% da meta, meta concluída). Grava score 0–10 + comentário no backend via `POST /nps`. É o concorrente/aliado direto do produto Escuta — vale espelhar a mesma lógica de gatilho para o canal WhatsApp.
- **A equipe da Bizzu já tem painel de NPS** (`/gestao/nps`, `GestaoNpsPage`) com gauge, distribuição, NPS por gatilho, evolução semanal e lista de comentários paginada. E **já tem central de atendimento/tickets** (`/gestao/atendimentos`) com thread por email, status, prioridade e anexos. Ou seja: a "Voz do Cliente" interna existe, mas presa ao app web; o Escuta entra como camada WhatsApp.
- **Captura de telefone existe e é OPCIONAL** no signup (`telefone` → backend). O número é validado por `libphonenumber-js` (`isValidPhoneNumber`). É o gancho natural de opt-in.
- **Opt-in de WhatsApp JÁ FOI PLUGADO localmente por nós** em dois lugares: checkbox `whatsappOptIn` no `Signup.jsx` (aparece só quando há telefone válido) e toggle na aba "Dados cadastrais" da `MinhaContaPage.jsx`. Ambos mandam `whatsappOptIn` no corpo (`POST /auth/signup` e `PATCH /user/me`). **Depende de o backend persistir o campo** (o front já lê `data.whatsappOptIn`).
- **NÃO há exit survey no cancelamento.** `MinhaAssinaturaPage` cancela com um `window.confirm` seco (`POST /user/subscription/cancel`) e dispara só o evento `subscription_cancelled` (refund). Zero captura de motivo. É a **maior lacuna/oportunidade** para o Escuta: gatilho de churn com pesquisa de saída via WhatsApp.
- **Telemetria é PostHog + GA**, com `trackEvent()` instrumentado de ponta a ponta (funil de signup campo-a-campo, checkout passo-a-passo, NPS, churn). Eventos como `subscription_cancelled`, `nps_submitted`, `user_signed_up` são candidatos a webhooks/gatilhos para o Escuta.
- **Auth é JWT em `localStorage`** (`token`), enviado como `Bearer` em todo request; sem cookies de sessão de API. Backend REST puro (`VITE_API_URL`), chamado direto via `fetch` (sem axios/react-query).
- **Identidade visual:** indigo `#6C5CE7` (primária), gold `#F5A623` (accent), fundo quase-preto `#0c0b10`; fontes Space Grotesk (títulos) + DM Sans (corpo). Slogan "Estude o que importa." Tokens centralizados em `theme/brand-tokens.css`.

---

## 1. Stack & build

`package.json` (`name: bizzu-frontend`, `type: module`, Node ≥22):

- **Build:** Vite **6** (`vite.config.js`) + `@vitejs/plugin-react`. Scripts: `dev`, `build` / `build:staging` / `build:production` (por `--mode`), `preview`. Sem TypeScript (JSX puro).
- **UI:** React **18.3** + React DOM. **Tailwind CSS v4** via `@tailwindcss/vite` (config CSS-first em `index.css` com `@theme`, sem `tailwind.config.js`). Ícones `lucide-react`. Animações `framer-motion`. Tooltips `@radix-ui/react-tooltip`. Editor rich text `react-quill` (comentários). `react-helmet-async` (head). Toasts `react-hot-toast`.
- **Roteamento:** `react-router-dom` **7** (modo declarativo `<Routes>`; README diz "v6" mas o pinned é 7).
- **Estado:** **sem Redux/Zustand**. Context API (`AuthContext`, `CurrentEditalContext`, `StudyRoutineContext`, `ThemeContext`) + `useState`/`useReducer` locais. Sem react-query — fetch manual em cada página/hook.
- **Forms:** sem lib de form. Estado controlado manual + validação custom (`utils/passwordValidation.js`, regex de email). Telefone com `react-phone-number-input` + `libphonenumber-js`.
- **Pagamento:** **Stripe.js** — `@stripe/stripe-js` + `@stripe/react-stripe-js` (re-exportados em `src/external-libraries/stripe.js`). `CardElement` + `confirmCardPayment`. **Pix** como método alternativo (QR code via API própria, não Stripe).
- **Analytics/telemetria:** **PostHog** (`posthog-js` + `@posthog/react`, init em `main.jsx` com session recording e `PostHogErrorBoundary` global) **e Google Analytics** (`analytics/gtag.js`, `initGtag`/`sendPageView` no `App.jsx`).
- **Segurança/util:** `dompurify` (sanitização de HTML, `external-libraries/sanitizeHtml.js`).
- **Testes:** **Vitest 4** + Testing Library + jsdom (`vitest.config.js`, `vitest.setup.js`). 82 arquivos `*.test.*` (co-locados, focados em view-models/lógica pura — ver §8).
- **Como roda (dev):** `npm run dev` → Vite na 5173, **proxy `/api` → `http://localhost:3000`** (rewrite tira o `/api`). `host: 0.0.0.0`, allowedHost ngrok hardcoded. Build é dockerizado (`Dockerfile` multi-stage + `nginx.conf`); landing-page estática em `public/landing-page.html` servida fora do SPA.

Build injeta commit/data git via `define` (`__FRONTEND_COMMIT__`, `__FRONTEND_DATE__`) — exibidos em `/version` (`VersionPage`).

---

## 2. Mapa de páginas (`src/pages/`)

Rotas definidas em `src/App.jsx` (entry: `main.jsx` → providers PostHog/Theme/Auth/Router → `App`). Layout global: `Header` + `Footer` + `PastDueBanner` + `ServiceSessionBanner` + `ActivationNoticeOverlay`.

### Públicas / auth
| Página (arquivo) | Rota | O que faz |
|---|---|---|
| `Login.jsx` | `/login` | Login email+senha e Google OAuth (`/auth/google`). |
| `Signup.jsx` | `/signup` | Cadastro (nome, email, **telefone opcional + checkbox whatsappOptIn**, senha c/ regras). Aceita `?plano=mensal\|anual`. Auto-login → `/checkout`. |
| `ForgotPasswordPage` / `ResetPasswordPage` | `/auth/forgot-password`, `/auth/reset-password` | Fluxo de recuperação de senha. |
| `AuthCallbackPage` | `/auth/callback` | Recebe token do OAuth Google e seta sessão. |
| `DescadastroPage` | `/descadastro` | Opt-out de comunicações (unsubscribe). |
| `ContatoPage` / `ReportarErroPage` / `PerguntasFrequentesPage` | `/contato`, `/reportar-problema`, `/perguntas-frequentes` | Contato (cria atendimento via `POST /contact`); reportar-erro é stub "em construção"; FAQ. |
| `VersionPage` | `/version` | Mostra commit/data do build. |

### Pagamento
| Página | Rota | O que faz |
|---|---|---|
| `CheckoutPage.jsx` | `/checkout` | **Núcleo de conversão.** Seleção de plano (mensal/anual) + Stripe `CardElement` ou Pix (com captura de CPF p/ Pix). Telemetria densa. |
| `PagamentoSucessoPage` / `PagamentoFalhaPage` / `PagamentoPendentePage` | `/pagamento/{sucesso,falha,pendente}` | Retorno pós-pagamento. |
| `PagamentoPixPage` / `RenovarPixPage` | `/pagamento/pix`, `/renovar-pix` | Exibe QR Pix e faz polling de confirmação; renovação Pix. |
| `BemVindoPage` | `/bem-vindo` | Boas-vindas pós-assinatura. |
| `EscolhaSeuPlanoPage` | `/escolha-seu-plano` | **Redirect** → `/minha-conta/assinatura`. |

### App do aluno (gated: `RequireAuth` → `RequirePlan` → `OnboardingGate` → `RequireCurrentEdital` + `RequireStudyRoutine`, dentro de `SidebarLayout`)
| Página | Rota | O que faz |
|---|---|---|
| `OnboardingPage.jsx` | `/onboarding` | Escolha do **contexto de estudo** (edital + cargo). Libera dashboard/Raio X/plano. Permite reusar contexto existente ou pedir edital faltante. |
| `onboarding-rotina/OnboardingRotina.jsx` | `/onboarding/rotina` | Define **rotina** (horas/dia por dia da semana). Recalcula prazos sem regerar plano. |
| `Dashboard.jsx` | `/dashboard` | Painel do aluno: progresso, cards de resumo, desempenho por matéria, tile do caderno. |
| `RaioXDaProvaPage.jsx` | `/raio-x-da-prova` | **Diferencial do produto.** "Raio X da prova": matérias/tópicos priorizados quantitativamente por incidência em questões reais; critérios e legenda de prioridade. (`GET /user-editais/:id/raio-x`) |
| `PlanoDeEstudoPage.jsx` | `/plano-de-estudo` | **Hub central de estudo.** Metas/tópicos, cronômetro de estudo, registrar estudo, abrir questões/anotações. **Onde o NpsModal é montado.** |
| `QuestoesPage.jsx` | `/questoes` | Lista/filtro de questões do edital. |
| `QuestoesFavoritasPage` / `QuestoesListaDetailPage` / `QuestaoDetailPage` | `/questoes/favoritas`, `/questoes/listas/:id`, `/questoes/questao/:id` | Favoritas, listas salvas, detalhe da questão (comentário IA, reportar erro). |
| `QuestaoSessaoPage.jsx` | `/questoes/sessao` | Sessão de resolução **fullscreen** (Header some). Modos IA/manual (`useSessaoIA`/`useSessaoManual`). |
| `CadernoHomePage` / `CadernoTopicoPage` | `/caderno`, `/caderno/topicos/:topicoId` | "Caderno" de erros/favoritas/notas por tópico, com autosave de anotações. |

### Conta / assinatura
| Página | Rota | O que faz |
|---|---|---|
| `MinhaContaPage.jsx` (`MinhaContaLayout` + seções) | `/minha-conta/*` | Dados cadastrais (**+ toggle whatsappOptIn + CPF**), rotina de estudo, trocar/definir senha. |
| `MinhaAssinaturaPage.jsx` | `/minha-conta/assinatura` | Ver assinatura, **cancelar** (window.confirm, sem survey), trocar de plano, retomar Pix pendente. |
| `MeusEditais.jsx` | `/meus-editais` | Editais/cargos do usuário. |

### Gestão/admin — ver §6.

---

## 3. Jornada do usuário (concurseiro)

Fluxo gated em cascata (cada gate redireciona se a etapa anterior falta):

1. **Descoberta → Signup.** Landing estática (`public/landing-page.html`, fora do SPA) com CTAs `…/signup?plano=mensal|anual`. `Signup.jsx` salva o plano (`utils/planoCheckout.js`) e cria conta (`POST /auth/signup`). Telefone é opcional; nosso checkbox de opt-in WhatsApp aparece quando o telefone é válido. Auto-login → `/checkout`.
2. **Pagamento.** `CheckoutPage` (gate `RequireAuth`): escolhe plano (mensal/anual, anual com "Economia 50%") e paga por **Stripe** (cartão) ou **Pix** (gera QR, exige CPF). Sucesso → `refetchUser()` (atualiza `planId` no JWT) → `/bem-vindo`.
3. **Onboarding de contexto.** `RequirePlan` libera `/onboarding`: escolher **edital + cargo** (contexto de estudo, salvo em storage + `CurrentEditalContext`). `OnboardingGate` garante que há contexto.
4. **Onboarding de rotina.** `/onboarding/rotina`: horas por dia. `RequireStudyRoutine` exige rotina antes de Raio X/plano/questões.
5. **Estudo (núcleo).** `RequireCurrentEdital` + `RequireStudyRoutine` liberam:
   - **Raio X** (`/raio-x-da-prova`): o que priorizar.
   - **Plano de Estudo** (`/plano-de-estudo`): metas/tópicos, cronômetro, registrar sessões, revisões, abrir questões/anotações. **É aqui que o NPS dispara** nos marcos.
   - **Questões** / sessões (IA/manual) e **Caderno** (erros, favoritas, notas).
6. **Conta & assinatura.** Header → dropdown → "Minha conta" / "Sair". `MinhaContaPage` (dados/rotina/senha) e `MinhaAssinaturaPage` (cancelar/trocar plano). `PastDueBanner` global avisa inadimplência; `RenovarPixPage` para renovar Pix.

Cada etapa está instrumentada com `trackEvent` (PostHog/GA).

---

## 4. Integração com o backend

- **Cliente HTTP:** `fetch` nativo direto, **sem axios nem react-query**. Cada arquivo em `src/api/*` (32 módulos) ou página monta a chamada na mão.
- **Base URL:** `import.meta.env.VITE_API_URL` (centralizado em `config/app.config.js` → `appConfig.api.baseUrl`, lido por `utils/planoEstudoApi.js::getPlanoEstudoApiUrl()`). Em dev, `vite.config.js` proxia `/api`.
- **Auth/JWT:** token em `localStorage['token']`. `getAuthHeaders()` (`utils/planoEstudoApi.js`) injeta `Authorization: Bearer <token>` + header fixo `ngrok-skip-browser-warning: true` (`getDefaultApiHeaders`). **Sem refresh-token rotativo via cookie**: `AuthContext.fetchUser()` chama `GET /user/me` no boot e dispara `POST /auth/refresh` em background para manter `planId` em sincronia. Logout → `POST /auth/logout` + limpa storage. Suporta **impersonação** ("service session": `sessionStorage['manager_token']`/`service_session_user`, banner em `ServiceSessionBanner`).
- **Identidade do usuário:** após `/user/me`, faz `posthog.identify(id, {email, name})`.
- **Onde ficam serviços/hooks de dados:**
  - `src/api/*` — wrappers REST por domínio: `npsApi`, `npsGestaoApi`, `atendimentosApi`, `dashboardApi`, `questoesApi`, `planoEstudoIaApi`, `studyRoutineApi`, `desempenhoApi`, `cadernoApi`, `editalExtractorApi`, `userEditaisApi`, `siteContentApi`, etc.
  - `src/hooks/*` — `useNpsCheck`, `useUserEditais`, `useSessaoBase/IA/Manual/Persistence`, `useFeatureFlag`.
  - Contexts em `src/context/*`.
- **Padrão de chamada:** `const res = await fetch(url, {headers: getAuthHeaders()}); if (!res.ok) throw/return null; return res.json()`. Erros geralmente engolidos com toast (`react-hot-toast`).
- **Endpoints-chave observados:** `/auth/{signup,login,logout,refresh,google}`, `/user/me` (+ `/cpf`, `/set-password`, `/change-password`, `PATCH` perfil), `/user/subscription` (+ `/cancel`, `/change-plan`), `/planos`, `/payments/create-checkout`, `/platform-config`, `/nps` (+ `/nps/check`), `/contact`, `/gestao/nps/{summary,comments}`, `/gestao/atendimentos/*`, `/user-editais/:id/raio-x`.

---

## 5. Feedback no front (CRÍTICO p/ Escuta)

### NpsModal + useNpsCheck (NPS in-app nativo)
- **Hook** `src/hooks/useNpsCheck.js`: expõe `{ npsTrigger, triggerCheck, clearTrigger }`. `triggerCheck()` chama **`GET /nps/check`** (`api/npsApi.js::checkNps`) que retorna `{ trigger }` (string do marco) ou null. Guard de **uma vez por sessão de navegação** (flag módulo-global `checkedThisSession`) + ref anti-concorrência. Falhas são silenciosas ("NPS não pode quebrar o fluxo principal").
- **Onde dispara:** apenas em `PlanoDeEstudoPage.jsx`. `triggerCheck()` é chamado: (a) após carregar o plano IA (`fetchAiPlan`, fim do load); (b) após qualquer `onTaskUpdate` (concluir/atualizar meta). O backend decide o gatilho; o front só pergunta. Gatilhos conhecidos (de `GestaoNpsPage`): **`FIRST_SESSION`** (primeira sessão), **`GOAL_HALF`** (50% da meta), **`GOAL_COMPLETE`** (meta concluída).
- **Modal** `src/components/NpsModal.jsx`: card flutuante bottom-center. Pergunta "De 1 a 10, qual a chance de você recomendar a Bizzu para um amigo?", grid 1–10, textarea opcional (≤500 chars). Categoriza PROMOTER(9-10)/PASSIVE(7-8)/DETRACTOR(≤6).
  - **Envia** `POST /nps` (`submitNps`) com `{ trigger, score, comment }`. Dismiss manda `score:null, comment:null` (registra "dismissal"). Auto-fecha 1.8s após envio.
  - Telemetria PostHog: `nps_shown`, `nps_score_selected`, `nps_submitted`, `nps_dismissed`.
- **Relevância p/ Escuta:** a lógica de gatilho por marco de jornada é exatamente o que o Escuta quer reproduzir no WhatsApp. O endpoint `/nps/check` já funciona como "motor de elegibilidade". Espelhar isso (ou consumir o mesmo sinal) evita duplicar regra de negócio.

### Exit survey no cancelamento — **NÃO EXISTE**
- `MinhaAssinaturaPage.jsx::handleCancel`: só um `window.confirm("Tem certeza que deseja cancelar…")`, depois `POST /user/subscription/cancel`. Dispara `trackEvent('subscription_cancelled', { refund_amount_cents })`. **Nenhum campo de motivo, nenhuma pesquisa de saída.** Esta é a oportunidade #1 do Escuta: pesquisa de churn (motivo de cancelamento) — seja inline aqui, seja via WhatsApp pós-cancelamento disparada pelo evento `subscription_cancelled`.

### Captura de telefone no signup
- `Signup.jsx`: campo "Celular (opcional)" via `PhoneInputField` (`react-phone-number-input` + `libphonenumber-js`). Validado por `isValidPhoneNumber`. Vai como `telefone` no `POST /auth/signup` (apenas se preenchido). Telefone também aparece em `ContatoPage` (pré-preenchido do user) e nos tickets de atendimento.

### Onde plugar opt-in de WhatsApp (e o que já fizemos localmente)
- **Signup (`Signup.jsx`):** estado `whatsappOptIn` no form; **checkbox condicional** que só renderiza quando há telefone válido ("Topo receber pesquisas e avisos do Bizzu no WhatsApp. Sem spam — dá pra sair quando quiser."). Enviado no body como `whatsappOptIn: form.phoneNumber ? form.whatsappOptIn : undefined`.
- **Minha Conta → Dados cadastrais (`MinhaContaPage.jsx`, `DadosCadastraisSection`):** carrega `whatsappOptIn` de `GET /user/me`; **toggle (checkbox)** "Receber pesquisas e avisos do Bizzu no WhatsApp", desabilitado sem telefone válido ("Adicione um celular para ativar"). Salvo via `PATCH /user/me` com `whatsappOptIn: form.phoneNumber ? form.whatsappOptIn : false`. Limpar o telefone zera o opt-in.
- Ambos comentados como "(Escuta)". **Pendência:** o backend precisa persistir/retornar `whatsappOptIn` no usuário (o front já lê `data.whatsappOptIn`). Confirmar no repo do backend.
- **Outros pontos plugáveis:** `DescadastroPage` (`/descadastro`) é o lugar natural para opt-out de WhatsApp; e os eventos `user_signed_up` / `subscription_cancelled` no PostHog podem acionar fluxos do Escuta.

---

## 6. Área de gestão/admin (`/gestao`, role `MANAGER`)

Gated por `RequireManager` (checa `user.role === 'MANAGER'`), dentro de `GestaoLayout` (sidebar com seções: Visão geral, Email, Cadastros, Comercial, Publicação, Infra, Knowledge Graph, Analytics). ~40 páginas em `src/pages/gestao/`. Destaques para o Escuta:

- **`GestaoNpsPage.jsx`** (`/gestao/nps`, seção "Analytics"): dashboard NPS completo (Recharts) — gauge -100/+100, score médio, total/dismissals, **taxa de resposta**, % promotores/passivos/detratores, distribuição de scores, donut, **NPS por gatilho** (primeira sessão / 50% / meta concluída), **evolução semanal**, e **lista de comentários** paginada com nome/email/score/gatilho/data. Consome `GET /gestao/nps/summary` e `/gestao/nps/comments` (`api/npsGestaoApi.js`).
- **`GestaoAtendimentosPage.jsx`** (`/gestao/atendimentos`): **central de tickets** estilo helpdesk. Lista filtrável (status: aberto/em_atendimento/resolvido/fechado; busca por nome/email/assunto; paginação). Painel de detalhe com **thread de mensagens** (admin × usuário), badges de status/prioridade/tipo (dúvida/erro/reclamação/sugestão), controles de status e prioridade, e **resposta por email com anexos** (`POST /gestao/atendimentos/:id/reply`, multipart, até 5 arquivos/10MB). API em `api/atendimentosApi.js`. Tickets nascem de `POST /contact` (ContatoPage).
- **`GestaoDashboardPage.jsx`** (`/gestao/dashboard`): visão geral com cards (faturamento, assinantes, NPS resumido via `npsColor`, atendimentos via `fetchAtendimentosStats`), solicitações de editais e cargos pendentes, filtro por período.
- Demais (fora do escopo Escuta): operação editorial, importar/extrair editais (com IA, `EditalExtractor`), importar questões, fila de processamento, knowledge graph, LLM observabilidade, radar de editais/matches, cadastros (editais/cargos/matérias/órgãos/bancas/áreas), comercial (assinantes/pagamentos/planos/reajuste/plataforma), email (boas-vindas/marketing), publicação de editais/conteúdo de site.

**Leitura p/ Escuta:** a Bizzu já internaliza NPS + atendimento. O Escuta não substitui isso — complementa com o **canal WhatsApp** (coleta proativa, churn survey, alcance de quem não abre o app). Idealmente o Escuta alimenta os mesmos dashboards (ou um equivalente) com o feedback vindo do WhatsApp.

---

## 7. Identidade visual

Tokens em `src/theme/brand-tokens.css` (fonte: `guideline/brand-guidelines-bizzu.html`), expostos ao Tailwind v4 em `src/index.css` (`@theme`):

- **Cores:** primária **indigo `#6C5CE7`** (`--indigo`; deep `#5B4BCF`, light `#A78BFA`, wash `#F0EBFF`). Accent **gold `#F5A623`** (`--gold`; usado no ponto da logo "Bizzu·" e em planos anuais). Estados: success `#10B981`, alert/erro `#EF4444`. Neutros escuros levemente tintados para indigo: void `#0c0b10` (fundo), ink `#14131a`, card `#1a1920`, charcoal `#28272e`, muted `#6e6d78`, silver `#a09fac`, canvas `#f9f8fc` (texto claro).
- **Tema claro:** suportado via `[data-theme="light"]` (`ThemeContext` + `ThemeToggle`), com overrides de tokens e classes utilitárias (`.sidebar-bg`, `.dashboard-card-*`, etc.) e correções de contraste.
- **Fontes:** títulos **Space Grotesk** (`--font-heading`), corpo **DM Sans** (`--font-body`); `font-variant-numeric: tabular-nums`. (Quill/dados usam família "data".)
- **Raios/espaços/easing:** escala de radius (6→100px), espaçamento (4→96px), `--ease-out: cubic-bezier(0.16,1,0.3,1)`. Respeita `prefers-reduced-motion`; foco visível com outline indigo.
- **Design system / componentes base:** `src/components/ui/` — `Button`, `Input`, `Card`, `Badge`, `SplitButton` (pequeno, não é shadcn). Muitos componentes de domínio em `src/components/**` (Dashboard, RaioX, Caderno, EditalExtractor, Checkout, ActivationNotice, gestao). Branding da marca: logo textual "Bizzu" + ponto gold + slogan "Estude o que importa." (Header).

---

## 8. Qualidade / dívida técnica

**Pontos fortes**
- **Telemetria de produto excelente:** `trackEvent` (PostHog + GA) cobre funil de signup campo-a-campo (`signup_field_focused/errored`), checkout passo-a-passo (`checkout_*`, incl. erros Stripe com decline_code), NPS e churn. Ótimo manancial de gatilhos para o Escuta.
- **Error boundary global** (`PostHogErrorBoundary` em `main.jsx`) com fallback amigável e captura de exceções.
- **Gating de rotas robusto** e em cascata; impersonação/service-session prevista.
- **Sanitização** com DOMPurify; CPF descrito como AES-256; Stripe não toca o servidor.
- **82 arquivos de teste** (Vitest), majoritariamente sobre **view-models e lógica pura** co-locada (`*.viewModel.test.js`, `cadernoTopicoPresentation.test.js`, `concursoDraftState.test.js`, etc.) e alguns components/guards (`RequirePlan.test.jsx`, `PastDueBanner.test.jsx`, `OnboardingGate.test.jsx`).

**Dívidas / pontos frágeis**
- **JWT em `localStorage`** (exposto a XSS). Sem refresh-token httpOnly; refresh é fetch manual em background.
- **Sem camada HTTP unificada:** `fetch` repetido em dezenas de arquivos; tratamento de erro inconsistente (ora toast, ora silêncio, ora `alert()` nativo em `GestaoAtendimentosPage`). Sem retry/cache (react-query ausente) → re-fetch manual e flicker.
- **`ReportarErroPage` é stub** ("em construção") embora linkada — caminho de feedback morto.
- **Cancelamento sem captura de motivo** (`window.confirm` cru) — perda de sinal de churn (lacuna p/ Escuta).
- **`whatsappOptIn` depende do backend** persistir/retornar o campo; se o backend ignorar, o toggle "funciona" no UI mas não tem efeito.
- **Inconsistências menores:** README diz "React Router v6"/rotas `/plano-de-estudos`,`/raio-x` que não batem com as rotas reais (`/plano-de-estudo`, `/raio-x-da-prova`); allowedHost ngrok e proxy `localhost:3000` hardcoded no `vite.config.js`; alguns textos com encoding/typo ("Topo receber" no checkbox de opt-in — provável "Topo/Topa"; "Voce"/"nao" sem acento em strings do CheckoutPage).
- **Sem TypeScript:** validação de shapes de API só em runtime; risco de drift com o backend.
- Página de Plano de Estudo é muito grande/stateful (cronômetro, modais, NPS) — candidata a refactor.

---

### Apêndice — arquivos-âncora (caminhos absolutos)

- Roteamento/entry: `C:\Users\jboni\Documents\Projetos\bizzu-repos\frontend\src\App.jsx`, `…\src\main.jsx`
- HTTP/Auth: `…\src\utils\planoEstudoApi.js`, `…\src\context\AuthContext.jsx`, `…\src\config\app.config.js`
- **NPS in-app:** `…\src\hooks\useNpsCheck.js`, `…\src\components\NpsModal.jsx`, `…\src\api\npsApi.js`, montado em `…\src\pages\PlanoDeEstudoPage.jsx`
- **Opt-in WhatsApp (nosso):** `…\src\pages\Signup.jsx` (checkbox), `…\src\pages\MinhaContaPage.jsx` (toggle em `DadosCadastraisSection`)
- **Churn (sem survey):** `…\src\pages\MinhaAssinaturaPage.jsx`
- Checkout/Stripe+Pix: `…\src\pages\CheckoutPage.jsx`, `…\src\external-libraries\stripe.js`
- Gestão feedback: `…\src\pages\gestao\GestaoNpsPage.jsx`, `…\src\pages\gestao\GestaoAtendimentosPage.jsx`, `…\src\api\npsGestaoApi.js`, `…\src\api\atendimentosApi.js`
- Telemetria: `…\src\utils\analytics.js`, `…\src\analytics\gtag.js`
- Tokens/visual: `…\src\theme\brand-tokens.css`, `…\src\index.css`, `…\src\components\Header.jsx`, `…\src\components\ui\`


================================================================
FONTE: docs\analise-bizzu\site.md
================================================================

# Análise Profunda — Bizzu Site Institucional

> Gerado em 08/06/2026. Leitura-only: nenhum arquivo foi modificado.

---

## Resumo Executivo

- **Site institucional / landing page** para assinatura da plataforma Bizzu — edtech de concursos públicos com IA. Não é o app; o app está em `plataforma.bizzu.ai`.
- **Proposta de valor central**: "Estude o que importa" — planejamento de estudos baseado em dados reais de 600 mil+ questões de bancas examinadoras, com Raio X da Prova (ranking de tópicos por prioridade real, cruzando banca + cargo + órgão + área).
- **Preços declarados**: R$ 10/mês ou R$ 60/ano (lançamento válido até 20/05). Preço cheio declarado internamente: R$ 60/mês ou R$ 650/ano. Garantia de 7 dias, sem fidelidade.
- **Captação de leads**: **ZERO captura de dados do visitante antes da assinatura.** Todos os CTAs levam diretamente a `plataforma.bizzu.ai/signup`. Não há campo de e-mail, telefone, WhatsApp ou lista de espera na landing page.
- **Analytics**: GA4 (`G-6WFC2DE7VE`) + PostHog (token injetado em runtime). Rastreamento UTM completo, scroll depth (25/50/75/100%), cliques em CTA por posição e variante.
- **Oportunidade clara para o Escuta**: adicionar captura de WhatsApp/e-mail antes da assinatura (hero ou exit-intent) permitiria nutrição de leads e funil NPS — atualmente não existe nenhum ponto de opt-in.

---

## 1. Stack & Propósito

| Item | Detalhe |
|---|---|
| Framework | Next.js 16 / React 19 / TypeScript 5 |
| CSS | Tailwind CSS 4 (v4, `@import "tailwindcss"`) |
| Deploy | Vercel (domínio `bizzu.ai`; redireciona `www.` → apex) |
| Papel | Site institucional — captação para assinatura. O produto real fica em `plataforma.bizzu.ai` |

**Padrão arquitetural incomum:** a home (rota `/`) é servida por um `GET` handler em `app/route.ts` que lê `public/landing-page.html` do disco, substitui o placeholder `__POSTHOG_TOKEN__` e retorna HTML bruto com `Cache-Control: public, max-age=3600`. Todo o conteúdo da landing page está em um único arquivo HTML estático de ~5.268 linhas, sem componentes React. As demais rotas (`/bancas`, `/editais`, `/editais/[slug]`, `/exemplo`) são páginas Next.js com componentes React/Tailwind.

---

## 2. Páginas & Conteúdo

| Rota | Tipo | Conteúdo |
|---|---|---|
| `/` | HTML estático servido via route handler | Landing page completa (hero, proof bar, depoimentos, problema, features, comparativo, preços, FAQ, CTA final, footer) |
| `/bancas` | Next.js page | Lista de bancas examinadoras disponíveis na plataforma (renderização client-side via `fetch /api/bancas`) |
| `/bancas/[slug]` | Next.js page | Perfil de cada banca com editais e concursos associados |
| `/editais` | Next.js page (SSR + ISR) | Lista de editais abertos com filtros de busca; hero com contadores de editais, vagas e bancas disponíveis |
| `/editais/[slug]` | Next.js page (SSR + ISR) | Detalhe do edital: cargos, cronograma, etapas da prova, salários, FAQ gerado dinamicamente, CTA "Montar meu plano para este edital" |
| `/exemplo` | Next.js page | Tour interativo da plataforma: Dashboard, Raio X do Tópico, Plano de Estudos, Questão Comentada, Caderno do Tópico |
| `/termos/termos-de-uso.html` | HTML estático | Termos de uso (arquivo em `public/termos/`) |
| `/termos/politica-de-privacidade.html` | HTML estático | Política de privacidade (arquivo em `public/termos/`) |

Não existe rota `/sobre`, `/blog`, nem `/parceiros` — o site é exclusivamente focado em conversão.

---

## 3. Proposta de Valor & Copy (frases declaradas)

### Tagline principal
- **"Bizzu · Estude o que importa."** (nav e footer)
- **Título H1 da home:** "Planejamento de estudos para concursos públicos com **inteligência**"

### Claims extraídos literalmente do HTML

- "600 mil questões reais analisadas" (proof bar, countup animado)
- "Maiores bancas examinadoras do Brasil"
- "12+ áreas de concursos"
- "IA — inteligência artificial aplicada"
- "Não é previsão nem achismo: são dados reais e verificáveis."
- "Modelo multifatorial: banca + cargo + órgão + área de atuação"
- "Classificação ALTA, MÉDIA e BAIXA por relevância comprovada"
- "Cada edital esconde um padrão. A Bizzu revela qual tópico pesa mais." (hero da página /editais)
- "O edital vira estratégia em minutos." (CTA em /editais)
- "A Bizzu não é um curso online e não vende aulas ou apostilas." (FAQ — diferenciação explícita)
- "Sim, a Bizzu complementa qualquer método ou curso preparatório." (FAQ)
- "Cancele quando quiser, sem fidelidade." (preços)
- "Garantia incondicional de 7 dias — Cancele nos primeiros 7 dias e receba reembolso integral, sem burocracia."

### Framing do problema (seção "O problema")
- "300+ Tópicos no edital — todos com o mesmo peso."
- "∞ Formas de organizar os estudos errado."
- "Zero Ferramentas que personalizam de verdade."
- "A maioria dos concurseiros perde tempo por falta de dados. Eles estudam no escuro."

### Depoimentos (nomes e perfis exibidos — verificabilidade não avaliada)
- Lucas R. / SEFAZ GO: "O Raio X mostrou que eu gastava 40% do tempo em tópicos que quase não caem."
- Camila S. / TJCE: "Trabalho o dia inteiro e só tenho 2 horas à noite para estudar. O plano automático me diz exatamente o que fazer."
- Rafael M. / PMAL 2026: "O edital tinha mais de 200 tópicos. A Bizzu ranqueou por prioridade e eu soube por onde começar no primeiro dia."
- Ana P. / UNEAL 2026, Juliana F. / TJSC 2026, Pedro H. / IFCE 2026, Fernanda L. / SES/MG 2026.

### Funcionalidades declaradas
1. **Raio X da Prova** — ranking de tópicos por prioridade (Muito Alta / Alta / Média / Baixa), modelo multifatorial.
2. **Bizzu do Tópico** — resumo inteligente gerado por IA a partir de questões reais; "o que mais cai, armadilhas comuns e checklist de revisão".
3. **Plano de Estudos automático** — cronograma com metas semanais progressivas, cobre 100% do edital.
4. **Questões Selecionadas** — banco de 600 mil+ questões filtradas por tópico dentro do plano.
5. **Questões Comentadas** — explicação IA com "por que cada alternativa está certa ou errada", detecta gabarito equivocado.
6. **Caderno do Tópico** — organiza Bizzus salvos, favoritas, erros e anotações por tópico.
7. **Revisões Inteligentes** — desbloqueadas automaticamente após completar cada tópico.

### Público-alvo declarado
- **Iniciante** ("Primeiro concurso? O edital saiu e são centenas de tópicos.")
- **Experiente** ("Já investiu meses de estudo. A Bizzu mostra onde concentrar esforço.")
- **Profissional** ("Com poucas horas por dia, cada minuto conta.")

---

## 4. Preços Declarados

Arquivo canônico de preços: `app/(site)/lib/pricing.ts` (fallback com valores hardcoded).

| Plano | Preço Lançamento | Preço Cheio (fallback) | Período Promo |
|---|---|---|---|
| Mensal | **R$ 10,00/mês** | R$ 60,00/mês | até 20/05 |
| Anual | **R$ 60,00/ano** | R$ 650,00/ano | até 20/05 |

- Ambos os planos incluem acesso completo a todas as funcionalidades (não há plano gratuito ou freemium declarado).
- Garantia: 7 dias com reembolso integral.
- Sem fidelidade (cancel any time).
- O plano anual é apresentado como "Economize 50% comparado ao valor mensal total".
- CTAs de assinatura apontam para `https://plataforma.bizzu.ai/signup?plano=mensal` e `https://plataforma.bizzu.ai/signup?plano=anual`.

**Nota:** a data "até 20/05" está defasada (data atual: 08/06/2026). O preço pode ter sido ajustado na plataforma via `api.bizzu.ai/platform-config`, mas o fallback hardcoded ainda exibe "R$ 10/mês" e "R$ 60/ano".

---

## 5. Captação de Leads (CRÍTICO para o Escuta)

### O que existe atualmente

**Não há nenhum formulário de captura de leads no site.** Levantamento completo:

- Nenhum `<form>`, `<input type="email">`, `<input type="tel">` ou campo de WhatsApp no HTML gerado.
- Os CSS classes `.hero-form` e `.cta-form` existem no arquivo de estilos, mas **não são usadas em nenhum elemento HTML** do body — evidência de que houve um formulário em versão anterior que foi removido.
- Todos os CTAs são links diretos para `plataforma.bizzu.ai` ou `#pricing`:
  - Nav: "Entrar" → `https://plataforma.bizzu.ai`
  - Nav: "Assinar agora" → `#pricing`
  - Hero: "Assinar agora" → `#pricing` | "Ver amostra grátis →" → `/exemplo`
  - Pricing: "Assinar Mensal" → `https://plataforma.bizzu.ai/signup?plano=mensal`
  - Pricing: "Assinar Anual" → `https://plataforma.bizzu.ai/signup?plano=anual`
  - CTA Final: "Assinar agora" → `#pricing`

- **Não há** lista de espera, newsletter, captura de e-mail pré-assinatura, nem integração com WhatsApp, Telegram ou qualquer canal de mensagens.

### Oportunidade para o Escuta

O funil hoje é: **visita → preço → signup na plataforma**. Quem não converte na primeira visita é perdido permanentemente.

Pontos de inserção naturais para captura de WhatsApp/e-mail:

1. **Hero** — após o H1, antes ou depois do CTA "Assinar agora": um campo "Receba novidades e análise do seu edital pelo WhatsApp" capturaria visitantes ainda na fase de consideração.
2. **Exit-intent** — pop-up ao tentar sair da página, com oferta de "análise gratuita do seu edital por WhatsApp".
3. **Página `/exemplo`** — ao final do tour interativo, o visitante já viu o produto; é o momento ideal para opt-in antes de pedir o pagamento.
4. **Páginas de edital (`/editais/[slug]`)** — cada página já segmenta o visitante por concurso específico; uma captura contextualizada ("Quero receber atualizações deste edital no WhatsApp") converteria muito melhor que a landing genérica.

**Ausência de telefone/WhatsApp é confirmada**: nenhuma menção nos ~5.268 linhas de `landing-page.html` nem nas páginas React.

---

## 6. SEO / Analytics / Tracking

### Google Analytics 4
- Propriedade: `G-6WFC2DE7VE`
- Injetado em dois lugares: `app/layout.tsx` (via `<Script>`) e `public/landing-page.html` (script inline direto).
- Eventos GA4 personalizados: `click_subscribe` (com `event_label` por posição: `hero`, `pricing_mensal`, `pricing_anual`, `cta_final`).

### PostHog
- Token injetado em runtime via variável de ambiente `NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN` (substituído no HTML via `replace()` no route handler).
- Configuração: `autocapture: true`, `capture_pageview: true`, `capture_pageleave: true`, session recording com `maskAllInputs: false`.
- Proxy via Next.js rewrites: `/ingest/*` → `https://us.i.posthog.com/*` (contorna bloqueadores de ads).
- Eventos customizados implementados:
  - `landing_cta_clicked` (com `cta_label`, `cta_position`, `cta_variant`, `href`)
  - `landing_amostra_cta_clicked` (variante `amostra_tour_v1`)
  - `landing_sample_pdf_clicked` (para amostras PDF)
  - `landing_scroll_depth` (25%, 50%, 75%, 100%)
- Classificação de canal UTM automatizada: `paid_search`, `paid_social`, `email`, `organic_search`, `organic_social`, `referral`, `direct`.

### SEO
- Meta description da home menciona preço ("Preço de lançamento R$ 10/mês até 20/05") — desatualizado.
- Canonical URL: `https://bizzu.ai/`
- Open Graph completo (imagem 1200×630, locale `pt_BR`).
- Twitter card `summary_large_image`.
- Structured data (JSON-LD): `Organization`, `SoftwareApplication` (com `offers.price: "10.00"`), `FAQPage` com 12 Q&As.
- Sitemap gerado em `app/sitemap.ts`.
- Páginas de edital geram metadata dinâmico com informações do concurso (vagas, salários, data da prova) para SEO long-tail.
- `robots`: `index, follow`.

---

## 7. Identidade Visual

### Cores (variáveis CSS declaradas)
| Token | Valor | Uso |
|---|---|---|
| `--void` | `#09090B` | Background principal (quase-preto) |
| `--indigo` | `#6C5CE7` | Cor primária de ação e destaque |
| `--indigo-deep` | `#5B4BCF` | Hover do indigo |
| `--indigo-light` | `#A78BFA` | Labels, badges, texto secundário |
| `--gold` | `#F5A623` | Cor de destaque/contraste, atenção |
| `--gold-soft` | `#FBBF24` | Variante suave do gold |
| `--success` | `#10B981` | Confirmações, checks |
| `--alert` | `#EF4444` | Prioridade alta, alertas |
| `--canvas` | `#FAFAFA` | Texto principal claro |
| `--silver` | `#A1A1AA` | Texto secundário |
| `--muted` | `#71717A` | Texto terciário |

Tema escuro consistente com fundo `#09090B` e glow ambiental via gradientes radiais em indigo/gold.

### Tipografia
| Variável | Fonte | Uso |
|---|---|---|
| `--font-heading` | Space Grotesk (400–700) | Títulos H1–H3, nomes de planos |
| `--font-body` | Inter (300–900) | Corpo de texto, botões, labels |
| `--font-data` | JetBrains Mono (400–700) | Números, percentuais, rankings, badges de dados |

Fontes carregadas via Google Fonts no `<head>`. No layout Next.js, `Geist` e `Geist_Mono` são declaradas mas afetam apenas as páginas React (não o HTML estático da home).

### Tom de comunicação
- Direto, técnico mas acessível. Evita superlativos vagos; ancora cada claim em dados ("214 questões globais", "35 questões específicas de Banca+Área").
- Posicionamento anti-achismo: repetição deliberada de "dados reais", "verificável", "transparente".
- CTA principal é "Assinar agora" (conversão direta, sem free trial).

---

## 8. Outros Arquivos Relevantes

- `lib/leads-api.ts` — cliente HTTP para `/leads/bancas`, `/leads/editais`, `/leads/editais/{slug}` via API interna com `x-api-key`. Usado pelas páginas React de bancas e editais. **O nome "leads" é interno/técnico** — não indica captura de leads de marketing; é o endpoint de dados públicos de editais.
- `lib/public-api.ts` — cliente alternativo para dados públicos de editais (diferente do `leads-api`).
- `lib/json-ld.ts` — helpers para gerar JSON-LD (Organization, SoftwareApplication, FAQ).
- `lib/banca-profiles.ts` — dados de perfis de bancas.
- `instrumentation-client.ts` — inicialização do PostHog no client-side para páginas React.
- `app/sitemap.ts` — geração automática do sitemap XML.
- `posthog-setup-report.md` — relatório interno de implementação do PostHog.
- `public/amostras/` — PDFs de amostras de análise (referenciados por `data-sample-pdf` em alguns CTAs).
- `public/screenshots/` — screenshots do produto para o carrossel da landing page.

---

## Conclusão para o Projeto Escuta

O site da Bizzu é uma landing page de conversão direta sem nenhum ponto de captura de dados do visitante antes do pagamento. Isso representa uma lacuna clara: visitantes que não convertem na primeira visita são completamente perdidos. O Escuta pode preencher exatamente essa lacuna com um opt-in de WhatsApp contextualizado — especialmente nas páginas de edital (`/editais/[slug]`), onde o visitante já demonstrou intenção específica por um concurso. A integração com NPS pós-assinatura (via `plataforma.bizzu.ai`) é o gancho natural já identificado nos demais arquivos do projeto.


================================================================
FONTE: docs\analise-bizzu\landing-pages.md
================================================================

# Análise: bizzu-repos/landing-pages

**Repositório:** `C:\Users\jboni\Documents\Projetos\bizzu-repos\landing-pages`
**Analisado em:** 2026-06-08
**Arquivos lidos:** `index.html`, `lista-de-espera/index.html`, `relatorios/auditor-fiscal-sefaz-sp-2026.html`, `relatorios/auditor-fiscal-sefaz-rn-2026.html`, `relatorios/analista-legislativo-camara-dos-deputados-2026.html`, `sitemap.xml`, `tag.txt`

---

## Resumo Executivo

- **Stack:** HTML/CSS/JS puro, sem framework. Hospedado em `lp.bizzu.ai`. Serve como entry point de toda a aquisição orgânica/paga.
- **Produto em pré-lançamento:** plataforma ainda não no ar ("fase final de desenvolvimento"). Captação é 100% lista de espera — sem venda, sem preço, sem garantia, sem urgência declarada.
- **Captação de leads: somente email**, via Google Forms (entry `entry.19628127`, form ID `1FAIpQLSePfBW-Xh1VF3D0pqLkK7jcSSU5SfFUHUd75SC0N8evTMwnkA`). Nenhum campo de telefone ou WhatsApp em nenhuma das páginas.
- **Prova social zero** (sem depoimentos, sem contagem de usuários, sem logos de clientes). Os números exibidos são claims de banco de dados ("500k questões", "5 bancas"), não usuários reais.
- **Tracking:** só Google Analytics GA4 (`G-6WFC2DE7VE`). Nenhum Meta Pixel, nenhum PostHog, nenhum pixel de retargeting.
- **Oportunidade Escuta:** lead entra com email apenas; capturar WhatsApp (ou enriquecer via link wa.me) seria upgrade direto com zero fricção adicional — e o produto ainda não existe para competir.

---

## 1. O Que É & Stack

### Produto
A Bizzu é uma plataforma de estudos para concursos públicos baseada em IA. Posicionamento: "não é curso, não vende aulas/apostilas". Proposta de valor central: ranquear tópicos por probabilidade real de cair, usando análise de 500 mil questões históricas das 5 maiores bancas (CEBRASPE, FGV, FCC, CESGRANRIO, VUNESP). Features prometidas:

1. **Raio X da Prova** — ranking de prioridade de tópicos por edital/banca/cargo
2. **Plano de Estudos automático** — cronograma gerado a partir do Raio X
3. **Banco de Questões por tópico** — questões selecionadas + explicação de erros por IA
4. **Revisão Espaçada automática** — revisões em 24h, 7, 15 e 30 dias

### Stack
- HTML/CSS/JS puro (zero frameworks, zero bundler)
- Fontes: Google Fonts (Inter, Space Grotesk, JetBrains Mono)
- Animações: IntersectionObserver + count-up JS nativo
- Sem Next.js, sem React, sem build step
- Servido em `lp.bizzu.ai` (domínio próprio, CDN não identificada pelo código)

### Estrutura de arquivos
```
landing-pages/
  index.html                          # Redirect meta-refresh 5s → lista-de-espera/
  lista-de-espera/index.html          # Landing principal (3082 linhas)
  relatorios/
    auditor-fiscal-sefaz-sp-2026.html # Raio X completo SEFAZ-SP (~5600 linhas)
    auditor-fiscal-sefaz-rn-2026.html # Raio X completo SEFAZ-RN (~3800 linhas)
    analista-legislativo-camara-dos-deputados-2026.html  # Raio X Câmara (~2200 linhas)
  sitemap.xml
  tag.txt                             # Snippet Google Analytics reutilizável
  image/favico.svg, favico.ico
```

---

## 2. Conteúdo / Copy de Conversão

### Headline principal (`lista-de-espera/index.html`, linha 2109)
> "Plano de estudos para concursos com **inteligência artificial**"

### Sub-headline (linha 2110)
> "A Bizzu analisa mais de 500 mil questões reais das maiores bancas do Brasil para mostrar quais tópicos mais caem na sua prova. Planejamento automático, questões selecionadas por tópico e revisões com repetição espaçada. Tudo baseado em dados reais, por banca, área e cargo."

### Badge / Contexto acima do H1 (linha 2107)
> "Plataforma de estudos para concursos públicos"

### Tagline / footer (linha 2847)
> "Estude o que importa."

### Seção-problema (linhas 2256–2280)
Três cards de números:
- **300+** tópicos no edital (Auditor Fiscal)
- **22** matérias para cobrir
- **0** ferramentas que resolvem isso ("Cursos vendem conteúdo. Planilhas organizam horas. Ninguém diz o que importa mais. Até agora.")

### Proof bar (linhas 2228–2248)
- 500k+ questões reais
- 5 bancas cobertas
- 12 áreas de concursos
- "estatística + ciência de dados + IA"

Estes números são **claims do produto** (banco de dados), não métricas de usuários. Nenhum depoimento, nenhuma avaliação, nenhuma contagem de "usuários cadastrados".

### Para quem é
Três perfis: Iniciante / Experiente / Profissional (trabalha e estuda).

### Posicionamento vs. concorrentes (linha 2768)
> "A Bizzu complementa qualquer método ou curso preparatório (Estratégia, Gran Cursos, Direção, entre outros). A Bizzu diz o que estudar e em que ordem priorizar. Seu curso ensina o conteúdo em si."

---

## 3. Preços / Oferta

**Nenhum preço declarado.** A única menção é vaga e de caráter especulativo, no FAQ (linha 2812):

> "A plataforma terá **planos acessíveis por assinatura mensal**. Entre na lista de espera para ser avisado no lançamento e garantir condições exclusivas de acesso antecipado."

Não há:
- Valores de lançamento
- Desconto de early access
- Garantia de devolução
- Conta regressiva / urgência real
- Quantidade de vagas limitadas

Os salários exibidos no slide panel (R$ 21.177 / R$ 13.283 / R$ 30.853,99) são dos **cargos dos concursos** analisados nos relatórios — não preços do produto (`lista-de-espera/index.html`, linhas 2883–2902).

---

## 4. Captura de Lead (CRÍTICO para Escuta)

### Mecanismo principal
**Somente email.** Dois formulários na landing principal:

| ID do form | Localização | CTA |
|---|---|---|
| `heroForm` | Hero section | "Quero acesso" |
| `ctaForm` | Seção final | "Garantir meu lugar" |

Ambos capturam apenas `input[type="email"]`. Nenhum campo de nome, telefone ou WhatsApp.

Mensagem pós-submissão (linha 2120): "Você está na lista. Avisaremos no lançamento."
Nota abaixo do botão (linha 2122): "Sem spam. Acesso antecipado para quem entrar agora."

### Destino dos leads — Google Forms
Todos os formulários (landing + 3 relatórios) submetem para o mesmo endpoint via `fetch` com `mode: 'no-cors'`:

```javascript
// lista-de-espera/index.html, linha 2935–2936
var GFORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSePfBW-Xh1VF3D0pqLkK7jcSSU5SfFUHUd75SC0N8evTMwnkA/formResponse';
var GFORM_ENTRY = 'entry.19628127';
```

O mesmo form ID e entry ID aparecem nos três arquivos de relatório (linhas 2212–2213, 3737–3738, 5552–5553). Não há webhook próprio, não há envio para CRM, não há API Bizzu sendo chamada — tudo vai direto para uma planilha Google Forms.

### Slide Panel (segundo ponto de captura)
Um painel lateral deslizante abre automaticamente 2,5 segundos após o carregamento (se não houver email salvo em `localStorage`), ou via FAB (botão flutuante). Permite selecionar um dos 3 concursos disponíveis e inserir email para acessar o "Raio X gratuito":

```javascript
// lista-de-espera/index.html, linhas 2944–2949
var REPORTS = [
  { cargo: 'Analista Legislativo – Câmara dos Deputados', banca: 'CESPE', salario: 'R$ 31.403',
    file: '/relatorios/analista-legislativo-camara-dos-deputados-2026.html' },
  { cargo: 'Auditor Fiscal da Receita Estadual – SEFAZ-RN', banca: 'CEBRASPE (CESPE)', salario: 'R$ 13.283',
    file: '/relatorios/auditor-fiscal-sefaz-rn-2026.html' },
  { cargo: 'Analista Legislativo – Câmara dos Deputados', banca: 'CEBRASPE (CESPE)', salario: 'R$ 30.853,99',
    file: '/relatorios/analista-legislativo-camara-dos-deputados-2026.html' },
];
```

Após o email, abre o relatório em nova aba. Os relatórios são HTML estáticos públicos — qualquer pessoa com a URL pode acessar sem fornecer email. Não há gate real.

### Formulários nos relatórios
Cada relatório (`sefaz-sp`, `sefaz-rn`, `analista-legislativo`) tem um formulário de "lista de espera" embutido no topo, com o mesmo endpoint Google Forms. CTA: "Quero acesso antecipado".

### Link wa.me / WhatsApp
**Inexistente.** Não há nenhum link `wa.me`, botão WhatsApp, ou campo de telefone em nenhuma das páginas. A captura é exclusivamente por email para Google Sheets.

---

## 5. Tracking / Pixels

| Ferramenta | Status | ID |
|---|---|---|
| Google Analytics (GA4) | **Ativo** em todas as páginas | `G-6WFC2DE7VE` |
| Meta Pixel (Facebook/Instagram) | **Ausente** | — |
| PostHog | **Ausente** | — |
| Hotjar / FullStory | **Ausente** | — |
| LinkedIn Insight Tag | **Ausente** | — |
| TikTok Pixel | **Ausente** | — |

O snippet GA4 está centralizado em `tag.txt` e incluído manualmente em cada HTML. Não há tag manager (GTM), apenas o snippet direto.

---

## 6. Conteúdo dos Relatórios "Raio X"

Os três relatórios HTML são documentos de análise extensos (2.200–5.600 linhas cada), com:

- Mapa de matérias com distribuição de prioridade Alta/Média/Baixa
- Tabelas tópico a tópico com justificativas geradas por IA
- Dados de frequência histórica por banca

**Exemplo de dados reais nos relatórios:**

| Concurso | Banca | Matérias | Tópicos | Salário |
|---|---|---|---|---|
| Auditor Fiscal SEFAZ-SP | FCC | 24 | 469 | R$ 21.177,10 |
| Auditor Fiscal SEFAZ-RN | CEBRASPE | — | — | R$ 13.283,64 |
| Analista Legislativo Câmara | CEBRASPE | 10 | 106 | R$ 30.853,99 |

Os dados de frequência (ex: "Direitos e Garantias Fundamentais · 127 questões · Presente em 94% das provas CESPE") **parecem reais** — são específicos, citam quantidades e anos de provas. Não há indicação de que sejam hardcoded/fictícios na estrutura do HTML: são tabelas densas com justificativas contextualizadas por cargo.

---

## 7. Oportunidade Escuta / Análise para Integração

### Fraquezas na captação atual
1. **Somente email** — sem telefone, sem WhatsApp. Lead entra frio e fica em uma planilha Google Forms sem follow-up automatizado visível.
2. **Sem gate real nos relatórios** — os arquivos HTML são públicos. O "email para acessar" é contornável com a URL direta. Incentivo para conversão é baixo.
3. **Sem prova social** — nenhum depoimento, nenhum contador de "X concurseiros já cadastrados".
4. **Sem urgência/escassez** — nenhuma mecânica de pressão de conversão.
5. **Tracking limitado** — só GA4, sem pixel de retargeting para reimpactar visitantes.

### Ganchos para Escuta / WhatsApp
- **Lead já existe** (Google Forms → planilha) mas sem canal de ativação. WhatsApp seria o canal natural de follow-up para pré-lançamento.
- Um campo `"Receber aviso pelo WhatsApp?"` ou link `wa.me` pós-cadastro de email não conflita com nenhum mecanismo existente.
- Os relatórios "Raio X" são conteúdo de alto valor — gatilho natural para uma sequência de nutrição via WhatsApp ("você acessou o Raio X do SEFAZ-SP, quer receber dicas de estudo para esse concurso?").
- A Bizzu já tem fluxo NPS in-app básico (conforme `docs/INTEGRACAO_BIZZU.md`) — o Escuta pode se posicionar como a camada de WhatsApp que complementa esse fluxo **antes mesmo do produto entrar no ar**, na fase de lista de espera.


================================================================
FONTE: docs\analise-bizzu\radar-editais.md
================================================================

> Exploração profunda realizada em 08/06/2026. Clone local: `C:\Users\jboni\Documents\Projetos\bizzu-repos\radar-editais`. Fontes: `CLAUDE.md` (fonte única do repo), `src/radar_editais/*` (todos os módulos lidos), `pyproject.toml`, `docker-compose.yml`, `docs/radar-editais.md` (contrato cross-repo).

# Radar de Editais — Análise Profunda

## Resumo Executivo

- Monitor diário de concursos públicos brasileiros: coleta via MCP do PCI Concursos, enriquece com Gemini, baixa PDFs para S3 e persiste tudo em Postgres próprio (porta 5434). Não compartilha banco com a plataforma principal.
- Pipeline de 5 fases (discover → filter → normalize → diff → enrich+persist) levando ~15 min/rodada; o diff classifica editais como `novos / atualizados / mesmos / encerrados` a cada sync.
- Gemini é usado em três pontos distintos: (1) filtro de seleções ambíguas (efetivo vs PSS), (2) extração estruturada de campos da notícia (banca, taxa, fases, data de prova, prova objetiva, PSS), e (3) classificação de PDFs candidatos antes do download.
- Flag `interesse_bizzu` (indexada em Postgres) é a regra de negócio central: só concursos com prova objetiva + conteúdo programático são sinalizados; os demais ficam ocultos com `motivo_descarte` gravado.
- Segurança de serviço via `X-Radar-Api-Key` (HMAC constant-time); UI via JWT HS256 delegado à `api.bizzu.ai`. Porta default real é 7400 (não 8000 como alguns docs legados citam).
- Não existe hoje nenhum mecanismo de notificação a usuários (sem webhook out, sem WhatsApp, sem e-mail).
- Oportunidade clara e cirúrgica para Escuta: conectar no evento `diff.novos` (linhas 297-317 de `pipeline.py`) para disparar WhatsApp "saiu o edital do seu concurso" — um único ponto de integração, sem modificar a lógica existente.

---

## 1. Propósito e Stack

### O que faz

O radar detecta diariamente quais concursos públicos brasileiros são novos ou foram atualizados, enriquece os dados via IA (banca, taxa de inscrição, data de prova, PDFs), aplica um filtro de relevância para a Bizzu e persiste tudo em banco próprio. É a "fonte da verdade de editais" do ecossistema Bizzu, operando de forma independente da plataforma principal.

Origem do nome: era `pci_mcp` (renomeado em maio de 2026 para `radar-editais`).

### Stack runtime

| Camada | Tecnologia |
|---|---|
| HTTP / API | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 async (`Mapped[]`) |
| DB driver | asyncpg |
| Banco | PostgreSQL 16 — porta **5434** (dev/Docker), banco próprio `radar-editais` |
| Migrations | Alembic (async env.py) |
| Storage S3 | aioboto3 (MinIO em dev, AWS S3 em prod) |
| Config | pydantic-settings (lê `.env.local`, gitignored) |
| CLI | Typer + Rich (`radar-editais sync|status|show|ui|db|prune|reenrich`) |
| Scraping | Crawl4AI (Chromium headless) |
| LLM | Google Gemini via `google-genai` SDK — modelo `gemini-3.1-flash-lite` |
| Testes | pytest + pytest-asyncio + pytest-postgresql (DB efêmero) + pytest-httpx |

### Agendamento

Não há scheduler embutido. O sync é disparado por:
- `scripts/cron-daily.sh` (bash wrapper para `crontab -e`, roda às 07h00)
- Systemd timer `radar-editais-sync.timer` na EC2 de produção (já foi encontrado inativo — ponto de atenção operacional)
- `POST /api/sync` da UI (botão "Sincronizar" — single-flight, background)

---

## 2. Pipeline — as 5 Fases

Código: `src/radar_editais/pipeline.py:run_pipeline()` (função assíncrona).

### Fase 1 — DISCOVER (`pipeline.py:242-253`)

Chama `McpClient.listar_concursos(regiao=r)` para cada uma das 5 regiões (`norte/nordeste/centro-oeste/sudeste/sul`). O cliente (`mcp_client.py`) fala JSON-RPC 2.0 sobre HTTPS com `https://www.pciconcursos.com.br/mcp`. Dedup por `noticia.id` (`_dedup_listings`, linha 45). Resultado: lista de `ConcursoListing` (Pydantic, campos: `titulo`, `cargos`, `uf`, `regiao`, `datas`, `noticia.link`, `apostila`).

### Fase 2 — FILTER (`pipeline.py:258-271`, `filter.py`)

Três sub-fases em sequência:

1. **Blocklist**: string-match em `titulo + cargos_resumo + noticia.titulo` contra ~40 marcadores (PSS, temporário, estágio, residência, cargo comissionado, remoção, CLT, brigadista, bolsista etc.) + regex `\breda\b`. Se bater: descarta imediatamente.
2. **Allowlist**: se contém "concurso público", "edital de concurso", "concurso de provas" etc.: aprova sem LLM.
3. **Gemini Flash**: para os ambíguos que não bateram em nenhuma das listas acima, dispara chamadas paralelas (`asyncio.gather`) ao Gemini com prompt de classificação binária (sim/não). Fallback conservador: `False` (descarta) em caso de erro.

A fase FILTER é **drop** — listings rejeitados aqui não chegam ao banco. É diferente do `interesse_bizzu` (que é soft-flag pós-enriquecimento).

### Fase 3 — NORMALIZE (`pipeline.py:278-283`)

Para cada listing aprovado, busca o registro anterior no banco (`ConcursoRepo.get(f"pci-{noticia_id}")`). Se existe, preserva `first_seen`, `enrichment` e `anexos_pdf` — garantia de que um resync não apaga dados de enriquecimento já feitos. Converte `ConcursoListing` → `Concurso` (modelo canônico Pydantic).

ID canônico: `pci-{noticia.id}` (ex.: `pci-98765`).

### Fase 4 — DIFF (`pipeline.py:285-293`, `repositories.py:260-287`)

Compara o estado atual com o snapshot de ontem (`SnapshotItemORM`). Campos rastreados: `inscricao_fim`, `inscricao_inicio`, `aberto`, `vagas_total`, `cargos`. Produz `DiffResult` com 4 listas: `novos / atualizados / mesmos / encerrados`.

### Fase 5 — ENRICH + PERSIST (`pipeline.py:297-342`)

Processa apenas `novos + atualizados`. Para cada um:

1. **Crawl4AI** (`enrich.py:fetch_noticia_markdown`): abre o link da notícia com Chromium headless, retorna markdown + HTML bruto + links externos.
2. **Gemini extração** (`enrich.py:extract_fields_via_gemini`): envia markdown truncado (30 000 chars) com prompt estruturado, extrai 13 campos: `banca`, `taxa_inscricao`, `data_prova`, `url_inscricao`, `fases`, `jornada_horas`, `regime`, `validade_anos`, `validade_prorrogavel`, `tem_prova_objetiva`, `tem_conteudo_programatico`, `eh_processo_seletivo_simplificado`, `extraction_confidence`. O resultado é armazenado em `Concurso.enrichment`.
3. **PDF discovery** (`pdf_extractor.py:collect_pdf_candidates`): varre o HTML por links com `.pdf`, textos-âncora com palavras-chave (edital, anexo, errata…) e domínios de bancas conhecidas (cebraspe, fgv, vunesp, ibfc etc.).
4. **Gemini classificação de PDFs** (`pdf_extractor.py:classify_candidates_with_gemini`): para cada candidato, decide tipo (`edital_principal`, `errata`, `retificacao`, `anexo_conteudo_programatico`, `anexo_outro`, `irrelevante`) e `should_download`.
5. **Download + S3** (`pdf_extractor.py:download_pdf`): baixa os PDFs marcados como `should_download=True`, valida magic bytes PDF (`%PDF-`), tamanho mínimo (50 KB), faz upload para S3 com chave `concursos/{slug}/{filename}`. Metadados (sha256, size, s3_key) persistidos em `anexos_pdf`.
6. **`aplicar_interesse(c)`** (`interesse.py`): define `interesse_bizzu` e `motivo_descarte` (ver §4).
7. **`ConcursoRepo.upsert(c)`** + `session.commit()`: commit **por concurso** (a UI vê dados progressivamente durante o sync longo).

Ao final, snapshot completo do dia é salvo em `SnapshotORM + SnapshotItemORM`.

**Tolerância a falhas**: erro em `_enrich_one` ou `upsert` de um concurso individual não derruba o run (try/except por item, rollback local, continua).

---

## 3. Modelo de Dados

### Entidades principais

**`concursos`** (tabela Postgres, mapeada em `db/orm.py:ConcursoORM`):

| Campo | Tipo | Nota |
|---|---|---|
| `id` | TEXT PK | `pci-{noticia_id}` |
| `slug` | TEXT UNIQUE | `{titulo-slugificado}-{uf}-{data_inicio}` |
| `titulo` | TEXT | título original do MCP |
| `uf`, `regiao`, `scope`, `esfera` | TEXT | normalizados |
| `cargos` | ARRAY(TEXT) | lista extraída |
| `vagas_total`, `salario_max` | INT, NUMERIC | parseados de `vagas_salario` |
| `inscricao_inicio`, `inscricao_fim` | DATE | |
| `aberto`, `dias_restantes` | BOOL, INT | |
| `banca` | TEXT | extraída pelo Gemini, coluna quente |
| `interesse_bizzu` | BOOL (indexado) | flag de relevância Bizzu |
| `first_seen`, `last_synced` | DATE, TIMESTAMPTZ | |
| `extra` | JSONB | `enrichment` completo + `motivo_descarte` |

**`anexos_pdf`** (metadados de PDFs; binários ficam no S3):

| Campo | Nota |
|---|---|
| `concurso_id` | FK `concursos.id` ON DELETE CASCADE |
| `tipo` | `edital_principal`, `errata`, `retificacao`, `anexo_conteudo_programatico`, etc. |
| `s3_key` | `concursos/{slug}/{filename}` |
| `sha256`, `size_bytes` | validação de integridade |
| `llm_classification`, `llm_summary` | output do Gemini sobre o PDF |

> Armadilha herdada: `AnexoPdf.local_path` (campo Pydantic) guarda o `s3_key` por decisão de migração — renomeação pendente (`CLAUDE.md` §Anti-padrões).

**`snapshots` + `snapshot_items`**: registro diário de estado para o diff. `snapshot_items.data` guarda o `Concurso.model_dump()` completo em JSONB, incluindo o `enrichment`.

### Flag `interesse_bizzu` — a regra de negócio central

Definida em `interesse.py:aplicar_interesse(c)` após o enriquecimento:

1. `selecao_nao_efetiva`: título/cargos batem na blocklist do `filter.py` (cobertura de legados).
2. `processo_seletivo_simplificado`: campo `enrichment.regime` contém marcador de temporário/regime especial (exceto carreiras policiais com "regime especial de trabalho policial").
3. `sem_prova_objetiva`: `tem_prova_objetiva=False` nas fases do Gemini, e sem PDF de conteúdo programático.
4. `None` → `interesse_bizzu=True`: interessa, ou inconclusivo (sem sinal suficiente → benefício da dúvida).

**A flag `eh_processo_seletivo_simplificado` do Gemini NÃO é usada na decisão** — em produção marcou ~95% de falso positivo lendo só a notícia. Está extraída apenas para inspeção.

Comando `radar-editais prune [--apply]` reaplica a regra a todo o banco (útil após mudança de critério). Comando `radar-editais reenrich [--abertos] [--so-faltando-flag]` re-roda o Gemini sem re-baixar PDFs.

---

## 4. Integração com o Backend Principal

### Auth de serviço

`auth.py` define dois esquemas:

- **Cookie JWT HS256** (role `MANAGER`): obtido via `POST /api/auth/login`, que proxeia credenciais para `https://api.bizzu.ai/auth/login`. O JWT recebido é validado com o `JWT_SECRET` local e armazenado como cookie `httponly; samesite=lax; secure`.
- **`X-Radar-Api-Key`** (role `SERVICE`): chave estática configurada em `RADAR_SERVICE_API_KEY` (.env.local). Comparação HMAC constant-time (`hmac.compare_digest`) para evitar timing attack. Acesso negado se a chave não estiver configurada (nunca concede por padrão). Rotas `GET /api/concursos` e `GET /api/concursos/{id}` e `GET /pdf/...` aceitam ambos (dependency `require_manager_or_service`).

### Sincronização de editais para a plataforma

O radar **não escreve diretamente** no banco da plataforma. A integração documentada (`docs/radar-editais.md` §8) é por **export para Google Sheet**, que o backend importa via `editais-garimpados` (flow `importacao-edital.md`). O mecanismo exato (Radar → Sheet automático ou export manual) não está implementado no código do repo — é um passo operacional externo.

Para consumo automatizado, o backend pode chamar `GET /api/concursos` com `X-Radar-Api-Key` — a API já retorna apenas `interesse_bizzu=true` por padrão.

---

## 5. Notificações — Estado Atual e Oportunidade Escuta (CRÍTICO)

### Estado atual: zero notificações

O radar **não notifica nenhum usuário**. A única saída "notificação" é o relatório markdown diário (`reporter.py:write_daily_report`) gravado em `data/reports/<date>.md` — não é enviado a ninguém, é apenas log local.

Não há: webhook OUT, integração WhatsApp, e-mail, push notification, ou qualquer canal de comunicação com usuários finais.

### Oportunidade: evento `novo_edital` → WhatsApp via Escuta

O ponto de integração é cirúrgico e está claramente demarcado em `pipeline.py`.

**Onde plugar** — `src/radar_editais/pipeline.py`, linhas 297-327:

```python
# Fase 5 — ENRICH + PERSIST
to_enrich = diff.novos + diff.atualizados   # linha 297
...
for i, c in enumerate(to_enrich, start=1):
    ...
    try:
        _, n_pdfs = await _enrich_one(c, pdf_storage=pdf_storage)
    ...
    aplicar_interesse(c)   # linha 317 — depois daqui, interesse_bizzu já está calculado
    # PONTO DE GANCHO: se c.interesse_bizzu and c.id in diff_novos_ids → disparar Escuta
    try:
        await concurso_repo.upsert(c)
        await session.commit()
```

**Implementação mínima sugerida**:

1. Adicionar variável `ESCUTA_WEBHOOK_URL` e `ESCUTA_API_KEY` em `config.py` (linha 19, após `service_api_key`).
2. Criar `src/radar_editais/notifications/whatsapp.py` com função async `notify_novo_edital(concurso: Concurso, webhook_url: str, api_key: str)`.
3. Em `pipeline.py`, após `aplicar_interesse(c)` (linha 317), adicionar:

```python
if c.interesse_bizzu and c.id in novos_ids_set:
    await notify_novo_edital(c, settings.escuta_webhook_url, settings.escuta_api_key)
```

**Payload recomendado para o Escuta**:

```json
{
  "event": "novo_edital",
  "edital_id": "pci-98765",
  "titulo": "Concurso Público — Prefeitura de Fortaleza CE",
  "uf": "CE",
  "regiao": "nordeste",
  "esfera": "municipal",
  "cargos": ["Analista de TI", "Contador"],
  "inscricao_fim": "2026-07-15",
  "dias_restantes": 37,
  "banca": "CEBRASPE",
  "taxa_inscricao": 85.0,
  "data_prova": "2026-09-14",
  "url_inscricao": "https://www.cebraspe.org.br/concursos/...",
  "noticia_link": "https://www.pciconcursos.com.br/...",
  "has_edital_pdf": true,
  "has_conteudo_programatico_pdf": true
}
```

**Dados já prontos no radar** que enriquecem a mensagem WhatsApp:
- `enrichment.banca` — "saiu o edital do CEBRASPE para Fortaleza!"
- `enrichment.taxa_inscricao` — mencionar taxa na mensagem
- `enrichment.data_prova` — "prova em setembro"
- `dias_restantes` — "faltam 37 dias para se inscrever"
- `cargos` — personalizar por cargo de interesse do usuário
- Link S3 para o PDF do edital principal (`GET /pdf/{slug}/{filename}` → presigned URL)

**Desafios operacionais**:

- O sync leva ~15 min → notificações chegam no "dia seguinte de manhã", não em tempo real (aceitável para o caso de uso de alertas diários).
- O Escuta precisará de uma tabela de preferências: qual usuário quer ser notificado sobre qual UF/cargo/esfera. Essa tabela vive no Escuta ou na plataforma Bizzu, não no radar.
- O radar não tem tabela de usuários — o cruzamento "qual usuário quer este edital" precisa ser feito no Escuta (recebe o evento com todos os dados, consulta suas próprias preferências, decide quem notificar).
- LGPD: usuário precisa ter optado por receber alertas WhatsApp. O opt-in deve existir na plataforma Bizzu antes de o Escuta disparar.

---

## 6. Qualidade, Dívida e Segurança

### Pontos de qualidade positivos

- Pipeline skip-tolerant por concurso: falha de enrich ou upsert não derruba o run.
- Commit incremental por concurso: UI fica atualizada progressivamente.
- `interesse_bizzu` é soft-flag (reversível): nenhum dado é deletado.
- Dedup robusto por `noticia.id` no discover; upsert resolve slug collision preservando `first_seen`.
- `immutable_unaccent()` como wrapper IMMUTABLE para o índice GIN trigram em `titulo` (solução correta para o Postgres que não aceita `unaccent()` STABLE em índices).
- Testes: ~28 arquivos de teste, incluindo DB ephêmero (pytest-postgresql), mocks httpx, e2e smoke.

### Dívida técnica conhecida

- `AnexoPdf.local_path` (campo Pydantic) guarda `s3_key` por decisão de migração; deve ser renomeado para `s3_key` em refactor futuro. Documentado em `CLAUDE.md` §Anti-padrões.
- `docs/plans/2026-05-07-*.md` descreve arquitetura antiga (JSON files); pode confundir se lida sem contexto. `CLAUDE.md` é a fonte única válida.
- Borda Radar → Google Sheet não automatizada (conforme `docs/radar-editais.md` §8 — "confirmar o mecanismo exato com o time").
- Systemd timer em produção já foi encontrado inativo (`CLAUDE.md` §"Branch deployado").
- Porta documentada no README como 8000, mas default real do CLI é 7400 (variável `PORT`).

### Segurança

**Segredos a observar** (locais, não expostos aqui):

- `.env.example` contém valores de exemplo hardcoded — incluindo `S3_ACCESS_KEY`, `S3_SECRET_KEY` e `GEMINI_API_KEY` com valores que parecem reais (não genéricos). Se esses valores foram comprometidos/rotacionados, o `.env.example` deve ser atualizado com placeholders `<SUBSTITUIR>`. Arquivo: `radar-editais/.env.example`, linhas 6-10 e 14.
- `JWT_SECRET` em `.env.example` tem valor padrão fraco (`change-me-in-production!@2`) — certifique-se de que `.env.local` de produção usa um segredo forte.

**Pontos positivos de segurança**:
- `X-Radar-Api-Key` usa `hmac.compare_digest` (constant-time, sem timing attack).
- Chave de serviço nunca concede acesso se não estiver configurada (`not configured or not provided → False`).
- Anti path-traversal em `GET /pdf/{slug}/{filename}` e `/img/{noticia_id}` (checa `/` e `..`).
- Cookie JWT com `httponly=True`, `samesite="lax"`, `secure=True`.
- Sem tabela de usuários no radar (superfície de ataque zero para PII).

---

## 7. Arquivos-Chave

| Arquivo | Papel |
|---|---|
| `CLAUDE.md` | Fonte única de verdade — arquitetura, setup, anti-padrões, gotchas |
| `src/radar_editais/pipeline.py` | Orquestrador das 5 fases; **PONTO DE GANCHO para Escuta nas linhas 297-327** |
| `src/radar_editais/models.py` | Modelo canônico `Concurso`, `Enrichment`, `AnexoPdf` (Pydantic) |
| `src/radar_editais/db/orm.py` | 4 tabelas ORM (SQLAlchemy 2.0): `concursos`, `anexos_pdf`, `snapshots`, `snapshot_items` |
| `src/radar_editais/db/repositories.py` | `ConcursoRepo.upsert`, `SnapshotRepo.diff_against`, `DiffResult` |
| `src/radar_editais/enrich.py` | Crawl4AI + Gemini; prompt de extração; modelo `gemini-3.1-flash-lite` |
| `src/radar_editais/filter.py` | Blocklist + allowlist + Gemini para seleções não-efetivas |
| `src/radar_editais/interesse.py` | Regra `motivo_descarte` + `aplicar_interesse` — central para o filtro Bizzu |
| `src/radar_editais/pdf_extractor.py` | Discovery, classificação Gemini e download de PDFs → S3 |
| `src/radar_editais/auth.py` | JWT HS256 cookie (MANAGER) + X-Radar-Api-Key HMAC (SERVICE) |
| `src/radar_editais/config.py` | `Settings` pydantic-settings; vars: DATABASE_URL, S3_*, GEMINI_API_KEY, JWT_SECRET, PLATFORM_API_URL, RADAR_SERVICE_API_KEY |
| `src/radar_editais/ui/server.py` | FastAPI: todas as rotas REST + lógica de sync em background |
| `src/radar_editais/mcp_client.py` | Cliente JSON-RPC 2.0 para `pciconcursos.com.br/mcp` |
| `src/radar_editais/normalize.py` | Slug, scope, esfera, `tem_prova_objetiva`, parse de vagas/salário |
| `src/radar_editais/reporter.py` | Relatório markdown diário do diff (log local, não enviado) |
| `docs/radar-editais.md` | Contrato cross-repo: contratos de API, filtro `interesse_bizzu`, borda com plataforma |
| `docker-compose.yml` | Dev stack: Postgres 16 (porta 5434) + MinIO (9000/9001) |
| `.env.example` | Template de variáveis — **contém valores de exemplo possivelmente reais** (ver §6 Segurança) |
| `scripts/cron-daily.sh` | Wrapper bash para crontab: `radar-editais sync` às 07h00 |


================================================================
FONTE: docs\analise-bizzu\infra.md
================================================================

# Análise Profunda — Infraestrutura Bizzu (gabarita-ai/infra)

> Leitura em 08/06/2026. Fonte: `~/Documents/Projetos/bizzu-repos/infra` (~56 arquivos).
> Arquivos lidos: `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `backend.tf`,
> `terraform.tfvars.example`, `environments/production/terraform.tfvars.example`,
> todos os `*-secrets.tf`, `secrets-policy.tf`, `modules/*/main.tf`, `modules/*/variables.tf`,
> `modules/radar-editais-ec2/user_data.sh`, `docs/INDEX.md` e docs individuais por módulo.

---

## Resumo Executivo

- **Cloud AWS us-east-1**, Terraform >= 1.0 com provider `hashicorp/aws ~> 5.0`. State remoto em S3 (`bizzu-terraform-state-633146206248/infra/terraform.tfstate`) com lock nativo (`use_lockfile`, requer Terraform >= 1.11).
- **11 módulos Terraform**: networking (VPC), dns-cert (Route 53 + ACM wildcard `*.bizzu.ai`), rds, elasticache, api-alb, api-asg, api-ec2, worker-asg, s3-cloudfront, s3-bucket, radar-editais-ec2. Ambiente único (`production`); sem workspaces ou diretórios `dev/staging`.
- **Compute**: ALB público + ASG NestJS (min 2 / max 4, `t4g.small` ARM64) + ASG Worker BullMQ (min 1 / max 3, `t4g.medium`) + EC2 individual para o site Next.js (`api-ec2`) + EC2 individual para o Radar Editais FastAPI (`radar-editais-ec2`). Todos em Amazon Linux 2023.
- **Dados**: RDS PostgreSQL 15 (`db.t3.small` Multi-AZ, gp3 criptografado, backup 7 dias, subnets privadas) + ElastiCache Redis 7.1 (`cache.t4g.micro`, subnets privadas). O Radar compartilha o mesmo RDS via `DATABASE_URL` (SG rule aberta).
- **Segredos**: 16 arquivos `*-secrets.tf` criam segredos em AWS Secrets Manager no namespace `prod/plataforma/*` (+ `prod/site/database` + `prod/radar-editais/db`). Instâncias consomem via IAM role; nenhum segredo versionado.
- **ACM wildcard `*.bizzu.ai` já emitido** (us-east-1). Qualquer subdomínio novo — incluindo `escuta.bizzu.ai` — é coberto sem nova solicitação de certificado.
- **Caminho recomendado para hospedar o Escuta**: criar `modules/escuta-ec2/` clonando o padrão de `radar-editais-ec2` (EC2 + EIP + Caddy + Route 53 A record), adicionar `escuta-secrets.tf` com path `prod/escuta/*`, referenciar subnet pública existente e zona Route 53 já provisionada. O Supabase do Escuta permanece separado do RDS Bizzu.

---

## 1. Visão Geral

| Item | Valor |
|---|---|
| Cloud | AWS |
| Região principal | `us-east-1` (us-east-1 também para ACM CloudFront, via provider alias) |
| Ferramenta | Terraform >= 1.0; provider AWS ~> 5.0 |
| State | S3 remoto: bucket `bizzu-terraform-state-633146206248`, key `infra/terraform.tfstate`, criptografado, lock nativo `use_lockfile` (Terraform >= 1.11) |
| Ambientes | Apenas `production` (`environments/production/terraform.tfvars.example`); sem separação dev/staging |
| Organização | Módulo por componente em `modules/`; secrets em arquivos raiz `*-secrets.tf`; política IAM consolidada em `secrets-policy.tf` |

O estado remoto ficou ativo em maio/2026 (commit `afa1c83`). O `terraform.tfstate.zip` antigo que continha a senha do RDS foi removido do tracking; senha deve estar rotacionada.

---

## 2. Recursos Provisionados

### 2.1 Compute (EC2 / ASG)

**API NestJS — ALB + ASG** (`modules/api-alb` + `modules/api-asg`):
- ALB público (`bizzu-api-alb`), listeners 80→301 e 443 (TLS 1.3, ACM), target group na porta 3000, health check em `/health`.
- ASG: min 2 / max 4 instâncias, `t4g.small` ARM64 (Amazon Linux 2023), 30 GB gp3. Rolling instance refresh. CloudWatch alarms (CPU > 70% → scale up; CPU < 20% → scale down).
- `user_data.sh`: instala Node 22, baixa artefato do S3 artifact bucket, injeta segredos do Secrets Manager, escreve `.env` (chmod 600), sobe serviço systemd `bizzu-api`.
- DNS: `api.bizzu.ai` → CNAME para `module.api_alb.alb_dns_name` (apontado no Cloudflare — comentário no `main.tf` linha 114).

**Site Next.js — EC2 individual** (`modules/api-ec2`):
- Instância `t4g.small` (ARM64), EIP estático, Caddy (Let's Encrypt), app em `/opt/bizzu-site`, 20 GB gp3.
- DNS: Route 53 A records para `bizzu.ai` e `www.bizzu.ai` → EIP.
- IAM role lê segredos: `prod/plataforma/database`, `prod/site/database`, `prod/plataforma/datadog`.

**Worker BullMQ — ASG** (`modules/worker-asg`):
- min 1 / max 3 instâncias, `t4g.medium` ARM64, 30 GB gp3. Sem ALB. CloudWatch alarms duplos: CPU e métrica customizada `Bizzu/Worker:QueueDepth` (> 5 → scale up; < 1 por 5 min → scale down).
- Processa filas BullMQ via Redis (seletor, geração de plano, extração de edital, comentário IA etc.).

**Radar Editais — EC2 individual** (`modules/radar-editais-ec2`):
- Instância `t4g.small` (ARM64, padrão; configurável via `radar_editais_instance_type`), EIP, Caddy, app FastAPI (uvicorn) em `/opt/radar-editais`, porta 7400.
- Systemd: `radar-editais.service` (uvicorn) + `radar-editais-sync.timer` (cron diário às 07:00 UTC).
- DNS: Route 53 A record `radar-editais.bizzu.ai` → EIP.
- IAM: lê `prod/plataforma/llm`, `prod/plataforma/jwt`, `prod/radar-editais/db`; acesso S3 ao bucket de PDFs.

### 2.2 Banco de Dados — RDS PostgreSQL

- Módulo: `modules/rds`. Identificador: `bizzu-postgres`.
- Engine: PostgreSQL 15, `db.t3.small` (variável `rds_instance_class`, default `db.t3.small`; tfvars.example usa `t3.micro` Free Tier).
- `multi_az = true` (produção); armazenamento 20 GB gp3 (auto-grow até 100 GB), criptografado.
- `backup_retention_period = 7`, `deletion_protection = true`.
- Subnets privadas (padrão). Acesso externo opt-in via `rds_publicly_accessible + rds_allowed_cidr_blocks`.
- SG rules em `main.tf` abrem porta 5432 para: `module.api_asg.security_group_id`, `module.worker_asg.security_group_id`, `module.radar_editais_ec2.security_group_id`.
- Banco padrão: `bizzudb` (variável `db_name`, default `bizzudb`; tfvars diz `plataforma`).
- Credenciais: secret `prod/plataforma/database` (campos: `username`, `password`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`).

### 2.3 Cache — ElastiCache Redis

- Módulo: `modules/elasticache`.
- Engine: Redis 7.1, `cache.t4g.micro`, 1 nó, porta 6379, subnets privadas.
- `maxmemory-policy = noeviction` (jobs BullMQ nunca eviccionados).
- SG rules: porta 6379 liberada somente para os SGs da API-ASG e Worker-ASG.
- Secret: `prod/plataforma/redis`.

### 2.4 Rede — VPC

- Módulo: `modules/networking`. CIDR `10.0.0.0/16`, 2 AZs.
- 2 subnets públicas (`/20` aprox.): ALB, EC2 com EIP. Internet Gateway.
- 2 subnets privadas: RDS, ElastiCache. Sem NAT Gateway (economia de custo: instâncias privadas sem saída direta para internet).
- Route tables: públicas ligadas ao IGW; privadas sem rota default.

### 2.5 Storage — S3

| Bucket (nome padrão) | Módulo | Uso |
|---|---|---|
| `bizzu-landing-lp-bizzu-ai` (gerado) | `s3-cloudfront` | Landing pages (lp.bizzu.ai) |
| `bizzu-plataforma-plataforma-bizzu-ai` (gerado) | `s3-cloudfront` | Frontend Vite (plataforma.bizzu.ai) |
| `plataforma-images-prod` | `s3-bucket` | Imagens privadas do backend (ETL migrations) |
| `bizzu-deploy-artifacts` | `s3-bucket` | Artefatos de deploy (CI → ASG instance refresh) |
| `radar-editais-pdfs` | `s3-bucket` | PDFs do Radar Editais |

Todos privados (`block_public_acls = true`). Buckets CloudFront usam OAC (Origin Access Control, não OAI legado).

### 2.6 CDN — CloudFront

- Módulo: `modules/s3-cloudfront`. Duas distribuições: landing (`spa_fallback = false`) e plataforma (`spa_fallback = true`, erros 403/404 → `index.html`).
- `PriceClass_100` (US + Europa), IPv6 habilitado, TLS mínimo 1.2, compressão ativa, TTL padrão 1h.
- Certificado ACM de `us-east-1` (obrigatório para CloudFront).

### 2.7 DNS — Route 53

- Módulo: `modules/dns-cert`. Hosted zone `bizzu.ai` criada pelo Terraform (`create_zone = true`).
- Records gerenciados: A records para `bizzu.ai`, `www.bizzu.ai`, `radar-editais.bizzu.ai` (→ EIPs); Alias records para `plataforma.bizzu.ai`, `lp.bizzu.ai` (→ CloudFront); registro CNAME para `api.bizzu.ai` feito fora do Terraform (no Cloudflare, conforme comentário `main.tf:114`).
- **Sem SQS** no código atual.
- **Sem Secrets Manager via SSM** — uso direto do Secrets Manager.
- **Sem WAF/Shield** explícito no código.

---

## 3. Módulos — Descrição

| Módulo | Localização | O que cria |
|---|---|---|
| `networking` | `modules/networking/` | VPC, 2 subnets públicas + 2 privadas, IGW, route tables/associations |
| `dns-cert` | `modules/dns-cert/` | Route 53 hosted zone (opcional), ACM cert (`bizzu.ai` + `*.bizzu.ai`, DNS validation), records de validação |
| `s3-cloudfront` | `modules/s3-cloudfront/` | S3 bucket privado, OAC, CloudFront distribution, Route 53 alias records; suporte a SPA fallback |
| `s3-bucket` | `modules/s3-bucket/` | S3 bucket privado simples (sem CloudFront); usado para images, artifacts, PDFs |
| `rds` | `modules/rds/` | RDS PostgreSQL, subnet group, security group |
| `elasticache` | `modules/elasticache/` | ElastiCache cluster Redis, subnet group, parameter group, security group + SG rules |
| `api-alb` | `modules/api-alb/` | ALB, listeners HTTP/HTTPS, target group (porta 3000), SG |
| `api-asg` | `modules/api-asg/` | Launch template, ASG, IAM role/profile/policy, SG, CloudWatch alarms + scaling policies |
| `api-ec2` | `modules/api-ec2/` | EC2 individual (site), EIP, IAM role (acesso a secrets), SG, Route 53 A records (raiz + www) |
| `worker-asg` | `modules/worker-asg/` | Launch template, ASG (sem ALB), IAM role, SG, CloudWatch alarms (CPU + queue depth) |
| `radar-editais-ec2` | `modules/radar-editais-ec2/` | EC2, EIP, IAM role (llm/jwt/db secrets + S3 PDFs), SG, Route 53 A record; user_data instala Python 3.11 + uvicorn + Caddy; systemd para uvicorn + timer diário |

---

## 4. Ambientes

Existe apenas **um ambiente**: `production`. O diretório `environments/production/` contém só um `terraform.tfvars.example`. Não há `dev`, `staging` ou workspaces Terraform.

Consequência para o Escuta: não há ambiente de homologação Bizzu para testar antes de produção. Qualquer módulo novo entra direto em `production`.

---

## 5. Segredos e Configuração

### Namespacing no Secrets Manager

| Path | Arquivo `*-secrets.tf` | Campos relevantes |
|---|---|---|
| `prod/plataforma/database` | `database-secrets.tf` | `username`, `password`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` |
| `prod/site/database` | `site-database-secrets.tf` | idem, para o site Next.js |
| `prod/plataforma/jwt` | `jwt-secrets.tf` | `JWT_SECRET` |
| `prod/plataforma/encryption` | `encryption-secrets.tf` | chave(s) de criptografia (CPF etc.) |
| `prod/plataforma/redis` | `redis-secrets.tf` | endpoint Redis |
| `prod/plataforma/llm` | `llm-secrets.tf` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` |
| `prod/plataforma/stripe` | `stripe-secrets.tf` | chaves Stripe |
| `prod/plataforma/asaas` | `asaas-secrets.tf` | chaves Asaas |
| `prod/plataforma/mercadolivre` | `mercadopago-secrets.tf` | chaves Mercado Pago |
| `prod/plataforma/sendgrid` | `sendgrid-secrets.tf` | `SENDGRID_API_KEY` |
| `prod/plataforma/sendkit` | `sendkit-secrets.tf` | chave SendKit |
| `prod/plataforma/google-oauth` | `google-oauth-secrets.tf` | OAuth Google |
| `prod/plataforma/facebook-oauth` | `facebook-oauth-secrets.tf` | OAuth Facebook |
| `prod/plataforma/google-sheet` | `google-sheet-secrets.tf` | service account Google Sheets |
| `prod/plataforma/datadog` | `datadog-secrets.tf` | `DATADOG_API_KEY` |
| `prod/radar-editais/db` | `radar-editais-secrets.tf` | `DATABASE_HOST/PORT/NAME/USER/PASSWORD` |

### Fluxo de consumo

`terraform apply` cria os secrets com valores vazios → operador popula via `aws secretsmanager put-secret-value` (comentários em cada `*-secrets.tf` mostram o comando exato) → `user_data.sh` das instâncias lê via `aws secretsmanager get-secret-value` no boot e escreve `.env` (modo 600) → serviço systemd carrega `EnvironmentFile`.

IAM policy consolidada em `secrets-policy.tf`: permite `GetSecretValue` em `prod/plataforma/*` e `prod/site/*` para os roles da API-ASG e Worker-ASG. O Radar-Editais tem policy própria mais restrita (só `llm`, `jwt`, `db` do radar).

### Variável crítica de apply

`TF_VAR_db_password` — obrigatório no ambiente onde `terraform apply` é executado. Sem ela o apply falha.

---

## 6. Domínios, DNS e Certificados

| Domínio | Tipo DNS | Destino | Certificado |
|---|---|---|---|
| `bizzu.ai` | Route 53 A → EIP | EC2 site (`api-ec2`) | Caddy / Let's Encrypt (na instância) |
| `www.bizzu.ai` | Route 53 A → EIP | EC2 site | idem |
| `api.bizzu.ai` | CNAME (Cloudflare, fora do TF) | ALB (`module.api_alb.alb_dns_name`) | ACM wildcard (ALB listener) |
| `plataforma.bizzu.ai` | Route 53 Alias → CloudFront | S3+CloudFront | ACM wildcard (us-east-1) |
| `lp.bizzu.ai` | Route 53 Alias → CloudFront | S3+CloudFront | ACM wildcard (us-east-1) |
| `radar-editais.bizzu.ai` | Route 53 A → EIP | EC2 radar | Caddy / Let's Encrypt |
| `suporte.bizzu.ai` | MX / SendGrid Inbound Parse | SendGrid | — (email, não HTTP) |

**ACM**: certificado único `bizzu.ai` + SAN `*.bizzu.ai`, emitido em `us-east-1`, validação DNS via Route 53. Cobre qualquer subdomínio de primeiro nível (ex.: `escuta.bizzu.ai`, `escuta2.bizzu.ai`) sem nova solicitação.

**Observação sobre `api.bizzu.ai`**: o comentário no `main.tf` linha 114 instrui definir um CNAME no Cloudflare. Isso significa que a zona primária do `api` está no Cloudflare, não no Route 53 — potencial duplo salto DNS. Os demais subdomínios usam Route 53 direto.

---

## 7. Onde o Escuta Vai Morar — Análise e Caminho Concreto

### Contexto do Escuta

O Escuta é composto por:
- **FastAPI** (Python) — backend NPS/pesquisa, porta 8000
- **WAHA** (WhatsApp HTTP API) — container Docker, porta 3000 ou 3001
- **Supabase** — banco de dados do Escuta (projeto `nlqeargxkidygbrahkbk`, conta `boxtrust34`, separado do RDS Bizzu)

### O RDS Bizzu é compartilhável?

**Não recomendado para o Escuta.** O RDS usa PostgreSQL 15 com Multi-AZ, mas pertence ao schema da plataforma Bizzu (banco `bizzudb`/`plataforma`). Adicionar o Escuta ao mesmo RDS criaria: (a) acoplamento de dados entre produtos distintos; (b) necessidade de criar usuário/schema separado no RDS Bizzu; (c) dependência operacional. O Escuta já tem Supabase próprio (`escuta` em `sa-east-1`) — mantê-lo separado é o caminho correto.

### Padrão disponível: `radar-editais-ec2`

O módulo `modules/radar-editais-ec2/` é o template ideal. Ele já resolve exatamente o caso de uso do Escuta:
- EC2 individual com EIP + Caddy (TLS automático via Let's Encrypt)
- IAM role com acesso restrito a seus próprios secrets
- Route 53 A record para `<subdomain>.bizzu.ai`
- `user_data.sh` que instala runtime, lê secrets do Secrets Manager, escreve `.env`, configura systemd

### Caminho concreto

**Passo 1 — Módulo Terraform `modules/escuta-ec2/`**

Criar clonando `modules/radar-editais-ec2/` com as seguintes adaptações:

- `app_dir = "/opt/escuta"`
- `subdomain = "escuta"`
- `user_data.sh`: instala Python 3.11 + Docker (para WAHA) + uvicorn; puxa secrets de `prod/escuta/*`
- Systemd: `escuta-fastapi.service` (uvicorn porta 8000) + `waha.service` (Docker porta 3001, interno)
- Caddyfile: `escuta.bizzu.ai → localhost:8000` (FastAPI); WAHA não exposto diretamente

**Passo 2 — `escuta-secrets.tf` (novo arquivo raiz)**

```hcl
resource "aws_secretsmanager_secret" "escuta" {
  name        = "prod/escuta/app"
  description = "Credenciais do Escuta (Supabase, WAHA, Webhook)."
}
```

Campos: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `WAHA_API_KEY`, `HOOK_SECRET`, `ADMIN_API_KEY`.

**Passo 3 — Referência em `main.tf`**

```hcl
module "escuta_ec2" {
  source          = "./modules/escuta-ec2"
  name_prefix     = var.project_name
  domain          = var.domain
  instance_type   = "t4g.small"         # ARM64, ~$0.017/h
  vpc_id          = module.networking.vpc_id
  subnet_id       = module.networking.public_subnet_ids[0]
  route53_zone_id = module.dns_cert.route53_zone_id
  aws_region      = var.aws_region
  ssh_key_name    = var.ssh_key_name != "" ? var.ssh_key_name : null
  secret_name     = "prod/escuta/app"
}
```

**Passo 4 — Security Group do Escuta**

O módulo cria seu próprio SG:
- Ingress 22 (SSH opcional, CIDR restrito)
- Ingress 80 + 443 (Caddy)
- Egress 0.0.0.0/0

WAHA (porta 3001) **não** precisa de ingress externo — FastAPI chama localmente. Se o Escuta precisar receber webhooks do WAHA externamente, abrir 3001 restrito ao próprio IP da instância (loopback basta).

**Passo 5 — DNS**

Route 53 A record `escuta.bizzu.ai` → EIP da instância. Gerenciado dentro do módulo (idêntico ao radar). ACM wildcard já cobre sem alteração.

**Passo 6 — Deploy**

Seguir o mesmo padrão do radar: SSH na instância + `git pull` + `systemctl restart escuta-fastapi`. Para deploy sem SSH: script `scripts/deploy/escuta` similar ao `landing`, ou considerar instance refresh de um ASG de 1 instância (over-engineering para o tamanho atual).

### WAHA — Considerações

O WAHA precisa de:
- Docker instalado na instância (não presente no `user_data.sh` do radar; adicionar `dnf install -y docker` + `systemctl enable --now docker`)
- Volume persistente para sessão WhatsApp (`/opt/escuta/waha-data`)
- Não expor porta 3001 externamente (comunicação interna apenas)
- Secret para `WAHA_API_KEY` em `prod/escuta/app`

### Alternativa: EC2 separado para WAHA

Se WAHA precisar de mais recursos (sessões múltiplas, alto volume), criar uma segunda instância `modules/waha-ec2/` menor (`t4g.micro`) na mesma VPC, com comunicação interna via IP privado. Para o piloto Bizzu (1 número, baixo volume), colocar tudo na mesma instância é suficiente.

### Separação Supabase x RDS

| | Escuta | Bizzu |
|---|---|---|
| Banco | Supabase `nlqeargxkidygbrahkbk` (sa-east-1, conta `boxtrust34`) | RDS `bizzu-postgres` (us-east-1) |
| Acesso | Via secret `prod/escuta/app` | Via secret `prod/plataforma/database` |
| SG rule no RDS | **Nenhuma** (Escuta não toca o RDS) | API + worker + radar |

Manter separado elimina qualquer risco de schema collision e simplifica o offboarding caso o Escuta seja descontinuado.

---

## 8. Resumo Executivo Detalhado

1. **Infraestrutura madura, custo-otimizada**: ALB+ASG para a API (HA real), EC2 individuais para serviços menores (site, radar), Redis gerenciado, RDS Multi-AZ. Sem ECS/Lambda/Fargate — tudo EC2. Tudo ARM64 (`t4g.*`) onde possível.

2. **11 módulos bem estruturados**: cada um com `main.tf`, `variables.tf`, `outputs.tf`. O módulo `radar-editais-ec2` é o template direto para o Escuta (FastAPI + Caddy + systemd).

3. **Secrets Manager bem organizado** (`prod/plataforma/*`): 16 segredos, cada um em arquivo dedicado `*-secrets.tf`. Adicionar `prod/escuta/*` segue o padrão sem atrito.

4. **ACM wildcard `*.bizzu.ai` já ativo** (us-east-1): `escuta.bizzu.ai` é coberto sem nenhuma mudança no módulo `dns-cert`.

5. **Ambiente único (`production`)**: não há staging/dev IaC. Testar mudanças de infra exige cuidado — qualquer `terraform apply` vai direto para produção.

6. **Ponto de atenção**: `api.bizzu.ai` usa CNAME no Cloudflare (fora do Terraform), não Route 53. Os demais subdomínios são Route 53. O `escuta.bizzu.ai` seguirá o padrão Route 53 (como o radar).

7. **Custo estimado do Escuta**: `t4g.small` (~$0.017/h) ≈ $12/mês + EIP ($0.005/h ocioso = $3.6/mês se parado, $0 se sempre rodando) + R53 query charges irrisórios. Total: ~$12-16/mês.

---

## Caminhos-Chave

| Arquivo | Relevância |
|---|---|
| `infra/main.tf` | Orquestração de todos os módulos; adicionar `module "escuta_ec2"` aqui |
| `infra/variables.tf` | Adicionar `escuta_secret_name`, `escuta_instance_type` |
| `infra/modules/radar-editais-ec2/` | Template para `modules/escuta-ec2/` |
| `infra/modules/radar-editais-ec2/user_data.sh` | Base para o `user_data.sh` do Escuta (Python + Caddy + systemd) |
| `infra/radar-editais-secrets.tf` | Base para `escuta-secrets.tf` |
| `infra/secrets-policy.tf` | Adicionar attachment do IAM role do Escuta se necessário |
| `infra/backend.tf` | State remoto S3; não alterar |
| `infra/modules/dns-cert/main.tf` | Confirma wildcard `*.bizzu.ai` — sem necessidade de alteração |
| `infra/docs/secrets.md` | Documentação canônica dos secrets |
| `infra/docs/radar-editais.md` | Descrição do módulo usado como template |


================================================================
FONTE: docs\corpus_bizzu\o-que-e-bizzu.md
================================================================

---
title: O que é a Bizzu
source: bizzu
tags: [sobre, proposta-de-valor, publico, posicionamento]
---

## O que é a Bizzu

A Bizzu é uma plataforma de estudos para concursos públicos que usa inteligência artificial e ciência de dados para ajudar concurseiros a estudar o que realmente importa. Ela analisa um banco de mais de 600 mil questões reais de provas aplicadas pelas maiores bancas examinadoras do Brasil para montar um ranking de prioridade dos tópicos, personalizado por edital, banca, área e cargo. A partir dessa análise, a plataforma gera um resumo inteligente de cada tópico, monta um plano de estudos automático, seleciona questões e agenda revisões.

## O que a Bizzu não é

A Bizzu não é um curso online e não vende aulas nem apostilas. Ela não ensina o conteúdo em si: o papel dela é dizer o que estudar e em que ordem priorizar. Por isso, ela complementa qualquer método ou curso preparatório (como Estratégia, Gran Cursos, Direção, entre outros) em vez de substituí-lo. Na prática, o aluno usa a Bizzu para descobrir quais tópicos merecem mais atenção e usa o curso ou material dele para aprender a matéria.

## Para quem é

A Bizzu foi desenvolvida para quem estuda para concursos públicos, em qualquer fase da preparação. Funciona com concursos de qualquer banca, área ou nível (médio, superior, técnico). Dezenas de editais das maiores bancas já estão disponíveis na plataforma, e novos editais são adicionados continuamente.

## Proposta de valor

A diferença central da Bizzu é a transparência baseada em dados reais. Os rankings e recomendações não são previsões subjetivas nem achismo: eles mostram padrões históricos verificáveis. Para cada recomendação, a plataforma deixa visíveis os números por trás dela — a frequência do tópico, a banca examinadora, o período analisado e a quantidade de questões consideradas. A ideia é que o concurseiro tome decisões informadas sobre o que priorizar, em vez de gastar tempo igual em tudo.

## Onde acessar

O site institucional da Bizzu fica em bizzu.ai, e a plataforma de estudos (onde o aluno entra na conta e estuda) fica em plataforma.bizzu.ai. Quem ainda não assina pode conhecer a ferramenta pela amostra grátis disponível no site, antes de decidir assinar.


================================================================
FONTE: docs\corpus_bizzu\funcionalidades.md
================================================================

---
title: Funcionalidades da Bizzu
source: bizzu
tags: [funcionalidades, raio-x, plano-de-estudos, bizzu-do-topico, caderno, revisoes, questoes]
---

## Raio X da Prova

O Raio X da Prova é o ranking de prioridade de tópicos da Bizzu. A plataforma cruza o conteúdo do edital do aluno com o histórico de provas anteriores (um banco de mais de 600 mil questões reais das maiores bancas) e identifica quais tópicos aparecem com mais frequência, considerando a banca, a área do concurso e o cargo específico. O resultado mostra, de forma transparente, o que mais cai e o que merece mais atenção. Não é previsão nem achismo: são dados reais e verificáveis, com a frequência, a banca e o período analisado visíveis para cada recomendação. O Raio X é o ponto de partida da preparação na Bizzu.

## Plano de estudos automático

Depois de gerar o Raio X do concurso, a Bizzu monta automaticamente um cronograma de estudos personalizado, com metas semanais progressivas. O plano prioriza os tópicos com mais chance de cair, mas sem deixar nenhum conteúdo do edital de fora. A cada sessão, a plataforma define o próximo passo do aluno: estudar a teoria, resolver questões ou fazer uma revisão. À medida que o aluno registra o progresso, o plano se adapta. Não é preciso configurar nada manualmente. Vale lembrar que o plano tem caráter de recomendação e não garante cobertura integral do conteúdo do concurso; o aluno continua responsável por complementar com os materiais que julgar necessários.

## Bizzu do Tópico

O Bizzu do Tópico é um resumo inteligente gerado pela IA a partir das questões que já caíram sobre aquele tópico, na banca e na área do concurso do aluno. Ele mostra o que mais cai, os conceitos essenciais, as armadilhas comuns e um checklist de revisão. Em vez de ler dezenas de páginas de material teórico, o aluno tem um resumo direto ao ponto, baseado no que a banca realmente costuma cobrar.

## Questões selecionadas e Questões Comentadas

Para cada tópico do edital, dentro do plano de estudos, a Bizzu seleciona questões reais para o aluno resolver. Ao resolver uma questão, o aluno pode ver o Comentário da Bizzu — uma explicação que vai além do gabarito: mostra por que a alternativa correta está certa, por que cada errada cai na pegadinha, os conceitos envolvidos, a armadilha típica da banca e uma dica para a prova. Funciona para múltipla escolha e para certo/errado, e em alguns casos traz a referência (artigo de lei, jurisprudência) usada. Antes de exibir, a Bizzu confere o comentário duas vezes: tenta resolver a questão por conta própria e depois compara com o gabarito oficial. Quando essa conferência sugere que o gabarito oficial pode estar equivocado, a plataforma mostra uma "Observação da Bizzu" em vez de fingir certeza.

## Caderno do Tópico

O Caderno do Tópico organiza tudo o que o aluno marcou como importante, agrupado por tópico do edital. Bizzus salvos, questões favoritas, questões erradas (já com o Comentário da Bizzu por dentro) e anotações pessoais ficam todos juntos no tópico em que aparecem. Quando o aluno volta para revisar, encontra exatamente o que importou para ele — e não uma pasta de PDFs ou um caderno genérico. As anotações por tópico são salvas automaticamente enquanto o aluno digita, e tudo fica vinculado ao edital ativo, sem misturar com outros concursos.

## Revisões inteligentes

As revisões inteligentes são desbloqueadas automaticamente dentro do plano de estudos, depois que o aluno completa o estudo e as questões de cada tópico. Em vez de revisar só quando sobra tempo, a revisão passa a fazer parte da rotina, no momento certo. Cada revisão inclui o Bizzu do Tópico e questões adicionais para consolidar o aprendizado antes de o aluno avançar.

## Banco de questões e cobertura

Todas as funcionalidades da Bizzu se apoiam num banco de mais de 600 mil questões reais de concursos públicos, das maiores bancas examinadoras do Brasil. É esse acervo que alimenta o Raio X, o Bizzu do Tópico, as questões selecionadas e as revisões. A plataforma funciona para concursos de qualquer banca, área ou nível, e novos editais são adicionados continuamente.


================================================================
FONTE: docs\corpus_bizzu\planos-e-precos.md
================================================================

---
title: Planos e preços da Bizzu
source: bizzu
tags: [precos, planos, assinatura, mensal, anual]
---

## Como funciona a assinatura

A Bizzu funciona por assinatura. A assinatura dá acesso completo a todas as funcionalidades da plataforma — Raio X da Prova, Bizzu do Tópico, plano de estudos automático, questões selecionadas, Questões Comentadas, Caderno do Tópico e revisões inteligentes — sem restrição de uso. Não há fidelidade: dá para cancelar quando quiser. Há dois ciclos de cobrança, mensal e anual.

## Valores

Importante: os valores da Bizzu são definidos pela própria empresa e podem mudar, especialmente porque parte deles é preço de lançamento com prazo. Por isso, sempre confirme o valor atual diretamente em plataforma.bizzu.ai antes de assinar.

O material de divulgação registrava um preço de lançamento de R$ 10,00 por mês ou R$ 60,00 por ano, com prazo de validade (a data do cutoff aparecia como 20/05 nas páginas mais recentes). Após o fim do período de lançamento, o valor cheio divulgado era de R$ 60,00 por mês ou R$ 650,00 por ano. Como esses números são de campanha e mudam com o tempo, eles servem só como referência: para saber quanto custa hoje, o aluno deve consultar os valores atualizados em plataforma.bizzu.ai.

## O que está incluso

Em qualquer um dos planos, a assinatura libera acesso completo a tudo, sem limite de uso: o Raio X da Prova com ranking de tópicos, o Bizzu do Tópico (resumo inteligente por tópico), o plano de estudos automático com metas, a resolução de questões selecionadas para cada tópico do edital, as Questões Comentadas (com a explicação de cada alternativa, a armadilha da banca e a dica para a prova), o Caderno do Tópico, as revisões inteligentes no momento certo e a personalização por edital, banca e cargo. O assinante também tem acesso a todos os editais disponíveis, com novos editais sendo adicionados continuamente.

## Amostra grátis

Quem ainda não assina pode conhecer a Bizzu por uma amostra grátis disponível no site (bizzu.ai), antes de decidir assinar. Essa amostra é uma demonstração da ferramenta — não é um teste gratuito do produto completo. O acesso pleno a todas as funcionalidades vem com a assinatura.

## Garantia

A assinatura tem garantia de 7 dias: quem cancela dentro dos primeiros 7 dias da primeira cobrança recebe reembolso integral, sem burocracia. Os detalhes de cancelamento, reembolso e garantia estão no tema "Cancelamento e garantia".

## Lacunas conhecidas

Os pontos abaixo não estão documentados de forma confiável nas fontes consultadas e não devem ser afirmados ao aluno como fato. São perguntas a confirmar com o time da Bizzu:

- Preço atual em vigor. As fontes só trazem preços de campanha de lançamento (R$ 10/mês ou R$ 60/ano) com data de validade (20/05) e um preço cheio de referência (R$ 60/mês ou R$ 650/ano). Não há como saber, a partir do código, qual valor está ativo hoje — os preços são gerenciáveis pela própria Bizzu (vêm de configuração da plataforma) e a data do cutoff variou entre 15/05 e 20/05 em diferentes arquivos. Sempre direcionar o aluno a confirmar em plataforma.bizzu.ai.
- Existência de um período de teste gratuito (trial). Os Termos de Uso mencionam que a Bizzu "poderá oferecer" períodos de teste, mas a comunicação atual oferece apenas a amostra grátis (demonstração), não um trial do produto completo. Não confirmar trial sem checar com a empresa.
- Descontos, cupons, planos para grupos/turmas ou condições especiais — não documentados.
- Formas de pagamento aceitas do ponto de vista do aluno (cartão, Pix, boleto). O backend integra Stripe, Asaas/Pix e MercadoPago, mas a oferta exata exibida no checkout não está documentada nas fontes de marketing; confirmar no checkout em plataforma.bizzu.ai.
- Diferenças de benefício entre o plano mensal e o anual além do preço — as fontes indicam que ambos dão "acesso completo a tudo", sem distinção de recursos. Confirmar se há algum benefício exclusivo do anual.


================================================================
FONTE: docs\corpus_bizzu\cancelamento-e-garantia.md
================================================================

---
title: Cancelamento, reembolso e garantia da Bizzu
source: bizzu
tags: [cancelamento, reembolso, garantia, fidelidade, assinatura]
---

## Como cancelar

O aluno pode cancelar a assinatura a qualquer momento, sem fidelidade. O cancelamento é feito pelo próprio aluno, diretamente no painel de configurações da conta na plataforma (na área de assinatura, dentro de plataforma.bizzu.ai). Não é preciso ligar nem pedir autorização para cancelar.

## Garantia de 7 dias

A Bizzu oferece garantia de 7 dias. Quem cancela a assinatura dentro do prazo de 7 dias contados da data da primeira cobrança tem direito ao reembolso integral do valor pago, sem burocracia e sem perguntas. Esse direito está alinhado ao direito de arrependimento previsto no Código de Defesa do Consumidor (artigo 49 da Lei nº 8.078/1990). Nesse caso, o acesso aos serviços é encerrado assim que o reembolso é processado.

## Cancelamento depois dos 7 dias

Se o cancelamento for solicitado após os primeiros 7 dias, não há reembolso do valor já pago referente ao ciclo em andamento. O acesso à plataforma continua disponível até o fim do período já contratado e pago. Quando esse período termina, não há nova cobrança recorrente e o acesso ao plano é encerrado. Em resumo: cancelar depois da janela de garantia interrompe as próximas cobranças, mas o aluno segue com acesso até o fim do ciclo que já pagou.

## Renovações

A partir da primeira renovação da assinatura, não se aplica o direito de arrependimento dos 7 dias. Ao cancelar nesse momento, o aluno mantém o acesso até o fim do ciclo vigente, sem direito a reembolso do valor desse ciclo. As cobranças seguintes deixam de ocorrer.

## Como o reembolso é feito

Quando há reembolso (cancelamento dentro dos 7 dias), o valor é devolvido pelo mesmo método de pagamento usado na contratação. O processamento pode levar até 30 dias úteis, sujeito aos prazos do meio de pagamento e da instituição financeira do aluno.

## Bizzu não garante aprovação

É importante deixar claro que a Bizzu não garante aprovação em concurso. As recomendações, o plano de estudos e as priorizações da IA são baseados em análise estatística de dados históricos de provas e não constituem garantia nem previsão sobre o conteúdo de provas futuras. O desempenho do aluno depende de fatores que estão fora do controle da plataforma. A "garantia de 7 dias" se refere apenas ao reembolso do pagamento, e não a qualquer resultado em prova.


================================================================
FONTE: docs\corpus_bizzu\conta-e-suporte.md
================================================================

---
title: Conta e suporte da Bizzu
source: bizzu
tags: [suporte, conta, atendimento, dados-cadastrais, contato, ajuda]
---

## Como falar com o suporte

A Bizzu tem uma central de atendimento por e-mail. Quando o aluno usa o canal de contato ou a opção de reportar um erro dentro da plataforma, a mensagem vira um atendimento (um ticket com número), e a equipe responde por e-mail. O atendimento funciona como uma conversa: as respostas trocadas por e-mail ficam registradas na mesma thread do ticket, então dá para acompanhar o histórico. O e-mail geral de contato da Bizzu é contato@bizzu.ai, e há uma central de ajuda em bizzu.ai/ajuda.

## Reportar um erro ou uma questão

Além do contato geral, a plataforma tem um caminho específico para reportar problemas, incluindo erros em questões. Esses relatos também viram atendimento (ticket) e ajudam a equipe a corrigir o conteúdo. Se o aluno achar que uma questão ou um gabarito está errado, esse é o canal indicado para avisar.

## Onde acessar a conta

O aluno acessa e gerencia a conta na plataforma, em plataforma.bizzu.ai, na área "Minha Conta". Lá ficam os dados cadastrais, a rotina de estudos, a troca de senha e a assinatura. Para entrar, o aluno faz login na própria plataforma.

## Alterar dados cadastrais e senha

Na área "Minha Conta", o aluno pode atualizar seus dados cadastrais (como nome, e-mail e telefone) e o CPF. A troca de senha também é feita por lá, em uma seção própria. Quem esqueceu a senha pode usar a recuperação de senha por e-mail.

## Gerenciar a assinatura

A assinatura é gerenciada na própria conta, dentro de "Minha Conta", na seção de assinatura. Lá o aluno consegue ver a assinatura, cancelar quando quiser e, quando disponível, trocar de plano. O cancelamento é autosserviço: o aluno mesmo faz, sem precisar acionar o suporte. Os detalhes de prazo, garantia e reembolso estão no tema "Cancelamento e garantia".

## Pesquisas de satisfação (NPS)

De tempos em tempos, a Bizzu pode pedir uma avaliação de satisfação dentro da plataforma (uma nota de 0 a 10, com espaço para um comentário). Essa pesquisa não aparece para todo mundo o tempo todo — ela é exibida em momentos elegíveis da jornada do aluno. Responder é opcional e ajuda a Bizzu a melhorar.

## Parar de receber e-mails e privacidade

O aluno pode se descadastrar dos e-mails de comunicação da Bizzu pelo link de cancelamento de inscrição presente nos próprios e-mails. Para assuntos de privacidade e dados pessoais (direitos da LGPD, como acesso, correção ou exclusão de dados), o canal indicado é o e-mail privacidade@bizzu.ai.

## Lacunas conhecidas

Os pontos abaixo não foram confirmados nas fontes e não devem ser afirmados ao aluno como fato:

- Horário de atendimento e prazo de resposta do suporte — não documentados.
- Existência de atendimento por telefone, chat ao vivo ou WhatsApp oficial da Bizzu — as fontes indicam atendimento por e-mail/ticket; não há canal de WhatsApp oficial documentado do lado da Bizzu. Não prometer canais que não estejam confirmados.
- URL exata de login/recuperação de senha além de plataforma.bizzu.ai — confirmar o caminho atual na plataforma.


================================================================
FONTE: docs\SESSAO_HANDOFF_2026-06-09.md
================================================================

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


