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

_ANSWER_SYSTEM = """Você é o assistente de uma empresa no WhatsApp (português brasileiro), respondendo uma dúvida de um cliente.
Você recebe TRECHOS DE CONHECIMENTO da empresa e a PERGUNTA do cliente. Responda SOMENTE com JSON válido:

{"answerable": true | false, "answer": "<string ou null>"}

Regras (groundedness é inegociável):
- Use APENAS informação contida nos trechos. NÃO use conhecimento geral seu, NÃO invente preços, prazos, políticas ou números.
- Se os trechos respondem a pergunta: answerable=true e "answer" = resposta curta (1-3 frases), calorosa, em português, SEM markdown, parafraseando os trechos.
- Se os trechos NÃO contêm a resposta (ou só tangenciam): answerable=false, answer=null. É melhor não responder do que inventar.
- Nunca cite "segundo os trechos" / "de acordo com o contexto": fale natural, como um atendente que conhece a empresa."""

_DIGEST_SYSTEM = """Você é o chief of staff de Voz do Cliente de uma empresa, escrevendo o resumo SEMANAL para o dono no WhatsApp (português brasileiro).
Recebe os números da semana em JSON. Escreva uma mensagem CURTA (no máximo ~8 linhas), humana e acionável. Responda SOMENTE com JSON válido:

{"message": "<texto pronto para enviar no WhatsApp>"}

Regras:
- Comece com uma saudação curta e o período ("Resumo da sua semana 👋").
- Destaque o NÚMERO-CHAVE: NPS e a variação vs semana anterior (subiu/caiu X pontos), se houver.
- Aponte 1-2 destaques REAIS dos dados: temas mais citados, casos urgentes, motivos de cancelamento. Cite no máximo 1 frase curta de cliente, se houver.
- Termine com UMA sugestão de ação concreta baseada nos dados (não genérica).
- Use no MÁXIMO 2-3 emojis no total. NÃO use markdown (nem **, nem #, nem listas com -). Quebras de linha simples para separar ideias.
- Não invente números que não estão no JSON. Se a semana foi fraca em dados, seja honesto e breve."""

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

    async def answer_from_context(self, question: str, chunks: list) -> Optional[str]:
        """Resposta grounded a uma dúvida, usando SÓ os trechos recuperados.

        chunks: itens com .title e .content (RetrievedChunk). Sem chunks ou
        LLM julgando não-respondível ⇒ None (quem chama cai no fallback honesto).
        """
        if not chunks:
            return None
        context = "\n\n".join(f"[{getattr(c, 'title', '')}]\n{getattr(c, 'content', '')}" for c in chunks)
        user = f"TRECHOS DE CONHECIMENTO:\n{context}\n\nPERGUNTA DO CLIENTE: {question!r}"
        data = await self.llm.chat_json(_ANSWER_SYSTEM, user)
        if not data or not data.get("answerable"):
            return None
        answer = data.get("answer")
        if not answer:
            return None
        return str(answer).strip()[:600] or None

    async def narrate_digest(self, data: dict) -> Optional[str]:
        """Narra os números da semana num texto pronto pro WhatsApp do dono.

        Recebe DigestData.as_dict(). Retorna a mensagem ou None (LLM indisponível
        ou resposta inválida) — quem chama tem um fallback determinístico.
        """
        import json

        user = "Números da semana (JSON):\n" + json.dumps(data, ensure_ascii=False)
        out = await self.llm.chat_json(_DIGEST_SYSTEM, user)
        if not out:
            return None
        msg = out.get("message")
        if not msg or not str(msg).strip():
            return None
        return str(msg).strip()[:1500]

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
