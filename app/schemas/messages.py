"""Schemas (Pydantic) do domínio de Message — metadados de mensagem inbound/outbound.

Hoje os schemas da Escuta vivem inline nos `app/api/*.py`. Este módulo é o
primeiro `app/schemas/*` dedicado: descreve o conteúdo do novo campo
`messages.msg_metadata` (JSONB nullable), o saco de metadados por mensagem.

`MessageMetadata` é um schema PERMISSIVO (extra='allow'): documenta as chaves
conhecidas mas não rejeita chaves novas — o JSONB pode crescer sem migration. O
write-path usa o padrão copia-edita-reatribui ao montar o dict (nunca muta
in-place o `msg_metadata` de uma linha existente).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class MessageMetadata(BaseModel):
    """Metadados livres de uma `Message` (vai serializado no JSONB `msg_metadata`).

    Tudo opcional — uma mensagem sem nada anotado tem `msg_metadata = NULL`. As
    chaves abaixo são as conhecidas hoje; chaves extras são preservadas
    (`extra='allow'`) para a coluna evoluir sem nova migration.
    """

    model_config = ConfigDict(extra="allow")

    # Evento bruto do WAHA que originou a mensagem ('message' | 'message.any').
    source_event: Optional[str] = None
    # Tipo de mídia, quando houver ('audio' p/ voz transcrita). None = texto puro.
    media_type: Optional[str] = None
    # True quando o corpo veio de transcrição de áudio (Groq Whisper).
    transcribed: Optional[bool] = None
    # Por qual caminho a inbound foi tratada quando NÃO casou pesquisa pendente:
    # 'no_pending_survey' | 'human_handoff' | 'audio_not_transcribed' | ...
    handler_route: Optional[str] = None

    def to_jsonb(self) -> dict[str, Any]:
        """Dict pronto p/ gravar no JSONB, já sem as chaves None (enxuto)."""
        return {k: v for k, v in self.model_dump().items() if v is not None}
