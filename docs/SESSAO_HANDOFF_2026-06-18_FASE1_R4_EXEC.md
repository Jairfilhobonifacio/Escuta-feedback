# Handoff — Onde Paramos (2026-06-18, tarde) — Execução da Fase 1 (IA) + R4 (filtros do board)

> Continuação de `SESSAO_HANDOFF_2026-06-18.md` (board-hub + análise do Nexus + plano de adaptação).
> Esta sessão **executou** o que aquele handoff deixou combinado: a **Fase 1** do plano de port da
> inteligência do Nexus + o **fechamento da R4** (frontend dos filtros do board). Tudo via 3 agentes
> paralelos em frentes de arquivos disjuntos. Leia o handoff anterior para o "porquê"; este é o "o quê foi feito".

---

## 1. TL;DR
- **3 agentes paralelos** entregaram 3 frentes sem colisão (arquivos disjuntos):
  - **A — R4 frontend:** barra de filtros do board + helper `boards.items(id, filtro)`. Board-hub **100% fechado**.
  - **B — Resiliência de LLM (Fase 1):** `circuit_breaker.py` no `GroqLLM` + RAG fallback honesto (`NO_KB_FALLBACK`).
  - **C — webhook/dedup + migrations (Fase 1):** `message_handler` + insert atômico/idempotente + 2 migrations **escritas (não aplicadas)**.
- **Verify consolidado VERDE:** suíte **466 passed** (era 438 → **+28**) · **tsc 0** no frontend.
- **Nada aplicado no piloto. Nenhum WhatsApp/WAHA disparado. Nada commitado** (tudo uncommitted p/ revisão).
- **Achado:** as colunas `improvement_id` que o plano mandava criar **já existiam** → a 2ª migration virou no-op defensiva.

---

## 2. Estado da stack
| Serviço | Porta | Estado |
|---|---|---|
| API FastAPI (uvicorn, sem `--reload`) | 8000 | parada (subir via `/escuta-stack`) |
| Painel Next.js | 3001 | parado |
| WAHA / Podman | 3000 | **parado** (intencional — WhatsApp só com OK) |
| Supabase | cloud (piloto) | intocado nesta sessão |

- **Branch:** `master` · **último commit:** `d873709` (board-hub camadas 2/3, de 14/06).
- **Working tree:** ~59 arquivos uncommitted (acúmulo de sessões anteriores + os desta).
- **Migrations head no piloto:** `20260614c_feedback_assignee` (as 2 novas **ainda não aplicadas**).
- **Cadeia Alembic local:** 1 só head → `20260618b_roadmap_cross_links`.

---

## 3. O que foi construído nesta sessão

### Frente A — R4: filtros do board (frontend)
- `frontend/app/board/page.tsx` — barra de filtros **contextual** (só exibe os campos aplicáveis à entidade
  do board: feedback/cliente/tarefa/melhoria) + reset ao trocar de board + "Limpar filtros".
- `frontend/lib/api.ts` — interface `BoardItemFiltro` + helper `boards.items(id, filtro?)` serializando via `buildQuery`.
- Endpoint real: `GET /api/boards/{id}/items` com query params opcionais: `estado`, `plan_type`, `perfil`,
  `tem_whatsapp` (`sim|nao`), `nps_bucket` (`promotor|neutro|detrator`), `team_tag`, `assignee`, `abordado` (bool),
  `health_band` (`healthy|watch|at_risk`), `owner`, `priority`, `effort`. Filtro aplicado **antes** do agrupamento
  → `items` e `count` de cada coluna refletem o filtro.

### Frente B — Resiliência de LLM (Fase 1)
- `app/services/circuit_breaker.py` **(novo)** — `CircuitBreaker` (closed/open/half-open, `failure_threshold=3`,
  `recovery_timeout=30s`, fecha após 1 sucesso em half-open), `CircuitOpenError`, **relógio injetável** (default
  `time.monotonic`), usável como `call`/`call_async`/decorator.
- `app/services/llm.py` — `GroqLLM` ganhou o breaker (compartilhado entre modelo principal e reserva,
  `expected_exception=_UpstreamError`). `_post` extraído levanta `_UpstreamError` só em **falha real** (rede/timeout/
  408/425/429/5xx); **4xx de cliente NÃO abre o circuito**. Com circuito aberto, `_call`/`_call_text` devolvem
  `None`/`""` sem tocar a rede (contrato never-raises preservado). **Fallback de modelo existente preservado.**
- `app/domain/survey/brain.py` — novo `answer_question_grounded` com caminho `NO_KB_FALLBACK` explícito:
  KB vazio OU melhor score < `BRAIN_MIN_RELEVANT_SCORE` (0.30) → resposta **honesta** sem gastar LLM; também honesto
  quando o LLM julga não-respondível. `answer_from_context` mantém o contrato `None` antigo (resolver/message_handler
  não afetados).
- `app/config.py` — flag `no_kb_fallback_enabled` (`NO_KB_FALLBACK_ENABLED`, default **ligado**).
- Testes: `tests/test_circuit_breaker.py` (13) + `tests/test_rag_honest_fallback.py` (7).

