# Blueprint — Jornada de Feedback (Escuta)

> Data: 2026-06-20 · Status: blueprint para virar tarefas de build · Escopo: 3 telas (Mapeamento `/temas`, Melhorias `/melhorias`, modal Fechar o loop). Design já aprovado em mockups.
> **READ-ONLY:** este documento NÃO altera código. Padrão arquitetural: **Layered** (router → função de domínio pura → models/SQL), multi-tenant por `organization_id`, igual ao resto do projeto.

A descoberta-chave desta análise: **quase toda a jornada já existe no código**. O roadmap priorizado, o `from-cluster`, o modal de "fechar o loop" com preview/confirm/cooldown/opt-in, e o cálculo de prioridade de melhorias **já estão prontos e testados**. As lacunas reais são: (1) o **índice de prioridade transparente das DORES** (volume × receita × gravidade) ainda não existe — a tela de dores só tem `pain_score`; (2) a tela `/melhorias` é uma **lista**, não um **Kanban** de 3 colunas; (3) `/melhorias` **não está no menu**. Nenhuma migration é necessária.

---

## 1. REUSA vs CRIA

### 1.1 JÁ EXISTE e só precisa RELIGAR/AJUSTAR (reuso)

| Peça | Onde | Estado | Ação |
|---|---|---|---|
| Clustering de dores + `pain_score` + `neg_count` + `dominant_sentiment` | `app/api/clusters.py:154` `_cluster_out`; motor `app/domain/clustering/engine.py` | Pronto | Manter; estender payload (aditivo) |
| Endpoint que serve os cards de dor | `app/api/clusters.py:224` `GET /api/feedbacks/clusters?days=&sort=` | Pronto | **Ajustar**: incluir índice + ordenar por ele |
| Agregações em lote (sem N+1) | `app/api/clusters.py:174` `_neg_counts_by_cluster`, `:194` `_themes_by_cluster` | Pronto | Reusar como molde p/ novas agregações |
| Leitura de receita/gravidade do `partner` | `app/api/admin.py:962` `compute_urgencia`; `:1052` `_partner_fields`; `app/domain/selos_vivos.py` | Pronto, testado | **Reusar a semântica** (não reinventar) |
| Tela Mapeamento (cards, abas, "Ver feedbacks", "Virar melhoria", badge dor crítica) | `frontend/app/temas/page.tsx` (`ClusterCard`) | Pronto | **Ajustar** card: + selo prioridade, + barra do índice, + "N clientes · M pagantes · sentimento" |
| Roadmap priorizado de melhorias | `app/api/admin.py:2323` `GET /api/improvements/roadmap` (`priority_score = feedback_count × max(urgência,1) × (1+neg)`) | Pronto | Reusar como está |
| Dor → melhoria (idempotente, bulk-link) | `app/api/admin.py:2467` `POST /api/improvements/from-cluster` | Pronto | Reusar |
| Entregar melhoria (grava `delivered_at`, esteira resolve feedbacks) | `app/api/admin.py:2699` `PATCH /api/improvements/{id}` | Pronto | Reusar |
| "Avisar quem pediu" (preview + confirm + cooldown + opt-in + `sem_whatsapp` + mensagem on-brand + `notified_at`) | `app/api/admin.py:2823` `POST /api/improvements/{id}/notify` | Pronto | Reusar |
| Tela Melhorias: lista priorizada + "Puxar dos temas" + **CloseLoopModal (preview/confirm)** + "N clientes pediram" + badge "loop fechado" | `frontend/app/melhorias/page.tsx` | Pronto | **Ajustar** layout p/ Kanban; modal já serve |
| Modal "Fechar o loop" (lista quem recebe/pula + prévia da mensagem + "Confirmar envio (N)") | `frontend/app/melhorias/page.tsx` `CloseLoopModal` | **Pronto — atende o requisito 3 integralmente** | Reusar |
| Tipos/clients TS (`FeedbackCluster`, `ImprovementRoadmapItem`, `NotifyResult`, `clusters.list`, `melhorias.*`) | `frontend/lib/api.ts:270,960,1000,1423,1430` | Pronto | **Estender** `FeedbackCluster` (campos do índice) |
| Item de menu Mapeamento (`/temas`) | `frontend/components/Sidebar.tsx:47` | Pronto, **já no menu** | Nada (requisito "reexpor" já satisfeito) |

### 1.2 NOVO (criar)

