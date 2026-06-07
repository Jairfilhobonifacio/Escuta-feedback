# PRD — Fase 0 (Tracer Bullet): NPS ponta-a-ponta para o Bizzu

> **Objetivo único:** provar que conseguimos **interceptar uma resposta inbound do WhatsApp e casá-la com a pergunta + a pessoa certa**. Tudo o resto (UI, clustering, tickets, Cloud API) é Fase 1+.
>
> **Projeto:** Escuta (novo, alimentado pelo Nexus AI — ver `../README.md`)
> **Piloto:** Bizzu (`bizzu.ai`, edtech de concursos) = `organizations.slug = 'bizzu'`
> **Data:** 2026-06-05

---

## 1. Critério de sucesso (a "bala" atravessou)

Um contato de teste do Bizzu recebe no WhatsApp:

> *"Oi {nome}! Aqui é o Bizzu 👋 De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"*

Responde **"9"** → o sistema:
1. reconhece que esse contato estava **aguardando** a pesquisa `NPS Bizzu`;
2. faz o **parsing** ("9" → score 9, categoria *promotor*);
3. **persiste** a resposta vinculada a `(survey_run, contact, question)`;
4. responde a **pergunta aberta de follow-up**: *"Massa! 🙌 Por quê? (pode mandar áudio)"*;
5. ao receber o motivo, **persiste** como texto e **fecha** a resposta.

E um contato que mandar mensagem **sem** pesquisa pendente segue o fluxo normal (na Fase 0, só é registrado — sem LLM). **Zero vazamento entre organizações** (tudo filtra `organization_id`).

---

## 2. Escopo

**Dentro (Fase 0):**
- 3 tabelas novas: `surveys`, `survey_runs`, `survey_responses`.
- `SurveyContextResolver` — casa resposta ↔ pergunta ↔ pessoa.
- `SurveyDispatcher` (fino) — dispara a 1ª pergunta e cria as linhas de resposta `status='sent'`.
- Parser de **1 tipo** de pergunta: **NPS (0–10)** + 1 pergunta aberta de follow-up.
- Caminho inbound **enxuto** (ver §5.1) — sem copiar o orchestrator inteiro ainda.
- Canal **WAHA** (não-oficial), 1 sessão, disparo limitadíssimo (lista de teste).

**Fora (Fase 1+):** UI de construção de survey, painel de resultados, tickets, clustering/sentimento, digest, Cloud API/BSP, throttling/tiers, templates HSM, multi-step além de NPS+follow-up, autopilot.

---

## 3. O caso Bizzu concreto

| | |
|---|---|
| Survey | `NPS Bizzu` (type=`nps`) |
| Pergunta 1 (nps) | "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?" |
| Pergunta 2 (open) | "Por quê? (pode mandar áudio)" |
| Público-piloto | lista pequena de contatos de teste (concurseiros reais com opt-in, ou números internos) |
| Janela de resposta | 24h (após isso a resposta tardia não é mais casada — vira mensagem normal) |

> A transcrição de áudio (pergunta 2) **não** é Fase 0 — se vier áudio, guardamos o ponteiro da mídia e tratamos na Fase 1 (pipeline AssemblyAI do Pulse). Na Fase 0, follow-up só processa **texto**.

---

## 4. Modelo de dados (3 tabelas novas)

Convenção e tipos espelham o Nexus (UUID PK `gen_random_uuid()`, `organization_id` FK obrigatório, timezone-aware). **Reuso:** `organizations`, `contacts` e `messages` vêm copiados do Nexus (não recriar).

```
surveys
  id              uuid pk
  organization_id uuid fk -> organizations  (NOT NULL, index)
  name            text            -- "NPS Bizzu"
  type            text            -- 'nps' (Fase 0)
  questions       jsonb           -- [{key:'nps', kind:'nps', text:'...'},
                                  --  {key:'reason', kind:'open', text:'...'}]
  status          text            -- 'active' | 'draft' | 'archived'
  created_at, updated_at
  UNIQUE (organization_id, name)

survey_runs                       -- uma "rodada" de disparo
  id              uuid pk
  survey_id       uuid fk -> surveys
  organization_id uuid fk         (NOT NULL, index)
  trigger         text            -- 'manual' (Fase 0) | 'event:subscription_canceled' ...
  status          text            -- 'running' | 'done'
  created_at

survey_responses                  -- 1 linha por contato por rodada (espelha CampaignSend)
  id              uuid pk
  survey_run_id   uuid fk -> survey_runs
  contact_id      uuid fk -> contacts
  organization_id uuid fk         (NOT NULL, index)
  status          text            -- 'sent'(aguardando) | 'awaiting_reason' | 'closed' | 'expired'
  answer_score    int             -- 0..10 (NPS)
  nps_bucket      text            -- 'promoter'|'passive'|'detractor' (derivado)
  answer_text     text            -- motivo (follow-up)
  channel_msg_id  text            -- waha id da pergunta enviada (rastreio)
  sent_at, answered_at, closed_at timestamptz
  UNIQUE (survey_run_id, contact_id)
  INDEX (organization_id, contact_id, status)   -- o resolver busca por aqui
```

