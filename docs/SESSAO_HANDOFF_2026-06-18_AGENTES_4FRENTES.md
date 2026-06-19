# Handoff — Onde Paramos (2026-06-18, continuação) — 4 frentes via agentes paralelos + commit 577a84e

> Continuação de `SESSAO_HANDOFF_2026-06-18_AUDITORIA_FIXES.md` (auditoria 8 agentes + 7 correções,
> base `d873709`, suíte em 484). Esta sessão **executou o backlog que aquela deixou aberto** em **4
> frentes paralelas** (arquivos disjuntos) + **review adversarial** (2 reviewers) + **verify** + **1º
> commit** (`577a84e`) + **Fase 0 pré-flight read-only no piloto**. Leia este primeiro para retomar.

---

## 1. TL;DR
- **4 frentes em paralelo (agentes, arquivos disjuntos):** **A** hardening multi-tenancy (org da inbound
  por sessão WAHA + IDOR fechado), **B** higiene de segredos (Postgres hardcoded fora; WAHA key/senhas
  redigidas; `docs/historico/` no gitignore), **C** retrieval PT (embedding multilíngue por env + RAG
  híbrido atrás de flag), **D** **Agente VoC (Fase 2)** — function-calling + 7 tools org-scoped + orchestrator,
  tudo atrás de flags **OFF**.
- **4 flags novas em `app/config.py`** (todas conservadoras): `embedding_model_name` (""), `rag_hybrid_enabled`
  (OFF), `voc_agent_enabled` (OFF), `voc_whatsapp_tool_enabled` (OFF).
- **Review adversarial (2 reviewers):** confirmou tools do VoC sem IDOR; achou **2 bugs** → **corrigidos**
  (webhook respondia pela sessão WAHA hardcoded; faltava `ESCAPE` no ILIKE do híbrido).
- **Verify consolidado VERDE: 555 passed** (era 484 → **+71**). **Commit `577a84e`** na `master` (86 arquivos,
  +21200/-592). **Working tree limpo.**
- **Fase 0 pré-flight no piloto (read-only, OK):** head `20260614c_feedback_assignee`, **0 duplicatas** em
  (org, channel_msg_id). As 2 migrations `20260618*` **commitadas** mas a **aplicação no piloto foi BLOQUEADA
  pelo classificador** → PENDENTE (precisa OK explícito).
- **Nenhum WhatsApp disparado. Repo ainda sem remote (sem `git push`).**

---

## 2. Estado da stack
| Serviço | Porta | Estado |
|---|---|---|
| API FastAPI (uvicorn, sem `--reload`) | 8000 | parada (subir via `/escuta-stack`) |
| Painel Next.js | 3001 | parado |
| WAHA / Podman | 3000 | **parado** (intencional — WhatsApp só com OK) |
| Supabase | cloud (piloto) | só leitura nesta sessão (Fase 0 pré-flight) |

- **Branch:** `master` · **último commit:** **`577a84e`** (esta sessão) · **working tree:** **limpo**.
- **Migrations head no piloto:** `20260614c_feedback_assignee` (as 2 de `20260618*` **ainda não aplicadas**).
- **Cadeia Alembic local:** linear, 1 head → `20260618b_roadmap_cross_links`
  (`20260614c_feedback_assignee` → `20260618_message_dedup_metadata` → `20260618b_roadmap_cross_links`).

---

## 3. O que foi feito nesta sessão (4 frentes)

### Frente A — Hardening multi-tenancy (`webhook.py`, `admin.py`, `tasks.py`, `boards.py`)
- **Org da inbound resolvida pela sessão WAHA:** `webhook.py::_resolve_org_for_inbound()` casa a sessão do
  envelope com `Organization.settings["waha_session"]`; **FALLBACK** para `default_org_slug` quando não há
  match (piloto single-org = idêntico ao de antes).
- **Resposta sai pela sessão da org resolvida:** `org_waha_session = (org.settings or {}).get("waha_session")
  or settings.waha_session` (era hardcoded — **bug pego no review, corrigido**).
