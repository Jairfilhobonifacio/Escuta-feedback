"""Disparo SELETIVO de surveys de WhatsApp POR PERFIL de cliente (Fase 0).

Liga os perfis já classificados (gravados em Contact.profile_data['partner']['profile']
pelo sync_partner_customers.py) às surveys do seed, via o mapa PURO
app/domain/segmentation/profile_surveys.py. Mesmo padrão de carga de .env do
dispatch_nps.py: lê o .env da raiz com os.environ.setdefault ANTES de importar
app.* (config.py avalia o ambiente no import). Org via settings.default_org_slug.

SEGURANÇA (regra dura desta entrega):
  - 'plan' é o subcomando DEFAULT e NÃO envia nada — só conta elegíveis por perfil.
    Nunca imprime PII (nome / e-mail / telefone): só perfil -> survey -> contagem.
  - 'dispatch' é o ÚNICO caminho que envia, e é sempre explícito. No WAHA real
    (WAHA_BASE_URL com ':3000') exige --force, igual ao dispatch_nps.py.
  - Elegibilidade exige opt_in=True + perfil casado + survey existente + cooldown OK
    (sem SurveyResponse para (contato, essa survey) nos últimos COOLDOWN_DAYS dias).

Uso (PowerShell):
    $env:PYTHONUTF8=1
    py scripts/dispatch_by_profile.py                       # = plan (dry-run, só contagens)
    py scripts/dispatch_by_profile.py plan
    py scripts/dispatch_by_profile.py plan --plan anual      # idem, só anuais ativos
    py scripts/dispatch_by_profile.py dispatch --profile ativo_recente [--limit 10] [--force]
    py scripts/dispatch_by_profile.py dispatch --profile ativo_fiel --plan anual [--limit 50] [--force]

Filtro --plan (opcional): casa com Contact.profile_data['partner']['subscription']
['planType'] (heurística tolerante: 'anual' bate 'anual'/'annual'/'yearly'/...). Sem
--plan, comportamento idêntico ao anterior (todos os planos do perfil).

Templating de variáveis na pergunta enviada (resolvido AQUI, por contato): além do
{nome} (que o dispatcher prefixa na saudação), resolvemos {meses_de_casa},
{dias_para_renovar} e {novidade} a partir de profile_data['partner'] quando houver.
Variável ausente é NEUTRALIZADA (some) — nunca vaza um {placeholder} cru pro cliente.

Não imprime segredos (DATABASE_URL nunca aparece na saída).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

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

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.domain.segmentation.profile_surveys import (  # noqa: E402
    PROFILE_TO_SURVEY,
    survey_cycle_for_profile,
    survey_for_profile,
)
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse, SurveyRun  # noqa: E402
from app.services.waha import WAHAService  # noqa: E402

# Janela mínima entre dois contatos com a MESMA survey para o MESMO contato.
COOLDOWN_DAYS = 7


def _die(msg: str, code: int = 1) -> int:
    print(f"ERRO: {msg}", file=sys.stderr)
    return code


async def _get_org(session) -> Organization | None:
    return (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()


def _profile_expr():
    """Expressão SQL p/ Contact.profile_data['partner']['profile'] como texto.

    No Postgres compila para `->>` (JSONB). Em SQLite (testes) usa o accessor JSON
    genérico. Mantém o filtro portável sem SQL cru.
    """
    return Contact.profile_data["partner"]["profile"].as_string()


def _plan_type_expr():
    """Expressão SQL p/ profile_data['partner']['subscription']['planType'] como texto.

    Mesmo padrão portável de _profile_expr (JSONB no PG, accessor JSON no SQLite).
    """
    return Contact.profile_data["partner"]["subscription"]["planType"].as_string()


# Tokens que, dentro do planType, contam como "plano anual" (heurística tolerante —
# espelha export_anuais_ativos._is_anual; o vocabulário real é confirmado nos logs).
_PLAN_ALIASES: dict[str, tuple[str, ...]] = {
    "anual": ("anual", "annual", "year", "yearly", "ano"),
}


def _plan_matches(plan_type: str | None, wanted: str) -> bool:
    """True se `plan_type` casa com o `wanted` (--plan). Tolerante: usa os aliases
    conhecidos (ex.: --plan anual casa 'anual'/'annual'/'yearly'); fora deles, faz
    substring case-insensitive do próprio termo. None nunca casa."""
    pt = (plan_type or "").strip().lower()
    if not pt:
        return False
    tokens = _PLAN_ALIASES.get(wanted.strip().lower(), (wanted.strip().lower(),))
    return any(tok in pt for tok in tokens)


# --- Templating de variáveis extras (resolvido por CONTATO, fora do dispatcher) ---

# Variáveis suportadas na pergunta da survey. {nome} é resolvido pelo dispatcher
# (saudação) e NÃO entra aqui. As demais saem de profile_data['partner'].
_TEMPLATE_VARS = ("meses_de_casa", "dias_para_renovar", "novidade")
# Texto neutro p/ {novidade} quando o snapshot não traz uma feature específica.
_NOVIDADE_FALLBACK = "uma novidade que acabamos de soltar"


def _parse_iso_dt(value) -> datetime | None:
    """ISO-8601 (str da API, com 'Z') -> datetime aware; tolera None/valor inválido.

    Mesmo padrão de export_anuais_ativos._parse_dt / app.domain.feedback.ingest.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _template_values(contact: Contact, now: datetime) -> dict[str, str]:
    """Calcula as variáveis extras p/ ESTE contato a partir de profile_data['partner'].

    Devolve só as variáveis com valor DISPONÍVEL (as ausentes ficam de fora → o
    render as neutraliza, sem deixar {placeholder} cru). Best-effort: dados ausentes
    ou malformados simplesmente não geram a variável.
      - meses_de_casa   <- subscription.daysAsSubscriber (arredondado por 30)
      - dias_para_renovar <- (subscription.currentPeriodEnd - hoje).days, se >= 0
      - novidade        <- partner.novidade, se gravada no snapshot
    """
    partner = (contact.profile_data or {}).get("partner") or {}
    sub = partner.get("subscription") or {}
    out: dict[str, str] = {}

    days = sub.get("daysAsSubscriber")
    if isinstance(days, (int, float)) and days >= 0:
        out["meses_de_casa"] = str(max(1, round(days / 30)))

    renova_dt = _parse_iso_dt(sub.get("currentPeriodEnd"))
    if renova_dt is not None:
        restante = (renova_dt.date() - now.date()).days
        if restante >= 0:
            out["dias_para_renovar"] = str(restante)

    novidade = partner.get("novidade")
    if isinstance(novidade, str) and novidade.strip():
        out["novidade"] = novidade.strip()

    return out


