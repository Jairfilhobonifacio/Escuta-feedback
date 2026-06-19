"""VoCAgentOrchestrator (loop de tool-calling) + chat_with_tools + regressão do resolver.

Sem rede, sem Groq real:
- O orchestrator roda com um FAKE de GroqLLM cujo `chat_with_tools` é roteirizado
  (devolve tool_calls numa rodada e texto final na seguinte).
- `chat_with_tools` REAL é exercitado quanto ao contrato never-raises: circuito aberto
  e payload malformado devolvem resultado neutro (sem tool calls), nunca lançam.
- Regressão do resolver: com a flag voc_agent_enabled OFF (default), `resolve()` NÃO
  toca o agente VoC (o `chat_with_tools` do llm nunca é chamado); e `_run_voc_agent`
  chamado direto conduz o turno quando o agente conclui.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.domain.survey.constants import STATUS_AWAITING_REASON, STATUS_SENT  # noqa: E402
from app.domain.survey.parsers import nps_bucket  # noqa: E402
from app.domain.survey.resolver import SurveyContextResolver  # noqa: E402
from app.domain.voc.orchestrator import VoCAgentOrchestrator  # noqa: E402
from app.domain.voc.registry import VoCToolRegistry  # noqa: E402
from app.models.core import Contact, Organization  # noqa: E402
from app.models.survey import Message, Survey, SurveyResponse, SurveyRun  # noqa: E402
from app.services.llm import ChatToolResult, GroqLLM, ToolCall, _UpstreamError  # noqa: E402
from app.services.llm import reset_default_breaker  # noqa: E402


def _now():
    return datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------------
# Fake do GroqLLM para o orchestrator: chat_with_tools roteirizado.
# ---------------------------------------------------------------------------------


class FakeToolsLLM:
    """Devolve uma sequência de ChatToolResult por chamada de `chat_with_tools`.

    Conta as chamadas e guarda os `messages`/`tools` da última, para asserts (ex.:
    provar que os resultados das tools voltaram ao modelo).
    """

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.last_messages = None
        self.last_tools = None

    async def chat_with_tools(self, messages, tools, **kwargs):
        self.calls += 1
        self.last_messages = messages
        self.last_tools = tools
        if self._results:
            return self._results.pop(0)
        # Esgotou o roteiro: resposta final vazia (encerra o loop com segurança).
        return ChatToolResult(message={"role": "assistant", "content": ""}, tool_calls=[])


def _simple_registry(record):
    """Registry com uma tool 'eco' que registra os args vistos em `record`."""
    reg = VoCToolRegistry()

    async def _eco(args):
        record.append(args)
        return {"ok": True, "echo": args}

    reg.register(
        "eco",
        "ecoa os argumentos",
        {"type": "object", "properties": {"v": {"type": "string"}}, "required": []},
        _eco,
    )
    return reg


@pytest.mark.asyncio
async def test_orchestrator_executa_tool_e_volta_ao_modelo():
    record: list = []
    reg = _simple_registry(record)
    # Rodada 1: o modelo pede a tool 'eco'. Rodada 2: responde texto final.
    llm = FakeToolsLLM(
        [
            ChatToolResult(
                message={"role": "assistant", "content": None, "tool_calls": [{"id": "t1", "function": {"name": "eco", "arguments": "{\"v\": \"abc\"}"}}]},
                tool_calls=[ToolCall(id="t1", name="eco", arguments={"v": "abc"})],
            ),
            ChatToolResult(message={"role": "assistant", "content": "Pronto!"}, tool_calls=[]),
        ]
    )
    orch = VoCAgentOrchestrator(llm, reg, max_iterations=5)

    result = await orch.run("faz aí", history=[])

    assert result.completed is True
    assert result.reply == "Pronto!"
    assert result.tool_calls_made == ["eco"]
    assert record == [{"v": "abc"}]
    assert llm.calls == 2
    # O resultado da tool voltou ao modelo como mensagem role="tool".
    tool_msgs = [m for m in llm.last_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "t1"
    assert tool_msgs[0]["name"] == "eco"


@pytest.mark.asyncio
async def test_orchestrator_sem_tool_calls_responde_direto():
    reg = _simple_registry([])
    llm = FakeToolsLLM([ChatToolResult(message={"role": "assistant", "content": "Oi!"}, tool_calls=[])])
    orch = VoCAgentOrchestrator(llm, reg)

    result = await orch.run("oi", history=[])
    assert result.completed is True
    assert result.reply == "Oi!"
    assert result.tool_calls_made == []
    assert result.iterations == 1


@pytest.mark.asyncio
async def test_orchestrator_teto_de_iteracoes():
    """Modelo que SEMPRE pede tool: o loop para no teto, sem completar."""
    record: list = []
    reg = _simple_registry(record)
    sempre_pede = ChatToolResult(
        message={"role": "assistant", "content": None, "tool_calls": [{"id": "t", "function": {"name": "eco", "arguments": "{}"}}]},
        tool_calls=[ToolCall(id="t", name="eco", arguments={})],
    )
    # Roteiro infinito: repete o "pede tool" muito além do teto.
    llm = FakeToolsLLM([sempre_pede] * 50)
    orch = VoCAgentOrchestrator(llm, reg, max_iterations=3)

    result = await orch.run("loop", history=[])
    assert result.completed is False
    assert result.iterations == 3
    assert len(result.tool_calls_made) == 3  # uma tool por iteração


@pytest.mark.asyncio
async def test_orchestrator_history_vira_messages():
    reg = _simple_registry([])
    llm = FakeToolsLLM([ChatToolResult(message={"role": "assistant", "content": "ok"}, tool_calls=[])])
    orch = VoCAgentOrchestrator(llm, reg)

    history = [("inbound", "oi"), ("outbound", "olá, tudo bem?")]
    await orch.run("preciso de ajuda", history=history)

    roles = [(m["role"], m.get("content")) for m in llm.last_messages]
    assert roles[0][0] == "system"
    assert ("user", "oi") in roles
    assert ("assistant", "olá, tudo bem?") in roles
    assert ("user", "preciso de ajuda") in roles


@pytest.mark.asyncio
async def test_orchestrator_nao_duplica_mensagem_atual():
    """Se a última do histórico JÁ é a mensagem atual (inbound), não duplica."""
    reg = _simple_registry([])
    llm = FakeToolsLLM([ChatToolResult(message={"role": "assistant", "content": "ok"}, tool_calls=[])])
    orch = VoCAgentOrchestrator(llm, reg)

    await orch.run("é essa", history=[("inbound", "é essa")])
    user_msgs = [m for m in llm.last_messages if m["role"] == "user" and m["content"] == "é essa"]
    assert len(user_msgs) == 1


@pytest.mark.asyncio
async def test_orchestrator_llm_que_lanca_nao_derruba():
    """Mesmo que o LLM fake levante (não deveria, mas...), run() é à prova de queda."""
    reg = _simple_registry([])

    class BoomLLM:
        async def chat_with_tools(self, messages, tools, **kwargs):
            raise RuntimeError("falha do provedor")

    orch = VoCAgentOrchestrator(BoomLLM(), reg)
    result = await orch.run("oi", history=[])
    assert result.completed is False
    assert result.reply == ""


# ---------------------------------------------------------------------------------
# chat_with_tools REAL — contrato never-raises (sem rede).
# ---------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_breaker():
    reset_default_breaker()
    yield
    reset_default_breaker()


@pytest.mark.asyncio
async def test_chat_with_tools_parseia_tool_calls(monkeypatch):
    async def fake_post_message(self, model, payload):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "abc", "type": "function", "function": {"name": "criar_tarefa", "arguments": "{\"title\": \"X\"}"}}
            ],
        }

    monkeypatch.setattr(GroqLLM, "_post_message", fake_post_message)
    llm = GroqLLM(api_key="x", model="m")
    res = await llm.chat_with_tools([{"role": "user", "content": "oi"}], [])
    assert res.has_tool_calls is True
    assert res.tool_calls[0].name == "criar_tarefa"
    assert res.tool_calls[0].arguments == {"title": "X"}
    assert res.tool_calls[0].id == "abc"


@pytest.mark.asyncio
async def test_chat_with_tools_arguments_invalidos_viram_dict_vazio(monkeypatch):
    async def fake_post_message(self, model, payload):
        return {
            "role": "assistant",
            "tool_calls": [{"id": "z", "function": {"name": "t", "arguments": "{nao eh json}"}}],
        }

    monkeypatch.setattr(GroqLLM, "_post_message", fake_post_message)
    llm = GroqLLM(api_key="x", model="m")
    res = await llm.chat_with_tools([{"role": "user", "content": "oi"}], [])
    assert res.tool_calls[0].arguments == {}


@pytest.mark.asyncio
async def test_chat_with_tools_sem_tool_calls(monkeypatch):
    async def fake_post_message(self, model, payload):
        return {"role": "assistant", "content": "resposta final"}

    monkeypatch.setattr(GroqLLM, "_post_message", fake_post_message)
    llm = GroqLLM(api_key="x", model="m")
    res = await llm.chat_with_tools([{"role": "user", "content": "oi"}], [])
    assert res.has_tool_calls is False
    assert res.message["content"] == "resposta final"


@pytest.mark.asyncio
async def test_chat_with_tools_falha_real_devolve_neutro(monkeypatch):
    """Erro real (5xx/timeout) → resultado neutro, sem tool calls, sem lançar."""
    async def boom(self, model, payload):
        raise _UpstreamError("HTTP 503")

    monkeypatch.setattr(GroqLLM, "_post_message", boom)
    llm = GroqLLM(api_key="x", model="m", fallback_model=None)
    res = await llm.chat_with_tools([{"role": "user", "content": "oi"}], [])
    assert res.has_tool_calls is False
    assert res.message == {"role": "assistant", "content": ""}


@pytest.mark.asyncio
async def test_chat_with_tools_circuito_aberto_pula_chamada(monkeypatch):
    """Com o circuito ABERTO, nem toca a 'rede' — devolve neutro."""
    chamou = {"n": 0}

    async def conta(self, model, payload):
        chamou["n"] += 1
        raise _UpstreamError("HTTP 500")

    monkeypatch.setattr(GroqLLM, "_post_message", conta)
    llm = GroqLLM(api_key="x", model="m", fallback_model=None)
    # Abre o circuito (threshold do breaker padrão).
    from app.services import llm as llm_mod

    for _ in range(llm_mod._BREAKER_FAILURE_THRESHOLD):
        await llm.chat_with_tools([{"role": "user", "content": "oi"}], [])
    n_apos_abrir = chamou["n"]
    # Próxima chamada: circuito aberto → não incrementa.
    res = await llm.chat_with_tools([{"role": "user", "content": "oi"}], [])
    assert res.has_tool_calls is False
    assert chamou["n"] == n_apos_abrir


# ---------------------------------------------------------------------------------
# Regressão do resolver: flag OFF = não toca o VoC; _run_voc_agent direto conduz.
# ---------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def org(session):
    o = Organization(slug="bizzu", name="Bizzu", settings={"owner_phone": "5511999990000"})
    session.add(o)
    await session.commit()
    return o


@pytest_asyncio.fixture
async def contact(session, org):
    c = Contact(organization_id=org.id, phone="5524998365809", name="Jair", opt_in=True, profile_data={})
    session.add(c)
    await session.commit()
    return c


async def _make_pending(session, org, contact, *, status, score=None):
    survey = Survey(
        organization_id=org.id, name="NPS Bizzu", type="nps", status="active",
        questions=[
            {"key": "nps", "kind": "nps", "text": "De 0 a 10?"},
            {"key": "reason", "kind": "open", "text": "Por quê?"},
            {"key": "thanks", "kind": "thanks", "text": "Valeu!"},
        ],
    )
    session.add(survey)
    await session.flush()
    run = SurveyRun(survey_id=survey.id, organization_id=org.id, trigger="t", status="running")
    session.add(run)
    await session.flush()
    resp = SurveyResponse(
        survey_run_id=run.id, contact_id=contact.id, organization_id=org.id,
        status=status, answer_score=score, nps_bucket=nps_bucket(score),
        sent_at=datetime.now(timezone.utc),  # recente: dentro da janela de 24h do resolver (não data fixa, que expira)
    )
    session.add(resp)
    await session.commit()
    return survey, resp


class _SpyBrain:
    """Brain mínimo cujo `.llm` registra se chat_with_tools foi chamado.

    Implementa só o que o caminho determinístico do resolver toca quando precisa: aqui
    forçamos o resolver a NÃO entrar no Survey Agent (basta a flag survey_agent_enabled
    estar OFF, que é o default) e medimos se o VoC foi acionado pela flag voc.
    """

    class _LLM:
        def __init__(self):
            self.tool_calls_invoked = 0

        async def chat_with_tools(self, messages, tools, **kwargs):
            self.tool_calls_invoked += 1
            return ChatToolResult(message={"role": "assistant", "content": "X"}, tool_calls=[])

    def __init__(self):
        self.llm = self._LLM()

    # O caminho determinístico (decide_next) NÃO usa o brain p/ uma nota válida; mas
    # interpret_reply pode ser chamado se a nota falhar. Damos um stub seguro.
    async def interpret_reply(self, question_text, message):
        return None


@pytest.mark.asyncio
async def test_resolver_flag_off_nao_toca_o_voc(session, org, contact):
    """Default (voc_agent_enabled OFF): resolve() processa a nota pelo fluxo de sempre
    e NUNCA chama chat_with_tools (o agente VoC fica dormente)."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_SENT)
    brain = _SpyBrain()
    resolver = SurveyContextResolver(session, org.id, brain=brain)

    reply = await resolver.resolve(contact.id, "9")  # nota válida → caminho determinístico

    assert reply is not None
    assert brain.llm.tool_calls_invoked == 0  # VoC não foi acionado
    await session.refresh(resp)
    assert resp.answer_score == 9  # a máquina de estados processou normalmente
    # ai_meta não foi marcado pelo VoC.
    assert "voc_agent" not in (resp.ai_meta or {})


