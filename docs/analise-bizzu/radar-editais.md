> Exploração profunda realizada em 08/06/2026. Clone local: `C:\Users\jboni\Documents\Projetos\bizzu-repos\radar-editais`. Fontes: `CLAUDE.md` (fonte única do repo), `src/radar_editais/*` (todos os módulos lidos), `pyproject.toml`, `docker-compose.yml`, `docs/radar-editais.md` (contrato cross-repo).

# Radar de Editais — Análise Profunda

## Resumo Executivo

- Monitor diário de concursos públicos brasileiros: coleta via MCP do PCI Concursos, enriquece com Gemini, baixa PDFs para S3 e persiste tudo em Postgres próprio (porta 5434). Não compartilha banco com a plataforma principal.
- Pipeline de 5 fases (discover → filter → normalize → diff → enrich+persist) levando ~15 min/rodada; o diff classifica editais como `novos / atualizados / mesmos / encerrados` a cada sync.
- Gemini é usado em três pontos distintos: (1) filtro de seleções ambíguas (efetivo vs PSS), (2) extração estruturada de campos da notícia (banca, taxa, fases, data de prova, prova objetiva, PSS), e (3) classificação de PDFs candidatos antes do download.
- Flag `interesse_bizzu` (indexada em Postgres) é a regra de negócio central: só concursos com prova objetiva + conteúdo programático são sinalizados; os demais ficam ocultos com `motivo_descarte` gravado.
- Segurança de serviço via `X-Radar-Api-Key` (HMAC constant-time); UI via JWT HS256 delegado à `api.bizzu.ai`. Porta default real é 7400 (não 8000 como alguns docs legados citam).
- Não existe hoje nenhum mecanismo de notificação a usuários (sem webhook out, sem WhatsApp, sem e-mail).
- Oportunidade clara e cirúrgica para Escuta: conectar no evento `diff.novos` (linhas 297-317 de `pipeline.py`) para disparar WhatsApp "saiu o edital do seu concurso" — um único ponto de integração, sem modificar a lógica existente.

---

## 1. Propósito e Stack

### O que faz

O radar detecta diariamente quais concursos públicos brasileiros são novos ou foram atualizados, enriquece os dados via IA (banca, taxa de inscrição, data de prova, PDFs), aplica um filtro de relevância para a Bizzu e persiste tudo em banco próprio. É a "fonte da verdade de editais" do ecossistema Bizzu, operando de forma independente da plataforma principal.

Origem do nome: era `pci_mcp` (renomeado em maio de 2026 para `radar-editais`).

### Stack runtime

| Camada | Tecnologia |
|---|---|
| HTTP / API | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 async (`Mapped[]`) |
| DB driver | asyncpg |
| Banco | PostgreSQL 16 — porta **5434** (dev/Docker), banco próprio `radar-editais` |
| Migrations | Alembic (async env.py) |
| Storage S3 | aioboto3 (MinIO em dev, AWS S3 em prod) |
| Config | pydantic-settings (lê `.env.local`, gitignored) |
| CLI | Typer + Rich (`radar-editais sync|status|show|ui|db|prune|reenrich`) |
| Scraping | Crawl4AI (Chromium headless) |
| LLM | Google Gemini via `google-genai` SDK — modelo `gemini-3.1-flash-lite` |
| Testes | pytest + pytest-asyncio + pytest-postgresql (DB efêmero) + pytest-httpx |

### Agendamento

Não há scheduler embutido. O sync é disparado por:
- `scripts/cron-daily.sh` (bash wrapper para `crontab -e`, roda às 07h00)
- Systemd timer `radar-editais-sync.timer` na EC2 de produção (já foi encontrado inativo — ponto de atenção operacional)
- `POST /api/sync` da UI (botão "Sincronizar" — single-flight, background)

---

## 2. Pipeline — as 5 Fases

Código: `src/radar_editais/pipeline.py:run_pipeline()` (função assíncrona).

### Fase 1 — DISCOVER (`pipeline.py:242-253`)

Chama `McpClient.listar_concursos(regiao=r)` para cada uma das 5 regiões (`norte/nordeste/centro-oeste/sudeste/sul`). O cliente (`mcp_client.py`) fala JSON-RPC 2.0 sobre HTTPS com `https://www.pciconcursos.com.br/mcp`. Dedup por `noticia.id` (`_dedup_listings`, linha 45). Resultado: lista de `ConcursoListing` (Pydantic, campos: `titulo`, `cargos`, `uf`, `regiao`, `datas`, `noticia.link`, `apostila`).

