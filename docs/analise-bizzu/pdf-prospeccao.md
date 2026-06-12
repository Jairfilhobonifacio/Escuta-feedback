# Gerador de PDF de Prospecção da Bizzu (`bizzu_midia`) — Anatomia + Melhorias

> Análise técnica do "Relatório de Raio-X da Prova" em PDF que a Bizzu usa como peça de prospecção.
> Raiz analisada: `C:\Users\jboni\Documents\Projetos\bizzu_midia`.
> Lido de verdade: `lib/report-pdf.js`, `lib/report-utils.js`, `lib/bizzu-api.js`, `server.js` (rotas `/api/relatorios/*`), `templates/slides/*` e o doc estratégico `relatorio-perfil-concurseiro.md`.
> Um PDF de exemplo foi **gerado de verdade** (ver seção F). Nada aqui é inventado: números de exemplo vêm da API real.

---

## A. ANATOMIA DO PDF ATUAL

### A.1. Visão geral

O PDF é construído 100% em HTML/CSS inline dentro de `lib/report-pdf.js` (função `buildReportHtml`, `report-pdf.js:372`). **Não usa nenhum dos templates de `templates/slides/*.html`** — esses são do pipeline de carrossel do Instagram. O relatório é um documento próprio, A4 retrato (`@page { size: A4; margin: 0; }`, `report-pdf.js:486`), gerado por cargo.

Cada "página" é uma `<section class="page">` com `width: 210mm; height: 297mm` e `page-break-after: always` (`report-pdf.js:491`). O número de páginas é **variável** (no exemplo gerado deram 18) porque a seção de "Top tópicos por matéria" emite uma página por matéria elegível.

### A.2. Seções (ordem real do build, `report-pdf.js:400-474`)

| # | Seção | Função geradora | Dados que entram |
|---|-------|-----------------|------------------|
| 01 | **Capa** | inline `report-pdf.js:403-425` | `edital_nome`, `cargo_nome`, 4 métricas: nº matérias, `totalTopicos`, `highTotal` (+`highPercent`), `salario`; source-strip com órgão/banca |
| 02 | **Dados do concurso** | inline `report-pdf.js:428-445` | grid 2col de 8 "facts": Edital, Órgão, Banca, Cargo, Área, Escolaridade, Remuneração, Ano (`facts[]` em `report-pdf.js:389-398`) |
| 03 | **O que faz esse cargo** (condicional) | `pageCargoOverview` `report-pdf.js:188` | `atribuicoes` (split por `\n`/`;`, até 10 itens) + `formacao`. **Pulada se não houver atribuições** (`report-pdf.js:190`) |
| 04 | **Distribuição da prova** | `pagePriorityDistribution` `report-pdf.js:170` | `stats` (contagens por prioridade) → barra empilhada de 5 cores + legenda; micro-helper com `%` de MUITO ALTA+ALTA |
| 05 | **Matérias por densidade** | `pageMateriasDensity` `report-pdf.js:277` | top 8 matérias por `densityHigh` (= (MA+ALTA)/total, só matérias com ≥3 tópicos) |
| 06 | **Matérias por volume** | `pageMateriasVolume` `report-pdf.js:208` | top 8 matérias por `zonaAtaque` absoluto (MA+ALTA) |
| 07..N | **Top tópicos por matéria** (1 página/matéria) | `pageTopicsBySubject` `report-pdf.js:247` | 3 tópicos visíveis por matéria (MA→ALTA, por rank) + até 2 cards "trancados" (`lockedTopicCard`) com CTA "Disponível em bizzu.ai" |
| N+1 | **Como a Bizzu te ajuda** (6 produtos) | `pageProductContextualized` `report-pdf.js:304` | texto estático: Raio-X, Bizzu do Tópico, Plano de Estudos, Questões Selecionadas, Comentário da Bizzu, Caderno do Tópico |
| N+2 | **CTA / Pricing** | `pageCta` `report-pdf.js:329` | 3 pilares + preços `R$ 20`/mês e `R$ 120`/ano + `launch-flag` "R$ 10/mês · 50% off" + link `https://www.bizzu.ai` |

### A.3. De onde vêm os dados (API Bizzu)

