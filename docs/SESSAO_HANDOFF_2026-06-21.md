# 🗓️ Sessão 2026-06-21 — Bugs residuais + P1-F + P2-I + polish do backlog

> **Projeto:** Escuta (Central de Voz do Cliente no WhatsApp) · `C:\Users\jboni\Documents\Projetos\escuta`
> **Continuação de:** `SESSAO_HANDOFF_2026-06-20_FEEDBACK_JORNADA.md`
> **Foco:** auditar o backlog do dono (`FEEDBACK_DONO_2026-06-20.md`), corrigir bugs residuais e
> implementar os itens de baixo risco. Tudo commitado **E pushed** para o GitHub.

---

## 🟢 Estado atual

| Serviço | Porta | Estado nesta sessão |
|---------|-------|---------------------|
| API FastAPI | 8000 | desligada (trabalho foi código + testes, não runtime) |
| Painel Next | 3001 | desligado |
| WAHA | 3000 | desligado |

- **Git:** branch `master` no commit **`a117914`**, **sincronizado com `origin/master`** (pushed).
  Remote: `github.com/Jairfilhobonifacio/Escuta-feedback`.
- **Worktrees:** limpos (4 criados e removidos nesta sessão; tudo já estava em `origin/master`).

---

## ✅ O que foi construído (6 commits, todos pushed)

| Commit | Entrega |
|--------|---------|
| `974c89a` | **5 bugs residuais** que o `f53d399` deixou passar: selos na tela **Feedbacks** migrados pro `SeloPopover` (portal — fim do "+selo fantasma" nesta tela); **Board lê `/api/config`** (status reais da org, não mais `novo/em_analise/planejado` que o backend não reconhece); **contagem do Board Follow-up** sincronizada com os cards dedupados; **status fantasma "novo"** na ficha → `a_abordar`; **flip vertical** do `SeloPopover`. tsc verde. |
| `2b43d49` | **P1-F** — ficha mostra **"Assinou em"** (`startedAt`) e **"Total pago"** (`totalPaidCentavos`). `sync_partner_customers.py::_build_partner_profile` passou a gravar `startedAt`/`planName`/`totalPaidCentavos` no snapshot (a API de Clientes já expunha, eram ignorados). Helper `fmtMoney` (BRL). tsc + `test_partner_profiles` 40/40. |
| `045a6e8` | **P2-I** — fila **"Quem abordar primeiro"** no Monitorar. Backend `GET /api/central/fila` (READ-ONLY; reusa `compute_health` da Fase 1 + a MESMA regra de "abordado" do overview; prioridade = `(100 - health) + min(silêncio, 60)`; **sem migration, sem cron**). Front: componente `FilaAbordar` (fetch próprio, degrada quando vazio) + `central.fila()` tipado. tsc + 3 testes novos (`test_central.py` 18/18). |
| `a117914` | **H** (excluir contato na **lista** `/clientes`: `ConfirmDialog` + `contacts.remove` + remoção local; o backend `DELETE /api/contacts/{id}` já existia, org-scoped + cascata) **+ G.3-A** (rota `/temas` → `/mapeamento`; `/temas` virou redirect p/ não quebrar bookmarks; Sidebar + link em Melhorias atualizados). tsc verde. |
| `cf0909b` | **G.3-B** — mapa de dores **2D** no `/mapeamento` (aba "Por significado", toggle **Cards / Mapa**). Componente `ScatterMap` (SVG inline, zero lib): Volume × Impacto com **quadrantes de ação** (ATACAR AGORA / VIGIAR / PLANEJAR / MONITORAR) + lista rankeada sincronizada no hover; fallback gracioso (sem `priority_index` cai em `pain_score`); clique → `/feedbacks?cluster_id`. **Projetado por workflow** (3 designs + judge) + **revisado adversarialmente** (4 lentes → 3 fixes: barra×número no fallback, Escape no scatter, foco visível WCAG). tsc verde. |
| `f3e962e` | **C (BACKEND)** — Board reordenar DENTRO da coluna. `board-move` aceita `position`/`board_id` OPCIONAIS; a ordem manual persiste em `Organization.settings["board_card_order"]` (**sem migration**); `_ordena_coluna` no GET (cards novos por **urgência no topo**, manuais abaixo na ordem salva); **fallback gracioso = nada regride**. **6 testes** (`test_board_reorder.py`) + 69 verdes sem regressão. **FRONT do DnD NÃO incluso** → spec de 10 passos em `docs/SPEC_BOARD_REORDER_FRONT.md` (exige QA visual). Projetado por workflow (corrigi bug do gerador: status `"novo"` inválido). |

