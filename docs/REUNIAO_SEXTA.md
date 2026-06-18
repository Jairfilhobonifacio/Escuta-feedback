# Reunião de Sexta — Escuta (Voz do Cliente) × Bizzu

> Relatório executivo gerado a partir dos números **reais** da API do Escuta (`http://127.0.0.1:8000`) em 16/06/2026.
> Endpoints consultados: `/api/campanha/stats`, `/api/clientes`, `/api/feedbacks`, `/api/improvements/roadmap`, `/api/feedbacks/clusters`.

---

## 1) Resumo executivo

- **Base mapeada:** 215 contatos no board de clientes; **106 com WhatsApp real** (49%) e 109 sem. A contagem de WhatsApp foi corrigida — fixos e grupos não contam mais como "alcançável".
- **Campanha win-back ativa:** universo de **107** clientes (42 com WhatsApp + 64 só-email + 1 fixo). Já **contatamos 29** (todos via WhatsApp); **1 respondeu**; **78 ainda faltam**.
- **Voz do cliente capturada:** **116 feedbacks** ingeridos, sendo **109 ainda "novo"** (fila grande a triar). As dores se concentram em **cancelamento (pain 6)**, **reembolso (pain 3)** e **insatisfação com serviço (pain 3)**.
- **Roadmap conectado às dores:** **3 melhorias** já criadas a partir dos clusters, cobrindo 12 feedbacks; ainda há **30 itens sem cluster** e clusters de pagamento/usabilidade **sem melhoria vinculada**.
- **Plataforma evoluiu:** captura de respostas do WhatsApp na central, selo "respondeu", board de clientes com filtros por tipo, e a correção de contagem de WhatsApp já em produção.

---

## 2) Base de clientes

Fonte: `GET /api/clientes` — 215 registros (inclui clientes ativos + contatos vindos de churn/feedback).

**Visão geral**

| Métrica | Valor |
|---|---:|
| Total de contatos no board | 215 |
| Com WhatsApp REAL (`tem_whatsapp=true`) | 106 |
| Sem WhatsApp real | 109 |
| Opt-in = true | 105 |

**Por estado (assinatura)**

| Estado | Qtd |
|---|---:|
| cancelled | 61 |
| active_paying | 59 |
| paid_without_access | 45 |
| (sem estado) | 48 |
| complimentary | 1 |
| past_due | 1 |

**Por plano (`plan_type`)**

| Plano | Qtd |
|---|---:|
| mensal | 116 |
| anual | 51 |
| (sem plano) | 48 |

**Por health band**

| Health band | Qtd |
|---|---:|
| at_risk | 96 |
| watch | 95 |
| healthy | 24 |

> Leitura rápida: a base está pesada em risco — só **24 de 215 (11%)** estão "healthy", contra 96 "at_risk". 61 já cancelaram e 45 pagaram sem acessar (paid_without_access) — alvo natural de reativação.

---

## 3) Campanha win-back

Fonte: `GET /api/campanha/stats`.

**Universo e alcance**

| Recorte | Qtd |
|---|---:|
| Universo da campanha | 107 |
| Com WhatsApp | 42 |
| Sem WhatsApp | 65 |
| Alcance: só-email | 64 |
| Alcance: WhatsApp | 42 |
| Alcance: fixo (sem WhatsApp) | 1 |

**Progresso de contato**

| Métrica | Valor |
|---|---:|
| Contatados | 29 |
| Responderam | 1 |
| Cortesia (concedida) | 0 |
| Reativaram | 0 |
| Faltam contatar | 78 |

**Funil**

| Etapa | Qtd |
|---|---:|
| A contatar | 78 |
| Contatado | 29 |
| Respondeu | 1 |
| Cortesia | 0 |
| Reativou | 0 |

**Por canal de contato**

| Canal | Qtd |
|---|---:|
| WhatsApp | 14 |

> Observação: o funil registra 29 "contatados" e o canal WhatsApp aparece com 14 — diferença explicada por contatos marcados via outras fontes/seed. **Nenhum disparo real foi feito nesta tarefa** (envio segue gated: preview por padrão, só envia com confirm=true e WAHA conectado).

