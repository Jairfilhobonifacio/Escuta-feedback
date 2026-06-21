---
name: escuta-security-review
description: Review de segurança do Escuta (FastAPI + Next.js BFF + Supabase + Groq). Checa auth fail-closed, cookie JWT httpOnly, org-scoping multi-tenant, prompt-injection da IA, segredos e PII. Use antes de commitar/deployar mudança sensível.
---

# Review de segurança do Escuta

## Escopo
Reveja o código sensível do Escuta. Padrão: `git -C ~/Documents/Projetos/escuta diff --name-only` (ou arquivos indicados). **Read-only** — só aponta achados (severidade + arquivo:linha + fix); não conserta sem o usuário pedir.

## Checklist (o que olhar)

**1. Autenticação / autorização**
- `require_panel_key` e `require_waha_webhook_secret` são **fail-CLOSED em produção** (`app_env=="production"` + segredo ausente → 503, nunca libera). Fail-open só em dev.
- Rotas do painel herdam `_panel = [require_panel_key, require_operator]` (`app/main.py`). Webhooks (HMAC próprio), `/health` e `/api/auth/login` ficam fora do `require_operator` de propósito — confirmar que nada sensível ficou sem `require_operator`.
- JWT: HS256, `JWT_SECRET` só no backend; cookie `escuta_session` é **httpOnly+Secure(prod)+SameSite=Lax**; o token nunca é exposto ao JS. O BFF (`frontend/app/api/[...path]/route.ts`) bloqueia (401) requisição sem sessão antes de chamar o backend.

**2. Multi-tenant / org-scoping**
- Toda query filtra por `organization_id`. ⚠️ Hoje a org vem de `settings.default_org_slug` (global), não do JWT do operador — OK no piloto single-tenant, mas **antes de multi-tenant** é preciso vincular operador→org (claim no JWT).

**3. Prompt-injection (features de IA)**
- Texto do cliente/feedback e nota do operador entram como **DADO delimitado** (`<<< >>>` neutralizado via `_neutralize_delims`), nunca no `system`. Few-shot do loop de correção é **JSON serializado** (não forja separador). System proíbe seguir instruções embutidas. Saída é só sugestão (endpoint read-only, não envia/age).

**4. Segredos / PII / TLS**
- Zero segredo hardcoded; tudo env. Valores só em `~/.secrets/...`, nunca em arquivo versionado nem no chat.
- PII (telefone) mascarada nos logs (`_mask_phone`); listas mascaram, ficha 1:1 mostra completo.
- TLS via `truststore.inject_into_ssl()` — **nunca desabilitar**.

**5. Input / vazamento**
- Erros para emissor externo são genéricos (não vazam `e.errors()`/stack).
- LIKE escapa `_`/`%`/`\` (`_escape_like`) na busca.

## Saída
Liste achados com **severidade** (crítico/alto/médio/baixo), **arquivo:linha** e **fix concreto**. Veredito: aprovado / aprovado com ressalvas / reprovado. Para um review mais fundo, eu posso disparar a skill `security-pro:security-auditor` em paralelo.