Tudo entra por dois endpoints, via `lib/bizzu-api.js`:
- `getCargoDetails(id)` → `GET /leads/concursos/{id}` (`bizzu-api.js:35`)
- `getCargoRaioX(id)` → `GET /leads/concursos/{id}/raio-x` (`bizzu-api.js:39`)

Disparados em paralelo em `generateCargoReport` (`report-pdf.js:769-772`). Auth por header `X-API-Key` lido de `process.env.BIZZU_API_KEY` (`bizzu-api.js:4,17`); timeout 10s (`bizzu-api.js:5,14`).

**Shape real de `details`** (confirmado no `api-data.json` do exemplo gerado): `edital_cargo_id, edital_id, edital_nome, edital_ano, banca_nome, orgao_nome, cargo_nome, cargo_area, escolaridade, salario, atribuicoes, formacao, data_prova`.

**Shape real de `raio_x`**: `{ materias: [{ materia_id, materia_nome, materia_categoria, topicos: [{ ecmt_id, topico_id, topico_nome, prioridade, justificativa, rank? }] }], stats: { total_materias, total_topicos, muito_alta, alta, media, baixa, muito_baixa } }`.

O processamento (de `details`+`raio_x` para as estruturas que as páginas consomem) está em `lib/report-utils.js`, função `buildReportAnalysis` (`report-utils.js:187`):
- `flattenTopics` (`:76`) achata todos os tópicos, normaliza prioridade (`displayPriority` `:20`), extrai "claim de questões" da justificativa via regex `\d+\s+quest(ões|oes)` (`extractQuestionClaim` `:57`).
- `buildMateriaRows` (`:98`) conta prioridades por matéria e computa `zonaAtaque` (MA+ALTA) e `score` (pesos 5/4/3/2/1).
- `rankByDensity` (`:163`) / `rankByVolume` (`:183`) ordenam matérias.
- `buildTopicsBySubject` (`:122`) seleciona 3 tópicos visíveis por matéria, conta `locked = total - visible`.

### A.4. Validações — `validateReportCopy` (`report-pdf.js:645`)

Roda **depois** de montar o HTML e **antes** de renderizar (`report-pdf.js:790`). Faz duas checagens sobre o HTML inteiro (normalizado em NFD + lowercase para ignorar acento, `report-pdf.js:661`):

**Termos PROIBIDOS** (`forbiddenTerms`, `report-pdf.js:648-659`) — se algum aparecer, lança erro e aborta a geração:
```
'aprovação garantida' / 'aprovacao garantida'
'método infalível'    / 'metodo infalivel'
'últimas vagas'       / 'ultimas vagas'
'gratuito'
'grátis'
'concentram'
'dominam o edital'
```
(Os dois últimos são o veto explícito do usuário ao framing "X matérias concentram Y% do edital" — ver `CLAUDE.md`.)

**Termos OBRIGATÓRIOS** (`requiredTerms`, `report-pdf.js:666-674`) — se algum faltar, lança erro:
```
'Raio-X da Prova', 'Bizzu do Tópico', 'prioridade real',
'questões reais', 'bizzu.ai', 'R$ 20', 'R$ 120'
```

Nota importante no código (`report-pdf.js:646`): em-dash/en-dash são **permitidos** no PDF (ao contrário dos carrosséis) porque dados crus da API trazem esses caracteres e bloquear quebraria a geração. Ou seja, a regra anti-travessão da marca vale para texto autoral, não para os dados da API que passam por `escapeHtml`.

---

## B. COMO É GERADO (pipeline Playwright HTML→PDF)

### B.1. Endpoint / fluxo do job (`server.js`)

O "Relatório Studio" é uma UI local (`public/relatorios.html` + `.js` + `.css`, servida em `http://localhost:3000/relatorios.html`, `server.js:1045`). Rotas em `server.js`:

