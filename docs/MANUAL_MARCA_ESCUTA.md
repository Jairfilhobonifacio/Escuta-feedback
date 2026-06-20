# Manual de Marca — Escuta

> **Escuta** é a central de Voz do Cliente no WhatsApp — by **Bizzu.**
> Tema **claro**, editorial e premium (referências mentais: Linear · Vercel · Monocle).
> Não é "dashboard de IA": é uma sala calma onde o gestor **bate o olho e entende**.

Este manual é a fonte de verdade visual do produto. Todos os valores aqui foram
**extraídos do código real** (`frontend/app/globals.css` + `frontend/app/layout.tsx`) —
nada é aspiracional. Se um token mudar no CSS, atualize aqui; as duas pontas têm de
contar a mesma história.

---

## 0. Essência e personalidade

| | |
|---|---|
| **Essência (1 frase)** | Escuta é a central que **transforma conversa de WhatsApp em decisão** para times que precisam ouvir o cliente sem virar planilha. |
| **3 atributos com tensão** | **Calmo** (não grita, não polui) · **Direto** (número grande, uma ideia por tela) · **Cuidadoso** (com a pessoa do outro lado e com o dado). |
| **Arquétipo** | Sábio (dominante — clareza, leitura, síntese) + Cuidador (tempero — acolhe quem reclama, fecha o loop). |
| **Referências nomeadas** | Painel da Linear (densidade calma) · tipografia da Vercel (preto-quase, mono em dados) · diagramação da Monocle (editorial, respiro). |
| **Anti-referência** | NUNCA parecer: gráfico de marketing colorido demais, "IA mágica" com gradiente arco-íris, dark-mode neon de fintech, ou planilha do Excel. |

**Princípio-mãe — "bato o olho e entendo":** se uma tela exige que o usuário pare para
decifrar, ela está errada. Hierarquia clara, um número-herói por bloco, cor só com função,
texto curto. O bonito aqui é consequência do claro, não enfeite.

---

## 1. Paleta — cores com PAPEL

A regra de ouro da marca: **cor é função, não decoração.** Indigo = estrutura/marca;
gold/âmbar = valor e número-herói; e o sentimento (promotor/neutro/detrator) é codificado
sem verde vivo, para coesão com a marca. **Nunca branco puro como fundo, nunca preto puro.**

> Convenção de papéis: os neutros são "tingidos" na direção do indigo (viés frio sutil),
> o que dá unidade subconsciente ao produto. As cores de texto sobre claro foram
> **escurecidas de propósito** para chegar perto do AA — por isso há um `gold` (texto) e
> um `gold-fill` (preenchimento) diferentes; não os troque.
>
> **Contrastes conferidos (WCAG 2.x, expoente 2.4) — leia antes de aplicar:** nem todo
> token de texto passa o AA estrito de 4,5:1. Os que ficam entre 3:1 e 4,5:1 são **"AA
> large"**: só os use em **≥14px com peso 600** ou em tamanho grande (título). Para texto
> pequeno crítico, escolha a variante mais escura indicada em cada tabela. Os valores nas
> colunas abaixo são os reais medidos, não os do comentário (otimista) do CSS.

### 1.1 Superfícies e neutros (o "papel" do produto)

| Token | Hex | Nome | Papel — quando usar |
|---|---|---|---|
| `--void` | `#f6f6fb` | Névoa | **Fundo principal** da aplicação (off-white com viés indigo). |
| `--ink` | `#eef0f7` | Trilho | Superfície base / trilhos de barra / fundo de campo / coluna de board (camada 1). |
| `--ink-800` | `#ffffff` | Carta | **Cards** — branco quase puro sobre o papel, só para leve elevação (camada 2). |
| `--ink-700` | `#eceef6` | Realce | Hover de linha/item, superfície elevada (camada 3). |
| `--charcoal` | `#e4e5f0` | Fio | **Bordas e divisores** padrão (hairline). |
| `--charcoal-2` | `#cfd0e0` | Fio forte | Bordas fortes, contorno de input/seletor, traços. |

Profundidade: a luz vem **de cima**. Card = borda `--charcoal` + sombra suave +
`--edge` (um hairline branco interno no topo). Nunca use sombra dura nem fundo branco
puro encostado em card branco — separe com `--ink` ou um fio.

