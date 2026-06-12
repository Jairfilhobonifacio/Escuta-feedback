"""Testes do SurveyBrain + integração com o SurveyContextResolver.

LLM dublado (FakeLLM devolve JSONs prontos) — nenhum teste toca a Groq.
Invariante central: com brain=None OU LLM falhando, o comportamento é
byte-a-byte o da Fase 0 (retry determinístico) — IA nunca quebra o fluxo.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey.brain import OPT_OUT_CONFIRM_MSG, BrainIntent, FeedbackTags, SurveyBrain  # noqa: E402
from app.domain.survey.constants import (  # noqa: E402
    STATUS_AWAITING_REASON,
    STATUS_CLOSED,
    STATUS_EXPIRED,
    STATUS_SENT,
)
from app.domain.survey.dispatcher import SurveyDispatcher  # noqa: E402
from app.domain.survey.resolver import DEFAULT_RETRY_MSG, SurveyContextResolver  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Survey, SurveyResponse  # noqa: E402
from sqlalchemy import select  # noqa: E402
from tests.fakes import FakeMessagingService  # noqa: E402


class FakeLLM:
    """Dublê de GroqLLM: devolve a sequência de JSONs configurada.

    A pergunta de motivo adaptada à nota (compose_reason_prompt) NÃO faz parte da
    sequência testada aqui: é ignorada (None ⇒ fallback no texto fixo) sem consumir
    a fila, para não desalinhar os testes que assumem a ordem das chamadas.
    """

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, system: str, user: str):
        self.calls.append((system, user))
        if "MOTIVO da nota" in system:
            return None
        if not self.responses:
            return None
        return self.responses.pop(0)


class BoomLLM:
    async def chat_json(self, system: str, user: str):
        raise RuntimeError("boom")


# --- helpers de cenário ----------------------------------------------------------


async def _setup_pending_nps(session) -> tuple[Organization, Contact, SurveyResponse]:
    """Org + survey NPS + contato com pergunta enviada (status sent)."""
    org = Organization(slug="bizzu", name="Bizzu", settings={})
    session.add(org)
    await session.flush()
    survey = Survey(
        organization_id=org.id,
        name="NPS Bizzu",
        type="nps",
        status="active",
        questions=[
            {"key": "nps", "kind": "nps", "text": "De 0 a 10, recomendaria o Bizzu?"},
            {"key": "reason", "kind": "open", "text": "Por quê?"},
        ],
    )
    contact = Contact(organization_id=org.id, phone="5524998365809", name="Jair", opt_in=True, profile_data={})
    session.add_all([survey, contact])
    await session.flush()

    dispatcher = SurveyDispatcher(session, org.id, FakeMessagingService())
    await dispatcher.dispatch(survey, [contact])
    await session.commit()

    resp = (
        await session.execute(select(SurveyResponse).where(SurveyResponse.contact_id == contact.id))
    ).scalar_one()
    return org, contact, resp


# --- unidade: SurveyBrain valida o que vem do LLM ---------------------------------


@pytest.mark.asyncio
async def test_interpret_score_natural():
    brain = SurveyBrain(FakeLLM({"kind": "score", "score": 8, "reply": None}))
    intent = await brain.interpret_reply("De 0 a 10?", "ah eu acho que uns oito")
    assert intent == BrainIntent(kind="score", score=8, reply=None)


@pytest.mark.asyncio
async def test_interpret_score_invalido_vira_none():
    brain = SurveyBrain(FakeLLM({"kind": "score", "score": 47, "reply": None}))
    assert await brain.interpret_reply("De 0 a 10?", "quarenta e sete") is None
    brain2 = SurveyBrain(FakeLLM({"kind": "score", "score": "oito", "reply": None}))
    assert await brain2.interpret_reply("De 0 a 10?", "oito") is None


@pytest.mark.asyncio
async def test_interpret_kind_desconhecido_ou_llm_off():
    assert await SurveyBrain(FakeLLM({"kind": "huh"})).interpret_reply("q", "m") is None
    assert await SurveyBrain(FakeLLM(None)).interpret_reply("q", "m") is None


@pytest.mark.asyncio
async def test_interpret_question_trunca_e_exige_reply():
    longa = {"kind": "question", "score": None, "reply": "x" * 1000}
    intent = await SurveyBrain(FakeLLM(longa)).interpret_reply("q", "como cancelo?")
    assert intent.kind == "question" and len(intent.reply) == 600
    sem_reply = {"kind": "question", "score": None, "reply": None}
    assert await SurveyBrain(FakeLLM(sem_reply)).interpret_reply("q", "?") is None


@pytest.mark.asyncio
async def test_classify_valida_enums_e_limita_temas():
    ok = {"sentiment": "negativo", "themes": ["Preço", " suporte ", "ux", "extra4"], "urgency": "alta"}
    tags = await SurveyBrain(FakeLLM(ok)).classify_feedback("caro demais", 3, "NPS")
    assert tags == FeedbackTags(sentiment="negativo", themes=["preço", "suporte", "ux"], urgency="alta")

    ruim = {"sentiment": "meh", "themes": [], "urgency": "alta"}
    assert await SurveyBrain(FakeLLM(ruim)).classify_feedback("x", None, "NPS") is None


# --- integração: resolver com brain ------------------------------------------------


@pytest.mark.asyncio
async def test_score_em_linguagem_natural_avanca_fluxo(session):
    org, contact, resp = await _setup_pending_nps(session)
    fake = FakeLLM({"kind": "score", "score": 9, "reply": None})
    brain = SurveyBrain(fake)
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    # Sem dígito nem número por extenso: o parser determinístico NÃO resolve
    # ("nove"/"9" ele já pega sozinho — ver parsers._WORDS); aqui é semântica pura.
    reply = await resolver.resolve(contact.id, "cara, gostei demais — recomendo com certeza!")
    await session.commit()

    # 2 consultas ao brain: interpreta a nota semântica + compõe o follow-up adaptativo.
    assert len(fake.calls) == 2
    assert "INTENÇÃO" in fake.calls[0][0]  # a 1ª foi a interpretação da nota
    assert reply is not None and reply.closed is False
    assert reply.text == "Por quê?"  # fallback (FakeLLM não dá 'message' p/ o compose)
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    assert resp.answer_score == 9
    assert resp.nps_bucket == "promoter"
    assert resp.ai_meta.get("score_via_llm") is True


@pytest.mark.asyncio
async def test_opt_out_desliga_contato_e_expira_pendencia(session):
    org, contact, resp = await _setup_pending_nps(session)
    brain = SurveyBrain(FakeLLM({"kind": "opt_out", "score": None, "reply": None}))
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    reply = await resolver.resolve(contact.id, "para de me mandar essas paradas")
    await session.commit()

    assert reply.text == OPT_OUT_CONFIRM_MSG
    assert reply.closed is True
    await session.refresh(resp)
    await session.refresh(contact)
    assert contact.opt_in is False
    assert resp.status == STATUS_EXPIRED
    assert resp.answer_score is None  # não conta em NPS
    assert resp.ai_meta.get("opt_out") is True


@pytest.mark.asyncio
async def test_pergunta_responde_e_mantem_pendente(session):
    org, contact, resp = await _setup_pending_nps(session)
    brain = SurveyBrain(
        FakeLLM({"kind": "question", "score": None, "reply": "Sou o assistente de pesquisas do Bizzu!"})
    )
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    reply = await resolver.resolve(contact.id, "quem é você??")
    await session.commit()

    assert "assistente de pesquisas" in reply.text
    assert "notinha de 0 a 10" in reply.text  # re-engaja
    assert reply.closed is False
    await session.refresh(resp)
    assert resp.status == STATUS_SENT  # pesquisa segue pendente

    # ...e o contato ainda pode responder a nota depois (caminho determinístico)
    reply2 = await resolver.resolve(contact.id, "9")
    await session.commit()
    await session.refresh(resp)
    assert resp.answer_score == 9 and resp.status == STATUS_AWAITING_REASON


@pytest.mark.asyncio
async def test_unclear_e_llm_quebrado_caem_no_retry(session):
    org, contact, resp = await _setup_pending_nps(session)

    # unclear → retry determinístico
    brain = SurveyBrain(FakeLLM({"kind": "unclear", "score": None, "reply": None}))
    reply = await SurveyContextResolver(session, org.id, brain=brain).resolve(contact.id, "👍")
    assert reply.text == DEFAULT_RETRY_MSG

    # LLM explodindo → retry determinístico (exceção engolida)
    reply2 = await SurveyContextResolver(session, org.id, brain=SurveyBrain(BoomLLM())).resolve(
        contact.id, "blz"
    )
    assert reply2.text == DEFAULT_RETRY_MSG

    await session.refresh(resp)
    assert resp.status == STATUS_SENT  # nada mudou


@pytest.mark.asyncio
async def test_fechamento_classifica_feedback(session):
    org, contact, resp = await _setup_pending_nps(session)
    brain = SurveyBrain(
        FakeLLM({"sentiment": "negativo", "themes": ["preço"], "urgency": "media"})
    )
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    # nota pelo caminho determinístico (não consome o FakeLLM)...
    await resolver.resolve(contact.id, "3")
    # ...motivo fecha e classifica
    reply = await resolver.resolve(contact.id, "achei caro demais pelo que entrega")
    await session.commit()

    assert reply.closed is True
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert resp.sentiment == "negativo"
    assert resp.themes == ["preço"]
    assert resp.ai_meta.get("urgency") == "media"


@pytest.mark.asyncio
async def test_sem_brain_comportamento_fase0_intacto(session):
    org, contact, resp = await _setup_pending_nps(session)
    resolver = SurveyContextResolver(session, org.id)  # brain=None

    reply = await resolver.resolve(contact.id, "como assim?")
    assert reply.text == DEFAULT_RETRY_MSG

    await resolver.resolve(contact.id, "10")
    reply2 = await resolver.resolve(contact.id, "tudo ótimo")
    await session.commit()

    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
    assert resp.sentiment is None and resp.themes is None and resp.ai_meta is None


# --- conversa conduzida e sensível à nota ------------------------------------------
#
# Os três problemas que o dono apontou: (1) follow-up FIXO/cego à nota; (2) fecha
# sem aprofundar resposta vaga; (3) não reconcilia nota×texto. Os testes abaixo
# travam o comportamento NOVO no nível do brain (contrato) e na integração
# determinística (resolver), sem tocar a Groq real.


class RoutingLLM:
    """Dublê que roteia por trecho do system prompt e GUARDA o user payload.

    Diferente do FakeLLM (fila por ordem), aqui cada "rota" devolve um JSON fixo —
    o que deixa asseverar que o brain recebeu o contexto certo (nota/sentimento)
    no `user`, provando que o follow-up NÃO é cego à nota.
    """

    def __init__(self, *, reason_prompt=None, followup=None, classify=None):
        self._reason_prompt = reason_prompt
        self._followup = followup
        self._classify = classify
        self.seen: dict[str, str] = {}  # rota -> último user payload

    async def chat_json(self, system: str, user: str, **kwargs):
        if "MOTIVO da nota" in system:
            self.seen["reason_prompt"] = user
            return self._reason_prompt
        if "pergunta de aprofundamento" in system:
            self.seen["followup"] = user
            return self._followup
        if "classifica feedback" in system:
            self.seen["classify"] = user
            return self._classify
        return None


# (1) follow-up por FAIXA DE NOTA — compose_reason_prompt (contrato do brain)


@pytest.mark.asyncio
async def test_reason_prompt_detrator_passa_a_nota_e_devolve_tom_acolhedor():
    llm = RoutingLLM(reason_prompt={"message": "poxa, sinto muito 😕 me conta o que aconteceu?"})
    brain = SurveyBrain(llm)
    msg = await brain.compose_reason_prompt(2, "NPS Bizzu", question_text="De 0 a 10?")
    assert msg == "poxa, sinto muito 😕 me conta o que aconteceu?"
    # a NOTA chegou ao LLM: é isso que torna o follow-up sensível à faixa.
    assert "2" in llm.seen["reason_prompt"]


@pytest.mark.asyncio
async def test_reason_prompt_promotor_devolve_tom_comemorativo():
    llm = RoutingLLM(reason_prompt={"message": "que demais, obrigado! 🎉 o que mais te ajudou?"})
    msg = await SurveyBrain(llm).compose_reason_prompt(10, "NPS Bizzu")
    assert "ajudou" in msg
    assert "10" in llm.seen["reason_prompt"]


@pytest.mark.asyncio
async def test_reason_prompt_sem_nota_nao_chama_llm():
    llm = RoutingLLM(reason_prompt={"message": "nunca deveria sair"})
    assert await SurveyBrain(llm).compose_reason_prompt(None, "NPS") is None
    assert "reason_prompt" not in llm.seen  # score None ⇒ nem consulta o LLM


# (2) aprofundar RESPOSTA VAGA + (3) reconciliar NOTA×TEXTO — decide_followup


@pytest.mark.asyncio
async def test_followup_aprofunda_resposta_vaga_de_detrator():
    llm = RoutingLLM(followup={"should_followup": True, "question": "o que mais te incomodou?"})
    brain = SurveyBrain(llm)
    q = await brain.decide_followup("sei lá", 3, "NPS Bizzu", sentiment="negativo")
    assert q == "o que mais te incomodou?"
    # nota + sentimento foram ao LLM (base p/ decidir aprofundar e reconciliar).
    assert "3" in llm.seen["followup"] and "negativo" in llm.seen["followup"]


@pytest.mark.asyncio
async def test_followup_reconcilia_contradicao_nota_alta_texto_negativo():
    llm = RoutingLLM(followup={
        "should_followup": True,
        "question": "você deu 9 mas comentou que não gostou — me ajuda a entender o que pesou?",
    })
    q = await SurveyBrain(llm).decide_followup(
        "detestei o suporte", 9, "NPS Bizzu", sentiment="negativo"
    )
    assert q is not None and "entender" in q


@pytest.mark.asyncio
async def test_followup_promotor_satisfeito_nao_aprofunda():
    llm = RoutingLLM(followup={"should_followup": False, "question": None})
    assert await SurveyBrain(llm).decide_followup(
        "amei, o app é ótimo", 10, "NPS", sentiment="positivo"
    ) is None


@pytest.mark.asyncio
async def test_followup_questao_vazia_vira_none():
    llm = RoutingLLM(followup={"should_followup": True, "question": "  "})
    assert await SurveyBrain(llm).decide_followup("x", 4, "NPS", sentiment="neutro") is None


# --- integração determinística (survey_agent OFF): follow-up adaptativo + reconciliação


@pytest.mark.asyncio
async def test_resolver_followup_adaptativo_usa_tom_da_nota(session):
    """No caminho determinístico (sem agente), ao receber a nota o resolver NÃO
    manda o 'Massa! 🙌' fixo: chama compose_reason_prompt com a nota e usa o tom
    que voltou (aqui, detrator → acolhimento)."""
    org, contact, resp = await _setup_pending_nps(session)
    llm = RoutingLLM(reason_prompt={"message": "poxa, que pena 😕 me conta o que rolou?"})
    resolver = SurveyContextResolver(session, org.id, brain=SurveyBrain(llm))

    reply = await resolver.resolve(contact.id, "2")  # nota baixa pelo parser
    await session.commit()

    assert reply.text == "poxa, que pena 😕 me conta o que rolou?"  # NÃO é o texto fixo
    assert "2" in llm.seen["reason_prompt"]
    await session.refresh(resp)
    assert resp.answer_score == 2 and resp.nps_bucket == "detractor"
    assert resp.status == STATUS_AWAITING_REASON


@pytest.mark.asyncio
async def test_resolver_reconcilia_nota_alta_com_texto_negativo_antes_de_fechar(session):
    """Promotor (10) cujo MOTIVO é negativo: o classify marca sentiment=negativo,
    então _maybe_followup NÃO fecha direto — faz UMA pergunta de reconciliação."""
    org, contact, resp = await _setup_pending_nps(session)
    llm = RoutingLLM(
        classify={"sentiment": "negativo", "themes": ["suporte"], "urgency": "media"},
        followup={
            "should_followup": True,
            "question": "você deu 10 mas falou do suporte — me conta o que pesou?",
        },
    )
    resolver = SurveyContextResolver(session, org.id, brain=SurveyBrain(llm))

    await resolver.resolve(contact.id, "10")                 # nota (parser)
    reply = await resolver.resolve(contact.id, "o suporte some quando preciso")
    await session.commit()

    # NÃO fechou: reabriu p/ a repergunta de reconciliação.
    assert reply.closed is False
    assert "pesou" in reply.text
    # o sentimento (negativo) chegou ao decide_followup — base da reconciliação.
    assert "negativo" in llm.seen["followup"]
    await session.refresh(resp)
    assert resp.status == STATUS_AWAITING_REASON
    assert (resp.ai_meta or {}).get("follow_up_count") == 1


@pytest.mark.asyncio
async def test_resolver_respeita_limite_de_aprofundamento(session):
    """Anti-loop do caminho determinístico: com follow_up_count já em MAX_FOLLOWUPS,
    o motivo seguinte FECHA (não dispara mais reperguntas), mesmo que o LLM queira."""
    from app.domain.survey.resolver import MAX_FOLLOWUPS

    org, contact, resp = await _setup_pending_nps(session)
    llm = RoutingLLM(
        classify={"sentiment": "negativo", "themes": ["preço"], "urgency": "media"},
        followup={"should_followup": True, "question": "me conta mais?"},
    )
    resolver = SurveyContextResolver(session, org.id, brain=SurveyBrain(llm))

    await resolver.resolve(contact.id, "3")
    # já estourou o limite de aprofundamento neste response
    resp.ai_meta = {**(resp.ai_meta or {}), "follow_up_count": MAX_FOLLOWUPS}
    await session.flush()

    reply = await resolver.resolve(contact.id, "tá caro demais")
    await session.commit()

    assert reply.closed is True   # fechou em vez de reperguntar (respeitou o teto)
    await session.refresh(resp)
    assert resp.status == STATUS_CLOSED
