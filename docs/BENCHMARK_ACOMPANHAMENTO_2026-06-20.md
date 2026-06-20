# Benchmark de Acompanhamento do Cliente — Timeline, Status e Follow-up (2026-06-20)

> Estudo pedido pelo dono (item **F** do `FEEDBACK_DONO_2026-06-20.md`): a "Linha do tempo do cliente"
> precisa fazer sentido para **acompanhar relacionamento**, não para rastrear bug. Os status de hoje
> (`novo / em_analise / planejado / resolvido / descartado`) têm cara de **bug-tracker** — descrevem o
> ciclo de vida de uma *tarefa de engenharia*, não o de uma *conversa com cliente*.
>
> Foco da pesquisa: como os líderes (Intercom, HubSpot, Pipedrive, Salesforce, Close, Zendesk, Vitally,
> Gainsight, Planhat, Custify) fazem (1) **timeline/activity feed**, (2) **status/estágios** e (3)
> **follow-up** (tarefas, lembretes, cadência, próximo passo, snooze/reabordar). Honesto e acionável.
> Complementa o `BENCHMARK_CS_2026-06-20.md` (que olhou o quadro geral de CS); aqui o recorte é
> **acompanhamento manual 1:1 de um cliente na ficha**.
>
> **Achado central:** os líderes usam **dois eixos de status distintos**, e o Escuta hoje confunde-os
> num só. (a) **Estágio do RELACIONAMENTO** (lifecycle/health: onde o cliente está na jornada — lead,
> ativo, em risco, churned) é macro, muda devagar e descreve a *conta*. (b) **Status da CONVERSA/AÇÃO**
> (open/snoozed/closed; a-fazer/feito) é micro, muda toda hora e descreve *este toque específico*. O
> `action_status` do Escuta é nominalmente "ação", mas o vocabulário herdado (`em_analise`/`planejado`)
> é de **fila de produto** ("vamos analisar e planejar esta sugestão"), não de **fila de relacionamento**
> ("preciso falar com este cliente e estou esperando ele responder"). É por isso que "não faz sentido".

---

## (1) Tabela — como os líderes fazem Timeline × Status/Estágios × Follow-up

| Produto | Timeline / activity feed | Status / estágios (os nomes reais) | Follow-up (próximo passo, lembrete, cadência, snooze) |
|---|---|---|---|
| **Intercom** | Timeline da conversa + perfil do cliente; mudanças de status e respostas entram como eventos. | **Conversa:** `Open` · `Snoozed` · `Closed`. Simples e de propósito: "snooze = ainda ativo, mas em espera". | **Snooze por tempo** é o coração: tira da fila e **reabre sozinho** quando o prazo vence **ou o cliente responde**. "Closed" só quando resolvido — se está esperando o cliente, **mantém snoozed, não fecha**. |
| **HubSpot** | Timeline do contato unifica e-mails, ligações, notas, mudanças de estágio, tarefas. | **Dois eixos separados, de propósito:** *Lifecycle stage* (macro: Subscriber→Lead→…→Customer→Evangelist; editável, **só avança**) e *Lead status* (micro/tático: `Attempted to contact`, `Connected`, `Open deal`, `Unqualified`). Deal stages é um 3º eixo (pipeline). | Tarefas com vencimento + lembrete; automação cria a tarefa de follow-up quando o estágio muda. Fila diária do que vence hoje. |
| **Pipedrive** | "Atividades" na timeline do negócio/pessoa; o que está **vencido/a-vencer** salta à vista. | Estágios do **pipeline** (customizáveis) + atividades com status **planejada / concluída**. Filosofia "activity-based selling": sempre existe **uma próxima atividade agendada**. | **Próximo passo obrigatório:** o sistema cobra que todo negócio tenha a próxima atividade marcada; **e-mail diário** com as atividades do dia; "deal rotting" sinaliza negócio parado há X dias. |
| **Salesforce / Close** | Activity timeline (ligações, e-mails, tarefas, mudanças de campo). | Lead status + estágio de oportunidade; tarefas `Open`/`Completed`. | **Cadences/Sequences:** passos com **delays** ("ligar em 3 dias"), com **branching** por comportamento; o próximo passo só dispara se o cliente **não respondeu/não mudou de status**. Mudança de status **pausa** a cadência. |
| **Zendesk** | Timeline do ticket; eventos de status. | **Ticket:** `New` · `Open` · `Pending` (esperando o cliente) · `On-hold` (esperando interno/terceiro) · `Solved` · `Closed`. | `Pending`/`On-hold` são exatamente o "estou esperando retorno"; automações reabrem/escalam por tempo parado. |
| **Gainsight** | Timeline da conta (toques, e-mails, reuniões) + Cockpit de CTAs. | **Lifecycle stages** da conta (Onboarding→Adoption→Engagement→Renewal→Growth) + **CTAs** (Call to Action) com status próprio. | **CTA = "isto pede ação"**, com playbook (lista de passos), dono e SLA; regra dispara CTA quando a conta fica **parada num estágio além do esperado** ou a saúde cai. |
| **Vitally / Planhat / Custify** | Customer 360 com timeline de eventos (uso, NPS, tickets, e-mails). | **Health stages / lifecycle:** Onboarding · Adopted/Engaged · **At-Risk** · Renewal · Advocate · Churned. Health score (cor) por cima. | Playbooks com tarefas e datas; **tarefa `open`/`done`**; renovação abre workflow com tarefas pré-preenchidas; alerta quando entra em **At-Risk**. |