### Fase 2 — FILTER (`pipeline.py:258-271`, `filter.py`)

Três sub-fases em sequência:

1. **Blocklist**: string-match em `titulo + cargos_resumo + noticia.titulo` contra ~40 marcadores (PSS, temporário, estágio, residência, cargo comissionado, remoção, CLT, brigadista, bolsista etc.) + regex `\breda\b`. Se bater: descarta imediatamente.
2. **Allowlist**: se contém "concurso público", "edital de concurso", "concurso de provas" etc.: aprova sem LLM.
3. **Gemini Flash**: para os ambíguos que não bateram em nenhuma das listas acima, dispara chamadas paralelas (`asyncio.gather`) ao Gemini com prompt de classificação binária (sim/não). Fallback conservador: `False` (descarta) em caso de erro.

A fase FILTER é **drop** — listings rejeitados aqui não chegam ao banco. É diferente do `interesse_bizzu` (que é soft-flag pós-enriquecimento).

### Fase 3 — NORMALIZE (`pipeline.py:278-283`)

Para cada listing aprovado, busca o registro anterior no banco (`ConcursoRepo.get(f"pci-{noticia_id}")`). Se existe, preserva `first_seen`, `enrichment` e `anexos_pdf` — garantia de que um resync não apaga dados de enriquecimento já feitos. Converte `ConcursoListing` → `Concurso` (modelo canônico Pydantic).

ID canônico: `pci-{noticia.id}` (ex.: `pci-98765`).

### Fase 4 — DIFF (`pipeline.py:285-293`, `repositories.py:260-287`)

Compara o estado atual com o snapshot de ontem (`SnapshotItemORM`). Campos rastreados: `inscricao_fim`, `inscricao_inicio`, `aberto`, `vagas_total`, `cargos`. Produz `DiffResult` com 4 listas: `novos / atualizados / mesmos / encerrados`.

### Fase 5 — ENRICH + PERSIST (`pipeline.py:297-342`)

Processa apenas `novos + atualizados`. Para cada um:

1. **Crawl4AI** (`enrich.py:fetch_noticia_markdown`): abre o link da notícia com Chromium headless, retorna markdown + HTML bruto + links externos.
2. **Gemini extração** (`enrich.py:extract_fields_via_gemini`): envia markdown truncado (30 000 chars) com prompt estruturado, extrai 13 campos: `banca`, `taxa_inscricao`, `data_prova`, `url_inscricao`, `fases`, `jornada_horas`, `regime`, `validade_anos`, `validade_prorrogavel`, `tem_prova_objetiva`, `tem_conteudo_programatico`, `eh_processo_seletivo_simplificado`, `extraction_confidence`. O resultado é armazenado em `Concurso.enrichment`.
3. **PDF discovery** (`pdf_extractor.py:collect_pdf_candidates`): varre o HTML por links com `.pdf`, textos-âncora com palavras-chave (edital, anexo, errata…) e domínios de bancas conhecidas (cebraspe, fgv, vunesp, ibfc etc.).
4. **Gemini classificação de PDFs** (`pdf_extractor.py:classify_candidates_with_gemini`): para cada candidato, decide tipo (`edital_principal`, `errata`, `retificacao`, `anexo_conteudo_programatico`, `anexo_outro`, `irrelevante`) e `should_download`.
5. **Download + S3** (`pdf_extractor.py:download_pdf`): baixa os PDFs marcados como `should_download=True`, valida magic bytes PDF (`%PDF-`), tamanho mínimo (50 KB), faz upload para S3 com chave `concursos/{slug}/{filename}`. Metadados (sha256, size, s3_key) persistidos em `anexos_pdf`.
6. **`aplicar_interesse(c)`** (`interesse.py`): define `interesse_bizzu` e `motivo_descarte` (ver §4).
7. **`ConcursoRepo.upsert(c)`** + `session.commit()`: commit **por concurso** (a UI vê dados progressivamente durante o sync longo).

Ao final, snapshot completo do dia é salvo em `SnapshotORM + SnapshotItemORM`.

**Tolerância a falhas**: erro em `_enrich_one` ou `upsert` de um concurso individual não derruba o run (try/except por item, rollback local, continua).

---

## 3. Modelo de Dados

### Entidades principais

**`concursos`** (tabela Postgres, mapeada em `db/orm.py:ConcursoORM`):

