# Integração de Feedback (retenção) — contexto completo

> A cadeia de retenção do Escuta: **API de Clientes da Bizzu → 13 perfis → survey por perfil →
> disparo seletivo (em teste)**. Doc útil pro chat (estratégia) e referência da implementação.
> Atualizado 2026-06-09.

## 1. A cadeia (visão)
```
API de Clientes (233)  ──►  classify_profile (13 perfis)  ──►  PROFILE_TO_SURVEY  ──►  dispatch_by_profile
  bizzu_partner.py            profiles.py                       profile_surveys.py       (--dry-run / --force)
  (GET, X-API-Key)            grava em Contact.profile_data['partner']                   reusa SurveyDispatcher
```

## 2. O motor de survey do Escuta (já existente)
- **Modelos** (`app/models/survey.py`): `Survey(type 'nps'|'exit', questions[], trigger_event)`, `SurveyRun`, `SurveyResponse(status sent→awaiting_reason→closed; + score, nps_bucket, answer_text, sentiment/themes/ai_meta)`.
- **Tipos de survey:** `nps` = pergunta de nota 0-10 + follow-up aberto + thanks. `exit` = **só pergunta aberta** + thanks (nasce em `awaiting_reason`, a resposta de texto fecha).
- **Dispatcher** (`app/domain/survey/dispatcher.py`): `dispatch(survey, contacts, trigger)` cria a run + uma `SurveyResponse` por contato (idempotente) e envia a 1ª pergunta via WAHA. Saudação automática `Oi {primeiro_nome}!`.
- **Disparo automático por evento** (`/api/events/bizzu`): surveys com `trigger_event` (`subscription_cancelled` → Exit; `topic_completed` → CSAT Tópico) disparam sozinhas no evento.
- **Disparo manual** (`scripts/dispatch_nps.py`): `list` inspeciona; `dispatch --phone X --force` envia (o `--force` é exigido quando o WAHA é o real na `:3000` — fricção proposital).

## 3. Os 13 perfis → survey (mapeamento)
| Perfil | Qtd | Survey | Por quê |
|--------|----:|--------|---------|
| ativo_silencioso | 100 | **NPS Bizzu** | nunca opinou → coletar nota |
| vai_expirar | 34 | **Retenção Bizzu** 🆕 | reter antes de perder acesso |
| ativo_promotor | 33 | **Indicação Bizzu** 🆕 | fã → depoimento/indicação |
| churn_rapido | 27 | **Exit Bizzu** | o que não atendeu de cara |
| ativo_passivo | 11 | **NPS Bizzu** | empurrar de neutro p/ promotor |
| churn_outro | 11 | **Exit Bizzu** | exit genérico |
| churn_involuntario | 6 | **— (não contatar)** | já recebe winback por e-mail |
| ativo_em_risco | 5 | **Escuta de Detrator Bizzu** 🆕 | ouvir antes de virar churn |
| ativo_recente | 2 | **CSAT Onboarding Bizzu** 🆕 | 1ª impressão |
| indefinido | 2 | **— (não contatar)** | anômalo |
| cortesia | 1 | **NPS Bizzu** | feedback qualitativo |
| churn_pos_uso | 1 | **Exit Bizzu** | por que parou após usar |
| embaixador | 0 | **Indicação Bizzu** 🆕 | (surge com o tempo) |

## 4. Roteiros das surveys (copy on-brand)
**NPS Bizzu** *(nps, existe)* — "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?" → "Massa! 🙌 Por quê?"
**Exit Bizzu** *(exit, existe)* — "vi aqui que você cancelou sua assinatura do Bizzu 😕 Pode me contar em uma frase o que pesou na decisão? Sua resposta vai direto pro time."
**CSAT Onboarding Bizzu** 🆕 *(nps)* — "vi que você começou no Bizzu faz pouco tempo 👋 De 0 a 10, como tá sendo a experiência até agora?" → "O que faria essa nota subir?"
**Escuta de Detrator Bizzu** 🆕 *(exit)* — "vi que sua experiência com o Bizzu não tá sendo a melhor 😕 Pode me contar, em uma frase, o que mais tá te incomodando? Quero levar direto pro time."
**Retenção Bizzu** 🆕 *(exit)* — "vi que seu acesso ao Bizzu tá quase no fim ⏳ Antes de ir: tem alguma coisa que faria você continuar com a gente?"
**Indicação Bizzu** 🆕 *(exit)* — "que bom te ver curtindo o Bizzu! 🙌 Me conta em uma frase o que mais te ajudou — e, se topar, uso como depoimento (só com seu ok). Quer indicar um amigo? manda o contato. 💙"

## 5. Como operar (a partir da raiz `escuta/`)
1. **Classificar a base:** `py scripts/sync_partner_customers.py --dry-run` (audita) → sem flag faz o upsert dos perfis nos contatos.
2. **Criar/garantir as surveys:** `py scripts/seed_bizzu.py` (idempotente; cria as 4 novas).
3. **Ver o plano de disparo:** `py scripts/dispatch_by_profile.py plan` (mostra perfil → survey → nº elegíveis, **sem enviar**).
4. **Testar disparo real (controlado):** `py scripts/dispatch_by_profile.py dispatch --profile <perfil> --limit 1 --force` (só com opt-in e em teste Jair↔Felipe).

## 6. Segurança / regras
- **Disparo só com opt-in** (`Contact.opt_in`) **e** `should_contact=True` no perfil.
- **Cooldown 7 dias:** não reenviar se já há `SurveyResponse` recente p/ o mesmo contato+survey.
- **`churn_involuntario` e `indefinido` nunca recebem** (mapeiam para None).
- **Double-touch:** churn por pagamento já recebe winback por e-mail da Bizzu — coordenar com o Felipe.
- **WAHA real (`:3000`) exige `--force`**; WAHA viola ToS → só teste pequeno antes de produção.
- **PII:** o `plan`/dry-run só imprime contagens — nunca nome/e-mail/telefone.