**Estado "aguardando pesquisa":** fica na própria `survey_responses.status` (`sent`/`awaiting_reason`) com janela de 24h via `sent_at`. *(Alternativa avaliada: reusar o model `ConversationContext` do Nexus — descartada na Fase 0 por acoplar demais; reconsiderar na Fase 1.)*

---

## 5. Componentes novos

### 5.1 Caminho inbound enxuto (decisão de engenharia)

O doc de visão dizia "reusa o orchestrator". Na prática, o `orchestrator._process_message_internal` arrasta uma árvore grande de dependências (memória, behaviors, RAG, LLM). Para o **tracer bullet** isso é peso morto — não precisamos de LLM pra provar a interceptação.

**Fase 0:** webhook → `SurveyContextResolver` **primeiro**. Se ele resolver, responde e encerra. Senão, só registra a mensagem.
**Fase 1:** copiamos o `orchestrator` completo e injetamos o resolver no ponto exato já mapeado — **`app/services/agent/orchestrator.py`, entre Behaviors (≈L217) e RAG (≈L219)**:

```python
# orchestrator._process_message_internal, após os behaviors:
if not overrides.get("skip_survey"):
    survey_decision = await self.survey_resolver.resolve(contact, message)
    if survey_decision:
        return survey_decision   # atalha antes de RAG/LLM
```

### 5.2 `SurveyContextResolver.resolve(contact, message) -> AgentDecision | None`

`app/domain/survey/resolver.py`. Lógica:
1. Busca a `survey_response` mais recente de `contact_id` + `organization_id` com `status IN ('sent','awaiting_reason')` e `sent_at >= now()-24h`. Nenhuma → retorna `None`.
2. Se `status='sent'` (esperando o NPS): `parse_nps(message)`.
   - válido → grava `answer_score`, `nps_bucket`, `status='awaiting_reason'`, `answered_at`; responde a pergunta 2.
   - inválido → responde *"me manda só um número de 0 a 10 🙂"* (não muda status).
3. Se `status='awaiting_reason'`: grava `answer_text`, `status='closed'`, `closed_at`; responde agradecimento. (Áudio → guarda ponteiro, fecha, trata na Fase 1.)
4. Retorna um `AgentDecision(response=..., contact_id=..., behavior_triggered='survey')`.

> Tudo `async` (AsyncSession), toda query com `organization_id`, datas em UTC (`datetime.now(timezone.utc)`).

### 5.3 `SurveyDispatcher.dispatch(survey, contacts) ` (fino)

`app/domain/survey/dispatcher.py`. Para cada contato (espelha o `CampaignSend` do `campaign_worker`):
1. cria/garante `survey_run` (`trigger='manual'`).
2. cria `survey_response(status='sent', sent_at=now)` — **idempotente** via `UNIQUE(survey_run_id, contact_id)`.
3. envia a pergunta 1 via `IMessagingService.send_text(chat_id=contact.phone, text=..., session=...)`; grava `channel_msg_id`.
4. throttling simples `await asyncio.sleep(delay)` (espelha `delay_seconds=30` do Nexus).

*(Fase 1: substituir por um "step de survey" dentro do `campaign_worker` real, reusando 100% o agendamento/semaphore/`SELECT FOR UPDATE skip_locked`.)*

### 5.4 `parse_nps(text) -> int | None`

`app/domain/survey/parsers.py` — **já implementado** neste commit (função pura, testável). Extrai inteiro 0–10. `nps_bucket`: 0–6 detrator, 7–8 passivo, 9–10 promotor.

---

## 6. Fluxo ponta-a-ponta

```
[Operador] dispara NPS Bizzu p/ lista de teste
   └─> SurveyDispatcher: cria survey_run + survey_responses(status=sent)
        └─> WAHAService.send_text(pergunta 1)  ──> WhatsApp do concurseiro
                                                        │
[Concurseiro responde "9"] ──> WAHA webhook ──> POST /api/webhook/waha
   └─> dedup por (organization_id, waha_message_id)
        └─> resolve organização via WhatsAppChannel.phone_number
             └─> SurveyContextResolver.resolve(contact, "9")
                  ├─ acha survey_response(status=sent) < 24h
                  ├─ parse_nps("9") = 9 (promotor)
                  ├─ UPDATE status=awaiting_reason, answer_score=9
                  └─> send_text(pergunta 2 "por quê?")
[Concurseiro responde motivo] ──> ... ──> resolve()
   └─ status=awaiting_reason → grava answer_text, status=closed → send_text(agradecimento)
```

---

## 7. O que copiar do Nexus (verificado, com `file:line`)

