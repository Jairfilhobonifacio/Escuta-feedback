# Mega Central — Fatia 2: fontes nativas por PUSH (blueprint)

> Gerado por 4 agentes em 10/06/2026 (workflow `mega-central-push-sources`). A fatia 1 (pull da
> API de Clientes → `FeedbackItem` + Visão 360) está pronta. Esta fatia conecta as fontes nativas
> que só existem **em tempo real** (ticket, report, solicitação) via **eventos do backend** caindo
> no mesmo `FeedbackItem`. Bizzu = leitura → cada mudança vira `.patch` em `docs/patches/`.

## Peça comum — lado Escuta (fazer 1×, serve as 3 fontes)
Estender `app/api/events.py`: hoje o handler procura uma `Survey` por `trigger_event` e dispara. Adicionar,
**antes do lookup de survey** (após HMAC + get-or-create contato), uma bifurcação por um mapa literal:

```python
GENERIC_EVENT_MAP = {                      # evento → (source, type) do FeedbackItem
    "ticket_created":   ("bizzu_support",  "ticket"),
    "ticket_resolved":  ("bizzu_support",  "ticket"),
    "question_reported":("bizzu_app",      "report"),
    "edital_requested": ("bizzu_platform", "edital_request"),
}
```
Se `payload.event` está no mapa → montar `spec` (source/type/external_id/text/score/occurred_at/extra) e chamar
`ingest_feedback_item(session, org.id, contact.id or None, spec, classify=True)`; retornar `202 {ingested, feedback_id}`.
Senão, segue o fluxo de survey atual (intacto). Dedup: `external_id = f"bizzu:{event}:{event_id}"` (UNIQUE em `feedback_items`).
`contact_id` é **nullable** (ticket público pode não ter contato resolvível). Testes: ticket→FeedbackItem, dedup idempotente, e `subscription_cancelled` **continua** virando survey.

## Fontes (lado Bizzu — patches), em ordem de esforço

### 1. Report de questão — `question_reported` (mais simples; tem userId)
- Call-site: `src/questoes/questoes.service.ts:101-161` (`createReport`); injetar `EscutaService`.
- `captureForUser(userId, 'question_reported', 'report:{questaoId}:{userId}:{ts}', {tipo, observacao, materia_nome, topico_nome})`.
- userId sempre presente (aluno logado). `captureForUser` resolve telefone via `User.phoneNumber`. → `FeedbackItem(source=bizzu_app, type=report)`.

### 2. Solicitação de edital — `edital_requested` (simples; tem userId; alto valor p/ clustering)
- Call-site: `src/edital-solicitacoes/edital-solicitacoes.service.ts:536` (`create`); injetar `EscutaService`.
- `captureForUser(user.userId, 'edital_requested', 'edital_req:{created.id}', {edital_nome, cargo_nome, banca})`.
- Valor: agregar por `(edital_nome, cargo_nome, banca)` → demanda priorizada por volume (clustering).

### 3. Atendimentos — `ticket_created` / `ticket_resolved` (mais valiosa, porém exige extra)
- Call-sites: `src/atendimentos/atendimentos.service.ts:65-96` (`create`) e `:184-193` (`updateStatus` → quando vira `resolvido`).
- ⚠️ **Ticket público não tem userId** — `captureForUser` resolve por `User.findByPk(userId)` e falharia. **Solução:** criar um `captureForTicket(phone, event, eventId, props)` no `EscutaService` que manda o telefone direto (`user.id=null`, phone do `Atendimento.telefone`). O lado Escuta já aceita `contact_id` nulo/resolução por telefone.
- ⚠️ **CSAT pós-atendimento**: não existe campo `csatScore` no modelo — decisão em aberto: (a) adicionar coluna, ou (b) disparar uma **survey CSAT por WhatsApp** ao resolver (reusa o motor de survey, não o ingest). Recomendo (b) p/ ter o "quão satisfeito" de verdade.
- Idempotência: `ticket:{ticketNumber}:created` / `ticket:{ticketNumber}:resolved_{ts}`.

## Recomendação de sequência
Report → Edital (rápidos, validam o caminho genérico de ingest) → Atendimentos (precisa do `captureForTicket` + decidir CSAT). A peça comum do lado Escuta entra junto com a 1ª fonte.
