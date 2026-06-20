# Benchmark de Customer Success — Escuta × líderes do mercado (2026-06-20)

> Estudo pedido pelo dono (item **J** do `FEEDBACK_DONO_2026-06-20.md`): comparar as capacidades de
> Customer Success dos produtos líderes com o que o **Escuta** já tem e o que falta. Honesto e
> acionável — não é marketing. Onde uma capacidade **já existe no código**, está citado o arquivo,
> para não recomendarmos reconstruir o que já temos.
>
> **Leitura do mercado:** os líderes se dividem em dois grupos. (a) **CS Platforms B2B** puro-sangue —
> Gainsight, Vitally, Planhat, Custify — focados em contas/ARR, health score, playbooks e renovação;
> (b) **plataformas de mensageria/suporte** — Intercom, Zendesk — fortes em conversa multicanal + IA,
> mas fracos em CS "de conta". **Nenhum dos dois grupos faz o que o Escuta faz: coletar feedback E agir
> em cima dele direto no WhatsApp, com LLM, sem o cliente sair da conversa.** Esse é o diferencial (§3).
>
> **Escala importa:** os líderes B2B são feitos para CSMs gerindo carteiras de centenas de contas de
> ticket alto (ARR). O Escuta/Bizzu mira o **dono/operador de uma edtech B2C com milhares de assinantes
> baratos** — a unidade não é "conta", é "assinante", e quem opera é o dono, não um time de CS. Isso
> muda o que faz sentido copiar: features de "QBR/Success Plan por conta" valem pouco; features de
> **triagem em massa + ação rápida no WhatsApp** valem muito.

---

## (1) Tabela — capacidade de CS × líderes × Escuta hoje × gap

Legenda Escuta: **Sim** = existe e funciona · **Parcial** = existe em parte / cru · **Não** = não existe.

