# Sistema de feedback NATIVO da Bizzu (pré-Escuta) — inventário completo

> Levantamento fiel ao código (backend + frontend clonados em `bizzu-repos/`), feito por 2 agentes em
> 09/06/2026, com `arquivo:linha`. Responde: **o que a Bizzu já tinha para ouvir o cliente ANTES do
> Escuta** — para o Escuta complementar, não duplicar. Corrige simplificações de docs anteriores.
>
> **Re-validado em 10/06/2026** (auditoria de 5 agentes sobre o código real). Correções marcadas com ⚠️
> ao longo do texto e consolidadas na seção final "Correções da auditoria (10/06)".

## Visão: a Bizzu já escuta o cliente em 5 frentes

A Bizzu **não era surda** — ela já coletava voz do cliente em 5 famílias. O que faltava era **(1) canal
conversacional (WhatsApp)**, **(2) inteligência sobre o que é coletado (sentimento/temas/clustering)** e
**(3) captura ativa do motivo de churn**. É exatamente aí que o Escuta entra.

| # | Família | Natureza | Mecanismos nativos |
|---|---------|----------|--------------------|
| A | **Satisfação proativa** | a Bizzu pergunta | NPS in-app |
| B | **Suporte reativo** | o cliente procura | Atendimentos (helpdesk e-mail) + Formulário de Contato |
| C | **Qualidade de conteúdo** | sobre as questões | Report de questão + Comentários/votos + Comentário-IA detector |
| D | **Sinais passivos / churn** | derivado/observado | `cancellationReason` automático + Tracking PostHog |
| E | **Demanda de produto** | pedido | Solicitação de edital |

---

## A. Satisfação proativa — NPS in-app

- **Onde:** `backend/src/nps/` (`nps-response.model.ts`, `nps.service.ts`, `nps.controller.ts`) ·
  `frontend` `NpsModal.jsx` + `useNpsCheck.js` + `npsApi.js`.
- **Como funciona:** o front chama `GET /nps/check`; o **motor de elegibilidade** (`nps.service.ts:34-88`)
  decide se mostra, por 3 gatilhos contextuais: `FIRST_SESSION` (1ª sessão de questões), `GOAL_HALF`
  (≥50% das tasks da meta), `GOAL_COMPLETE` (100%). Modal pergunta nota **1-10 + comentário livre** →
  `POST /nps`. Tabela `nps_responses` com **unique `(user_id, trigger)`** → 1 resposta por gatilho por
  vida (upsert).
- **O que a Bizzu faz:** painel `/gestao/nps` completo — gauge NPS, % promotor/passivo/detrator,
  distribuição 1-10, **NPS por gatilho**, evolução semanal, comentários paginados. ⚠️ *auditoria 10/06:
  "score no perfil do assinante" NÃO foi encontrado no código (front nem back) — doc desatualizado ou
  feature removida; validar.*
- **Lacunas:** ⚠️ montado **só na `PlanoDeEstudoPage`** (quem não abre o plano nunca vê) · **sem cooldown
  temporal** (só dedup por gatilho) · **sem análise de sentimento/tema** nos comentários · **sem alerta de
  detrator** em tempo real · sem segmentação por plano · 🐛 o painel de comentários (`getNpsComments`,
  `gestao.service.ts:1382`) não popula o nome do autor (sai `null`).

## B. Suporte reativo — Atendimentos + Contato

- **Onde:** `backend/src/atendimentos/` (helpdesk) + `backend/src/contact/` (formulário) ·
  `frontend` `/contato` (`ContatoPage.jsx`) + `/gestao/atendimentos` (`GestaoAtendimentosPage.jsx`).
- **É um helpdesk de verdade** (eu tinha subestimado): tickets com `ticketNumber`, **threading por e-mail**
  via **SendGrid Inbound Parse** (`suporte+<ticket>@suporte.bizzu.ai`), `status` (aberto/em_atendimento/
  resolvido/fechado), `prioridade` (baixa→urgente), `tipo` (dúvida/erro/reclamação/sugestão/outro),
  **anexos em S3** (expiram 90d), notas internas. Schema Postgres `suporte`.