**Padrões que se repetem (e que importam para o Escuta):**

1. **Separam "estágio do relacionamento" de "status do toque".** Lifecycle/health ≠ open/snoozed/done. O
   Escuta tem o estágio do relacionamento **resolvido por outro caminho** (o **Health Score** de
   `app/domain/cs/health.py`: `healthy/watch/at_risk`, mais o `estado` da assinatura). Então o
   `action_status` **não precisa carregar a jornada** — só o **status do acompanhamento deste sinal**.
2. **"Esperando o cliente" é um status de primeira classe.** Intercom `Snoozed`, Zendesk `Pending`,
   tarefa de cadência aguardando resposta. É o estado mais comum no dia a dia de relacionamento e **o
   Escuta não tem** — `em_analise` não é isso (é "estou olhando", não "a bola está com o cliente").
3. **Sempre existe um "próximo passo".** Pipedrive cobra a próxima atividade; Gainsight tem a CTA aberta;
   cadências têm o próximo step agendado. Acompanhamento sem "quando voltar a falar" vira esquecimento.
4. **Reabrir é automático e barato.** Resposta do cliente ou prazo vencido **reabre** o item. Fechar não
   é "arquivar para sempre" — é "por ora, resolvido"; se o cliente voltar, reabre.
5. **Fechamento tem dois sabores:** *resolvido* (deu certo) vs *perdido/sem retorno/descartado* (acabou
   sem desfecho positivo). Os líderes distinguem para medir taxa de sucesso do acompanhamento.

---

## (2) RECOMENDAÇÃO — conjunto de status de acompanhamento para o Escuta

**Princípio:** trocar o vocabulário de *fila de produto* por *fila de relacionamento*. São 6 status que
cobrem o ciclo de um toque manual: **a abordar → aguardando retorno → em acompanhamento → resolvido**,
com duas saídas terminais (**sem retorno**, **descartado**). Mapeiam quase 1:1 nos pares Intercom
(open/snoozed/closed) e Zendesk (open/pending/solved), e batem com a própria sugestão do dono no item F
("a contatar / aguardando retorno / resolvido / perdido").

> Implementação: **encaixa perfeitamente no que já existe** — `/api/config` (PUT) já guarda status como
> `{key, label, cor}` em `Organization.settings`, e a ficha já consome essa lista (`statusOptions`). Hoje
> os 6 defaults nascem todos com a mesma cor (`_COR_STATUS_DEFAULT = "#6366f1"`) e label derivado da key.
> A recomendação é **mudar os DEFAULTS** (as keys/labels/cores abaixo viram `ACTION_STATUSES` +
> `_status_default_items()`), mantendo o mecanismo de customização intacto.

### Os status propostos