### Frente C — webhook/dedup + migrations (Fase 1) — escritas, **NÃO aplicadas**
- `app/domain/survey/message_handler.py` **(novo)** — `InboundMessageHandler`: funil da inbound **sem pesquisa
  pendente** (captura na Mega Central, best-effort/gated, **não dispara WhatsApp**). Consolida lógica que estava
  inline no webhook, no espírito do `SurveyContextResolver`.
- `app/schemas/messages.py` **(novo, primeira coisa em `app/schemas/`)** — `MessageMetadata` (Pydantic,
  `extra="allow"`, helper `to_jsonb()`).
- `app/models/survey.py` — coluna `msg_metadata` (JSON nullable) + índice único **PARCIAL**
  `uq_messages_org_channel_msg_id (organization_id, channel_msg_id) WHERE channel_msg_id IS NOT NULL` no `Message`.
- `app/api/webhook.py` — insert da inbound agora **atômico/idempotente** (`session.begin_nested()` +
  `try/except IntegrityError` → rollback do savepoint → resposta 200 'duplicate'); grava `msg_metadata` via
  copia-edita-reatribui; ramo "sem pesquisa" delega ao `InboundMessageHandler`.
- `alembic/versions/20260618_message_dedup_metadata.py` — `down_revision='20260614c_feedback_assignee'`
  (coluna `msg_metadata` JSONB + índice único parcial).
- `alembic/versions/20260618b_roadmap_cross_links.py` — `down_revision='20260618_message_dedup_metadata'`.
  **No-op defensiva** no schema atual (ver §6).
- Testes: `tests/test_message_dedup.py` (4) + regressão em `tests/test_webhook_capture.py`.

---

## 4. Verify consolidado (rodado por mim, da raiz)
- `py -m pytest -q` → **466 passed** em ~43s (subiu de 438 → **+28**).
- `npx tsc --noEmit` (em `frontend/`, com `NODE_OPTIONS=--use-system-ca`) → **0 erros**.

---

## 5. Onde paramos / próximos passos (dependem de você)
1. **Revisão do diff** — rodar `/code-review` adversarial sobre as mudanças desta sessão antes de qualquer commit.
2. **Fase 0 pré-flight (read-only no piloto)** — `SELECT version_num FROM alembic_version`; listar tabelas;
   checar duplicatas em `messages` por `(organization_id, channel_msg_id)` **antes** de aplicar migration.
3. **Aplicar as 2 migrations no piloto** — **só com OK explícito**, depois da Fase 0.
4. **Validação visual da R4** logado — subir a stack (`/escuta-stack`) e conferir os filtros no `/board`.
5. **Commit** quando aprovado (working tree tem acúmulo de sessões anteriores — separar o que entra).
6. **Fase 2 do plano** (próxima grande frente): tools/function-calling (`chat_with_tools`, `VoCAgentOrchestrator`)
   + busca híbrida no RAG. Ver tabela de decisões no `SESSAO_HANDOFF_2026-06-18.md` §3.3.

---

## 6. Pegadinhas / achados novos desta sessão
- **`improvement_id` já existia** em `feedback_items` (migration `20260612c_improvements`) e em `feedback_clusters`
  (`20260614_feedback_clusters`). Por isso `20260618b_roadmap_cross_links` foi escrita **idempotente/defensiva**:
  inspeciona o schema em runtime e só adiciona coluna/índice/FK onde faltar → **no-op no schema atual** (verificado
  em SQLite efêmero). Mantida na cadeia para ambientes que estejam atrás.
- **`Settings` é `@dataclass(frozen=True)`** → não dá pra monkeypatchar atributo direto nos testes. A flag
  `NO_KB_FALLBACK` é lida em call-time via `_no_kb_fallback_enabled()` (ponto de teste/indireção).
- Circuit breaker conta **falha de upstream**, não erro de validação/parse — JSON inválido do Groq **não** abre o circuito.
- (Confirmadas do handoff anterior) pytest **sempre da raiz do escuta**; emoji em `.ts/.tsx` só com `\u{...}`;
  copia-edita-reatribui em JSONB; migration no piloto só com OK.

---

## 7. Como religar a stack
Use a skill **`/escuta-stack`** (sobe API 8000 / painel 3001 / WAHA 3000 + Podman; não duplicar comandos aqui).

---

## 8. Refs rápidas (por caminho/env — sem valores de segredo)
- Flags novas: `NO_KB_FALLBACK_ENABLED` (default 1), `BRAIN_MIN_RELEVANT_SCORE` (0.30).
- Migrations novas: `alembic/versions/20260618_message_dedup_metadata.py`, `20260618b_roadmap_cross_links.py`.
- Novos módulos: `app/services/circuit_breaker.py`, `app/domain/survey/message_handler.py`, `app/schemas/messages.py`.
- Fonte da verdade: `docs/BIZZU_ESCUTA_MASTER.md` (§7 = backlog priorizado). Diário anterior de hoje:
  `docs/SESSAO_HANDOFF_2026-06-18.md`. Histórico cronológico desta sessão: `docs/HISTORICO_SESSAO_2026-06-18_FASE1_R4.md`.
