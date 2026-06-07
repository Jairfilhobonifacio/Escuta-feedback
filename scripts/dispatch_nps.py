"""Dispara a survey NPS para um contato e/ou inspeciona o funil (Fase 0).

Mesmo padrão de carga de .env do seed/check_db_state: lê o .env da raiz com
os.environ.setdefault ANTES de importar app.* (config.py avalia o ambiente no
momento do import). Variáveis já presentes no ambiente do processo VENCEM o .env.

Política do projeto (07/06): SEM mocks — o envio é sempre via WAHA real (porta 3000).

Uso (PowerShell):
    $env:PYTHONUTF8=1
    py scripts/dispatch_nps.py list
    py scripts/dispatch_nps.py dispatch --phone <DDI+DDD+numero> --force

Proteção: `dispatch` no WAHA real (porta 3000) exige --force — fricção proposital
antes de mandar mensagem de verdade para um contato.

Não imprime segredos (DATABASE_URL nunca aparece na saída).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

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
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyRun, SurveyResponse  # noqa: E402
from app.services.waha import WAHAService  # noqa: E402


def _die(msg: str, code: int = 1) -> int:
    print(f"ERRO: {msg}", file=sys.stderr)
    return code


async def _get_org(session) -> Organization | None:
    return (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()


async def cmd_list() -> int:
    from app.db import SessionLocal

    if SessionLocal is None:
        return _die("DATABASE_URL não configurada (defina no .env ou no ambiente).")

    async with SessionLocal() as session:
        org = await _get_org(session)
        if org is None:
            return _die(f"org '{settings.default_org_slug}' não encontrada — rode o seed.")
        print(f"Org: slug={org.slug!r} name={org.name!r} id={org.id}")

        surveys = (
            await session.execute(select(Survey).where(Survey.organization_id == org.id))
        ).scalars().all()
        for sv in surveys:
            print(f"Survey: id={sv.id} name={sv.name!r} type={sv.type!r} status={sv.status!r} ({len(sv.questions or [])} perguntas)")

        contacts = (
            await session.execute(
                select(Contact).where(Contact.organization_id == org.id).order_by(Contact.phone)
            )
        ).scalars().all()
        print(f"Contatos ({len(contacts)}):")
        for c in contacts:
            print(f"  - phone={c.phone} name={c.name!r} opt_in={c.opt_in} id={c.id}")

        runs = (
            await session.execute(
                select(SurveyRun).where(SurveyRun.organization_id == org.id).order_by(SurveyRun.created_at)
            )
        ).scalars().all()
        print(f"Survey runs ({len(runs)}):")
        for r in runs:
            print(f"  - id={r.id} trigger={r.trigger!r} status={r.status!r} created_at={r.created_at}")

        responses = (
            await session.execute(
                select(SurveyResponse, Contact.phone)
                .join(Contact, Contact.id == SurveyResponse.contact_id)
                .where(SurveyResponse.organization_id == org.id)
                .order_by(SurveyResponse.sent_at)
            )
        ).all()
        print(f"Survey responses ({len(responses)}):")
        for resp, phone in responses:
            print(
                f"  - phone={phone} status={resp.status!r} score={resp.answer_score} "
                f"bucket={resp.nps_bucket!r} text={resp.answer_text!r} "
                f"channel_msg_id={resp.channel_msg_id!r}\n"
                f"    sent_at={resp.sent_at} answered_at={resp.answered_at} closed_at={resp.closed_at} "
                f"run={resp.survey_run_id}"
            )
    return 0


async def cmd_dispatch(phone: str, force: bool) -> int:
    from app.db import SessionLocal

    if SessionLocal is None:
        return _die("DATABASE_URL não configurada (defina no .env ou no ambiente).")

    waha_url = settings.waha_base_url
    if ":3000" in waha_url and not force:
        return _die(
            f"WAHA_BASE_URL={waha_url} aponta para a porta 3000 (WAHA real). "
            "Para validação local use o mock (ex.: $env:WAHA_BASE_URL='http://localhost:3001'); "
            "para enviar de verdade, repita com --force."
        )
    print(f"WAHA_BASE_URL efetiva: {waha_url} (session={settings.waha_session!r})")

    async with SessionLocal() as session:
        org = await _get_org(session)
        if org is None:
            return _die(f"org '{settings.default_org_slug}' não encontrada — rode o seed.")

        survey = (
            await session.execute(
                select(Survey).where(
                    Survey.organization_id == org.id,
                    Survey.type == "nps",
                    Survey.status == "active",
                )
            )
        ).scalars().first()
        if survey is None:
            return _die("nenhuma survey NPS ativa para a org — rode o seed.")

        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.organization_id == org.id,
                    Contact.phone == phone,
                )
            )
        ).scalar_one_or_none()
        if contact is None:
            return _die(f"contato com phone={phone} não encontrado na org '{org.slug}'.")

        messaging = WAHAService(waha_url, settings.waha_api_key, settings.waha_session)
        dispatcher = SurveyDispatcher(session, org.id, messaging, whatsapp_session=settings.waha_session)
        run = await dispatcher.dispatch(survey, [contact])
        await session.commit()

        resp = (
            await session.execute(
                select(SurveyResponse).where(
                    SurveyResponse.survey_run_id == run.id,
                    SurveyResponse.contact_id == contact.id,
                )
            )
        ).scalar_one()

        print("=== Dispatch concluído ===")
        print(f"SurveyRun:      id={run.id} status={run.status!r} trigger={run.trigger!r}")
        print(
            f"SurveyResponse: id={resp.id} status={resp.status!r} "
            f"channel_msg_id={resp.channel_msg_id!r} sent_at={resp.sent_at}"
        )
        if resp.channel_msg_id is None:
            print(
                "AVISO: channel_msg_id vazio — o gateway não confirmou o envio "
                "(mock fora do ar? URL errada?). Verifique o log do mock.",
                file=sys.stderr,
            )
            return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispara/inspeciona a survey NPS (Fase 0).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="mostra org, survey, contatos, runs e responses")
    p_dispatch = sub.add_parser("dispatch", help="dispara a survey NPS para um contato")
    p_dispatch.add_argument("--phone", required=True, help="telefone do contato (apenas dígitos: DDI+DDD+numero)")
    p_dispatch.add_argument("--force", action="store_true", help="permite WAHA_BASE_URL na porta 3000 (WAHA real)")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        return asyncio.run(cmd_list())
    return asyncio.run(cmd_dispatch(args.phone, args.force))


if __name__ == "__main__":
    raise SystemExit(main())
