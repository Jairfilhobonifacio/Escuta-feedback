# Board de Gestão de Feedback — Spec (Camada 2 da Central de Gestão de Feedbacks)

> A camada "Gerir": eleva o `action_status` (que já existe) a um **Kanban visual** (novo→em_analise→
> planejado→resolvido), com **roteamento por time** e ligação direta feedback→melhoria. Gerada 2026-06-14.
> Reusa tudo (NÃO reescrever). 301 testes seguem verdes. Sem nova tabela — o board é uma VIEW do que já há.

## 0. O que já existe (reusar)
- `FeedbackItem.action_status` (`novo|em_analise|planejado|resolvido|descartado`), `abordado`, `improvement_id`.
- `/api/feedbacks` (inbox) com filtros + `compute_urgencia` + `_feedback_out` (`app/api/admin.py`).
- `PATCH /api/feedbacks/{id}` (já muda `action_status`). `Modal`/`Avatar`/`AbordarModal` no frontend.

## 1. Schema (migration `20260614c_feedback_assignee`, down_revision `20260614b_roadmap_links`)
Em `feedback_items` (ambos no ORM, portáveis, nullable):
- `assignee VARCHAR NULL` — quem do time cuida (slug/email; sem tabela de users, igual `cs_tasks.owner`).
- `team_tag VARCHAR NULL` — roteamento por time (`produto`/`suporte`/`comercial`/`cs`).
Índice `ix_feedback_items_assignee (organization_id, assignee)`.

## 2. API (estende `app/api/admin.py`)
- **Estender** `FeedbackCreateIn`/`FeedbackActionIn`/`_feedback_out` e `list_feedbacks` (filtros) com `assignee`, `team_tag`.
- **`GET /api/feedbacks/board?team_tag=&assignee=`** → itens agrupados por coluna:
  `{"columns": {"novo":{"count":N,"items":[...top 12 por urgência...]}, "em_analise":{...}, "planejado":{...}, "resolvido":{...}, "descartado":{...}}}`. 1 query (filtros aplicados), agrupa em Python, reusa `_feedback_out`+`compute_urgencia`. `count` = total da coluna; `items` = os 12 mais urgentes.
- **`POST /api/feedbacks/{id}/move`** `{status, improvement_id?, assignee?}` → muda `action_status` (valida vocabulário); se `status=='planejado'` e `improvement_id` dado, faz o vínculo (`feedback.improvement_id`, valida pertence à org); aplica `assignee` se dado. Retorna `_feedback_out`. É o "drag-and-drop": 1 request por card movido.

## 3. Frontend — tela `/board` (Kanban)
### `frontend/app/board/page.tsx` (NOVO)
- `.page-head` ("Board" / "Triagem do feedback — arraste para mover"). `.toolbar` com selects `team_tag` e `assignee`.
- **5 colunas** lado a lado (classe nova `.board-cols` grid/flex; coluna `.board-col` com cabeçalho `.board-col-head` = nome + `.badge` de count).
- Cards `.board-card` (reusa `.cell-person`+`Avatar`): tipo (`.badge.type`), trecho do texto (truncado), barra fina de urgência (verde<30/amarelo<60/vermelho≥60), chip de `team_tag`/`assignee` se houver. Click → `Modal` com detalhe + select "Mover para…" (status) + (se planejado) select de melhoria → `POST /api/feedbacks/{id}/move`.
- **Drag-and-drop nativo** (HTML5 Drag and Drop API, sem libs/sem Tailwind): `draggable`, `onDragStart` guarda `feedback.id`; `onDrop` na coluna → `api.post('/api/feedbacks/{id}/move', {status: coluna})` com **optimistic update** (move o card no estado local antes da resposta; reverte se erro).
- Consome `GET /api/feedbacks/board`.
### Sidebar (`frontend/components/Sidebar.tsx`)
Item **"Board"** entre "Feedbacks" e "Temas" (ícone de colunas/kanban: 3 `rect` verticais, SVG Lucide inline).
### Tipos (`frontend/lib/api.ts`)
`FeedbackBoard` (`columns: Record<status,{count,items:Feedback[]}>`), `FeedbackMoveInput` (`{status, improvement_id?, assignee?}`); + `assignee`/`team_tag` em `Feedback`.

## 4. Testes
`tests/test_board_api.py` (NOVO): `GET /board` agrupa por status + counts corretos; filtro `team_tag`; `POST /{id}/move` muda status; move p/ "planejado" com `improvement_id` válido vincula; improvement de outra org → 404; `PATCH` com `assignee`/`team_tag`. Padrão SQLite/conftest.

## 5. Definition of Done
- [ ] migration `20260614c_feedback_assignee` + campos no model.
- [ ] `GET /api/feedbacks/board` + `POST /api/feedbacks/{id}/move` + campos novos nos schemas/filtros.
- [ ] tela `/board` (Kanban drag-drop) + sidebar + tipos; `tsc` 0.
- [ ] testes novos; suíte verde (301 + novos). Migration NÃO aplicada ainda (passo separado).
