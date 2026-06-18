# Handoff — Onde Paramos (2026-06-14) — Central de Gestão de Feedbacks

> Estado canônico ao fim da sessão. Cobre o **pivô do Escuta para uma central de GESTÃO de feedbacks**
> (3 camadas) + a Fase 2 (Playbooks) feita mais cedo no mesmo dia. Leia este primeiro para retomar.

---

## 1. TL;DR — o que está no ar
O Escuta deixou de "só coletar + reagir a churn" e passou a **gerir o ciclo do feedback de ponta a ponta**:

```
 COLETA → [1] ENTENDER (clustering de dores) → [2] GERIR (board) → [3] DECIDIR (roadmap) → ENTREGA → FECHA O LOOP
```

Tudo **validado AO VIVO no piloto** (Supabase `nlqeargxkidygbrahkbk`), **315 testes verdes**, **`tsc` 0**,
**0 WhatsApp disparado**. Commitado na `master` (sem push — repo local, sem remote).

## 2. Estado por área
- **Migrations aplicadas no piloto** → head **`20260614c_feedback_assignee`**. Cadeia desta sessão:
  `20260613_playbooks_cs_tasks` (Fase 2) → `20260614_feedback_clusters` (C1) → `20260614b_roadmap_links` (C3) → `20260614c_feedback_assignee` (C2).
- **Commits** (`master`, sem push): `254d411` Fase 2 · `d952023` Camada 1 · `d873709` Camadas 2+3.
- **Stack rodando**: API FastAPI `:8000` (uvicorn, **sem `--reload`**) + painel Next `:3001`. Supabase cloud + Groq + WAHA/Podman `:3000` (parado, não foi usado).
- **Telas no ar**: `/` (Dashboard) · `/feedbacks` · **`/board`** 🆕 · `/temas` (com aba **"Por significado"** 🆕) · **`/melhorias`** 🆕 · `/clientes` · `/contatos` · `/pesquisas` · `/tarefas` (Fase 2) · `/playbooks` (Fase 2).

## 3. As 3 camadas da central de gestão (14/06)

### Camada 1 — ENTENDER: Clustering Semântico de Dores
A aba "Temas" só **contava tags** (`digest/aggregator.py:185`, tinha o comentário "v2 = clustering semântico").
Agora a IA **agrupa por significado** e rotula cada dor, reusando embeddings/pgvector (antes só no RAG).
- **Motor**: `app/domain/clustering/engine.py::run_clustering` — aglomerativo por cosseno, **threshold 0.48** (calibrado; 0.75 fragmentava) + **separa por sentimento** (`_agglomerate_by_sentiment` — MiniLM é inglês e misturava elogio com crítica). Rotulagem LLM 1×/cluster via **`brain.llm`** (o `GroqLLM` DENTRO do `SurveyBrain`, não o brain). `dry_run` idempotente.
- **Dados**: model `app/models/cluster.py` (`FeedbackCluster`) + migration `20260614_feedback_clusters`. `feedback_clusters.centroid` e `feedback_items.embedding` são `vector(384)` **FORA do ORM** (só migration + SQL cru, igual `knowledge_chunks`). `feedback_items.cluster_id` no ORM.
- **API** `app/api/clusters.py`: `POST /api/feedbacks/reindex?limit=` (gera embeddings em lote), `POST /api/feedbacks/cluster?dry_run=`, `GET/PATCH /api/feedbacks/clusters`. Flag `CLUSTERING_INLINE_ENABLED` (default **off**). Filtro `cluster_id` no inbox.
- **Front**: aba **"Por significado"** em `frontend/app/temas/page.tsx` (cards de dor + índice de dor) + fix do deep-link de tag (`?theme=`).
- **Ao vivo**: 27 feedbacks → **11 dores** rotuladas (Cancelamento, Falta de Recursos, Dificuldade de Navegação…).
- 🔴 **Limite**: MiniLM é **inglês** → fragmenta/erra nuance em PT (dores quase-duplicadas). **Próximo passo de qualidade = embedding multilíngue** (re-gerar vetores; a `HUGGINGFACE_API_KEY` precisa estar válida). Também: os "churn codes" (USER_CANCEL/PAYMENT_FAILED) entram como dores — idealmente o clustering focaria só no texto livre.

### Camada 2 — GERIR: Board Kanban
- **API** (`app/api/admin.py`): `GET /api/feedbacks/board?team_tag=&assignee=` (agrupa por `action_status`, top 12/coluna por urgência) + `POST /api/feedbacks/{id}/move` `{status, improvement_id?, assignee?}` (drag-drop; em "planejado" vincula melhoria). `feedback_items` + `assignee`/`team_tag` (migration `20260614c`).
- **Front**: `frontend/app/board/page.tsx` — Kanban 5 colunas, **drag-drop HTML5 nativo** (optimistic + revert), card abre `Modal`. Item "Board" na sidebar.
- **Ao vivo**: novo 63 · em_analise 1.

