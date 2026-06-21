---
description: Verificação rápida do Escuta — pytest (backend, SQLite in-memory) + tsc (frontend). Não toca o piloto.
---

# /check — verificação rápida do Escuta

Rode as duas suítes e relate a contagem. A suíte usa SQLite in-memory (`tests/conftest.py`) — **não escreve no piloto**, então rodar é seguro.

**Backend (pytest):**
```bash
cd ~/Documents/Projetos/escuta && export PYTHONUTF8=1 HF_HUB_OFFLINE=1 && set -a && source .env && set +a && py -m pytest tests/ -q
```

**Frontend (typecheck):**
```bash
cd ~/Documents/Projetos/escuta/frontend && npx tsc --noEmit
```

Relate: pytest passou/falhou (contagem exata; quais falharam, se houver) e tsc (0 erros?). Se algo não rodar por ambiente, explique o porquê. **Só diagnostique — não conserte nada sem o usuário pedir.**
