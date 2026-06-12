# Handoff de Sessão — 12/06/2026

> Projeto **Escuta** (retenção/Voz do Cliente). Continuação do `SESSAO_HANDOFF_2026-06-10.md`.
> Frente desta sessão: **"voz do cliente ativa"** — abordagem dos **91 assinantes do plano anual ativo**
> (a tela que o Jair usa para falar 1-a-1 no WhatsApp). 3 agentes em paralelo + 1º commit consolidando
> todo o débito uncommitted. Sessão Claude: `35be6285-ae37-43e7-a12a-419c001d6287`.

## 🟢 Estado atual
- **Painel de abordagem dos anuais ativos no ar (local)**: `export --real` puxou **233 clientes → 91
  anuais ativos** (60 `ativo_silencioso`, 17 `ativo_promotor`, 6 `ativo_passivo`, 5 `ativo_recente`,
  3 `ativo_em_risco`; objetivo: 71 `nps`, 20 `relacionamento`). HTML gerado e aberto (contém PII → **fora do git**).
- **Repositório consolidado**: commit **`4f66e37`** em `master` — 76 arquivos, primeiro commit do acúmulo
  de várias sessões (Mega Central, chatbot, perfis, integração Bizzu, campanha anuais). `.env`, `venv/`,
  `*.db` e `abordagem-anuais.html` (PII) ficaram fora via `.gitignore`. **Working tree limpo.**
- **158 testes verdes** (era 136 no handoff de 10/06; +22 entre perfis/profile_surveys/survey_agent/brain).
- **Stack NÃO está de pé** nesta máquina; Supabase cloud `nlqeargxkidygbrahkbk` inalcançável daqui (DNS).

## ✅ Construído (11–12/06)
**Campanha "anuais ativos" (voz do cliente ativa):**
- `scripts/export_anuais_ativos.py`: puxa a **API de Clientes (Partner)** da Bizzu (`BIZZU_PARTNER_API_KEY`),
  filtra `state == active_paying` + `planType` anual, classifica por perfil e injeta no template. `--demo`
  gera 8 fictícios sem tocar API/PII. **NÃO dispara** mensagem; stdout sem PII.
- `scripts/seed_bizzu.py`: **3 surveys novas** — `Check-in Bizzu` (exit), `Renovação Anual Bizzu` (exit),
  `Novidade Bizzu` (nps) — com os textos on-brand do `docs/campanhas/mensagens-anuais-ativos.md`; e a
  **variação on-brand neutra da `NPS Bizzu`** (não comemora antes de saber a nota).
- `app/domain/segmentation/profile_surveys.py`: roteamento perfil→survey com **rotação Check-in↔Indicação**
  por cooldown (`PROFILE_SURVEY_ROTATION` + `survey_cycle_for_profile()`); primária preservada p/ não mexer nos testes.
- `scripts/dispatch_by_profile.py`: argumento **`--plan anual`** (filtra `profile_data['partner'].subscription.planType`,
  tolerante; sem `--plan` = comportamento idêntico) + **templating** de `{meses_de_casa}`, `{dias_para_renovar}`,
  `{novidade}` com fallback gracioso (nunca vaza `{placeholder}` cru).
- `docs/campanhas/_abordagem-anuais.template.html`: vira **worklist** — botão **"já contatei"** persistido em
  `localStorage` (chave estável por whatsapp/email, sobrevive à regeneração) + contador; **ordenação "⚡ Prioridade"**
  (default: em-risco → renovação próxima → detratores; contatados descem); **filtro por objetivo**; "ocultar
  contatados". *Copiar* + *abrir wa.me com texto pré-preenchido* já existiam. Corrigido bug do marcador
  `/*__CLIENTES__*/` **duplicado** num comentário (injeção dupla) → agora único.