| # | Capacidade de CS | O que os líderes têm | Escuta hoje | Gap (o que falta) |
|---|---|---|---|---|
| 1 | **Health Score** (saúde da conta 0-100) | Gainsight/Custify/Planhat/Vitally: scorecards configuráveis multi-sinal (uso, suporte, billing, NPS); cada vez mais com ML | **Sim** — `app/domain/cs/health.py`: 0-100, 5 sinais (NPS, perfil, recência, sentimento, assinatura), banda healthy/watch/at_risk, **`factors` auditável** (explica cada ajuste) | Expor na UI com a explicação dos fatores; deixar os pesos/regras **editáveis** pelo dono (hoje são fixos no código) |
| 2 | **Playbooks** (gatilho → ação) | Gainsight Cockpit/CTAs, Custify/Vitally visual builder; automatizam onboarding, risco, renovação | **Sim** — `app/domain/cs/engine.py`: 5 gatilhos (`nps_detractor`, `health_at_risk`, `inactive_days`, `renewal_soon`, `churn_detected`) → `create_task`/`alert_owner`; **idempotente** (`dedup_key`), `dry_run` por padrão, sem `eval` | Flag `PLAYBOOKS_INLINE_ENABLED` está **OFF** e o dono achou "automático demais". Manter opt-in + **modo sugestão** (propõe, dono aprova) em vez de agir sozinho |
| 3 | **Segmentação da base** | Segmentos salvos/nomeados, dinâmicos, usados em automação e relatórios | **Parcial** — filtros ad-hoc em Clientes (contatáveis/winback/at_risk, `tem_whatsapp`); perfis de churn calculados no sync | **Segmentos salvos e nomeados** (ex.: "detratores sem abordagem", "renova em 7d"); reusar como filtro rápido e como público de pesquisa/playbook |
| 4 | **Customer 360 / timeline** | Perfil único com uso, tickets, e-mails, NPS, eventos numa linha do tempo | **Sim** — ficha `/contatos/{id}` com perfil+assinatura, conversa e **timeline editável**; dados via `profile_data.partner` (API Clientes Bizzu) | Puxar **mais dados de assinatura** (data que assinou, ciclo, valor, renovação) como eventos na timeline; corrigir a ficha "quebrada" (item D do feedback) |
| 5 | **NPS / CSAT** | Surveys NPS/CSAT nativos, gatilhos por evento, loop fechado | **Sim** — pesquisas NPS no WhatsApp + ingestão de NPS in-app; agregação em `central.py` (`/central/nps`, média das 2 fontes, buckets) | CSAT pós-resolução (1 pergunta após fechar um caso); **a conversa de NPS ainda é cega à nota** (follow-up fixo até para detrator — ver §2) |
| 6 | **Coleta + ação no canal do cliente (WhatsApp)** | **Raro.** Intercom/Zendesk conversam no WhatsApp mas **não** fecham o loop de CS ali; CS Platforms B2B vivem em e-mail/in-app | **Sim — DIFERENCIAL** (ver §3): coleta NPS, detecta intent, escala para humano e age, tudo no WhatsApp + LLM (Groq) | — (é a vantagem; o gap é só operacional: religar o WAHA em prod) |
| 7 | **Fila/tarefas de CS** | Cockpit/inbox de CTAs, tarefas por conta com dono/SLA | **Sim** — `CsTask` (modelo + `/api/tarefas`), "+tarefa" no card do feedback, dono/prioridade/SLA, dedup | Tela/visão de fila priorizada ("quem abordar primeiro") — hoje a tarefa existe mas falta a **fila ordenada por risco × silêncio** |
| 8 | **Churn / risco proativo** | Predição de churn, alertas de risco, "early warning" | **Parcial** — gatilhos `churn_detected`/`health_at_risk`/`inactive_days` existem no motor; perfis de churn no sync | Falta o **resumo proativo** ("X detratores novos esta semana", "Y em risco sem abordagem há N dias") na home — item I do feedback (digest já existe no backend) |
| 9 | **Mapa de dores / clustering de temas** | Parcial nos líderes (tags, alguns com IA de tópicos) | **Sim** — clustering semântico pgvector (`clustering/engine.py`), separa por sentimento, rotula via LLM | Virar **"Mapeamento" visual** (dor por volume × impacto, filtro por tipo/origem) — item G do feedback |
| 10 | **Roadmap "você pediu, a gente fez"** (loop fechado) | Parcial (alguns ligam a Productboard/Canny) | **Sim** — tela Melhorias + `/api/improvements/roadmap` + `from-cluster` | Está **escondido** (saiu do menu); reavaliar se vira parte de "Mapeamento" ou volta como aba |
| 11 | **IA conversacional / copiloto** | Forte: Intercom Fin (resolve ~67% sozinho), Gainsight Copilot, resumos/QBR por IA | **Parcial** — LLM já interpreta NPS, classifica intent, faz hand-off e roda o agente VoC (`VOC_*`, atrás de flag) | **Copiloto do dono**: "resuma esta conta", "rascunhe a resposta para este detrator", "o que pedem mais este mês" — reusa Groq + clustering + health |
| 12 | **Renovação / expansão / forecasting** | Núcleo dos B2B (Gainsight Renewal Center, NRR, upsell por sinal de uso) | **Não** (e **fora de escopo** para B2C de assinatura barata) | Não recomendado copiar: a unidade da Bizzu é assinante recorrente, não conta de ARR com QBR/upsell manual |
| 13 | **Success Plans / QBR** | Núcleo dos B2B enterprise (planos por conta, portais compartilhados) | **Não** (**fora de escopo**) | Não recomendado: não há "conta enterprise" para um plano de sucesso individual |
| 14 | **Apagar/gerir os próprios dados (self-service)** | Sim (CRUD pleno na UI) | **Parcial** — `DELETE /api/feedbacks/{id}` existe; apagar **contato** é só via script | Ação de excluir contato pela UI com confirmação — item H do feedback |

---

## (2) Os 5-7 recursos que mais fariam diferença (valor × esforço)

Priorizados para o **Escuta/Bizzu** (dono operando, base B2C grande). Quase tudo reusa peças que já
existem — por isso o esforço é baixo.

1. **Resumo proativo na home ("o que importa hoje").** *(valor ALTO · esforço BAIXO)* — Um bloco no topo
   da Monitorar: "N detratores novos esta semana · M em risco sem abordagem há ≥X dias · NPS vs. semana
   passada". Reusa `health.py` + o digest semanal que já existe. É o que transforma a base rica em ação.

2. **Fila "quem abordar primeiro".** *(valor ALTO · esforço BAIXO-MÉDIO)* — Ordenar contatos por risco
   (Health) × silêncio (recência) e mostrar como fila de trabalho. `CsTask` e `compute_health` já
   existem; falta a ordenação e a tela.

