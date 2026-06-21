# MAPA ÚNICO — Sistema de Feedback + Acompanhamento (Escuta / Bizzu)

> Síntese de 8 mapas de área. Data: 2026-06-20.
> Escuta = central de Voz do Cliente no WhatsApp (FastAPI + Groq + Supabase pgvector + painel Next.js), integrada à Bizzu via webhook HMAC.
> PROD: API em Modal (`…escuta-api-fastapi-app.modal.run`) + painel Vercel (`escuta-feedback.vercel.app`) + Supabase cloud. WAHA fora do deploy.
> Números reais do piloto: NPS **8,9** · **5 detratores** · **~174 contatos**.

---

## 1. PIPELINE PONTA-A-PONTA

O feedback nasce em 4 fontes, converge em 2 destinos de dados (`SurveyResponse` e `FeedbackItem`), é entendido por IA, gerido por workflow, priorizado por dor e tem o loop fechado de volta ao cliente.

```
                            ┌──────────────────── FONTES (como o feedback NASCE) ────────────────────┐
                            │                                                                         │
  [Backend Bizzu]   subscription_cancelled / topic_completed / ticket / report / edital              │
      │  HMAC-SHA256 (X-Escuta-Signature)                                                             │
      ▼                                                                                               │
  POST /api/events/bizzu ──┐                                                                          │
                           │     [WhatsApp inbound] ──► POST /api/webhook/waha (X-Webhook-Secret)     │
                           │            │ dedup channel_msg_id                                        │
                           │            ▼                                                             │
                           │     resolve org (waha_session) + get-or-create Contact + grava Message   │
   [Forms CSV] ────────────┤            │                                                             │
   POST /forms/import      │     ┌───────┴────────┐                                                   │
                           │     │ survey pendente?│                                                  │
   [Sync Partner API] ─────┤     ▼ sim            ▼ não                                               │
   sync_partner_customers  │  SurveyContextResolver   InboundMessageHandler                           │
   (NPS in-app + churn)    │  (interpreta nota/motivo) (ingere churn/outro)                           │
                           │     │                      │                                            │
        ═══════ CAPTURA ═══╪═════╪══════════════════════╪════════════════════════════════════════════╪═
                           │     ▼                      ▼                                            │
                           └─► ingest_feedback_item (DEDUP por external_id) ◄────────────────────────┘
                                        │
        ═══════ ORGANIZAÇÃO / ENTENDER ═╪══════════════════════════════════════════════════════════════
                                        ▼
                       SurveyBrain (Groq LLM) → sentiment / themes / urgency   [best-effort, nunca bloqueia]
                                        │
                       reindex (MiniLM-L12-v2 multilíngue 384d) → embedding pgvector
                                        │
                       ClusteringEngine (cosseno ≥0.48, por sentimento) → FeedbackCluster (label LLM)
                                        │
        ═══════ ACOMPANHAMENTO ═════════╪══════════════════════════════════════════════════════════════
                                        ▼
            FeedbackItem.action_status:  a_abordar → aguardando_retorno → em_acompanhamento → resolvido
                                                                            └► sem_retorno / descartado (terminais)
            flag abordado + abordado_em · selos (manual/vivo/log) · CsTask (SLA/owner) · Board Kanban
            Ficha 360 (GET /contacts/{id}/360): timeline + selos_vivos + partner snapshot + health_band
                                        │
        ═══════ PRIORIZAÇÃO ════════════╪══════════════════════════════════════════════════════════════
                                        ▼
            urgência feedback-level (neg+churn+detrator+anual+não_abordado+recência, 0-100)
            priority_index cluster-level (volume×receita×gravidade, pesos 0.50/0.30/0.20) → banda
            Tela /temas (Mapa de dores + Por tema) → "Virar melhoria"
                                        │
        ═══════ FECHAR O LOOP ══════════╪══════════════════════════════════════════════════════════════
                                        ▼
            Improvement (roadmap: ideia→planejada→em_andamento→entregue→descartada)
            from-cluster (idempotente, bulk-vincula FeedbackItem.improvement_id)
            AO ENTREGAR: bulk action_status=resolvido nos vinculados
            POST /improvements/{id}/notify (preview → confirm=true) → WhatsApp "você pediu, a gente fez"
            cooldown 20h + opt-in + WhatsApp válido · carimba notified_at
                                        │
                                        ▼
                       Digest semanal narrado (NPS, temas top, urgências) → owner
```

**Resumo das 5 etapas:**
1. **Captura** — 4 fontes (WhatsApp inbound, Events Bizzu HMAC, Forms CSV, Sync Partner API) convergem em `ingest_feedback_item`, deduplicado por `external_id`. Surveys WhatsApp passam por cooldown 7d + opt-in.
2. **Organização/Entender** — classificação IA (sentimento/tema/urgência), embedding MiniLM, clustering semântico por dor.
3. **Acompanhamento** — workflow `action_status` (6 estados), flag `abordado`, selos, tarefas (CsTask), boards Kanban, ficha 360.
4. **Priorização** — urgência por feedback + `priority_index` por dor (volume×receita×gravidade) → tela de Mapeamento.
5. **Fechar o loop** — dor → melhoria (roadmap) → entrega → aviso WhatsApp personalizado + digest semanal.

