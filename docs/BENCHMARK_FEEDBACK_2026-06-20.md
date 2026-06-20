# Benchmark de GESTÃO DE FEEDBACK — Escuta × líderes de Feedback Management (2026-06-20)

> Estudo pedido pelo dono: aprofundar e melhorar o **sistema de feedback + acompanhamento**. Recorte
> deste doc = **FEEDBACK MANAGEMENT** (capturar → organizar → priorizar → fechar o loop), olhando como
> fazem os melhores produtos do gênero: **Canny, Productboard, Savio, Cycle, Enterpret, Dovetail,
> UserVoice, Intercom, Zendesk, Pendo**. Honesto e acionável; onde uma capacidade **já existe no código**
> do Escuta, está citado o arquivo, para não recomendarmos reconstruir o que já temos.
>
> **Complementa, não duplica:** `BENCHMARK_CS_2026-06-20.md` (quadro geral de CS: health/playbooks/
> renovação) e `BENCHMARK_ACOMPANHAMENTO_2026-06-20.md` (timeline, vocabulário de status, follow-up 1:1).
> Aqui o foco é a **disciplina de gerir o feedback em si**: a caixa de entrada, os temas, a priorização
> por demanda/receita e o "você pediu, a gente fez". Onde toco em status, remeto ao doc de Acompanhamento.
>
> **Leitura do mercado (importa para não copiar errado):** os líderes se dividem em três famílias.
> (a) **Portais de votação públicos** — Canny, UserVoice, Pendo Feedback/Listen: o *cliente* envia e vota
> em ideias num board público; o loop fecha sozinho por notificação de status. (b) **Repositórios de
> insight para PM** — Productboard, Cycle, Savio: o *time* captura feedback de vários canais, **linka
> trechos a features** e prioriza por demanda/receita. (c) **IA de análise de feedback não-estruturado** —
> Enterpret, Dovetail: auto-taxonomia/clustering de tópicos em escala, ligando tema → receita.
> **Nenhuma faz o que o Escuta faz:** coletar feedback E agir nele direto no WhatsApp, com LLM, sem o
> cliente sair da conversa — e nenhuma é pensada para o **dono/operador de uma edtech B2C** com milhares
> de assinantes baratos (a unidade é "assinante", não "conta de ARR"; quem opera é o dono, não um PM/CSM).
> Isso muda o que vale copiar: **portal público de votação e RICE multi-coluna valem pouco; captura
> rápida + temas claros + um "fechar o loop" no WhatsApp valem muito.**

---

## (1) Tabela comparativa — produto × os 5 eixos

Eixos: **(1) Captura & Organização** · **(2) Acompanhamento** (status/abordado/atribuição/SLA) ·
**(3) Priorização** (volume × impacto, RICE, votos, receita) · **(4) Fechar o loop** (avisar o cliente
que virou melhoria) · **(5) Simplicidade** (quão "bato o olho e entendo").