### 1.2 Marca — Indigo

| Token | Hex | Papel — quando usar | Contraste |
|---|---|---|---|
| `--indigo` | `#6c5ce7` | A cor que **é** a marca: ícones ativos, faixa do item ativo, focus-ring, dots, **preenchimentos** (barras, gauge), botão sólido (texto branco). | sobre `#fff`: 4,86:1 ✅ (mesmo assim reservamos texto p/ `--indigo-light`) |
| `--indigo-deep` | `#5b4bcf` | Hover/ênfase; borda do botão; fim do gradiente de marca. | — |
| `--indigo-light` | `#5a49c9` | **Texto e acento de marca sobre fundo claro** (links, números promotor, rótulos indigo). Escurecido p/ AA. | sobre `#fff`: 6,50:1 ✅ · sobre `--ink`: 5,71:1 ✅ |
| `--indigo-glow` | `rgba(108,92,231,.16)` | Brilhos/halo: focus-ring, sombra colorida do brand-mark, fundo de coluna em drag. | — |

**DO ✅** texto indigo → sempre `--indigo-light`. Preenchimento (barra/dot/gauge) → `--indigo`.
**DON'T 🚫** usar `--indigo` puro como cor de texto de corpo (falha AA).

### 1.3 Valor — Gold / Âmbar

O gold marca **o que importa olhar**: o NPS-herói, o ponto da assinatura "Bizzu.", scores.

| Token | Hex | Papel — quando usar | Contraste |
|---|---|---|---|
| `--gold` | `#b3760a` | **Texto/ação âmbar grande** (NPS médio, label de score). | sobre `#fff`: **3,81:1 — AA large** (≥14px/600 ou maior) |
| `--gold-soft` | `#946105` | Gold mais escuro p/ **número-herói e texto âmbar pequeno** sobre claro. **Prefira este em texto.** | sobre `#fff`: 5,29:1 ✅ |
| `--gold-fill` | `#f5a623` | **Âmbar puro só p/ PREENCHIMENTOS**: barras, pontos, gradientes, o ponto da assinatura. | — (não usar como texto) |
| `--gold-glow` | `rgba(245,166,35,.16)` | Halo/fundo do item de destaque (Feedbacks), pílula de score. | — |

**DO ✅** número-herói NPS grande → `--gold-soft` (5,29:1); rótulo âmbar pequeno → `--gold-soft`; ponto "Bizzu**.**" → `--gold-fill`.
**DON'T 🚫** texto âmbar pequeno (<14px) em `--gold` (#b3760a só passa em tamanho grande); texto em `--gold-fill` (reprova).

### 1.4 Sentimento e indicadores (sem verde vivo)

A leitura de NPS/sentimento é codificada na própria família da marca — **positivo = indigo,
neutro = âmbar, negativo = vermelho dessaturado editorial.** Cada um tem 3 variantes:
texto (AA), `-soft` (fundo translúcido) e `-line` (borda translúcida).

| Papel | Texto (AA sobre claro) | Fundo `-soft` | Borda `-line` | Preenchimento |
|---|---|---|---|---|
| **Promotor / positivo** | `--indigo-light` `#5a49c9` | `--promoter-soft` | `--promoter-line` | `--promoter` `#6c5ce7` |
| **Neutro / passivo** | `--gold-soft` `#946105` | `--passive-soft` | `--passive-line` | `--passive` `#f5a623` |
| **Detrator / negativo** | `--detractor` `#cf4d4d` | `--detractor-soft` | `--detractor-line` | `--detractor` `#cf4d4d` |

`--detractor #cf4d4d` é vermelho **dessaturado** (editorial, não alarme): sobre `#fff` dá
**4,36:1 — AA large**, fica logo abaixo do 4,5 estrito. Por isso o produto sempre o aplica
em **peso 600** (badges, scores) ou em fill/borda; não o use em corpo fino e longo.

**Verde existe, mas é exceção controlada:** só em barras de Health Score em risco
(gradiente `--detractor → #eb9090`), no botão de WhatsApp (`#25d366`, cor da plataforma,
não da marca) e na barra de urgência baixa do board (`#3f9c66`). **Verde nunca é cor de
marca nem de "positivo"** — positivo é indigo.

