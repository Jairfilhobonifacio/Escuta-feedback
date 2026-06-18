"""Análise DETALHADA do churn da Bizzu — TODOS os clientes que pediram cancelamento.

Puxa a API de Clientes (Partner), pega TODOS os que cancelaram (qualquer plano:
mensal, anual, etc.) e produz um relatório AGREGADO (sem PII): por plano, perfil de
churn, motivo, tempo de casa, NPS prévio (satisfação antes de sair) e receita perdida.
Salva também docs/campanhas/analise-churn.md (sem PII — só números).

  NÃO dispara mensagem. Só LÊ a API e agrega. stdout/MD sem nome/e-mail/whatsapp.

Modos:  py scripts/analise_churn.py        (real)
        py scripts/analise_churn.py --demo  (usa os fictícios do export_churn_mensal)

TLS (Avast): truststore.inject_into_ssl() no TOPO, antes de qualquer import app.*.
"""
from __future__ import annotations

import truststore

truststore.inject_into_ssl()

import argparse
import asyncio
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_env() -> None:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


load_env()

_OUT_MD = _PROJECT_ROOT / "docs" / "campanhas" / "analise-churn.md"

_MOTIVO_LABEL = {
    "GUARANTEE_REFUND": "Reembolso na garantia",
    "USER_CANCEL": "Cancelamento voluntário",
    "PAYMENT_FAILED": "Pagamento falhou (involuntário)",
    "OTHER": "Outro",
    None: "Não informado",
}
_PERFIL_LABEL = {
    "churn_rapido": "Cancelou cedo (≤7d / garantia)",
    "churn_pos_uso": "Usou e parou (≥30d)",
    "churn_outro": "Outro motivo (zona cinza)",
    "churn_involuntario": "Pagamento falhou",
    "vai_expirar": "Cancelou, ainda com acesso",
}
_FAIXAS = [(0, 7, "0–7 dias"), (8, 30, "8–30 dias"), (31, 90, "31–90 dias"), (91, 10 ** 9, "90+ dias")]


def _plano(sub: dict) -> str:
    pt = (sub.get("planType") or "").strip().lower()
    pn = (sub.get("planName") or "").strip().lower()
    if any(t in pt for t in ("anual", "annual", "year")) or "anual" in pn:
        return "anual"
    if any(t in pt for t in ("mensal", "monthly", "month", "mes", "mês")) or "mensal" in pn:
        return "mensal"
    return pt or "desconhecido"


def _faixa(days: int | None) -> str:
    if days is None:
        return "sem dado"
    for lo, hi, label in _FAIXAS:
        if lo <= days <= hi:
            return label
    return "sem dado"


def _reais(centavos: int) -> str:
    inteiro, cents = divmod(int(round(centavos)), 100)
    return f"R$ {f'{inteiro:,}'.replace(',', '.')},{cents:02d}"


