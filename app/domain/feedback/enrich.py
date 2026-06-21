"""Aplicação das tags de IA num objeto de feedback — regra do "não chutar".

Compartilhado pelos 3 write-paths que classificam (ingest, resolver de survey,
auto-classify manual). Função PURA sobre o objeto (não toca a sessão/DB): recebe
um alvo com `.sentiment`/`.themes`/`.ai_meta` (vale p/ FeedbackItem E SurveyResponse,
duck-typing) e aplica `FeedbackTags`.

Regra do incerto (Feature 1, SENTIMENT_PT_V2_ENABLED):
- confiança baixa (`tags.incerto`) E flag v2 ON ⇒ NÃO grava `sentiment` (deixa como
  está / None → "sem classificação", que a UI já trata) e guarda o palpite em
  `ai_meta["sentiment_sugerido"]`. Não chutamos uma classe quando a IA não tem certeza.
- confiança alta/média (ou flag OFF) ⇒ grava `sentiment` normalmente, como hoje.
Em qualquer caso, `themes` é gravado e `ai_meta` registra urgency/confianca/incerto/modelo.
"""
from __future__ import annotations

from typing import Any

from app.domain.survey.brain import FeedbackTags, _sentiment_pt_v2_enabled


def apply_tags(target: Any, tags: FeedbackTags, *, model: str | None = None) -> None:
    """Aplica `tags` ao `target` (FeedbackItem | SurveyResponse) in-place, sem DB.

    NÃO sobrescreve nada quando `tags is None` (chamador deve checar antes). Segue a
    regra do incerto: quando incerto+v2, segura o `sentiment` e preserva o palpite."""
    meta: dict[str, Any] = dict(getattr(target, "ai_meta", None) or {})
    meta["urgency"] = tags.urgency
    meta["confianca"] = tags.confianca
    meta["incerto"] = tags.incerto
    if model:
        meta["model"] = model

    if tags.incerto and _sentiment_pt_v2_enabled():
        # Não chuta: deixa o sentiment como está (None vira "sem classificação" na UI)
        # e preserva o palpite da IA para o operador conferir/revisar.
        meta["sentiment_sugerido"] = tags.sentiment
    else:
        target.sentiment = tags.sentiment

    # Temas são informativos mesmo quando o sentimento é incerto — sempre úteis.
    target.themes = tags.themes
    target.ai_meta = meta