| key (interno) | label (PT) | Significado (quando usar) | Cor | Equivale a |
|---|---|---|---|---|
| `a_abordar` | **A abordar** | Sinal novo que ainda **não foi tocado**. A bola está com a gente: precisa falar com o cliente. (Substitui `novo`.) | `#6366f1` indigo (neutro/novo) | Intercom *Open* (novo) · HubSpot *Attempted to contact* (antes) |
| `aguardando_retorno` | **Aguardando retorno** | Já falamos; **a bola está com o cliente**. Sai da fila ativa e deve **reabrir** quando ele responder ou o prazo vencer. *(Estado-chave que faltava.)* | `#f59e0b` âmbar (espera) | Intercom *Snoozed* · Zendesk *Pending* |
| `em_acompanhamento` | **Em acompanhamento** | Caso **ativo e em andamento** da nossa parte (conversa em curso, tratativa rolando). A bola está com a gente. (Substitui `em_analise`+`planejado`.) | `#3b82f6` azul (ativo) | Zendesk *Open* · Gainsight *CTA aberta* |
| `resolvido` | **Resolvido** | Fechado **com desfecho positivo** (cliente atendido, dúvida sanada, churn revertido). Terminal — mas **reabre** se o cliente voltar. | `#10b981` verde (sucesso) | Intercom/Zendesk *Closed/Solved* (ok) |
| `sem_retorno` | **Sem retorno** | Tentamos abordar e o cliente **não respondeu** depois de N tentativas/dias. Terminal "neutro" — diferente de resolvido (não deu certo) e de descartado (não tentamos). | `#94a3b8` cinza (esfriou) | Cadência *no-reply* · Intercom *unresponsive* |
| `descartado` | **Descartado** | **Não pede ação** (ruído, duplicado, fora de escopo, resolvido por outro canal). Terminal "arquivar". (Mantém a key — preserva dados.) | `#64748b` ardósia (arquivado) | Zendesk *Closed (no action)* |

**Por que 6 e não 4:** os 4 do dono ("a contatar/aguardando/resolvido/perdido") são o esqueleto certo,
mas a operação real precisa distinguir (a) **a bola está com a gente e ainda não comecei** (`a_abordar`)
de **estou no meio** (`em_acompanhamento`) — senão tudo vira "a abordar" e a fila perde sentido; e (b)
**não deu certo / o cliente sumiu** (`sem_retorno`) de **nem era pra agir** (`descartado`) — duas saídas
que medem coisas diferentes (eficácia do follow-up vs. triagem de ruído). Seis é o teto: mais que isso e
o dono não consegue decidir rápido (regra de ouro de UX de status — Intercom usa 3, Zendesk 6).

### Como migrar dos atuais SEM quebrar dados

O `action_status` é uma **string livre** validada na API (não há `CHECK`/enum no banco; ver comentário em
`ACTION_STATUSES`). Logo, mudar o vocabulário **não exige migration de schema** — mas os **valores já
gravados** (`novo`, `em_analise`, `planejado`) precisam ou ser remapeados ou continuar aceitos.

**Mapa de migração proposto:**

| Status atual | → Novo status | Observação |
|---|---|---|
| `novo` | → `a_abordar` | renomeação semântica direta |
| `em_analise` | → `em_acompanhamento` | "estou olhando" ≈ "caso ativo da nossa parte" |
| `planejado` | → `em_acompanhamento` | funde com o de cima (era a mesma "fila ativa") |
| `resolvido` | → `resolvido` | **inalterado** (key e significado mantidos) |
| `descartado` | → `descartado` | **inalterado** |
| *(novo)* | `aguardando_retorno`, `sem_retorno` | não existem hoje; só passam a ser oferecidos |

**Duas estratégias (recomendo a A):**

- **A — Backfill único + troca dos defaults (limpo, recomendado).** (1) Um `UPDATE` em lote por org:
  `novo→a_abordar`, `em_analise→em_acompanhamento`, `planejado→em_acompanhamento` (script standalone, no
  padrão dos outros `scripts/` — lembrar do `truststore.inject_into_ssl()` e de exportar `DATABASE_URL`).
  (2) Trocar `ACTION_STATUSES` e `_status_default_items()` para as 6 keys/labels/cores acima. (3) Atualizar
  o `STATUS_OPTIONS_FALLBACK` do front (`contatos/[id]/page.tsx`) e o `_FEEDBACK_TERMINAL_STATUSES`.
  **Ponto de atenção (load-bearing):** `_FEEDBACK_TERMINAL_STATUSES = {resolvido, descartado}` controla a
  esteira (auto-resolve ao entregar melhoria) e a idempotência — ao adicionar terminais, decidir se
  `sem_retorno` também é terminal (recomendo **sim**: a esteira não deve reabrir um "sem retorno").

- **B — Só trocar defaults, sem backfill (zero-touch, mas convive com legado).** As keys antigas viram
  "órfãs": o front já tem `withCurrentStatus()`, que **injeta a key atual no select mesmo fora do
  vocabulário** — então um item gravado como `em_analise` continua aparecendo e editável, mas como label
  cru `em_analise`. Funciona sem script, porém deixa rótulos feios no histórico. Bom para um deploy
  imediato; faça o backfill (A) logo depois.

**Compatibilidade garantida em ambos:** como não há enum no banco e a validação usa a **lista efetiva**
(`effective_status_keys = defaults ∪ custom`), nenhum valor existente quebra a aplicação; o pior caso (B)
é só estético. Orgs que já tiverem **status customizados** em `settings` ficam intactas (defaults nunca
sobrescrevem custom).