| Peça | Onde (novo) | Por quê |
|---|---|---|
| **Função pura do índice de prioridade** | `app/domain/prioridade.py` (NOVO) | Não existe índice volume×receita×gravidade p/ DORES; isolar em domínio (espelha `selos_vivos.py`) |
| Pesos default do índice (transparentes) | `app/config.py` (3-4 settings novos) | Pesos exibíveis/ajustáveis sem tocar código |
| Agregação de **clientes distintos** e **pagantes** por cluster | `app/api/clusters.py` (helper novo, molde `_neg_counts_by_cluster`) | `pain_score` conta itens, não clientes; "pagante" vem do `partner` do contato |
| Campos do índice no payload de `/clusters` | `app/api/clusters.py` `_cluster_out` (aditivo) | UI precisa de `distinct_customers`, `paying_customers`, `priority_index`, `priority_band`, `priority_breakdown` |
| Selo de prioridade + barra do índice + linha "📊/💳/🔴" no card de dor | `frontend/app/temas/page.tsx` `ClusterCard` | Requisito 1 |
| Layout Kanban (Ideias / Fazendo / Entregue) | `frontend/app/melhorias/page.tsx` (refactor da lista) | Requisito 2 (hoje é lista linear) |
| Faixa "N clientes esperando retorno → Avisar" na coluna Entregue | `frontend/app/melhorias/page.tsx` | Requisito 2 (já há dados: `feedback_count` + `notified_at`) |
| Item de menu Melhorias (`/melhorias`) | `frontend/components/Sidebar.tsx` | Requisito 1+2 (hoje fora do menu — `Sidebar.tsx:35`) |
| Campo TS opcional no `FeedbackCluster` (índice) | `frontend/lib/api.ts:270` | Contrato dos novos campos |

> **SEM MIGRATION.** Todas as colunas necessárias já existem: `Improvement.{status,cluster_id,delivered_at,notified_at,effort,target_date}` (`app/models/improvement.py`), `FeedbackCluster.improvement_id` (`app/models/cluster.py`), `FeedbackItem.{contact_id,improvement_id,cluster_id,score,sentiment,type}` (`app/models/feedback.py`). O "pagante" sai de `Contact.profile_data["partner"]` (já populado pelo sync da API de Clientes).

---

## 2. Índice de Prioridade (fórmula concreta + onde calcular)

### 2.1 Decisão

**Calcular no BACKEND**, dentro do endpoint `GET /api/feedbacks/clusters` (`app/api/clusters.py`), via uma **função pura nova** `app/domain/prioridade.py::priority_index(...)`. Espelha exatamente o padrão de `app/domain/selos_vivos.py` (função pura, sem rede, testável) chamada por um endpoint — e o padrão de `roadmap_improvements` (`admin.py:2323`), que já calcula um score no endpoint. **Sem migration**, **sem serviço novo**, **sem lógica de negócio no frontend**.

Motivo de não materializar em coluna: o "pagante" e a receita vêm do snapshot `partner`, que muda **fora** do run de clustering (renovação, cancelamento). Calcular na leitura mantém o índice sempre fiel ao estado atual — mesma filosofia dos selos vivos.

### 2.2 Os três sinais (todos já existem na base)

| Sinal | Definição | Fonte (citação) |
|---|---|---|
| **Volume** | nº de **clientes distintos** (`COUNT(DISTINCT contact_id)`) com feedback no cluster | `FeedbackItem.contact_id` (`models/feedback.py:38`) |
| **Receita** | fração de clientes **pagantes** entre os distintos do cluster (peso maior p/ pagantes / plano alto) | `Contact.profile_data["partner"].subscription.state` ∈ paga; `planType ∈ {mensal,anual}` (`admin.py:1063,1103`; `selos_vivos.py:100`) |
| **Gravidade** | fração negativa = `neg_count / item_count` (sentimento/negatividade) | `_neg_counts_by_cluster` + `item_count` (`clusters.py:174,167`) |

> **Pagante (regra canônica):** `state` (lower) contém `paying`/`paid`/`active` E não contém `cancel`/`complimentary`. Estados vistos no código: `active_paying`, `paid_without_access`, `cancelled`, `complimentary`, `past_due` (`admin.py:1104`). **Plano alto:** `planType == 'anual'` ganha um multiplicador (espelha o `+10` de plano anual em `compute_urgencia`, `admin.py:1010-1012`).

