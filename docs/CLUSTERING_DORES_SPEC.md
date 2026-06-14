# Clustering Semântico de Dores — Spec (Camada 1 da Central de Gestão de Feedbacks)

> Transforma a aba "Temas" (que hoje só **conta tags** que a IA colou) numa descoberta automática de
> **DORES** agrupadas por significado, reusando a infra de embeddings/pgvector que já existe (parada, só
> usada no RAG). Gerada 2026-06-14. Fonte única de verdade p/ backend e frontend.

## 0. Princípio
Reusar tudo (NÃO reescrever): `EmbeddingService` (MiniLM 384d, offline, lazy) e o padrão de query pgvector
de `app/domain/knowledge/retriever.py`. **Os 265 testes continuam verdes.** Nada de WhatsApp. LLM best-effort.

## 1. Schema (migration `alembic/versions/20260614_feedback_clusters.py`, down_revision `20260613_playbooks_cs_tasks`)
### Tabela `feedback_clusters`
| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | UUID FK→organizations CASCADE | |
| `label` | str? | título da dor (LLM): "Dificuldade com acesso à conta" |
| `description` | text? | 1 parágrafo (LLM) |
| `dominant_sentiment` | str? | `positivo`/`neutro`/`negativo` (mais frequente) |
| `item_count` | int | cache, atualizado na run |
| `improvement_id` | UUID FK→improvements SET NULL? | liga a dor a uma melhoria (usado no Roadmap depois) |
| `centroid` | `vector(384)` | **fora do ORM** (só na migration + SQL cru), igual `knowledge_chunks` |
| `created_at`/`updated_at` | timestamptz | |

### Colunas novas em `feedback_items`
- `cluster_id UUID REFERENCES feedback_clusters(id) ON DELETE SET NULL` (no ORM, nullable)
- `embedding vector(384)` — **fora do ORM** (só migration + SQL cru)

### Índices
`ix_feedback_clusters_org` (org) e `ix_feedback_items_cluster_id` (cluster_id) — portáveis (vão no ORM/migration).
HNSW cosseno em `feedback_clusters.centroid` e `feedback_items.embedding` — **PG-only via `op.execute()`**.
`op.execute("CREATE EXTENSION IF NOT EXISTS vector")` defensivo. **Nada de `postgresql_where`/vector nos models** (quebra SQLite dos testes).

## 2. Motor — `app/domain/clustering/engine.py`
```
async def run_clustering(session, org_id, *, embedder, llm=None, threshold=0.75,
                         dry_run=True, now=None) -> ClusterReport
```
- Carrega via SQL cru os `feedback_items` da org com `embedding IS NOT NULL` (id, embedding, sentiment, text).
- Vetores → `numpy.ndarray` float32 (já L2-normalizados → cosseno = dot).
- **Clustering aglomerativo por threshold** (O(n²), ok p/ ~centenas): cada item começa só; une pares com
  cosine ≥ `threshold`. (Acima de ~2k itens, trocar por `scipy` linkage='average' — anotar, não implementar.)
- Por cluster: centroide (média renormalizada), `dominant_sentiment` (Counter), `item_count`.
- `dry_run=True` (default): NÃO grava — só `ClusterReport`. `dry_run=False`: upsert em `feedback_clusters`
  (reusa cluster existente se centroide novo tem cosine ≥ 0.92 com um antigo); `UPDATE feedback_items SET
  cluster_id=...`; grava `centroid` via `to_pgvector`.
- **Rotulagem LLM (1 chamada/cluster, não por item)**: prompt com top-5 textos → `{label, description,
  dominant_sentiment}` JSON. Best-effort (try/except engole; cluster fica sem label). Só rotula clusters
  novos ou que cresceram >20%.
- `ClusterReport{evaluated, clusters_found, clusters_created, clusters_updated, items_assigned, dry_run}`.

Se `GroqLLM` não tiver um método simples de completar texto (`complete(prompt)->str`), adicionar o mínimo.

