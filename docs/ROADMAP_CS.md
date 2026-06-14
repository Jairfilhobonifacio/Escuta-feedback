# Roadmap — do "fluxo de feedbacks" ao Customer Success completo (Escuta × Bizzu)

> Visão: hoje o Escuta **coleta e organiza a voz do cliente**. O destino é uma **plataforma de
> Customer Success** que cobre o ciclo de vida inteiro — capta sinal, mede saúde, prevê risco, dispara
> a ação certa e fecha o loop — com a Bizzu como cliente-piloto. Gerado 2026-06-13.

---

## 1. O que JÁ temos (base sólida)

| Pilar | Capacidades entregues |
|------|----------------------|
| **Coleta multicanal** | WhatsApp bidirecional (WAHA) · surveys NPS/CSAT/Exit · **chatbot conversacional** que aprofunda e faz hand-off humano · **áudio transcrito** (Groq Whisper) · eventos push da Bizzu (HMAC) · pull da API de Clientes · feedback manual |
| **Mega Central de Dados** | `FeedbackItem` unifica TODAS as fontes (app, billing, whatsapp, manual, campanha) · **Visão 360** por contato (timeline) · ações (status novo→resolvido) + flag "abordado" |
| **Inteligência (IA)** | Classificação automática (sentimento, temas, urgência) · **clustering de temas/dores** · segmentação em 13 perfis · alerta de detrator em tempo real |
| **Painel (Next.js)** | Dashboard (gauge NPS, funil, distribuição) · Inbox de feedbacks com **CRUD + abordagem WhatsApp (templates)** · Temas · Clientes · Contatos · Ficha 360 · Pesquisas |
| **Ação de CS** | **Campanha de churn** (worklist + análise + fechar-o-loop) · templates de win-back fundamentados · digest ao dono · oferta de call no hand-off |

**Maturidade atual:** somos fortes em **Voice of Customer reativo** (capta → classifica → organiza → abordagem manual).

---

## 2. O que FALTA para um CS completo (os gaps)

O ciclo de CS é: **Onboarding → Adoção → Valor → Renovação → Advocacy** (e prevenção de churn em paralelo).
Hoje atuamos no fim do funil (churn/feedback). Faltam as peças proativas:

1. **Health Score** composto por cliente (uso + NPS + tickets + pagamento + recência) — hoje só temos NPS e perfil, sem um número que **preveja risco**.
2. **Estágio de jornada/lifecycle** explícito (onboarding, ativado, em risco, churn).
3. **Playbooks / automação** (gatilho → ação): "detrator → cria tarefa", "inativo 14d → reengajar", "renova em 7d → check-in".
4. **Fila de trabalho de CS** — "contas em risco para abordar hoje", com dono e SLA (não só inbox de feedback).
5. **Métricas de CS** — churn rate, retention, NRR/GRR, time-to-resolve, NPS no tempo, coortes.
6. **Predição de churn** — sinais de risco **antes** do cancelamento (não só reagir ao exit).
7. **Onboarding/ativação** — capturar e acompanhar o primeiro valor.
8. **Expansão & Advocacy** — identificar contas saudáveis para upsell e promotores para indicação.
9. **Série temporal/histórico** — hoje a maioria das telas é snapshot.

---

## 3. Roadmap priorizado (por alavancagem × esforço)

| Fase | Tema | Entrega | Esforço | Por quê agora |
|------|------|---------|---------|---------------|
| **0** | **Polimento** (✅ feito) | UI premium (gauge, avatares, timeline), áudio, call, fechar-o-loop, fix sync + emojis | — | Base limpa |
| **1** ✅ | **Health & Risco** | **Health Score** (0-100, transparente — `app/domain/cs/health.py`) + coluna Saúde + **fila "contas em risco"** no painel · *(estágio de jornada = próximo incremento)* | médio | **ENTREGUE 13/06**: 144 contas pontuadas (60 risco · 64 atenção · 20 saudáveis); 7 testes verdes |
| **2** | **Playbooks / automação** | Motor de regras gatilho→ação (tarefa, mensagem, alerta) reusando o que já temos (detrator alert, abordagem, dispatch) | médio | Closed-loop **automático**, não manual |
| **3** | **Métricas de CS & coortes** | Dashboard executivo: churn/retention/NRR, NPS no tempo, série histórica (tabela `metrics_daily`) | médio | Decisão baseada em tendência, não foto |
| **4** | **Predição de churn** | Score de risco antecipado (heurística forte → ML leve) usando recência, queda de uso, sentimento, pagamento | alto | Agir **antes** do cancelamento |
| **5** | **Expansão & Advocacy** | Detectar contas saudáveis p/ upsell + programa de promotores/indicação (NPS 9-10 → pedido de review/indicação) | médio | Crescer receita, não só reter |
| **6** | **Escala / multi-tenant** | Produtizar além da Bizzu (isolamento por org, onboarding self-serve) | alto | Virar produto |

---

## 4. Melhorias transversais (qualidade da aplicação)

- **Estabilidade dev**: os servidores caem nos resets — script supervisor (`/escuta-stack`) que religa sozinho.
- **UX**: skeletons de loading, empty states ricos, atalhos de teclado no inbox.
- **Confiabilidade**: manter a suíte (228 testes) verde a cada fase; testes E2E do painel.
- **Encoding**: padronizar símbolos via escapes `\u{}` (lição do bug de emoji) — já aplicado em `templates.ts` e worklist.
- **Observabilidade**: logs estruturados + painel de saúde da própria stack (WAHA, fila, IA).
- **Segurança/LGPD**: revisão de PII (já: arquivos com PII fora do git), rotação de segredos WAHA.

---

## 5. Métricas-alvo (como saber que o CS funciona)

| Métrica | Hoje | Meta |
|--------|------|------|
| Taxa de resposta às pesquisas | ~73% (amostra) | manter > 60% |
| Churn abordado / churn total | manual | 100% com tarefa automática (Fase 2) |
| Tempo até abordar conta em risco | — | < 24h (Fase 1+2) |
| Reativação de churn | — | medir baseline (campanha atual) |
| Contas com Health Score | 0 | 100% (Fase 1) |

---

## 6. Recomendação de sequência

**Começar pela Fase 1 (Health & Risco)** — é o que converte a base atual (dados ricos, já temos) em **ação de CS proativa**, e habilita as Fases 2–4. Primeira fatia concreta:

1. `health.py` — fórmula de Health Score (0-100) por contato a partir de sinais que já temos (NPS, recência de feedback, sentimento médio, perfil, status de assinatura).
2. Campo derivado + endpoint `GET /api/clientes` enriquecido com `health` e `risco`.
3. No painel: coluna **Health** (barra colorida) em Clientes + uma aba/seção **"Contas em risco"** (fila priorizada para abordar).

> Cada fase é incremental e reaproveita o que já existe — nada de reescrever. O roadmap é a forma de
> "melhorar toda a aplicação" sem fazer tudo de uma vez e sem perder o que já está sólido.
