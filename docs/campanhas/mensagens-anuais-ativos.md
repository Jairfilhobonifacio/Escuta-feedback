# Campanha — Abordagem dos assinantes do plano ANUAL ATIVO (WhatsApp / Escuta)

> Gerado 2026-06-11. Mensagens on-brand para contatar, via WhatsApp (Escuta), os clientes
> do **plano anual que estão ativos pagantes**. Fonte dos clientes: **API de Clientes**
> (`GET /partner/customers`, `BIZZU_PARTNER_API_KEY`) → filtrar `subscription.planType == 'anual'`
> + `subscription.state == 'active_paying'`. As mensagens seguem o formato do `scripts/seed_bizzu.py`
> (cada uma vira uma `Survey`) e são disparadas por `scripts/dispatch_by_profile.py`.

## Regras de uso (LGPD / anti-ban) — valem para TODAS

1. **Só com `opt_in=True`** (campo `whatsappOptIn` sincronizado da Bizzu). A API serve para
   classificar e priorizar, não para forçar contato.
2. **Cooldown de 7 dias** por contato/survey (já no `dispatch_by_profile`).
3. **Throttle**: usar `--limit 50` por execução para não queimar o número (WhatsApp real = risco de ban).
4. **Sem double-touch**: quem já votou NPS no app entra por `ingest_mode` e NÃO recebe o NPS por WhatsApp.
5. **Saudação automática**: o dispatcher já prefixa `Oi {nome}!` — por isso os textos abaixo começam em minúscula.

## Mapa objetivo → perfil(s) anual ativo → survey

| Objetivo | Perfis-alvo (anuais ativos) | Survey | Status no seed |
|---|---|---|---|
| 📊 Coletar NPS / satisfação | `ativo_silencioso`, `ativo_passivo` | `NPS Bizzu` | já existe (variação abaixo) |
| 🤝 Relacionamento / check-in | `ativo_fiel`, `embaixador` | `Check-in Bizzu` | **NOVA** |
| 🔁 Renovação do plano anual | anuais ativos com `currentPeriodEnd` em ~15-30 dias | `Renovação Anual Bizzu` | **NOVA** |
| ✨ Novidade / nova feature | todos os anuais ativos | `Novidade Bizzu` | **NOVA** |

---

## 🤝 Objetivo 1 — Relacionamento / Check-in  (`Check-in Bizzu`)

Disparo periódico (a cada 60-90 dias) com o anual em dia, fora de janela de NPS/renovação. Só um oi + ouvir.

```python
{
    "name": "Check-in Bizzu",
    "type": "exit",          # 1 pergunta aberta + thanks
    "trigger_event": None,    # disparo manual por perfil
    "questions": [
        {"key": "reason", "kind": "open",
         "text": "passando só pra saber como tão indo seus estudos com o Bizzu 😊 me conta: tem rolado algo que eu possa levar pro time pra deixar sua rotina ainda melhor?"},
        {"key": "thanks", "kind": "thanks",
         "text": "valeu demais por compartilhar! adoro saber como você tá. qualquer coisa que precisar, é só chamar aqui que eu levo pro time. bons estudos! 🙌"},
    ],
}
```
**Variações da pergunta (A/B/C):**
- **A** "passando só pra saber como tão indo seus estudos com o Bizzu 😊 me conta: tem rolado algo que eu possa levar pro time pra deixar sua rotina ainda melhor?"
- **B** "tava aqui pensando em você e quis dar um oi 👋 como tá sendo sua experiência com o Bizzu ultimamente? pode falar o que tá bom e o que dá pra melhorar."
- **C** "faz um tempo que a gente não conversa e eu queria saber de você 😊 nos seus estudos agora, o que tá te ajudando mais e o que você sente que ainda falta?"

---

## 📊 Objetivo 2 — Coletar NPS / Satisfação  (`NPS Bizzu`)

Anual ativo que ainda não opinou. Follow-up **neutro** de propósito (não comemora antes de saber a nota — foi um problema real apontado pelo dono).

```python
{
    "name": "NPS Bizzu",     # já existe no seed — esta é a variação on-brand pro anual
    "type": "nps",
    "trigger_event": None,
    "questions": [
        {"key": "nps", "kind": "nps",
         "text": "queria saber como tá sua experiência com o Bizzu na sua rotina de estudos. De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"},
        {"key": "reason", "kind": "open",
         "text": "valeu por responder 🙏 conta pra mim o que pesou nessa nota? (pode mandar em texto)"},
        {"key": "thanks", "kind": "thanks",
         "text": "show, anotado aqui. obrigado pela sinceridade, isso ajuda demais a deixar o Bizzu melhor pra você."},
    ],
}
```
**Variações da abertura (A/B/C):**
- **A** "queria saber como tá sua experiência com o Bizzu na sua rotina de estudos. De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"
- **B** "tô passando só pra te ouvir de verdade 👀 De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo que também estuda pra concurso?"
- **C** (ancora no tempo de casa, exige templating) "você já tá com a gente faz {meses_de_casa} meses de Bizzu, e sua opinião pesa muito. De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"

---

