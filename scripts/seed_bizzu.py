"""Seed IDEMPOTENTE do tenant-piloto Bizzu (org + survey NPS + contatos de teste).

Cria (ou reaproveita, se já existirem) os dados mínimos para tocar o piloto:
  - Organization(slug='bizzu', name='Bizzu')
  - Survey 'NPS Bizzu' (type='nps', disparo manual) com perguntas nps + open
  - Survey 'Exit Bizzu' (type='exit', trigger_event='subscription_cancelled' —
    disparada automaticamente pelo POST /api/events/bizzu no churn)
  - Survey 'CSAT Tópico Bizzu' (type='nps', trigger_event='topic_completed' —
    disparada quando o aluno conclui um tópico de estudos; reusa o motor NPS
    0-10 como escala única do produto)
  - surveys de disparo MANUAL/SELETIVO por perfil (trigger_event=None — sem
    automação; disparadas por scripts/dispatch_by_profile.py):
      'NPS Bizzu' (nps), 'CSAT Onboarding Bizzu' (nps), 'Escuta de Detrator Bizzu'
      (exit), 'Retenção Bizzu' (exit), 'Indicação Bizzu' (exit) e a campanha do
      plano ANUAL ATIVO (docs/campanhas/mensagens-anuais-ativos.md):
      'Check-in Bizzu' (exit), 'Renovação Anual Bizzu' (exit) e 'Novidade Bizzu' (nps)
  - N contatos com opt_in=True (--phones)

100% async (SQLAlchemy 2.0: AsyncSession + select()). Toda query filtra por chave
única (slug / (org_id, name) / (org_id, phone)) ANTES de inserir, então rodar o
script 2x não duplica nada.

Como rodar (precisa de DATABASE_URL = postgresql+asyncpg://...):

    # Linha de comando (PowerShell):
    $env:PYTHONUTF8=1
    $env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
    python scripts/seed_bizzu.py

    # Telefones customizados (apenas dígitos: DDI+DDD+numero):
    python scripts/seed_bizzu.py --phones 5531999998888,5531888887777

Sem DATABASE_URL o script imprime instruções e sai com código != 0 (não tenta
conectar em banco nenhum).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

# Permite rodar standalone (`python scripts/seed_bizzu.py`) sem instalar o pacote:
# garante que a raiz do projeto esteja no sys.path para `import app...` resolver.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Carrega .env (se python-dotenv estiver instalado) ANTES de importar app.config /
# app.db, pois ambos avaliam as variáveis de ambiente no momento do import.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except Exception:  # python-dotenv ausente ou .env inexistente: seguimos com o ambiente atual.
    pass


# --- Dados do seed -------------------------------------------------------------

ORG_SLUG = "bizzu"
ORG_NAME = "Bizzu"

SURVEYS = [
    {
        # NPS de disparo MANUAL/seletivo (perfis ativo_silencioso/ativo_passivo).
        # Variação ON-BRAND do anual (docs/campanhas/mensagens-anuais-ativos.md):
        # follow-up NEUTRO de propósito — não comemora antes de saber a nota (era um
        # problema real apontado pelo dono). O "Massa! 🙌" cego ao bucket saiu daqui;
        # em runtime o resolver ainda adapta o tom à nota via SurveyBrain._adaptive_reason.
        "name": "NPS Bizzu",
        "type": "nps",
        "trigger_event": None,
        "questions": [
            {
                "key": "nps",
                "kind": "nps",
                "text": (
                    "queria saber como tá sua experiência com o Bizzu na sua rotina de "
                    "estudos. De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo "
                    "concurseiro?"
                ),
            },
            {
                "key": "reason",
                "kind": "open",
                "text": "valeu por responder 🙏 conta pra mim o que pesou nessa nota? (pode mandar em texto)",
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": (
                    "show, anotado aqui. obrigado pela sinceridade, isso ajuda demais a "
                    "deixar o Bizzu melhor pra você."
                ),
            },
        ],
    },
    {
        # Exit survey de churn: disparada pelo POST /api/events/bizzu quando o
        # backend da Bizzu emite 'subscription_cancelled' (EscutaService).
        "name": "Exit Bizzu",
        "type": "exit",
        "trigger_event": "subscription_cancelled",
        "questions": [
            {
                "key": "reason",
                "kind": "open",
                "text": (
                    "vi aqui que você cancelou sua assinatura do Bizzu 😕 "
                    "Pode me contar em uma frase o que pesou na decisão? "
                    "Sua resposta vai direto pro time que constrói o produto."
                ),
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": "Recebido — obrigado pela sinceridade! 💙 Se mudar de ideia, a porta tá sempre aberta.",
            },
        ],
    },
    {
        # CSAT de qualidade do conteúdo do tópico: disparada pelo POST
        # /api/events/bizzu quando o backend da Bizzu emite 'topic_completed'.
        # Decisão consciente: reusa o motor NPS 0-10 (uma escala única em todo
        # o produto — sem parser 1-5).
        "name": "CSAT Tópico Bizzu",
        "type": "nps",
        "trigger_event": "topic_completed",
        "questions": [
            {
                "key": "nps",
                "kind": "nps",
                "text": (
                    "acabou de concluir mais um tópico! 🎯 De 0 a 10, que nota "
                    "você dá pra qualidade do conteúdo (resumo e questões) desse tópico?"
                ),
            },
            {
                "key": "reason",
                "kind": "open",
                "text": "Valeu! O que faria essa nota virar 10? (pode responder em texto)",
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": "Anotado! 💙 Obrigado por ajudar a melhorar o Bizzu — bons estudos!",
            },
        ],
    },
    {
        # NPS in-app ESPELHADO: recebe (ingest) as respostas de NPS já dadas no
        # app Bizzu via POST /api/events/bizzu ('nps_submitted'). ingest_mode=True
        # => o handler registra + classifica (sentimento/tema) e NÃO dispara
        # WhatsApp — evita double-touch com quem já respondeu no app.
        "name": "NPS Bizzu (ingest)",
        "type": "nps",
        "trigger_event": "nps_submitted",
        "ingest_mode": True,
        "questions": [
            {
                "key": "nps",
                "kind": "nps",
                "text": "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?",
            },
            {
                "key": "reason",
                "kind": "open",
                "text": "Massa! 🙌 Por quê?",
            },
        ],
    },
    {
        # CSAT pós-atendimento: disparada pelo POST /api/events/bizzu quando o backend
        # emite 'ticket_resolved' (suporte resolveu um ticket). Reusa o motor NPS 0-10.
        "name": "CSAT Atendimento Bizzu",
        "type": "nps",
        "trigger_event": "ticket_resolved",
        "questions": [
            {
                "key": "nps",
                "kind": "nps",
                "text": (
                    "vi que seu atendimento com o suporte do Bizzu foi resolvido 🙌 De 0 a 10, "
                    "o quanto você ficou satisfeito com o atendimento?"
                ),
            },
            {
                "key": "reason",
                "kind": "open",
                "text": "Valeu! O que faria essa nota ser 10? (pode responder em texto)",
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": "Anotado! 💙 Obrigado pelo retorno — qualquer coisa, é só chamar.",
            },
        ],
    },
    {
        # CSAT de onboarding: disparo MANUAL/seletivo (por perfil 'ativo_recente'
        # via scripts/dispatch_by_profile.py). trigger_event None = sem automação.
        "name": "CSAT Onboarding Bizzu",
        "type": "nps",
        "trigger_event": None,
        "questions": [
            {
                "key": "nps",
                "kind": "nps",
                "text": (
                    "vi que você começou no Bizzu faz pouco tempo 👋 De 0 a 10, "
                    "como tá sendo a experiência até agora?"
                ),
            },
            {
                "key": "reason",
                "kind": "open",
                "text": "Valeu! O que faria essa nota subir? (pode responder em texto)",
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": "Anotado! 💙 Qualquer dúvida nos primeiros passos, é só chamar. Bons estudos!",
            },
        ],
    },
    {
        # Escuta de detrator: disparo MANUAL/seletivo (perfil 'ativo_em_risco').
        # type 'exit' = 1 pergunta aberta + 'thanks' (sem etapa de nota).
        "name": "Escuta de Detrator Bizzu",
        "type": "exit",
        "trigger_event": None,
        "questions": [
            {
                "key": "reason",
                "kind": "open",
                "text": (
                    "vi que sua experiência com o Bizzu não tá sendo a melhor 😕 "
                    "Pode me contar, em uma frase, o que mais tá te incomodando? "
                    "Quero levar direto pro time pra gente resolver."
                ),
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": (
                    "Recebido — obrigado por confiar e me contar. 💙 "
                    "Vou levar isso pro time e a gente te dá um retorno."
                ),
            },
        ],
    },
    {
        # Retenção: disparo MANUAL/seletivo (perfil 'vai_expirar').
        "name": "Retenção Bizzu",
        "type": "exit",
        "trigger_event": None,
        "questions": [
            {
                "key": "reason",
                "kind": "open",
                "text": (
                    "vi que seu acesso ao Bizzu tá quase no fim ⏳ Antes de ir, posso "
                    "te perguntar: tem alguma coisa que faria você continuar com a gente? "
                    "Pode falar com sinceridade."
                ),
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": (
                    "Valeu por compartilhar! 💙 Vou levar isso pro time. "
                    "Seu acesso continua ativo até o fim do período."
                ),
            },
        ],
    },
    {
        # Indicação/depoimento: disparo MANUAL/seletivo (perfis promotor/fiel/embaixador).
        "name": "Indicação Bizzu",
        "type": "exit",
        "trigger_event": None,
        "questions": [
            {
                "key": "reason",
                "kind": "open",
                "text": (
                    "que bom te ver curtindo o Bizzu! 🙌 Posso te pedir um favor rápido? "
                    "Me conta em uma frase o que mais te ajudou nos estudos — e, se topar, "
                    "posso usar como depoimento (só com seu ok). Se quiser indicar pra um "
                    "amigo concurseiro, manda o contato. 💙"
                ),
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": "Muito obrigado! 💙 Isso ajuda demais a gente a crescer. Bons estudos!",
            },
        ],
    },
    {
        # Relacionamento / Check-in: disparo MANUAL/seletivo (perfis ativo_fiel/embaixador,
        # alternando com 'Indicação Bizzu' por cooldown — ver profile_surveys.py).
        # Periódico (60-90 dias) com o anual em dia, fora de janela de NPS/renovação:
        # só um oi + ouvir. type 'exit' = 1 pergunta aberta + 'thanks'.
        # Textos on-brand de docs/campanhas/mensagens-anuais-ativos.md (variação A).
        "name": "Check-in Bizzu",
        "type": "exit",
        "trigger_event": None,
        "questions": [
            {
                "key": "reason",
                "kind": "open",
                "text": (
                    "passando só pra saber como tão indo seus estudos com o Bizzu 😊 me "
                    "conta: tem rolado algo que eu possa levar pro time pra deixar sua "
                    "rotina ainda melhor?"
                ),
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": (
                    "valeu demais por compartilhar! adoro saber como você tá. qualquer "
                    "coisa que precisar, é só chamar aqui que eu levo pro time. bons "
                    "estudos! 🙌"
                ),
            },
        ],
    },
    {
        # Renovação do plano anual: disparo MANUAL/seletivo (anuais ativos com
        # currentPeriodEnd em ~15-30 dias). Tom de continuidade positiva — NUNCA
        # "antes de ir" nem urgência. Coordenar p/ NÃO disparar no mesmo dia da
        # cobrança automática. type 'exit'. Textos on-brand (variação A) do md.
        "name": "Renovação Anual Bizzu",
        "type": "exit",
        "trigger_event": None,
        "questions": [
            {
                "key": "reason",
                "kind": "open",
                "text": (
                    "fez quase um ano que você começou essa jornada com a gente 🎯 bora "
                    "pra mais um ciclo de estudos juntos? me conta: o que o Bizzu mais te "
                    "ajudou a destravar até aqui?"
                ),
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": (
                    "valeu demais por seguir nessa com a gente 💙 bons estudos e conta "
                    "comigo sempre que precisar!"
                ),
            },
        ],
    },
    {
        # Novidade / nova feature: disparo MANUAL/seletivo (todos os anuais ativos).
        # Anuncia uma feature e mede a reação — type 'nps' (0-10 = quanto animou) +
        # porquê + thanks. Variação A (Raio-X da Prova) do md; a variação C usa o
        # placeholder {novidade}, resolvido por scripts/dispatch_by_profile.py.
        "name": "Novidade Bizzu",
        "type": "nps",
        "trigger_event": None,
        "questions": [
            {
                "key": "nps",
                "kind": "nps",
                "text": (
                    "saiu novidade no Bizzu e eu já pensei em você 👀 acabamos de soltar o "
                    "Raio-X da Prova, que mostra em ranking quais tópicos do seu edital "
                    "mais caem pra você atacar primeiro. De 0 a 10, o quanto isso te "
                    "ajudaria hoje?"
                ),
            },
            {
                "key": "reason",
                "kind": "open",
                "text": "boa! me conta: o que você mais quer que o Bizzu te ajude a resolver agora nos estudos?",
            },
            {
                "key": "thanks",
                "kind": "thanks",
                "text": (
                    "anotado 💙 obrigado pelo retorno, isso ajuda a gente a priorizar o "
                    "que constrói de novo. bons estudos!"
                ),
            },
        ],
    },
]
SURVEY_STATUS = "active"

# Política do projeto (07/06): SEM dados mockados. O seed não cria mais contatos
# fictícios — telefones reais via --phones são obrigatórios (org+survey seguem ok).


def _digits_only(value: str) -> str:
    """Mantém apenas dígitos (DDI+DDD+numero), descartando +, espaços, hífens etc."""
    return re.sub(r"\D", "", value or "")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed idempotente do tenant-piloto Bizzu (org + survey NPS + contatos).",
    )
    parser.add_argument(
        "--phones",
        type=str,
        default=None,
        help=(
            "Lista de telefones REAIS separados por vírgula (apenas dígitos: "
            "DDI+DDD+numero), ex.: 5531999998888,5531888887777. Obrigatório para "
            "criar contatos — sem ele o seed cria/garante apenas org + survey."
        ),
    )
    return parser.parse_args(argv)


def _contacts_from_args(phones_arg: str | None) -> list[dict[str, str | None]]:
    """Monta a lista de contatos a partir do --phones (sem fallback fictício)."""
    if not phones_arg:
        return []

    contacts: list[dict[str, str | None]] = []
    for i, raw in enumerate(phones_arg.split(","), start=1):
        phone = _digits_only(raw)
        if not phone:
            continue
        contacts.append({"phone": phone, "name": f"Contato {i}"})
    return contacts


# --- Lógica de seed (async, SQLAlchemy 2.0) ------------------------------------


async def _get_or_create_org(session, name: str, slug: str):
    """get-or-create por slug (unique)."""
    from sqlalchemy import select
    from app.models.core import Organization

    existing = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    org = Organization(slug=slug, name=name, settings={})
    session.add(org)
    # flush para obter o id gerado (default=uuid.uuid4) antes de usá-lo nas FKs.
    await session.flush()
    return org, True


async def _get_or_create_survey(session, organization_id, spec: dict):
    """get-or-create por (organization_id, name) (unique).

    Se a survey já existe mas ainda não tem trigger_event e o spec define um,
    atualiza só esse campo (idempotente p/ bases criadas antes da migration).
    """
    from sqlalchemy import select
    from app.models.survey import Survey

    existing = (
        await session.execute(
            select(Survey).where(
                Survey.organization_id == organization_id,
                Survey.name == spec["name"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        changed = False
        if spec.get("trigger_event") and existing.trigger_event is None:
            existing.trigger_event = spec["trigger_event"]
            changed = True
        if spec.get("ingest_mode") and not existing.ingest_mode:
            existing.ingest_mode = spec["ingest_mode"]
            changed = True
        if changed:
            await session.flush()
        return existing, False

    survey = Survey(
        organization_id=organization_id,
        name=spec["name"],
        type=spec["type"],
        status=SURVEY_STATUS,
        questions=spec["questions"],
        trigger_event=spec.get("trigger_event"),
        ingest_mode=spec.get("ingest_mode", False),
    )
    session.add(survey)
    await session.flush()
    return survey, True


async def _get_or_create_contact(session, organization_id, phone: str, name: str | None):
    """get-or-create por (organization_id, phone) (unique). Sempre com opt_in=True."""
    from sqlalchemy import select
    from app.models.core import Contact

    existing = (
        await session.execute(
            select(Contact).where(
                Contact.organization_id == organization_id,
                Contact.phone == phone,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    contact = Contact(
        organization_id=organization_id,
        phone=phone,
        name=name,
        opt_in=True,
        profile_data={},
    )
    session.add(contact)
    await session.flush()
    return contact, True


async def seed(contacts_spec: list[dict[str, str | None]]) -> int:
    """Executa o seed dentro de uma única transação. Retorna o exit code."""
    # Import tardio: db.py avalia SessionLocal no import a partir de DATABASE_URL.
    from app.db import SessionLocal

    if SessionLocal is None:
        print(
            "ERRO: DATABASE_URL não configurada — não há engine de banco.\n"
            "\n"
            "Defina a variável de ambiente (postgresql+asyncpg) e rode de novo. Ex.:\n"
            '  PowerShell:  $env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"\n'
            "  bash:        export DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db\n"
            "\n"
            "Você também pode criar um arquivo .env na raiz (veja .env.example) — ele é\n"
            "carregado automaticamente se python-dotenv estiver instalado.",
            file=sys.stderr,
        )
        return 1

    async with SessionLocal() as session:
        org, org_created = await _get_or_create_org(session, ORG_NAME, ORG_SLUG)

        survey_results: list[tuple[object, bool]] = []
        for survey_spec in SURVEYS:
            survey, created = await _get_or_create_survey(session, org.id, survey_spec)
            survey_results.append((survey, created))

        contact_results: list[tuple[object, bool]] = []
        for spec in contacts_spec:
            phone = str(spec["phone"])
            name = spec.get("name")
            contact, created = await _get_or_create_contact(session, org.id, phone, name)
            contact_results.append((contact, created))

        await session.commit()

    # --- Resumo --------------------------------------------------------------
    print("=== Seed Bizzu concluído ===")
    print(
        f"Organization: id={org.id} slug={org.slug!r} name={org.name!r} "
        f"[{'criada' if org_created else 'existente'}]"
    )
    for survey, survey_created in survey_results:
        print(
            f"Survey:       id={survey.id} name={survey.name!r} type={survey.type!r} "
            f"trigger_event={survey.trigger_event!r} status={survey.status!r} "
            f"[{'criado' if survey_created else 'existente'}] "
            f"({len(survey.questions)} perguntas)"
        )
    print(f"Contatos ({len(contact_results)}):")
    for contact, created in contact_results:
        marca = "criado" if created else "existente"
        print(
            f"  - id={contact.id} phone={contact.phone} name={contact.name!r} "
            f"opt_in={contact.opt_in} [{marca}]"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    contacts_spec = _contacts_from_args(args.phones)
    if args.phones is not None and not contacts_spec:
        print(
            "ERRO: nenhum telefone válido em --phones (use apenas dígitos: DDI+DDD+numero).",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(seed(contacts_spec))


if __name__ == "__main__":
    raise SystemExit(main())
