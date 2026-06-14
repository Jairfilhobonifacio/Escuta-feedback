# Handoff — Sessão 2026-06-14 (Escuta × Bizzu) — Fase 2: Playbooks & Automação

> Continuação do `ROADMAP_CS.md`. A **Fase 2** (motor gatilho→ação + fila de Tarefas de CS) foi
> implementada via 2 ondas de agentes (4 exploração + 2 implementação) e **VALIDADA AO VIVO no piloto**.

---

## 1. O que foi feito

### 🤖 Motor de Playbooks — `app/domain/cs/engine.py`
`run_playbooks(session, org_id, *, triggers, dry_run=True, messaging, now)`: 5 gatilhos
(`nps_detractor`, `health_at_risk`, `inactive_days`, `renewal_soon`, `churn_detected`) → 2 ações
(`create_task`, `alert_owner`). Avaliação por comparação de chaves (**sem `eval`**), idempotente por
`dedup_key = "{trigger}:{contact}:{YYYY-MM}"`, reusa `compute_health` (Fase 1). `dry_run=True` não grava.

### 🗃️ Dados — `app/models/playbook.py` + `alembic/versions/20260613_playbooks_cs_tasks.py`
Tabelas `playbooks` (regra) e `cs_tasks` (fila). JSONB livre p/ `trigger_config`/`action_config`/`meta`.
Índices parciais Postgres-only só na migration; UNIQUE `(org, dedup_key)`. **Aplicada no piloto** (head).

### 🔌 API — `app/api/playbooks.py` + `app/api/tasks.py` (registrados em `main.py`)
CRUD `/api/playbooks` + `POST /api/playbooks/run?dry_run=` + fila `/api/tarefas` (filtros status/owner/
priority, `sort`, `counts_by_status`, `health`/`health_band` recomputados inline).

### 🖥️ Painel — `frontend/app/tarefas/` + `frontend/app/playbooks/`
`/tarefas` = fila priorizada (Cliente, Saúde, Motivo, Playbook, SLA, Status, botão **WhatsApp** reusando
o modal "Abordar"). `/playbooks` = CRUD de regras (`.two-col`). Componentes extraídos para `components/`
(`Modal`, `ConfirmDialog`, `AbordarModal`, `HealthCell`). Sidebar com 8 itens.

### 🔒 Plugues inline (atrás da flag `PLAYBOOKS_INLINE_ENABLED`, default **OFF**, best-effort)
`resolver.py` (detrator fecha → `nps_detractor`) e `events.py` (`subscription_cancelled` → `churn_detected`).
Com a flag off, comportamento idêntico ao anterior (os 235 testes originais seguem verdes).

### 📄 Spec: `docs/FASE2_PLAYBOOKS_SPEC.md`.

---

## 2. Validado AO VIVO no piloto (14/06)
- Migration aplicada → head `20260613_playbooks_cs_tasks`. API `:8000` + painel `:3001` no ar.
- 3 playbooks criados. Motor **dry-run** → **87 candidatos** (3 detrator + **60 risco** + 24 churn; o "60"
  bate com a Fase 1). **Wet** → 87 `CsTask` criadas. **Re-run** idempotente → 0 criadas, **63 puladas**.
- QA visual de `/tarefas` e `/playbooks` (Playwright) — render com dados reais, **0 erro de console**.
- **265 testes** verdes · `tsc` 0 · **0 WhatsApp disparado**.

## 3. Estado
- Migration **aplicada no piloto**. **87 `CsTask` reais** (status `aberta`) na fila — contas que de fato
  merecem abordagem (detratores/risco/churn).
- Commit: código limpo da Fase 1+2 versionado. **Cluster de churn fora do git** por conter PII
  (`scripts/export_churn.py` tem telefones; `docs/campanhas/analise-churn.md` e `mensagens-churn-mensal.md`
  no `.gitignore`).

## 4. Próximos passos
1. **Automatizar**: cron externo (Modal/n8n) → `POST /api/playbooks/run` 1×/dia (igual ao digest).
2. **Tempo real**: ligar `PLAYBOOKS_INLINE_ENABLED=true` após calibrar (detrator/churn viram tarefa na hora).
3. **Alerta ao dono**: criar playbook `action_type=alert_owner` (avisa no WhatsApp do `owner_phone`).
4. **Higiene**: limpar a PII de `scripts/export_churn.py` para poder versioná-lo.

## 5. Como retomar
`/escuta-stack` (sobe 8000/3001) · `/bizzu-escuta` (contexto). Ler `FASE2_PLAYBOOKS_SPEC.md`,
`ROADMAP_CS.md` e este handoff. Regra de ouro: Bizzu = leitura; Escuta = código; WhatsApp real só com OK.
