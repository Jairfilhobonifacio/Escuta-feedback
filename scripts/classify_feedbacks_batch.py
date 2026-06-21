"""Classificação em LOTE dos feedback_items por IA (sentimento + temas + urgência).

A tela "Temas" e o score de urgência só ficam ricos quando os FeedbackItems têm
`sentiment` e `themes`. O sync da API de Clientes (sync_partner_customers.py) ingere
os sinais NPS/churn com `classify=False` (233 clientes não viram 233 chamadas LLM),
deixando a classificação para depois — este script é o "depois".

Varre `feedback_items` que TÊM texto livre e ainda NÃO foram classificados
(sentiment nulo OU themes nulo/vazio), e para cada um chama o MESMO cérebro do
fluxo em tempo real — `SurveyBrain.classify_feedback(...)` — gravando `sentiment`,
`themes` e a `urgency` em `ai_meta`, além de uma marca de proveniência
(`ai_meta["classified_by"]="ai_batch"` + modelo) para auditoria/idempotência.

Idempotente: só processa quem tem `text` não-vazio E (sentiment nulo OU themes
nulo/vazio). Re-rodar NÃO re-classifica o que já tem tags. NÃO dispara WhatsApp.
NÃO toca survey_responses nem o resolver — só enriquece a central.

  --dry-run   -> SÓ conta quantos seriam classificados (NÃO chama IA, NÃO grava).
  --limit N   -> processa no máximo N itens (controle de custo/rate-limit).

Resiliência: usa o fallback_model do settings (cota separada) — o GroqLLM já tenta
o reserva uma vez em 429/timeout. Throttle leve entre chamadas para não estourar a
cota da Groq. Falha de classificação de UM item nunca derruba o lote (best-effort).

Privacidade (LGPD): o stdout nunca imprime texto de feedback, nome, e-mail ou
telefone — apenas contagens e a distribuição resultante de sentiment/temas.

Envs:
  DATABASE_URL          — Supabase do Escuta (postgresql+asyncpg://...), via .env
  GROQ_API_KEY          — chave Groq (sem ela / LLM_ENABLED=0 = nada a fazer)
  GROQ_MODEL            — modelo principal (default llama-3.3-70b-versatile)
  GROQ_FALLBACK_MODEL   — modelo de reserva p/ 429 (default llama-3.1-8b-instant)

Uso:
    py scripts/classify_feedbacks_batch.py --dry-run
    py scripts/classify_feedbacks_batch.py --limit 40
    py scripts/classify_feedbacks_batch.py
"""
from __future__ import annotations

# Fix TLS ANTES de qualquer import que abra conexão TLS (asyncpg ao Supabase +
# HTTPS à Groq). Global por processo — espelha app/main.py e os outros standalone.
import truststore

truststore.inject_into_ssl()

import argparse
import asyncio
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:
    pass

# Throttle leve entre chamadas à Groq (segundos). Pequeno o bastante para um lote
# de dezenas terminar rápido, grande o bastante para não martelar o rate-limit.
_THROTTLE_SECONDS = 0.6