---

## 2. MODELO DE DADOS (entidades + relações)

```
Organization (1)───< Contact (N)
   │ settings: action_statuses, feedback_types,        │ phone (UNIQUE/org), opt_in, needs_human_handoff
   │           feedback_origins, selos_catalogo,        │ profile_data{ selos[], selos_log[], abordagens[],
   │           boards[], waha_session                   │               partner snapshot(nps/sub/health_band) }
   │                                                    │
   ├──< Survey (N) ───< SurveyRun (N) ───< SurveyResponse (N)
   │     type(nps/exit)   trigger_event       score, nps_bucket, answer_text
   │     questions[]      UNIQUE(run,contact)  status(sent/awaiting_reason/closed/expired/ingested)
   │     trigger_event                         sentiment, themes, ai_meta(urgency)  ◄── IA
   │     ingest_mode                           source(whatsapp/in_app)
   │                                              │
   │                                           Message (N) ── direction, body, channel_msg_id(WAHA),
   │                                              transcript append-only, dedup (org,channel_msg_id)
   │
   ├──< FeedbackItem (N)  ★ MEGA CENTRAL  ────────────────────────────┐
   │     source(bizzu_app/bizzu_billing/whatsapp/forms/in_app)        │
   │     type(nps/churn/csat/ticket/report/edital_request)            │
   │     score, nps_bucket, text, external_id(DEDUP)                  │
   │     sentiment, themes, ai_meta(urgency)  ◄── IA                  │
   │     embedding vector(384)  ◄── pgvector (SQL cru, HNSW)          │
   │     action_status, abordado, abordado_em, assignee, team_tag     │
   │     ├─ FK contact_id ───────────────────────────────────────────┘
   │     ├─ FK improvement_id (SET NULL)  ──► Improvement
   │     └─ FK cluster_id  ──────────────►  FeedbackCluster
   │
   ├──< FeedbackCluster (N) ── label, description, dominant_sentiment, item_count(cache)
   │     centroid vector(384) [PG-only]   FK improvement_id (SET NULL)
   │
   ├──< Improvement (N) ── title, status(ideia/planejada/em_andamento/entregue/descartada)
   │     effort(P/M/G/XG), target_date, delivered_at, notified_at   FK cluster_id (SET NULL)
   │
   ├──< CsTask (N) ── title, status(aberta/em_andamento/concluida/adiada), priority, owner,
   │     due_at, snoozed_until, dedup_key(UNIQUE)   FK contact_id, feedback_item_id, playbook_id
   │
   └──< Playbook (N) ── trigger(nps_detractor/health_at_risk/inactive_days/renewal_soon/churn_detected)
         actions(create_task/alert_owner)  [flag PLAYBOOKS_INLINE OFF]
```

**Relações-chave:**
- `Contact` é a cola (1 por telefone/org); agrega survey, feedback, tarefas, abordagens, selos.
- `FeedbackItem` é a mega central — unifica QUALQUER sinal; dedup por `external_id`.
- `FeedbackItem (N) → Improvement (1)`: liga dor resolvida à melhoria (fechar o loop). **Limitação: máx. 1 melhoria por item.**
- `FeedbackCluster ↔ Improvement`: bidirecional (dor vira melhoria, idempotente).
- **Dois eixos confundidos hoje**: `action_status` (micro: ação/acompanhamento) vs `health_band` (macro: lifecycle do relacionamento).

---

## 3. ONDE A IA ATUA

| Camada | Componente | Modelo | Estado | Best-effort |
|---|---|---|---|---|
| Interpretação resposta NL ("uns oito"→8) | SurveyBrain.interpret_reply | Groq llama-3.3-70b | ✅ ON | sim (cai no parser determinístico) |
| Classificação (sentimento/tema/urgência) | SurveyBrain.classify_feedback | Groq | ✅ ON | sim (NULL se falhar) |
| Embedding semântico | EmbeddingService (MiniLM-L12-v2 multilíngue 384d) | offline | ✅ ON (reindex) | n/a |
| Clustering de dores | ClusteringEngine (cosseno ≥0.48) | local + Groq p/ rótulo | ✅ ON (dry_run default) | rótulo best-effort |
| Rótulo de cluster | _label_cluster (top-5 textos) | Groq | ✅ ON | sim |
| Digest semanal narrado | DigestService.narrate_digest | Groq | ✅ ON | fallback determinístico |
| Sugerir selos de negócio | /contacts/{id}/sugerir-selos | Groq | ✅ ON | sim |
| Mensagem "você pediu, a gente fez" | _notify_message (tema da dor) | template + tema IA | ✅ ON | n/a |
| RAG (corpus Bizzu, groundedness honesta) | KnowledgeBase + answer_from_context | pgvector + Groq | ⚠️ semântico ON; **híbrido OFF** | NO_KB_FALLBACK ON |
| Detecção handoff humano | SurveyBrain (intent) | Groq | ✅ ON | sim |
| Agente VoC (7 tools function-calling) | VoCAgentOrchestrator | Groq chat_with_tools | 🔴 OFF (VOC_AGENT) | — |
| Survey full-agentivo | SURVEY_AGENT | Groq | 🔴 OFF | — |
| Playbooks/automação | engine.run_playbooks | regras | 🔴 OFF (PLAYBOOKS_INLINE) | — |