### 1.5 Texto

| Token | Hex | Papel | Contraste sobre `#fff` |
|---|---|---|---|
| `--text` | `#1a1830` | Texto principal (quase-preto tingido de indigo, **nunca `#000`**). | 17,3:1 ✅ |
| `--text-dim` | `#56546b` | Texto secundário, descrições, corpo calmo. | 7,30:1 ✅ |
| `--text-faint` | `#82809a` | Rótulos (kicker/uppercase), metadados, captions. | 3,82:1 — AA large: só ≥14px/600 ou caps |
| `--text-ghost` | `#a9a7bd` | Placeholders, estados "nada aqui", desabilitado. | 2,35:1 — decorativo, nunca conteúdo essencial |

### 1.6 Gradientes de marca (preenchimento — cor viva permitida)

- `--grad-indigo` = `linear-gradient(135deg, #7c6cf0, #5b4bcf)` → botão primário, brand-mark, régua do título, barras indigo.
- `--grad-gold` = `linear-gradient(135deg, #f5a623, #e0930f)` → realces de valor.

Proporção nas telas (60-30-10): **~60%** papel/neutro · **~30%** tinta de texto + cards ·
**~10%** indigo/gold (acento). Se a cor de acento passar de ~10% da tela, está poluído.

---

## 2. Tipografia

Três famílias, cada uma com **um trabalho**. Carregadas via `next/font/google` (layout.tsx).

| Família | Variável | Pesos carregados | Trabalho |
|---|---|---|---|
| **Space Grotesk** | `--font-display` | 500 · 600 · 700 | **Títulos e nomes próprios**: título de página, nome de card/pessoa, brand-name, título de modal, avatar. Geométrica, com personalidade — carrega a marca. |
| **Inter** | `--font-body` | 400 · 500 · 600 · 700 | **Corpo e UI**: parágrafos, labels, botões, inputs, descrições. Neutra e legível — o cavalo de batalha. |
| **JetBrains Mono** | `--font-data` | 400 · 500 · 600 · 700 | **Todo dado verificável**: NPS, scores, contagens, telefones, percentuais. Sempre com `font-variant-numeric: tabular-nums` (números não "dançam"). |

**Regra dura:** número que o usuário pode conferir → **mono**. Nome/título → **display**.
Todo o resto → **Inter**. Duas exceções de tamanho gigante usam display para impacto
(gauge do NPS, valor herói), mas **dado tabular sempre em mono.**

### 2.1 Escala (valores reais do CSS)

| Papel | Família | Tamanho | Peso | Tracking |
|---|---|---|---|---|
| Título de página (`.page-title`) | display | `clamp(28px, 3.2vw, 38px)` | 700 | −1.4px |
| Valor-herói gauge (`.hero-gauge-val`) | display | 66px | 700 | −3px |
| NPS card-herói (`.kpi-nps .kpi-value`) | mono | 48px | 600 | −1.2px |
| KPI valor (`.kpi-value`) | mono | 32px | 600 | −1.2px |
| Título de modal / seção (`.modal-title`) | display | 18px | 700 | −0.4px |
| Nome de card/pessoa (`.fb-who`, `.tema-name`) | display | 14.5–16px | 600–700 | −0.3px |
| Corpo / feedback (`.fb-text`) | Inter | 14px | 400 | — |
| Texto secundário (`.page-sub`, `.section-sub`) | Inter | 12.5–14px | 400 | — |
| **Kicker / rótulo** (`.kpi-label`, `.lbl`) | Inter | 10.5–11px | 600 | **+1.1px, UPPERCASE** |
| Caption / meta (`.fb-when`, `.tl-when`) | Inter | 11.5–12px | 400–500 | — |

Piso de tamanho: **10.5px** e **só** em kicker uppercase 600 (`--text-faint`). Corpo nunca
abaixo de 13px. Linha de corpo: `line-height` 1.5–1.6.

### 2.2 Fallbacks (fora do navegador / fora desta máquina)

