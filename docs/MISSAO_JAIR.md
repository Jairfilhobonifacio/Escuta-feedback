# 🎯 MISSÃO JAIR — Sócio de Growth da Bizzu (mapa de tudo)

> Briefing único da missão do **Jair** como sócio de mídia/growth da **Bizzu** (fundador técnico:
> **Felipe Lemes**). Escrito para que **qualquer chat do Claude** (Code, Claude.ai/Projects, Desktop)
> entenda o todo e ajude na missão. Fonte: reuniões 05/06 e 08/06 + análise dos repos.
> Atualizado 2026-06-09.

## 1. Quem é o Jair aqui
Sócio responsável por **growth**, em **2 frentes**. NÃO é dev do backend (isso é o Felipe). Vínculo:
**PJ**. Governança: **Trello** (tarefas) + reuniões semanais. Liberdade criativa alta; decisões de
produto/preço alinhar com o Felipe.

## 2. As 2 frentes (o coração da missão)

```
        ┌──────────── DADOS DA BIZZU (produção) ────────────┐
        │  api.bizzu.ai   ·   radar-editais.bizzu.ai          │
        └───────┬───────────────────────────┬────────────────┘
                ▼                            ▼
 ┌──────────────────────────┐   ┌──────────────────────────────┐
 │ FRENTE 1 — AQUISIÇÃO      │   │ FRENTE 2 — RETENÇÃO           │
 │ repo: bizzu_midia         │   │ produto: Escuta               │
 │ gerar artes/posts de      │   │ WhatsApp + IA: pesquisa,      │
 │ editais p/ Instagram,     │   │ ouvir feedback, reativar,     │
 │ prospecção (PDF)          │   │ segmentar por PERFIL          │
 └──────────────────────────┘   └──────────────────────────────┘
        traz gente                       segura gente
```

| | Frente 1 — Aquisição | Frente 2 — Retenção |
|---|---|---|
| **Repo/Produto** | `bizzu_midia` (clonado, `Documents/Projetos/bizzu_midia`) | `Escuta` (`Documents/Projetos/escuta`) |
| **O que faz** | Carrosséis de cargo/edital, Daily Editais, Notícias, e-mail, PDF de prospecção | Survey WhatsApp + cérebro IA + classificação + digest |
| **Consome** | API Bizzu (Raio-X) + Radar + Gemini + Miniflux | Eventos Bizzu (HMAC) + **API de Clientes** (perfis) |
| **Publicação/Disparo** | Instagram **manual** hoje (Meta API = a construir) | WhatsApp via WAHA (só com opt-in; teste antes de prod) |
| **Estado (09/06)** | ✅ deps instaladas, pronto p/ operar | ✅ churn/CSAT plugados; falta integrar perfis |

## 3. Acessos, chaves e ferramentas
- **Repos:** `bizzu_midia` (GitHub `felipelemes/bizzu_midia`, clonado) · `escuta` (local) · `bizzu-repos/`
  (6 repos da Bizzu, **leitura**).
- **Chaves (em `.env`, nunca commitar):** `GEMINI_API_KEY` (trocar pela própria, grátis em
  aistudio.google.com/apikey) · `BIZZU_API_KEY` (Leads/Raio-X) · `RADAR_SERVICE_API_KEY` (editais) ·
  **`BIZZU_PARTNER_API_KEY`** (API de Clientes — já no `.env` do Escuta).
- **A obter/combinar com o Felipe:** acesso ao **Instagram** (central de contas) · links de **Telegram** ·
  **Trello** (board) · app **Meta** para publicar via API oficial (homologação 4-7 dias).

## 4. Perfis de feedback (resumo)
A API de Clientes (233 clientes) permite segmentar em **9 perfis** por estado + tempo de casa + NPS +
motivo de saída, cada um com uma abordagem e uma survey. Detalhe completo + integração em
[`analise-bizzu/api-clientes-partner.md`](analise-bizzu/api-clientes-partner.md). Resumo:
Embaixador · Ativo recente · Ativo silencioso · Ativo em risco (detrator) · Vai expirar · Churn pós-uso ·
Churn rápido · Churn involuntário (⚠️ não duplicar com winback) · Cortesia.

## 5. Roadmap priorizado

**🟢 Frente 1 — Aquisição (bizzu_midia)**
1. ✅ Deps instaladas. Próximo: `npm start` → `localhost:3000` e rodar `node agents/daily-editais/run-daily-editais.js --date <hoje>`; revisar a arte em `output/`.
2. Ler `brand-guidelines-bizzu.html` (obrigatório) antes de gerar.
3. Validar/refinar os 3 templates do Daily + criar modelos de referência de estilo.
4. **Iniciar homologação do app Meta JÁ** (demora) — postar manual enquanto isso.
5. Definir avatar/mascote dentro da marca (objeto editorial recorrente; sem humanos/stock).
6. Melhorar o PDF de prospecção (perfil do concurseiro + comparativo + screenshot do Raio-X).

**🎧 Frente 2 — Retenção (Escuta + API de Clientes)**
7. ✅ API validada + chave guardada + perfis definidos.
8. Implementar `sync_partner_customers.py` (paginar 233 → classificar em perfil → upsert no contato, **sem disparar**) + `--dry-run` para auditar a distribuição.
9. Criar as surveys 🆕 (Indicação, CSAT Onboarding, Escuta de Detrator, Retenção) reusando o motor do Escuta.
10. Teste de disparo Jair↔Felipe antes de produção. Coordenar **double-touch de churn** com o Felipe.

**🗂️ Governança**
11. Preencher o **Trello** (tarefas das duas frentes).
12. Listar ferramentas/assinaturas p/ a Bizzu contratar.
13. Estudar mercado (`bizzu_midia/relatorio-perfil-concurseiro.md`) + entrar nos grupos de Telegram.

## 6. Pontos de atenção
- **Segredos:** as chaves são de produção; só em `.env` (gitignored), nunca em doc/Claude.ai/commit.
- **PII / LGPD:** a API de Clientes tem nome/e-mail/WhatsApp; disparo só com opt-in; não exportar a base.
- **Preço:** conteúdo novo usa **R$20/mês · R$120/ano**; site pode ter resíduo de R$10/R$60 — confirmar.
- **WhatsApp:** WAHA viola ToS — só teste pequeno; produção exige cuidado.

## 7. Ponteiros (docs canônicos em `escuta/docs/`)
`BIZZU_ESCUTA_MASTER.md` (ecossistema Bizzu + Escuta) · `analise-bizzu/api-clientes-partner.md` (API +
perfis) · `analise-bizzu/feedback-nativo.md` (o que a Bizzu já ouvia) · `analise-bizzu/<repo>.md` (cada
repo) · `_context-pack/` (pacote p/ Claude.ai Projects). bizzu_midia: ver `bizzu_midia/README.md` e
`bizzu_midia/CLAUDE.md`.
