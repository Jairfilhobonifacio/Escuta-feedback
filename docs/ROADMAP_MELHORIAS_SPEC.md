# Roadmap & Melhorias — Spec (Camada 3 da Central de Gestão de Feedbacks)

> Fecha o ciclo: **dor (cluster) → melhoria priorizada → entrega → avisar o cliente**. Hoje a API de
> `Improvement` existe (CRUD + link + notify) mas **não tem tela** e nada liga as dores às melhorias.
> Gerada 2026-06-14. Reusa tudo (NÃO reescrever). 282 testes seguem verdes. Nada de WhatsApp sem confirm.

## 0. O que já existe (reusar)
- `app/models/improvement.py` (`Improvement`: title, description, status ideia→planejada→em_andamento→entregue→descartada, delivered_at, notified_at) + `FeedbackItem.improvement_id` (FK).
- Endpoints (`app/api/admin.py` ~1393): `POST/GET /api/improvements`, `PATCH /api/improvements/{id}`, `POST /api/improvements/{id}/link` (vincula feedbacks), `POST /api/improvements/{id}/notify` (preview/`?confirm=true`, "você pediu, a gente fez", respeita opt_in+cooldown).
- `FeedbackCluster.improvement_id` (FK→improvements) já existe (migration `20260614_feedback_clusters`).
- `compute_urgencia` (`admin.py` ~559) — reusar no score.

## 1. Schema (migration `20260614b_roadmap_links`, down_revision `20260614_feedback_clusters`)
Em `improvements`:
- `cluster_id UUID REFERENCES feedback_clusters(id) ON DELETE SET NULL` (no ORM, nullable) — a melhoria responde a uma dor.
- `effort VARCHAR NULL` — `P`/`M`/`G`/`XG` (sem enum no banco; valida na API).
- `target_date TIMESTAMPTZ NULL` — data-alvo (exibida no roadmap).
Índice `ix_improvements_cluster_id`. Tudo aditivo/portável (sem pgvector → SQLite/testes ok).

## 2. API (estende `app/api/admin.py`)
- **Estender** `ImprovementIn`/`ImprovementPatchIn`/`_improvement_out` com `cluster_id`, `effort`, `target_date` (PATCH parcial via `model_fields_set`; valida `cluster_id` pertence à org).
- **`GET /api/improvements/roadmap?status=`** → lista priorizada. Para cada improvement: `feedback_count` (já existe) + `urgencia_media` (média do `compute_urgencia` sobre os feedbacks vinculados — **1 query em lote** `WHERE improvement_id IN (...)`, agrupa em Python; nada de N+1) + `cluster_label`/`cluster_neg_fraction` (se `cluster_id`). `priority_score = feedback_count * max(urgencia_media,1) * (1 + cluster_neg_fraction)`. Ordena desc. Campos: todos do `_improvement_out` + `priority_score`, `urgencia_media`, `cluster_label`.
- **`POST /api/improvements/from-cluster`** `{cluster_id, title?}` → **cria** uma `Improvement` a partir de uma dor: title = `title` ou o `label` do cluster; status `ideia`; seta `improvement.cluster_id` E `cluster.improvement_id`; **bulk-link** de todos os `FeedbackItem` daquele cluster (`improvement_id = nova.id`). Retorna o `_improvement_out` com `feedback_count`. Idempotente: se o cluster já tem `improvement_id`, retorna a existente (não duplica).
- `notify` e `link` já existem — manter intactos.

## 3. Frontend — tela `/melhorias` (a que falta) + botão na aba de dores
### `frontend/app/melhorias/page.tsx` (NOVO)
Roadmap visual orientado a feedback. Cabeçalho `.page-head`. Layout `.two-col` (igual `/pesquisas`):
- **Esquerda (lista priorizada)**: consome `GET /api/improvements/roadmap`. Cada item num card `.card`/`.survey-item`:
  título; badge de estágio (`.badge`: ideia/planejada/em_andamento/entregue/descartada); **`feedback_count`** com texto "N clientes pediram isso"; `priority_score` em destaque (mono); `effort` como `.chip`; `cluster_label` (se houver) como `.chip` clicável → `/temas` (aba significado); select de estágio que faz `PATCH /api/improvements/{id}`; quando `status==='entregue' && !notified_at`, botão **"Fechar o loop"** → abre `Modal` (reusar) com preview do `notify` (`GET`/sem confirm) e botão "Confirmar envio" (`?confirm=true`).
- **Direita (form criar)**: title, description, effort (select P/M/G/XG), target_date (date), estágio inicial. `POST /api/improvements`.
- Loading/empty states.
### `frontend/app/temas/page.tsx` — botão "Virar melhoria" no `ClusterCard`
No card de cada dor (aba "Por significado"), botão **"Virar melhoria"** → `POST /api/improvements/from-cluster {cluster_id}` → flash de sucesso + link "ver em Melhorias". (Cria a melhoria a partir da dor e vincula os feedbacks.)
### Sidebar (`frontend/components/Sidebar.tsx`)
Adicionar item **"Melhorias"** após "Temas" (ícone lâmpada/check-circle, SVG Lucide inline).
### Tipos (`frontend/lib/api.ts`)
`Improvement` (estender com `cluster_id`, `effort`, `target_date`, `feedback_count`, `priority_score?`, `urgencia_media?`, `cluster_label?`, `delivered_at`, `notified_at`), `ImprovementRoadmapItem`.

## 4. Testes
`tests/test_roadmap_api.py` (NOVO): `GET /roadmap` ordena por `priority_score` (3 improvements com counts diferentes); score sobe com cluster negativo; `?status=` filtra; `POST /from-cluster` cria + vincula todos os feedbacks do cluster + idempotente (cluster já com improvement → mesma). Estender `tests/test_improvements_api.py` com `cluster_id`/`effort`/`target_date` no create/patch. Padrão SQLite/conftest.

## 5. Definition of Done
- [ ] migration `20260614b_roadmap_links` (head encadeada) + campos no model.
- [ ] `GET /api/improvements/roadmap` + `POST /api/improvements/from-cluster` + campos novos nos schemas.
- [ ] tela `/melhorias` (lista priorizada + form + estágio + fechar-o-loop) + botão "Virar melhoria" na aba de dores + sidebar + tipos; `tsc` 0.
- [ ] testes novos; suíte verde (282 + novos). Migration NÃO aplicada ainda (passo separado).