---

## (3) Ideias de melhoria — Timeline ("Acompanhamento do cliente") e Follow-up

### 3.1 Renomear e reposicionar a timeline
- **"Linha do tempo do cliente" → "Acompanhamento do cliente"** (ou manter "Linha do tempo" como subtítulo).
  O nome atual descreve um *log*; o que o dono quer é uma *ferramenta de relacionamento*. Pequena mudança
  de cópia, grande mudança de intenção — alinha com o vocabulário novo de status.
- **Topo da ficha: faixa de "estado atual do relacionamento"** (reusa o que já existe, não inventa):
  Health Score + banda (`healthy/watch/at_risk` de `health.py`) + estado da assinatura + **status do
  acompanhamento aberto** (se houver um `a_abordar`/`aguardando_retorno`/`em_acompanhamento`). Responde de
  relance "como está este cliente e o que devo fazer". É o "header de conta" de Gainsight/Vitally.

### 3.2 "Próximo passo" / lembrete de reabordar (o maior gap vs. líderes)
Hoje a ficha registra o passado (timeline) mas **não agenda o futuro**. Os líderes giram em torno disso.
Há duas formas, da mais leve à mais completa:

- **Leve (campo na própria ação):** ao mudar o status para `aguardando_retorno`, perguntar **"reabordar
  em quê?"** (3d / 7d / data) e gravar um `follow_up_at` no `FeedbackItem`. A ficha e a fila destacam o
  que **venceu** ("reabordar este cliente — combinado há 5 dias"). É o **snooze do Intercom** + o "deal
  rotting" do Pipedrive, no nosso modelo. Esforço baixo (1 coluna nova ou um campo em `profile_data`).
- **Completa (tarefa de CS):** reusar o **`CsTask`** que **já existe** (modelo + `/api/tarefas`, com
  dono/prioridade/SLA/dedup — ver `BENCHMARK_CS_2026-06-20.md`). "Aguardando retorno" cria/atualiza uma
  `CsTask` com vencimento; a fila "quem abordar primeiro" (item I do feedback) lista as vencidas. Não
  precisa construir motor de tarefa — **já está pronto**, falta ligar à ficha e ordenar.

### 3.3 Reabrir automático (paridade barata com Intercom/Zendesk)
- Quando chega **mensagem do cliente no WhatsApp** (inbound já tratado pelo resolver) **ou** vence o
  `follow_up_at`, um item terminal/aguardando volta para `a_abordar` (ou destaca "reabriu"). Fecha o loop
  de "não fechei de verdade, só estava esperando". Reusa o ingest de mensagens que já existe.

### 3.4 Cadência leve de reabordagem
- Não precisa de motor de sequência tipo Salesforce. Basta: para quem está `aguardando_retorno` há mais
  de N dias **sem resposta**, sugerir (modo opt-in, não automático — o dono pediu controle humano) "2ª
  tentativa" e, depois de M dias, propor marcar `sem_retorno`. Reusa o **motor de Playbooks**
  (`app/domain/cs/engine.py`, gatilho tipo `inactive_days`) em **modo sugestão**.

### 3.5 Acabamento da timeline (já que vamos mexer)
- **Cor por status na bolinha/badge:** hoje a bolinha (`tl-dot`) é colorida por *sentimento*; adicionar a
  **cor do status** (o `cor` do config) no badge de status torna a fila legível de relance (verde
  resolvido, âmbar aguardando, azul em acompanhamento). O `cor` já trafega no `/api/config` — o front só
  não o usa ainda no select/badge.