| Rota | Método | Handler | O que faz |
|------|--------|---------|-----------|
| `/api/relatorios/cargo?id=` | GET | `handleReportCargoPreview` `server.js:233` | preview leve (sem PDF) via `buildReportPreview` |
| `/api/relatorios/generate` | POST | `handleReportGenerate` `server.js:250` | enfileira job (até 5 cargos/vez), responde `202 {jobId}` |
| `/api/relatorios/status?jobId=` | GET | `handleReportStatus` `server.js:306` | polling de progresso (`step`, `ranSteps`, `result`, `error`) |
| `/api/relatorios/file?path=` | GET | `handleReportFile` `server.js:323` | serve PDF/PNG/HTML com guard anti-path-traversal (`isInsideDir` `server.js:192`) |
| `/api/relatorios/history` | GET | `handleReportHistory` `server.js:343` | lista relatórios já gerados em `output/relatorios/` |

**Padrão de job assíncrono** (`server.js:265-303`): a geração leva tempo (Playwright), então o POST cria um `job` num `Map` em memória (`reportJobs`, `server.js:190`), dispara um IIFE async, e o cliente faz polling no `/status`. Jobs expiram em 1h (`cleanupReportJobs` `server.js:226`). Validações de input: IDs precisam ser UUID (`isUuid`), máx. 5 por job (`server.js:262-263`). **Estado é só em memória** — reiniciou o server, perdeu os jobs (mas os arquivos ficam em disco).

`onProgress` reporta 4 steps: `fetch → analysis → html → render` (`report-pdf.js:768,775,788,793`).

### B.2. Renderização (`renderReportPdf`, `report-pdf.js:715`)

Pipeline de **dois passes** com Playwright/Chromium headless:

1. **Pass vetorial**: escreve o HTML em disco, abre no Chromium (`viewport 1240×1754, deviceScaleFactor 2`, `report-pdf.js:725`), espera `networkidle` (fontes Google Fonts carregam de rede!), gera `*-vector-source.pdf` via `page.pdf({ preferCSSPageSize: true, printBackground: true })` (`report-pdf.js:727`).
2. **Screenshot por página**: para cada `.page`, tira screenshot PNG `preview_page_NN.png` (`report-pdf.js:733-739`).
3. **Pass "flat" (rasterizado)**: monta um segundo HTML (`buildFlattenedPdfHtml` `report-pdf.js:685`) onde cada página é um `<img>` do PNG, e gera o **PDF final** desse HTML (`report-pdf.js:743-749`). Esse flat HTML injeta um único hotspot clicável `<a class="hit assinatura">` na última página apontando para `https://www.bizzu.ai` (`report-pdf.js:698,708`).

**Saídas** (no exemplo gerado, `report-pdf.js:752`): `*.html` (76 KB), `*-flat.html` (4.5 KB), `*-vector-source.pdf` (1.8 MB, texto selecionável), `*.pdf` (8.1 MB, raster), 18× `preview_page_NN.png`, e `api-data.json` (snapshot da API, `report-pdf.js:781-785`).

**Decisão de design crucial:** o PDF "oficial" entregue é o **raster (flat)**, não o vetorial. Vantagem: fidelidade pixel-perfect (nenhum risco de fonte faltando/quebra de layout no leitor de PDF do destinatário). Custo: **8.1 MB** vs 1.8 MB, texto não-selecionável, não-acessível, sem SEO/copy-paste. Para prospecção por e-mail/WhatsApp, 8 MB é pesado.

### B.3. Cargo / qual endpoint da API

A geração é por **cargo** (`edital_cargo_id`, um UUID), não por edital. A lista de IDs disponíveis vem de `GET /leads/concursos/available` (`bizzu-api.js:31`, `listAvailableConcursos`), que retorna 118 editais / 184 cargos hoje. O `flattenConcursos` (`bizzu-api.js:43`) expande para a lista de cargos com label legível.

---

## C. PROPOSTAS DE MELHORIA CONCRETAS (para prospecção)

Cada proposta indica **onde mexer** (arquivo:linha). Prioridade: 🔴 alto impacto / 🟡 médio / 🟢 polimento.

### C.1. 🔴 Página de "Perfil do Concurseiro" (usar `relatorio-perfil-concurseiro.md`)

**Por quê:** o PDF hoje fala 100% de *dados da prova* e 0% do *humano que vai estudar*. O doc estratégico tem munição pronta para criar empatia e ancorar a venda nas dores. Numa peça de prospecção (que muitas vezes é lida por um decisor de marketing/parceria, não pelo concurseiro), mostrar que a Bizzu **entende o público** é diferencial.

