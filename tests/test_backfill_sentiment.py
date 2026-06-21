"""Testes do backfill de sentimento (scripts/backfill_sentiment.py).

Cobrem a SELEÇÃO/elegibilidade (a parte que o dry-run conta) sem tocar na Groq:
- só entra quem tem texto não-vazio E sentiment vazio (NULL/''/espaços);
- quem já tem sentiment, quem não tem texto, e texto/sentiment só-espaços são fora;
- --org restringe por organização (org-scoped);
- idempotência: depois de setar sentiment, o item deixa de ser elegível.

Usa o engine SQLite in-memory da conftest (sem Supabase, sem LLM).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.core import Organization
from app.models.feedback import FeedbackItem
from scripts.backfill_sentiment import _needs_sentiment, select_eligible


def _org(session, name="Org"):
    org = Organization(id=uuid.uuid4(), name=name, slug=f"slug-{uuid.uuid4().hex[:8]}")
    session.add(org)
    return org


def _fb(org_id, *, text=None, sentiment=None, source="bizzu_app", type="nps", score=None):
    return FeedbackItem(
        id=uuid.uuid4(),
        organization_id=org_id,
        source=source,
        type=type,
        score=score,
        text=text,
        sentiment=sentiment,
    )


# --- _needs_sentiment: critério canônico (puro, sem banco) -----------------------


@pytest.mark.parametrize(
    "text,sentiment,expected",
    [
        ("péssimo atendimento", None, True),       # tem texto, sem sentiment -> SIM
        ("ótimo", "", True),                        # sentiment string vazia -> SIM
        ("ótimo", "   ", True),                     # sentiment só espaços -> SIM
        ("ótimo", "positivo", False),               # já classificado -> NÃO
        (None, None, False),                        # sem texto -> NÃO
        ("", None, False),                          # texto vazio -> NÃO
        ("   ", None, False),                       # texto só espaços -> NÃO
        ("   ", "positivo", False),                 # sem texto util, já tem -> NÃO
    ],
)
def test_needs_sentiment(text, sentiment, expected):
    item = FeedbackItem(text=text, sentiment=sentiment)
    assert _needs_sentiment(item) is expected


# --- select_eligible: a query + refino que o dry-run conta -----------------------


@pytest.mark.asyncio
async def test_select_eligible_picks_only_missing_sentiment(session):
    org = _org(session)
    await session.flush()
    falta = _fb(org.id, text="demorou demais", sentiment=None)
    vazio = _fb(org.id, text="confuso", sentiment="  ")
    ja = _fb(org.id, text="adorei", sentiment="positivo")
    sem_texto = _fb(org.id, text=None, sentiment=None)
    session.add_all([falta, vazio, ja, sem_texto])
    await session.commit()

    eligible = await select_eligible(session, org_id=None)
    ids = {it.id for it in eligible}
    assert ids == {falta.id, vazio.id}


@pytest.mark.asyncio
async def test_select_eligible_is_org_scoped(session):
    org_a = _org(session, "A")
    org_b = _org(session, "B")
    await session.flush()
    a = _fb(org_a.id, text="ruim", sentiment=None)
    b = _fb(org_b.id, text="ruim também", sentiment=None)
    session.add_all([a, b])
    await session.commit()

    only_a = await select_eligible(session, org_id=org_a.id)
    assert {it.id for it in only_a} == {a.id}

    todas = await select_eligible(session, org_id=None)
    assert {it.id for it in todas} == {a.id, b.id}


@pytest.mark.asyncio
async def test_backfill_is_idempotent_after_setting_sentiment(session):
    org = _org(session)
    await session.flush()
    item = _fb(org.id, text="caro demais", sentiment=None)
    session.add(item)
    await session.commit()

    # Antes: elegível.
    assert {it.id for it in await select_eligible(session, None)} == {item.id}

    # Simula o que o --apply faz (grava sentiment) e re-seleciona.
    item.sentiment = "negativo"
    await session.commit()

    assert await select_eligible(session, None) == []
