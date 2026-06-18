# Handoff — Onde Paramos (2026-06-18, fim do dia) — Auditoria multi-agente + Correções Fase 1/R4

> Continuação de `SESSAO_HANDOFF_2026-06-18_FASE1_R4_EXEC.md` (Fase 1 da IA + R4 do board).
> Esta sessão fez **duas coisas**: (1) uma **auditoria full em 8 agentes paralelos** (revisão adversarial +
> segurança + testes + multi-tenancy + plano Fase 2 + mapa do estado real) e (2) **corrigiu 7 achados**
> (4 blockers + 3 da Fase 1) via 4 agentes em frentes de arquivos disjuntos. Leia este primeiro para retomar.

---

## 1. TL;DR
- **Auditoria (8 agentes, read-only):** levantou 4 blockers + achados de segurança/multi-tenancy/testes,
  confirmou o estado real do repo e produziu o **blueprint completo da Fase 2** (tools/function-calling + RAG híbrida).
- **Correções (4 agentes, editando):** os **7 achados escolhidos (#1–#7)** foram corrigidos. **Verify consolidado
  VERDE: 484 passed** (era 466 → **+18**) · **tsc 0** no frontend.
- **Nada commitado. Nenhuma migration aplicada. Nenhum WhatsApp disparado.** Tudo uncommitted p/ revisão.
- **NÃO atacados (fora do escopo desta sessão):** multi-tenancy H1–H6, rotação de segredos, gaps de cobertura de teste.

---

## 2. Estado da stack
| Serviço | Porta | Estado |
|---|---|---|
| API FastAPI (uvicorn, sem `--reload`) | 8000 | parada (subir via `/escuta-stack`) |
| Painel Next.js | 3001 | parado |
| WAHA / Podman | 3000 | **parado** (intencional — WhatsApp só com OK) |
| Supabase | cloud (piloto) | intocado nesta sessão |

- **Branch:** `master` · **último commit:** `d873709` (board-hub camadas 2/3, de 14/06).
- **Working tree:** uncommitted = acúmulo de sessões anteriores + Fase 1/R4 + os arquivos novos desta sessão.
- **Migrations head no piloto:** `20260614c_feedback_assignee` (as 2 de `20260618*` **ainda não aplicadas**).
- **Cadeia Alembic local:** linear, 1 head → `20260618b_roadmap_cross_links`.

---

## 3. O que foi corrigido nesta sessão (#1–#7)

| # | Correção | Arquivo(s) | O que mudou |
|---|---|---|---|
| **1** | Circuit breaker decorativo | `app/services/llm.py` (+ `tests/test_llm_breaker_lifecycle.py`) | `GroqLLM` era instanciado por request → breaker novo e zerado toda vez (nunca abria). Agora há `_DEFAULT_BREAKER` singleton de módulo (ciclo de processo) + `reset_default_breaker()` p/ isolar testes. Injeção de breaker preservada. |
| **2** | `except IntegrityError` largo | `app/api/webhook.py` | `_is_dedup_violation()` só absorve a violação do índice `uq_messages_org_channel_msg_id`; **qualquer outra `IntegrityError` re-levanta** (vira `error`+rollback+`status:error`, não "duplicate" 200). Parou de perder mensagens silenciosamente. |
| **3** | Painel `/api/*` sem auth | `app/main.py` + **novo** `app/api/_security.py` | `require_panel_key` (header `X-Panel-Key`) aplicado a admin/digest/playbooks/tasks/clusters/campanha/boards/whatsapp. `integration` (já tinha) e `events` (HMAC próprio) preservados. |
| **4** | Webhook WAHA sem auth | `app/api/_security.py` + `webhook.py` | `require_waha_webhook_secret` (header `X-Webhook-Secret`), no modelo HMAC de `events.py`. |
| **5** | RAG honesto não-cabeado | `app/domain/survey/resolver.py` | **Confirmado: estava morto.** `_answer_question` chamava `answer_from_context` (None antigo) → caía no reply genérico. Agora chama `answer_question_grounded` (atrás da flag, default ON) → a `HONEST_NO_KB_MSG` de fato chega ao cliente. `brain.py` não precisou mudar. |
| **6** | Fetch redundante do board (R4) | `frontend/app/board/page.tsx` | `selecionarBoard()` zera filtros no mesmo commit da troca + removido o `useEffect` redundante → 1 fetch só, sem vazar o recorte do board anterior nem race. |
| **7** | KB quebrada invisível | `app/domain/survey/resolver.py` | Retrieval que **lança** agora loga `logger.error` ("FALHA na busca da KB") e NÃO se disfarça de resposta honesta — distinto de "KB sem match". |

**Arquivos novos desta sessão:** `app/api/_security.py`, `tests/test_llm_breaker_lifecycle.py`,
`tests/test_resolver_honest_kb.py`, `tests/test_webhook_auth.py`.

---

## 4. Verify consolidado (rodado da raiz, estado estável)
- `py -m pytest -q` → **484 passed** em ~106s (era 466 → **+18**).
- `npx tsc --noEmit` em `frontend/` (com `NODE_OPTIONS=--use-system-ca`) → **0 erros**.

---

## 5. Onde paramos / próximos passos (dependem de você)
1. **`/code-review` adversarial sobre o diff das correções** — escrevi código novo (auth, breaker singleton,
   classificação de IntegrityError); vale uma 2ª passada antes de confiar/commitar.
2. **Decisão fail-open × fail-closed em #3/#4** (ver §6 — pegadinha-mãe). Hoje é **fail-open quando a env
   não está setada**. Se quiser fail-closed (503 sem env, como a integração), precisa de `dependency_override`
   no conftest p/ a suíte não quebrar.
3. **Setar `PANEL_API_KEY` e `WAHA_WEBHOOK_SECRET`** no ambiente (sem elas, as portas seguem abertas).
4. **Fase 0 pré-flight (read-only no piloto)** → **aplicar as 2 migrations `20260618*`** (só com OK explícito).
5. **Commit** quando aprovado (separar o acúmulo de sessões anteriores do que entra).
6. **Backlog NÃO atacado desta vez:**
   - **Multi-tenancy H1–H6** (`select(Model).where(Model.id...)` sem `organization_id` em `boards.py:700`,
     `admin.py:2033/1538/1661`, `tasks.py:223/484/578`) — correção barata, padronizadora. + o **Critical latente**
     `webhook.py:256` (org hardcoded p/ toda inbound — bloqueio de go-live multi-tenant).
   - **Rotação de segredos:** **WAHA_API_KEY vazada** em `docs/SESSAO_HANDOFF_2026-06-07.md:107` e
     `...08.md:103` (versionados!); **senha Postgres Bizzu** hardcoded em `scripts/sync_bizzu_contacts.py:17,43`.
   - **Gaps de teste:** isolamento multi-tenant do board dinâmico; filtros `owner/priority/effort` que nunca
     filtram de fato; `msg_metadata` sem cobertura; `GroqLLM` never-raises só testa 5xx.
7. **Fase 2 (próxima grande frente):** blueprint pronto — `chat_with_tools()` no GroqLLM + `VoCToolRegistry`
   + 7 tools (registrar abordagem, selo, criar tarefa, vincular melhoria, atualizar feedback, **enviar WhatsApp
   com 3 gates**, ler perfil) + `VoCAgentOrchestrator` + `search_hybrid()` no RAG. **Sem migrations novas**,
   13 passos (P1→P13), atrás das flags `VOC_AGENT_ENABLED`/`VOC_WHATSAPP_TOOL_ENABLED` (OFF por default).

---

## 6. Pegadinhas / achados novos desta sessão
- **PEGADINHA-MÃE (#3/#4 fail-open):** as travas de auth do painel e do webhook **só fecham quando a env
  está configurada**. Sem `PANEL_API_KEY`/`WAHA_WEBHOOK_SECRET` definidas, elas **liberam + logam `warning`**.
  Foi deliberado p/ não quebrar o piloto nem a suíte (que não setam env). **Em produção é OBRIGATÓRIO setar as duas.**
- **O breaker era decorativo:** a lógica interna do `CircuitBreaker` estava correta e testada, mas o
  **ciclo de vida** (instância por request) zerava o estado — toda a resiliência da Fase 1 estava de fato desligada.
- **`answer_question_grounded` estava morto:** existia e tinha testes, mas o resolver nunca o chamava no fluxo real.
- **`BRAIN_MIN_RELEVANT_SCORE` é constante hardcoded** em `brain.py:39`, **não é env** (o handoff EXEC §8 listava
  como se fosse). Para mudar hoje é preciso editar código.
- **Contagem real do working tree ≈ 64 arquivos** uncommitted (handoffs anteriores diziam "~59").
- (Confirmadas) pytest **sempre da raiz do escuta**; emoji em `.ts/.tsx` só com `\u{...}`; copia-edita-reatribui
  em JSONB; migration no piloto só com OK.

---

## 7. Como religar a stack
Use a skill **`/escuta-stack`** (sobe API 8000 / painel 3001 / WAHA 3000 + Podman; não duplicar comandos aqui).

---

## 8. Refs rápidas (por caminho/env — sem valores de segredo)
- **Novas envs (defaults `None` = fail-open + warning):** `PANEL_API_KEY` (header `X-Panel-Key`),
  `WAHA_WEBHOOK_SECRET` (header `X-Webhook-Secret`). Definir em produção.
- **Flags existentes relevantes:** `NO_KB_FALLBACK_ENABLED` (ON), `ESTEIRA_ENABLED` (ON),
  `PLAYBOOKS_INLINE_ENABLED` (OFF), `INTEGRATION_API_KEY` (None→integração 503).
- **Novos módulos/arquivos:** `app/api/_security.py`; testes `test_llm_breaker_lifecycle.py`,
  `test_resolver_honest_kb.py`, `test_webhook_auth.py`.
- **Migrations escritas, não aplicadas:** `alembic/versions/20260618_message_dedup_metadata.py`,
  `20260618b_roadmap_cross_links.py`.
- **Fonte da verdade:** `docs/BIZZU_ESCUTA_MASTER.md` (§7 = backlog) — **PENDENTE atualizar** com a nova
  camada de auth, o singleton do breaker e o cabeamento do RAG honesto. Diários anteriores de hoje:
  `docs/SESSAO_HANDOFF_2026-06-18.md`, `docs/SESSAO_HANDOFF_2026-06-18_FASE1_R4_EXEC.md`.

---

## 9. Auditoria — referência dos achados (para quem for atacar o backlog)
- **Blockers (corrigidos):** #1 breaker · #2 IntegrityError · #3 auth painel · #4 auth webhook.
- **Fase 1 (corrigidos):** #5 RAG honesto cabeado · #6 fetch board R4 · #7 KB quebrada visível.
- **Abertos (segurança):** painel/webhook precisam das envs setadas; WAHA key + senha Bizzu a rotacionar.
- **Abertos (multi-tenancy):** C1 (`webhook.py:256` org hardcoded) + H1–H6 (queries por id sem `organization_id`).
  RAG/clustering/CS-engine já estão corretamente escopados. Bug de mutação in-place de JSONB **não existe**.
- **Abertos (testes):** ver §5.6.
- **Fase 2:** blueprint completo (ver §5.7).
