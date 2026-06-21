"""Limpa DADOS DE TESTE do piloto com SEGURANÇA (dry-run por padrão).

Contexto: o piloto pode ficar poluído com respostas de teste que inflam os números
(especialmente detratores). Passe os telefones de teste reais via --phone (repetível) —
NÃO deixamos números/nomes reais versionados neste script (PII). Os placeholders abaixo
em DEFAULT_TEST_PHONES NÃO casam com ninguém em produção; servem só de exemplo de formato.

O que faz, por telefone (via Contact.phone) e pelos registros LIGADOS ao contato
por contact_id:
  - conta/lista feedback_items, survey_responses, messages e o próprio contact.

Ordem de exclusão (modo --apply, dentro de UMA transação, respeitando as FKs):
    feedback_items -> survey_responses -> messages -> contact
(Message.survey_response_id é ON DELETE SET NULL; por isso apagamos as messages do
contato por contact_id logo em seguida — nenhuma fica órfã.)

Modos:
  --dry-run  (PADRÃO)  LISTA o que existe; NÃO apaga nada (rollback no fim).
  --apply              APAGA de verdade (commit). NÃO rode sem revisão.

Telefones configuráveis: passe um ou mais via --phone (repetível). Sem --phone,
usa os 3 acima como DEFAULT.

Rodar (recomendado, evita 'charmap' no Windows):
    PYTHONUTF8=1 py scripts/_limpar_dados_teste.py            # dry-run (default)
    PYTHONUTF8=1 py scripts/_limpar_dados_teste.py --phone 5524998365809
    PYTHONUTF8=1 py scripts/_limpar_dados_teste.py --apply    # NÃO rodar sem OK
"""
from __future__ import annotations

# TLS do antivírus desta máquina: precisa vir no TOPO, antes de qualquer rede/SSL.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001  (best-effort; segue sem se indisponível)
    pass

import argparse
import asyncio
import os
import re
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# O .env NÃO é carregado pelo ambiente — carregamos aqui ANTES de importar app.config
# (Settings lê DATABASE_URL no import). Os scripts do projeto fazem o mesmo.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:  # noqa: BLE001  (fallback manual abaixo)
    pass

if not os.getenv("DATABASE_URL"):
    # Fallback: parse manual mínimo do .env (KEY=VALUE), caso python-dotenv falte.
    _env_path = os.path.join(_PROJECT_ROOT, ".env")
    if os.path.exists(_env_path):
        with open(_env_path, encoding="utf-8") as _fh:
            for _line in _fh:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())


# Placeholders genéricos (NÃO são telefones reais). Os números de teste reais devem
# vir via --phone (repetível) — não versionamos PII neste script. Strings: comparamos
# contra Contact.phone exatamente como está armazenado.
DEFAULT_TEST_PHONES = [
    "5511999990000",
    "5511999990001",
]


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