Nenhuma das três fontes está instalada no Windows (conferido). No app, o `next/font` resolve;
em peças geradas pelo design-studio nesta máquina, use os fallbacks:

- **Space Grotesk → Segoe UI** (impacto: Segoe UI Semibold/Black)
- **Inter → Segoe UI**
- **JetBrains Mono → Consolas** (ou Cascadia Code)

O stack já está nos tokens: `--font`, `--font-display`, `--mono` caem nesses fallbacks
automaticamente se o `next/font` falhar.

---

## 3. Gramática visual — os gestos proprietários

O que torna uma tela "Escuta" mesmo sem o logo. Use sempre ≥2 destes.

### 3.1 Cards
- **Raio:** `--radius` 16px (card), `--radius-sm` 11px (botão/input/chip-pílula), `--radius-xs` 8px (mini).
- **Borda:** 1px `--charcoal`. Borda forte (`--charcoal-2`) só em superfícies que pedem destaque (hero, modal, toolbar).
- **Sombra:** `--shadow` (suave, tingida de indigo, luz de cima) + `--edge` (hairline branco interno no topo). Hover → `--shadow-pop`, sobe 1–2px.
- **Fio de função no topo/lateral:** o card-herói (NPS) tem fio gold no topo (`::before` 2px gradiente gold→transparente). Cards de exceção ganham **barra lateral de acento** à esquerda (3px): indigo p/ "abordado"/ativo, vermelho p/ "dor a priorizar".
- DO ✅ card branco sobre papel névoa, fio de cor indicando função. 🚫 card branco direto sobre branco sem fio/sombra.

### 3.2 Chips e pílulas
- **Chip de tema:** retângulo `--radius-xs`, fundo `--ink`, borda `--charcoal`, texto `--text-dim`, contagem em mono `--indigo-light`.
- **Pílula de status/filtro:** `border-radius: 999px`, min-height 38–42px (hit-area), estado `.active` = fundo `--indigo` + texto branco.
- **Selo (chip colorido):** pílula 999px com `selo-dot` (7px) + contagem mono separada por fio interno. Cor configurável pelo usuário.
- **Chip tracejado = ação de adicionar** ("+ selo", "vincular"): borda `dashed`, hover indigo.
- DO ✅ pílula arredondada p/ navegação de estado; retângulo p/ rótulo/etiqueta. 🚫 misturar raios na mesma faixa.

### 3.3 Badges (sentimento, tipo, perfil)
- Retângulo `--radius` 7px, 11px/600, `-soft` + `-line` da família correspondente.
- Badge de **sentimento** tem `::before` = dot 7px na `currentColor` (indigo/âmbar/vermelho).
- Badge de **tipo** (NPS/Exit) é outline discreto (fundo transparente).
- DO ✅ badge sempre na trinca soft-fill/line/texto da mesma família. 🚫 badge com cor fora das 3 famílias de sentimento + neutro.

### 3.4 Dados e barras
- **Número-herói** sempre em mono, gigante, tracking negativo, cor por função (gold p/ NPS, indigo p/ promotor).
- **Barra/trilho:** altura 4–12px, `border-radius: 999px`, fundo `--ink` + borda `--charcoal`, preenchimento em gradiente da família (indigo p/ volume, gold p/ neutro, vermelho p/ dor/risco).
- **Gauge NPS:** arco SVG, track `--charcoal`, fill indigo com drop-shadow indigo, dot na ponta.
- **Régua de marca:** filete 2px gradiente indigo de 54px sob o título da página (assinatura).
- **Waveform** (assinatura "Escuta"): faixa de barras finas indigo a ~7% de opacidade no rodapé do hero — textura sutil que evoca "voz/áudio".

