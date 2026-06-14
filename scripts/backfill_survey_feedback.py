"""Backfill: respostas de pesquisa (survey_responses) -> inbox da mega central.

As respostas REAIS das pesquisas no WhatsApp vivem em `survey_responses`, mas o
inbox de monitoramento (`feedback_items`) só tinha o snapshot da API de Clientes
(NPS in-app / churn). Este script varre as respostas JÁ respondidas/fechadas
(têm `answer_score` OU `answer_text`) e cria um FeedbackItem para cada — para que
apareçam no inbox ao lado dos demais sinais.

Idempotente por external_id='survey_response:<id>' (rodar de novo NÃO duplica:
atualiza o mesmo FeedbackItem). Reusa a MESMA ponte do resolver
(app/domain/feedback/from_survey.py), então backfill e tempo-real ficam idênticos.

NÃO chama LLM: copia o enriquecimento que o resolver já gravou na resposta
(sentiment/themes/urgency). NÃO dispara WhatsApp. NÃO toca survey_responses.

  --dry-run  -> SÓ conta quantas respostas elegíveis existem (sem tocar o banco,
                sem PII — apenas números).

Privacidade (LGPD): o stdout nunca imprime texto de resposta, nome, e-mail ou
telefone — apenas contagens e ids opacos.

Envs:
  DATABASE_URL — Supabase do Escuta (postgresql+asyncpg://...), via .env

Uso:
    py scripts/backfill_survey_feedback.py --dry-run
    py scripts/backfill_survey_feedback.py
"""
from __future__ import annotations

# Fix TLS ANTES de qualquer import que abra conexão TLS (asyncpg ao Supabase).
# Global por processo — espelha app/main.py e os outros scripts standalone.
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


async def backfill(dry_run: bool) -> int:
    from sqlalchemy import or_, select

    # Registra TODOS os models no metadata antes de qualquer FK ser resolvida
    # (feedback_items referencia contacts; sem core o asyncpg quebra a FK).
    import app.models.core  # noqa: F401
    import app.models.feedback  # noqa: F401
    import app.models.survey  # noqa: F401
    from app.db import SessionLocal
    from app.domain.feedback.from_survey import feedback_from_survey_response
    from app.models.survey import SurveyResponse

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada (Supabase do Escuta).", file=sys.stderr)
        return 1

    # Elegível: já respondida (nota) OU já tem texto. Cobre 'closed' e respostas
    # parciais (nota dada, motivo pendente) — ambas são sinais reais do cliente.
    eligible = (
        select(SurveyResponse)
        .where(
            or_(
                SurveyResponse.answer_score.is_not(None),
                SurveyResponse.answer_text.is_not(None),
            )
        )
        .order_by(SurveyResponse.organization_id, SurveyResponse.id)
    )

    async with SessionLocal() as session:
        responses = (await session.execute(eligible)).scalars().all()
        total = len(responses)
        # Distribuição por org (só números — sem PII).
        by_org: dict[str, int] = {}
        for r in responses:
            by_org[str(r.organization_id)] = by_org.get(str(r.organization_id), 0) + 1

        print(f"survey_responses elegíveis (com nota e/ou texto): {total}")
        for org_id, count in sorted(by_org.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  org {org_id}: {count}")

        if dry_run:
            print("=== DRY-RUN (nada gravado, sem tocar o banco) ===")
            return 0

        created = updated = 0
        for r in responses:
            item = await feedback_from_survey_response(session, r)
            # created_at == updated nunca; usamos o pré-flush: se o id já existia,
            # o ingestor atualizou. Distinguir create/update exige checar antes —
            # simplificamos contando "processados"; o total no banco é a verdade.
            if item is not None:
                created += 1  # "processados" (idempotente: re-run vira update)

        await session.commit()

        # Confirmação: total de FeedbackItems source='whatsapp' (a central nova).
        from app.models.feedback import FeedbackItem

        wa_total = (
            await session.execute(
                select(FeedbackItem.id).where(FeedbackItem.source == "whatsapp")
            )
        ).scalars().all()

        print(
            f"=== Backfill executado: {created} resposta(s) espelhada(s); "
            f"feedback_items source='whatsapp' agora: {len(wa_total)} ==="
        )
        # `updated` fica 0 por design (não diferenciamos); ruído removido.
        _ = updated
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill de survey_responses -> feedback_items (inbox da mega central)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="só conta as respostas elegíveis (sem tocar o banco, sem PII)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(backfill(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