- **Agrupar "marcos" vs "toques":** a timeline já funde `FeedbackItem` + `SurveyResponse` + marco de
  assinatura. Vale puxar **mais marcos de assinatura como eventos** ("assinou em DD/MM", "cancelou em
  DD/MM") — é o item F do feedback e o que dá textura de "jornada" (estilo HubSpot timeline). Nota: o
  snapshot `partner.subscription` hoje só traz `currentPeriodEnd`/`daysAsSubscriber` (não a data de
  assinatura nem valor — ver `PartnerSub` no front); puxar mais campos depende da API de Clientes Bizzu.
- **Filtro rápido na timeline:** "só abertos" / "só desta fonte" — quando o histórico cresce, ajuda a
  focar no que pede ação (paridade com filtro de inbox).

### 3.6 Fechamento que mede sucesso
- Com `resolvido` vs `sem_retorno` vs `descartado` separados, dá para mostrar na Monitorar/digest a **taxa
  de resolução do acompanhamento** ("dos detratores abordados este mês, X% resolvidos, Y% sem retorno").
  É o que transforma o acompanhamento manual em métrica — e responde "o follow-up está funcionando?".

---

## Resumo do que JÁ existe (para não reconstruir)
- **Status customizáveis por org** com `{key, label, cor}` → `/api/config` (GET/PUT) em
  `app/api/admin.py`; lista efetiva = `defaults ∪ custom`; front já consome (`statusOptions`).
- **Timeline 360 unificada** (FeedbackItem + SurveyResponse + marco de assinatura), com status e
  "abordado" **editáveis inline** → `frontend/app/contatos/[id]/page.tsx` + `GET /contacts/{id}/360`.
- **Health Score** (`healthy/watch/at_risk`, auditável) → `app/domain/cs/health.py` (é o "estágio do
  relacionamento" — o eixo macro; por isso o `action_status` só precisa ser o eixo micro).
- **Tarefas de CS** (`CsTask`, dono/SLA/prioridade/dedup) + **Playbooks** (`app/domain/cs/engine.py`,
  gatilho `inactive_days`, dry-run) — base pronta para "próximo passo" e "cadência de reabordagem".
- **`withCurrentStatus()`** no front injeta status legado no select → migração B é zero-touch.
- **Ponto de atenção:** `_FEEDBACK_TERMINAL_STATUSES = {resolvido, descartado}` é load-bearing (esteira
  auto-resolve + idempotência) — atualizar junto com qualquer novo terminal (`sem_retorno`).

## Fontes (pesquisa de mercado, jun/2026)
- **Intercom** (open/snoozed/closed, auto-reabrir) — [Snooze a conversation](https://www.intercom.com/help/en/articles/6564538-snooze-a-conversation) · [Close a conversation](https://www.intercom.com/help/en/articles/8363763-close-a-conversation) · [Auto-close inactive](https://www.intercom.com/help/en/articles/9636573-auto-close-inactive-conversations) · [Customer unresponsive](https://www.intercom.com/help/en/articles/7155449-customer-or-teammate-has-been-unresponsive)
- **HubSpot** (lifecycle stages × lead status × deal stages) — [Lifecycle & Lead Status 2026](https://content.hubjoy.co/hubspot-lifecycle-stages-lead-status-8-proven-alignment-tips) · [Full 2026 guide (Default)](https://www.default.com/post/hubspot-lead-status-lifecycle-stages) · [Mapping your sales process (HQ Digital)](https://www.hq-digital.com/blog/mapping-your-sales-process-101-hubspot-lifecycle-stages-lead-statuses-and-deal-stages)
- **Pipedrive** (activity-based, próximo passo, lembrete diário) — [Activities & Goals](https://www.pipedrive.com/en/features/activities-goals) · [Processes & pipeline activities](https://www.pipedrive.com/en/products/sales/processes-pipeline-activities) · [Sequences](https://www.pipedrive.com/en/blog/sequences-in-pipedrive)
- **Salesforce / Close** (cadences, delays, branching, pausa por status) — [Salesforce Cadence objects](https://developer.salesforce.com/docs/sales/sales-engagement/guide/sales-cadence-objects.html) · [Cadence automation tools](https://help.salesforce.com/s/articleView?id=sales.hvs_cadences_automation_tools.htm&language=en_US&type=5) · [Pause sequence on status change (Zapier/Close)](https://zapier.com/automations/sales/outbound-sales/sales-sequencing/pause-outreach-sequences-when-lead-status-changes-for-reps)
- **Gainsight** (lifecycle stages + CTAs + Rules Engine) — [Define key stages](https://communities.gainsight.com/define-and-structure-the-customer-lifecycle-233/define-key-stages-in-the-customer-lifecycle-26567) · [Set transition criteria](https://communities.gainsight.com/define-and-structure-the-customer-lifecycle-233/set-transition-criteria-for-lifecycle-stages-26568) · [Essential guide: lifecycle](https://www.gainsight.com/essential-guide/the-customer-journey-and-lifecycle/)
- **Vitally / Planhat / Custify** (health stages, at-risk, tarefas/playbooks) — [Planhat lifecycle](https://www.planhat.com/customer-success/lifecycle) · [Planhat playbooks](https://www.planhat.com/customer-success/playbooks) · [CS lifecycle stages (ZapScale)](https://www.zapscale.com/blog/customer-success-lifecycle)
- **Zendesk** (New/Open/Pending/On-hold/Solved/Closed) — referência canônica de status de ticket de suporte (usada no benchmark de CS deste repo).