async def _amain(phones: list[str], apply: bool) -> int:
    from sqlalchemy import delete, func, select

    from app.db import SessionLocal

    # Importa TODOS os models p/ registrar os mappers (senão SQLAlchemy estoura ao
    # resolver os relacionamentos por FK). Mesma precaução de _diag_telefones.py.
    from app.models.core import Contact  # noqa: F401
    from app.models.feedback import FeedbackItem
    from app.models.survey import Message, SurveyResponse
    import app.models.improvement  # noqa: F401
    import app.models.cluster  # noqa: F401
    import app.models.playbook  # noqa: F401

    if SessionLocal is None:
        print("ERRO: DATABASE_URL não configurada — não há engine de banco.", file=sys.stderr)
        return 1

    modo = "APPLY (APAGANDO)" if apply else "DRY-RUN (somente listando)"
    print("=" * 72)
    print(f"  LIMPEZA DE DADOS DE TESTE — modo: {modo}")
    print(f"  Telefones-alvo ({len(phones)}): {', '.join(phones)}")
    print("=" * 72)

    # Totais agregados (para o resumo final).
    tot = {"contacts": 0, "feedback_items": 0, "survey_responses": 0, "messages": 0}
    phones_sem_contato: list[str] = []

    async with SessionLocal() as session:
        for phone in phones:
            print(f"\n### Telefone: {phone}")

            # Match por igualdade exata E por dígitos (cobre variações de máscara/DDI).
            contatos = (
                (
                    await session.execute(
                        select(Contact).where(
                            (Contact.phone == phone)
                            | (func.regexp_replace(Contact.phone, r"\D", "", "g") == _digits(phone))
                        )
                    )
                )
                .scalars()
                .all()
            )

            if not contatos:
                print("   (nenhum contato encontrado para este telefone)")
                phones_sem_contato.append(phone)
                continue

            contact_ids = [c.id for c in contatos]
            for c in contatos:
                org = str(c.organization_id)
                print(
                    f"   contact id={c.id}  org={org[:8]}…  "
                    f"phone={c.phone!r}  name={c.name!r}  opt_in={c.opt_in}  "
                    f"handoff={c.needs_human_handoff}"
                )

            # ---- feedback_items ligados a esses contatos ----
            fbs = (
                (
                    await session.execute(
                        select(FeedbackItem).where(FeedbackItem.contact_id.in_(contact_ids))
                    )
                )
                .scalars()
                .all()
            )
            print(f"   feedback_items: {len(fbs)}")
            for fb in fbs:
                txt = (fb.text or "").replace("\n", " ")
                if len(txt) > 60:
                    txt = txt[:57] + "..."
                print(
                    f"      - id={str(fb.id)[:8]}… source={fb.source} type={fb.type} "
                    f"score={fb.score} bucket={fb.nps_bucket} text={txt!r}"
                )

            # ---- survey_responses ligadas a esses contatos ----
            srs = (
                (
                    await session.execute(
                        select(SurveyResponse).where(SurveyResponse.contact_id.in_(contact_ids))
                    )
                )
                .scalars()
                .all()
            )
            print(f"   survey_responses: {len(srs)}")
            for sr in srs:
                txt = (sr.answer_text or "").replace("\n", " ")
                if len(txt) > 60:
                    txt = txt[:57] + "..."
                print(
                    f"      - id={str(sr.id)[:8]}… status={sr.status} score={sr.answer_score} "
                    f"bucket={sr.nps_bucket} source={sr.source} text={txt!r}"
                )

            # ---- messages (transcript) ligadas a esses contatos ----
            msgs = (
                (
                    await session.execute(
                        select(Message).where(Message.contact_id.in_(contact_ids))
                    )
                )
                .scalars()
                .all()
            )
            print(f"   messages: {len(msgs)}")
            n_in = sum(1 for m in msgs if m.direction == "inbound")
            n_out = sum(1 for m in msgs if m.direction == "outbound")
            if msgs:
                print(f"      ({n_in} inbound / {n_out} outbound)")

            tot["contacts"] += len(contatos)
            tot["feedback_items"] += len(fbs)
            tot["survey_responses"] += len(srs)
            tot["messages"] += len(msgs)

            if apply:
                # Ordem segura, respeitando as FKs:
                #   feedback_items -> survey_responses -> messages -> contact
                await session.execute(
                    delete(FeedbackItem).where(FeedbackItem.contact_id.in_(contact_ids))
                )
                await session.execute(
                    delete(SurveyResponse).where(SurveyResponse.contact_id.in_(contact_ids))
                )
                await session.execute(
                    delete(Message).where(Message.contact_id.in_(contact_ids))
                )
                await session.execute(delete(Contact).where(Contact.id.in_(contact_ids)))
                print("   [APPLY] registros marcados para exclusão (commit no fim).")

        # Resumo.
        print("\n" + "=" * 72)
        print("  RESUMO (total entre todos os telefones)")
        print("=" * 72)
        print(f"   contacts ........... {tot['contacts']}")
        print(f"   feedback_items ..... {tot['feedback_items']}")
        print(f"   survey_responses ... {tot['survey_responses']}")
        print(f"   messages ........... {tot['messages']}")
        if phones_sem_contato:
            print(f"   telefones sem contato: {', '.join(phones_sem_contato)}")

        if apply:
            await session.commit()
            print("\n>>> APPLY: transação COMMITADA. Dados de teste removidos.")
        else:
            await session.rollback()
            print("\n>>> DRY-RUN: nada foi alterado (rollback). Use --apply para apagar.")

    return 0