def _render_template(text: str, values: dict[str, str]) -> str:
    """Substitui {var} conhecidas por seus valores; NEUTRALIZA as ausentes.

    Só mexe nas variáveis de _TEMPLATE_VARS (não toca {nome}, que é do dispatcher,
    nem chaves desconhecidas). Variável sem valor:
      - {novidade}            -> texto neutro de fallback (a frase precisa de um sujeito);
      - {meses_de_casa}/{dias_para_renovar} -> some, junto de espaço/pontuação órfã ao redor,
        pois são quantidades (deixar "fez  meses" ou " dias" ficaria torto).
    Nunca devolve um {placeholder} cru.
    """
    result = text
    for var in _TEMPLATE_VARS:
        token = "{" + var + "}"
        if token not in result:
            continue
        val = values.get(var)
        if val is not None:
            result = result.replace(token, val)
        elif var == "novidade":
            result = result.replace(token, _NOVIDADE_FALLBACK)
        else:
            # Quantidade ausente: remove o token e o espaço/pontuação imediatamente
            # ao redor para não deixar lacuna dupla ("fez  meses" -> "fez meses").
            result = re.sub(r"\s*" + re.escape(token) + r"\s*", " ", result)
    # Colapsa espaços que possam ter sobrado da remoção.
    return re.sub(r"[ \t]{2,}", " ", result).strip()