**O que adicionar:** uma página nova entre a 03 (cargo overview) e a 04 (distribuição), tipo `pagePerfilConcurseiro(meta)`, com 3-4 blocos retirados do doc:
- **A dor**: "Não sei o que estudar primeiro" / "Excesso de material paralisa" (`relatorio-perfil-concurseiro.md:98-101`). Conecta direto com o Raio-X.
- **Dado de comportamento**: "51,9% dos concurseiros já usam IA na preparação" (`:82`), "média de 2 anos de preparação" (`:54`), "resolução de questões é o método nº 1" (`:60`). Posiciona a Bizzu como a ferramenta certa para esse público.
- **Persona**: opcionalmente um card "Ana, a Concurseira Determinada" (`:381-393`) — mas para prospecção B2B talvez melhor manter como estatística agregada, sem a persona ficcional.

**Onde mexer:**
- Nova função em `lib/report-pdf.js` (modelo: `pageCargoOverview` em `report-pdf.js:188`). Os estilos já existem (`.attr-list`, `.note-box`, `.intro`).
- Inserir no build em `report-pdf.js:452` (logo após o `cargoOverview`), com `next()`.
- **Cuidado com a validação**: o doc usa "gratuito"/"grátis" e "aprovação garantida" (`:154,241,375`). Esses termos estão na blocklist (`report-pdf.js:648`). **Não copie literal** — parafraseie. Ex.: "garantia de satisfação" em vez de qualquer coisa com "garantida".
- Os números aqui são de pesquisa de mercado (Censo), não da API Bizzu — então cite a fonte ("Censo dos Concursos 2025") para não violar a regra "números sempre reais da API". É legítimo desde que rotulado como dado de mercado, não de plataforma.

### C.2. 🔴 Seção de ROI (aprovação vale R$X vs Bizzu R$20/mês)

**Por quê:** é o argumento de venda mais forte e hoje **não existe** no PDF. O dado já está na mão: o `salario` do cargo (no exemplo, R$ 16.458,70/mês). O CTA mostra só o preço da Bizzu (R$ 20/R$ 120) sem ancorar contra o valor da aprovação.

**O cálculo (honesto, sem prometer aprovação):**
- Remuneração anual do cargo = `salario_mensal × 13` (13º). No exemplo: ~R$ 213 mil/ano.
- Investimento Bizzu = R$ 120/ano.
- Frame: "O cargo paga R$ 16.458/mês. A preparação completa na Bizzu custa R$ 120 no ano — menos de 1% de um único salário do cargo." E cruzar com o doc: o concurseiro médio investe **R$ 2.011/ano** em preparação (`relatorio-perfil-concurseiro.md:116,163`) — a Bizzu a R$ 120 é ~6% disso.

**Onde mexer:**
- Nova função `pageRoi(meta)` em `lib/report-pdf.js`, inserida antes do CTA (em `report-pdf.js:473`). Reusar `.metric` / `.price-card`.
- **Parsing do salário é obstáculo real**: hoje `meta.salario` vem munged — no exemplo é a string `"1456 vagas até R$ 16.458,70"` (vagas + faixa salarial concatenados, vindo de `flattenConcursos`/da API). Para o ROI precisa de um parser que extraia o número (regex `R\$\s*([\d.]+,\d{2})`) em `report-utils.js`. Se não der pra extrair, **omitir a página** (mesma estratégia de `pageCargoOverview` que pula quando faltam dados, `report-pdf.js:190`) — nunca inventar valor.
- Evitar linguagem de promessa: frase deve ser sobre *custo da ferramenta vs salário do cargo*, nunca "você vai ganhar R$X". A blocklist (`report-pdf.js:648`) já barra "aprovação garantida"; manter o tom em "custo-benefício", que o próprio doc diz ressoar forte com esse público sensível a preço (`relatorio-perfil-concurseiro.md:34,375`).

### C.3. 🟡 Screenshot/mockup do Raio-X dentro da plataforma