### 3.5 Estados
| Estado | Como se vê |
|---|---|
| **Hover** (card/linha) | sobe 1–2px, `--shadow-pop`, borda `--charcoal-2`; linha de tabela ganha fundo `--promoter-soft`. |
| **Focus** | sempre `--ring-indigo` (`0 0 0 3px` glow indigo) — nunca outline serrilhado do browser. |
| **Active/pressionado** | botão encolhe (`scale .985`), brilho reduzido. |
| **Disabled** | fundo `--charcoal`, texto `--text-ghost`, sem sombra, cursor `not-allowed`. |
| **Loading** | skeleton com shimmer (`--sk-base` + faixa de luz `--sk-sheen`) — troca "Carregando…" por estrutura. |
| **Vazio** | bloco `.empty` centrado: ilustração discreta em moldura circular tingida → título (display) → frase curta (`--text-faint`) → CTA opcional. **É aqui que entram os SVGs de empty-state.** |
| **Selecionado/ativo (nav, board-over)** | faixa/realce indigo (`--promoter-soft` ou `--indigo-glow`). |

### 3.6 Movimento
- Curva da casa: `--ease` `cubic-bezier(0.16,1,0.3,1)` (entradas/hover) e `--ease-out` para reveals.
- Conteúdo entra em cascata (`rise` 540ms, stagger por `nth-child`). Listas usam `.reveal`.
- **Tudo respeita `prefers-reduced-motion`** — sem exceção.

### 3.7 Assinatura "Bizzu."
A marca do fornecedor aparece como **"Bizzu."** com **o ponto final SEMPRE em `--gold-fill`**
(`.brand-by-dot`). O brand-mark do produto (sidebar) é um quadrado `--radius-sm` com gradiente
indigo + um **dot gold** no canto inferior direito (`.brand-mark-dot`). O ponto gold é a
menor unidade da marca — nunca o pinte de outra cor.

---

## 4. Tom de voz (PT-BR)

Como a Escuta fala. Três regras + microcopy.

1. **Próximo, nunca corporativo.** Fala com o gestor como um colega que já leu tudo por ele.
   Sem "prezado", sem "solicitação", sem jargão de produto.
2. **Curto e concreto.** Uma frase. Diz o que é e o que fazer. Número antes de adjetivo.
   Se cabe em 6 palavras, não use 12.
3. **Cuidadoso com a pessoa e honesto com o dado.** Quem reclamou é gente, não "detrator
   nº 4". E nunca inventa: se não há dado, diz que não há — não enfeita.

> Voz nos **estados vazios** (onde os SVGs vivem): acolhedora e orientada à ação, não
> "erro". O vazio é um convite, não uma falha.

### Microcopy — bom × ruim

| Contexto | ✅ Bom (na voz) | 🚫 Ruim (fora da voz) |
|---|---|---|
| Empty — Mapeamento | **"Nenhuma dor mapeada ainda."** Conforme os feedbacks chegam, agrupamos as dores aqui. | "Nenhum registro encontrado no sistema de classificação." |
| Empty — Melhorias | **"Nenhuma melhoria ainda."** Vire uma dor recorrente em melhoria e feche o loop. | "A lista de itens de roadmap está vazia (0 resultados)." |
| Sucesso — envio | **"Pronto — a pesquisa saiu."** Avisamos você quando a pessoa responder. | "Operação concluída com sucesso. Status: 200 OK." |
| Loop fechado | **"Você pediu, a gente fez."** Avisamos quem reclamou que isso mudou. | "Notificação de resolução enviada aos stakeholders impactados." |
| Detrator no inbox | "Nota 3 — vale uma conversa." | "DETRATOR. Ação corretiva requerida." |
| Erro de envio | "Não consegui enviar agora. Quer tentar de novo?" | "Falha na requisição. Erro interno." |
| Botão primário | "Enviar pesquisa" · "Virar melhoria" · "Fechar o loop" | "Submeter" · "Processar" · "Confirmar operação" |
| Confirmação destrutiva | "Apagar este feedback? Não dá pra desfazer." | "Tem certeza que deseja prosseguir com a exclusão?" |
| Renovação próxima | "Renova em 8 dias — fique de olho." | "Status de contrato: vencimento iminente." |

Convenções: **frase curta, ponto final** (combina com o ponto da marca). Verbo no
imperativo amigável nos CTAs ("Enviar", "Virar melhoria"). "Você/a gente", nunca "o usuário".
Números sempre por extenso só até dez quando NÃO são dado; dado é dígito em mono.

---

## 5. Preset de tokens (bloco para reuso no design-studio)