- **IDOR fechado:** queries por id ganharam `organization_id` em `admin.py` / `tasks.py` / `boards.py`
  (ex.: `select(Contact).where(Contact.id == cid, Contact.organization_id == org.id)`;
  `select(CsTask).where(CsTask.id == tid, CsTask.organization_id == org.id)`).
- **Teste:** `tests/test_multitenancy_isolation.py` (2 orgs, prova isolamento).

### Frente B — Higiene de segredos (sem rotação real — só código/docs)
- **Postgres hardcoded REMOVIDO** de `scripts/sync_bizzu_contacts.py`: agora `_bizzu_database_url()` lê
  `BIZZU_DATABASE_URL` do ambiente e **SystemExit sem default** (zero senha no arquivo).
- **`.env.example`** passa a documentar `BIZZU_DATABASE_URL` (vazio).
- **WAHA key + senhas redigidas** em `docs/SESSAO_HANDOFF_2026-06-07.md` e `...08.md`
  (`‹redigido — ver ~/.secrets/...›`).
- **`docs/historico/`** adicionado ao `.gitignore` (transcripts fora do versionamento).

### Frente C — Retrieval PT (multilíngue + híbrido, ambos conservadores)
- **`app/services/embeddings.py`** lê `settings.embedding_model_name` (`_resolve_model_name()`): **vazio =
  `all-MiniLM-L6-v2` atual (zero regressão)**. Recomendado p/ PT:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (**também 384-dim → NÃO exige migration** da
  coluna `vector(384)`); exige o modelo no cache HF + **reindex** (re-gerar vetores).
- **`app/domain/knowledge/retriever.py`** ganhou **busca híbrida** (`_search_hybrid()`): semântica (pgvector)
  + lexical (`content ILIKE :like ESCAPE '\\'` — **ESCAPE foi o 2º bug do review, corrigido**) fundidas por
  **RRF** (`RRF_K = 60`). Atrás de `settings.rag_hybrid_enabled` (**OFF** = só semântica, idêntico ao atual).
- **Testes:** `tests/test_embeddings_model.py`, `tests/test_hybrid_retrieval.py`.

### Frente D — Agente VoC (Fase 2): infra completa, **dormente atrás de flags**
- **`app/services/llm.py`:** novo `chat_with_tools(messages, tools, *, tool_choice="auto", temperature, max_tokens)
  -> ChatToolResult` (function-calling Groq). **Never-raises** (retorna `ChatToolResult` neutro em falha/circuito
  aberto) e **reusa o circuit breaker** (`_DEFAULT_BREAKER` singleton da sessão anterior). `ChatToolResult` tem
  `message` / `tool_calls: list[ToolCall]` / `has_tool_calls`.
- **`app/domain/voc/registry.py`:** `VoCToolRegistry` (genérico) — `register` / `as_tools` (formato Groq) /
  `dispatch(ToolCall)`. **Dispatch never-raises:** tool desconhecida ou executor que falha vira
  `{"ok": false, "error": ...}` (string) que volta ao modelo.
- **`app/domain/voc/tools.py`:** as **7 tools, TODAS org-scoped** (lookups sempre com `organization_id == ctx.org_id`):
  `registrar_abordagem`, `aplicar_selo`, `criar_tarefa`, `vincular_melhoria`, `atualizar_feedback`,
  **`enviar_whatsapp`** (atrás de flag + 3 gates) e `ler_perfil_contato`. **Sem schema novo, sem migration.**
- **`app/domain/voc/orchestrator.py`:** `VoCAgentOrchestrator` — loop tool-calling com **teto de iterações**
  (`DEFAULT_MAX_ITERATIONS = 5`); todo o `run()` numa caixa try/except (**nunca derruba o webhook**).
- **Cabeamento em `resolver.py`** (`_run_voc_agent()`): só roda quando `settings.voc_agent_enabled` é True e há
  brain; se a flag está OFF **ou** o agente devolve None/falha, **cai no fluxo determinístico atual** (Survey
  Agent → máquina de estados). Fallback total.
