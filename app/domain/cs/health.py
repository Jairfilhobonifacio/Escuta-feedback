"""Health Score de cliente (0-100) — função pura, transparente, sem ML.

Combina os sinais que JÁ temos (NPS, perfil de segmentação, recência de feedback,
sentimento acumulado, estado de assinatura) num score único + banda de risco. A
fórmula é explícita e auditável: `factors` devolve cada ajuste que pesou, pra o time
de CS confiar e agir. Base 50 (neutro) ± ajustes, clamp [0, 100].

É a peça da Fase 1 do ROADMAP_CS: transforma a base de dados rica em ação proativa
(fila de "contas em risco"). Reaproveitada pelo /api/clientes e pela ficha 360.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

BAND_HEALTHY = "healthy"  # >= 70
BAND_WATCH = "watch"      # 40-69
BAND_AT_RISK = "at_risk"  # < 40


@dataclass
class HealthResult:
    score: int
    band: str
    factors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "band": self.band, "factors": self.factors}


def band_for(score: int) -> str:
    if score >= 70:
        return BAND_HEALTHY
    if score >= 40:
        return BAND_WATCH
    return BAND_AT_RISK


# perfil de segmentação -> impacto na saúde (profiles.py). Prefixos cobrem variações.
_PROFILE_DELTA: dict[str, int] = {
    "embaixador": 20,
    "ativo_promotor": 20,
    "ativo_fiel": 18,
    "ativo_recente": 10,
    "ativo_passivo": 0,
    "ativo_silencioso": -5,
    "ativo_em_risco": -22,
    "vai_expirar": -18,
    "churn_involuntario": -30,
    "churn_rapido": -40,
    "churn_pos_uso": -40,
    "churn_outro": -38,
    "cortesia": 0,
    "indefinido": 0,
}


def _profile_delta(perfil: str) -> Optional[int]:
    key = perfil.lower().strip()
    if key in _PROFILE_DELTA:
        return _PROFILE_DELTA[key]
    # match por prefixo (ex.: "churn_xyz" -> trata como churn)
    for k, v in _PROFILE_DELTA.items():
        if key.startswith(k):
            return v
    if key.startswith("churn"):
        return -38
    if key.startswith("ativo"):
        return 0
    return None


def _aware(dt: datetime) -> datetime:
    """SQLite devolve datetime naive; trata como UTC pra subtração não estourar."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def compute_health(
    *,
    nps_score: Optional[int] = None,
    perfil: Optional[str] = None,
    last_feedback_at: Optional[datetime] = None,
    neg_count: int = 0,
    pos_count: int = 0,
    subscription_state: Optional[str] = None,
    now: Optional[datetime] = None,
) -> HealthResult:
    """Calcula o Health Score (0-100) e a banda. Todos os sinais são opcionais —
    o que faltar simplesmente não pesa. Nunca lança."""
    now = now or datetime.now(timezone.utc)
    score = 50.0
    factors: list[dict[str, Any]] = []

    def add(delta: float, label: str) -> None:
        nonlocal score
        if delta:
            score += delta
            factors.append({"delta": int(delta), "label": label})

    # 1. NPS — o sinal mais forte de satisfação declarada.
    if nps_score is not None:
        if nps_score >= 9:
            add(25, f"NPS promotor ({nps_score})")
        elif nps_score >= 7:
            add(5, f"NPS passivo ({nps_score})")
        else:
            add(-30, f"NPS detrator ({nps_score})")

    # 2. Perfil de segmentação (já calculado no sync da API).
    if perfil:
        d = _profile_delta(perfil)
        if d:
            add(d, f"perfil {perfil.replace('_', ' ')}")

    # 3. Recência de engajamento (último feedback).
    if last_feedback_at is not None:
        days = (now - _aware(last_feedback_at)).days
        if days <= 30:
            add(10, "engajou nos últimos 30 dias")
        elif days > 90:
            add(-10, f"sem contato há {days} dias")
    else:
        add(-8, "nunca deu feedback")

    # 4. Sentimento acumulado dos sinais.
    if neg_count > 0 and neg_count >= pos_count:
        add(-15, f"{neg_count} sinal(is) negativo(s)")
    elif pos_count > 0 and pos_count > neg_count:
        add(10, f"{pos_count} sinal(is) positivo(s)")

    # 5. Estado da assinatura (snapshot partner).
    if subscription_state:
        st = subscription_state.lower()
        if "cancel" in st:
            add(-25, "assinatura cancelada")
        elif st in ("active", "ativo", "trialing", "trial"):
            add(5, "assinatura ativa")

    final = max(0, min(100, round(score)))
    return HealthResult(score=final, band=band_for(final), factors=factors)
