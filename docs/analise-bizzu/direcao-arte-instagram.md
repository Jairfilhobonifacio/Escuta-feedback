# Direção de Arte — a arte de concurso da Bizzu no Instagram

> Brief de direção de arte para melhorar o visual dos posts gerados pelo `bizzu_midia`.
> Pensado de fora pra dentro: público → intenção → tensão → princípios → passo a passo → código.
> Fontes: `relatorio-perfil-concurseiro.md` (ICP), `analise-mercado-instagram-concursos.md` (benchmark),
> `brand-guidelines-bizzu.html` (marca). Criado 2026-06-10.

## 1. Para quem (ICP) — e o que isso exige da arte
| Fato do público | Fonte | O que a arte tem que fazer |
|---|---|---|
| 25-39 anos, 50,9% mulheres, 78,6% com superior | `relatorio-perfil:12,17,27` | Adulto, sóbrio, sem infantilizar. Público exigente → estética de qualidade, não "panfleto". |
| Renda 1-3 SM, sensível a preço | `:32-34` | Mostrar valor/acessibilidade (R$ 20/120) sem parecer "barateza". |
| 51,9% já usam IA pra estudar | `:82` | A arte deve **sinalizar o DADO REAL** (600 mil questões reais) e a curadoria da Bizzu, é o diferencial. Não vender "IA" como buzzword. |
| Ansiedade, "não sei por onde começar", "excesso de material paralisa" | `:98-101` | A arte vende **alívio**: clareza, ordem, "comece por aqui". |
| Consome no celular, salva carrossel, descobre no grid de busca | `:194-197` + `analise-mercado:436` | **Legível em <1s no mobile**; primeiro slide pensado pro grid de busca. |
| Resolução de questões = método nº 1 | `:60` | Falar a língua: questões, prioridade, prova. |

## 2. O campo de batalha (benchmark) — onde a Bizzu ganha
- Os fortes (`@victorconcursos`, `@grancursosonline`, `@gurujaconcursos`) usam: **gancho de urgência** ("SAIU EDITAL"), **número grande** (vagas/salário/data), **texto alto contraste legível em 1 segundo** no grid (`analise-mercado:380-436`).
- Eles vencem a **atenção**. Mas entregam notícia/hype — **não conseguem entregar priorização real** (não têm o dado).
- **A jogada da Bizzu** (`analise-mercado:495`): *"saiu o concurso → aqui está o que importa → aqui está como começar"*. Vencer a atenção com a **linguagem do nicho** e entregar a diferença com a **inteligência (Raio-X)**.

## 3. A tensão central a resolver (o problema de design)
A marca Bizzu é **premium/editorial** (still life, luz fria, referências Linear/Vercel/Monocle — `bizzu_midia/prompts/_brand_soft.md`). O feed de concurso é **urgência + número gigante**. Se a arte for "bonita demais", **some no feed**; se for "panfleto", **mata a marca**. 
→ **Norte:** parar o scroll com a linguagem do nicho (gancho + número herói), mas com o acabamento da marca. Premium **e** legível.

## 4. Princípios de direção de arte (o norte de toda peça)
1. **1 slide = 1 ideia = 1 número herói.** Nada de slide lotado (o público já está sobrecarregado — `:100`).
2. **Regra dos 3 segundos / teste do squint:** desfoque a capa; se a mensagem-chave não sobrevive, refaça.
3. **Mobile-first:** o carrossel é 1080px exibido a ~393px (downscale 2,75×). Texto-corpo nunca < 30px no slide; herói 76-128px.
4. **Hierarquia brutal:** eyebrow → gancho → número herói → contexto → marca. O olho cai no número.
5. **Cor com função (não decoração):** ver §6.
6. **Honestidade da marca:** sem "grátis", sem "aprovação garantida", sem promessa; número sempre real; "Bizzu." com o ponto gold. (`brand-guidelines` + blocklist do guardian.)

## 5. Anatomia da capa (o slide 1 ganha ou perde 90% da batalha)
A capa é o que aparece no grid de busca e para (ou não) o scroll. Estrutura proposta:
```
┌─────────────────────────────────┐
│ Bizzu.   [ESTUDE O QUE IMPORTA]  │ ← marca (canto, pequeno)
│                                  │
│ EYEBROW: SAIU O EDITAL / RAIO-X  │ ← tipo de post (mono, gold)
│                                  │
│ GANCHO em 1 linha curta          │ ← Space Grotesk, grande
│ (a dor ou a oportunidade)        │
│                                  │
│      1.456        R$ 16 mil      │ ← NÚMERO HERÓI (JetBrains Mono,
│      vagas        salário        │    gigante, gold/branco)
│                                  │
│ Nome do Concurso · Banca         │ ← contexto (mono, menor)
│                          swipe › │
└─────────────────────────────────┘
```
- **Número herói** é o que para o scroll (vagas, salário OU "% prioritário" — o ângulo Bizzu).
- **Arte de fundo** entra como **fundo/textura sutil** atrás do número, não competindo com o texto (hoje o `08-artist` faz a capa ser arte-dominante; inverter: **texto/dado domina, arte ambienta**).