- **Tool de WhatsApp blindada (`enviar_whatsapp`):** **GATE 0 = flag** `voc_whatsapp_tool_enabled` OFF → **NO-OP**
  (`sent:false, reason:tool_desligada`). Mesmo ON, **3 gates**: (1) opt-in, (2) cooldown (`notify_cooldown_hours`),
  (3) alcançável (`tem_whatsapp`). Grava o outbound em `messages` (igual ao `/improvements/{id}/notify`).
- **Testes:** `tests/test_voc_registry.py`, `tests/test_voc_tools.py`, `tests/test_voc_orchestrator.py`.

---

## 4. Flags novas (em `app/config.py`) — todas conservadoras
| Env | Default | Efeito |
|---|---|---|
| `EMBEDDING_MODEL_NAME` | `""` | vazio = `all-MiniLM-L6-v2` (zero regressão). Setar p/ multilíngue (384-dim, **sem migration**) + **reindex**. |
| `RAG_HYBRID_ENABLED` | `0` (OFF) | OFF = só semântica (idêntico). ON = semântica + lexical ILIKE fundidas por RRF. |
| `VOC_AGENT_ENABLED` | `0` (OFF) | OFF = fluxo atual **byte-a-byte**. ON = Agente VoC (function-calling) conduz o turno. |
| `VOC_WHATSAPP_TOOL_ENABLED` | `0` (OFF) | OFF = tool de WhatsApp é **NO-OP**. Mesmo ON, passa por 3 gates. |

---

## 5. Verify consolidado (rodado da raiz, estado estável)
- `py -m pytest -q` → **555 passed** (era 484 → **+71**).
- (Frontend não foi tocado nesta sessão; `tsc 0` seguia da sessão anterior.)
- **Commit:** `577a84e` na `master` (86 arquivos, +21200/-592) — engloba **o acúmulo de sessões anteriores +
  Fase 1/R4 + auditoria/fixes + estas 4 frentes**. Working tree **limpo** após o commit.

---

## 6. Onde paramos / próximos passos (dependem de você)
1. **Aplicar as 2 migrations `20260618*` no piloto** — **Fase 0 já provou que está limpo** (0 duplicatas em
   (org, channel_msg_id); `msg_metadata` ainda não existe). A aplicação foi **bloqueada pelo classificador** →
   precisa **OK explícito** (rodar `alembic upgrade head` com `DATABASE_URL` exportado — ver §8).
2. **Reindex multilíngue** — depende de: (a) **download do modelo OK** no cache HF (estava em andamento), (b)
   **OK de escrita no piloto** (reindex grava vetores), (c) setar `EMBEDDING_MODEL_NAME` + restart. Depois,
   **reavaliar o threshold `0.48` do clustering** (o limite do MiniLM inglês era o motivo do multilíngue).
3. **Setar `PANEL_API_KEY` e `WAHA_WEBHOOK_SECRET` em produção** — sem elas, a auth do painel/webhook é
   **fail-open** (libera + WARN). Herdado da sessão anterior; segue obrigatório.
4. **Rotação real de `WAHA_API_KEY` e senha Postgres** — esta sessão só fez **higiene de código/docs**; as
   credenciais ainda precisam ser **giradas de fato** (novas em `~/.secrets/`).
5. **`git push`** — **repo ainda sem remote**. Criar remote e empurrar `577a84e`.
6. **Validar a Fase 2 com Groq real** — `VOC_AGENT_ENABLED=1` em ambiente de teste (manter
   **`VOC_WHATSAPP_TOOL_ENABLED=0`**); depois ligar `RAG_HYBRID_ENABLED` após validar o retrieval.
7. **Backlog multi-tenancy remanescente (inócuo no piloto single-org):**
   - `webhook.py::_resolve_chat_phone` roda **antes** da resolução de org.
   - o webhook faz **full-scan de `Organization`** por inbound (sem índice na chave JSON `settings.waha_session`).