- **Fluxos de entrada:** (1) `POST /contact` (público) cria ticket + avisa `suporte@bizzu.ai`; (2) reply do
  usuário por e-mail → webhook `/webhooks/email-inbound` reabre/atualiza o ticket; (3) admin responde pelo
  painel com anexos.
- **O que a Bizzu faz:** painel two-panel (lista+thread), filtros, troca de status/prioridade, resposta
  por e-mail. Stats no dashboard.
- **Lacunas:** **sem CSAT pós-atendimento** (não pergunta se resolveu) · sem SLA/alerta de ticket parado ·
  auto-classificação de tipo é heurística de keyword · sem WhatsApp · aluno não vê nº de protocolo.

## C. Qualidade de conteúdo — 3 mecanismos sobre as questões

> ⚠️ **Correção importante:** existem DOIS "reportar erro". O `ReportarErroPage` (`/reportar-problema`) é
> **stub** ("em construção"). MAS o **report de questão** (`QuestaoReportModal`) é **totalmente
> funcional** — eu havia dito que report de erro era stub; estava incompleto.

1. **Report de questão** (ativo) — `frontend QuestaoReportModal.jsx` (botão "⚑ Reportar" na sessão de
   questões) → `POST /questoes/:id/report`. Backend `question-report.model.ts`: tipo (`GABARITO_ERRADO`,
   `IMAGEM_AUSENTE`, `TEMA_INCORRETO`, `OUTRO`) + observação + contexto (matéria/tópico/edital/cargo).
   Alerta imediato p/ `suporte@bizzu.ai`. Painel `/gestao/question-reports` agrupa por questão, **valida
   gabarito com IA (Gemini)** e notifica o usuário de volta.
2. **Comentários + votos por questão** — `frontend QuestaoComentarios.jsx` · backend
   `questoes-comentarios/`: fórum com threading (1 nível), **votos UP/DOWN** (score), flag de moderação
   (só MANAGER), soft-delete. Painel `/gestao/comentarios` modera flagados. É **feedback de conteúdo**
   (quais questões geram dúvida/discordância).
3. **Comentário-IA detector de divergência** — backend `questoes-comentarios-ia/`: a IA (solver→reconciler)
   marca `agreesWithGabarito=false` + `needsReview=true` quando discorda do gabarito oficial → fila de
   revisão da gestão. É um **detector automático de erro de gabarito** (mais preciso que report manual).
   ⚠️ *auditoria 10/06: o filtro `?needsReview=true` existe só na **API** (`gestao/questoes-comentarios-ia`);
   ainda **não há painel no frontend** para essa fila.*
- **Lacunas:** sem threshold automático (N reports `GABARITO_ERRADO` → revisão urgente) · sem cruzamento
  report manual × detector-IA · aluno não vê status do report · nenhum rating/"foi útil?" sobre o
  comentário-IA · sem rating de conteúdo/plano (estrelas/like) em lugar nenhum.

## D. Sinais passivos / churn — derivados, não perguntados

- **Motivo de churn** (`backend/src/payments/subscription.model.ts:124-129`): `cancellationReason` é
  **preenchido automaticamente** pelo fluxo — **NUNCA perguntado ao usuário**. 4 categorias:
  `GUARANTEE_REFUND` · `USER_CANCEL` · `PAYMENT_FAILED` · `OTHER`. O endpoint
  `POST /user/subscription/cancel` **não aceita corpo** → no front é `window.confirm` seco, sem survey.
- **Consequência:** `USER_CANCEL` é monolítico — não distingue "caro" / "não preciso mais" / "insatisfeito"
  / "fui pro concorrente". `PAYMENT_FAILED` é hardcoded no webhook (suja churn voluntário). É a **maior
  lacuna de feedback da Bizzu** — e o ponto de maior valor do Escuta.
- **Tracking PostHog** (`backend/src/tracking/`): eventos server-side de ciclo de vida
  (`subscription_cancelled` com `reason`/`days_subscribed`, `checkout_payment_succeeded`,
  `subscription_plan_changed`...). Análise externa no PostHog; **sem signup nem eventos de engajamento de
  produto** capturados (esses só existem no Escuta).
