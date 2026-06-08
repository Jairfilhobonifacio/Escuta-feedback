"""SurveyBrain — a camada de inteligência do fluxo de pesquisa.

Entra em cena APENAS quando o caminho determinístico não resolve:
o parser de nota falhou e precisamos entender a intenção do contato
("ah, uns oito eu acho" / "para de me mandar isso" / "quem é você?").
Também classifica o feedback textual ao fechar (sentimento/temas/urgência).

Contratos:
- Toda função devolve um resultado tipado ou None (LLM indisponível/da
  resposta inválida) — quem chama SEMPRE tem um fallback determinístico.
- O brain não toca banco: decide; o resolver aplica.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

from app.services.llm import GroqLLM

logger = logging.getLogger(__name__)

IntentKind = Literal["score", "opt_out", "question", "unclear"]

# Resposta fixa de opt-out (precisa ser estável: entra no filtro de eco do webhook).
OPT_OUT_CONFIRM_MSG = "Entendido! Não vou mais te mandar pesquisas por aqui. 🙏 Se mudar de ideia, é só avisar."

_INTERPRET_SYSTEM = """Você é o assistente de pesquisas via WhatsApp de uma empresa (português brasileiro).
O contato recebeu uma pergunta de pesquisa com nota de 0 a 10 e respondeu algo que o sistema não entendeu como nota direta.
Classifique a INTENÇÃO da mensagem do contato e responda SOMENTE com JSON válido:

{"kind": "score" | "opt_out" | "question" | "unclear",
 "score": <inteiro 0-10 ou null>,
 "reply": "<string ou null>"}

Regras:
- "score": a mensagem contém/implica uma nota (ex.: "uns oito", "nota máxima", "zero!", "8/10", "dez"). Extraia o inteiro 0-10 em "score".
- "opt_out": o contato pede para PARAR de receber mensagens/pesquisas, sair da lista, "me tira disso", "não me mande mais nada". reply=null.
- "question": o contato fez uma pergunta ou levantou uma dúvida/objeção (sobre a pesquisa, a empresa, quem é você, como cancelar etc.).
  Em "reply", responda em 1-2 frases simpáticas e honestas EM PORTUGUÊS. Você é um assistente de pesquisa de satisfação:
  NÃO invente fatos sobre a empresa (preços, políticas). Se não souber, diga que vai encaminhar ao time. Não use markdown.
- "unclear": qualquer outra coisa (emoji solto, "ok", assunto aleatório sem pergunta). reply=null.
- Sarcasmo/ironia ("nota mil", "menos mil") NÃO é nota válida 0-10: trate como "unclear", score=null."""

_CLASSIFY_SYSTEM = """Você classifica feedback de clientes (português brasileiro) para um painel de Voz do Cliente.
Responda SOMENTE com JSON válido:

{"sentiment": "positivo" | "neutro" | "negativo",
 "themes": ["tema1", "tema2"],
 "urgency": "baixa" | "media" | "alta"}

Regras:
- themes: 1 a 3 temas CURTOS em minúsculas (ex.: "preço", "qualidade do conteúdo", "suporte", "usabilidade", "tempo", "concorrência"). Use o tema mais específico possível que o texto suporte.
- urgency "alta": ameaça de churn explícita, problema bloqueante, raiva forte, menção a órgão de defesa/justiça.
- urgency "media": insatisfação concreta acionável.
- urgency "baixa": elogio, neutro ou vago.
- Não invente temas que o texto não menciona."""


@dataclass
class BrainIntent:
    kind: IntentKind
    score: Optional[int] = None
    reply: Optional[str] = None


@dataclass
class FeedbackTags:
    sentiment: str
    themes: list[str]
    urgency: str

    def as_dict(self) -> dict[str, Any]:
        return {"sentiment": self.sentiment, "themes": self.themes, "urgency": self.urgency}


class SurveyBrain:
    def __init__(self, llm: GroqLLM):
        self.llm = llm

    async def interpret_reply(self, question_text: str, message: str) -> Optional[BrainIntent]:
        """Interpreta uma resposta que o parser determinístico não entendeu."""
        user = (
            f"Pergunta enviada ao contato: {question_text!r}\n"
            f"Mensagem do contato: {message!r}"
        )
        data = await self.llm.chat_json(_INTERPRET_SYSTEM, user)
        if not data:
            return None

        kind = data.get("kind")
        if kind not in ("score", "opt_out", "question", "unclear"):
            return None

        score = data.get("score")
        if kind == "score":
            # Valida o inteiro 0-10 com o mesmo rigor do parser — LLM não tem passe livre.
            if not isinstance(score, int) or not (0 <= score <= 10):
                return None
        else:
            score = None

        reply = data.get("reply")
        if kind == "question":
            reply = (str(reply).strip() or None) if reply else None
            if reply is None:
                return None
            reply = reply[:600]  # nunca mandar um textão no WhatsApp
        else:
            reply = None

        return BrainIntent(kind=kind, score=score, reply=reply)

    async def classify_feedback(
        self, answer_text: str, score: Optional[int], survey_name: str
    ) -> Optional[FeedbackTags]:
        """Classifica o motivo textual ao fechar uma response."""
        user = (
            f"Pesquisa: {survey_name!r}\n"
            f"Nota dada: {score if score is not None else 'sem nota'}\n"
            f"Feedback do cliente: {answer_text!r}"
        )
        data = await self.llm.chat_json(_CLASSIFY_SYSTEM, user)
        if not data:
            return None

        sentiment = data.get("sentiment")
        urgency = data.get("urgency")
        themes = data.get("themes")
        if sentiment not in ("positivo", "neutro", "negativo"):
            return None
        if urgency not in ("baixa", "media", "alta"):
            return None
        if not isinstance(themes, list):
            return None
        themes = [str(t).strip().lower()[:60] for t in themes if str(t).strip()][:3]

        return FeedbackTags(sentiment=sentiment, themes=themes, urgency=urgency)
