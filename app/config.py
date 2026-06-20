"""Configuração (stdlib-only, sem pydantic para manter db.py importável enxuto).

Lê de variáveis de ambiente. Em produção, vêm de Secrets do Modal; em dev, de .env
carregado pelo runner.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # postgresql+asyncpg://user:pass@host:5432/db  (Supabase)
    database_url: str = os.getenv("DATABASE_URL", "")
    # Gateway WAHA
    waha_base_url: str = os.getenv("WAHA_BASE_URL", "http://localhost:3000")
    waha_api_key: str | None = os.getenv("WAHA_API_KEY")
    waha_session: str = os.getenv("WAHA_SESSION", "default")
    # Org do piloto
    default_org_slug: str = os.getenv("DEFAULT_ORG_SLUG", "bizzu")
    # Segredo compartilhado p/ eventos da Bizzu (HMAC-SHA256). Sem ele o endpoint
    # /api/events/bizzu responde 503 (integração desligada).
    bizzu_webhook_secret: str | None = os.getenv("BIZZU_WEBHOOK_SECRET")
    # Token da API pública de integração (GET /api/integration/*). Sistemas externos
    # mandam no header X-API-Key. Sem a env, a API de integração fica DESLIGADA (503).
    integration_api_key: str | None = os.getenv("INTEGRATION_API_KEY")
    # Auth do PAINEL interno (admin/whatsapp/campanha/boards/tasks/playbooks/clusters/
    # digest). Sistemas/painel mandam no header X-Panel-Key. Fail-OPEN quando ausente
    # (libera + WARN, p/ não quebrar o piloto e a suíte de testes); fail-CLOSED quando
    # configurada (header obrigatório, 401 sem/errado). ⚠️ OBRIGATÓRIO em produção.
    panel_api_key: str | None = os.getenv("PANEL_API_KEY")
    # Segredo de ORIGEM do webhook do WAHA (POST /api/webhook/waha), header
    # X-Webhook-Secret. Fail-OPEN quando ausente (aceita + WARN, p/ não quebrar o
    # piloto ainda não configurado); fail-CLOSED quando configurado (header obrigatório,
    # 401 sem/errado) — impede mensagens forjadas. ⚠️ OBRIGATÓRIO em produção.
    waha_webhook_secret: str | None = os.getenv("WAHA_WEBHOOK_SECRET")
    # LLM (Groq) — cérebro do fluxo de survey (interpretação de respostas livres,
    # opt-out, perguntas) + classificação de feedback. Sem chave = desligado e o
    # fluxo determinístico segue intacto. LLM_ENABLED=0 força OFF mesmo com chave.
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    # Modelo de reserva: quando o principal estoura a cota diária (429), o agente
    # continua neste (cota separada, mais folgada) em vez de cair na máquina de
    # estados. GROQ_FALLBACK_MODEL="" desliga a cascata.
    groq_fallback_model: str = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
    # Transcrição de áudio inbound (WhatsApp) via Groq Whisper. Usa a GROQ_API_KEY;
    # sem chave, áudio não é transcrito (o bot só acolhe e avisa que vai ouvir).
    groq_whisper_model: str = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
    llm_enabled: bool = (
        os.getenv("LLM_ENABLED", "1") == "1" and bool(os.getenv("GROQ_API_KEY"))
    )
    # Modo de teste: aceita mensagens do "chat consigo mesmo" (ver webhook.py).
    # NUNCA ligar em produção — existe só para o E2E com um único número.
    self_chat_test: bool = os.getenv("SELF_CHAT_TEST", "0") == "1"
    # Survey Agent: o miolo conversacional que conduz a pesquisa como um agente
    # (lê a conversa inteira + estado e decide cada turno) no lugar da máquina de
    # estados. Atrás de flag para rollback instantâneo; OFF = fluxo determinístico
    # atual + remendos. Cai no determinístico também se o LLM falhar num turno.
    survey_agent_enabled: bool = os.getenv("SURVEY_AGENT_ENABLED", "0") == "1"
    # Hand-off → abrir ticket no Atendimentos da Bizzu (best-effort, opcional).
    # Requer o patch docs/patches/bizzu-backend-support-ticket-endpoint.patch no backend.
    bizzu_support_ticket_url: str | None = os.getenv("BIZZU_SUPPORT_TICKET_URL")
    bizzu_support_api_key: str | None = os.getenv("BIZZU_SUPPORT_API_KEY")
    # Link de agendamento de call (Calendly/Google) — entra na oferta de call e no
    # hand-off. Sem a env, as mensagens não incluem link (comportamento atual).
    bizzu_call_url: str | None = os.getenv("BIZZU_CALL_URL")
    # Cooldown de outbound proativo (em horas): janela mínima entre mensagens NÃO
    # solicitadas para o MESMO contato (ex.: aviso "você pediu, a gente fez" do
    # /improvements/{id}/notify). Evita spammar quem acabou de receber algo. Conta
    # só mensagens 'outbound' recentes na tabela `messages`. 0 = desliga o cooldown.
    notify_cooldown_hours: int = int(os.getenv("NOTIFY_COOLDOWN_HOURS", "20"))
    # Fase 2 (Playbooks): plugues INLINE do motor nos pontos de evento (resolver de
    # survey + endpoint de eventos). OFF (default) = o motor SÓ roda via
    # POST /api/playbooks/run; o comportamento dos webhooks é idêntico ao atual.
    # Os plugues são best-effort (try/except que engole) — nunca derrubam o webhook.
    playbooks_inline_enabled: bool = os.getenv("PLAYBOOKS_INLINE_ENABLED", "0") == "1"
    # Camada 1 (Clustering de Dores): geração INLINE do embedding no write-path de
    # feedback (após o commit do create_feedback), via asyncio.create_task
    # fire-and-forget numa sessão nova. OFF (default) = só o POST /api/feedbacks/reindex
    # (lote, manual/cron) gera embeddings. O plugue é best-effort (engole erro) e
    # NUNCA bloqueia/derruba a resposta do endpoint.
    clustering_inline_enabled: bool = os.getenv("CLUSTERING_INLINE_ENABLED", "0") == "1"
    # RAG honesto (NO_KB_FALLBACK): quando o retrieval não traz contexto relevante
    # (KB vazio OU melhor score abaixo do piso), o brain responde de forma HONESTA
    # ("vou encaminhar ao time") em vez de deixar o LLM inventar um fato. LIGADO por
    # default. NO_KB_FALLBACK_ENABLED=0 desliga o caminho honesto explícito (volta a
    # devolver None e deixa quem chama decidir o genérico).
    no_kb_fallback_enabled: bool = os.getenv("NO_KB_FALLBACK_ENABLED", "1") == "1"
    # Fase D (Esteira cruzada): automações cruzadas do board — mover um card dispara as
    # ações conectadas (concluir tarefa resolve o feedback; melhoria entregue resolve os
    # feedbacks vinculados). Atrás de UMA flag para reversibilidade instantânea.
    # ESTEIRA_ENABLED=0 desliga TODAS as automações cruzadas (default LIGADO). Cada plugue
    # é best-effort e idempotente — nunca derruba o PATCH que o disparou.
    esteira_enabled: bool = os.getenv("ESTEIRA_ENABLED", "1") == "1"
    # Modelo de embedding (retrieval/clustering). VAZIO ("") = mantém EXATAMENTE o
    # modelo atual (all-MiniLM-L6-v2, 384-dim) — zero regressão. Para PT, setar
    # EMBEDDING_MODEL_NAME="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # (também 384-dim → NÃO exige migration da coluna vector(384)); exige o modelo no
    # cache HF (HF_HUB_OFFLINE=1) + re-gerar os vetores (reindex). Troca = passo manual.
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "")
    # RAG híbrido: combina busca semântica (pgvector) + lexical (ILIKE) no retriever.
    # OFF (default) = comportamento atual idêntico (só semântica). Quando ON, une e
    # reordena os dois conjuntos — melhora recall em PT enquanto o embedding é inglês.
    rag_hybrid_enabled: bool = os.getenv("RAG_HYBRID_ENABLED", "0") == "1"
    # Fase 2 (Agente VoC): substitui a máquina de estados/determinístico pelo agente
    # com function-calling (chat_with_tools + VoCToolRegistry + orchestrator). OFF
    # (default) = fluxo atual BYTE-A-BYTE; liga só para validar com Groq real.
    voc_agent_enabled: bool = os.getenv("VOC_AGENT_ENABLED", "0") == "1"
    # Tool de envio de WhatsApp DENTRO do Agente VoC. OFF (default) = a tool é NO-OP
    # (não envia nada). Mesmo ON, passa por 3 gates (opt-in, cooldown, alcançável).
    # WhatsApp real só com OK explícito do dono — manter OFF até lá.
    voc_whatsapp_tool_enabled: bool = os.getenv("VOC_WHATSAPP_TOOL_ENABLED", "0") == "1"
    # Índice de Prioridade das DORES (Mapeamento): pesos do índice
    # volume×receita×gravidade calculado na leitura de /api/feedbacks/clusters (ver
    # app/domain/prioridade.py). TRANSPARENTES: vão no payload (priority_breakdown.weights)
    # para a UI explicar a prioridade, e ajustáveis por env sem tocar código. Os defaults
    # (0.50/0.30/0.20, somando 1.0) seguem a SPEC §2.3.
    priority_weight_volume: float = float(os.getenv("PRIORITY_WEIGHT_VOLUME", "0.50"))
    priority_weight_revenue: float = float(os.getenv("PRIORITY_WEIGHT_REVENUE", "0.30"))
    priority_weight_gravity: float = float(os.getenv("PRIORITY_WEIGHT_GRAVITY", "0.20"))
    # Volume (clientes distintos) que satura o volume_score em 1.0.
    priority_volume_ref: int = int(os.getenv("PRIORITY_VOLUME_REF", "10"))
    # Multiplicador de receita do pagante de plano ALTO (anual) vs. mensal (1.0).
    priority_plano_alto_mult: float = float(os.getenv("PRIORITY_PLANO_ALTO_MULT", "1.5"))


settings = Settings()