| Produto | (1) Captura & Organização | (2) Acompanhamento | (3) Priorização | (4) Fechar o loop | (5) Simplicidade |
|---|---|---|---|---|---|
| **Canny** | Portal onde o cliente posta/vota; admin agrupa posts duplicados num só; categorias/boards; AI dedupe de pedidos. | Status do post (Open→Planned→In Progress→Complete) + roadmap por colunas. | **Votos** (peso por segmento/MRR nos planos pagos); ordena por demanda. | **Forte e automático:** ao mudar status, **todos que votaram/comentaram são notificados** (e via changelog ao enviar). | **Alta** — board público é auto-explicativo; é a referência de "simples". |
| **Productboard** | **Insights Inbox** unifica Intercom/Zendesk/Slack/Salesforce/email; **linka trecho → feature**; automação de tag/assignee por regra; AI auto-link. | Estados da feature + dono; workflow de PM (não de relacionamento). | **RICE** (colunas Reach/Impact/Confidence/Effort, score automático) + **Customer Importance Score** (soma de insights ponderada). | Portal + changelog; avisa seguidores quando entrega. | **Média-baixa** — poderoso mas pesado; "Series A/B feliz, B/C reclama". |
| **Savio** | Centraliza feedback de HubSpot/Intercom/Slack; **dedup e agrega** pedidos iguais; importa o cliente com **MRR/plano** junto. | Estado do request; quem pediu (lista de pessoas/contas por feature). | **Por receita:** ordena por **MRR/ARR** (e por receita **churnada**) e por upvotes. | **E-mail em lote** "para todos que pediram X" direto do Savio quando entrega. | **Alta** — proposta explícita: "simple tool", pouca cerimônia. |
| **Cycle** | **Captura por IA** de conversas → "quotes"; **autopilot** extrai citações, sugere tags e **linka a requests/features** (com você no controle — flaga p/ revisão). | Estados da request; integra Linear (dev) two-way. | Por volume de quotes vinculados + atributos do cliente. | Avisa via integrações quando a request muda. | **Média-alta** — "feedback hub on autopilot", mas é ferramenta de PM. |
| **Enterpret** | **Auto-taxonomia**: aprende os temas do *seu* produto, unifica 50+ canais, categoriza não-estruturado em escala (Customer Context Graph). | — (não é ferramenta de acompanhamento 1:1; é analítica). | **Tema × receita × segmento**: liga cada tema a receita/segmento de cliente. | — (informa decisão; não fecha o loop com o cliente). | **Baixa** — setup de semanas, time de insights dedicado, preço enterprise. |
| **Dovetail** | Repositório de pesquisa; **theme detection + auto-summary + busca semântica** ("Ask Dovetail"); ainda depende de importar/taggear manual. | — (research-focused, não operacional). | Por frequência de temas; sem receita nativa. | — (gera relatório p/ time, não avisa cliente). | **Média** — bom p/ pesquisador, não p/ operador de relacionamento. |
| **UserVoice** | Portal estruturado de feature requests (cliente/prospect/interno); agrega e prioriza. | **Status internos customizáveis** (Settings→Suggestions→Internal Statuses) + status público. | **Votos ponderados por receita/segmento/plano** (10 enterprise de $1M ≠ 50 pequenos). | **Automático em escala:** ao enviar, **notifica todos que votaram**. | **Média** — robusto e "corporativo"; mais cerimônia que Canny. |
| **Intercom** | Conversa multicanal (inclui WhatsApp) é a fonte; tags/temas de conversa; **Fin (IA)** resolve sozinho. Não é repositório de "ideias". | **open/snoozed/closed** + atribuição + SLA + auto-reabrir (ver doc de Acompanhamento). | Por volume de conversas/tag; sem RICE/receita nativos de feedback. | Não fecha loop de "feature pedida"; foco é resolver o ticket. | **Alta** no inbox de conversa; **não** é gestão de feedback de produto. |
| **Zendesk** | Tickets como fonte; tags, views, macros; campos custom. | **New/Open/Pending/On-hold/Solved/Closed** + SLA + automações (ver doc de Acompanhamento). | Por volume/SLA; sem priorização de "ideias" nativa. | CSAT pós-resolução; não avisa "sua ideia virou feature". | **Média** — forte em suporte, não em feedback de produto. |
| **Pendo (Feedback/Listen)** | Captura in-app + categoriza/roteia ideias num lugar (Listen). | Estado da request + roteamento. | **Voto com orçamento finito** por visitante (subir um pedido baixa os outros) → revela prioridade real; liga a uso/analytics. | **Automático:** quem votou/enviou é **notificado quando o status muda** (in-app + e-mail). | **Média** — acoplado ao ecossistema Pendo (analytics/guias). |
| **➡️ Escuta (hoje)** | **Inbox `/feedbacks`** (tipo/origem/sentimento/temas, busca, ~10 filtros, "novo feedback"); **clustering semântico por significado** (pgvector) separado por sentimento; selos manuais. **Sem dedupe de "mesma ideia"; sem linkar trecho→melhoria a partir do inbox.** | **`action_status` por org** `{key,label,cor}` + **"abordado"** + **atribuição** (assignee/team) + **`CsTask`** (SLA/prioridade/dedup) — bom; **vocabulário herdado de bug-tracker** (ver doc de Acompanhamento). | **Calculada, não votada:** `urgencia` 0-100 (sentimento+tipo+nota, `compute_urgencia`) ordena o inbox; **`priority_score` = nº pedidos × urgência média × (1+fração negativa)** no roadmap; **`pain_score` = volume × fração negativa** no cluster. **Sem receita/MRR; sem voto humano.** | **Tem, e é raro:** tela `/melhorias` → **"Fechar o loop"** avisa **no WhatsApp** quem pediu (preview + opt-in + cooldown), grava `notified_at`; esteira auto-resolve feedback ao entregar. | **É o norte do produto** — mas hoje **Temas/Melhorias estão escondidos** do menu e o dono não entendeu ("pra que serve"). |