3. **Conversa de NPS ciente da nota + IA de resposta ao detrator.** *(valor ALTO · esforço MÉDIO)* —
   Hoje o follow-up é fixo ("Massa! 🙌") mesmo para quem deu nota baixa. Ramificar por bucket
   (detrator → "o que aconteceu?"; promotor → indicação) e oferecer ao dono um **rascunho de resposta**
   gerado pelo LLM. Fecha o loop no canal — o diferencial só vale se a conversa for inteligente.

4. **Health Score visível + explicável + editável.** *(valor MÉDIO-ALTO · esforço BAIXO)* — `factors`
   já carrega a explicação; basta exibir ("por que esta conta está em risco") na ficha e na lista, e
   deixar os pesos ajustáveis em `Organization.settings` (mesmo padrão dos boards, sem migration).

5. **Segmentos salvos e nomeados.** *(valor MÉDIO-ALTO · esforço MÉDIO)* — Transformar os filtros
   ad-hoc em segmentos com nome ("detratores sem abordagem", "renova em 7d") reutilizáveis como filtro
   rápido, público de pesquisa e gatilho de playbook. É o que dá alavancagem em base grande.

6. **Playbooks em "modo sugestão" (opt-in).** *(valor MÉDIO · esforço BAIXO)* — O motor já existe e é
   idempotente; o dono só não quer automação cega. Rodar em `dry_run` e **sugerir** tarefas/alertas para
   o dono aprovar — mantém o controle humano que ele pediu sem jogar fora o que já foi construído.

7. **"Mapeamento" visual de dores + apagar dados pela UI.** *(valor MÉDIO · esforço MÉDIO)* — Promover o
   clustering (`clustering/engine.py`) a um mapa volume × impacto com filtros (itens G), e dar ao dono o
   botão de excluir contato/feedback na tela (item H). Tira a dependência de script e responde a dois
   pedidos diretos do feedback.

> **Deliberadamente fora:** Renovação/forecasting, Success Plans e QBR (linhas 12-13). São o coração dos
> CS Platforms B2B, mas pressupõem contas de ARR e um time de CSMs — não a realidade de uma edtech B2C
> com assinatura barata. Copiá-los seria gold-plating.

---

## (3) O diferencial do Escuta

**Coletar feedback e agir em cima dele, direto no WhatsApp, com LLM — sem o cliente sair da conversa.**

Os líderes ficam de um lado **ou** do outro desta linha, nunca dos dois:

- **CS Platforms B2B (Gainsight, Vitally, Planhat, Custify):** ótimos em health score, playbooks e
  renovação — mas a operação vive em **e-mail e in-app**, voltada a um **CSM gerindo contas de ARR**. O
  cliente final não está na conversa; o canal é assíncrono e corporativo.
- **Mensageria/Suporte (Intercom, Zendesk):** falam WhatsApp muito bem e têm IA forte (Fin resolve ~67%
  dos tickets sozinho), mas são **reativos a tickets** — não fecham o loop de **Customer Success de
  conta** (saúde, risco, fila proativa, mapa de dores) dentro do canal. WhatsApp ali é só mais um inbox
  de suporte (a própria Zendesk não suporta nem botão de CSAT no WhatsApp).

O Escuta junta as duas metades **no canal onde o cliente B2C realmente responde** (WhatsApp, não e-mail):
dispara NPS, **interpreta a resposta com LLM**, detecta intenção de churn/hand-off, **escala para humano**,
**clusteriza as dores** e alimenta Health Score + fila de ação — tudo no mesmo fio de conversa. Para uma
edtech B2C com milhares de assinantes, isso é estruturalmente diferente: **taxa de resposta de WhatsApp >>
e-mail**, e a ação acontece onde a atenção do cliente está. Esse é o fosso; o resto da tabela é paridade.

> **Honestidade:** o diferencial só é real se (a) o **WAHA voltar a rodar em prod** (hoje está fora — Chat/
> envio inativos) e (b) a **conversa for inteligente de ponta a ponta** (hoje o follow-up de NPS é cego à
> nota — §2, item 3). Sem isso, vira "só mais um disparador de pesquisa".

---

## (4) Roadmap de CS em 3 ondas

