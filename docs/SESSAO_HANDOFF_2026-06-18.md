# Handoff — Onde Paramos (2026-06-18) — Board-hub + Análise do Nexus + Plano de Adaptação

> Estado canônico ao fim da sessão. Duas frentes: (1) **board-hub** (board virou centro de comando) e
> (2) **descoberta + análise profunda da plataforma de agentes "Nexus/AISEC"** e o **plano de adaptar a
> inteligência dela para o Escuta**. Leia este primeiro para retomar.

---

## 1. TL;DR
- O **board** do Escuta virou um **centro de comando**: cards ricos (mostram tarefa/dor/melhoria/conversa/abordado),
  ações no card, board universal (feedback/cliente/**tarefa**/**melhoria**), esteira cruzada e filtros por segmento.
- Em paralelo, achamos no disco a **plataforma de agentes de IA** (pasta `AISECPlataformadeagentesdeIA-...`,
  apelidada "Nexus") — **mesma stack do Escuta** (FastAPI + SQLAlchemy + Supabase/pgvector + WAHA + Groq).
  Analisamos **o código** a fundo e montamos o **plano de portar a inteligência dela** pro Escuta.
- **Próximo passo combinado:** executar a **Fase 1** do plano de adaptação (baixo risco, sem WAHA/Groq ligados).
- **Nada de WhatsApp real disparado.** Migrations novas só aplicam no piloto **com OK explícito**.

---

## 2. O que foi feito/validado nesta sessão (board-hub)

Rodadas (cada uma com testes + revisão adversarial + validação ao vivo):
- **R1 (A+B) — cards ricos + ações.** Card de feedback expõe `tem_tarefa`, `tarefa_status`, `improvement_id`,
  `melhoria_titulo`, `dor_label`, `conversa_count`, `assignee`, `team_tag`, `abordado`. Card de cliente:
  `feedbacks_count`, `tarefas_abertas`, `conversa_count`. Ações: criar tarefa, vincular melhoria, atribuir.
- **R2 (C) — board universal.** Entidades novas `tarefa` e `melhoria` (campo `status`); **6 boards default**
  (+`default-tarefas` "Tarefas (CS)", +`default-roadmap` "Roadmap"). Drag muda status via PATCH `/tarefas` e
  `/improvements`. Validado ao vivo (Tarefas: Aberta 86/Em andamento 1; Roadmap: Ideia 3).
- **R3 (D) — esteira cruzada** (flag `ESTEIRA_ENABLED`, default ON): concluir tarefa → resolve o feedback
  vinculado; melhoria "entregue" → resolve os feedbacks vinculados; nudge "vincular melhoria" no board.
  Correções da revisão aplicadas (best-effort com `refresh` após rollback; transição real de status).
  **Suíte: 438 passed · tsc 0.**
- **R4 (E+F) — filtros + saneamento.** ⚠️ **Só o BACKEND landou** (filtros nos items do board por
  estado/plano/perfil/health/NPS/tem_whatsapp/team/assignee/owner/priority/effort + **exclusão de grupos**
  dos boards de cliente; 43 testes em `test_boards.py`). **Pendente:** o frontend (barra de filtros em
  `board/page.tsx`), o helper `boards.items(id, filtros)` em `lib/api.ts`, verify (pytest+tsc) e a revisão.
  (O limite de sessão cortou no meio; o backend é retrocompatível, nada quebrado.)

Contexto anterior já no ar (sessões passadas + início desta): correção do **tem_whatsapp real** (só celular BR
válido; 106 de 215), **filtros por tipo de cliente**, **chat na central** (`/chat`: lista+thread+envio gated,
gate "alcançável", "Só 1:1"), **thread no 360**, **API de integração** (`/api/integration/*`, gated por
`X-API-Key`, desligada sem env), **auto-tarefa** (`POST /api/tarefas/gerar-de-feedbacks`).

---

## 3. A grande frente: análise do Nexus + plano de adaptação

### 3.1 O que é o Nexus (plataforma de agentes de IA)
- Caminho: `C:\Users\jboni\Documents\Projetos\AISECPlataformadeagentesdeIA-claude-kind-bell\AISECPlataformadeagentesdeIA-claude-kind-bell`
- Git: remoto `github.com/Jairfilhobonifacio/AISECPlataformadeagentesdeIA`. **HEAD do remoto = `origin/dev`** (canônica).
  A cópia local está na branch **`feature/wave-bc-completa`**. **As docs (`docs_legado/`) estão ATRASADAS — ler o CÓDIGO.**
- Modelo de conversa robusto (em `app/services/database.py`): `contacts`, `messages` (com **dedup `uq_messages_waha_dedup`**
  por `waha_message_id`), `conversation_context` (memória durável 1:1), `conversation_session` (multi-turn),
  `message_feedback`, `knowledge_base` (pgvector). `msg_metadata` JSONB = **trace explicável** por mensagem.
- Inteligência: `AgentOrchestrator` (funil de ~10 passos: contexto→handoff→dedup→flows→determinístico→behaviors→
  RAG→sentimento→tools→LLM→avanço de funil→memória), `BehaviorEngine`, `ToolRegistry`+`Skills` (function-calling),
  `LLMService` (Groq→Ollama→Gemini + circuit breaker), `KnowledgeRetriever` (RAG híbrido + fallback honesto),
  `LeadMemoryService` (extrai fatos por LLM), funil de lead LEAD→QUALIFICADO→CONVERTIDO + `nexus_score` (stub).