**Por quê:** o PDF descreve o Raio-X em texto (`pageProductContextualized` `report-pdf.js:307`) mas **nunca mostra o produto**. Prova visual converte muito mais que descrição. E o repo **já tem o componente pronto**: `templates/slides/raio_x_mockup.html` é uma réplica fiel do `RaioXMateriaCard.jsx` da plataforma (cards de matéria com barra de distribuição + lista de tópicos com prioridade colorida).

**O que fazer:** renderizar uma página com um mockup do Raio-X **preenchido com os dados reais do cargo** (matéria top + seus tópicos MUITO ALTA + justificativas). Vira "olha como esse exato edital aparece na plataforma".

**Onde mexer:**
- Opção A (mais limpa): nova função `pageRaioXMockup(analysis)` em `lib/report-pdf.js` que monta, no mesmo CSS inline do relatório, um card estilo `raio_x_mockup.html` (linhas `.rx-materia-card` / `.rx-topic`, ver `templates/slides/raio_x_mockup.html:53-185`) com a matéria #1 de `analysis.topicsBySubject` (`report-utils.js:225`).
- Opção B: ler o `raio_x_mockup.html`, preencher os placeholders (`{{mockup_materia_nome}}`, `{{rx_rows_html}}` etc.) e screenshotar separadamente, embutindo o PNG como `<img>` (alinha com o pass flat já existente, `report-pdf.js:703`). Mais reuso, mas mistura dois sistemas de template.
- Inserir logo após a seção "Top tópicos por matéria" (`report-pdf.js:468`), como ponte visual para a página de produtos.
- Existem também `plano_estudos_mockup.html` e `bizzu_topico_mockup.html` — dá pra montar uma sequência "veja na plataforma" de 2-3 mockups, fortalecendo a seção de produto que hoje é só texto.

### C.4. 🟡 Comparativo com concorrentes

**Por quê:** o doc lista os players (QConcursos, Estratégia, Gran Cursos, Direção — `relatorio-perfil-concurseiro.md:76-79,200-206`). Um quadro comparativo posiciona a Bizzu (IA + priorização específica por edital/banca) contra o "muito material, pouca priorização" dos genéricos. O diferencial competitivo já está escrito no doc (`:371-376`): IA aplicada, seleção por tópico, planejamento personalizado, acessibilidade.

**O que fazer:** uma tabela "O que diferencia a Bizzu" — colunas: Bizzu vs "Cursos tradicionais" vs "Bancos de questões genéricos"; linhas: Priorização por edital específico, IA treinada na banca, Plano que adapta à sua rotina, Preço (R$ 10-20/mês vs cursos de centenas de reais). **Não citar concorrentes pelo nome no PDF** (risco jurídico/comparativo) — usar categorias genéricas.

**Onde mexer:**
- Nova função `pageComparativo()` em `lib/report-pdf.js`. A engine de tabela já existe: `table(headers, rows, className)` (`report-pdf.js:90`). É praticamente só montar as linhas.
- Inserir entre a página de produtos e o CTA (`report-pdf.js:471`).
- Ancorar o preço no dado do doc: concurseiro gasta em média R$ 2.011/ano (`:163`); cursos premium custam muito mais que isso. A Bizzu a R$ 120/ano é a opção acessível — exatamente o gatilho de conversão #4 do doc ("preço acessível", `:155`).

### C.5. 🟢 O que falta de brand / polimento

Coisas que hoje deixam a peça menos "Bizzu" do que deveria, à luz das regras de marca em `CLAUDE.md` e `brand-guidelines-bizzu.html`:

1. **Logo no PDF está incompleto.** `logo()` (`report-pdf.js:61`) renderiza `<span>Bizzu</span>` + dot + tagline, mas o invariante de marca é **"Bizzu."** *com ponto no wordmark* (CLAUDE.md: "Logomarca é 'Bizzu.' capitalizado com ponto gold terminator"). Aqui o ponto é um `<i>` separado por flex-gap, visualmente perto mas não é o ponto do wordmark. Verificar contra `brand-guidelines-bizzu.html` se o espaçamento bate com o canônico. **Mexer em `report-pdf.js:62`.**