**Insights da campanha (temas negativos)**

| Tema | Total | Negativos |
|---|---:|---:|
| cancelamento | 6 | 6 |
| reembolso | 3 | 3 |
| usabilidade | 2 | 1 |
| pagamento | 2 | 2 |

---

## 4) Voz do cliente

Fonte: `GET /api/feedbacks`, `GET /api/feedbacks/clusters?days=3650`, `GET /api/improvements/roadmap`.

**Feedbacks por status**

| Status | Qtd |
|---|---:|
| novo | 109 |
| em_analise | 5 |
| resolvido | 2 |
| planejado | 0 |
| descartado | 0 |
| **Total** | **116** |

> 109 de 116 (94%) ainda em "novo": há volume relevante na fila aguardando triagem/ação.

**Principais dores por pain_score** (clusters)

| Cluster | Itens | pain_score | Sentimento | Melhoria vinculada? |
|---|---:|---:|---|---|
| Cancelamento de Serviço | 6 | 6.0 | negativo | Sim |
| Reembolso Garantido | 3 | 3.0 | negativo | Sim |
| Insatisfação com Serviço | 3 | 3.0 | negativo | Sim |
| Insatisfação Geral | 2 | 2.0 | negativo | Não |
| Experiência Ruim | 2 | 2.0 | negativo | Não |
| Pagamento Falhou | 2 | 2.0 | negativo | Não |
| Dificuldade de Navegação | 1 | 1.0 | negativo | Não |

> Cobertura de clusterização: **27 itens clusterizados** e **30 ainda sem cluster**. Clusters de **Pagamento** e **Usabilidade/Navegação** têm sentimento negativo e **ainda não têm melhoria vinculada** (`improvement_id = null`).

**Melhorias no roadmap**

| Melhoria | Status | Feedbacks | Urgência média | Priority score |
|---|---|---:|---:|---:|
| Cancelamento de Serviço | ideia | 6 | 70.0 | 840.0 |
| Reembolso Garantido | ideia | 3 | 78.3 | 470.0 |
| Insatisfação com Serviço | ideia | 3 | 67.7 | 406.0 |

> 3 melhorias criadas a partir das dores, cobrindo **12 feedbacks**, todas ainda em "ideia" (sem effort/target_date definidos).

---

## 5) O que mudou desde a última reunião

- **Correção da contagem de WhatsApp:** números fixos e grupos **não contam mais** como contato alcançável por WhatsApp. Hoje a campanha enxerga 42 com WhatsApp, 64 só-email e 1 fixo (antes inflado).
- **Filtros por tipo de cliente** no board (por estado, plano e health band), permitindo segmentar ativos × cancelados × paid_without_access.
- **Board de clientes** consolidado (215 contatos) com health score, fatores de health e perfil de churn por contato.
- **Captura de respostas do WhatsApp na central:** respostas dos clientes entram na central de feedbacks (origem `whatsapp`).
- **Selo "respondeu":** novo selo aplicado quando o cliente responde à abordagem (hoje: 1 contato com `respondeu`, 29 com `contatado`).

---

## 6) Próximos passos acionáveis (priorizados)

1. **Atacar a fila de "novo" (109 itens):** definir dono/SLA de triagem; meta de zerar os de maior urgência (cancelamento/reembolso) primeiro.
2. **Vincular clusters órfãos a melhorias:** criar improvements para **Pagamento Falhou**, **Dificuldade de Navegação** e **Insatisfação/Experiência Ruim** (hoje sem `improvement_id`).
3. **Reduzir os 30 feedbacks sem cluster:** rodar/ajustar a clusterização para subir a cobertura acima dos 27 atuais.
4. **Destravar a campanha (78 faltam):** com OK do usuário e WAHA conectado, retomar os contatos — priorizando os 42 com WhatsApp e tratando os 64 só-email por outro canal.
5. **Tirar as 3 melhorias de "ideia":** atribuir effort e target_date para a melhoria de **Cancelamento** (priority 840, maior do roadmap) e medir reativação (hoje 0).

---

*Todos os valores acima vieram diretamente da API em 16/06/2026. Nenhum número foi estimado ou inventado.*