| Campo | Tipo | Nota |
|---|---|---|
| `id` | TEXT PK | `pci-{noticia_id}` |
| `slug` | TEXT UNIQUE | `{titulo-slugificado}-{uf}-{data_inicio}` |
| `titulo` | TEXT | título original do MCP |
| `uf`, `regiao`, `scope`, `esfera` | TEXT | normalizados |
| `cargos` | ARRAY(TEXT) | lista extraída |
| `vagas_total`, `salario_max` | INT, NUMERIC | parseados de `vagas_salario` |
| `inscricao_inicio`, `inscricao_fim` | DATE | |
| `aberto`, `dias_restantes` | BOOL, INT | |
| `banca` | TEXT | extraída pelo Gemini, coluna quente |
| `interesse_bizzu` | BOOL (indexado) | flag de relevância Bizzu |
| `first_seen`, `last_synced` | DATE, TIMESTAMPTZ | |
| `extra` | JSONB | `enrichment` completo + `motivo_descarte` |

**`anexos_pdf`** (metadados de PDFs; binários ficam no S3):

| Campo | Nota |
|---|---|
| `concurso_id` | FK `concursos.id` ON DELETE CASCADE |
| `tipo` | `edital_principal`, `errata`, `retificacao`, `anexo_conteudo_programatico`, etc. |
| `s3_key` | `concursos/{slug}/{filename}` |
| `sha256`, `size_bytes` | validação de integridade |
| `llm_classification`, `llm_summary` | output do Gemini sobre o PDF |

> Armadilha herdada: `AnexoPdf.local_path` (campo Pydantic) guarda o `s3_key` por decisão de migração — renomeação pendente (`CLAUDE.md` §Anti-padrões).

**`snapshots` + `snapshot_items`**: registro diário de estado para o diff. `snapshot_items.data` guarda o `Concurso.model_dump()` completo em JSONB, incluindo o `enrichment`.

### Flag `interesse_bizzu` — a regra de negócio central

Definida em `interesse.py:aplicar_interesse(c)` após o enriquecimento:

1. `selecao_nao_efetiva`: título/cargos batem na blocklist do `filter.py` (cobertura de legados).
2. `processo_seletivo_simplificado`: campo `enrichment.regime` contém marcador de temporário/regime especial (exceto carreiras policiais com "regime especial de trabalho policial").
3. `sem_prova_objetiva`: `tem_prova_objetiva=False` nas fases do Gemini, e sem PDF de conteúdo programático.
4. `None` → `interesse_bizzu=True`: interessa, ou inconclusivo (sem sinal suficiente → benefício da dúvida).

**A flag `eh_processo_seletivo_simplificado` do Gemini NÃO é usada na decisão** — em produção marcou ~95% de falso positivo lendo só a notícia. Está extraída apenas para inspeção.

Comando `radar-editais prune [--apply]` reaplica a regra a todo o banco (útil após mudança de critério). Comando `radar-editais reenrich [--abertos] [--so-faltando-flag]` re-roda o Gemini sem re-baixar PDFs.

---

## 4. Integração com o Backend Principal

### Auth de serviço

`auth.py` define dois esquemas:

- **Cookie JWT HS256** (role `MANAGER`): obtido via `POST /api/auth/login`, que proxeia credenciais para `https://api.bizzu.ai/auth/login`. O JWT recebido é validado com o `JWT_SECRET` local e armazenado como cookie `httponly; samesite=lax; secure`.
- **`X-Radar-Api-Key`** (role `SERVICE`): chave estática configurada em `RADAR_SERVICE_API_KEY` (.env.local). Comparação HMAC constant-time (`hmac.compare_digest`) para evitar timing attack. Acesso negado se a chave não estiver configurada (nunca concede por padrão). Rotas `GET /api/concursos` e `GET /api/concursos/{id}` e `GET /pdf/...` aceitam ambos (dependency `require_manager_or_service`).

### Sincronização de editais para a plataforma

O radar **não escreve diretamente** no banco da plataforma. A integração documentada (`docs/radar-editais.md` §8) é por **export para Google Sheet**, que o backend importa via `editais-garimpados` (flow `importacao-edital.md`). O mecanismo exato (Radar → Sheet automático ou export manual) não está implementado no código do repo — é um passo operacional externo.

Para consumo automatizado, o backend pode chamar `GET /api/concursos` com `X-Radar-Api-Key` — a API já retorna apenas `interesse_bizzu=true` por padrão.

---

## 5. Notificações — Estado Atual e Oportunidade Escuta (CRÍTICO)

### Estado atual: zero notificações

O radar **não notifica nenhum usuário**. A única saída "notificação" é o relatório markdown diário (`reporter.py:write_daily_report`) gravado em `data/reports/<date>.md` — não é enviado a ninguém, é apenas log local.