2. **`data_prova` é buscado mas nunca usado.** A API retorna `data_prova` (no exemplo `2026-08-22`) e ele está em `details`, mas nenhuma página o exibe. Concurso tem **contagem regressiva** como gatilho de urgência legítimo (o doc cita "urgência quando sai o edital", `:158`). Adicionar "Prova em DD/MM · faltam N dias" na capa ou nos facts. **Mexer em `facts[]` `report-pdf.js:389` e/ou na capa `report-pdf.js:412`.** (Urgência real por data ≠ urgência artificial "últimas vagas" que é proibida.)

3. **`escolaridade` veio `null` no exemplo** e cai pra "Não informado" (`apiValue` `report-pdf.js:40`). O `formacao` ("Médio / Técnico / Superior") tem a info melhor. Considerar preferir `formacao` quando `escolaridade` for nulo nos facts (`report-pdf.js:395`).

4. **PDF final tem 8.1 MB (raster).** Para prospecção por e-mail/WhatsApp isso é pesado e o texto não é selecionável (ruim para acessibilidade e para o destinatário copiar trechos). Opções: (a) entregar o `*-vector-source.pdf` (1.8 MB, texto real) quando o ambiente do destinatário for confiável; (b) baixar o `deviceScaleFactor` do flat de 2→1.5 ou comprimir os PNGs; (c) servir ambos e deixar o vendedor escolher. **Mexer em `renderReportPdf` `report-pdf.js:715-756`.**

5. **Fontes carregam de rede (`networkidle` + Google Fonts CDN, `report-pdf.js:484,726`).** Se a geração rodar offline ou o CDN cair, o PDF sai com fonte fallback (quebra a tipografia de marca Space Grotesk/Inter/JetBrains Mono). Considerar auto-hospedar as fontes (woff2 local embutido em base64 ou `file://`). **Mexer no `<head>` `report-pdf.js:482-484`.**

6. **Terminologia de marca:** o PDF acerta nos `requiredTerms` (`report-pdf.js:666`), mas a página de produtos cita "Caderno do Tópico" e "Comentário da Bizzu" (`report-pdf.js:311-312`) que **não** estão na lista canônica dos 5 produtos do `CLAUDE.md` (`PAID_FEATURES`: Raio-X, Bizzu do Tópico, Plano de Estudos, Questões Selecionadas, Revisões Inteligentes). Há divergência entre os 6 produtos do PDF e os 5 produtos canônicos. Alinhar com `agents/lib/brand-constants.js` para consistência cross-channel. **Mexer em `pageProductContextualized` `report-pdf.js:306-313`.**

