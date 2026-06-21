# Handoff — Sessão "Feedback + Jornada" (2026-06-20)

> Continuação de `SESSAO_HANDOFF_2026-06-20.md`. Sessão **monumental** (ultracode ON): mapeamento
> completo do sistema + **4 ondas de melhoria do feedback** + selos inteligentes + Feedbacks
> redesenhada + matching BR + métricas — **tudo em PRODUÇÃO**. Use os benchmarks/mapa em `docs/`
> (`MAPA_SISTEMA_FEEDBACK_2026-06-20.md`, `BENCHMARK_FEEDBACK_2026-06-20.md`,
> `BENCHMARK_ACOMPANHAMENTO_2026-06-20.md`, `MANUAL_MARCA_ESCUTA.md`, `SPEC_JORNADA_FEEDBACK_2026-06-20.md`).

## 🟢 Estado atual
| Serviço | Onde | Estado |
|---|---|---|
| **Painel (front)** | https://escuta-feedback.vercel.app | 🟢 PROD (Vercel) |
| **API FastAPI** | https://jbonifaciomoreirafilho--escuta-api-fastapi-app.modal.run | 🟢 PROD (Modal `escuta-api`) |
| **Banco** | Supabase cloud (piloto) | 🟢 **head `20260620_follow_up_automation`** |
| **WAHA** | — | 🔴 FORA do deploy (Chat/Conexão/envio/auto-reabrir/fechar-loop inativos em prod) |
| Stack local | 8000 / 3001 / 3000 + Podman | dev |

- **Repo:** `github.com/Jairfilhobonifacio/Escuta-feedback` (branch `master`). **Head: `9e60df6`**.
- **Números (prod):** NPS **~8,9** · base **247 contatos** (todos os ~240 da API Bizzu + extras) · taxa de resolução 1,5% · **166 candidatos a playbook** (backlog de CS).

## ✅ O que foi construído (esta sessão)
**Base + matching:** sync agora puxa **TODOS** os clientes (174→247, com/sem telefone) + **matching BR canônico** (`phone_key`, trata 9º dígito/DDI — não duplica contato). Tela Clientes abre em "Todos".

**Status de acompanhamento:** trocados os de bug-tracker por **A abordar / Aguardando retorno / Em acompanhamento / Resolvido / Sem retorno / Descartado** (com cor); 135 feedbacks migrados; status/tipos/origens **customizáveis** em `/config`.

**Selos inteligentes:** camada com **log de auditoria**; **inbound→`respondeu` automático** (webhook); **selos vivos** (VIP/Detrator/Em risco/Novo/Renovação, derivados — 232/247); **IA sugere selos** (Groq, validado em prod). Ficha = "Acompanhamento do cliente" + "Registrar feedback" + Excluir.

**Feedbacks redesenhada** (texto-herói + kebab) + **Abordado** de volta visível + rótulos humanos + PII mascarada nas listas.

**Jornada de feedback (4 ondas, SDD + workflows):**
1. **Urgência** da IA (`compute_urgencia` 0-100) visível/ordenável no Board + Feedbacks.
2. **Métricas** no Monitorar: `/api/central/overview` ganhou bloco `metricas` (taxa_resolucao, loops_fechados, tempo_1a_abordagem, nps_por_tema, **follow_up_pendentes**).
3. **Mapeamento** (`/temas`) com **índice de prioridade** (volume×receita×gravidade, `app/domain/prioridade.py`) + **Melhorias** (`/melhorias`) Kanban "você pediu, a gente fez" + modal "Avisar quem pediu" (fechar o loop) — ambos **religados no menu**.
4. **Playbooks LIGADOS** (`PLAYBOOKS_INLINE_ENABLED=1`, inline por evento) + **follow-up** (`follow_up_at`, "Reabordar em N dias") + **auto-reabrir** (cliente responde → feedback terminal/aguardando volta p/ a_abordar) + fila "Follow-up (para hoje)".

**Commits-chave:** `c387085` (matching/sync) · `25e8ea4` (status) · `f7f8f9b`+`780f19b`+`ee58509` (selos) · `6820b93`+`e35ad4a` (Feedbacks redesign/Abordado) · `010583e`+`b99faec` (jornada) · `62afe3e` (urgência+métricas) · `9e60df6` (follow-up). ~672 testes verdes; tsc 0.