(+ os 3 commits locais do dono que também subiram nesta sessão: `609e818` login-operador, `4e335b7` sentimento-PT-v2, `5a86b1b` skills.)

---

## 📊 Backlog do dono (`FEEDBACK_DONO_2026-06-20.md`) — real vs. feito

A auditoria (3 agentes) revelou que **o backlog estava muito desatualizado** — quase tudo já tinha sido entregue:

| Item | Estado real |
|------|-------------|
| B selos (P0) · D ficha (P0) | ✅ feito (`f53d399` + `974c89a`) |
| A Clientes: chips de canal (P1) | ✅ feito (`f53d399`) |
| E Pesquisas redesign (P1) | ✅ feito (nunca foi bug de styled-jsx) |
| F assinatura + status custom (P1) | ✅ feito (`2b43d49` + `974c89a`) |
| G.1/G.2 tipos/origem custom (P2) | ✅ feito (`/api/config` + tela `/config`) |
| J benchmark de CS (P2) | ✅ feito (`docs/BENCHMARK_CS_2026-06-20.md`) |
| H apagar dados (P2) | ✅ feito (ficha já tinha; **lista** agora em `a117914`) |
| I monitoramento inteligente (P2) | ✅ feito (fila em `045a6e8`) |
| **G.3-B** mapa de dores 2D (P2) | ✅ feito (`cf0909b`) |
| **C** Board reordenar intra-coluna (P1) | 🟡 **backend feito** (`f3e962e`, testado); **front DnD pendente** (`docs/SPEC_BOARD_REORDER_FRONT.md`, exige QA visual) |

---

## 🟡 Onde paramos / próximos passos

**Pendência técnica — ÚNICO item do backlog ainda aberto (front exige QA visual):**
1. **C — Board reorder. BACKEND FEITO E TESTADO** (`f3e962e`): `card_order` em `Organization.settings`
   (sem migration), `board-move` aceita `position`/`board_id`, `_ordena_coluna` no GET (novos por urgência no
   topo; manuais abaixo), fallback gracioso (nada regride até alguém arrastar). 6 testes + 69 verdes.
   **FALTA SÓ O FRONT (DnD)** — spec cirúrgica de 10 passos pronta em **`docs/SPEC_BOARD_REORDER_FRONT.md`**
   (`overIndex` por midpoint do `clientY`, linha divisória, splice otimista mesma-coluna vs cross, drag handle
   `GripVertical`, payload `position`/`board_id`). **Exige QA visual** (5 pontos: cálculo de midpoint, piscar
   otimista×refetch, no-op de mesma posição) — subir `/escuta-stack` e arrastar cards de verdade ANTES de
   considerar pronto/deployar. **Riscos de PRODUTO** já fixados no backend: truncamento em 30
   (`BOARD_ITEMS_PER_COLUMN` — reorder só no top-30 visível); ordem-manual sobrepõe urgência só nos cards
   tocados (novos urgentes ainda no topo); concorrência last-write-wins. Front ~3-4h com a stack no ar.

**Operacional (depende do usuário):**
3. **Validação visual** dos 5 commits desta sessão — não subi a stack (só `tsc` + `pytest`). Subir 8000/3001
   (skill `escuta-stack`) e conferir: selos em Feedbacks, ficha com assinatura, fila no Monitorar, excluir
   na lista, `/mapeamento` (toggle Cards / **Mapa** 2D; e `/temas` redirecionando).
4. **Re-sync** `scripts/sync_partner_customers.py` p/ popular `startedAt`/`totalPaidCentavos` nos contatos
   já existentes (a ficha só mostra os campos novos depois do sync). Precisa `BIZZU_PARTNER_API_KEY` e
   **toca o piloto** — rodar com OK explícito.
5. **Deploy** dos novos commits p/ prod (Modal API + Vercel painel) — não foi feito (skill `escuta-deploy`).

---

## 🔧 Como religar a stack
Use a skill **`escuta-stack`** (sobe 8000 / 3001 / 3000 + containers Podman). Não duplicar comandos aqui.

---

## ⚠️ Pegadinhas (novas desta sessão)
- **Worktree em background-job parte de `origin/master`** (baseRef "fresh"), não do `master` local — se houver
  commits locais não-pushed, fazer `git merge --ff-only master` no worktree ANTES de editar (senão regride no
  merge). Depois do 1º push, os worktrees seguintes já nasceram corretos.
