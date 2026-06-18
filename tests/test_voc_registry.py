"""VoCToolRegistry — registro, exposição no formato Groq e despacho (sem rede, sem LLM).

Cobre o contrato do registry genérico:
- register + as_tools() devolve o formato `tools` do Groq (type/function/parameters);
- dispatch(ToolCall) acha o executor certo e devolve o resultado serializado (string);
- tool desconhecida e executor que LANÇA viram um JSON de erro (never-raises);
- resultado não-string (dict) é serializado para JSON.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.domain.voc.registry import VoCToolRegistry  # noqa: E402
from app.services.llm import ToolCall  # noqa: E402


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
    }


def test_as_tools_formato_groq():
    reg = VoCToolRegistry()

    async def _exec(args):
        return {"ok": True, "echo": args.get("x")}

    reg.register("faz_algo", "descrição da tool", _schema(), _exec)
    tools = reg.as_tools()

    assert len(tools) == 1
    tool = tools[0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "faz_algo"
    assert tool["function"]["description"] == "descrição da tool"
    assert tool["function"]["parameters"] == _schema()
    assert "faz_algo" in reg
    assert reg.names() == ["faz_algo"]
    assert len(reg) == 1


@pytest.mark.asyncio
async def test_dispatch_executa_a_tool_certa():
    reg = VoCToolRegistry()
    seen: dict = {}

    async def _exec(args):
        seen.update(args)
        return {"ok": True, "got": args.get("x")}

    reg.register("faz_algo", "d", _schema(), _exec)
    out = await reg.dispatch(ToolCall(id="c1", name="faz_algo", arguments={"x": "oi"}))

    assert seen == {"x": "oi"}
    parsed = json.loads(out)
    assert parsed == {"ok": True, "got": "oi"}


@pytest.mark.asyncio
async def test_dispatch_tool_desconhecida_vira_erro():
    reg = VoCToolRegistry()
    out = await reg.dispatch(ToolCall(id="c1", name="nao_existe", arguments={}))
    parsed = json.loads(out)
    assert parsed["ok"] is False
    assert "desconhecida" in parsed["error"]


@pytest.mark.asyncio
async def test_dispatch_executor_que_lanca_nao_derruba():
    reg = VoCToolRegistry()

    async def _boom(args):
        raise RuntimeError("falhei feio")

    reg.register("explode", "d", _schema(), _boom)
    out = await reg.dispatch(ToolCall(id="c1", name="explode", arguments={"x": "y"}))
    parsed = json.loads(out)
    assert parsed["ok"] is False
    assert "explode" in parsed["error"]


@pytest.mark.asyncio
async def test_dispatch_resultado_string_passa_direto():
    reg = VoCToolRegistry()

    async def _txt(args):
        return "resultado cru"

    reg.register("texto", "d", _schema(), _txt)
    out = await reg.dispatch(ToolCall(id="c1", name="texto", arguments={}))
    assert out == "resultado cru"


def test_re_registrar_sobrescreve():
    reg = VoCToolRegistry()

    async def _a(args):
        return "a"

    async def _b(args):
        return "b"

    reg.register("dup", "primeira", _schema(), _a)
    reg.register("dup", "segunda", _schema(), _b)
    assert len(reg) == 1
    assert reg.as_tools()[0]["function"]["description"] == "segunda"