def _bar(n: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return ""
    filled = round(width * n / total)
    return "█" * filled + "·" * (width - filled)


def _is_churn(sub: dict) -> bool:
    """Pediu/sofreu cancelamento: flag cancelled OU state cancelado (com/sem acesso)."""
    return bool(sub.get("cancelled")) or sub.get("state") in ("cancelled", "cancelled_with_access")


def _collect(customers: list[dict]) -> dict[str, Any]:
    from app.domain.segmentation.profiles import classify_profile
    from app.domain.survey.parsers import nps_bucket

    total_base = len(customers)
    churners: list[dict] = []
    for c in customers:
        sub = c.get("subscription") or {}
        if not _is_churn(sub):
            continue
        nps = c.get("nps") or {}
        days = sub.get("daysAsSubscriber")
        days = int(days) if isinstance(days, (int, float)) else None
        score = nps.get("score")
        score = int(score) if isinstance(score, (int, float)) else None
        churners.append(
            {
                "plano": _plano(sub),
                "perfil": classify_profile(c)["profile"],
                "should_contact": bool(classify_profile(c).get("should_contact")),
                "motivo": sub.get("cancellationReason"),
                "days": days,
                "voted": bool(nps.get("voted")),
                "score": score,
                "bucket": nps_bucket(score) if score is not None else None,
                "pago": sub.get("totalPaidCentavos") if isinstance(sub.get("totalPaidCentavos"), (int, float)) else 0,
            }
        )

    n = len(churners)
    by_plano = Counter(c["plano"] for c in churners)
    by_perfil = Counter(c["perfil"] for c in churners)
    by_motivo = Counter(c["motivo"] for c in churners)
    by_faixa = Counter(_faixa(c["days"]) for c in churners)
    plano_perfil = Counter((c["plano"], c["perfil"]) for c in churners)

    voted = [c for c in churners if c["voted"] and c["score"] is not None]
    by_bucket = Counter(c["bucket"] for c in voted)
    dias_validos = [c["days"] for c in churners if c["days"] is not None]
    contataveis = sum(1 for c in churners if c["should_contact"])
    ltv_perdido = sum(c["pago"] for c in churners)

    return {
        "total_base": total_base,
        "n": n,
        "by_plano": by_plano,
        "by_perfil": by_perfil,
        "by_motivo": by_motivo,
        "by_faixa": by_faixa,
        "plano_perfil": plano_perfil,
        "voted": voted,
        "by_bucket": by_bucket,
        "dias_validos": dias_validos,
        "contataveis": contataveis,
        "ltv_perdido": ltv_perdido,
    }


def _report(a: dict[str, Any]) -> str:
    n = a["n"]
    L: list[str] = []
    P = L.append
    P("# Análise detalhada do CHURN — Bizzu")
    P("")
    P(f"> Gerado {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')} · fonte: API de Clientes (Partner).")
    P("> Agregados sem PII. 'churn' = pediu/sofreu cancelamento (flag `cancelled` ou state cancelado).")
    P("")
    taxa = round(100 * n / a["total_base"], 1) if a["total_base"] else 0
    P(f"**{n} clientes em churn** de {a['total_base']} na base (**{taxa}%**). "
      f"{a['contataveis']} contatáveis (involuntário fica de fora — winback e-mail).")
    P(f"**Receita perdida (LTV somado dos churners):** {_reais(a['ltv_perdido'])} "
      f"(média {_reais(a['ltv_perdido'] // n if n else 0)}/cliente).")
    P("")

    def bloco(titulo: str, counter: Counter, label_map: dict | None = None) -> None:
        P(f"## {titulo}")
        for key, cnt in counter.most_common():
            label = (label_map or {}).get(key, key if key is not None else "—")
            pct = round(100 * cnt / n) if n else 0
            P(f"- **{label}** — {cnt} ({pct}%)  `{_bar(cnt, n)}`")
        P("")

    bloco("Por plano", a["by_plano"])
    bloco("Por perfil de churn", a["by_perfil"], _PERFIL_LABEL)
    bloco("Por motivo (cancellationReason)", a["by_motivo"], _MOTIVO_LABEL)
    bloco("Por tempo de casa", a["by_faixa"])

    # NPS prévio — satisfação ANTES de sair
    P("## NPS prévio (satisfação antes de cancelar)")
    v = a["voted"]
    if v:
        det = a["by_bucket"].get("detractor", 0)
        pas = a["by_bucket"].get("passive", 0)
        pro = a["by_bucket"].get("promoter", 0)
        media = round(sum(c["score"] for c in v) / len(v), 1)
        P(f"- {len(v)} dos {n} churners tinham votado NPS (nota média **{media}/10**).")
        P(f"- Detratores (0–6): **{det}** · Passivos (7–8): {pas} · **Promotores (9–10): {pro}** "
          f"(saíram satisfeitos — sinal de churn evitável!).")
    else:
        P("- Nenhum churner tinha votado NPS antes de sair — a maioria cancela **sem nunca dar feedback**.")
    P("")

    # Cruzamento plano × perfil
    P("## Plano × perfil de churn")
    for (plano, perfil), cnt in a["plano_perfil"].most_common(10):
        P(f"- {plano} · {_PERFIL_LABEL.get(perfil, perfil)} — {cnt}")
    P("")

    # Insights automáticos
    P("## Leitura rápida (insights)")
    outro = a["by_perfil"].get("churn_outro", 0)
    rapido = a["by_perfil"].get("churn_rapido", 0)
    invol = a["by_perfil"].get("churn_involuntario", 0)
    if outro:
        P(f"- **{outro} cancelaram sem motivo registrado** ({round(100 * outro / n)}%): o maior buraco — "
          "a Bizzu nunca pergunta o porquê. É exatamente o que o Escuta captura.")
    if rapido:
        P(f"- **{rapido} cancelaram cedo** (≤7d/garantia): fricção na 1ª experiência — consertar o onboarding.")
    if invol:
        P(f"- **{invol} involuntários** (pagamento falhou): NÃO são insatisfação — recuperáveis por dunning/winback, não por survey.")
    pro = a["by_bucket"].get("promoter", 0)
    if pro:
        P(f"- **{pro} eram promotores** quando saíram: churn evitável (gostavam, mas algo externo pesou) — prioridade de reativação.")
    P("")
    return "\n".join(L)


async def run(demo: bool) -> int:
    if demo:
        from scripts.export_churn import _demo_customers  # type: ignore

        customers = _demo_customers()
    else:
        from app.integrations.bizzu_partner import (
            BizzuPartnerAuthError,
            BizzuPartnerClient,
            BizzuPartnerError,
        )

        client = BizzuPartnerClient()
        customers = []
        try:
            async for c in client.iter_all_customers(page_size=500):
                customers.append(c)
        except BizzuPartnerAuthError:
            print("ERRO: X-API-Key inválida/ausente (401). BIZZU_PARTNER_API_KEY no .env.", file=sys.stderr)
            return 1
        except BizzuPartnerError as exc:
            print(f"ERRO: API de Clientes falhou ({exc}).", file=sys.stderr)
            return 1

    analise = _collect(customers)
    report = _report(analise)
    _OUT_MD.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[salvo em {_OUT_MD}]")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Análise detalhada do churn (todos os planos). NÃO dispara mensagem.")
    parser.add_argument("--demo", action="store_true", help="usa os clientes fictícios (sem tocar API)")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.demo))


if __name__ == "__main__":
    raise SystemExit(main())