- **`node_modules` não existe no worktree** (gitignored). Para rodar `tsc`, criar junction
  `New-Item -ItemType Junction` apontando pro `node_modules` do checkout principal — e **removê-lo com
  `[System.IO.Directory]::Delete($link, $false)`** (NUNCA `Remove-Item -Recurse`, que seguiria o junction e
  apagaria o `node_modules` REAL do checkout principal).
- **Backlog do dono estava muito desatualizado:** vários itens "abertos" já estavam implementados — **sempre
  verificar no código antes de implementar**. Os agentes de planejamento erraram 2× afirmando que algo não
  existia (o `DeleteContactModal` da ficha e a migração de selos) quando existia; a leitura direta corrigiu.

---

## 🔁 Sessão 2026-06-21 (cont.) — Board reorder (Item C): FRONT + re-arquitetura do BACKEND

**Branch:** `worktree-board-front-dnd` (a partir de `origin/master`=`99b8857`). **NÃO deployado.**
Trabalho guiado por **2 rounds de review adversarial** (Ultracode: 21 + 8 agentes) — foi o que
salvou a feature, que tinha premissas falhas na spec original.

**O que mudou (5 arquivos, ~300 linhas):**
- **`app/api/boards.py`** — `position` deixou de inserir "só entre manuais" (que jogava o 1º card
  reordenado pro FIM = salto garantido) e passou a fazer **snapshot da ordem visual COMPLETA**
  (`_ordem_visual_coluna` + `_snapshot_card_order`): o GET devolve exatamente o que o front mostrou.
  **Off-by-one unificado** front↔backend (ajuste `-1` só intra-coluna, via `status_antigo==valor`).
  **Ordem determinística** (desempate `(-urgencia, id)`) em `_items_action_status` e no snapshot.
- **`frontend/app/board/page.tsx`** — DnD com `overIndex` (midpoint), `.board-drop-line`, splice
  posicional + no-op de mesma-posição. Guard **`podeReordenar`**: só reordena quando
  `fbCards === col.items` é garantido (action_status, modo "padrão", sem "só urgentes", fora do
  Follow-up, **sem filtro de servidor**). Fora disso, drag só move entre colunas.
- **`frontend/lib/api.ts`** — `BoardMoveInput` ganhou `position?`/`board_id?`.
- **`frontend/app/globals.css`** — `.board-drop-line`.
- **`tests/test_board_reorder.py`** — 10 testes (off-by-one forward, "pro fim", snapshot, no-op).

**Verificação:** tsc strict 0 · suíte **738 verde** · 2 rounds de review → **0 HIGH / 0 MEDIUM abertos**.
13 achados do round 1 + 4 do round 2: 15 corrigidos por construção, 2 LOW viraram dívida.

**Decisão de produto tomada (REVERSÍVEL — confirmar com o dono):** "ordenar por urgência" e ordem
manual são **modos mutuamente exclusivos**. Para reordenar à mão, o seletor vai de "urgência" →
"padrão". Justificativa: não dá pra ter auto-ordenação por urgência E ordem manual ao mesmo tempo.

**⚠️ Falta SÓ o QA visual do gesto** (arrastar cards de verdade com a stack no ar). A LÓGICA está
correta-por-construção + testada; o GESTO não foi validado (bg-job não faz QA visual confiável de
HTML5 drag). Ver os 5 pontos em `docs/SPEC_BOARD_REORDER_FRONT.md`.

**Dívida LOW conhecida (não bloqueia):** (1) órfãos em `board_card_order` — `action_status` muda por
outras vias e deletes não limpam o mapa JSONB; `_ordena_coluna` ignora órfãos (não corrompe), é só
crescimento de espaço; pré-existente. (2) cross-coluna em coluna >30 cards desloca ~1 posição. A cura
de ambos seria âncora-por-id (`before_id`) em vez de índice — fica para uma próxima iteração.

---

## 🔑 Refs rápidas (sem valores de segredo)
| Item | Valor / Caminho |
|------|-----------------|
| Repo | `github.com/Jairfilhobonifacio/Escuta-feedback` (branch `master` = `origin/master`) |
| Prod API | Modal (app `escuta-api`, secret `escuta-prod`) |
| Prod painel | Vercel (projeto `escuta-feedback`) |
| Endpoint novo | `GET /api/central/fila` — fila "quem abordar primeiro" (risco × silêncio) |
| Rota renomeada | `/temas` → `/mapeamento` (a antiga redireciona) |
| Re-sync assinatura | `scripts/sync_partner_customers.py` (precisa `BIZZU_PARTNER_API_KEY`) |
