# API de Clientes da Bizzu (Partner) + Perfis de Feedback

> A "API de dados de usuários" prometida nas reuniões (05/06 e 08/06). É o **combustível da
> segmentação por perfil** para a frente de retenção (Escuta). Somente leitura (GET).
> **Validada em 2026-06-09: 200 OK, 233 clientes, schema confere. Integração implementada
> e classificador refinado (13 perfis, distribuição real abaixo).**

## 1. A API (resumo técnico)

- **Base:** `https://api.bizzu.ai` · **Auth:** header `X-API-Key` (env `BIZZU_PARTNER_API_KEY` — **segredo**,
  já no `.env` do Escuta; nunca commitar nem colar em doc).
- **Endpoints:**
  - `GET /partner/customers?page=&pageSize=&search=` → `{ items[], total, page, pageSize }`. Paginar até
    items vazio (pageSize máx 500). **total atual = 233.**
  - `GET /partner/customers/by-email?email=` → 1 `PartnerCustomer` (404 se não for cliente).
- **`PartnerCustomer`:** `id, name, email, whatsapp, signedUpAt, nps{voted,score,comment,respondedAt},
  subscription{state, active, cancelled, complimentary, planName, planType, paymentMethod, startedAt,
  cancelledAt, cancellationReason, currentPeriodEnd, daysAsSubscriber, totalPaidCentavos, lastPaymentAt}`.
- **Quem NÃO aparece:** cadastrou e nunca pagou. Sem CPF/senha.
- **`state`:** `active_paying` · `complimentary` · `past_due` · `cancelled` · `cancelled_with_access` ·
  (borda) `access_without_subscription` / `paid_without_access`.

## 2. ⚠️ Privacidade / LGPD (regras antes de qualquer disparo)

1. **A API tem PII** (nome, e-mail, WhatsApp). Não exporte a base; não cole PII em doc/Claude.ai.
2. **Disparo só com opt-in** (`whatsappOptIn`, do sync da Bizzu). Esta API serve para **classificar e
   priorizar**, não para forçar contato.
3. **Coordenar double-touch:** `churn_involuntario` (PAYMENT_FAILED) já recebe **winback por e-mail** —
   por isso `should_contact=false` nesse perfil. Não duplicar com WhatsApp.
4. **Fase atual = entender + preparar.** O `--dry-run` só mostra contagens (sem PII, sem tocar banco).
   Disparo em produção vem depois, em teste (Jair ↔ Felipe).

## 3. Os 13 Perfis de Feedback + distribuição real (233 clientes, 2026-06-09)

Classificador puro em `app/domain/segmentation/profiles.py` (40 testes). Precedência: terminais
(cortesia → churns → vai_expirar) antes dos ativos. `should_contact=false` em churn_involuntário e
indefinido.

| Perfil | Critério (campos da API) | Qtd | % | Abordagem / survey |
|--------|--------------------------|----:|----:|--------------------|
| 🟢 **ativo_silencioso** | active_paying + nps.voted=false | 100 | 42.9% | maior balde: coletar NPS (✅ NPS Bizzu) |
| 🟡 **vai_expirar** | state cancelled_with_access/past_due | 34 | 14.6% | retenção urgente (janela curta) 🆕 |
| 🟢 **ativo_promotor** | active_paying + score≥9 (days<90) | 33 | 14.2% | pedir indicação/depoimento 🆕 |
| 🔴 **churn_rapido** | GUARANTEE_REFUND ou cancelou ≤7d | 27 | 11.6% | o que não atendeu de cara (✅ Exit) |
| 🟢 **ativo_passivo** | active_paying + score 7-8 | 11 | 4.7% | empurrar de passivo p/ promotor 🆕 |
| 🔴 **churn_outro** | cancelled fora dos casos acima (OTHER / 8-29d) | 11 | 4.7% | exit genérico (✅ Exit) 🆕 |
| 🔴 **churn_involuntario** | PAYMENT_FAILED | 6 | 2.6% | ⚠️ NÃO contatar (winback e-mail) |
| 🟡 **ativo_em_risco** | active_paying + score≤6 (detrator) | 5 | 2.1% | escuta prioritária antes do churn 🆕 |
| 🟢 **ativo_recente** | active_paying + days≤14 (sem nota) | 2 | 0.9% | CSAT onboarding 🆕 |
| ⚪ **indefinido** | anômalo residual (votou sem score) | 2 | 0.9% | nenhuma (should_contact=false) |
| 🎁 **cortesia** | complimentary | 1 | 0.4% | feedback qualitativo (✅ NPS) |
| 🔴 **churn_pos_uso** | USER_CANCEL + days≥30 | 1 | 0.4% | por que parou após usar (✅ Exit) |
| 🟢 **embaixador** | active_paying + days≥90 + score≥9 | 0 | 0% | (base nova; vai surgir) |

> Eixos de adaptação da mensagem: **estado** (`state`), **tempo de casa** (`daysAsSubscriber`),
> **plano** (`planType`), **satisfação** (`nps.score`), **motivo de saída** (`cancellationReason`).
> O refinamento de 09/06 zerou ~23% de "indefinido" (54→2), revelando 33 promotores e 11 passivos.

**Leitura de growth:** 3 alvos imediatos = (1) 100 silenciosos → coletar NPS (saúde da base);
(2) 34 "vai expirar" → reter antes de perder acesso; (3) 27 churn rápido → consertar a fricção de
entrada. Bônus: **33 promotores + futuros embaixadores = base de depoimentos reais** (o site hoje usa
depoimentos fake).

## 4. Como integra com o Escuta (já implementado, sem disparo)

Arquivos criados (workflow de 09/06, 40 testes, review PRONTO):
- `app/integrations/bizzu_partner.py` — cliente HTTP (GET-only, header X-API-Key, trata 401/404).
- `app/domain/segmentation/profiles.py` — `classify_profile()` puro (13 perfis).
- `scripts/sync_partner_customers.py` — `--dry-run` (só contagens, sem PII, sem banco); sem flag faz
  upsert do perfil em `Contact.profile_data["partner"]` (sem disparar WhatsApp).

Reaproveita o motor existente do Escuta (survey `trigger_event`, dispatcher, cooldown 7d, dedup). As
surveys 🆕 (Retenção, Indicação, CSAT Onboarding, Escuta de Detrator) reusam o mesmo motor. **Nenhum
disparo automático nesta fase** — só sync + classificação + preparação.

**Rodar:** `py scripts/sync_partner_customers.py --dry-run` (auditar) · sem `--dry-run` faz o upsert.
