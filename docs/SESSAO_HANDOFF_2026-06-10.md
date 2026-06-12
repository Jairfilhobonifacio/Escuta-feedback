# Handoff de Sessão — 10/06/2026

> Projeto **Escuta** (retenção/Voz do Cliente). Continuação do `SESSAO_HANDOFF_2026-06-09.md`.
> Sessão longa: auditoria do feedback nativo, espelho de NPS, **Mega Central de Dados** completa,
> tela 360, deck p/ o sócio. Tudo testado.

## 🟢 Estado atual
- **Mega Central de Dados COMPLETA**: unifica **5 fontes** (NPS, churn, report de questão, solicitação
  de edital, atendimentos) + WhatsApp num modelo único (`FeedbackItem`), classificado por IA, com
  **Visão 360 por cliente**. **129 testes verdes.**
- **Espelho de NPS in-app** (evento `nps_submitted`, modo ingest sem disparo) — feito.
- **Tela 360** no painel (`frontend/app/contatos/[id]`) — build Next verde; demonstrada ao vivo (SQLite demo).
- **Auditoria do feedback nativo** (5 famílias) revalidada; docs corrigidos.
- **Deck p/ o sócio**: `docs/ESCUTA_RESUMO_COLEGA.pdf`.

## ✅ Construído (10/06)
**Escuta (código):**
- `app/models/feedback.py` (`FeedbackItem`) + `app/domain/feedback/` (`partner_map.py`, `ingest.py`).
- `app/api/events.py`: branch ingest NPS + `GENERIC_EVENT_MAP` (`question_reported`, `edital_requested`,
  `ticket_created` → `FeedbackItem`); `ticket_resolved` → survey **CSAT Atendimento**; `EventUser.id`
  opcional (ticket público); helper `_get_or_create_contact`.
- `app/api/admin.py`: `GET /api/contacts/{id}/360` (timeline unificada).
- `scripts/sync_partner_customers.py`: cria `FeedbackItem` (NPS+churn) no sync.
- `scripts/seed_bizzu.py`: surveys **NPS Bizzu (ingest)** + **CSAT Atendimento Bizzu**.
- Migrations: `20260610_nps_ingest` (source/ingest_mode) + `20260610b_feedback_items`.
- Frontend: tela 360 + tipos `Contact360` em `lib/api.ts` + link na lista + estilos.
- **Chatbot conversacional** (`tests/test_chatbot.py`): model `Message` (transcript, migration `20260610c`)
  gravado no webhook (inbound/outbound) e dispatcher; **aprofundamento** (`brain.decide_followup` +
  resolver `_maybe_followup`, até 2 follow-ups, viés detrator, acumula motivo); **hand-off humano**
  (intent `handoff` no brain → resolver `_handle_handoff`/`_notify_handoff`: marca `FeedbackItem(handoff)`
  + `Contact.needs_human_handoff` + alerta o dono via `owner_phone` + pausa o bot). Falta: abrir ticket
  no Atendimentos (endpoint backend) + melhorar parser (`um/uma`→nota 1).
- **Fase 2**: clustering de temas (`aggregate_themes` + `GET /api/themes/aggregate`), alertas de detrator
  em tempo real (`resolver._notify_detractor_realtime`), parser corrigido (`um/uma` não viram nota 1),
  e gancho de ticket no hand-off (`resolver._open_support_ticket`, best-effort, envs `BIZZU_SUPPORT_*`).
- Testes: +24 (nps ingest, feedback/360, eventos genéricos, ticket, chatbot, fase 2) → **136 verdes**.

**Patches backend** (`docs/patches/`, aplicar com `git apply --recount` na raiz do backend):
- `bizzu-backend-nps-escuta-ingest.patch` · `bizzu-backend-question-report-escuta.patch`
- `bizzu-backend-edital-requested-escuta.patch` · `bizzu-backend-atendimentos-escuta.patch`
- `bizzu-backend-support-ticket-endpoint.patch` (endpoint p/ o hand-off abrir ticket no Atendimentos)

**Docs:** `BIZZU_ESCUTA_MASTER.md` (auditoria + mega central) · `analise-bizzu/feedback-nativo.md`
(correções) · `MEGA_CENTRAL_PUSH_BLUEPRINT.md` · `ESCUTA_RESUMO_COLEGA.pdf` (+ `_deck_escuta.html`).

## 🟡 Onde paramos / próximo passo = ATIVAR (com o Felipe)
1. Aplicar os **4 patches** no backend real (`gabarita-ai/backend`), commitar, deploy.
2. Setar `ESCUTA_API_URL` + `ESCUTA_WEBHOOK_SECRET` no `.env` do backend.
3. `alembic upgrade head` no Supabase do Escuta (cria `feedback_items` + campos do nps_ingest).
4. `py scripts/seed_bizzu.py` (cria as surveys novas).
5. `py scripts/sync_partner_customers.py` (sem `--dry-run`) → popula a central com os 233 (**PII**).
6. Coordenar **double-touch de churn** (winback e-mail × survey WhatsApp).
**Produto (Fase 2 restante):** clustering de temas, painel multi-tenant c/ login, WhatsApp Cloud API.

## ⚠️ Pegadinhas (desta sessão)
- `GEMINI_API_KEY` do `bizzu_midia` **esgotada** (429) — fallback determinístico cobre; trocar pela própria.
- Demo da tela 360 sobe via SQLite (`_demo360.db`) + `Start-Process`; processos caem em reset do ambiente
  → re-subir com PowerShell `Start-Process` (API :8000 com `DATABASE_URL=sqlite+aiosqlite:///.../_demo360.db` + `node next start`).
- **Bizzu = leitura**: tudo do backend vira `.patch` em `docs/patches/`, nunca commitar nos clones.

## 🔑 Refs
- Mega central: `app/models/feedback.py`, `app/domain/feedback/`, `app/api/events.py` (`GENERIC_EVENT_MAP`),
  `app/api/admin.py` (`/360`), `frontend/app/contatos/[id]/page.tsx`.
- Painel demo ao vivo: http://localhost:3001/contatos (contato Maria = `c7148c77-9ebc-4202-9b5b-5705b598f61b`).