7. **Cor "Indigo #6C5CE7" da marca aparece pouco.** O PDF é dominado por Gold (#F5A623) + Dark (#09090B); o Indigo só aparece em `.density-fill` e `.quote-box`. As guidelines tratam Indigo como cor primária de igual peso. Avaliar dar mais presença ao indigo (ex.: na barra de distribuição, hoje MÉDIA usa indigo mas as prioritárias são vermelho/laranja). Decisão de design — checar contra `brand-guidelines-bizzu.html`.

---

## D. RISCOS / OBSERVAÇÕES TÉCNICAS

- **`PRIORITY_ORDER` e `shortText` importados mas não usados** em `report-pdf.js:10,15` — dead import inofensivo.
- **`rank` dos tópicos**: `flattenTopics` lê `topic.rank` com fallback 999 (`report-utils.js:87`), mas o shape real da API **não traz `rank`** no objeto de tópico (confirmado no `api-data.json`: tópicos têm `ecmt_id, topico_id, topico_nome, prioridade, justificativa`). Logo o ordenamento "por rank" dentro de prioridade vira no-op (todos 999) e cai no tiebreak. A ordem dos top-3 por matéria é, na prática, a ordem de chegada da API filtrada por prioridade. Não quebra nada, mas a promessa de "3 tópicos mais bem ranqueados" (`report-pdf.js:263`) é frouxa. Se a API passar a expor `rank`, melhora sozinho.
- **`escolaridade: null`** já mencionado (C.5.3).
- **`salario` munged** com vagas (C.2) — afeta capa, facts e qualquer ROI.
- **Jobs em memória** (`server.js:190`) — sem persistência; aceitável para ferramenta single-user local.

---

## E. RESUMO EXECUTIVO DAS MELHORIAS (por esforço × impacto)

| Proposta | Impacto | Esforço | Onde |
|----------|---------|---------|------|
| ✅ Página de ROI (salário vs R$120) | 🔴 Alto | **FEITO 10/06** — `pageRoi` + `parseSalarioMensal` | `report-pdf.js` |
| ✅ Perfil do concurseiro (dores + IA 51,9%) | 🔴 Alto | **FEITO 10/06** — `pagePerfilConcurseiro` | `report-pdf.js` |
| Mockup visual do Raio-X | 🟡 Médio | Médio | reusar `raio_x_mockup.html` + `report-pdf.js:468` |
| Comparativo (categorias, não nomes) | 🟡 Médio | Baixo (`table()` pronta) | nova fn + `report-pdf.js:471` |
| Contagem regressiva (`data_prova`) | 🟡 Médio | Baixo | `report-pdf.js:389/412` |
| Logo "Bizzu." canônico | 🟢 Brand | Baixo | `report-pdf.js:62` |
| Alinhar 6→5 produtos canônicos | 🟢 Brand | Baixo | `report-pdf.js:306` |
| Peso do PDF (8.1 MB) / fontes offline | 🟢 Técnico | Médio | `report-pdf.js:715/482` |

---

## F. PDF DE EXEMPLO — GERADO DE VERDADE ✅

Foi rodado o pipeline real (`generateCargoReport`) contra a API de produção, com a `BIZZU_API_KEY` do `.env` do `bizzu_midia` (confirmado presente). Pré-requisitos satisfeitos: Playwright + Chromium instalados em `node_modules`.

**Cargo escolhido:** AUDITOR FISCAL — Prefeitura de Araguaína 2026 (banca IDIB), `edital_cargo_id = 378ef217-38a4-4ad5-b37f-1ee96da1d778` (obtido de `GET /leads/concursos/available`). Escolhido por ter salário alto (bom para ilustrar o argumento de ROI da proposta C.2).

**Comando equivalente:**
```js
generateCargoReport({ editalCargoId: '378ef217-...', outputBaseDir: 'output/relatorios' })
```

**Resultado (dados 100% reais da API):**
- **18 páginas**, 10 matérias, **166 tópicos** ranqueados.
- Distribuição: 19 MUITO ALTA · 32 ALTA · 49 MÉDIA · 41 BAIXA · 25 MUITO BAIXA.
- **51 tópicos prioritários (31% do edital)**.
- Steps do job: `fetch ok → analysis ok → html ok → render ok` (validação `validateReportCopy` passou).

**Onde salvou** (pasta com timestamp):
```
C:\Users\jboni\Documents\Projetos\bizzu_midia\output\relatorios\prefeitura-de-araguaina-2026-auditor-fiscal-2026-06-10-11-33-36\
```
Conteúdo:
- `prefeitura-de-araguaina-2026-auditor-fiscal-bizzu.pdf` — **PDF final raster, 8.1 MB** (o entregável)
- `prefeitura-de-araguaina-2026-auditor-fiscal-bizzu-vector-source.pdf` — 1.8 MB, texto selecionável
- `prefeitura-de-araguaina-2026-auditor-fiscal-bizzu.html` — 76 KB (HTML fonte)
- `prefeitura-de-araguaina-2026-auditor-fiscal-bizzu-flat.html` — 4.5 KB (HTML do raster)
- `preview_page_01.png` … `preview_page_18.png` — 18 previews
- `api-data.json` — snapshot da resposta da API (120 KB)

**Verificação visual** (3 páginas inspecionadas): capa (navy/gold, headline Space Grotesk, 4 métricas em JetBrains Mono, source-strip Prefeitura/IDIB/Raio-X), página 05 "Matérias por densidade" (tabela com barra indigo, Direito Tributário 53% no topo), e página 18 CTA (R$ 20 / R$ 120, 3 pilares, link assinar). Layout fiel à marca, sem termos proibidos, todos os obrigatórios presentes.

---

*Doc gerado por análise direta do código em `bizzu_midia` + geração real de PDF. Caminhos sempre absolutos. Números de exemplo vêm da API Bizzu de produção (não inventados).*
