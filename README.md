# Escuta — Voz do Cliente no WhatsApp

> *Um Typeform que conversa no WhatsApp e te entrega o insight já mastigado.*

Plataforma SaaS multi-tenant de **Feedback Intelligence**: dispara pesquisas (NPS/CSAT) por WhatsApp, um agente de IA conduz a conversa, e os temas voltam **agrupados** — sem o dono ler 300 mensagens. Feedback negativo vira ticket; histórias positivas viram prova social.

**NÃO é** central de atendimento (não competimos com Zendesk/Take Blip de frente). O coração é **escutar + analisar**.

- **Status:** 2026-06-05 — scaffold + PRD da Fase 0 (tracer bullet NPS). Sem código de produto ainda além do parser de NPS.
- **Codinome:** Escuta (mira PME-BR) / Echo (global).
- **Cliente-piloto:** **Bizzu** (`bizzu.ai`).

---

## 🎯 Cliente-piloto: Bizzu (edtech de concursos)

[bizzu.ai](https://bizzu.ai/) é uma plataforma de **planejamento de estudos para concursos públicos com IA** (Raio X da Prova, plano de estudos automático, +600k questões, "Bizzu do Tópico", revisões inteligentes). **Web-only, R$20/mês ou R$120/ano, sem WhatsApp/comunidade hoje.** É o "infoprodutor" do beachhead.

Por que é um piloto quase perfeito: SaaS por assinatura (churn = vida ou morte) · sem WhatsApp hoje (valor 100% novo) · concurseiro é usuário emocional/movido a meta (feedback rico) · já valoriza prova social (aprovados).

**Momentos de feedback no ciclo do concurseiro:**

| Gatilho no Bizzu | Pesquisa | Por que importa |
|---|---|---|
| Gerou o 1º plano (Raio X) | CSAT de ativação | Aha moment → ativação |
| Concluiu um tópico/revisão | Qualidade do resumo/questão · "erro no comentário?" → **ticket** | "Dupla conferência de gabarito" é zona de risco |
| Mensal (assinante ativo) | **NPS** | Termômetro de retenção |
| **Cancelou** (7 dias / sem fidelidade) | **Exit survey** | 🥇 ouro p/ churn de edtech |
| "Passou no concurso?" | Captura de **aprovado** + NPS promoter | Vira depoimento/review/indicação |

---

## 🧬 Arquitetura: projeto novo, alimentado por 3 doadores

Este repositório é **novo e independente**. Reusa código de 3 projetos existentes (copiando + limpando o domínio que não serve), **não** é construído dentro de nenhum deles.

| Doador | O que vem dele |
|---|---|
| **AIESEC Nexus AI** (núcleo) | Agente+RAG (`orchestrator`, `rag/`), disparo (`campaign_worker`), canal WhatsApp (`waha.py` + interface `IMessagingService`), multi-tenant (`organization_id`) + auth JWT, LGPD, circuit breaker, esqueleto Alembic |
| **AIESEC Pulse** | Feature flags por tenant + white-label, transcrição de áudio (AssemblyAI), email dispatcher |
| **Incentivo BH** | Motor de regras versionado, multi-cron, conector Podio (se necessário) |
| **🆕 Domínio novo** | `Survey` + `SurveyContextResolver`, `Ticket`, `feedback_items`/clustering, digest |

**Stack** (mantida igual à do Nexus, pra o copy-paste rodar): FastAPI + SQLAlchemy 2.0 async + Alembic (deploy Modal) · Next.js 14 + Tailwind (Vercel) · Supabase Postgres + pgvector · Upstash Redis · LLM Groq · WhatsApp via WAHA.

---

## 📁 Estrutura

```
escuta/
├─ README.md                 ← este arquivo
├─ docs/
│  └─ PRD_FASE0.md           ← PRD do tracer bullet (LEIA ISTO)
├─ app/                      (backend — espelha o Nexus)
│  ├─ api/                   webhook + endpoints
│  ├─ auth/                  deps multi-tenant (copiar do Nexus)
│  ├─ services/
│  │  └─ agent/              orchestrator (copiar na Fase 1)
│  ├─ workers/               campaign_worker (copiar)
│  ├─ rag/                   retriever + embeddings (Fase 2: clustering)
│  ├─ domain/
│  │  ├─ interfaces/         IMessagingService (copiar)
│  │  └─ survey/             🆕 dispatcher, resolver, parsers
│  └─ models/                Survey/SurveyRun/SurveyResponse + copiados
├─ alembic/versions/         migrations
└─ frontend/                 Next.js (Fase 1+)
```

---

## 🗺️ Roadmap

- **Fase 0 — Tracer bullet (~1 sem):** 1 NPS ponta-a-ponta pro Bizzu sobre WAHA. Prova que a interceptação inbound funciona. → `docs/PRD_FASE0.md`
- **Fase 1 — MVP (~3-4 sem):** todos os tipos de pergunta + UI de construção + painel de resultados; Tickets; inbox em tempo real (Supabase Realtime); `feedback_items` + sentimento.
- **Fase 2 — Inteligência e escala (~3-4 sem):** clustering + dashboard de temas + insight push; migração de disparo WAHA → Cloud API via BSP; SLA/fila.

**Decisões que só travam a Fase 1** (não a 0): WAHA × Cloud API · número chip × oficial · pricing repassado · dono do opt-in · autopilot × copilot.

---

## ▶️ Próximos passos

1. Implementar a Fase 0 conforme `docs/PRD_FASE0.md` (copiar núcleo do Nexus + criar as 3 tabelas + resolver + parser).
2. Alinhar com o Bizzu a integração mínima: **opt-in de WhatsApp no signup** + **webhook de eventos de ciclo de vida**.
3. Escolher o nome definitivo (Escuta vs Echo).