Sequência pensada para entregar valor cedo reusando o que já existe, sem brigar com os P0/P1 de bug e
design que o dono já priorizou no `FEEDBACK_DONO_2026-06-20.md`.

### Onda 1 — Curto prazo: "tornar visível o que já temos" (baixo esforço, alto valor)
- **Resumo proativo na home** (§2.1) — bloco "o que importa hoje" reusando Health + digest.
- **Health Score visível e explicável** na ficha e na lista (§2.4) — só expor os `factors`.
- **Conversa de NPS ciente da nota** (§2.3, parte 1) — ramificar follow-up por bucket.
- *Pré-requisito de plataforma:* **religar o WAHA em prod** (sem ele o diferencial está desligado).

### Onda 2 — Médio prazo: "operar a base de forma inteligente" (valor alto, esforço médio)
- **Fila "quem abordar primeiro"** (§2.2) — ordenação risco × silêncio sobre `CsTask`.
- **Segmentos salvos e nomeados** (§2.5) — em `Organization.settings`, reusáveis em filtro/pesquisa/playbook.
- **Playbooks em modo sugestão** (§2.6) — `dry_run` + aprovação do dono.
- **IA de resposta ao detrator** (§2.3, parte 2) — rascunho via Groq na ficha/fila.

### Onda 3 — Longo prazo: "inteligência e autonomia do dono" (maior esforço / mais maturação)
- **"Mapeamento" visual de dores** (volume × impacto, filtros) — promove o clustering (item G).
- **Copiloto do dono** (§ tabela 11) — "resuma esta conta", "o que pedem mais este mês", sobre Groq + clustering + health.
- **Self-service de dados** — apagar contato/feedback pela UI (item H) + tipos/origem/status customizáveis (itens F/G).
- **Status e tipos customizáveis** alimentando os boards/colunas (item F) — fecha a régua de "gerir do meu jeito".

---

## Resumo do que JÁ existe no código (para não reconstruir)
- **Health Score 0-100 auditável** com 5 sinais e bandas → `app/domain/cs/health.py`.
- **Motor de Playbooks** (5 gatilhos → tarefa/alerta, idempotente, dry-run, sem eval) → `app/domain/cs/engine.py`.
- **Tarefas de CS** (`CsTask`, dono/SLA/prioridade/dedup) + "+tarefa" no card.
- **Central agregada** (NPS de 2 fontes, feedbacks por fonte/sentimento, segmentos churn/ativos) → `app/api/central.py`.
- **Coleta + hand-off + agente no WhatsApp com LLM** (Groq) — o diferencial.
- **Clustering semântico de dores** (pgvector) → `clustering/engine.py`.
- **Roadmap "você pediu, fizemos"** → tela Melhorias + `/api/improvements/*`.

## Fontes (pesquisa de mercado)
- Gainsight — [features: health scores, playbooks](https://www.oliv.ai/blog/gainsight-features) · [CS overview](https://www.gainsight.com/customer-success/) · [essential guide](https://www.gainsight.com/essential-guide/customer-success/)
- Vitally / Planhat / Custify — [Vitally vs Gainsight vs Planhat](https://www.vitally.io/post/planhat-gainsight-vitally-which-csp-is-best) · [health score software](https://thecxlead.com/tools/best-customer-health-score-software/) · [Custify vs Planhat](https://www.g2.com/compare/custify-vs-planhat)
- Custify — [CS platform](https://www.custify.com/customer-success-platform) · [health score guide](https://www.custify.com/blog/customer-health-score-guide/)
- Intercom (Fin, WhatsApp, multicanal) — [Fin AI guide 2026](https://myaskai.com/blog/intercom-fin-ai-agent-complete-guide-2026) · [Intercom review 2025](https://hiverhq.com/blog/intercom-review)
- Zendesk (CSAT, WhatsApp, proativo) — [WhatsApp business](https://www.zendesk.com/service/messaging/whatsapp-business/) · [CSAT em messaging](https://support.zendesk.com/hc/en-us/articles/4408832620570-About-CSAT-ratings-in-messaging) · [retenção](https://www.zendesk.com/blog/customer-experience/retention/customer-retention/)
- Capacidades canônicas de CS (success plans, QBR, forecasting, NPS) — [Planhat playbooks](https://www.planhat.com/customer-success/playbooks) · [NPS para CS](https://www.zonkafeedback.com/blog/nps-for-customer-success)