async def _amain_grupos(apply: bool) -> int:
    """Apaga contatos de GRUPO residuais (classe 'group') SEM nome e SEM vinculo de
    cliente real (sem partner/bizzu_user_id) — lixo do webhook anterior a barreira de
    @g.us. Mesma ordem de exclusao de FK do _amain (feedback_items -> survey_responses
    -> messages -> contact). Criterio conservador p/ nunca pegar cliente real."""
    from sqlalchemy import delete, select

    from app.db import SessionLocal
    from app.domain.contacts.whatsapp import classify_phone
    from app.models.core import Contact
    from app.models.feedback import FeedbackItem
    from app.models.survey import Message, SurveyResponse
    import app.models.improvement  # noqa: F401
    import app.models.cluster  # noqa: F401
    import app.models.playbook  # noqa: F401

    if SessionLocal is None:
        print("ERRO: DATABASE_URL nao configurada.", file=sys.stderr)
        return 1

    modo = "APPLY (APAGANDO)" if apply else "DRY-RUN (somente listando)"
    print("=" * 72)
    print(f"  LIMPEZA DE GRUPOS-RESIDUO (classe 'group', sem nome/vinculo) — modo: {modo}")
    print("=" * 72)

    async with SessionLocal() as session:
        contatos = (await session.execute(select(Contact))).scalars().all()
        alvo = []
        for c in contatos:
            pd = c.profile_data or {}
            nome_vazio = not (c.name or "").strip()
            sem_vinculo = not pd.get("partner") and not pd.get("bizzu_user_id")
            if classify_phone(c.phone) == "group" and nome_vazio and sem_vinculo:
                alvo.append(c)

        if not alvo:
            print("  (nenhum contato de grupo residual encontrado)")
            return 0

        ids = [c.id for c in alvo]
        print(f"  {len(alvo)} contato(s) de grupo a remover:")
        for c in alvo:
            print(f"   - id={str(c.id)[:8]}... phone={c.phone!r} name={c.name!r}")

        n_fb = len((await session.execute(select(FeedbackItem).where(FeedbackItem.contact_id.in_(ids)))).scalars().all())
        n_sr = len((await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id.in_(ids)))).scalars().all())
        n_msg = len((await session.execute(select(Message).where(Message.contact_id.in_(ids)))).scalars().all())
        print(f"  ligados: feedback_items={n_fb}  survey_responses={n_sr}  messages={n_msg}")

        if apply:
            await session.execute(delete(FeedbackItem).where(FeedbackItem.contact_id.in_(ids)))
            await session.execute(delete(SurveyResponse).where(SurveyResponse.contact_id.in_(ids)))
            await session.execute(delete(Message).where(Message.contact_id.in_(ids)))
            await session.execute(delete(Contact).where(Contact.id.in_(ids)))
            await session.commit()
            print(f"\n>>> APPLY: {len(alvo)} grupos + ligados REMOVIDOS (commit).")
        else:
            await session.rollback()
            print("\n>>> DRY-RUN: nada alterado (rollback). Use --grupos --apply para apagar.")

    return 0


