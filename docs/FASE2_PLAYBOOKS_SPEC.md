# Fase 2 — Playbooks & Automação (gatilho → ação) + Fila de Tarefas de CS

> Spec canônica da Fase 2 do `ROADMAP_CS.md`. Fonte única de verdade para backend e frontend.
> Gerada 2026-06-13 a partir de 4 mapeamentos do código (dados, motor de eventos, API, painel).
> **Princípio:** reaproveitar tudo que já existe (não reescrever). Nada toca produção sem OK.

## 0. Objetivo
Transformar o closed-loop **manual** de hoje (operador lê inbox → aborda no WhatsApp) num
**semi-automático**: um motor de regras observa gatilhos (detrator, conta em risco, inatividade,
renovação, churn) e cria **tarefas de CS** numa fila priorizada — opcionalmente alertando o dono.
A abordagem em si segue humana (reusa o modal "Abordar no WhatsApp").

## 1. Regras de segurança (inegociáveis)
1. **Não dispara WhatsApp para o cliente** no MVP. `action_type=alert_owner` só fala com o dono
   (reusa `owner_phone` + WAHA, igual ao alerta de detrator). Disparo ao contato fica para depois.
2. **Os 235 testes continuam verdes.** Código novo vem com testes próprios (SQLite, padrão `conftest`).
3. **Plugues inline atrás de flag `PLAYBOOKS_INLINE_ENABLED` (default `false`)** e **best-effort**
   (try/except que NUNCA propaga p/ o webhook do WAHA nem p/ o endpoint de eventos). Com a flag off,
   o comportamento atual é idêntico — o motor só roda via `POST /api/playbooks/run`.
3. **Migration NÃO é aplicada automaticamente.** Fica pronta; aplicar no Supabase é passo manual
   com `DATABASE_URL` exportado (pegadinha conhecida do `alembic/env.py`).
4. **Índices parciais (`postgresql_where`) só na migration**, nunca no `__table_args__` dos models
   (senão quebram o `create_all` do SQLite nos testes).

## 2. Schema (2 tabelas novas)
JSONB livre via `JSONVariant` (= `JSON().with_variant(JSONB,"postgresql")`), igual a `profile_data`.

### `playbooks` — a regra (stateless)
| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | `default=uuid.uuid4` (server `gen_random_uuid()` na migration) |
| `organization_id` | UUID FK→organizations CASCADE | |
| `name` | str | |
| `description` | str? | |
| `enabled` | bool | default `true` |
| `trigger_type` | str (enum) | `nps_detractor` \| `health_at_risk` \| `inactive_days` \| `renewal_soon` \| `churn_detected` |
| `trigger_config` | JSONB | ex.: `{"band":"at_risk"}`, `{"days":14}`, `{"days_before":7}`, `{"max_score":6}` |
| `action_type` | str (enum) | `create_task` \| `alert_owner` |
| `action_config` | JSONB | ex.: `{"title":"Abordar {nome}","priority":"alta","sla_hours":24,"owner":"cs"}` |
| `created_at`/`updated_at` | timestamptz | server_default now / onupdate |

### `cs_tasks` — a tarefa concreta (fila de CS)
| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | UUID FK→organizations CASCADE | |
| `contact_id` | UUID FK→contacts SET NULL? | nullable |
| `playbook_id` | UUID FK→playbooks SET NULL? | nullable (null = tarefa manual) |
| `feedback_item_id` | UUID FK→feedback_items SET NULL? | nullable (contexto) |
| `survey_response_id` | UUID FK→survey_responses SET NULL? | nullable (contexto) |
| `title` | str | interpolável com `{nome}` |
| `reason` | text? | contexto livre (pode vir de `ai_meta`/motivo do gatilho) |
| `status` | str | `aberta` \| `em_andamento` \| `concluida` \| `adiada` — default `aberta` |
| `priority` | str | `baixa` \| `normal` \| `alta` \| `urgente` — default `normal` |
| `owner` | str? | slug/telefone/email do responsável (sem tabela de users ainda) |
| `due_at` | timestamptz? | SLA = `created_at + sla_hours` |
| `snoozed_until` | timestamptz? | preenchido ao adiar (status→`adiada`) |
| `notes` | text? | anotações do operador |
| `meta` | JSONB | snapshot do gatilho: `{health, health_band, nps_score, perfil, trigger_type}` |
| `dedup_key` | str? UNIQUE(org_id,dedup_key) | idempotência do motor; null = duplicata permitida |
| `created_at`/`updated_at` | timestamptz | |
| `closed_at` | timestamptz? | preenchido ao virar `concluida` |