### 2.3 Fórmula (pesos default transparentes e exibíveis)

```
# componentes normalizados em 0..1
volume_score  = min(1.0, distinct_customers / VOL_REF)                 # VOL_REF default = 10
revenue_score = paying_weighted / max(distinct_customers, 1)           # 0..1
                  onde paying_weighted = Σ peso_do_cliente
                  peso_do_cliente = 1.0 (pagante mensal) | PLANO_ALTO_MULT (pagante anual) | 0.0 (não pagante)
                  PLANO_ALTO_MULT default = 1.5 (clampado: revenue_score ≤ 1.0)
gravity_score = neg_count / item_count                                 # 0..1 (0 se item_count=0)

# índice final 0..100 com pesos default V=0.50, R=0.30, G=0.20 (somam 1.0)
priority_index = round(100 * (W_VOLUME*volume_score + W_REVENUE*revenue_score + W_GRAVITY*gravity_score), 1)

# selo (banda)
priority_band = "alta"  se priority_index >= 66
              | "media" se priority_index >= 33
              | "baixa" caso contrário
```

**Pesos default em `app/config.py`** (exibíveis no payload p/ a UI explicar "por que essa prioridade"):

| Setting | Default | Significado |
|---|---|---|
| `priority_weight_volume` | `0.50` | peso do volume (clientes distintos) |
| `priority_weight_revenue` | `0.30` | peso da receita (pagantes / plano alto) |
| `priority_weight_gravity` | `0.20` | peso da gravidade (negatividade) |
| `priority_volume_ref` | `10` | volume que satura `volume_score` em 1.0 |
| `priority_plano_alto_mult` | `1.5` | multiplicador do pagante anual |

> Quando o sentimento por item ainda não foi classificado (`neg_count == 0` com `item_count > 0`), `gravity_score = 0` — a UI já trata esse caso hoje como "sentimento pendente" (`temas/page.tsx:269`). O índice continua válido por volume+receita; o card mostra o selo + badge "⏳ sentimento pendente" (reuso do existente).

### 2.4 Onde, exatamente

1. `app/domain/prioridade.py` — `priority_index(distinct_customers, paying_weighted, neg_count, item_count, *, weights) -> dict` (função pura: devolve `{priority_index, priority_band, breakdown}`).
2. `app/api/clusters.py` — novo helper `_customer_counts_by_cluster(session, org_id, cluster_ids) -> dict[uuid, (distinct, paying_weighted)]` (UMA query agregando `FeedbackItem` join `Contact`, lendo `partner` em Python; molde = `_neg_counts_by_cluster`).
3. `app/api/clusters.py:154` `_cluster_out` — recebe os números e injeta `distinct_customers`, `paying_customers`, `priority_index`, `priority_band`, `priority_breakdown` no dict (aditivo; **`pain_score` permanece**).
4. `app/api/clusters.py:224` `list_clusters` — chama o helper; aceita `sort="prioridade"` (novo default) e ordena por `priority_index` desc.

---

## 3. Mudanças por arquivo

### 3.1 Backend

| Arquivo | Mudança | Detalhe |
|---|---|---|
| `app/config.py` | **NOVO**: 5 settings de pesos | `priority_weight_volume/revenue/gravity`, `priority_volume_ref`, `priority_plano_alto_mult` (com defaults da §2.3) |
| `app/domain/prioridade.py` | **NOVO ARQUIVO** | Função pura `priority_index(...)` + helper `peso_pagante(partner) -> float` + `is_paying(partner) -> bool`. Tolerante a None (nunca lança), espelhando `selos_vivos.py` |
| `app/api/clusters.py` | **NOVO helper** `_customer_counts_by_cluster` | 1 query: `FeedbackItem(cluster_id IN …)` join `Contact`; agrupa por cluster em Python; soma `peso_pagante(partner)` e conta `DISTINCT contact_id` |
| `app/api/clusters.py` `_cluster_out` (:154) | **Estender (aditivo)** | + `distinct_customers`, `paying_customers`, `priority_index`, `priority_band`, `priority_breakdown`; **manter `pain_score`** |
| `app/api/clusters.py` `list_clusters` (:224) | **Ajustar** | chamar o novo helper; `sort` aceita `"prioridade"` (novo default) → ordena por `priority_index` desc; `get_cluster`/`update_cluster` passam os novos args ao `_cluster_out` |
| `tests/test_clustering.py`, `tests/test_roadmap_api.py` | **Atualizar asserts** | só ADITIVO — garantir que `pain_score` e contratos existentes seguem; cobrir os novos campos |