Não há: webhook OUT, integração WhatsApp, e-mail, push notification, ou qualquer canal de comunicação com usuários finais.

### Oportunidade: evento `novo_edital` → WhatsApp via Escuta

O ponto de integração é cirúrgico e está claramente demarcado em `pipeline.py`.

**Onde plugar** — `src/radar_editais/pipeline.py`, linhas 297-327:

```python
# Fase 5 — ENRICH + PERSIST
to_enrich = diff.novos + diff.atualizados   # linha 297
...
for i, c in enumerate(to_enrich, start=1):
    ...
    try:
        _, n_pdfs = await _enrich_one(c, pdf_storage=pdf_storage)
    ...
    aplicar_interesse(c)   # linha 317 — depois daqui, interesse_bizzu já está calculado
    # PONTO DE GANCHO: se c.interesse_bizzu and c.id in diff_novos_ids → disparar Escuta
    try:
        await concurso_repo.upsert(c)
        await session.commit()
```

**Implementação mínima sugerida**:

1. Adicionar variável `ESCUTA_WEBHOOK_URL` e `ESCUTA_API_KEY` em `config.py` (linha 19, após `service_api_key`).
2. Criar `src/radar_editais/notifications/whatsapp.py` com função async `notify_novo_edital(concurso: Concurso, webhook_url: str, api_key: str)`.
3. Em `pipeline.py`, após `aplicar_interesse(c)` (linha 317), adicionar:

```python
if c.interesse_bizzu and c.id in novos_ids_set:
    await notify_novo_edital(c, settings.escuta_webhook_url, settings.escuta_api_key)
```

**Payload recomendado para o Escuta**:

```json
{
  "event": "novo_edital",
  "edital_id": "pci-98765",
  "titulo": "Concurso Público — Prefeitura de Fortaleza CE",
  "uf": "CE",
  "regiao": "nordeste",
  "esfera": "municipal",
  "cargos": ["Analista de TI", "Contador"],
  "inscricao_fim": "2026-07-15",
  "dias_restantes": 37,
  "banca": "CEBRASPE",
  "taxa_inscricao": 85.0,
  "data_prova": "2026-09-14",
  "url_inscricao": "https://www.cebraspe.org.br/concursos/...",
  "noticia_link": "https://www.pciconcursos.com.br/...",
  "has_edital_pdf": true,
  "has_conteudo_programatico_pdf": true
}
```

**Dados já prontos no radar** que enriquecem a mensagem WhatsApp:
- `enrichment.banca` — "saiu o edital do CEBRASPE para Fortaleza!"
- `enrichment.taxa_inscricao` — mencionar taxa na mensagem
- `enrichment.data_prova` — "prova em setembro"
- `dias_restantes` — "faltam 37 dias para se inscrever"
- `cargos` — personalizar por cargo de interesse do usuário
- Link S3 para o PDF do edital principal (`GET /pdf/{slug}/{filename}` → presigned URL)

**Desafios operacionais**:

- O sync leva ~15 min → notificações chegam no "dia seguinte de manhã", não em tempo real (aceitável para o caso de uso de alertas diários).
- O Escuta precisará de uma tabela de preferências: qual usuário quer ser notificado sobre qual UF/cargo/esfera. Essa tabela vive no Escuta ou na plataforma Bizzu, não no radar.
- O radar não tem tabela de usuários — o cruzamento "qual usuário quer este edital" precisa ser feito no Escuta (recebe o evento com todos os dados, consulta suas próprias preferências, decide quem notificar).
- LGPD: usuário precisa ter optado por receber alertas WhatsApp. O opt-in deve existir na plataforma Bizzu antes de o Escuta disparar.

---

## 6. Qualidade, Dívida e Segurança

### Pontos de qualidade positivos

- Pipeline skip-tolerant por concurso: falha de enrich ou upsert não derruba o run.
- Commit incremental por concurso: UI fica atualizada progressivamente.
- `interesse_bizzu` é soft-flag (reversível): nenhum dado é deletado.
- Dedup robusto por `noticia.id` no discover; upsert resolve slug collision preservando `first_seen`.
- `immutable_unaccent()` como wrapper IMMUTABLE para o índice GIN trigram em `titulo` (solução correta para o Postgres que não aceita `unaccent()` STABLE em índices).
- Testes: ~28 arquivos de teste, incluindo DB ephêmero (pytest-postgresql), mocks httpx, e2e smoke.

### Dívida técnica conhecida