**Padrões que se repetem nos líderes (e que importam para o Escuta):**

1. **Captura é de baixíssimo atrito e onde o cliente já está.** Canny/UserVoice/Pendo: o cliente posta
   sozinho; Productboard/Cycle/Savio: o time captura **de dentro do canal** (Intercom/Slack/conversa) com
   1 clique. **O Escuta tem o canal certo (WhatsApp) mas a captura ainda é um modal manual** — não há
   "transformar esta mensagem do cliente em feedback" a partir da conversa.
2. **Dedupe / agregação de "a mesma coisa" é capability de primeira classe.** Canny funde posts, Savio
   agrega requests, Enterpret/Cycle clusterizam. **O Escuta clusteriza por significado (ótimo)** mas não
   tem o gesto de "esses 3 feedbacks são o mesmo pedido — junte".
3. **Priorização tem dois sabores: democrática (votos) e econômica (receita).** Canny/Pendo/UserVoice =
   votos (ponderados); Savio/Enterpret/Productboard = **receita/impacto**. **O Escuta usa um 3º caminho —
   urgência + negatividade calculadas por IA** — que é defensável para B2C de massa (o cliente não vai a
   um portal votar), mas hoje **ignora a receita/assinatura** que já temos no `partner`.
4. **Fechar o loop é AUTOMÁTICO e em massa.** Em quase todos, mudar o status para "entregue" **dispara a
   notificação a quem pediu**, sem passo manual. **O Escuta fecha o loop no canal mais forte (WhatsApp) —
   mas exige o operador abrir a tela e confirmar** (o que é bom para controle, mas perde a automação).
5. **Os simples vencem o operador.** Canny e Savio são adotados por serem "bato o olho e entendo".
   Productboard/Enterpret são poderosos e **largados por complexidade** em times pequenos. **Para o dono
   do Escuta, simplicidade não é nice-to-have — é o critério de sobrevivência da feature.**

---

## (2) O que o Escuta JÁ faz bem × GAPS concretos

### Já faz bem (não reconstruir)
- **Inbox real com triagem rica** — `frontend/app/feedbacks/page.tsx`: tipo, origem, sentimento, temas,
  busca e ~10 filtros (inclusive por **perfil/assinatura/NPS** do autor, via `partner`), status inline,
  "abordado", "+tarefa", criar/editar/excluir. É mais rico que o inbox de muitos portais de votação.
- **Clustering semântico de dores** — `app/domain/clustering/engine.py` + `app/api/clusters.py`: agrupa
  por **significado** (embeddings pgvector), **separa por sentimento** (não mistura elogio com crítica),
  rotula via LLM, é idempotente (reusa cluster por cosseno ≥0.92). Isso é a parte cara do Enterpret/Cycle
  — e já existe.
- **Priorização computada e transparente** — `compute_urgencia` (0-100, sentimento+tipo+nota),
  `pain_score = item_count × neg_fraction` (cluster) e `priority_score = pedidos × urgência média ×
  (1+fração negativa)` (roadmap, `app/api/admin.py`). É um "RICE implícito" que **não exige o cliente
  votar** — adequado a B2C de massa.