@pytest.mark.asyncio
async def test_run_voc_agent_direto_conduz_turno(session, org, contact):
    """Chamando _run_voc_agent diretamente (sem depender da flag frozen): quando o
    agente conclui com texto, devolve uma SurveyReply e marca ai_meta['voc_agent']."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=8)

    # Brain cujo .llm devolve direto um texto final (sem tools) → agente conclui.
    class _Brain:
        class _LLM:
            async def chat_with_tools(self, messages, tools, **kwargs):
                return ChatToolResult(
                    message={"role": "assistant", "content": "Obrigado pelo retorno!"}, tool_calls=[]
                )

        def __init__(self):
            self.llm = self._LLM()

    resolver = SurveyContextResolver(session, org.id, brain=_Brain())
    reply = await resolver._run_voc_agent(resp, contact.id, "valeu", _now())

    assert reply is not None
    assert reply.text == "Obrigado pelo retorno!"
    await session.refresh(resp)
    assert (resp.ai_meta or {}).get("voc_agent") is True


@pytest.mark.asyncio
async def test_run_voc_agent_reply_vazia_cai_no_fallback(session, org, contact):
    """Agente que não conclui com texto → _run_voc_agent devolve None (fallback)."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=8)

    class _Brain:
        class _LLM:
            async def chat_with_tools(self, messages, tools, **kwargs):
                return ChatToolResult(message={"role": "assistant", "content": ""}, tool_calls=[])

        def __init__(self):
            self.llm = self._LLM()

    resolver = SurveyContextResolver(session, org.id, brain=_Brain())
    reply = await resolver._run_voc_agent(resp, contact.id, "valeu", _now())
    assert reply is None


