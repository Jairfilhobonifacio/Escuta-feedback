# Sessao handoff — 2026-06-27 — WhatsApp import + design skills

## Contexto

Sessao focada em retomar o projeto Escuta/Central de Feedbacks a partir do historico do Claude de hoje.

O que foi validado no historico:

- WAHA local subiu em `127.0.0.1:3000`.
- Sessao WAHA `default` reconectou como Jair `5524998365809`, status `WORKING`.
- WAHA retornou 490 chats: 396 individuais e 94 grupos.
- A feature desejada ficou clara: puxar historico de conversa do WhatsApp por cliente, com liberdade/confirmacao do operador antes de gravar.
- Antes desta sessao, isso ainda nao estava implementado no codigo.

## Implementado nesta sessao

### Backend WAHA

Arquivo: `app/services/waha.py`

- Adicionado `get_chats(session, limit)`.
- Adicionado `get_chat_messages(chat_id, session, limit, download_media)`.
- Ambos sao best-effort, so leem dados do WAHA e retornam lista vazia em erro.

### API de importacao de historico

Arquivo: `app/api/whatsapp.py`

- Adicionado payload `WhatsAppImportIn`.
- Adicionado endpoint:
  - `POST /api/contacts/{contact_id}/whatsapp/import`
- Fluxo:
  - `confirm=false`: preview, nao grava nada.
  - `confirm=true`: grava somente mensagens novas em `Message`.
- Busca o chat por telefone salvo no contato.
- Resolve chats `@lid` com `waha.resolve_lid`.
- Ignora grupos.
- Bloqueia se WAHA estiver desconectado.
- Deduplica por `channel_msg_id`.
- Mensagens sem id estavel do WAHA nao sao importadas, para evitar duplicacao futura.
- Importacao grava transcript, nao cria `FeedbackItem` automaticamente ainda.

### Frontend API

Arquivo: `frontend/lib/api.ts`

- Adicionados tipos:
  - `WhatsappImportPreviewMessage`
  - `WhatsappImportResult`
- Adicionados helpers:
  - `whatsapp.importPreview(contactId, limit)`
  - `whatsapp.importConfirm(contactId, limit)`

### Ficha 360 do contato

Arquivo: `frontend/app/contatos/[id]/page.tsx`

- Adicionado componente `ImportarConversaWhatsapp`.
- Fluxo visual:
  - botao `Verificar`
  - preview do chat encontrado
  - contadores de mensagens encontradas, novas e ja importadas
  - amostra da conversa
  - botao `Importar`, habilitado so quando ha mensagens novas
- `ConversaWhatsapp` ganhou `refreshKey`.
- `WhatsappSection` agora atualiza a conversa apos envio ou importacao.

### Design da importacao

Arquivo: `frontend/app/globals.css`

- Criado bloco visual `.wa-import-*`.
- Direcao aplicada: produto operacional, refinado e claro.
- A secao ficou separada do envio de WhatsApp e mais escaneavel para operador:
  - cabecalho com intencao
  - acoes com hierarquia
  - status `conversa encontrada` / `nada encontrado`
  - contadores visuais
  - bolhas de amostra do transcript
  - responsivo em mobile

## Skills de design

Foram instaladas e testadas:

- `taste-skill` em `C:\Users\jboni\.codex\skills\taste-skill`
- `impeccable` em `C:\Users\jboni\.codex\skills\impeccable`

Depois do restart, as duas carregaram.

O `taste-skill` foi tratado como filtro anti-design generico, mas ele mesmo diz que nao e ideal para dashboards/painel denso.

O `impeccable` passou a ser a skill principal para UI de produto.

### Setup do Impeccable

Criado:

- `PRODUCT.md`
- `.impeccable/live/config.json`

`PRODUCT.md` define o Escuta como `product` e fixa:

- usuarios: donos, gestores, CS/produto de SaaS PME, piloto Bizzu
- proposito: transformar conversa de WhatsApp em decisao acionavel
- personalidade: calmo, direto, cuidadoso
- anti-referencias: dashboard de IA generico, helpdesk lotado, planilha, dark neon, grafico colorido demais
- principio central: "bate o olho e entende"

O contexto do `impeccable` passou a reconhecer o projeto corretamente.

## Validacao executada

Comandos rodados e aprovados:

- `python -m pytest tests/test_whatsapp_api.py -q`
  - resultado: 13 passed
- `python -m pytest tests/test_whatsapp_api.py tests/test_webhook_capture.py tests/test_webhook_phone_match.py -q`
  - resultado: 20 passed
- `python -m py_compile app/services/waha.py app/api/whatsapp.py tests/test_whatsapp_api.py`
  - resultado: ok
- `npx tsc --noEmit` em `frontend`
  - resultado: ok

## Arquivos modificados/criados por esta sessao

Modificados:

- `app/api/whatsapp.py`
- `app/services/waha.py`
- `frontend/app/contatos/[id]/page.tsx`
- `frontend/app/globals.css`
- `frontend/lib/api.ts`
- `tests/test_whatsapp_api.py`

Criados:

- `PRODUCT.md`
- `.impeccable/live/config.json`
- `docs/SESSAO_HANDOFF_2026-06-27_WHATSAPP_IMPORT_DESIGN.md`

Ja existiam untracked antes e nao foram mexidos/revertidos:

- `_gen_monitorar_refinada.py`
- `_gen_qa_composicao.py`
- `docs/FEEDBACK_DONO_2026-06-20.md`
- `docs/PLANO_TERMINAR_E_SIMPLIFICAR_2026-06-19.md`
- `docs/feedback-2026-06-20/`
- `scripts/_diag_churn_whatsapp.py`
- `scripts/_modal_tls.py`
- `scripts/_smoke_sentiment_v2.py`
- `scripts/_smoke_voc_groq.py`

## Onde continuar

Proximo passo recomendado:

1. Gerar um `DESIGN.md` oficial a partir de:
   - `docs/MANUAL_MARCA_ESCUTA.md`
   - `frontend/app/globals.css`
   - `frontend/app/layout.tsx`
   - componentes atuais da ficha 360
2. Testar a feature pela UI com WAHA real, usando primeiro apenas preview.
3. Se o preview bater com o cliente certo, testar `Importar` em ambiente seguro.
4. Depois decidir se historico importado deve gerar `FeedbackItem` automaticamente ou continuar como transcript manual.

Observacao importante:

- `confirm=true` grava no banco configurado no `.env`. Em teste real, usar preview primeiro para nao gravar acidentalmente em producao/piloto.