- **Fechar o loop no WhatsApp** — tela `/melhorias` + `POST /api/improvements/{id}/notify` (preview do
  que será enviado, **opt-in**, **cooldown**, `notified_at`) + esteira que **auto-resolve** os feedbacks
  vinculados ao entregar a melhoria. **Avisar no WhatsApp quem pediu é um diferencial que nem Canny tem.**
- **Da dor ao roadmap em 1 clique** — `/melhorias` → "Puxar para o roadmap" cria a melhoria a partir do
  cluster e já vincula os feedbacks (`from-cluster`). É o "linkar feedback → feature" do Productboard,
  no nosso modelo.
- **Board Kanban multi-entidade** — `frontend/app/board/page.tsx`: arrasta feedback por `action_status`
  ou por selo; cards com chips de conexão (tarefa/melhoria/dor/conversa). A base de "Trello de feedback".

### GAPS concretos (priorizados na §3)
- **G1 — Captura a partir da conversa.** Não há "virar feedback" a partir de uma mensagem do cliente no
  WhatsApp/Chat. Todo feedback nasce de um **modal manual** ou da ingestão de NPS. (Líderes: Cycle/
  Productboard capturam do canal com 1 clique.)
- **G2 — Dedupe / "mesclar" feedbacks iguais.** O clustering agrupa por significado, mas falta o gesto
  humano "estes são o mesmo pedido → junte / vincule à mesma melhoria em lote".
- **G3 — Receita/assinatura não entra na prioridade.** `priority_score`/`urgencia` ignoram MRR, plano e
  estado da assinatura — que **já temos** no `partner`. (Savio/UserVoice/Enterpret priorizam por receita.)
- **G4 — Fechar o loop é 100% manual e item-a-item.** Não há sugestão proativa de "estas melhorias
  entregues têm gente esperando aviso" nem disparo em lote a partir de uma fila.
- **G5 — Temas/Melhorias escondidos e sem nome que o dono entenda.** Saíram do menu; o dono não captou o
  valor. O "você pediu, a gente fez" só rende se estiver visível e nomeado certo (item G do feedback:
  "Temas"→"Mapeamento").
- **G6 — Sem visão "1 card por IDEIA".** O inbox e o board são **por feedback** (1 linha por sinal). Falta
  a visão agregada "por ideia/dor" com **contagem de quantos pediram** — que é como Canny/Savio mostram a
  demanda de relance.
- **G7 — Tipos/origem fixos.** Conjunto fixo no código (já inclui "Bug"); o dono quer **criar tipos e
  editar origens** (item G). Mecânica de `Organization.settings` já existe para status — falta estender.
- **G8 — Sem changelog público / "novidades".** O loop fecha por mensagem 1:1 (forte), mas não há um
  "o que mudou" consolidável (paridade leve com changelog de Canny) — provavelmente **fora de escopo**,
  citado por completude.

---

## (3) 8-12 ideias de melhoria priorizadas

Cada uma com **impacto × esforço** e **por que serve à operação manual simples do dono**. Quase tudo
reusa peças que já existem — por isso o esforço é baixo. Ordenadas por custo-benefício.