## 6. Sistema visual (cor, tipo, grid)
- **Cor por função:** `#09090B` fundo (foco no conteúdo) · **`#F5A623` gold = o número herói + a ação/CTA** (o que o olho deve achar) · **`#6C5CE7` indigo = marca/confiança/dado real** (selo "600 mil questões reais", molduras) · vermelho/laranja **só** para os níveis de prioridade do Raio-X (consistência com o PDF). Branco `#FAFAFA` texto.
- **Tipo:** Space Grotesk (gancho/headline) · JetBrains Mono (todo número, data, sigla — vira "assinatura de dado") · Inter (corpo). O **mono nos números** é o que faz parecer "dado real", não "post motivacional".
- **Grid:** margem segura, baseline consistente, um único ponto focal por slide.

## 7. Passo a passo (execução)
1. **Auditar o atual** — gerar 3 capas reais (1 cargo com salário alto, 1 com muitas vagas, 1 sem Raio-X) e aplicar o teste do squint. Marcar o que não sobrevive em <1s.
2. **Definir os 3 ganchos de capa** (alinha com a tese §2): `SAIU O EDITAL` (número = vagas/salário) · `RAIO-X` (número = % prioritário / nº de tópicos que importam) · `POR ONDE COMEÇAR` (número = "X tópicos = 80% da prova"). Cada um é um padrão de capa.
3. **Reescrever a anatomia da capa** (§5): inverter a relação texto×arte, dado domina, arte de fundo vira fundo. Definir a escala tipográfica mobile-first.
4. **Travar o sistema de cor por função** (§6) nos design tokens, gold = herói/ação, indigo = marca/dado.
5. **Padronizar os slides do meio:** slide do Raio-X (a barra de prioridade real, igual ao PDF) · slide "o que importa" (top matérias) · slide "como começar" (3 passos) · slide CTA (preço + bizzu.ai). 1 ideia cada.
6. **Selo de dado:** um micro-selo recorrente ("600 mil questões reais") em indigo, o diferencial é o DADO REAL e a curadoria da Bizzu (não "IA"), e ninguém no nicho mostra isso bem.
7. **Avatar/identidade recorrente** (opcional): um **objeto editorial** que se repete (não mascote humano — a marca proíbe stock/humano) para criar reconhecimento de feed.
8. **Validar no contexto real:** montar um mockup do **grid de busca** (9 posts) e do **feed**, comparar lado a lado com os concorrentes. Ajustar até a capa Bizzu "ganhar" o grid.

## 8. Como isso vira código no `bizzu_midia`
- **Capa:** `templates/slides/capa_hook.html` (estrutura) + `prompts/art/capa_hook.md` e `prompts/_brand_soft.md` (mudar a instrução do `08-artist` de "arte dominante" para "arte de fundo, texto/dado em primeiro plano").
- **Hooks de capa:** `agents/lib/hook-router.js` (os padrões A-H) — mapear pros 3 ganchos do passo 2.
- **Cor/tipo/tokens:** `templates/tokens.css` + `agents/lib/brand-constants.js` (cor por função).
- **Slides do meio:** `templates/slides/*.html` (numeros_do_edital, distribuicao_prioridade, raio_x_mockup…).
- **Teste:** `node agents/run-pipeline.js --cargo <id>` → revisar PNGs em `output/cargo/<slug>/`.

## 9. Métrica de sucesso
A capa passa se: (a) sobrevive ao **squint** (mensagem + número legíveis desfocado); (b) num **grid de 9**, o olho vai nela; (c) mantém "Bizzu." + paleta + mono nos números; (d) zero termo proibido. O resto do carrossel: cada slide entrega 1 ideia e o último converte (preço + bizzu.ai).

> **Limite honesto:** este brief é a *direção* (o que fazer e por quê). A escolha fina entre variações ("qual ficou mais bonita") é olho humano/seu. Eu opero a execução no `bizzu_midia` (templates + prompts) e gero as variações pra você julgar.