> `roadmap_improvements`, `from-cluster`, `notify`, modelos: **inalterados**.

### 3.2 Frontend

| Arquivo | Mudança | Detalhe |
|---|---|---|
| `frontend/lib/api.ts` `FeedbackCluster` (:270) | **Estender** | campos opcionais `distinct_customers?`, `paying_customers?`, `priority_index?`, `priority_band?: "alta"\|"media"\|"baixa"`, `priority_breakdown?` |
| `frontend/lib/api.ts` `ClustersSort` (:297) | **Estender** | + `"prioridade"` |
| `frontend/app/temas/page.tsx` `ClusterCard` (:262) | **Ajustar** | + **selo de prioridade** (Alta/Média/Baixa) no header, + **barra do índice** (estilo da `tema-volume`), + linha "📊 N clientes · 💳 M pagantes · 🔴 sentimento"; manter "Ver feedbacks" + "Virar melhoria" |
| `frontend/app/temas/page.tsx` `loadClusters` (:472) | **Ajustar** | `sort=prioridade` (default); manter "dor"/"volume" como alternativas |
| `frontend/app/melhorias/page.tsx` (:646) | **Refactor de layout** | trocar a **lista única** por **3 colunas Kanban**: Ideias (`ideia`+`planejada`), Fazendo (`em_andamento`), Entregue (`entregue`); reusa `ImprovementCard` e o agrupamento por `status`; mover entre colunas = o `changeStage` que já existe |
| `frontend/app/melhorias/page.tsx` coluna Entregue | **NOVO bloco** | faixa "**N clientes esperando retorno → Avisar**" por melhoria entregue com `notified_at == null` (N = `feedback_count`); botão abre o **CloseLoopModal já existente** |
| `frontend/components/Sidebar.tsx` (grupo Operação) | **Adicionar item** | `{ href: "/melhorias", label: "Melhorias", icon: <Lucide> }` logo após "Mapeamento"; remover `/melhorias` do comentário de "fora do menu" (:35) |

> O `CloseLoopModal`, `RecipientRow`, `openCloseLoop`/`confirmCloseLoop` (preview→confirm) **não mudam** — o requisito 3 (modal "Avisar quem pediu" com lista + prévia + "Enviar para os N") já está implementado.

---

## 4. Frentes de implementação (paralelizáveis, sem sobreposição de arquivos)

```
F1 backend-prioridade ──► F2 frontend-Mapeamento
   (clusters + domínio)      (consome o índice)

F3 frontend-Melhorias  (independente)
F4 Sidebar + tipos     (independente; libera cedo)
```

| Frente | Escopo | Arquivos (exclusivos da frente) | Depende de |
|---|---|---|---|
| **F1 — Backend: índice nas dores** | Função pura do índice + agregação distinct/paying + expor no payload + ordenar | `app/domain/prioridade.py` (novo), `app/config.py`, `app/api/clusters.py`, `tests/test_clustering.py`, `tests/test_roadmap_api.py` | — |
| **F2 — Frontend: Mapeamento redesign** | Selo de prioridade + barra do índice + "📊/💳/🔴" no `ClusterCard`; `sort=prioridade` | `frontend/app/temas/page.tsx` | **F1** (contrato dos campos) + F4 (tipo `FeedbackCluster`) |
| **F3 — Frontend: Melhorias Kanban + faixa Avisar** | 3 colunas (Ideias/Fazendo/Entregue) + faixa "N esperando → Avisar" (reusa CloseLoopModal/notify) | `frontend/app/melhorias/page.tsx` | — (backend já pronto) |
| **F4 — Sidebar + contrato TS** | Re-adicionar `/melhorias` ao menu; estender `FeedbackCluster`/`ClustersSort` em `api.ts` | `frontend/components/Sidebar.tsx`, `frontend/lib/api.ts` | — |

**Disjunção de arquivos garantida:** F1 = só backend; F2 = só `temas/page.tsx`; F3 = só `melhorias/page.tsx`; F4 = só `Sidebar.tsx` + `api.ts`. Nenhum arquivo aparece em duas frentes.

**Ordem prática:** começar F1 e F4 em paralelo (liberam contrato + tipos cedo). F3 corre o tempo todo (não depende de F1). F2 entra quando F1 e F4 fecham o contrato. F2 pode usar mock do payload p/ não bloquear.