| # | Ideia | Impacto | Esforço | Por que serve ao dono (operação manual, simples) |
|---|---|---|---|---|
| **1** | **Renomear e revelar "Mapeamento" (ex-Temas) + número "quantos pediram".** Trazer o clustering de volta ao menu como **"Mapeamento"** (ou "O que pedem"), cada dor mostrando **N clientes pediram isso** + sentimento + 1 ação ("virar melhoria"). | ALTO | BAIXO | Responde direto ao item G. O dono "bate o olho" e vê as 5 dores que mais doem, com volume — sem ler 200 feedbacks. Reusa `clusters.py` + `pain_score`. |
| **2** | **"Você pediu, a gente fez" visível + atalho de fechar o loop.** Devolver `/melhorias` ao menu (renomeado, ex.: "Entregas"/"Roadmap") e mostrar na home/Monitorar um aviso: **"X melhorias entregues têm N clientes esperando aviso → Fechar o loop"**. | ALTO | BAIXO | O diferencial (avisar no WhatsApp) está escondido. Um empurrão de 1 clique transforma entrega em retenção. Reusa `notify` + `notified_at` (preview/opt-in/cooldown já prontos). |
| **3** | **Receita/assinatura na priorização.** Somar ao `priority_score`/ordenação um fator de **plano/estado/“dias de casa”** do `partner` (ex.: detrator pagante anual pesa mais que cortesia cancelada). Exibir no card "pediram: 3 · 2 pagantes". | ALTO | BAIXO-MÉDIO | É como Savio/UserVoice priorizam — e o dado **já existe** no `partner`. Faz a fila refletir "o que dói no caixa", não só o que é negativo. Sem portal de voto (que B2C não usaria). |
| **4** | **Capturar feedback a partir da conversa (WhatsApp/Chat).** Botão "virar feedback" numa mensagem do cliente, pré-preenchendo texto/contato/origem=WhatsApp; opcional: LLM sugere tipo+sentimento+tema (já temos o classificador). | ALTO | MÉDIO | É o gesto que Cycle/Productboard têm e o que **fecha o diferencial do canal**: o feedback nasce onde o cliente fala, sem digitação manual. Reusa `compute_urgencia`/classificador. |
| **5** | **Agrupar / mesclar "mesma ideia" (dedupe assistido).** Na dor (cluster) ou no inbox, ação "estes feedbacks são o mesmo pedido" → vincula todos à **mesma melhoria** em lote (e marca como agrupados). | MÉDIO-ALTO | MÉDIO | Tira o ruído de "o mesmo pedido 8 vezes" (o que Canny/Savio fazem). O clustering já propõe os grupos; falta o **confirmar humano** em 1 clique. Reusa `from-cluster` + vínculo em lote. |
| **6** | **Visão "por ideia" (1 card = 1 demanda).** Uma aba/modo que lista **dores/melhorias com contagem de pedidos** (não 1 card por feedback), ordenada por prioridade, com "fechar o loop" e "ver quem pediu". | MÉDIO-ALTO | MÉDIO | É a tela que Canny/Savio mostram de cara: "o que mais pedem, quanto, e em que pé está". Complementa (não substitui) o inbox por-feedback. Reusa roadmap + counts já calculados. |
| **7** | **Tipos e origens editáveis pelo dono.** Estender o padrão `Organization.settings` (que já guarda status) para **tipos de feedback** e **origens** customizáveis; UI consome a lista. | MÉDIO | BAIXO-MÉDIO | Item G do feedback. Sem migration (mesmo mecanismo dos status/boards). Deixa o dono "gerir do meu jeito" sem tocar código. |
| **8** | **Fechar o loop em LOTE a partir de uma fila.** Tela/lista "esperando aviso": todas as melhorias `entregue` sem `notified_at`, com botão único "avisar todos que pediram" (reusa o preview/opt-in/cooldown por item). | MÉDIO | BAIXO-MÉDIO | Savio faz "e-mail em lote"; aqui é **WhatsApp em lote**, com a salvaguarda de opt-in/cooldown que já existe. Transforma o loop de "item-a-item" em rotina semanal de 2 min. |
| **9** | **Status do feedback alinhado a "ideia" (planejado/entregue) + mostrar no card "quem pediu sabe?".** Pequeno selo no feedback/melhoria: "loop fechado ✓" vs "entregue, ninguém avisado". | MÉDIO | BAIXO | Canny/Pendo deixam o estado do pedido óbvio para o cliente; aqui deixamos **óbvio para o dono** se ele ainda deve um aviso. Reusa `notified_at` (já no `/melhorias`). |
| **10** | **CSAT/"resolveu?" de 1 toque após fechar um caso no WhatsApp.** Ao marcar `resolvido`, oferecer disparo de 1 pergunta ("isso resolveu? 👍/👎") — vira novo `FeedbackItem`. | MÉDIO | MÉDIO | Zendesk/Intercom medem CSAT pós-resolução; aqui no canal forte. Mede se o **acompanhamento** funcionou e realimenta o Mapeamento. (Cruza com o doc de Acompanhamento §3.6.) |
| **11** | **Resumo "o que pedem esta semana" (IA) na home.** Bloco curto: top 3 dores novas/crescendo + "N esperando aviso" + queda/alta de sentimento. Reusa clustering + digest semanal (já no backend). | MÉDIO | BAIXO-MÉDIO | É o "monitoramento inteligente" (item I) na chave de **feedback**. O dono abre e entende a semana em 10 s. (Coordenar com a ideia equivalente do BENCHMARK_CS §2.1 para não duplicar bloco.) |
| **12** | *(Provável fora de escopo)* **Changelog/"novidades" consolidado.** Página simples "o que mudou" alimentada pelas melhorias `entregue`. | BAIXO | MÉDIO | Paridade leve com Canny, mas o loop 1:1 no WhatsApp já cobre o essencial para B2C. Citado por completude; **não recomendo agora**. |