### Migration
Arquivo `alembic/versions/20260613_playbooks_cs_tasks.py`, `down_revision="20260612c_improvements"`
(head atual). Cria as 2 tabelas. Índices: `ix_playbooks_org`, parcial
`ix_playbooks_org_trigger (org,trigger_type) WHERE enabled`; `ix_cs_tasks_org_status_due`,
parcial `ix_cs_tasks_org_open (org,status) WHERE status='aberta'`, `ix_cs_tasks_contact`,
único `uq_cs_tasks_dedup (organization_id, dedup_key)`. `downgrade` dropa tudo.

## 3. Motor — `app/domain/cs/engine.py`
Função quase-pura (recebe sessão + dados, sem rede salvo a ação `alert_owner`):
```
async def run_playbooks(session, org_id, *, triggers=None, dry_run=True, messaging=None,
                        now=None) -> RunReport
```
- Carrega playbooks `enabled` da org (filtra por `trigger_type` em `triggers` se dado).
- Para cada playbook, resolve os **candidatos** conforme `trigger_type`:
  - `nps_detractor`: `Contact.profile_data["partner"]["nps"]["score"] <= trigger_config.get("max_score",6)`.
  - `health_at_risk`: `compute_health(...)` (reusa Fase 1) com `band == trigger_config.get("band","at_risk")`.
  - `inactive_days`: último `FeedbackItem` há mais de `trigger_config["days"]` dias (ou nunca).
  - `renewal_soon`: `partner.subscription.daysAsSubscriber`/`currentPeriodEnd` → `dias_para_renovar <= days_before`.
  - `churn_detected`: existe `FeedbackItem(type='churn')` não vinculado a tarefa ainda.
- **Avaliação de `condition`/`trigger_config` é comparação de chaves — SEM `eval`.**
- Ação:
  - `create_task`: monta `CsTask` (interpola `{nome}`, calcula `due_at` por `sla_hours`, grava `meta`
    com o snapshot, `dedup_key = f"{trigger_type}:{contact_id}:{YYYY-MM}"`). Idempotente por `dedup_key`.
  - `alert_owner`: só se `dry_run=false` E `messaging` presente E `owner_phone` existir → `send_text`.
- Retorna `RunReport{evaluated, playbooks_run, tasks_would_create[], tasks_created, skipped_duplicate}`.
- `dry_run=true` (default): não grava nada, só relata.

### Plugues inline (atrás de `PLAYBOOKS_INLINE_ENABLED`, best-effort)
- `app/domain/survey/resolver.py` ~L174 (após `_classify`, antes de `_notify_detractor_realtime`):
  `trigger='nps_detractor'` quando `nps_bucket=='detractor'`.
- `app/api/events.py` antes do `return` final: `trigger=payload.event` (ex.: `subscription_cancelled`).
- Envolver em `try/except` que loga e engole — webhook/eventos nunca podem cair por causa do motor.

## 4. API (prefixo `/api`) — routers novos `app/api/playbooks.py` e `app/api/tasks.py`
Padrão do repo: `APIRouter()`, `Depends(get_session)`, helper `_get_org`, schemas Pydantic inline,
serializer `_out()`. Registrar ambos em `app/main.py` com `prefix="/api"`.

### Playbooks
- `GET /api/playbooks` → `list[PlaybookOut]`
- `POST /api/playbooks` 201 (valida enums; 409 nome duplicado) → `PlaybookOut`
- `PATCH /api/playbooks/{id}` (parcial via `model_fields_set`) → `PlaybookOut`
- `DELETE /api/playbooks/{id}` 204
- `POST /api/playbooks/run?dry_run=true` → `RunReport` (chamável por cron externo, igual a `/api/digest/run`)

