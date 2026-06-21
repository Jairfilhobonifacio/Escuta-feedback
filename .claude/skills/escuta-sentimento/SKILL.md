---
name: escuta-sentimento
description: Re-roda a classificação de sentimento dos feedbacks do Escuta (feedbacks novos chegam sem sentiment). Use periodicamente para o índice de prioridade e o Mapeamento ficarem reais.
---

# /escuta-sentimento — reclassificar feedbacks

> Feedbacks ingeridos pelo sync (`classify=False`) chegam **sem sentiment** → o índice de prioridade fica "média" em quase tudo (gravidade = 0). Este batch preenche e faz o Mapeamento diferenciar.

## 1. Dry-run primeiro (NÃO escreve)
```bash
cd ~/Documents/Projetos/escuta && export PYTHONUTF8=1 HF_HUB_OFFLINE=1 && set -a && source .env && set +a && py scripts/classify_feedbacks_batch.py --dry-run
```
Mostra quantos seriam classificados, sem tocar o banco.

## 2. Aplicar (ESCREVE no piloto → precisa de OK explícito do usuário)
```bash
cd ~/Documents/Projetos/escuta && export PYTHONUTF8=1 HF_HUB_OFFLINE=1 && set -a && source .env && set +a && py scripts/classify_feedbacks_batch.py
```
- Idempotente (só pega os sem sentiment); throttle ~0,6s/item; best-effort (erro em 1 item não derruba o lote).
- Custo Groq: ~meio centavo por dezenas de itens.
- Se `SENTIMENT_PT_V2_ENABLED=1`, usa o prompt v2 (ironia/negação/gíria + "neutro") e, em baixa confiança, **marca "incerto" em vez de chutar** (não preenche `sentiment`, guarda o palpite em `ai_meta.sentiment_sugerido`).
- Se `CORRECTION_LOOP_ENABLED=1`, usa suas edições manuais como exemplos de calibração.

## 3. Depois
- Conferir o **Mapeamento** (`/temas`): dores com mais negativos devem subir para **ALTA** (o índice é runtime — reflete sem re-deploy).
- ⚠️ Escrita no piloto é **barrada pelo classificador** sem OK pontual — o usuário autoriza ("permissão total") ou roda via `!`.
- Futuro: virar cron (hoje é manual a cada leva nova de feedbacks).