> **Deliberadamente fora:** portal **público de votação** (Canny/UserVoice/Pendo) — o assinante B2C de
> uma edtech não vai a um board votar; o sinal do Escuta vem da conversa, não do voto. E **RICE
> multi-coluna manual** (Productboard) — exige um PM preenchendo Reach/Impact/Confidence/Effort; o
> `priority_score` automático já entrega 80% do valor sem cerimônia. Copiá-los seria gold-plating contra
> o pedido nº 1 do dono (simplicidade).

---

## (4) As 3 de melhor custo-benefício (com esboço no Escuta)

As três escolhidas são **alto impacto, baixo esforço, e atacam o pedido central do dono** (simplicidade +
"deixe mais claro o que o cliente pede e o que fizemos"). Todas reusam código existente.

### ⭐ Destaque 1 — "Mapeamento" visível com contagem de demanda *(ideia 1)*
**O que muda:** a aba **Temas** volta ao menu como **"Mapeamento"** (sugestões: *Mapa de Dores*, *O que
pedem*, *Insights*). Em vez de "lista de temas", vira um **mapa de relance**: cada dor é um card com
**"N clientes pediram isso"**, a cor do **sentimento dominante**, o **`pain_score`** como barra, e um
botão **"Virar melhoria"**. Ordenado pelas dores que mais doem.

**Como fica (reuso direto):**
- Dados: `GET /api/clusters` já devolve `label`, `description`, `item_count`, `dominant_sentiment`,
  `pain_score`, `top_themes`, `improvement_id` — **nada novo no backend**.
- UI: o componente `PendingPainRow` de `frontend/app/melhorias/page.tsx` já renderiza exatamente esse
  card (título + sentimento + "N pediram isso" + `pain_score` + chips + "Puxar para o roadmap").
  **Mover/duplicar para `/temas` renomeada** e devolver ao `Sidebar.tsx`.
- Toque de "mapa": ordenar por `pain_score` e, opcional, **agrupar por sentimento** (negativo no topo).
- **Por que ganha:** resolve o item G ("Temas"→"Mapeamento") com quase zero código novo e dá ao dono a
  tela que ele não entendia, agora auto-explicativa ("bato o olho e vejo o que mais pedem").

### ⭐ Destaque 2 — "Você pediu, a gente fez" visível + fechar o loop em 1 clique *(ideias 2 + 8)*
**O que muda:** `/melhorias` volta ao menu (ex.: **"Entregas"**), e na **Monitorar** aparece um aviso
acionável: **"3 melhorias entregues têm 12 clientes esperando aviso → Fechar o loop"**. Clicar abre a
**fila de loops pendentes** (melhorias `entregue` sem `notified_at`); cada uma com o **preview** que já
existe (quem recebe, quem fica fora por opt-in/cooldown) e um botão para disparar — uma a uma ou em lote.

**Como fica (reuso direto):**
- Pendências: `GET /api/improvements/roadmap` já traz `status` e `notified_at`/`notified_em`; filtrar
  `status == "entregue" && !notified_at` é trivial (o front já calcula `canCloseLoop`).
- Envio: `POST /api/improvements/{id}/notify` (preview) e `?confirm=true` (envia + grava `notified_at`)
  **já existem**, com **opt-in + cooldown + mensagem personalizada por tema** (`_notify_message`).