def _render_survey_for_contact(survey: Survey, contact: Contact, now: datetime):
    """Clona (em memória, NÃO na sessão) a survey com as perguntas TEMPLATADAS p/ este
    contato. Devolve um shim com (id, type, questions) — os ÚNICOS atributos que o
    SurveyDispatcher lê. Preserva survey.id (FK real do SurveyRun) e survey.type.

    Se nenhuma pergunta tem placeholder, devolve a própria survey (sem alocar nada).
    """
    questions = survey.questions or []
    has_placeholder = any(
        any(("{" + v + "}") in (q.get("text") or "") for v in _TEMPLATE_VARS)
        for q in questions
    )
    if not has_placeholder:
        return survey

    values = _template_values(contact, now)
    rendered = [
        {**q, "text": _render_template(q.get("text", ""), values)} for q in questions
    ]
    return SimpleNamespace(id=survey.id, type=survey.type, questions=rendered)


async def _eligible_contacts(
    session, org_id, profile: str, survey: Survey, plan: str | None = None
) -> list[Contact]:
    """Contatos ELEGÍVEIS para receber `survey` por estarem no `profile`.

    Critérios (todos obrigatórios):
      - opt_in == True
      - profile_data['partner']['profile'] == profile
      - se `plan` informado: profile_data['partner']['subscription']['planType'] casa
        `plan` (heurística tolerante — ver _plan_matches). Sem `plan`, filtro inativo.
      - cooldown OK: NÃO existe SurveyResponse para (contato, essa survey) criada
        nos últimos COOLDOWN_DAYS dias (join responses -> runs filtrando survey_id).
    A existência da survey é responsabilidade do chamador (já resolvida).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)

    # contatos que JÁ receberam esta survey dentro da janela de cooldown
    recent_contact_ids = (
        select(SurveyResponse.contact_id)
        .join(SurveyRun, SurveyRun.id == SurveyResponse.survey_run_id)
        .where(
            SurveyResponse.organization_id == org_id,
            SurveyRun.survey_id == survey.id,
            SurveyResponse.sent_at.is_not(None),
            SurveyResponse.sent_at >= cutoff,
        )
    )

    rows = (
        await session.execute(
            select(Contact)
            .where(
                Contact.organization_id == org_id,
                Contact.opt_in.is_(True),
                _profile_expr() == profile,
                Contact.id.not_in(recent_contact_ids),
            )
            .order_by(Contact.phone)
        )
    ).scalars().all()

    contacts = list(rows)
    if plan:
        # planType é heurístico (anual/annual/yearly...): filtra em Python sobre o
        # snapshot já carregado, em vez de tentar casar variantes em SQL.
        contacts = [
            c
            for c in contacts
            if _plan_matches(
                ((c.profile_data or {}).get("partner") or {})
                .get("subscription", {})
                .get("planType"),
                plan,
            )
        ]
    return contacts


async def _surveys_by_name(session, org_id) -> dict[str, Survey]:
    surveys = (
        await session.execute(select(Survey).where(Survey.organization_id == org_id))
    ).scalars().all()
    return {sv.name: sv for sv in surveys}


# --------------------------------------------------------------------------- plan


async def cmd_plan(plan: str | None = None) -> int:
    """SÓ contagens: perfil -> survey -> nº de contatos elegíveis. NÃO envia, sem PII.

    Mostra a survey PRIMÁRIA de cada perfil (survey_for_profile). Perfis com
    alternância (Check-in vs Indicação) recebem um marcador '+rot' — o disparo real
    escolhe a 1ª survey da rotação com cooldown OK por contato. `plan` filtra por
    planType (ex.: 'anual'); None = todos os planos.
    """
    from app.db import SessionLocal

    if SessionLocal is None:
        return _die("DATABASE_URL não configurada (defina no .env ou no ambiente).")

    async with SessionLocal() as session:
        org = await _get_org(session)
        if org is None:
            return _die(f"org '{settings.default_org_slug}' não encontrada — rode o seed.")

        surveys = await _surveys_by_name(session, org.id)
        plan_label = f" | plan={plan!r}" if plan else ""
        print(f"Org: slug={org.slug!r} id={org.id} (cooldown={COOLDOWN_DAYS} dias){plan_label}")
        print(f"{'PERFIL':<22} {'SURVEY':<26} {'ELEGÍVEIS':>9}")
        print(f"{'-' * 22} {'-' * 26} {'-' * 9}")

        total = 0
        # Itera só os perfis COM survey associada (None = não contatar, fica de fora).
        for profile, survey_name in sorted(PROFILE_TO_SURVEY.items()):
            if survey_name is None:
                continue
            # Marca perfis em rotação (Check-in vs Indicação) — a contagem usa a primária.
            rot = "+rot" if len(survey_cycle_for_profile(profile)) > 1 else ""
            label = f"{survey_name}{(' ' + rot) if rot else ''}"
            survey = surveys.get(survey_name)
            if survey is None:
                print(f"{profile:<22} {label:<26} {'AUSENTE':>9}  (rode o seed)")
                continue
            eligible = await _eligible_contacts(session, org.id, profile, survey, plan=plan)
            total += len(eligible)
            print(f"{profile:<22} {label:<26} {len(eligible):>9}")

        print(f"{'-' * 22} {'-' * 26} {'-' * 9}")
        print(f"{'TOTAL ELEGÍVEIS':<49} {total:>9}")
        print("=== PLAN (dry-run): nada enviado, nenhum dado pessoal impresso ===")
    return 0


# ----------------------------------------------------------------------- dispatch


async def cmd_dispatch(
    profile: str, limit: int | None, force: bool, plan: str | None = None
) -> int:
    from app.db import SessionLocal

    if SessionLocal is None:
        return _die("DATABASE_URL não configurada (defina no .env ou no ambiente).")

    # Surveys candidatas em ordem de preferência (alternância Check-in vs Indicação
    # para os fãs do produto; lista de 1 para os demais). Vazia = não contatar.
    cycle = survey_cycle_for_profile(profile)
    if not cycle:
        return _die(
            f"perfil {profile!r} não tem survey associada (None = não contatar). "
            f"Perfis com survey: "
            f"{sorted(p for p, s in PROFILE_TO_SURVEY.items() if s is not None)}"
        )

    waha_url = settings.waha_base_url
    if ":3000" in waha_url and not force:
        return _die(
            f"WAHA_BASE_URL={waha_url} aponta para a porta 3000 (WAHA real). "
            "Para validação local use o mock (ex.: $env:WAHA_BASE_URL='http://localhost:3001'); "
            "para enviar de verdade, repita com --force."
        )
    plan_label = f" | plan={plan!r}" if plan else ""
    print(f"WAHA_BASE_URL efetiva: {waha_url} (session={settings.waha_session!r})")
    print(
        f"Perfil={profile!r} -> candidatas={cycle} (cooldown={COOLDOWN_DAYS} dias)"
        f"{plan_label}"
    )

    async with SessionLocal() as session:
        org = await _get_org(session)
        if org is None:
            return _die(f"org '{settings.default_org_slug}' não encontrada — rode o seed.")

        # Escolhe a 1ª survey da rotação que esteja ATIVA e tenha elegíveis (cooldown
        # OK). É assim que Check-in vs Indicação se decide por contato/histórico.
        survey = None
        contacts: list[Contact] = []
        for name in cycle:
            candidate = (
                await session.execute(
                    select(Survey).where(
                        Survey.organization_id == org.id,
                        Survey.name == name,
                        Survey.status == "active",
                    )
                )
            ).scalar_one_or_none()
            if candidate is None:
                print(f"  ~ survey {name!r} ativa não existe — pulando (rode o seed).")
                continue
            eligible = await _eligible_contacts(session, org.id, profile, candidate, plan=plan)
            if eligible:
                survey, contacts = candidate, eligible
                break

        if survey is None:
            print("Nenhum contato elegível (opt_in + perfil + plano + cooldown). Nada a enviar.")
            return 0

        if limit is not None and limit >= 0:
            contacts = contacts[:limit]

        print(f"Survey escolhida: {survey.name!r}. Elegíveis a disparar: {len(contacts)} contato(s).")
        messaging = WAHAService(waha_url, settings.waha_api_key, settings.waha_session)
        dispatcher = SurveyDispatcher(
            session, org.id, messaging, whatsapp_session=settings.waha_session
        )

        now = datetime.now(timezone.utc)
        # Templating por contato ({meses_de_casa}/{dias_para_renovar}/{novidade}): se a
        # survey tem placeholders, cada contato precisa do próprio texto, então dispara
        # individualmente (1 SurveyRun por contato). Sem placeholders, dispara o lote
        # inteiro de uma vez (1 SurveyRun) — caminho comum, comportamento anterior.
        needs_templating = (
            _render_survey_for_contact(survey, contacts[0], now) is not survey
        )
        runs = []
        if needs_templating:
            for contact in contacts:
                rendered = _render_survey_for_contact(survey, contact, now)
                runs.append(await dispatcher.dispatch(rendered, [contact], trigger="profile"))
        else:
            runs.append(await dispatcher.dispatch(survey, contacts, trigger="profile"))
        await session.commit()

        run_ids = [r.id for r in runs]
        sent = (
            await session.execute(
                select(SurveyResponse).where(SurveyResponse.survey_run_id.in_(run_ids))
            )
        ).scalars().all()
        with_msg = sum(1 for r in sent if r.channel_msg_id)

        print("=== Dispatch por perfil concluído ===")
        print(
            f"SurveyRun(s): {len(runs)} ({'templating por contato' if needs_templating else 'lote único'})"
            f" trigger='profile'"
        )
        print(f"Responses:  {len(sent)} criada(s); {with_msg} com channel_msg_id (envio confirmado).")
        if with_msg < len(sent):
            print(
                "AVISO: algumas mensagens ficaram sem channel_msg_id — o gateway pode "
                "não ter confirmado (mock fora do ar? URL errada?).",
                file=sys.stderr,
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Disparo SELETIVO de surveys por perfil (Fase 0). 'plan' é dry-run e default."
    )
    sub = parser.add_subparsers(dest="cmd")
    p_plan = sub.add_parser("plan", help="(default) conta elegíveis por perfil. NÃO envia, sem PII.")
    p_plan.add_argument(
        "--plan",
        default=None,
        help="filtra por planType (ex.: 'anual'); sem ele, conta todos os planos.",
    )
    p_dispatch = sub.add_parser("dispatch", help="dispara a survey do perfil para os elegíveis")
    p_dispatch.add_argument("--profile", required=True, help="rótulo do perfil (ex.: ativo_recente)")
    p_dispatch.add_argument("--limit", type=int, default=None, help="limita quantos contatos disparar")
    p_dispatch.add_argument(
        "--plan",
        default=None,
        help="filtra por planType (ex.: 'anual'); sem ele, todos os planos do perfil.",
    )
    p_dispatch.add_argument(
        "--force", action="store_true", help="permite WAHA_BASE_URL na porta 3000 (WAHA real)"
    )
    args = parser.parse_args(argv)

    if args.cmd == "dispatch":
        return asyncio.run(cmd_dispatch(args.profile, args.limit, args.force, plan=args.plan))
    # default / 'plan' -> dry-run seguro. getattr: 'plan' pode não ter sido criado
    # quando nenhum subcomando foi passado (argparse não roda o parser do 'plan').
    return asyncio.run(cmd_plan(plan=getattr(args, "plan", None)))


if __name__ == "__main__":
    raise SystemExit(main())