async def classify_batch(dry_run: bool, limit: int | None) -> int:
    from sqlalchemy import or_, select
    from sqlalchemy.orm import load_only

    # Registra TODOS os models no metadata antes de qualquer FK ser resolvida
    # (feedback_items referencia contacts/organizations).
    import app.models.core  # noqa: F401
    import app.models.feedback  # noqa: F401
    import app.models.survey  # noqa: F401
    import app.models.improvement  # noqa: F401  (FK feedback_items.improvement_id)
    import app.models.cluster  # noqa: F401  (FK feedback_items.cluster_id)
    import app.models.playbook  # noqa: F401
    from app.config import settings
    from app.db import SessionLocal
    from app.models.feedback import FeedbackItem

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada (Supabase do Escuta).", file=sys.stderr)
        return 1

    # Elegível: tem texto não-vazio E ainda não classificado (sentiment nulo OU
    # themes nulo/vazio). O filtro de "themes vazio" ([]) fica em Python — varia
    # por dialeto no SQL; o volume é pequeno e a query já corta o grosso.
    #
    # load_only restringe o SELECT às colunas que ESTE script lê/escreve. Além de
    # enxuto, blinda contra skew model×banco: se outro agente adicionar uma coluna
    # ao model ANTES da migration rodar (ex.: improvement_id), o SELECT completo
    # quebraria ("column does not exist") — load_only não a referencia.
    eligible_q = (
        select(FeedbackItem)
        .options(
            load_only(
                FeedbackItem.id,
                FeedbackItem.source,
                FeedbackItem.type,
                FeedbackItem.score,
                FeedbackItem.text,
                FeedbackItem.sentiment,
                FeedbackItem.themes,
                FeedbackItem.ai_meta,
                FeedbackItem.organization_id,
                FeedbackItem.created_at,
            )
        )
        .where(
            FeedbackItem.text.is_not(None),
            FeedbackItem.text != "",
            or_(
                FeedbackItem.sentiment.is_(None),
                FeedbackItem.themes.is_(None),
            ),
        )
        .order_by(FeedbackItem.organization_id, FeedbackItem.created_at)
    )

    async with SessionLocal() as session:
        candidates = (await session.execute(eligible_q)).scalars().all()
        # Refina em Python: themes == [] também conta como "não classificado".
        eligible = [
            it
            for it in candidates
            if (it.text or "").strip() and (it.sentiment is None or not (it.themes or []))
        ]

        # Distribuição por (source, type) — só números, sem PII.
        by_kind: dict[str, int] = {}
        for it in eligible:
            k = f"{it.source}:{it.type}"
            by_kind[k] = by_kind.get(k, 0) + 1

        print(f"feedback_items elegíveis (com texto e não classificados): {len(eligible)}")
        for kind, count in sorted(by_kind.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  {kind:<28} {count:>5}")

        if dry_run:
            print("=== DRY-RUN (nada gravado, nenhuma chamada à IA) ===")
            return 0

        if not (settings.llm_enabled and settings.groq_api_key):
            print(
                "ERRO: LLM desabilitado (sem GROQ_API_KEY ou LLM_ENABLED=0). "
                "Sem IA não há o que classificar.",
                file=sys.stderr,
            )
            return 1

        if limit is not None:
            eligible = eligible[:limit]
            print(f"--limit aplicado: processando no máximo {limit} item(ns).")

        from app.domain.survey.brain import SurveyBrain
        from app.services.llm import GroqLLM

        # Mesmo cérebro do tempo-real; passa o fallback_model p/ a cascata de 429.
        brain = SurveyBrain(
            GroqLLM(
                settings.groq_api_key,
                settings.groq_model,
                fallback_model=settings.groq_fallback_model or None,
            )
        )

        classified = skipped = failed = 0
        sentiment_dist: dict[str, int] = {"positivo": 0, "neutro": 0, "negativo": 0}
        urgency_dist: dict[str, int] = {"baixa": 0, "media": 0, "alta": 0}
        theme_counter: dict[str, int] = {}

        # Feature 2 (CORRECTION_LOOP_ENABLED): carrega 1× por org os exemplos de
        # correções humanas e reusa entre os itens (custo amortizado). OFF = sem exemplos.
        from app.domain.feedback.correction_loop import collect_correction_examples

        examples_cache: dict = {}

        async def _examples_for(org_id) -> list | None:
            if not settings.correction_loop_enabled:
                return None
            if org_id not in examples_cache:
                examples_cache[org_id] = await collect_correction_examples(session, org_id)
            return examples_cache[org_id]

        for idx, it in enumerate(eligible):
            text = (it.text or "").strip()
            if not text:
                skipped += 1
                continue
            try:
                tags = await brain.classify_feedback(
                    text, it.score, f"{it.source}:{it.type}",
                    examples=await _examples_for(it.organization_id),
                )
            except Exception:  # noqa: BLE001 — IA é enriquecedor, nunca derruba o lote.
                failed += 1
                tags = None

            if tags is None:
                # LLM indisponível/resposta inválida/cota: best-effort, segue.
                if failed == 0:  # só conta como skip quando não foi exceção contada acima
                    skipped += 1
            else:
                it.sentiment = tags.sentiment
                it.themes = tags.themes
                it.ai_meta = {
                    **(it.ai_meta or {}),
                    "urgency": tags.urgency,
                    "classified_by": "ai_batch",
                    "model": settings.groq_model,
                }
                classified += 1
                sentiment_dist[tags.sentiment] = sentiment_dist.get(tags.sentiment, 0) + 1
                urgency_dist[tags.urgency] = urgency_dist.get(tags.urgency, 0) + 1
                for t in tags.themes:
                    theme_counter[t] = theme_counter.get(t, 0) + 1

            # Throttle leve entre chamadas (não no último).
            if idx < len(eligible) - 1:
                await asyncio.sleep(_THROTTLE_SECONDS)

        await session.commit()  # único commit, fora do loop

    # --- Resumo (sem PII) ---
    print("=== Classificação em lote executada ===")
    print(f"  classificados: {classified}")
    print(f"  sem tags (LLM indisponível/cota/inválido): {skipped}")
    print(f"  falhas (exceção): {failed}")
    print("  --- sentimento resultante ---")
    for s, c in sorted(sentiment_dist.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {s:<10} {c:>5}")
    print("  --- urgência resultante ---")
    for u, c in sorted(urgency_dist.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {u:<10} {c:>5}")
    print("  --- top temas resultantes ---")
    for t, c in sorted(theme_counter.items(), key=lambda kv: kv[1], reverse=True)[:15]:
        print(f"    {t:<28} {c:>5}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classifica em lote os feedback_items por IA (sentimento + temas + urgência)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="só conta quantos seriam classificados (sem IA, sem gravar, sem PII)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="processa no máximo N itens (controle de custo/rate-limit)",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit deve ser um inteiro positivo")
    return asyncio.run(classify_batch(args.dry_run, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