- Lote: iterar a fila chamando o mesmo endpoint por item (a salvaguarda de cooldown/opt-in protege).
- **Por que ganha:** é o **maior diferencial do produto** hoje desperdiçado por estar escondido. Avisar
  no WhatsApp "lembra que você pediu X? saiu!" é retenção barata que nem Canny faz tão direto. Esforço
  baixíssimo — quase tudo é re-expor o que existe. (Depende do **WAHA em prod**, como o resto do canal.)

### ⭐ Destaque 3 — Receita/assinatura na priorização *(ideia 3)*
**O que muda:** a fila do inbox e o `priority_score` do roadmap passam a **pesar o valor do cliente**.
Hoje `priority_score = nº pedidos × urgência média × (1 + fração negativa)` e `urgencia` combina só
sentimento+tipo+nota. Adicionar um **multiplicador de receita/estado** derivado do `partner` (plano,
estado da assinatura, dias de casa), e **exibir** no card "pediram: 3 · 2 pagantes".

**Como fica (reuso direto):**
- Dado: o `partner` (estado `active_paying`/`past_due`/`cancelled`, plano `mensal`/`anual`,
  `daysAsSubscriber`) já vem no snapshot do contato e já é **filtro** no inbox (`estado`, `plan_type`).
- Cálculo: um fator simples e legível, ex. `peso = 1.0 + (0.5 se anual) + (0.5 se active_paying)`,
  somado em `compute_urgencia`/`priority_score` (`app/api/admin.py`). **Sem migration** (dado já no
  snapshot); manter o fator **transparente** (mesma filosofia auditável do `factors` do Health Score).
- **Por que ganha:** é como Savio/UserVoice priorizam ("10 enterprise ≠ 50 pequenos"), adaptado a B2C:
  um detrator **pagante anual** sobe na fila acima de um elogio de cortesia cancelada. Faz a triagem
  refletir o caixa, **sem** exigir portal de votação (que o público B2C não usaria). Risco: manter o peso
  modesto e visível para o dono não sentir "a máquina decidindo sozinha" (preocupação dele com automação).

> **Sequência sugerida:** Destaque 1 (revela o valor escondido, ~0 backend) → Destaque 2 (ativa o
> diferencial, ~0 backend, depende do WAHA) → Destaque 3 (afina a priorização com dado que já temos).
> As três juntas entregam o arco completo de feedback management — **capturar/organizar → ver demanda →
> priorizar por valor → fechar o loop** — sem nenhuma feature pesada de PM e sem brigar com os P0/P1 de
> bug e design já priorizados no `FEEDBACK_DONO_2026-06-20.md`.

---

## Resumo do que JÁ existe no código (para não reconstruir)
- **Inbox de feedback** com tipo/origem/sentimento/temas/busca + ~10 filtros (incl. perfil/assinatura/NPS
  do autor) + status/abordado/atribuição/+tarefa inline → `frontend/app/feedbacks/page.tsx`.
- **Clustering semântico de dores** (pgvector, separa por sentimento, rotula via LLM, idempotente) →
  `app/domain/clustering/engine.py` + `app/api/clusters.py` (`pain_score = item_count × neg_fraction`).
- **Priorização computada** → `compute_urgencia` (0-100) e `priority_score = pedidos × urgência média ×
  (1 + fração negativa)` em `app/api/admin.py`.
- **Fechar o loop no WhatsApp** (preview + opt-in + cooldown + `notified_at` + esteira auto-resolve) →
  `/melhorias` + `POST /api/improvements/{id}/notify` (`_notify_message` em `app/api/admin.py`).
- **Dor → roadmap em 1 clique** (`from-cluster`, vincula feedbacks) e **vincular melhoria** no card do board.
- **Board Kanban multi-entidade** (arrasta por status/selo; chips de conexão) → `frontend/app/board/page.tsx`.
- **Status/tipos por org** via `Organization.settings` (mecanismo pronto p/ estender a tipos/origens).