@pytest.mark.asyncio
async def test_run_voc_agent_executa_tool_e_marca_meta(session, org, contact):
    """O agente VoC chama uma tool real (criar_tarefa) e depois responde — a tarefa é
    criada e ai_meta registra a tool usada."""
    survey, resp = await _make_pending(session, org, contact, status=STATUS_AWAITING_REASON, score=2)

    class _Brain:
        class _LLM:
            def __init__(self):
                self.n = 0

            async def chat_with_tools(self, messages, tools, **kwargs):
                self.n += 1
                if self.n == 1:
                    return ChatToolResult(
                        message={"role": "assistant", "content": None, "tool_calls": [
                            {"id": "t1", "function": {"name": "criar_tarefa", "arguments": "{\"title\": \"Ligar para Jair\"}"}}
                        ]},
                        tool_calls=[ToolCall(id="t1", name="criar_tarefa", arguments={"title": "Ligar para Jair"})],
                    )
                return ChatToolResult(message={"role": "assistant", "content": "Criei a tarefa."}, tool_calls=[])

        def __init__(self):
            self.llm = self._LLM()

    from app.models.playbook import CsTask

    resolver = SurveyContextResolver(session, org.id, brain=_Brain())
    reply = await resolver._run_voc_agent(resp, contact.id, "péssimo", _now())

    assert reply is not None and reply.text == "Criei a tarefa."
    tasks = (await session.execute(select(CsTask).where(CsTask.organization_id == org.id))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].title == "Ligar para Jair"
    await session.refresh(resp)
    assert (resp.ai_meta or {}).get("voc_tools") == ["criar_tarefa"]
