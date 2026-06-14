# Handoff — Sessão 2026-06-13 (Escuta × Bizzu)

> Onde paramos e como retomar. Sessão longa: 3 features novas, central conectada, redesign do
> painel, correções de bugs, **roadmap de Customer Success** e a **Fase 1 (Health & Risco) entregue**.

---

## 1. O que foi feito

### 🎙️ 3 features (áudio · call · fechar-o-loop)
- **Áudio inbound transcrito** — `app/services/audio.py` (Groq `whisper-large-v3`); `webhook._extract_inbound` detecta `audio/ptt/voice`, transcreve e trata como texto. Sem chave/falha → acolhe.
- **Oferta de call** — `app/domain/survey/helpers.py::append_call_link` + env `BIZZU_CALL_URL`, aplicada no hand-off.
- **Fechar o loop** — worklist de churn (3 perguntas + flags) → `scripts/import_abordagens.py` ingere como `FeedbackItem` (idempotente). Botão "📤 Exportar p/ central".

### 🔌 Central de feedbacks (Supabase) — conectada e no ar
- A central É o **Supabase Cloud** (`aws-1-sa-east-1.pooler...`). API (`:8000`) + painel (`:3001`) rodando.
- 3 fontes unificadas em `FeedbackItem` (bizzu_app, bizzu_billing, whatsapp) + dados de partner.

### 💬 Mensagens de win-back (churn) — fundamentadas
- Pesquisa de técnicas (tom não-acusatório, curto, sem venda) → templates em `frontend/lib/templates.ts`
  (CRUD no modal "Abordar no WhatsApp" da tela Feedbacks: modelo + msg editável + `{nome}`/`{seu_nome}` + abrir wa.me).

### 🎨 Redesign do painel (UI premium)
- Ícones SVG na navegação (fim dos emojis), gauge de NPS no Dashboard, funil de resposta, waveform de assinatura, avatares de iniciais (Clientes/Contatos/Feedbacks/360), timeline visual na 360, zebra striping, scrollbar custom, hover-lift.

### 🐛 Correções
- **Emojis do template corrompidos pelo bundler** (viravam `�`/sumiam no link wa.me) → escapes `\u{...}` em `templates.ts`. Validado ao vivo. Ver memória `feedback_nextjs_emoji_bundler`.
- **Sync de clientes quebrado** (`NoReferencedTableError: improvements`, faltava import de model) → corrigido em `sync_partner_customers.py` e `import_abordagens.py`. Re-puxado: 60 atualizados.
- Worklist `①②③` → `1. 2. 3.` (fonte-robusto).

### 🗺️ Roadmap de Customer Success
- `docs/ROADMAP_CS.md` — 7 fases (Health → Playbooks → Métricas → Predição → Expansão → Escala), com o que temos × gaps, esforço e métricas.

### ⭐ Fase 1 — Health & Risco (ENTREGUE)
- `app/domain/cs/health.py` — **Health Score 0-100 transparente** (NPS + perfil + recência + sentimento + assinatura; devolve os `factors`). 7 testes.
- `/api/clientes` enriquecido com `health` / `health_band` / `health_factors`.
- Painel Clientes: coluna **Saúde** + chip **"⚠️ Em risco"** (fila priorizada, pior Health primeiro).
- Validado: **144 contas → 60 risco · 64 atenção · 20 saudáveis**.

---

## 2. Estado atual
- **Testes:** 235 verdes (228 + 7 health). **Type-check** do frontend: OK.
- **Stack:** API `:8000` (uvicorn, sem `--reload` — reiniciar após mudar backend) + painel `:3001` (Next dev, hot-reload). Caem nos resets de MCP → religar via `/escuta-stack`.
- **Envs novas:** `GROQ_WHISPER_MODEL` (default ok), `BIZZU_CALL_URL` (vazio — call desligada até ter link).

## 3. Próximos passos
1. **Fase 2 — Playbooks/automação** (recomendado): motor gatilho→ação (detrator→tarefa, em risco há Xd→alerta, renovação→check-in).
2. Rodar a fila de risco real e **calibrar os pesos** do Health Score com base no que aparece.
3. Estágio de jornada explícito (incremento da Fase 1).
4. (Deferred) Ativação com o Felipe: aplicar patches em `docs/patches/` + migrations + deploy.

## 4. Como retomar
- `/bizzu-escuta` (contexto) · `/escuta-stack` (subir 8000/3001) · ler `docs/ROADMAP_CS.md` e este handoff.
- Regra de ouro: Bizzu = leitura (patches), Escuta = código; segredos por env; WhatsApp real só com OK.