**NPS conversacional sensível à nota** (descoberta: já estava em código uncommitted, faltava cobertura):
- Follow-up **adaptativo por faixa** (detrator acolhe+causa-raiz / passivo "o que faltou p/ 10" / promotor
  comemora+indicação), **aprofundamento de resposta vaga** (teto `MAX_FOLLOWUPS=2`) e **reconciliação
  nota×texto** já vivem em `app/domain/survey/{brain,resolver}.py`.
- `tests/test_brain.py`: **+11 testes** (10→21) provando que a nota chega ao LLM e que cada conduta dispara.
  Nenhuma mudança de código de produção foi necessária nesta frente.

## 🟡 Onde paramos / próximos passos
**Decisões que dependem do usuário / Felipe:**
1. **Validar volume real do disparo** (com a stack de pé): `py scripts/dispatch_by_profile.py plan --plan anual`
   (dry-run, sem PII) → conferir volumes antes de qualquer envio.
2. **Disparar WhatsApp real** — NÃO foi feito (escolha consciente; WAHA viola ToS, risco de ban). Só com OK
   explícito e `--limit` baixo.
3. **Ligar o agente conversacional** (`SURVEY_AGENT_ENABLED=1`): o default em prod é o determinístico (que já
   é sensível à nota); o modo "conduzido" precisa ser validado com **Groq real** antes de ligar.
4. Pendências de ATIVAÇÃO ainda abertas do handoff 10/06 (aplicar os 4 patches no backend, `alembic upgrade head`,
   `seed_bizzu`, `sync_partner_customers` real) seguem válidas.

**Backlog técnico (puxado do §7 do MASTER):**
- Popular `partner.novidade` no `sync_partner_customers.py` p/ o templating `{novidade}` sair do fallback.
- Reescrever `questions` da `NPS Bizzu` já existente (hoje o get-or-create só patcheia trigger/ingest_mode).

## 🔧 Como religar a stack
Ver skill **`escuta-stack`** (sobe API :8000 / painel :3001 / WAHA :3000 + Podman). Não duplicar comandos aqui.

## ⚠️ Pegadinhas (desta sessão)
- **`export_anuais_ativos.py` usa a API de Clientes da Bizzu (`api.bizzu.ai`, `BIZZU_PARTNER_API_KEY`), NÃO o
  Supabase** — por isso `--real` funcionou mesmo com o Supabase cloud fora do ar (são caminhos distintos).
- **`venv/` não estava no `.gitignore`** (só `.venv/`) — adicionado, junto com `*.db`, antes do `git add -A`,
  senão o commit arrastaria o ambiente virtual inteiro e o `_demo360.db`.
- **Seed idempotente não reescreve `questions`**: surveys que já existem no banco mantêm o texto antigo; a
  variação on-brand da NPS só vale em **seed novo** (decisão consciente p/ não clobberar edições do painel).
- **Templating por contato = 1 SurveyRun por contato** (só quando há placeholder), por causa do limite de não
  tocar `dispatcher.py`; cooldown segue correto (shim preserva o `survey.id` real).

## 🔑 Refs rápidas
- Campanha: `scripts/export_anuais_ativos.py`, `scripts/dispatch_by_profile.py`, `scripts/seed_bizzu.py`,
  `app/domain/segmentation/profile_surveys.py`, `docs/campanhas/_abordagem-anuais.template.html`,
  `docs/campanhas/mensagens-anuais-ativos.md`.
- NPS adaptativo: `app/domain/survey/brain.py`, `app/domain/survey/resolver.py`, `tests/test_brain.py`.
- Envs (por nome, sem valor): `BIZZU_PARTNER_API_KEY`, `BIZZU_PARTNER_API_URL`, `GROQ_API_KEY`,
  `SURVEY_AGENT_ENABLED` (default 0), `LLM_ENABLED` (default 1).
- HTML do painel (PII, fora do git): `docs/campanhas/abordagem-anuais.html` (regenerar com `py scripts/export_anuais_ativos.py`).