## Fontes (pesquisa de mercado, jun/2026)
- **Canny** (votos, dedupe, status auto-notifica voters) — [Canny review (RevOps)](https://revops.tools/canny/) · [Public roadmap](https://help.canny.io/en/articles/3828148-public-roadmap) · [Feature voting best practices](https://canny.io/blog/feature-voting-best-practices/) · [Canny site](https://canny.io/)
- **Productboard** (Insights Inbox, link insight→feature, RICE, Customer Importance Score, AI auto-link) — [Quick start: Feedback](https://support.productboard.com/hc/en-us/articles/26907498937235-Quick-start-guide-Feedback) · [Link feedback to ideas](https://support.productboard.com/hc/en-us/articles/360056354514-Link-user-feedback-to-related-feature-ideas-using-insights) · [Prioritization frameworks (RICE)](https://www.productboard.com/glossary/product-prioritization-frameworks/) · [AI auto-link](https://support.productboard.com/hc/en-us/articles/26949590820627-Link-insights-automatically-with-Productboard-AI)
- **Savio** (centraliza, dedup/agrega, MRR/receita, e-mail em lote no loop) — [Product feedback management](https://www.savio.io/product-feedback-management/) · [Track customer feedback](https://www.savio.io/track-customer-feedback/) · [Closing the loop](https://www.savio.io/blog/closing-the-loop-customer-feedback/) · [Save customer data (MRR/plan)](https://www.savio.io/features/save-customer-data-with-product-feedback/)
- **Cycle** (captura por IA, quotes, autopilot linka a requests, com revisão humana) — [AI to process feedback](https://help.cycle.app/core-concepts/ai-to-process-feedback) · [Processing feedback](https://help.cycle.app/cycle-core/processing-feedback) · [Cycle AI](https://help.cycle.app/core-concepts/cycle-ai)
- **Enterpret** (auto-taxonomia, 50+ canais, tema×receita×segmento) — [Deep analysis of unstructured feedback](https://www.enterpret.com/guides/best-software-that-offers-deep-analysis-of-unstructured-feedback) · [Tools for product insights](https://www.enterpret.com/guides/the-6-top-rated-tools-for-product-insights-based-on-user-feedback)
- **Dovetail** (theme detection, auto-summary, Ask Dovetail; research-focused) — [Best Dovetail alternatives 2026 (overview)](https://blog.buildbetter.ai/best-dovetail-alternatives-in-2026/) · [AI feedback analytics tools](https://www.zonkafeedback.com/blog/ai-feedback-analytics-tools)
- **UserVoice** (votos ponderados por receita, status internos custom, notifica voters ao enviar) — [UserVoice (RevOps)](https://revops.tools/uservoice/) · [Internal status updates for ideas](https://feedback.uservoice.com/knowledgebase/articles/1882915-internal-status-updates-for-ideas)
- **Pendo (Feedback/Listen)** (voto com orçamento finito, notifica ao mudar status) — [Overview of Pendo Feedback](https://support.pendo.io/hc/en-us/articles/5092218184475-Overview-of-Pendo-Feedback) · [Requests, votes, priorities](https://support.pendo.io/hc/en-us/articles/13585480291355-Requests-votes-and-priorities) · [Manage feedback in Listen](https://support.pendo.io/hc/en-us/articles/18161565569819-Manage-feedback-in-Listen)
- **Intercom / Zendesk** (canal/tickets como fonte; status e CSAT) — referências canônicas reusadas do `BENCHMARK_ACOMPANHAMENTO_2026-06-20.md` (Intercom Snooze/Close; Zendesk New/Open/Pending/On-hold/Solved/Closed; Zendesk CSAT em messaging).
- **Comparativos gerais** (famílias de produto, maturidade, quando cada um cansa) — [Canny vs Productboard (UserJot)](https://userjot.com/blog/canny-vs-productboard) · [Tools for product insights 2026 (Enterpret)](https://www.enterpret.com/guides/best-customer-feedback-analysis-tools-for-making-product-roadmap-decisions-2026) · [Feedback consolidation tools (Mindbacklog)](https://mindbacklog.com/blog/customer-feedback-consolidation-tools-how-to-unify-every-channel-into-one-intelligence-view/)
