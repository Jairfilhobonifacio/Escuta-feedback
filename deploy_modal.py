"""Deploy da API FastAPI do Escuta no Modal (serverless ASGI).

═══════════════════════════════════════════════════════════════════════════════
COMO DEPLOYAR
═══════════════════════════════════════════════════════════════════════════════
    1) Crie ANTES o Modal Secret `escuta-prod` (uma única vez). Pode ser pela UI
       (modal.com → Secrets → Create) ou pela CLI:

           modal secret create escuta-prod \
               DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/postgres" \
               GROQ_API_KEY="gsk_..." \
               PANEL_API_KEY="<token-forte-do-painel>" \
               DEFAULT_ORG_SLUG="bizzu" \
               BIZZU_PARTNER_API_URL="https://api.bizzu.ai" \
               BIZZU_PARTNER_API_KEY="<x-api-key-bizzu>" \
               BIZZU_WEBHOOK_SECRET="<hmac-compartilhado>" \
               EMBEDDING_MODEL_NAME=""

       (NÃO commite valores; este arquivo só referencia o secret PELO NOME.)

    2) Deploy:

           modal deploy deploy_modal.py

       A URL pública sai no fim (algo como
       https://<workspace>--escuta-api-fastapi.modal.run). O `/health` e os
       `/api/*` ficam sob essa raiz.

═══════════════════════════════════════════════════════════════════════════════
CHAVES QUE O SECRET `escuta-prod` DEVE TER (lidas em app/config.py via os.getenv)
═══════════════════════════════════════════════════════════════════════════════
    DATABASE_URL          postgresql+asyncpg://...  (Supabase/Postgres async)
    GROQ_API_KEY          chave do LLM (Groq). Sem ela o fluxo cai no determinístico.
    PANEL_API_KEY         token do painel (X-Panel-Key). OBRIGATÓRIO em prod
                          (sem ele a auth do painel fica fail-OPEN = aberta).
    DEFAULT_ORG_SLUG      slug da org do piloto (ex.: "bizzu").
    BIZZU_PARTNER_API_URL base da API de Clientes da Bizzu (ex.: https://api.bizzu.ai).
    BIZZU_PARTNER_API_KEY X-API-Key da API de Clientes da Bizzu.
    BIZZU_WEBHOOK_SECRET  HMAC-SHA256 dos eventos da Bizzu (POST /api/events/bizzu).
    EMBEDDING_MODEL_NAME  deixe VAZIO ("") — embeddings/clustering/RAG não fazem
                          parte deste deploy (torch/sentence-transformers ficam de
                          fora da imagem; o import deles é lazy).

═══════════════════════════════════════════════════════════════════════════════
O QUE FICA DE FORA (e falha graciosamente)
═══════════════════════════════════════════════════════════════════════════════
    • WAHA (WhatsApp) NÃO é serverless — é stateful (sessão pareada por QR) e
      mora num host Docker/VPS, FORA do Modal. Os endpoints de WhatsApp
      (/api/whatsapp/*, envio outbound) só funcionam se WAHA_BASE_URL apontar
      para um WAHA acessível pela função. Sem isso eles FALHAM GRACIOSAMENTE
      (erro de conexão tratado), sem derrubar a API. O webhook inbound do WAHA
      também depende de o WAHA externo conseguir alcançar esta URL pública.
    • torch / sentence-transformers NÃO entram na imagem (requirements.txt é leve).
      Clustering semântico e RAG dependem deles (import lazy em
      app/services/embeddings.py) e estão FORA do escopo deste deploy inicial.
      Mantenha EMBEDDING_MODEL_NAME="".
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import modal

app = modal.App("escuta-api")

# Imagem: Debian slim + Python 3.12, deps do requirements.txt (leve: fastapi,
# uvicorn, sqlalchemy[asyncio], asyncpg, httpx, pydantic*, numpy, truststore...).
# `add_local_python_source("app")` torna o PACOTE local `app/` importável dentro
# do container. Por padrão ele NÃO copia para a imagem (copy=False) e entra como
# última camada (mount lazy), então editar o código NÃO invalida o cache das
# camadas de pip — e o default ignore=NON_PYTHON_FILES é o correto aqui, pois
# `app/` é Python puro (config vem de os.getenv, sem arquivos de dados embutidos).
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .add_local_python_source("app")
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("escuta-prod")],
    # 1 container quente evita cold start a cada request do painel/webhook.
    # Suba para max_containers maior se precisar de mais concorrência.
    min_containers=1,
    max_containers=2,
    timeout=300,
)
@modal.asgi_app()
def fastapi_app():
    # Import DENTRO da função: só roda no container (onde o secret `escuta-prod`
    # já populou o ambiente que app/config.py lê via os.getenv). app/main.py já
    # chama truststore.inject_into_ssl() no topo do módulo — mantido como está.
    from app.main import app as web_app

    return web_app
