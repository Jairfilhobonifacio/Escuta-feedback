# Handoff — Onde Paramos (2026-06-20) — Reforma completa + limpezas + 🚀 DEPLOY NO AR + repo

> Continuação de `SESSAO_HANDOFF_2026-06-18_AGENTES_4FRENTES.md`. Sessão muito longa (19→20/06):
> a Central foi **reformada de ponta a ponta** (Fase 0→3), a base foi **limpa**, o repo ganhou **remote**
> e a stack foi **deployada** (API no Modal + front no Vercel, WAHA fora). Leia também
> `docs/FEEDBACK_DONO_2026-06-20.md` (backlog das melhorias que vêm a seguir).

---

## 🟢 Estado atual
| Serviço | Onde | Estado |
|---|---|---|
| **Painel (front)** | **https://escuta-feedback.vercel.app** | 🟢 PROD (Vercel, projeto `escuta-feedback`) |
| **API FastAPI** | **https://jbonifaciomoreirafilho--escuta-api-fastapi-app.modal.run** | 🟢 PROD (Modal app `escuta-api`), protegida por PANEL_API_KEY |
| **Banco** | Supabase cloud (piloto) | 🟢 |
| **WAHA** | — | 🔴 FORA do deploy (Chat/Conexão/envio inativos em prod) |
| Stack LOCAL | 8000 / 3001 / 3000 + Podman | no ar (dev) |

- **Repo:** `https://github.com/Jairfilhobonifacio/Escuta-feedback.git` (branch `master`).
- **Commits:** `2599417` (simplificada) → `0c74b63` (timeline) → `f3ff826` (Fase 3) → `e26de5a` (deploy code). Tudo pushed.
- **Números reais (prod):** NPS **8,9** · **5 detratores** · **~174 contatos** (após limpezas).

---

## ✅ O que foi feito
**Reforma (3 commits):** Monitorar (home) · Board "Trello" (Contatados/Respondidos/Não responderam + criar
feedback) · menu 16→7 · Clientes (contatáveis + at_risk real) · Feedbacks (filtros em botão + "+tarefa") ·
Chat (1:1 + espaçado) · timeline do cliente **editável** · Pesquisas (público filtrado + acompanhamento) ·
fixes NPS/Tailwind/styled-jsx.

**Limpezas no piloto** (script `scripts/_limpar_dados_teste.py`, com `--phone`/`--grupos`/`--chat-lixo`):
3 telefones de teste + 24 grupos-resíduo + 20 conversas-lixo. NPS 8,4→8,9, detratores 11→5.

**🚀 DEPLOY (commit `e26de5a`):**
- `deploy_modal.py` — API no Modal (imagem leve sem torch; secret `escuta-prod`; ASGI).
- Proxy **BFF** `frontend/app/api/[...path]/route.ts` — injeta `X-Panel-Key` **server-side** (chave nunca no
  browser; elimina CORS); `lib/api.ts` base relativa.
- E2E validado em prod: front → proxy → Modal → Supabase = 200 com dados; **sem chave = 401** (PII segura).

---

## 🟡 Próximos passos (backlog em `docs/FEEDBACK_DONO_2026-06-20.md`)
**Melhorias pedidas pelo dono (ordem sugerida):**
1. **P0 bugs:** (B) **popover de selos bugado** (sobreposto/duplicado, img-2); (D) **ficha do contato
   quebrada** (img-3, provável styled-jsx).  ← *em andamento ao fim desta sessão.*
2. **P1 design:** (A) Clientes (deixar claro com-WhatsApp/só-e-mail/sem-contato + chip "Abordados"); (C)
   Board mais "Trello"; (E) Pesquisas redesign (styled-jsx antigo).
3. **P1 dados:** (F) timeline com dados de assinatura (quando assinou etc.) + **status customizáveis**.
4. **P2:** (G) tipos/origem customizáveis + "Temas"→"Mapeamento"; (H) apagar dados pela UI; (I)
   monitoramento inteligente; (J) benchmark de Customer Success.

**Infra:**
- **WAHA** (reativa Chat/envio) — quando quiser: **Fly.io** grátis com volume (ou Oracle Free VM / local +
  Cloudflare Tunnel). Depois, setar `WAHA_BASE_URL` no secret Modal + `HOOK_URL` público.
- Toda mudança de front exige **re-deploy** (ver abaixo).

---

## 🔧 Como religar / re-deployar
- **Stack local:** skill `/escuta-stack` (API 8000 sem `SELF_CHAT_TEST`; painel 3001; WAHA 3000).
- **Re-deploy API (Modal):** `cd escuta && export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 && py scripts/_modal_tls.py deploy deploy_modal.py`.
- **Re-deploy front (Vercel):** `cd escuta/frontend && export NODE_OPTIONS=--use-system-ca && vercel deploy --prod --yes`.
- **Secret Modal:** `py scripts/_deploy_modal_secret.py` (lê `.env` + `~/.secrets/escuta_panel_key.txt`).

---

## ⚠️ Pegadinhas
- **Modal/curl batem no TLS do antivírus.** Modal CLI: rodar via `scripts/_modal_tls.py` (truststore+runpy
  NO MESMO processo — não propaga a subprocess) + **`PYTHONUTF8=1 PYTHONIOENCODING=utf-8` no SHELL antes**
  (senão `charmap` aborta no meio do build). Validar URLs externas via **httpx+truststore** (curl dá 000).
- **Vercel CLI:** `NODE_OPTIONS=--use-system-ca` (mesmo TLS).
- **styled-jsx NÃO funciona no SSR** deste projeto → CSS no `globals.css` (já corrigido em Monitorar/Chat;
  **ficha do contato e Pesquisas ainda podem ter** — alvo dos P0/P1).
- **Sub-agente que reinicia a API mata o uvicorn ao terminar** → reiniciar via orquestrador.
- **Escrita no piloto** barrada pelo classificador sem OK explícito (o dono autoriza via "permissão total"
  ou roda via `!`).
- `scripts/_*.py` (limpeza/deploy) têm valores locais/PII → **fora do git**.

---

## 🔑 Refs rápidas (sem segredos)
- **Prod:** front `escuta-feedback.vercel.app` · API `…escuta-api-fastapi-app.modal.run` · Modal app `escuta-api` · secret `escuta-prod` · Vercel projeto `escuta-feedback`.
- **PANEL_API_KEY:** `~/.secrets/escuta_panel_key.txt` (= secret Modal + env Vercel; o proxy BFF a injeta).
- **Backlog/feedback:** `docs/FEEDBACK_DONO_2026-06-20.md` (+ imagens `docs/feedback-2026-06-20/`).
- **Deploy:** `deploy_modal.py` · `frontend/app/api/[...path]/route.ts` (BFF) · `scripts/_modal_tls.py` · `scripts/_deploy_modal_secret.py`.
- **Pendências de prod herdadas:** `WAHA_WEBHOOK_SECRET` (quando o WAHA voltar) · rotação WAHA key/Postgres.
