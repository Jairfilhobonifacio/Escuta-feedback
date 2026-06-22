# Spec do FRONT — Board reorder (Item C, parte 2/2)

> ## ✅ IMPLEMENTADO (branch `worktree-board-front-dnd`) — pendente SÓ QA visual do gesto
>
> O front (DnD) foi implementado, e o **backend foi re-arquitetado** durante a implementação
> porque a spec original tinha premissas falhas que 2 rounds de review adversarial (21 + 8
> agentes) expuseram. Estado atual:
>
> - **Backend:** `position` agora faz **snapshot da ordem visual COMPLETA** da coluna
>   (`_ordem_visual_coluna` + `_snapshot_card_order`), não mais inserção só-entre-manuais — o
>   GET devolve exatamente o que o front mostrou no drop (sem salto). Off-by-one unificado
>   front↔backend (ajuste `-1` só intra-coluna). Ordem determinística (desempate por id).
> - **Front:** reorder ativa só quando **`podeReordenar`** = board feedback `action_status`,
>   modo "padrão" (`ordUrg` off), sem "só urgentes", fora do Follow-up e **sem nenhum filtro
>   de servidor** — aí `fbCards === col.items` por construção, e índice/splice/position falam
>   da MESMA lista. Fora disso, o drag só move entre colunas (sem drop-line/position).
> - **Testes:** 10 em `tests/test_board_reorder.py` (off-by-one forward, "pro fim",
>   snapshot ordem-total, no-op); suíte 738 verde; tsc strict 0.
> - **Decisão de produto (a confirmar com o dono):** auto-ordenação por urgência e ordem
>   manual são **modos mutuamente exclusivos** — para reordenar à mão, troca-se o seletor de
>   "urgência" para "padrão". Reversível.
>
> ### ⚠️ Falta: QA VISUAL do gesto (com a stack no ar — `/escuta-stack`)
> Validar arrastando cards de verdade os 5 pontos no fim deste doc. NÃO deployar antes.
>
> ### 🧾 Dívida conhecida (LOW, documentada — não bloqueia)
> - **Órfãos em `board_card_order`** (#11/#2 do review): `action_status` muda por outras vias
>   (admin/tasks/webhook) e deletes não limpam o id do mapa JSONB. `_ordena_coluna` ignora
>   órfãos (não corrompe nada visível); é só crescimento de espaço no `settings`. Pré-existente.
> - **Cross-coluna em coluna com >30 cards** (#4): o front vê o top-30 e o backend posiciona na
>   lista completa; só desloca ~1 posição ao soltar abaixo do 30º card numa coluna gigante.
>   A correção robusta de ambos seria âncora-por-id (`before_id`) em vez de índice absoluto.
>
> ---
>
> **Histórico (spec original, parcialmente superada pelas correções acima):**
> Backend inicial no commit `f3e962e`. A spec abaixo descreve a 1ª versão do front; os
> passos seguem válidos como mapa, mas a lógica final difere (ver correções acima).

---

# SPEC CIRURGICA — Item C: Board Reorder (FRONT)

Arquivos: `frontend/app/board/page.tsx` e `frontend/lib/api.ts` (caminhos relativos a `C:\Users\jboni\Documents\Projetos\escuta\.claude\worktrees\escuta-board-reorder\`).

Pre-condicao: o backend ja deve aceitar `board_id` + `position` no `POST /api/feedbacks/{id}/board-move` e persistir ordem dentro da coluna. Esta spec assume isso pronto (item C backend). Se nao estiver, o front quebra silencioso (position ignorada).

Escopo desta spec: APENAS feedback (`moveFeedbackByDrop` / `BoardCard`). Os fluxos cliente/tarefa/melhoria ficam INTOCADOS — eles nao tem ordenacao manual.

---

## Passo 1 — Novo estado `overIndex`

Arquivo: `page.tsx`, ao lado das declaracoes de DnD existentes.

- **Local exato:** logo apos a linha 1512 (`const [overColumn, setOverColumn] = useState<string | null>(null);`).
- **Adicionar:**
  ```ts
  const [overIndex, setOverIndex] = useState<number | null>(null);
  ```
- Semantica: indice de INSERCAO 0-based dentro da coluna sob o cursor (0 = antes do 1o card; `N` = depois do ultimo). `null` = sem alvo (nao desenha a linha).
- Importante: `overIndex` so faz sentido pareado com `overColumn`. Sempre que `overColumn` for resetado para `null` (onDragLeave, onDragEnd, onColumnDrop), `overIndex` TAMBEM deve ir a `null`. Ver Passos 4, 8 e 9.

---

## Passo 2 — Calcular `overIndex` no `onDragOver` da coluna

Arquivo: `page.tsx`, handler `onDragOver` da `<section className="board-col ...">`, linhas 2268-2275.

- **Hoje** o handler so faz `preventDefault` + `dropEffect` + `setOverColumn(col.id)`.
- **Adicionar** ao corpo (depois do `setOverColumn`):
  1. Obter os elementos-card renderizados dentro da coluna. Forma cirurgica sem refs novas: dar um atributo de marcacao no wrapper de cada card e fazer query no `e.currentTarget`. O `<section>` (`e.currentTarget`) e a coluna; os cards estao dentro do scroll-body dela.
  2. Selecionar os cards: `const cards = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-board-card]"));`
     - REQUER marcar o `<article>` do `BoardCard` com `data-board-card` — ver Passo 7 (atributo, separado do drag handle). Adicione `data-board-card` no `<article>` em torno da linha 850-853 mesmo que nao implemente o GripVertical.
  3. Calcular o midpoint de cada card via `getBoundingClientRect()` e comparar com `e.clientY`:
     ```ts
     const y = e.clientY;
     let idx = cards.length;
     for (let i = 0; i < cards.length; i++) {
       const r = cards[i].getBoundingClientRect();
       if (y < r.top + r.height / 2) { idx = i; break; }
     }
     if (overIndex !== idx) setOverIndex(idx);
     ```
  4. Guard de re-render: so chamar `setOverIndex` se mudou (`overIndex !== idx`), espelhando o padrao ja usado para `overColumn` na linha 2273.
- **Por que `e.currentTarget`:** em `onDragOver` o `currentTarget` e estavel (a `<section>`); `e.target` varia por filho. Use sempre `currentTarget`.
- ⚠️ **QA VISUAL OBRIGATORIO** (calculo de midpoint): validar que arrastar para a metade SUPERIOR de um card retorna o indice DELE (insere antes) e metade INFERIOR retorna `idx+1` (insere depois). Testar tambem coluna vazia (`cards.length === 0` ⇒ `idx = 0`) e drop abaixo do ultimo card (`idx = cards.length`). Em colunas com scroll, confirmar que `getBoundingClientRect` (viewport-relative, igual a `clientY`) nao desalinha com a rolagem.

---

## Passo 3 — Linha divisoria de 2px no `overIndex` (feedback visual)

Arquivo: `page.tsx`, no `.map` de cards, linhas 2371-2389 (bloco `(fbCards ?? []).map(...)`).

- Objetivo: renderizar um separador de 2px ANTES do card cujo indice == `overIndex`, e um separador APOS o ultimo quando `overIndex === fbCards.length`.
- **So desenhar quando** `dropEnabled && overColumn === col.id && overIndex != null` — caso contrario nenhuma linha aparece (evita linha em coluna errada).
- Implementacao cirurgica: trocar o `.map` direto por um `.map` com indice e injetar o separador condicional. Esqueleto:
  ```tsx
  const showLine = dropEnabled && overColumn === col.id && overIndex != null;
  // ...
  {(fbCards ?? []).map(({ fb, extraCount }, i) => (
    <Fragment key={fb.id}>
      {showLine && overIndex === i && <div className="board-drop-line" />}
      <BoardCard ... />
    </Fragment>
  ))}
  {showLine && overIndex === (fbCards?.length ?? 0) && <div className="board-drop-line" />}
  ```
  - `Fragment` precisa ser importado de `react` (verificar se ja esta importado no topo; se nao, adicionar a `import { ... } from "react"`).
  - A `key` migra do `<BoardCard>` para o `<Fragment>`.
- CSS: definir `.board-drop-line` no mesmo arquivo de estilos do board (procurar onde `.board-col` / `.board-card` estao definidos — provavel `globals.css` ou CSS-module do board). Sugestao: `height: 2px; margin: 4px 0; border-radius: 1px; background: var(--accent, #ff5a3c);`.
- ⚠️ **QA VISUAL** (piscar): a linha deve aparecer onde o card vai cair e seguir o cursor suavemente; nao pode piscar/duplicar. Como `overIndex` so muda quando cruza um midpoint, o piscar e baixo, mas confirmar.

---

## Passo 4 — Reset de `overIndex` no `onDragLeave` da coluna

Arquivo: `page.tsx`, handler `onDragLeave`, linhas 2277-2284.

- **Hoje** so reseta `overColumn` quando o ponteiro sai de fato da `<section>` (guard `!e.currentTarget.contains(e.relatedTarget)`).
- **Adicionar** dentro do mesmo `if`, junto ao `setOverColumn(...)`:
  ```ts
  setOverIndex(null);
  ```
- Manter o guard `contains` — sem ele, mover entre cards dispara `dragleave` espurio e a linha some/pisca.

---

## Passo 5 — `moveFeedbackByDrop`: assinatura + decisao mesma-coluna vs cross-coluna

Arquivo: `page.tsx`, `moveFeedbackByDrop`, linhas 1670-1735.

### 5a. Assinatura — receber `toIndex`
- Linha 1671: trocar
  ```ts
  async (feedbackId: string, toColId: string) => {
  ```
  por
  ```ts
  async (feedbackId: string, toColId: string, toIndex: number | null) => {
  ```

### 5b. Early-return no-op (linhas 1689-1696) — DEIXAR DE RETORNAR quando ha reorder
- **Hoje** (linha 1694-1695): `else if (fromColId === toColId) return;` — bloqueia qualquer drop na mesma coluna. Isso e o que impede reordenar hoje.
- **Novo comportamento:**
  - `campo === "selo"`: manter o no-op atual (`if (card.selos.includes(toValor)) return;`) — selo nao tem ordem manual nesta entrega; reorder so vale para `action_status`. (Confirmar com backend se selo-boards terao ordem; se nao, sem mudanca aqui.)
  - `campo === "action_status"` e `fromColId === toColId` (mesma coluna): **NAO retornar** se houver intencao de reordenar. Calcular o indice atual do card e comparar com o destino; so retornar se for genuino no-op:
    ```ts
    } else if (fromColId === toColId) {
      // mesma coluna: reorder. So no-op se cair na mesma posicao.
      const colItems = toCol.items as Feedback[];
      const curIdx = colItems.findIndex((it) => it.id === feedbackId);
      const dest = toIndex ?? colItems.length;
      // soltar logo acima/abaixo da posicao atual = mesma posicao final
      if (dest === curIdx || dest === curIdx + 1) return;
    }
    ```
    - Racional do `curIdx`/`curIdx+1`: inserir no proprio indice ou no imediatamente seguinte resulta na mesma ordem apos o splice (porque o item sai antes de reentrar). Tratar ambos como no-op evita request inutil.
- Cross-coluna (`fromColId !== toColId`): segue como hoje (nao cai no `else if`, prossegue).

⚠️ **QA VISUAL:** confirmar que largar o card exatamente onde ja estava NAO dispara request (sem flicker) e que mover 1 posicao acima/abaixo dispara.

---

## Passo 6 — Reorder otimista com `splice` no lugar de `[moved, ...]`

Arquivo: `page.tsx`, bloco otimista `setItems`, linhas 1699-1723.

- **Hoje** (linha 1718) a coluna destino faz `items: [moved, ...colItems]` — sempre joga no TOPO. Isso ignora a posicao.
- **Mudanca:** inserir na posicao `toIndex`.

Tratar dois casos dentro do `.map` de colunas (linhas 1701-1721):

1. **Cross-coluna** (`campo === "action_status" && fromColId !== toColId`):
   - Coluna origem (linha 1703-1709): mantem (remove o card, decrementa count).
   - Coluna destino (linha 1710-1719): trocar `[moved, ...colItems]` por insercao posicional:
     ```ts
     const next = [...colItems];
     const at = toIndex == null ? next.length : Math.min(toIndex, next.length);
     next.splice(at, 0, moved);
     return { ...col, count: col.count + 1, items: next };
     ```

2. **Mesma coluna** (`campo === "action_status" && fromColId === toColId`):
   - **Atencao:** o branch atual de origem (linha 1703) REMOVE o card e o branch destino (linha 1710) tem guard `!colItems.some(it.id === feedbackId)` que IMPEDE reinserir — ou seja, na mesma coluna o codigo de hoje removeria sem readicionar. Como hoje a mesma-coluna era early-return (Passo 5b), nunca chegava aqui. Agora chega e precisa de um branch dedicado:
     ```ts
     if (campo === "action_status" && col.id === fromColId && fromColId === toColId) {
       const arr = colItems.filter((it) => it.id !== feedbackId);
       const at = toIndex == null ? arr.length : Math.min(toIndex, arr.length);
       // ajuste: se o destino estava depois da posicao removida, o indice "desliza" -1
       const curIdx = colItems.findIndex((it) => it.id === feedbackId);
       const finalAt = (toIndex != null && toIndex > curIdx) ? at - 1 : at;
       arr.splice(Math.max(0, finalAt), 0, card!);
       return { ...col, items: arr }; // count NAO muda
     }
     ```
   - Este branch deve vir ANTES dos branches de cross-coluna existentes (origem/destino) no `.map`, senao cai no branch de remocao (linha 1703) e o card some.
   - `count` NAO muda na mesma coluna.

⚠️ **QA VISUAL** (piscar otimista x refetch): hoje o `try` chama `boardsApi.move(...)` e DEPOIS `await loadItems(selected.id)` (linha 1726-1728), ou seja sempre refaz fetch. O reorder otimista vai mostrar a ordem nova e o `loadItems` confirma. Se a ordem otimista divergir da canonica (ex.: ordenacao secundaria do backend), havera um "salto" visivel. Validar visualmente que otimista == servidor. Se houver salto, considerar remover o `loadItems` do caminho de sucesso e confiar no otimista (fora do escopo desta spec — anotar como achado).

---

## Passo 7 — Drag handle `GripVertical` + atributo `data-board-card` no `BoardCard`

Arquivo: `page.tsx`, componente `BoardCard`, `<article>` linhas 850-861.

### 7a. `data-board-card` (OBRIGATORIO — usado pelo Passo 2)
- No `<article>` (linha 850-853), adicionar o atributo:
  ```tsx
  data-board-card
  ```
- Sem isso o `querySelectorAll` do Passo 2 retorna vazio e `overIndex` fica sempre `cards.length`.

### 7b. GripVertical (cue visual de "arrastavel")
- Dependencia confirmada: `lucide-react@^1.21.0` em `package.json` (linhas 10-19); `GripVertical` existe nessa versao.
- Import no topo do arquivo: `import { GripVertical } from "lucide-react";` (verificar se ja ha import de lucide; se sim, acrescentar ao destructuring existente).
- Renderizar um pequeno icone no canto do card (ex.: dentro do `<article>`, antes do `inner`), com `aria-hidden` e estilo discreto (`opacity: .4`).
- **Importante:** o card INTEIRO ja e `draggable` (linha 853). O GripVertical e so um CUE visual — NAO precisa ser o unico ponto de arrasto. Nao mover o `draggable`/`onDragStart` para o handle (manteria o card-todo arrastavel, comportamento atual).
- **Se por algum motivo o import falhar** (versao sem o icone): alternativa zero-dependencia — desenhar 6 pontinhos via `<span>⠿</span>` (U+2807) ou um pequeno SVG inline de 2 colunas x 3 pontos. Nao bloquear a feature por causa do icone.

---

## Passo 8 — `onColumnDrop`: repassar `overIndex` e resetar

Arquivo: `page.tsx`, `onColumnDrop`, linhas 1893-1910.

- **Capturar o indice ANTES de resetar.** Hoje (linha ~1896-1897) faz `setOverColumn(null); setDraggingId(null);`. Adicionar a captura e o reset:
  ```ts
  const dropIndex = overColumn === colId ? overIndex : null;
  setOverColumn(null);
  setDraggingId(null);
  setOverIndex(null);
  ```
  - Guard `overColumn === colId`: so usar o `overIndex` se ele foi calculado PARA esta coluna; senao passar `null` (insere no fim).
- Na chamada do feedback (linha que hoje e `void moveFeedbackByDrop(id, colId);`), passar o indice:
  ```ts
  void moveFeedbackByDrop(id, colId, dropIndex);
  ```
- NAO alterar as chamadas de `moveClienteByDrop` / `moveTarefaByDrop` / `moveMelhoriaByDrop` — fora do escopo.

---

## Passo 9 — `onDragEnd` dos cards: limpar `overIndex`

Arquivo: `page.tsx`, render do `BoardCard`, `onDragEnd` linhas 2377-2380.

- **Hoje:** `() => { setDraggingId(null); setOverColumn(null); }`.
- **Adicionar** `setOverIndex(null);`:
  ```tsx
  onDragEnd={() => { setDraggingId(null); setOverColumn(null); setOverIndex(null); }}
  ```
- (O `onDragEnd` da melhoria nas linhas 2364-2367 NAO precisa mudar — melhoria nao usa overIndex.)

---

## Passo 10 — Payload: `board_id` + `position` na API

### 10a. Tipo em `lib/api.ts`
Arquivo: `lib/api.ts`, `interface BoardMoveInput`, linhas 803-806.
- Adicionar dois campos OPCIONAIS (opcionais para nao quebrar os outros call-sites que so passam `campo`/`valor`):
  ```ts
  export interface BoardMoveInput {
    campo: BoardCampo;
    valor: string;
    board_id?: string;
    position?: number;
  }
  ```
- `boards.move` (linhas 1424-1425) NAO precisa mudar — ja repassa o `body` inteiro para `api.post(...)`.
- Confirmar com o contrato do backend o NOME exato do campo (`board_id` vs `boardId`, `position` vs `index`) — usar o que o backend espera; ler a rota `POST /api/feedbacks/{id}/board-move` no backend antes de fechar.

### 10b. Enviar no `moveFeedbackByDrop`
Arquivo: `page.tsx`, linha 1726 (`await boardsApi.move(feedbackId, { campo, valor: toValor });`).
- Trocar por:
  ```ts
  await boardsApi.move(feedbackId, {
    campo,
    valor: toValor,
    board_id: selected.id,
    position: toIndex ?? undefined,
  });
  ```
  - `selected.id` ja esta disponivel no escopo (guard na linha 1672 garante `selected` nao-nulo).
  - `toIndex ?? undefined`: se `null` (drop sem alvo), nao envia `position` e o backend usa default (append).

---

## Resumo dos pontos que EXIGEM QA VISUAL (manual, com o stack no ar)

1. **Calculo de midpoint (Passo 2):** metade superior insere antes / metade inferior insere depois; coluna vazia; drop abaixo do ultimo card; coluna com scroll.
2. **Linha divisoria (Passo 3):** aparece na coluna certa, segue o cursor, nao pisca nem duplica; aparece tambem no fim (`overIndex === length`).
3. **No-op da mesma posicao (Passo 5b):** largar onde ja estava NAO dispara request; mover 1 acima/abaixo dispara.
4. **Piscar otimista x refetch (Passo 6):** a ordem otimista (splice) bate com a ordem que volta do `loadItems`; sem "salto" perceptivel. Se saltar, anotar como achado (possivel remover `loadItems` do sucesso).
5. **Cross-coluna posicional:** largar no meio de outra coluna mantem o card no indice solto (nao no topo).

## Itens que dependem de confirmacao com o BACKEND antes de fechar
- Nome exato dos campos do payload (`board_id`/`position`) e se a rota persiste ordem.
- Se selo-boards terao reorder (esta spec mantem selo como no-op de ordem).
- Se o `loadItems` no caminho de sucesso deve permanecer (risco de salto visual no reorder).
