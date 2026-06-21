---
name: escuta-deploy
description: Deploy guiado do Escuta (API no Modal + painel no Vercel) com a checklist do fail-closed — gerar segredos → secret → deploy → smoke. Use quando for subir mudanças para produção.
---

# Deploy do Escuta — passo a passo (fail-closed safe)

> ⚠️ **A API é fail-closed em produção** (`APP_ENV=production`): sem `PANEL_API_KEY`/`JWT_SECRET`/`WAHA_WEBHOOK_SECRET`/`ESCUTA_OPERATOR_*` no secret, o painel responde **503**. A **ORDEM** importa — segredos ANTES do deploy.
> 🔒 Segredos só por caminho (`~/.secrets/...`), nunca valor no chat. Deploy = ação de produção → **OK explícito do usuário** antes.

## 0. Pré-checagem
- Rode `/check` (pytest + tsc verdes).
- Confirme com o usuário o que está subindo.

## 1. Segredos (só caminho, nunca valor no chat)
- **JWT_SECRET** (≥32 bytes): `py -c "import secrets;print(secrets.token_urlsafe(48))" > ~/.secrets/escuta_jwt_secret.txt`
- **Senha do operador → hash bcrypt**: `py scripts/_gen_operator_hash.py` (digita a senha via getpass; salva o hash em `~/.secrets/escuta_operator_hash.txt`)
- No `.env`: `APP_ENV=production`, `ESCUTA_OPERATOR_USER=<login>`, `CORS_ALLOWED_ORIGINS=<domínio Vercel>`. Garanta que `~/.secrets/escuta_panel_key.txt` e `WAHA_WEBHOOK_SECRET` existem.

## 2. Modal Secret (ANTES do deploy)
```bash
cd ~/Documents/Projetos/escuta && py scripts/_deploy_modal_secret.py
```
Confirme que as chaves novas (`APP_ENV`/`JWT_SECRET`/`ESCUTA_OPERATOR_*`/`CORS_ALLOWED_ORIGINS`) entraram.

## 3. Deploy API (Modal)
```bash
cd ~/Documents/Projetos/escuta && export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 && py scripts/_modal_tls.py deploy deploy_modal.py
```
⚠️ Às vezes o 1º deploy **não troca o container** (serve defaults antigos) — validar `/api/config` no Modal **direto**; 2º deploy resolve.

## 4. Deploy painel (Vercel)
```bash
cd ~/Documents/Projetos/escuta/frontend && export NODE_OPTIONS=--use-system-ca && vercel deploy --prod --yes
```

## 5. Smoke pós-deploy
- `GET /health` = 200.
- Sem cookie de sessão → painel manda pro `/login`.
- Login com o operador → entra; `GET /api/auth/me` = 200.
- Requisição sem `X-Panel-Key`/`Bearer` em rota protegida → 401/503 (prova o fail-closed).

## Flags de IA (opcional — ligar UMA por vez: `.env` → re-secret → re-deploy)
`SENTIMENT_PT_V2_ENABLED` · `CORRECTION_LOOP_ENABLED` · `RESPONSE_SUGGESTION_ENABLED` (default OFF). Medir o piloto antes/depois de ligar (esp. o impacto do "incerto" no índice de prioridade).
