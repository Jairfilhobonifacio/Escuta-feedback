"""Fechar o loop: import_abordagens (worklist → mega central) — cria/atualiza, idempotente."""
from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import select

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.models.core import Contact, Organization  # noqa: E402
from app.models.feedback import FeedbackItem  # noqa: E402
from scripts.import_abordagens import ingest_abordagens  # noqa: E402


async def _org(session) -> Organization:
    org = Organization(slug="bizzu", name="Bizzu")
    session.add(org)
    await session.flush()
    return org


@pytest.mark.asyncio
async def test_ingest_cria_feedback_churn(session):
    org = await _org(session)
    registros = [{
        "whatsapp": "5531999990000", "nome": "Fulano",
        "motivo": "achei caro", "faltou": "mais simulados", "voltaria": "se baixar o preço",
        "flags": {"quer_call": True, "audio": False, "reativavel": True},
        "abordado_em": "2026-06-12T15:00:00Z",
    }]
    res = await ingest_abordagens(session, org, registros)
    assert res.created == 1 and res.updated == 0 and res.skipped == 0

    item = (await session.execute(select(FeedbackItem))).scalars().one()
    assert item.type == "churn"
    assert item.source == "campanha_churn"
    assert item.abordado is True
    assert item.abordado_em is not None
    assert "Por que saiu: achei caro" in item.text
    assert "O que faltou: mais simulados" in item.text
    assert "O que faria voltar: se baixar o preço" in item.text
    assert "quer_call" in item.themes
    assert "reativavel" in item.themes
    assert "respondeu_audio" not in item.themes  # audio=False
    # contato criado por whatsapp
    contact = (await session.execute(select(Contact))).scalars().one()
    assert contact.phone == "5531999990000" and contact.name == "Fulano"


@pytest.mark.asyncio
async def test_ingest_idempotente_atualiza_sem_duplicar(session):
    org = await _org(session)
    base = {"whatsapp": "5531888880000", "nome": "Beltrano", "motivo": "sem tempo",
            "flags": {"quer_call": False}}
    await ingest_abordagens(session, org, [base])

    # re-importa o MESMO contato com a nota corrigida → atualiza, não duplica
    base2 = {**base, "motivo": "sem tempo, voltei a estudar sozinho", "flags": {"quer_call": True}}
    res = await ingest_abordagens(session, org, [base2])
    assert res.updated == 1 and res.created == 0

    itens = (await session.execute(select(FeedbackItem))).scalars().all()
    assert len(itens) == 1  # uma abordagem por cliente/campanha
    assert "voltei a estudar sozinho" in itens[0].text
    assert "quer_call" in itens[0].themes


@pytest.mark.asyncio
async def test_ingest_pula_vazios(session):
    org = await _org(session)
    registros = [
        {"whatsapp": "", "motivo": "x"},                       # sem whatsapp
        {"whatsapp": "5531777770000", "flags": {}},            # nada apurado
    ]
    res = await ingest_abordagens(session, org, registros)
    assert res.skipped == 2 and res.created == 0
    assert (await session.execute(select(FeedbackItem))).scalars().first() is None