async def _amain_chat_lixo(apply: bool) -> int:
    """Apaga conversa-LIXO do Chat: contatos SEM vinculo de cliente (sem partner /
    bizzu_user_id) que TEM mensagens (entraram via webhook em testes, conversa pessoal/
    spam — nao sao clientes). Preserva: clientes importados (tem partner) e leads de
    e-mail/winback (sem mensagens). Mesma ordem de FK do _amain."""
    from sqlalchemy import delete, select

    from app.db import SessionLocal
    from app.models.core import Contact
    from app.models.feedback import FeedbackItem
    from app.models.survey import Message, SurveyResponse
    import app.models.improvement  # noqa: F401
    import app.models.cluster  # noqa: F401
    import app.models.playbook  # noqa: F401

    if SessionLocal is None:
        print("ERRO: DATABASE_URL nao configurada.", file=sys.stderr)
        return 1

    modo = "APPLY (APAGANDO)" if apply else "DRY-RUN (somente listando)"
    print("=" * 72)
    print(f"  LIMPEZA DE CONVERSA-LIXO DO CHAT (sem vinculo + com mensagens) — modo: {modo}")
    print("=" * 72)

    async with SessionLocal() as session:
        com_msg = set(
            (await session.execute(select(Message.contact_id).distinct())).scalars().all()
        )
        com_msg.discard(None)
        if not com_msg:
            print("  (nenhum contato com mensagens)")
            return 0
        contatos = (
            await session.execute(select(Contact).where(Contact.id.in_(com_msg)))
        ).scalars().all()
        alvo = []
        for c in contatos:
            pd = c.profile_data or {}
            if not pd.get("partner") and not pd.get("bizzu_user_id"):
                alvo.append(c)

        if not alvo:
            print("  (nenhuma conversa-lixo: todos os contatos com mensagem tem vinculo de cliente)")
            return 0

        ids = [c.id for c in alvo]
        print(f"  {len(alvo)} contato(s) de conversa-lixo a remover:")
        for c in alvo:
            print(f"   - id={str(c.id)[:8]}... phone={c.phone!r} name={c.name!r}")
        n_fb = len((await session.execute(select(FeedbackItem).where(FeedbackItem.contact_id.in_(ids)))).scalars().all())
        n_sr = len((await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id.in_(ids)))).scalars().all())
        n_msg = len((await session.execute(select(Message).where(Message.contact_id.in_(ids)))).scalars().all())
        print(f"  ligados: feedback_items={n_fb}  survey_responses={n_sr}  messages={n_msg}")

        if apply:
            await session.execute(delete(FeedbackItem).where(FeedbackItem.contact_id.in_(ids)))
            await session.execute(delete(SurveyResponse).where(SurveyResponse.contact_id.in_(ids)))
            await session.execute(delete(Message).where(Message.contact_id.in_(ids)))
            await session.execute(delete(Contact).where(Contact.id.in_(ids)))
            await session.commit()
            print(f"\n>>> APPLY: {len(alvo)} conversas-lixo + ligados REMOVIDOS (commit).")
        else:
            await session.rollback()
            print("\n>>> DRY-RUN: nada alterado (rollback). Use --chat-lixo --apply para apagar.")

    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--phone",
        action="append",
        default=None,
        help="Telefone de teste a limpar (repetível). Sem este argumento, usa os 3 DEFAULT.",
    )
    p.add_argument(
        "--grupos",
        action="store_true",
        help="Em vez de telefones, apaga os contatos de GRUPO residuais (classe 'group' sem nome/vinculo).",
    )
    p.add_argument(
        "--chat-lixo",
        dest="chat_lixo",
        action="store_true",
        help="Apaga conversa-lixo do Chat: contatos sem vinculo de cliente que tem mensagens.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Só lista (PADRÃO).")
    g.add_argument("--apply", action="store_true", help="APAGA de verdade (commit).")
    args = p.parse_args()

    if args.grupos:
        return asyncio.run(_amain_grupos(apply=bool(args.apply)))
    if args.chat_lixo:
        return asyncio.run(_amain_chat_lixo(apply=bool(args.apply)))

    phones = args.phone if args.phone else list(DEFAULT_TEST_PHONES)
    # Normaliza/limpa entradas vazias mantendo a string original do usuário.
    phones = [s.strip() for s in phones if s and s.strip()]
    if not phones:
        print("ERRO: nenhum telefone informado.", file=sys.stderr)
        return 2

    return asyncio.run(_amain(phones, apply=bool(args.apply)))


if __name__ == "__main__":
    raise SystemExit(main())