---

## 7. Pegadinhas / achados desta sessão
- **PEGADINHA-MÃE (migration no piloto):** `alembic/env.py` **NÃO carrega `.env`** → **exportar `DATABASE_URL`
  ANTES** de `alembic upgrade head`, senão cai em `localhost` (ConnRefused WinError 1225). É o que bloqueou a
  Fase 0 de virar aplicação real (isso + o gate do classificador).
- **2 bugs pegos no review adversarial (e corrigidos):** (1) o webhook **respondia pela sessão WAHA hardcoded**
  (`settings.waha_session`) em vez da sessão da org resolvida; (2) faltava **`ESCAPE '\'`** no ILIKE do híbrido
  (um `%`/`_` no texto da pergunta viraria curinga).
- **As travas de auth (#3/#4 da sessão anterior) seguem fail-open** sem as envs — não esquecer em produção.
- **Tudo da Fase 2 é DORMENTE:** com `VOC_AGENT_ENABLED=0`, `app/domain/voc/*` nem entra no caminho — o fluxo é
  byte-a-byte o atual. Mesma filosofia do `embedding_model_name=""` e `rag_hybrid_enabled=0`.
- (Confirmadas) pytest **sempre da raiz do escuta**; embedding multilíngue **não exige migration** por ser
  384-dim; trocar de modelo **exige reindex** (não basta a env); WhatsApp real só com OK.

---

## 8. Como religar a stack
Use a skill **`/escuta-stack`** (sobe API 8000 / painel 3001 / WAHA 3000 + Podman). Para aplicar migration no
piloto (com OK): exportar `DATABASE_URL` (do `.env`) **antes** de `alembic upgrade head`.

---

## 9. Refs rápidas (por caminho/env — sem valores de segredo)
- **Flags novas (defaults conservadores):** `EMBEDDING_MODEL_NAME` (""), `RAG_HYBRID_ENABLED` (0),
  `VOC_AGENT_ENABLED` (0), `VOC_WHATSAPP_TOOL_ENABLED` (0). Todas em `app/config.py`.
- **Flags da sessão anterior (produção):** `PANEL_API_KEY` (header `X-Panel-Key`), `WAHA_WEBHOOK_SECRET`
  (header `X-Webhook-Secret`) — **fail-open sem elas**; setar em prod.
- **Segredo a girar de fato:** `WAHA_API_KEY` + senha Postgres (`BIZZU_DATABASE_URL`); novas em `~/.secrets/`.
- **Módulos/arquivos novos:** `app/domain/voc/{__init__,registry,tools,orchestrator}.py`; `chat_with_tools` +
  `ChatToolResult`/`ToolCall` em `app/services/llm.py`; híbrido em `app/domain/knowledge/retriever.py`;
  modelo por env em `app/services/embeddings.py`; org da inbound em `app/api/webhook.py`.
- **Testes novos:** `test_multitenancy_isolation.py`, `test_embeddings_model.py`, `test_hybrid_retrieval.py`,
  `test_voc_registry.py`, `test_voc_tools.py`, `test_voc_orchestrator.py`.
- **Migrations escritas, não aplicadas no piloto:** `alembic/versions/20260618_message_dedup_metadata.py`
  (coluna `msg_metadata` JSONB + índice único parcial `uq_messages_org_channel_msg_id`),
  `20260618b_roadmap_cross_links.py` (garante `improvement_id` em `feedback_items`/`feedback_clusters`,
  idempotente).
- **Fonte da verdade:** `docs/BIZZU_ESCUTA_MASTER.md` (§7 = mapa de oportunidades) — **atualizado nesta sessão**
  com a camada do Agente VoC, o retrieval multilíngue/híbrido e as flags novas. Diários anteriores de hoje:
  `SESSAO_HANDOFF_2026-06-18.md`, `..._FASE1_R4_EXEC.md`, `..._AUDITORIA_FIXES.md`.