## 3. Geração de embeddings
- **Endpoint de lote** `POST /api/feedbacks/reindex?limit=200`: pega `feedback_items` com `embedding IS NULL
  AND text IS NOT NULL`, gera em batch via `embedder.embed([...])`, grava por SQL cru `UPDATE feedback_items
  SET embedding = CAST(:v AS vector) WHERE id=:id`. Best-effort por item. Retorna `{reindexed: N, remaining: M}`.
- **Inline** (write-path) atrás de flag `CLUSTERING_INLINE_ENABLED` (default **False**, em `app/config.py`):
  em `create_feedback` (admin) e na ingestão de eventos, após o commit, `asyncio.create_task` fire-and-forget
  que gera+grava o embedding numa sessão nova. Best-effort. Com a flag off, só o reindex manual roda.

## 4. API — `app/api/clusters.py` (router, registrado em `app/main.py` com prefix `/api`)
- `POST /api/feedbacks/reindex?limit=200` → `{reindexed, remaining}`
- `POST /api/feedbacks/cluster?dry_run=true` → `ClusterReport`
- `GET /api/feedbacks/clusters?days=30&sort=dor|volume|recente` → `{clusters:[ClusterOut], total_items_clustered, total_unclustered}`
  - `ClusterOut`: `{id, label, description, dominant_sentiment, item_count, neg_count, pain_score, top_themes, improvement_id, created_at}` · `pain_score = item_count * neg_fraction`
- `GET /api/feedbacks/clusters/{id}` → `{cluster, items:[até 50 FeedbackOut]}`
- `PATCH /api/feedbacks/clusters/{id}` `{label?, description?}` (operador corrige) → ClusterOut
- **+1 linha** em `list_feedbacks` (admin.py): filtro opcional `cluster_id` (`FeedbackItem.cluster_id == uuid`).

Padrões do repo: `APIRouter`, `Depends(get_session)`, `_get_org`, Pydantic inline, serializer `_out`. Embedder
injetável via dependency (`get_embedder_dep`) p/ stub em teste. SQL pgvector sempre via `text()` + bind (nunca f-string).

## 5. Frontend — aba "Por significado" na tela `/temas`
NÃO criar rota nova (Temas já cobre o conceito). Em `frontend/app/temas/page.tsx`: tab switcher
`"Por tag" | "Por significado"`. Na aba nova: `GET /api/feedbacks/clusters?sort=dor`, renderiza `ClusterCard`
(label ou "Cluster sem rótulo"; `item_count`; barra de sentimento reusando `SentimentBar`; `pain_score`;
badge `.badge.detractor` "dor crítica" se `item_count≥3 && dominant_sentiment=='negativo'`; botão "Ver
feedbacks" → `/feedbacks?cluster_id=<id>`). Tipos em `frontend/lib/api.ts` (`FeedbackCluster`, `ClustersResponse`).
Em `frontend/app/feedbacks/page.tsx`: aceitar `?cluster_id=` e repassar à API. **Corrigir** o deep-link de tag
(hoje `?search=` → usar `?theme=`). Sidebar: sem item novo.

## 6. Testes (sem tocar pgvector)
`tests/test_clustering.py`: engine `dry_run` com vetores numpy sintéticos (stub do SELECT de embeddings);
agrupamento correto; `FakeLLM` rotula; endpoints `GET/PATCH /clusters` com `FeedbackCluster` pré-inseridos
(sem `centroid`, fora do ORM); `reindex` com `EmbeddingService` stub (vetor fixo 384d). **`tests/conftest.py`:
adicionar `import app.models.cluster`** (senão SQLite não cria a tabela → "no such table"). `numpy` no `requirements.txt`.

## 7. Definition of Done
- [ ] model `FeedbackCluster` + migration `20260614_feedback_clusters` (head encadeada).
- [ ] `engine.py` + testes (dry_run não grava; agrupa; rotula best-effort).
- [ ] `clusters.py` (5 endpoints) + filtro `cluster_id` no inbox + registrado no main.
- [ ] inline atrás de flag OFF + reindex em lote.
- [ ] frontend aba "Por significado" + tipos + fix do deep-link; `tsc` limpo.
- [ ] suíte verde (265 + novos). Migration NÃO aplicada ainda (passo separado com OK).