## 🔁 Objetivo 3 — Renovação do plano anual  (`Renovação Anual Bizzu`)

Anual ativo e satisfeito cujo ciclo está renovando (`currentPeriodEnd` próximo). Tom de continuidade positiva, **nunca** "antes de ir" nem urgência. Plano anual = R$ 120/ano (R$ 10/mês), citar só se ajudar.

```python
{
    "name": "Renovação Anual Bizzu",
    "type": "exit",
    "trigger_event": None,
    "questions": [
        {"key": "reason", "kind": "open",
         "text": "fez quase um ano que você começou essa jornada com a gente 🎯 bora pra mais um ciclo de estudos juntos? me conta: o que o Bizzu mais te ajudou a destravar até aqui?"},
        {"key": "thanks", "kind": "thanks",
         "text": "valeu demais por seguir nessa com a gente 💙 bons estudos e conta comigo sempre que precisar!"},
    ],
}
```
**Variações da pergunta (A/B/C):**
- **A** "fez quase um ano que você começou essa jornada com a gente 🎯 bora pra mais um ciclo de estudos juntos? me conta: o que o Bizzu mais te ajudou a destravar até aqui?"
- **B** "tá chegando a hora de renovar seu plano e eu queria saber em primeira mão: o que você quer conquistar nesse próximo ano com o Bizzu do seu lado? 📚"
- **C** "esse ano de Bizzu rendeu, hein? 🙌 antes de seguirmos pro próximo, queria te ouvir: tem algo que tornaria sua rotina de estudos ainda melhor pra gente caprichar?"

> Coordenar para NÃO disparar no mesmo dia da cobrança automática de renovação.

---

## ✨ Objetivo 4 — Novidade / nova feature  (`Novidade Bizzu`)

Anuncia uma feature e mede a reação. `type nps` (0-10 = quanto animou) + porquê + thanks. Escolher 1 das 5 ferramentas reais (Raio-X da Prova, Bizzu do Tópico, Plano de Estudos, Questões Selecionadas, Revisões Inteligentes) ou usar `{novidade}`.

```python
{
    "name": "Novidade Bizzu",
    "type": "nps",
    "trigger_event": None,
    "questions": [
        {"key": "nps", "kind": "nps",
         "text": "saiu novidade no Bizzu e eu já pensei em você 👀 acabamos de soltar o Raio-X da Prova, que mostra em ranking quais tópicos do seu edital mais caem pra você atacar primeiro. De 0 a 10, o quanto isso te ajudaria hoje?"},
        {"key": "reason", "kind": "open",
         "text": "boa! me conta: o que você mais quer que o Bizzu te ajude a resolver agora nos estudos?"},
        {"key": "thanks", "kind": "thanks",
         "text": "anotado 💙 obrigado pelo retorno, isso ajuda a gente a priorizar o que constrói de novo. bons estudos!"},
    ],
}
```
**Variações da abertura (A/B/C):**
- **A** (Raio-X da Prova) "saiu novidade no Bizzu e eu já pensei em você 👀 acabamos de soltar o Raio-X da Prova, que mostra em ranking quais tópicos do seu edital mais caem pra você atacar primeiro. De 0 a 10, o quanto isso te ajudaria hoje?"
- **B** (Questões Selecionadas) "tem novidade fresquinha no Bizzu pra você 🙌 agora dá pra filtrar questões reais por tópico, direto do que a banca cobra. De 0 a 10, o quanto isso te deixa com vontade de voltar a treinar?"
- **C** (genérica com placeholder) "lançamos uma novidade no Bizzu e quis te avisar em primeira mão 👀 é o {novidade}, feito pra deixar seus estudos mais certeiros. De 0 a 10, o quanto isso te anima a dar uma olhada hoje?"

---

## Como colocar no ar

1. **Adicionar as 3 surveys novas** (`Check-in Bizzu`, `Renovação Anual Bizzu`, `Novidade Bizzu`) à
   lista `SURVEYS` em `scripts/seed_bizzu.py` e rodar o seed (idempotente).
2. **Mapear no roteamento** (`app/domain/segmentation/profile_surveys.py`): hoje `ativo_fiel`/`embaixador`
   apontam para `Indicação Bizzu`. Decidir quando usar Check-in vs Indicação (ex.: alternar por cooldown).
3. **Filtro `planType=anual`** no `dispatch_by_profile.py` — pequeno ajuste: o `planType` já é gravado
   em `Contact.profile_data['partner']`; basta adicionar um `--plan anual` que filtra junto do perfil.
4. **Conferir volumes (dry-run, sem PII):** `py scripts/dispatch_by_profile.py plan`
5. **Disparar (com OK p/ WhatsApp real):** `py scripts/dispatch_by_profile.py dispatch --profile ativo_fiel --limit 50 --force`

## Pendências de código (pequenas)
- `--plan anual` no `dispatch_by_profile` (filtro por `planType`).
- Templating de variáveis extras (`{meses_de_casa}`, `{dias_para_renovar}`, `{novidade}`) — hoje só o
  nome é resolvido na saudação. Sem o ajuste, usar as variações que dependem só do nome.