### Camada 3 — DECIDIR + FECHAR O LOOP: Roadmap/Melhorias
O `Improvement` tinha API (CRUD+link+notify) mas **ZERO tela**. Agora tem.
- **API** (`app/api/admin.py`): `GET /api/improvements/roadmap?status=` (prioriza por **volume×impacto** `priority_score = feedback_count * max(urgencia_media,1) * (1 + cluster_neg_fraction)`) + `POST /api/improvements/from-cluster` `{cluster_id, title?}` (transforma uma **dor** em melhoria, vinculando os feedbacks; **idempotente**). `improvements` + `cluster_id`/`effort`/`target_date` (migration `20260614b`). `notify` (fechar o loop) reusado.
- **Front**: `frontend/app/melhorias/page.tsx` (lista priorizada + estágios + "Fechar o loop"/notify) + botão **"Virar melhoria"** no card de dor. Item "Melhorias" na sidebar.
- **Ao vivo**: dor "Cancelamento" → melhoria **score 902** (> Reembolso 474 > Insatisfação 414).
- ⚠️ **Drift de contrato**: `_improvement_out` emite sufixo **`_em`** (`notified_em`/`created_em`), a spec usava `_at` — o front lê **ambos** defensivamente. Limpar um dia.

## 4. Fase 2 (Playbooks & Automação) — feita mais cedo hoje (já no ar)
Motor gatilho→ação + fila de Tarefas. Detalhe em `docs/SESSAO_HANDOFF_2026-06-14.md`. Resumo: `app/domain/cs/engine.py::run_playbooks` (5 gatilhos→`create_task`/`alert_owner`, flag `PLAYBOOKS_INLINE_ENABLED` off), telas `/tarefas`+`/playbooks`. **87 `CsTask` reais** na fila do piloto.

## 5. Como retomar
1. **Subir/checar a stack**: `/escuta-stack` (sobe 8000/3001) ou manual — ver §6. `curl localhost:8000/health`.
2. **Ver no navegador**: `localhost:3001/temas` (aba "Por significado") · `/board` · `/melhorias` · `/tarefas` · `/playbooks`.
3. **Contexto**: `/bizzu-escuta`. Specs em `docs/{CLUSTERING_DORES,ROADMAP_MELHORIAS,BOARD_GESTAO,FASE2_PLAYBOOKS}_SPEC.md`.

## 6. Pegadinhas (já custaram tempo nesta sessão)
- **Aplicar migration**: `alembic/env.py` **NÃO carrega `.env`** → rodar via `py -c "from dotenv import load_dotenv; load_dotenv(); subprocess.call([...,'alembic','upgrade','head'])"` (o subprocess herda `DATABASE_URL`). Cada migration nova no piloto **pede OK explícito** (o classificador bloqueia "continue" genérico).
- **Reiniciar a API a cada camada**: uvicorn sobe **sem `--reload`** → matar o processo na 8000 (é o que *nós* criamos) e ressubir com `HF_HUB_OFFLINE=1` + `host 0.0.0.0`, p/ pegar models/rotas novos. O `GET` de leitura não precisa, mas `POST`/novos endpoints sim.
- **Rotulagem de cluster** usa `brain.llm` (extraído do `SurveyBrain` via `getattr(brain,'llm',None)`), NÃO o brain. Passar o brain inteiro = clusters "sem rótulo" (falha best-effort silenciosa).
- **Embedder ao vivo**: `embed_one` é **async** (`await`) + precisa `truststore.inject_into_ssl()` + `HF_HUB_OFFLINE=1`. Funciona (MiniLM no cache HF).
- **Encerrar processo que não criamos** (ex.: o painel `:3001` do usuário) é **bloqueado** pelo classificador — reusar o que já está rodando (next dev pega rotas novas por hot-reload).

## 7. Próximos passos (priorizados)
1. **Embedding multilíngue** (qualidade do clustering em PT) — o maior retorno. Re-gerar embeddings após validar a chave HF; considerar separar churn codes do clustering de dores.
2. **`git push`** — configurar um remote (não há). E **limpar a PII** de `scripts/export_churn.py` + `docs/campanhas/*` (estão fora do git por isso).
3. **Cron** (Modal/n8n) → `POST /api/feedbacks/cluster`, `/api/playbooks/run`, `/api/digest/run` 1×/dia.
4. **Refinos**: drift `_em`×`_at`; ligar flags inline (`CLUSTERING_INLINE_ENABLED`/`PLAYBOOKS_INLINE_ENABLED`) após calibrar; deploy cloud do Escuta.

## 8. Regras de ouro do projeto
Bizzu = leitura (patches, nunca commit nos clones) · Escuta = código · segredos por env · **WhatsApp real só com OK** · PII fora do git.
