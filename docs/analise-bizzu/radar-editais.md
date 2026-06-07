# Relatório do agente — Radar de Editais (gabarita-ai/radar-editais)

> Exploração automática em 07/06/2026. Clone local: `~/Documents/Projetos/bizzu-repos/radar-editais`.

## 1. O que é

**Monitor diário de concursos públicos brasileiros** — detecta editais novos/abertos.

Pipeline (5 fases):
1. **Discovery** — servidor MCP do PCI Concursos por região; dedup por noticia.id
2. **Filter** — remove seleções não-efetivas (PSS, temporário, estágio...) em 3 fases: blocklist → allowlist → **Gemini Flash** para ambíguos
3. **Normalize** — preserva `first_seen`/`enrichment`/`anexos_pdf` (sync incremental)
4. **Diff** — compara com snapshot do dia anterior → novos/atualizados/mesmos/encerrados
5. **Enrich + Persist** — Crawl4AI (HTML) + Gemini (banca, taxa, fases, data de prova, `tem_prova_objetiva`, `tem_conteudo_programatico`); baixa PDFs → S3; aplica flag `interesse_bizzu`; commit por concurso; snapshot do dia

Saída: Postgres + S3, consumível via REST (FastAPI) ou SQL.

## 2. Stack

Python 3.10+ · FastAPI/Uvicorn · SQLAlchemy 2.0 async (asyncpg) · PostgreSQL 16 (porta **5434**, banco próprio) · Alembic · S3 (MinIO dev / AWS prod) · Crawl4AI · Google Gemini (google-genai) · Typer+Rich CLI · pydantic-settings · JWT HS256 + `X-Radar-Api-Key` (HMAC constant-time) · pytest

Agendamento: cron manual (`radar-editais sync`) / K8s CronJob / systemd timer.

## 3. Notificações

**NÃO há sistema de notificação a usuários.**
- Sem webhook OUT, sem email/WhatsApp/SMS/push
- Relatório diário em markdown (`reporter.py` → `/data/reports/<date>.md`) — não é enviado a ninguém
- UI tem botão "Sincronizar" (POST `/api/sync` + polling `/api/sync/status`)
- Plataforma principal provavelmente importa dados manualmente (via Sheet — docs §8)

## 4. Dados de usuário

**Zero tabelas de usuários** (deliberado). Banco local: `concursos`, `anexos_pdf`, `snapshots`, `snapshot_items`.
Auth delegada: valida JWT contra `https://api.bizzu.ai` (`POST /auth/login`). Sem telefone/email/profile local.

## 5. Relação com o ecossistema

- Banco próprio (não compartilha o Postgres da plataforma)
- Auth delegada à plataforma; role MANAGER (cookie JWT) p/ UI; role SERVICE (`X-Radar-Api-Key`) p/ consumo automatizado
- Endpoints: `GET /api/tree`, `GET /api/concursos` (só `interesse_bizzu=true` p/ service), `GET /api/concursos/{id}`, `GET /api/stats`, `GET /pdf/{slug}/{filename}` (307 → S3 pré-assinada TTL 1h), `POST /api/sync`

## 6. Sinergia com WhatsApp (Escuta)

**SIM — clara.** Edital novo detectado (`status='novo'` no diff) → notificar usuários elegíveis via WhatsApp.

Ganchos:
- `src/radar_editais/pipeline.py` (~L100-150), fase ENRICH+PERSIST: após `aplicar_interesse(c)` e antes do `upsert(c)` → callback `on_edital_novo`
- Novo `src/radar_editais/notifications/whatsapp.py` + `ESCUTA_WEBHOOK_URL`/`ESCUTA_API_KEY` em `config.py` (~L19)
- Usuários/preferências: consultar plataforma principal (endpoint a confirmar)
- Auditoria opcional: tabela `whatsapp_notifications`

Payload exemplo:
```json
{ "to_phone": "+55...", "template": "edital_novo",
  "variables": { "titulo": "...", "uf": "CE", "inscricao_fim": "2026-06-30", "url": "...", "edital_id": "pci-12345" } }
```

Vantagens prontas: filtro `interesse_bizzu` reduz ruído; `dias_restantes` permite "faltam 3 dias"; banca/fases via Gemini personalizam a mensagem; PDFs no S3 dão link direto.
Desafios: pipeline ~15min (não tempo-real); custo Gemini (só novos/atualizados); LGPD/permissões na plataforma.

## Resumo executivo

| Aspecto | Status |
|---|---|
| Detecção de editais novos | ✅ pronto |
| Filtragem por interesse | ✅ pronto (`interesse_bizzu`) |
| Notificação WhatsApp | ❌ não existe (oportunidade) |
| Base de usuários | ❌ não existe (usar plataforma) |

## Arquivos-chave

`/CLAUDE.md` (fonte única) · `src/radar_editais/db/orm.py` (4 tabelas) · `pipeline.py` (5 fases) · `interesse.py` (regra Bizzu) · `ui/server.py` (FastAPI) · `auth.py` · `config.py` (PLATFORM_API_URL) · `docs/radar-editais.md` (contrato cross-repo)