`PlaybookOut`: `{id, name, description, enabled, trigger_type, trigger_config, action_type, action_config, created_at, updated_at}`

### Tarefas
- `GET /api/tarefas?status=&owner=&priority=&contact_id=&playbook_id=&sort=&limit=50&offset=0`
  → `{items: TarefaOut[], total, counts_by_status:{aberta,em_andamento,concluida,adiada}}`
  - `sort`: `prioridade` (default; urgente→baixa, depois due_at asc) \| `recente` \| `sla`.
  - `health`/`health_band` recomputados inline (reusa `compute_health`) p/ refletir estado atual.
- `POST /api/tarefas` 201 (manual): `{contact_id, title, reason?, priority?, owner?, due_at?}` → `TarefaOut`
- `PATCH /api/tarefas/{id}` (parcial): `{status?, owner?, priority?, due_at?, snoozed_until?, notes?}`.
  Ao `status=concluida` grava `closed_at=now`; ao setar `snoozed_until` força `status=adiada`.

`TarefaOut`: `{id, contato_id, contato_nome, contato_whatsapp, playbook_id, playbook_nome, title,
reason, status, priority, owner, due_at, snoozed_until, notes, health, health_band, meta, criada_em, atualizada_em}`

## 5. Frontend (`frontend/`, Next 15 App Router, fetch puro, sem Tailwind)
Reusar `lib/api.ts` (`api.get/post/patch/del`) e classes do `globals.css`. **Extrair** para `components/`
(hoje inline em `app/feedbacks/page.tsx`): `Modal` (L145), `ConfirmDialog` (L206), `AbordarModal` (L718).
Extrair `healthCell()` (de `app/clientes/page.tsx:45`) p/ `components/HealthCell.tsx`.

### `/tarefas` — `app/tarefas/page.tsx`
Fila priorizada (contas a abordar hoje). Cabeçalho `.page-head`; KPIs (Abertas / Vencidas / Concluídas
hoje) com `.kpi-grid`; `.toolbar` (busca + selects status/dono/prioridade); tabela com colunas
**Cliente** (`.cell-person`+`Avatar`), **Saúde** (`HealthCell` reusado), **Motivo** (`.badge.type`),
**Playbook** (`.chip`), **Dono**, **SLA** (mono, `.renova-soon` se vencido), **Status** (`.badge`),
**Ação** (`.btn-wa-sm` → abre `AbordarModal` reusado via adaptador que monta um objeto mínimo com
`contato_id/nome/whatsapp`). Consome `GET /api/tarefas`, `PATCH /api/tarefas/{id}`.

### `/playbooks` — `app/playbooks/page.tsx`
Layout `.two-col` (igual `/pesquisas`): esquerda lista de regras (nome + badge ativo/inativo + "gatilho→ação"
+ toggle + editar/excluir); direita form criar/editar (nome, select gatilho, config condicional, select ação,
dono padrão, SLA horas, ativo). Consome CRUD `/api/playbooks`.

### Sidebar (`components/Sidebar.tsx:27`)
Adicionar 2 itens após "Contatos": **Tarefas** (`/tarefas`, ícone checklist) e **Playbooks**
(`/playbooks`, ícone documento-regra). SVG inline estilo Lucide (`viewBox 0 0 24 24`, stroke currentColor 1.75).

### Tipos (`lib/api.ts`)
`Tarefa`, `Playbook`, `TarefaCounts` — campos espelhando `TarefaOut`/`PlaybookOut` acima.

## 6. Definition of Done
- [ ] Models `Playbook`/`CsTask` + migration `20260613_playbooks_cs_tasks` (head encadeada).
- [ ] `engine.py` + testes (criação idempotente por `dedup_key`, dry_run não grava, cada trigger, condição sem eval).
- [ ] Routers `playbooks.py`/`tasks.py` registrados + testes de API (CRUD, run dry_run, filtros, counts).
- [ ] Plugues inline atrás de flag OFF, best-effort (não muda os 235 testes).
- [ ] Frontend `/tarefas` + `/playbooks` + componentes extraídos + sidebar + tipos; `tsc` limpo.
- [ ] Suíte verde (235 + novos). Migration NÃO aplicada no Supabase (passo manual com OK).
