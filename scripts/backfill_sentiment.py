"""Backfill de SENTIMENTO dos feedback_items que ainda não têm (sentiment nulo/vazio).

Recorte estreito e cirúrgico: ao contrário de `classify_feedbacks_batch.py` (que
enriquece sentiment + themes + urgency e elege quem está faltando QUALQUER um dos
dois), este script olha SÓ para `sentiment`. Seleciona os FeedbackItems com:

  - `text` não-vazio (não há o que classificar sem comentário livre), E
  - `sentiment` NULL **ou** string vazia/espaços.

Para cada um, reusa o MESMO cérebro do fluxo em tempo real —
`SurveyBrain.classify_feedback(text, score, "<source>:<type>")` — e grava só o
`sentiment`. Não cria cliente LLM novo, não toca survey_responses, não dispara
WhatsApp, não mexe em themes/urgency de quem já os tem (apenas anota `urgency` no
ai_meta se vier, sem sobrescrever o resto).

Idempotente: só processa quem tem `sentiment` ainda vazio. Re-rodar NÃO re-classifica
o que já recebeu sentiment. Best-effort: falha de UM item nunca derruba o lote.

Modos:
  (default)   DRY-RUN  -> conta os elegíveis + mostra até 10 exemplos do que
                          classificaria (id curto + source:type + score + prévia do
                          texto truncada). NÃO chama a Groq, NÃO grava.
  --apply               -> classifica via Groq em lotes (throttle) e faz UPDATE só
                          do sentiment (e urgency no ai_meta). Idempotente.
  --org <uuid>          -> restringe a uma organização (org-scoped). Sem isso, varre
                          todas as orgs do banco.
  --limit N             -> processa no máximo N itens (controle de custo/rate-limit).

Privacidade (LGPD): no DRY-RUN os exemplos mostram só uma PRÉVIA curta do texto
(até 80 chars) — necessária para o operador conferir o que seria classificado —
e nunca nome/e-mail/telefone. No --apply o stdout é só contagem/distribuição.

Envs (padrão dos scripts standalone _*.py):
  DATABASE_URL          — Supabase do Escuta (postgresql+asyncpg://...), via .env
  GROQ_API_KEY          — chave Groq (sem ela / LLM_ENABLED=0 = só dry-run funciona)
  GROQ_MODEL            — modelo principal (default llama-3.3-70b-versatile)
  GROQ_FALLBACK_MODEL   — modelo de reserva p/ 429 (default llama-3.1-8b-instant)

Uso:
    py scripts/backfill_sentiment.py                 # DRY-RUN (default)
    py scripts/backfill_sentiment.py --org <uuid>    # DRY-RUN de uma org
    py scripts/backfill_sentiment.py --apply --limit 40
    py scripts/backfill_sentiment.py --apply
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
import uuid

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

# Tamanho da prévia de texto exibida no DRY-RUN (operador confere SEM dump de PII).
_PREVIEW_CHARS = 80
_PREVIEW_EXAMPLES = 10


def _needs_sentiment(item) -> bool:
    """True se o item tem texto não-vazio E sentiment ainda vazio (NULL/''/espaços).

    Espelha o filtro SQL, mas é o critério canônico em Python — usado tanto para
    refinar a query (que não distingue ''/espaços por dialeto) quanto pelos testes.
    """
    if not (item.text or "").strip():
        return False
    return not (item.sentiment or "").strip()


def _build_query(org_id: uuid.UUID | None):
    """SELECT enxuto (load_only) dos candidatos a backfill de sentiment.

    load_only restringe às colunas que ESTE script lê/escreve — blinda contra skew
    model×banco (uma coluna nova no model antes da migration não quebra o SELECT) e
    evita arrastar embeddings/textões à toa. O SQL já pega NULL/''/espaços
    (func.trim == ''); o Python (`_needs_sentiment`) reaplica o mesmo critério como
    rede de segurança e como contrato único e testável.
    """
    from sqlalchemy import func, or_, select
    from sqlalchemy.orm import load_only

    from app.models.feedback import FeedbackItem

    q = (
        select(FeedbackItem)
        .options(
            load_only(
                FeedbackItem.id,
                FeedbackItem.source,
                FeedbackItem.type,
                FeedbackItem.score,
                FeedbackItem.text,
                FeedbackItem.sentiment,
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
                func.trim(FeedbackItem.sentiment) == "",
            ),
        )
        .order_by(FeedbackItem.organization_id, FeedbackItem.created_at)
    )
    if org_id is not None:
        q = q.where(FeedbackItem.organization_id == org_id)
    return q


async def select_eligible(session, org_id: uuid.UUID | None):
    """Carrega e refina (em Python) os FeedbackItems que precisam de sentiment."""
    candidates = (await session.execute(_build_query(org_id))).scalars().all()
    return [it for it in candidates if _needs_sentiment(it)]


def _short(value) -> str:
    s = str(value)
    return s[:8] if len(s) >= 8 else s


def _preview(text: str | None) -> str:
    t = " ".join((text or "").split())  # colapsa espaços/quebras
    return (t[:_PREVIEW_CHARS] + "…") if len(t) > _PREVIEW_CHARS else t


def _print_summary(eligible) -> None:
    by_kind: dict[str, int] = {}
    for it in eligible:
        k = f"{it.source}:{it.type}"
        by_kind[k] = by_kind.get(k, 0) + 1
    print(f"feedback_items SEM sentiment (com texto): {len(eligible)}")
    for kind, count in sorted(by_kind.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {kind:<28} {count:>5}")


async def backfill_sentiment(apply: bool, org_id: uuid.UUID | None, limit: int | None) -> int:
    # Registra TODOS os models no metadata antes de qualquer FK ser resolvida
    # (feedback_items referencia contacts/organizations/improvements/clusters).
    import app.models.core  # noqa: F401
    import app.models.feedback  # noqa: F401
    import app.models.survey  # noqa: F401
    from app.config import settings
    from app.db import SessionLocal

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada (Supabase do Escuta).", file=sys.stderr)
        return 1

    async with SessionLocal() as session:
        eligible = await select_eligible(session, org_id)
        _print_summary(eligible)

        if not apply:
            print(f"=== DRY-RUN (nada gravado, nenhuma chamada à IA) — até {_PREVIEW_EXAMPLES} exemplos ===")
            for it in eligible[:_PREVIEW_EXAMPLES]:
                score = it.score if it.score is not None else "-"
                print(
                    f"  [{_short(it.id)}] {it.source}:{it.type} score={score} :: {_preview(it.text)}"
                )
            if not eligible:
                print("  (nada a fazer — todo feedback com texto já tem sentiment)")
            print(
                "\nPara classificar de verdade:  py scripts/backfill_sentiment.py --apply"
            )
            return 0

        if not (settings.llm_enabled and settings.groq_api_key):
            print(
                "ERRO: LLM desabilitado (sem GROQ_API_KEY ou LLM_ENABLED=0). "
                "Sem IA não há como classificar o sentimento.",
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

        # Feature 2 (CORRECTION_LOOP_ENABLED): exemplos de correções humanas, 1× por org
        # (cache reusado entre itens). OFF (default) = sem exemplos (prompt como hoje).
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
                skipped += 1
            else:
                it.sentiment = tags.sentiment
                # Não sobrescreve themes (recorte é só sentiment). Anota urgency e
                # proveniência no ai_meta para auditoria/idempotência.
                it.ai_meta = {
                    **(it.ai_meta or {}),
                    "urgency": tags.urgency,
                    "sentiment_backfilled_by": "backfill_sentiment",
                    "model": settings.groq_model,
                }
                classified += 1
                sentiment_dist[tags.sentiment] = sentiment_dist.get(tags.sentiment, 0) + 1

            if idx < len(eligible) - 1:
                await asyncio.sleep(_THROTTLE_SECONDS)

        await session.commit()  # único commit, fora do loop

    print("=== Backfill de sentimento executado ===")
    print(f"  classificados: {classified}")
    print(f"  sem tags (LLM indisponível/cota/inválido): {skipped}")
    print(f"  falhas (exceção): {failed}")
    print("  --- sentimento resultante ---")
    for s, c in sorted(sentiment_dist.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {s:<10} {c:>5}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill do SENTIMENTO dos feedback_items sem classificação (dry-run por default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="classifica via Groq e grava o sentiment (default é dry-run)",
    )
    parser.add_argument(
        "--org",
        type=str,
        default=None,
        help="restringe a uma organização (UUID). Sem isso, varre todas as orgs.",
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
    org_id: uuid.UUID | None = None
    if args.org:
        try:
            org_id = uuid.UUID(args.org)
        except ValueError:
            parser.error(f"--org inválido (não é UUID): {args.org!r}")
    return asyncio.run(backfill_sentiment(args.apply, org_id, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