### 3.2 Correções importantes de entendimento (eu errei e corrigi)
- **Extração de grupo NÃO é uma API** no projeto. A entrada real de contatos é: **import de CSV**
  (`app/api/leads.py` → `POST /leads/import-csv`) + **webhook do WAHA** (tempo real). A extensão Chrome
  (`whatsapp-extractor-v2`, DOM scraping) só **gera CSV**. O `fetchAllGroups` da Evolution API está **só em
  docs atrasadas**, não no código. → No Escuta a entrada será **CSV import + webhook WAHA + sync do parceiro Bizzu**.
- **O Escuta TEM Alembic** (15 migrations encadeadas; head atual `20260614c_feedback_assignee`). A ideia de
  "sem Alembic" era falsa — mudanças de schema entram por migration normal.

### 3.3 O plano de adaptação (decisões por componente)
Princípio: **o Escuta já tem o miolo** — o `SurveyContextResolver` (`app/domain/survey/resolver.py`) já é o
"orquestrador" (dedup, gate handoff, LLM best-effort, RAG). Então **reforçar o que existe + adicionar ações**, e
**descartar o peso de vendas/multi-tenant** (BehaviorEngine, PromptBuilder genérico, funil de lead, `nexus_score`,
FlowExecutor, multi-turn, A/B — tudo over-engineering p/ Voz do Cliente).

| Componente | Decisão | Esforço | Fase |
|---|---|---|---|
| Funil de decisão (preencher caminho "sem pesquisa pendente" no `webhook.py`) | inspirar | Baixo | 1 |
| Circuit breaker no Groq (`services/llm.py` já tem fallback de modelo) | portar | Baixo | 1 |
| RAG fallback honesto explícito (`NO_KB_FALLBACK`) | reforçar | Baixo | 1 |
| Dedup atômico (`uq_messages_org_channel_msg_id`) + coluna `messages.msg_metadata` JSONB | portar (Alembic) | Médio | 1 |
| `improvement_id` faltando nas migrations (`feedback_items`/`feedback_clusters`) | portar (Alembic) | Baixo | 1/2 |
| **Tools / function-calling** (registrar abordagem, aplicar selo, criar tarefa, vincular melhoria, atualizar feedback, enviar WhatsApp, ler perfil) + `chat_with_tools()` no GroqLLM + `VoCAgentOrchestrator` | portar infra + inspirar tools | Médio | 2 |
| RAG busca híbrida (semântica + ILIKE) | inspirar | Médio | 2 |
| **Memória durável** em `Contact.profile_data["memory"]` (MemoryService Groq) → alimenta `compute_health()` | inspirar | Médio | 3 |
| BehaviorEngine, PromptBuilder genérico, funil de lead, nexus_score, FlowExecutor, multi-turn, A/B | **descartar** | Zero | — |

**Ordem:** Fase 1 (circuit breaker → fallback honesto → message_handler → dedup/`msg_metadata`) → Fase 2 (tools +
function-calling + VoC agent + busca híbrida) → Fase 3 (memória durável → health, só com Survey Agent em produção).

**Pré-flight (Fase 0):** rodar SQL read-only no piloto (`SELECT version_num FROM alembic_version`; tabelas;
duplicatas em `messages` por `org+channel_msg_id`) antes de qualquer migration.

---

## 4. Próximo passo (combinado)
**Executar a Fase 1** (baixo risco; não depende de WAHA/Groq ligados):
1. `app/services/circuit_breaker.py` (threshold=3, recovery=30s) + envolver `_call`/`_call_text` no `GroqLLM`.
2. `NO_KB_FALLBACK` em `app/domain/survey/brain.py`.
3. `app/domain/survey/message_handler.py` (funil p/ mensagem sem pesquisa pendente) + ligar no `webhook.py` (TODO).
4. Migration `20260618_message_dedup_metadata` (índice único parcial + coluna `msg_metadata`) + `MessageMetadata`
   em `app/schemas/messages.py` + insert atômico (`try/except IntegrityError`) no webhook.
5. Migration `20260618_roadmap_cross_links` (colunas `improvement_id` que faltam).
Testes: `test_message_dedup.py` + regressão `test_webhook_capture.py`. **Aplicar migrations no piloto = OK do usuário.**

Também pendente: **fechar a R4** (barra de filtros no board — só o frontend).

---

## 5. Constraints / gotchas (reler antes de codar)
- **WhatsApp real só com OK** (WAHA viola ToS). Migrations no piloto Supabase **só com OK explícito**.
- `messages.channel_msg_id` é **nullable e SEM unique** hoje → a Fase 1 adiciona o índice único parcial.
- Padrão **copia-edita-reatribui** obrigatório em JSONB (`profile_data`/`settings`).
- Emoji em `.ts/.tsx` **só com `\u{...}`** (bundler do Next no Windows corrompe literal).
- pytest **sempre da raiz do escuta** (rodar da pasta-mãe pega projetos vizinhos e quebra a coleta).
- Subir API: `set -a && source .env && set +a && cd <escuta> && py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning` (com `cd`!).

---

## 6. Estado da stack
- **API** FastAPI `:8000` (uvicorn, sem `--reload`) · **painel** Next `:3001` · Supabase cloud · WAHA/Podman `:3000` (parado).
- Telas: `/` · `/feedbacks` · `/chat` · `/board` (6 boards) · `/temas` · `/melhorias` · `/campanha` · `/clientes` ·
  `/pesquisas` · `/contatos` · `/tarefas` · `/playbooks` · `/integracao`.
- Migrations head no piloto: `20260614c_feedback_assignee` (confirmar na Fase 0).

---

## 7. Workflows desta sessão (para auditoria/resume)
Análises read-only (resultados nos `tasks/*.output` da sessão): mapa do banco do Escuta + fusão WAHA; análise
completa do Nexus; plano de port P1; **blueprint de adaptação da inteligência** (o mais completo —
explicação do orquestrador real com `arquivo:linha` + decisões reusar/portar/inspirar/descartar).