**Padrão de ouro do sistema:** toda IA é best-effort — falha de LLM/Groq nunca bloqueia o fluxo. Fallback: principal (70b) → reserva (8b instant), circuit breaker 3 falhas→30s.

---

## 4. NO AR vs FALTA

### NO AR (PROD — Modal + Vercel + Supabase cloud)
- **Captura**: webhook Bizzu HMAC, webhook WAHA inbound, Forms import, Sync Partner. Dedup por `external_id`/`event_id`/`channel_msg_id`.
- **Entender**: classificação IA (sentimento/tema/urgência), embedding multilíngue, clustering em dry_run, tela /temas (2 abas).
- **Acompanhar**: 6 `action_status` + flag `abordado` editáveis (PATCH); selos (manual/vivo/log); 7 boards default + custom (CRUD sem migration); ficha 360; CsTask CRUD; Config (vocabulários customizáveis).
- **Priorizar**: urgência feedback-level + `priority_index` cluster-level com breakdown exposto.
- **Fechar loop**: roadmap Improvement; from-cluster idempotente; AUTO-resolve ao entregar; notify preview→confirm com cooldown 20h + opt-in.
- **Infra**: BFF proxy Vercel injeta PANEL_API_KEY; banco Supabase cloud; digest semanal.

### FALTA / NÃO-CONSTRUÍDO
- **WAHA fora do deploy** (stateful) → Chat/Conexão/envio inativos em PROD.
- **Bugs P0 de UI (styled-jsx)**: ficha 360, selos popover, Pesquisas, Clientes quebrados em prod.
- **Migrations `20260618*` commitadas mas NÃO aplicadas no Supabase prod.**
- **Flags Fase 2 desligadas**: VOC_AGENT, SURVEY_AGENT, PLAYBOOKS_INLINE, CLUSTERING_INLINE, RAG_HYBRID — código pronto, sem benchmark.
- **Double-touch churn**: e-mail winback Bizzu + WhatsApp Escuta no mesmo cancelamento (sem dedup cruzado).
- **Auto-reabrir / follow_up_at**: agendar reabordagem + reabrir por inbound — não existe.
- **Customização de status/tipos/boards na UI**: backend pronto, front parcial.
- **Sem auditoria/telemetria**: nenhum log de quem-fez-o-quê; sem SLO Groq; classificação falha em silêncio.
- **Edição manual da mensagem do loop**; export CSV/PDF; busca semântica HNSW (índice existe, nunca consultado); reclassificação em batch via UI.

---

## 5. GAPS / OPORTUNIDADES PRIORIZADOS (impacto × esforço)

| # | Gap / Oportunidade | Impacto | Esforço |
|---|---|---|---|
| 1 | **Double-touch churn** — dedup cruzado e-mail Bizzu × WhatsApp Escuta (flag `skip_escuta`/`event_id`) | Alto (UX cliente + risco churn) | Baixo |
| 2 | **WAHA em produção** (Fly.io/VPS + secrets) — destrava Chat/Conexão/envio reais | Alto (loop só fecha com WhatsApp) | Médio |
| 3 | **Corrigir styled-jsx P0** (ficha 360, selos, Pesquisas, Clientes) → Tailwind/CSS modules | Alto (UI quebrada em prod) | Médio |
| 4 | **Aplicar migrations `20260618*` no prod** (schema desatualizado) | Alto (drift/erros latentes) | Baixo |
| 5 | **Usar urgência/priority no Board** (sort/filtro) — IA já calcula, board ignora | Alto (priorização real do PM) | Baixo |
| 6 | **Auto-reabrir + follow_up_at** (snooze tipo Intercom + reabrir por inbound) | Alto (não perder follow-up) | Médio |
| 7 | **Telemetria/auditoria** (log estruturado + SLO Groq + alerta classificação falha) | Médio (compliance/debug) | Médio |
| 8 | **Separar eixo macro (health/lifecycle) × micro (action_status)** no modelo+UI | Médio (clareza de gestão) | Médio |
| 9 | Ligar RAG híbrido (lexical RRF) p/ recall PT + ligar CLUSTERING_INLINE | Médio | Baixo |
| 10 | Métrica taxa de resolução (% resolvido/terminais) no dashboard/digest | Médio | Baixo |
| 11 | Rate-limit global de notify (evitar flood "você pediu") + auditoria de envio | Médio | Baixo |
| 12 | Customização de status/tipos/boards na UI (backend pronto) | Médio | Médio |

---
*Síntese gerada a partir de 8 mapas de área (captura, acompanhamento, entendimento, workflow, priorização, frontend, VoC, integrações/deploy).*