Cole este bloco em qualquer gerador/peça do estúdio para herdar a marca Escuta. Valores
**idênticos** ao `globals.css`. (Fontes: usar fallbacks da §2.2 fora do navegador.)

```
ESCUTA — design tokens (tema claro · by Bizzu.)

SUPERFÍCIES / NEUTROS
  void/fundo            #f6f6fb     (nunca #fff puro de fundo)
  ink/trilho            #eef0f7
  card                  #ffffff     (só card sobre o papel)
  realce/hover          #eceef6
  fio/borda             #e4e5f0
  fio-forte             #cfd0e0

MARCA — INDIGO
  indigo (fill/marca)   #6c5ce7
  indigo-deep (hover)   #5b4bcf
  indigo-light (TEXTO)  #5a49c9     (texto/links/acento sobre claro — AA)
  indigo-glow           rgba(108,92,231,.16)

VALOR — GOLD/ÂMBAR
  gold (texto GRANDE)   #b3760a     (3,81:1 = AA large; só ≥14px/600)
  gold-soft (TEXTO/nº)  #946105     (5,29:1 ✅ — preferir em texto âmbar pequeno)
  gold-fill (PREENCH.)  #f5a623     (barras/pontos/assinatura — nunca texto)
  gold-glow             rgba(245,166,35,.16)

SENTIMENTO (texto AA / fill)
  promotor/positivo     texto #5a49c9 · fill #6c5ce7
  neutro/passivo        texto #946105 · fill #f5a623
  detrator/negativo     texto #cf4d4d · fill #cf4d4d   (vermelho dessaturado)

TEXTO
  text                  #1a1830     (nunca #000)
  text-dim              #56546b
  text-faint            #82809a     (kicker/caption, ≥14px ou caps)
  text-ghost            #a9a7bd     (placeholder/disabled)

TIPOGRAFIA
  display  Space Grotesk 500/600/700   → títulos, nomes      (fallback Segoe UI)
  corpo    Inter 400/500/600/700       → UI, texto           (fallback Segoe UI)
  dados    JetBrains Mono 400–700      → números (tabular)   (fallback Consolas)

FORMA / PROFUNDIDADE
  raio                  16 / 11 / 8 px
  borda card            1px #e4e5f0 + hairline interno topo (edge)
  sombra card           0 1px 2px rgba(26,24,48,.05), 0 10px 28px -12px rgba(26,24,48,.14)
  focus-ring            0 0 0 3px rgba(108,92,231,.16)
  grad-indigo           135deg #7c6cf0 → #5b4bcf
  grad-gold             135deg #f5a623 → #e0930f
  ease                  cubic-bezier(0.16,1,0.3,1)

PROPORÇÃO   60% papel/neutro · 30% texto+card · 10% acento (indigo+gold)
PRINCÍPIO   "bato o olho e entendo" — cor só com função, 1 número-herói por bloco,
            frase curta com ponto final, ponto da marca sempre gold.
```

---

## 6. Auditoria rápida — "está na marca?"

Antes de aprovar uma tela/peça, marque:

- [ ] Fundo é névoa `#f6f6fb` (não branco puro)? Cards brancos com fio/sombra?
- [ ] Cor de acento (indigo+gold) ≤ ~10% da área? Nenhuma cor intrusa fora das famílias?
- [ ] Texto âmbar usa `--gold`/`--gold-soft` (não `#f5a623`)? Texto indigo usa `--indigo-light`?
- [ ] Número verificável está em **mono tabular**? Título/nome em **Space Grotesk**?
- [ ] Pelo menos 2 gestos presentes (fio de função · régua sob título · chip-pílula · número-herói · waveform · ponto gold)?
- [ ] Microcopy passa nas 3 regras de voz (próximo · curto · cuidadoso)? CTA é verbo amigável?
- [ ] Foco usa ring indigo; nada serrilhado; movimento respeita reduced-motion?

Falhou em 2+ → não está na marca. Corrija antes de polir detalhe.

---

*Extraído de `frontend/app/globals.css` e `frontend/app/layout.tsx` em 2026-06-20.
Ilustrações da marca em `frontend/public/illustrations/`. Preset espelhado no catálogo do
estúdio: `~/.claude/skills/design-studio/references/brand-presets.md`.*