- `AnexoPdf.local_path` (campo Pydantic) guarda `s3_key` por decisão de migração; deve ser renomeado para `s3_key` em refactor futuro. Documentado em `CLAUDE.md` §Anti-padrões.
- `docs/plans/2026-05-07-*.md` descreve arquitetura antiga (JSON files); pode confundir se lida sem contexto. `CLAUDE.md` é a fonte única válida.
- Borda Radar → Google Sheet não automatizada (conforme `docs/radar-editais.md` §8 — "confirmar o mecanismo exato com o time").
- Systemd timer em produção já foi encontrado inativo (`CLAUDE.md` §"Branch deployado").
- Porta documentada no README como 8000, mas default real do CLI é 7400 (variável `PORT`).

### Segurança

**Segredos a observar** (locais, não expostos aqui):

- `.env.example` contém valores de exemplo hardcoded — incluindo `S3_ACCESS_KEY`, `S3_SECRET_KEY` e `GEMINI_API_KEY` com valores que parecem reais (não genéricos). Se esses valores foram comprometidos/rotacionados, o `.env.example` deve ser atualizado com placeholders `<SUBSTITUIR>`. Arquivo: `radar-editais/.env.example`, linhas 6-10 e 14.
- `JWT_SECRET` em `.env.example` tem valor padrão fraco (`change-me-in-production!@2`) — certifique-se de que `.env.local` de produção usa um segredo forte.

**Pontos positivos de segurança**:
- `X-Radar-Api-Key` usa `hmac.compare_digest` (constant-time, sem timing attack).
- Chave de serviço nunca concede acesso se não estiver configurada (`not configured or not provided → False`).
- Anti path-traversal em `GET /pdf/{slug}/{filename}` e `/img/{noticia_id}` (checa `/` e `..`).
- Cookie JWT com `httponly=True`, `samesite="lax"`, `secure=True`.
- Sem tabela de usuários no radar (superfície de ataque zero para PII).

---

## 7. Arquivos-Chave

| Arquivo | Papel |
|---|---|
| `CLAUDE.md` | Fonte única de verdade — arquitetura, setup, anti-padrões, gotchas |
| `src/radar_editais/pipeline.py` | Orquestrador das 5 fases; **PONTO DE GANCHO para Escuta nas linhas 297-327** |
| `src/radar_editais/models.py` | Modelo canônico `Concurso`, `Enrichment`, `AnexoPdf` (Pydantic) |
| `src/radar_editais/db/orm.py` | 4 tabelas ORM (SQLAlchemy 2.0): `concursos`, `anexos_pdf`, `snapshots`, `snapshot_items` |
| `src/radar_editais/db/repositories.py` | `ConcursoRepo.upsert`, `SnapshotRepo.diff_against`, `DiffResult` |
| `src/radar_editais/enrich.py` | Crawl4AI + Gemini; prompt de extração; modelo `gemini-3.1-flash-lite` |
| `src/radar_editais/filter.py` | Blocklist + allowlist + Gemini para seleções não-efetivas |
| `src/radar_editais/interesse.py` | Regra `motivo_descarte` + `aplicar_interesse` — central para o filtro Bizzu |
| `src/radar_editais/pdf_extractor.py` | Discovery, classificação Gemini e download de PDFs → S3 |
| `src/radar_editais/auth.py` | JWT HS256 cookie (MANAGER) + X-Radar-Api-Key HMAC (SERVICE) |
| `src/radar_editais/config.py` | `Settings` pydantic-settings; vars: DATABASE_URL, S3_*, GEMINI_API_KEY, JWT_SECRET, PLATFORM_API_URL, RADAR_SERVICE_API_KEY |
| `src/radar_editais/ui/server.py` | FastAPI: todas as rotas REST + lógica de sync em background |
| `src/radar_editais/mcp_client.py` | Cliente JSON-RPC 2.0 para `pciconcursos.com.br/mcp` |
| `src/radar_editais/normalize.py` | Slug, scope, esfera, `tem_prova_objetiva`, parse de vagas/salário |
| `src/radar_editais/reporter.py` | Relatório markdown diário do diff (log local, não enviado) |
| `docs/radar-editais.md` | Contrato cross-repo: contratos de API, filtro `interesse_bizzu`, borda com plataforma |
| `docker-compose.yml` | Dev stack: Postgres 16 (porta 5434) + MinIO (9000/9001) |
| `.env.example` | Template de variáveis — **contém valores de exemplo possivelmente reais** (ver §6 Segurança) |
| `scripts/cron-daily.sh` | Wrapper bash para crontab: `radar-editais sync` às 07h00 |
