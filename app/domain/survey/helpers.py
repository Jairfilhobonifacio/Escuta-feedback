"""Helpers de composição do texto das respostas (puros, sem estado — testáveis isolados)."""
from __future__ import annotations


def append_call_link(text: str, call_url: str | None) -> str:
    """Anexa um convite de call ao texto, se houver link configurado (BIZZU_CALL_URL).

    Sem link (env não setada) devolve o texto intacto — comportamento atual.
    Idempotente: não duplica o link se ele já estiver presente.
    """
    if not call_url:
        return text
    if call_url in text:
        return text
    return f"{text}\n\nSe preferir, dá pra trocar uma ideia rápida numa call — é só agendar aqui: {call_url} 📞"