Root doador: `…\AISECPlataformadeagentesdeIA-claude-kind-bell\AISECPlataformadeagentesdeIA-claude-kind-bell`

| Peça | Arquivo no Nexus | Notas p/ a cópia |
|---|---|---|
| Interface de canal | `app/domain/interfaces/messaging_service.py` | `IMessagingService` (Protocol: `send_text/send_image/send_audio/get_contacts`) — copiar como está |
| Serviço WAHA | `app/services/waha.py` | `WAHAService.send_text(chat_id, text, session)` (L95–138) + `_retry_with_backoff` |
| Circuit breaker | `app/utils/circuit_breaker.py` | `waha_breaker` |
| Models base | `app/services/database.py` | copiar `Organization`, `Contact`, `Message`, `WhatsAppChannel`; **deixar de fora** os models de domínio AIESEC (LeadType/Behavior/Agent/Meeting…) |
| Webhook inbound | `app/api/waha_hub.py` + `app/api/webhook.py` | rota `POST /api/webhook/waha`, dedup por `(organization_id, waha_message_id)`, resolve org via `WhatsAppChannel.phone_number` |
| Auth multi-tenant | `app/auth/dependencies.py` | `get_current_org_and_role` → `OrgContext.organization_id` (cache Redis TTL 15s) |
| Convenção de migration | `alembic/versions/20260513_waha_dedup_index.py` | nome `YYYYMMDD_desc.py`; head atual = `20260524_lgpd_data_access_log` |
| Orchestrator (**Fase 1**) | `app/services/agent/orchestrator.py` | `process_message`/`_process_message_internal`; injetar resolver entre Behaviors (≈L217) e RAG (≈L219) |
| RAG/embeddings (**Fase 2**) | `app/rag/retriever.py`, `app/rag/embeddings.py` | `EmbeddingService` dim **384** (`all-MiniLM-L6-v2`) p/ clustering de feedback |

---

## 8. Migration (seguir a convenção do Nexus)

Arquivo: `alembic/versions/20260605_initial.py` ✅ **(implementado)**
`down_revision = None` — é a **primeira** migration do repo novo (a convenção `YYYYMMDD_desc.py` é copiada do Nexus, mas o histórico Alembic é independente). Cria `organizations`, `contacts`, `surveys`, `survey_runs`, `survey_responses` com os índices/uniques do §4. `CREATE EXTENSION IF NOT EXISTS pgcrypto` (p/ `gen_random_uuid()`). `downgrade()` dropa na ordem inversa. FKs `ON DELETE CASCADE`. Config em `alembic.ini` + `alembic/env.py` (async, lê `DATABASE_URL`).

---

## 9. Critérios de aceite

- [ ] `organizations` tem linha `slug='bizzu'`; survey `NPS Bizzu` (type=`nps`) ativa.
- [ ] Disparo p/ contato de teste **envia** a pergunta 1 e cria `survey_response(status='sent')`.
- [ ] Reenvio do mesmo disparo **não duplica** (unique `survey_run_id, contact_id`).
- [ ] Responder "9" → `answer_score=9`, `nps_bucket='promoter'`, `status='awaiting_reason'`, e chega a pergunta 2.
- [ ] Responder o motivo → `answer_text` gravado, `status='closed'`.
- [ ] Resposta inválida ("oi") com survey pendente → pede número, não muda status.
- [ ] Mensagem **sem** survey pendente → resolver retorna `None` (fluxo normal).
- [ ] Resposta após 24h → `None` (não casa).
- [ ] Nenhuma query sem `organization_id`; teste com 2 orgs não vaza.
- [ ] `parse_nps` com testes unitários verdes.

---

## 10. Integração que o Bizzu precisa prover

Como o Bizzu é web/Supabase e **não tem WhatsApp**, para a Fase 0 (manual) basta uma **lista de contatos de teste com opt-in**. Para a Fase 1 (disparo por evento):
1. **Opt-in de WhatsApp** no signup/perfil do Bizzu (telefone + consentimento) → vira `Contact` na Escuta.
2. **Webhook de eventos de ciclo de vida** do Bizzu → Escuta: `plano_gerado`, `topico_concluido`, `assinatura_cancelada`, `aprovado` (payload: id do aluno, telefone, evento, timestamp). Cada evento mapeia para uma survey.

---

## 11. Riscos / decisões em aberto

- **WAHA viola ToS** → ban em disparo em massa. Fase 0 é lista de teste minúscula; disparo de verdade só na Fase 1 com Cloud API/BSP (a interface `IMessagingService` permite trocar sem reescrever).
- **Nome** (Escuta vs Echo) — não bloqueia a Fase 0.
- **Reuso de `ConversationContext`** vs coluna `status` — escolhido `status` na Fase 0; revisitar.
- **Áudio no follow-up** — fora da Fase 0 (só ponteiro); pipeline do Pulse na Fase 1.