**Interface de contrato entre F1↔F2 (congelar antes):** os 5 campos novos do `FeedbackCluster` (`distinct_customers:int`, `paying_customers:int`, `priority_index:number`, `priority_band:"alta"|"media"|"baixa"`, `priority_breakdown:{volume_score,revenue_score,gravity_score,weights}`) + `sort="prioridade"`.

---

## 5. Critérios de aceite por frente

### F1 — Backend: índice nas dores
- `GET /api/feedbacks/clusters` retorna, por cluster: `distinct_customers`, `paying_customers`, `priority_index` (0–100), `priority_band` (`alta`/`media`/`baixa`), `priority_breakdown` (3 componentes + pesos); `pain_score` **continua presente** (back-compat).
- `priority_index` = `100*(0.50*volume + 0.30*revenue + 0.20*gravity)` com os defaults da §2.3; mudar os pesos em `config` muda o resultado (teste com pesos custom).
- `distinct_customers` = `COUNT(DISTINCT contact_id)` (não nº de itens); cluster com 3 feedbacks do mesmo cliente conta **1**.
- `paying_customers` reflete `partner.subscription.state` pagante; pagante **anual** pesa mais que mensal (multiplicador) e `revenue_score` clampa em 1.0.
- `sort=prioridade` ordena por `priority_index` desc; `sort=dor`/`volume`/`recente` seguem funcionando.
- Função `app/domain/prioridade.py` é **pura** (sem sessão/rede), tolera `partner` None/sujo sem lançar; coberta por unit test (inclui caso `neg_count=0` → `gravity_score=0`).
- Sem migration; `pytest` verde.

### F2 — Frontend: Mapeamento redesign
- Cada card de dor mostra: **selo de prioridade** (Alta/Média/Baixa, cor coerente), **barra do índice** (largura ∝ `priority_index`), e a linha "📊 N clientes · 💳 M pagantes · 🔴 <sentimento>".
- Lista **ordenada por prioridade desc** por padrão (`sort=prioridade`).
- "Ver feedbacks" e "Virar melhoria" continuam funcionando (idempotência preservada).
- Caso "sentimento pendente" (`neg_count=0`) ainda renderiza selo + badge ⏳ sem quebrar.
- `tsc` 0 erros; sem `pageerror` no `/temas`.

### F3 — Frontend: Melhorias Kanban + faixa Avisar
- `/melhorias` exibe **3 colunas**: Ideias (ideia+planejada), Fazendo (em_andamento), Entregue (entregue); descartadas fora das colunas (ou colapsadas).
- Cada melhoria mostra "**N clientes pediram**" (= `feedback_count`).
- Na coluna **Entregue**, melhoria com `notified_at == null` mostra faixa "**N clientes esperando retorno → Avisar**"; o botão abre o **CloseLoopModal** (preview), e "Confirmar envio (N)" chama `notify?confirm=true` (igual hoje).
- Trocar coluna = `PATCH /api/improvements/{id}` com novo `status` (reusa `changeStage`); entregar grava `delivered_at` (já no backend).
- `tsc` 0 erros; sem `pageerror`.

### F4 — Sidebar + contrato TS
- "Melhorias" aparece no menu (grupo Operação), navega p/ `/melhorias`, fica ativo na rota.
- "Mapeamento" (`/temas`) permanece no menu.
- `FeedbackCluster` e `ClustersSort` estendidos em `api.ts`; `tsc` 0 erros; nenhum consumidor existente quebra (campos novos opcionais).

---

## 6. Workflow da jornada (visão de fluxo)

```
COLETA/INGESTÃO ─► feedback_items (sentiment, contact_id, partner via Contact)
        │
        ▼
[run_clustering] agrupa por significado ─► feedback_clusters (pain_score, dominant_sentiment)
        │
        ▼
MAPEAMENTO (/temas)  ── índice = volume × receita × gravidade ──► cards ordenados por prioridade
        │  selo Alta/Média/Baixa · barra · "📊 N · 💳 M · 🔴"
        │  "Virar melhoria" (POST /improvements/from-cluster, idempotente, bulk-link)
        ▼
MELHORIAS (/melhorias)  Kanban: Ideias → Fazendo → Entregue   (PATCH status)
        │  "N clientes pediram" (feedback_count)
        │  entregar ─► delivered_at + esteira resolve feedbacks vinculados
        ▼
FECHAR O LOOP  coluna Entregue: "N esperando → Avisar"
        │  CloseLoopModal: preview (notify) ─► lista quem recebe/pula + prévia da msg
        ▼  "Confirmar envio (N)" ─► notify?confirm=true ─► WAHA + grava notified_at
   loop fechado ✓ (badge)
```