## 🟡 Próximos passos (ordem de impacto)
1. **WAHA** (Fly.io/VPS+Docker) — destrava: auto-reabrir real, **fechar-o-loop** ("avisar quem pediu"), Chat/envio, e um host **com embeddings** (torch) p/ RAG híbrido + clustering inline (hoje inertes no Modal).
2. **Classificar sentimento** dos ~88 feedbacks sem sentiment — faz o **índice de prioridade diferenciar** (hoje quase tudo "média" pq gravidade=0) e o Mapeamento ficar real.
3. **Guardrails do VoC** — o agente **reprovou o smoke** (loop + ações excessivas com o fallback `llama-3.1-8b` por 429 do 70b). Limitar tools por contexto + prompt mais rígido + re-smoke antes de ligar `VOC_AGENT_ENABLED`.
4. **Backlog dos 166** — transformar os 166 detratores/risco em tarefas de CS (lote controlado via `POST /api/playbooks/run`).

## 🔧 Como religar / deployar
- **Stack local:** skill `/escuta-stack` (API 8000 sem `SELF_CHAT_TEST`; painel 3001; WAHA 3000).
- **Re-deploy API (Modal):** `cd escuta && export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 && py scripts/_modal_tls.py deploy deploy_modal.py`.
- **Re-deploy front (Vercel):** `cd escuta/frontend && export NODE_OPTIONS=--use-system-ca && vercel deploy --prod --yes`.
- **Secret Modal:** `py scripts/_deploy_modal_secret.py` (lê `.env` + `~/.secrets/escuta_panel_key.txt`; **agora inclui as flags de IA**).
- **Migration no piloto:** `export DATABASE_URL=... && py -m alembic upgrade head` (env.py NÃO lê `.env`).

## ⚠️ Pegadinhas (novas desta sessão)
- **Modal serverless NÃO tem `torch`/`sentence-transformers`** (`deploy_modal.py:40-56`, `EMBEDDING_MODEL_NAME=""`): RAG híbrido e clustering inline ligados no Modal ficam **INERTES** — só rendem num host com embeddings.
- **Flags de IA** (`PLAYBOOKS_INLINE_ENABLED`, `VOC_AGENT_ENABLED`, `VOC_WHATSAPP_TOOL_ENABLED`, `RAG_HYBRID_ENABLED`, `CLUSTERING_INLINE_ENABLED`) agora são lidas do `.env` pelo `scripts/_deploy_modal_secret.py` → controlar pelo `.env` + regravar secret + re-deploy. **VoC e WhatsApp-tool ficam em 0.**
- **VoC reprovado no smoke** (`scripts/_smoke_voc_groq.py`, banco in-memory isolado): com fallback 8b, loop de 5 iterações + ações excessivas. Não ligar sem guardrails.
- **Deploy Modal às vezes não troca o container no 1º deploy** (servia defaults antigos) — validar `/api/config` ou o campo novo no Modal **direto** após deploy de mudança de default; 2º deploy resolve.
- **Migration/escrita no piloto barrada pelo classificador** sem OK específico (mesmo com "OK geral") — pedir OK pontual ou rodar via `!`.
- **styled-jsx não renderiza no SSR** — CSS no `globals.css` (append no fim, sem alterar o existente).
- Screenshots headless: telas com `framer-motion`/`Promise.all`/`setInterval` somem por timing → usar `--virtual-time-budget` alto + `--force-prefers-reduced-motion`, ou validar no local.

## 🔑 Refs rápidas (sem segredos)
- **Prod:** front `escuta-feedback.vercel.app` · API `…escuta-api-fastapi-app.modal.run` · Modal app `escuta-api` · secret `escuta-prod` · Vercel `escuta-feedback`.
- **PANEL_API_KEY:** `~/.secrets/escuta_panel_key.txt` (= secret + env Vercel; proxy BFF injeta).
- **Docs desta sessão:** `MAPA_SISTEMA_FEEDBACK_2026-06-20.md` · `SPEC_JORNADA_FEEDBACK_2026-06-20.md` · `BENCHMARK_FEEDBACK_2026-06-20.md` · `BENCHMARK_ACOMPANHAMENTO_2026-06-20.md` · `MANUAL_MARCA_ESCUTA.md` · ilustrações em `frontend/public/illustrations/`.
- **Skills:** `bizzu-escuta` (contexto mestre) · `escuta-stack` · `escuta-handoff` · design: `design-studio`/`svg-illustrator`/`composition-master`/`brand-builder` (+agente `art-director`).