- ⚠️ **auditoria 10/06 (correção importante):** o `subscription_cancelled` só é enviado ao PostHog pelos
  **webhooks** (`webhook.service.ts:212`) e pelo **cron asaas-overdue** (`asaas-overdue-cancellation.service.ts:65`).
  O **cancelamento voluntário** (`finishCancel`, `subscription.service.ts:461`) **não** chama `tracking.capture` —
  então o churn voluntário **some do PostHog server-side**, mas **chega ao Escuta** via `escuta.captureForUser`.
  Isso reforça o Escuta como a **única fonte do churn voluntário**.

## E. Demanda de produto — Solicitação de edital

- `backend/src/edital-solicitacoes/` + `frontend MissingEditalRequestPanel.jsx` (no checkout, quando o
  aluno não acha o edital): grava demanda → notifica o aluno quando o edital é adicionado. Sinal de **voz
  de produto** (quais concursos querem). Lacuna: sem agregação/priorização por volume de pedidos.
  ⚠️ *auditoria 10/06: há também `pedirInformacoes()` (`edital-solicitacoes.service.ts:640`) que abre um
  ticket de atendimento a partir da solicitação — não estava documentado.*

---

## Quadro-mestre: feedback nativo × como o Escuta se relaciona

| Mecanismo nativo | Captura | O que a Bizzu faz hoje | Lacuna-chave | Relação com o Escuta |
|---|---|---|---|---|
| **NPS in-app** | nota 1-10 + comentário, 3 gatilhos | painel NPS completo (gauge, por-gatilho, evolução) | sem sentimento/tema; só na pág. do plano | **Espelhar** (🥉 `nps.service.ts:101`→`nps_submitted`) p/ análise unificada + sentimento; **não substituir** |
| **Atendimentos (helpdesk e-mail)** | ticket texto livre, threading, anexos | triagem/resposta por e-mail no painel | sem CSAT pós-atendimento; sem WhatsApp | **Complementar**: CSAT pós-resolução via WhatsApp (futuro); não virar helpdesk |
| **Formulário de Contato** | nome/email/assunto/mensagem | vira ticket | sem protocolo ao aluno | canal alternativo; Escuta não toca |
| **Report de questão** (ativo) | erro de gabarito/imagem/tema | painel + validação IA Gemini + notifica | sem status p/ usuário | **deixar nativo**; é qualidade de conteúdo, não voz-do-cliente WhatsApp |
| **Comentários + votos** | discussão/UP-DOWN por questão | exibe + modera | sem análise de tendência | **deixar nativo** |
| **Comentário-IA detector** | divergência IA × gabarito | fila de revisão | sem cruzar c/ report manual | **deixar nativo** |
| **`cancellationReason`** | categoria automática (4) | filtra winback; mostra no painel | **nunca pergunta o porquê** | 🥇 **Exit survey WhatsApp** = o ouro do Escuta (✅ já plugado) |
| **CSAT de tópico/meta** | — (não existia) | — | inexistente | ✅ **criado pelo Escuta** (`topic_completed`) |
| **Tracking PostHog** | eventos de ciclo de vida | análise externa | sem engajamento de produto | Escuta capta engajamento (tópico/meta) que o PostHog não tinha |
| **Solicitação de edital** | demanda de concurso | fila + notifica | sem priorização | Escuta poderia avisar "saiu seu edital" (via radar) |

## Conclusão (a tese refinada)

A Bizzu tem **boa escuta reativa** (helpdesk maduro) e **de conteúdo** (report + fórum + detector-IA), e
**satisfação proativa básica** (NPS sem inteligência). Os **3 buracos reais** que o Escuta preenche:
1. **Canal conversacional (WhatsApp)** — a Bizzu não tem nenhum ponto de WhatsApp.
2. **Inteligência sobre o feedback** — NPS e atendimentos só **armazenam**; ninguém classifica
   sentimento/tema nem clusteriza. O Escuta faz cérebro + classificação + RAG + digest.
3. **Motivo de churn ativo** — a Bizzu **categoriza sozinha** mas **nunca pergunta**. O exit survey via
   WhatsApp (já plugado) é o maior ganho.

O Escuta **não deve duplicar** o helpdesk, o report de questão nem o fórum (são fortes e nativos). Deve
**espelhar** o NPS (unificar análise) e **adicionar** o que não existe: WhatsApp, inteligência e o
"porquê" do churn — sempre cuidando do **double-touch** (winback e-mail + exit survey ao mesmo tempo).