Estados de uma melhoria (já no backend, `admin.py:2105`):
```
ideia ─► planejada ─► em_andamento ─► entregue ─(notify confirm)─► [notified]
                                  └─► descartada
```

---

## 7. Architecture Decisions

### ADR-1 — Índice de prioridade calculado na leitura (não materializado)
- **Status:** Aceito.
- **Contexto:** a tela de dores precisa de um índice volume×receita×gravidade transparente; receita/pagante muda fora do run de clustering.
- **Opções:** (1) função pura no endpoint de clusters; (2) coluna materializada via migration no `run_clustering`; (3) cálculo no frontend.
- **Decisão:** (1) — função pura `app/domain/prioridade.py` chamada por `list_clusters`. Espelha `selos_vivos.py` + `roadmap_improvements`.
- **Consequências:** sempre fiel ao `partner` atual; sem migration; pequeno custo de 1 query agregada por listagem (mesmo padrão das outras); pesos transparentes em `config`.

### ADR-2 — Reusar o pipeline de "fechar o loop" existente
- **Status:** Aceito.
- **Contexto:** o requisito 3 (modal Avisar + preview + "Enviar para os N") parecia novo.
- **Decisão:** **não criar nada** — `POST /improvements/{id}/notify` (preview/confirm/cooldown/opt-in/`sem_whatsapp`) e o `CloseLoopModal` já implementam o requisito; só se acrescenta a **porta de entrada** (faixa "N esperando → Avisar" na coluna Entregue).
- **Consequências:** respeita a regra de ouro (WhatsApp real só com OK — o `confirm=true` já é o gate); zero risco de duplicar lógica de envio.

### ADR-3 — `/melhorias` vira Kanban e volta ao menu
- **Status:** Aceito.
- **Contexto:** a tela existe e funciona como lista priorizada, mas o design aprovado pede colunas (Ideias/Fazendo/Entregue) e ela foi removida do menu por "ruído".
- **Decisão:** refatorar o layout em 3 colunas reusando `ImprovementCard` + `changeStage`; re-adicionar o item no Sidebar.
- **Consequências:** mudança só de apresentação no front; backend e contrato intactos.

---

## 8. Contrato — campos novos de `FeedbackCluster` (payload `/api/feedbacks/clusters`)

```jsonc
{
  // … campos atuais (id, label, description, dominant_sentiment, item_count,
  //    neg_count, pain_score, top_themes, improvement_id, created_at) …
  "distinct_customers": 7,            // COUNT(DISTINCT contact_id) no cluster
  "paying_customers": 4,              // nº de clientes pagantes (partner.subscription)
  "priority_index": 71.5,             // 0..100
  "priority_band": "alta",            // "alta" | "media" | "baixa"
  "priority_breakdown": {
    "volume_score": 0.70,             // 0..1
    "revenue_score": 0.86,            // 0..1 (pondera plano alto)
    "gravity_score": 0.55,            // 0..1 (= neg_count/item_count)
    "weights": { "volume": 0.5, "revenue": 0.3, "gravity": 0.2 }
  }
}
```

> Todos **aditivos e opcionais** no TS — nenhum consumidor atual (`/melhorias` "Puxar dos temas" ordena por `pain_score`, que permanece) quebra.

---

## Referências (arquivo:linha)

- Dores/índice: `app/api/clusters.py:154,174,194,224` · `app/models/cluster.py` · `frontend/app/temas/page.tsx:262,472` · `frontend/lib/api.ts:270,297`
- Receita/gravidade (reuso): `app/api/admin.py:962,1010,1052,1104` · `app/domain/selos_vivos.py:100`
- Roadmap/loop: `app/api/admin.py:2105,2323,2467,2699,2823` · `app/models/improvement.py` · `app/models/feedback.py:38,44,51` · `frontend/app/melhorias/page.tsx` · `frontend/lib/api.ts:934,960,1000,1430`
- Menu: `frontend/components/Sidebar.tsx:35,47`
- Scratchpad de análise: `.specs/scratchpad/063bfc1b.md`
