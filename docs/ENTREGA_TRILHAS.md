# Entrega — Trilhas de Retenção e Automação (foco do Claude Code)

> Escopo de trabalho do Claude Code (Jair): **Retenção (Escuta)** + **Automação (bizzu_midia/radar)**.
> Design/marca ficam fora deste escopo. Balanço do que foi entregue, os artefatos e o que falta.
> Atualizado 2026-06-09.

---

## 🎧 TRILHA 1 — RETENÇÃO (Escuta) — ~90% (falta operar)

### ✅ O que já foi feito
1. **API de Clientes validada** — `GET /partner/customers`, **233 clientes**, schema confirmado.
2. **Cliente HTTP** — `app/integrations/bizzu_partner.py` (GET-only, header X-API-Key, trata 401/404).
3. **Classificador de 13 perfis** — `app/domain/segmentation/profiles.py` (refinado de 9→13; indefinidos caíram de 54 para 2). 40 testes.
4. **Mapeamento perfil → survey** — `app/domain/segmentation/profile_surveys.py`.
5. **Sync de clientes** — `scripts/sync_partner_customers.py` (`--dry-run` mostra a distribuição, sem PII).
6. **Disparo por perfil** — `scripts/dispatch_by_profile.py` (`plan` = dry-run; `dispatch --force` = teste real; cooldown 7d, opt-in).
7. **4 surveys novas** — `scripts/seed_bizzu.py`: CSAT Onboarding, Escuta de Detrator, Retenção, Indicação (+ as 3 que já existiam). Roteiros on-brand prontos.
8. **Qualidade** — suíte **112 testes verde**; revisão adversarial PRONTO.
9. **Distribuição real dos 233:** 100 silenciosos · 34 vai_expirar · 33 promotores · 27 churn_rapido · 11 passivo · 11 churn_outro · 6 involuntário · 5 detrator · resto.

### 🟡 O que falta (é OPERAR, não construir — fazer com o Felipe)
- **Rodar no banco:** `seed_bizzu.py` (cria surveys) + `sync_partner_customers.py` sem `--dry-run` (cria/classifica os 233 — ⚠️ popula PII).
- **Ver o plano:** `dispatch_by_profile.py plan`.
- **Teste de disparo Jair↔Felipe** (`dispatch --profile X --limit 1 --force`) antes de cliente real.
- **Validar o fluxo de atendimento (RAG)** — já existe no Escuta; falta testar respostas.
- **Coordenar o double-touch de churn** com o Felipe (decisão de produto).

### 📄 Documentos da trilha
- [`INTEGRACAO_FEEDBACK.md`](escuta/docs/INTEGRACAO_FEEDBACK.md) — **o doc-mestre da retenção** (motor, perfis, mapeamento, roteiros, como operar, segurança).
- [`analise-bizzu/api-clientes-partner.md`](escuta/docs/analise-bizzu/api-clientes-partner.md) — a API + os 13 perfis + distribuição.
- [`analise-bizzu/feedback-nativo.md`](escuta/docs/analise-bizzu/feedback-nativo.md) — o que a Bizzu já tinha de feedback (pra não duplicar).

### 💻 Código da trilha
`app/integrations/bizzu_partner.py` · `app/domain/segmentation/profiles.py` · `app/domain/segmentation/profile_surveys.py` · `scripts/sync_partner_customers.py` · `scripts/dispatch_by_profile.py` · `scripts/seed_bizzu.py` · `scripts/dispatch_nps.py` · `tests/test_partner_profiles.py` · `tests/test_profile_surveys.py`.

---

## ⚙️ TRILHA 2 — AUTOMAÇÃO & PRODUTO (bizzu_midia/radar) — ~destrave (itens não começados)

### ✅ O que já foi feito
1. **`bizzu_midia` clonado e destravado** — `npm install` ok, Chromium do Playwright ok, `.env` posicionado.
2. **Fábrica mapeada** — analisei os **5 subsistemas** (carrossel cargo/edital, Daily Editais, Notícias/Miniflux, Email+PDF) e suas integrações (Radar, API Bizzu, Gemini, Miniflux).

### 🟡 O que falta (CONSTRUIR — ainda não começou)
- **Mecanismo de notícias quentes** — cruzar Instagram/influencers + radar de editais → gerar PDF/post. (Parte local existe: Notícias/Miniflux + Daily Editais; o cruzamento com influencers é novo.)
- **Buscador de grupos no Telegram** — script que verifica se o grupo do concurso já existe.
- **Melhorar a geração de artes/PDF** — mexer no `bizzu_midia` (`lib/report-pdf.js`, templates) — depende de estudar o PDF atual primeiro.
- **Consertar `radar_gui.py` no Windows** (bug pequeno: abrir pasta usa comando macOS).
- **Publicação via API oficial da Meta** — `lib/instagram-client.js` (após homologação do app Meta).

### 📄 Documento da trilha
- [`analise-bizzu/bizzu-midia.md`](escuta/docs/analise-bizzu/bizzu-midia.md) — a fábrica de conteúdo (5 subsistemas, stack, integrações, brand, benchmark de março, próximos passos).

### 💻 Código da trilha
Repo `bizzu_midia/` (operacional): `server.js`, `agents/` (4 pipelines), `lib/` (clientes Bizzu/Radar/Miniflux/Gemini, report-pdf), `templates/slides/`, `radar_gui.py`.

---

## 🧭 Onde focar agora (recomendação)
- **Retenção:** está pronta — o próximo passo é **operar com o Felipe** (seed + sync + teste de disparo). Eu opero os comandos quando você autorizar.
- **Automação:** o próximo passo lógico é **estudar o PDF atual** (pré-requisito de "melhorar artes/PDF") + **consertar o `radar_gui.py`** (rápido) e então atacar **notícias quentes** ou **buscador de Telegram**.

> Docs de apoio (transversais): [`MISSAO_JAIR.md`](escuta/docs/MISSAO_JAIR.md) · [`SESSAO_HANDOFF_2026-06-09.md`](escuta/docs/SESSAO_HANDOFF_2026-06-09.md) · [`TRELLO_BOARD.md`](escuta/docs/TRELLO_BOARD.md).
