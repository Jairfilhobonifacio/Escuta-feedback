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

from app.config import settings
from app.services.llm import GroqLLM

logger = logging.getLogger(__name__)

IntentKind = Literal["score", "opt_out", "question", "unclear", "handoff"]

# Resposta fixa de opt-out (precisa ser estável: entra no filtro de eco do webhook).
OPT_OUT_CONFIRM_MSG = "Entendido! Não vou mais te mandar pesquisas por aqui. 🙏 Se mudar de ideia, é só avisar."

# Resposta HONESTA quando não há contexto relevante na base (NO_KB_FALLBACK):
# nunca inventa um fato — encaminha ao time. Curta e calorosa.
HONEST_NO_KB_MSG = (
    "Boa pergunta! Essa eu não sei responder com certeza por aqui — "
    "vou encaminhar pro time pra te dar o retorno certinho. 🙏"
)

# Piso de similaridade NO NÍVEL DO BRAIN: mesmo que o retriever devolva trechos,
# se o MELHOR deles não passa deste score o contexto é fraco demais → tratamos como
# "sem KB". Conservador; o retriever já filtra por um piso próprio, isto é a 2ª trava.
BRAIN_MIN_RELEVANT_SCORE = 0.30


def _no_kb_fallback_enabled() -> bool:
    """Lê a flag NO_KB_FALLBACK em call-time (settings é frozen; isto é o ponto de
    indireção que os testes monkeypatcham para alternar o comportamento honesto)."""
    return settings.no_kb_fallback_enabled

_INTERPRET_SYSTEM = """Você é o assistente de pesquisas via WhatsApp de uma empresa (português brasileiro).
O contato recebeu uma pergunta de pesquisa com nota de 0 a 10 e respondeu algo que o sistema não entendeu como nota direta.
Classifique a INTENÇÃO da mensagem do contato e responda SOMENTE com JSON válido:

{"kind": "score" | "opt_out" | "question" | "handoff" | "unclear",
 "score": <inteiro 0-10 ou null>,
 "reply": "<string ou null>"}

Regras:
- "score": a mensagem contém/implica uma nota (ex.: "uns oito", "nota máxima", "zero!", "8/10", "dez"). Extraia o inteiro 0-10 em "score".
- "opt_out": o contato pede para PARAR de receber mensagens/pesquisas, sair da lista, "me tira disso", "não me mande mais nada". reply=null.
- "question": o contato fez uma pergunta ou levantou uma dúvida/objeção (sobre a pesquisa, a empresa, quem é você, como cancelar etc.).
  Em "reply", responda em 1-2 frases simpáticas e honestas EM PORTUGUÊS. Você é um assistente de pesquisa de satisfação:
  NÃO invente fatos sobre a empresa (preços, políticas). Se não souber, diga que vai encaminhar ao time. Não use markdown.
- "handoff": o contato pede explicitamente falar com uma PESSOA/humano/atendente, OU está muito irritado/ameaça (cancelar tudo, Procon/justiça, "isso é um absurdo"), OU relata um problema GRAVE/bloqueante que precisa de ação humana. reply=null.
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


_REASON_PROMPT_SYSTEM = """Você é o assistente de pesquisa de satisfação de uma empresa no WhatsApp (português brasileiro). O cliente ACABOU de responder uma nota de 0 a 10. Escreva a PRÓXIMA mensagem do bot: uma pergunta curta pedindo o MOTIVO da nota, com o TOM CERTO para o tamanho da nota. Responda SOMENTE com JSON válido:

{"message": "<uma pergunta curta, 1 linha, calorosa, sem markdown>"}

Regras de tom (NUNCA comemore uma nota baixa — isso é o erro mais grave):
- Nota 0 a 6 (detrator): demonstre EMPATIA e atenção genuína, SEM "Massa!"/festa/emoji alegre. Pergunte o que deu errado ou o que mais incomodou. Ex.: "Poxa, sinto muito que a experiência não tenha sido boa 😕 Me conta o que aconteceu?".
- Nota 7 a 8 (neutro): agradeça e pergunte o que FALTOU para virar um 10. Ex.: "Valeu pela nota! 🙌 O que faltou pra ser um 10 pra você?".
- Nota 9 a 10 (promotor): comemore de leve e pergunte o que MAIS ajudou. Ex.: "Que demais, obrigado! 🎉 O que mais te ajudou?".
- No máximo 1 emoji, coerente com o tom. Não repita a pergunta da nota. Não invente fatos sobre a empresa. Seja humano e direto."""


_FOLLOWUP_SYSTEM = """Você é um pesquisador de satisfação (português brasileiro) decidindo se vale UMA pergunta de aprofundamento, depois que o cliente deu uma nota e um comentário. Responda SOMENTE com JSON válido:

{"should_followup": true | false, "question": "<string ou null>"}

Você recebe a NOTA (0-10), o COMENTÁRIO e o SENTIMENTO detectado.

should_followup=true quando:
- Nota BAIXA (0-6, detrator) e o comentário NÃO explica o porquê de verdade — vago, genérico, brincadeira/ironia ("kkk", "massa? kkk", "sei lá", "tudo", "nada"), ou um "não gostei" sem dizer de quê. DETRATOR É PRIORIDADE: vale entender mesmo que o cliente tenha respondido pouco ou de brincadeira. Em "question", faça UMA pergunta aberta, empática e específica para descobrir o que realmente aconteceu.
- CONTRADIÇÃO entre a nota e o comentário/sentimento (ex.: nota 9-10 mas comentário negativo ou sentimento "negativo"; ou nota 0-2 com elogio). Em "question", aponte a incoerência com gentileza e peça para entender (ex.: "Você deu 10 mas comentou que não gostou — me ajuda a entender o que pesou?").
- Comentário vago mas com um detalhe concreto que dá pra puxar.

should_followup=false quando:
- O comentário JÁ é informativo/acionável ("muito caro", "faltam questões de X", "o app trava"); OU
- É um promotor satisfeito (nota alta + comentário coerente e positivo); OU
- Não há nada honesto a perguntar.

Regras: UMA pergunta só, 1 linha, calorosa, sem markdown. Nunca repita a pergunta anterior. Não invente fatos; pergunte sobre o que o cliente disse ou sobre a incoerência nota×comentário. question=null quando should_followup=false."""


_SURVEY_AGENT_SYSTEM = """Você é um pesquisador de satisfação simpático e esperto conduzindo uma pesquisa NPS pelo WhatsApp (português brasileiro). Seu objetivo é descobrir a NOTA (0 a 10) que a pessoa daria e ENTENDER o motivo de verdade — conversando como um humano atento, nunca como um robô de respostas prontas.

Você recebe a CONVERSA até aqui (a última linha é a mensagem que o cliente acabou de mandar) e o ESTADO da pesquisa. Responda SOMENTE com JSON válido:
{"score": <inteiro 0-10 ou null>,
 "reason": <string ou null>,
 "topic": <string curta ou null>,
 "next": "ask_score" | "probe" | "close" | "handoff" | "opt_out",
 "reply": "<sua próxima mensagem para o cliente>"}

Como preencher:
- score: a nota ATUAL da pessoa (a mais recente que ela quis dar). Se ela CORRIGIR a nota — "na verdade é 1", ou só manda "1" depois de você apontar uma incoerência — ATUALIZE o score. NUNCA trate um número solto como se fosse o motivo. Entenda nota em linguagem natural ("uns oito"=8, "nota máxima"=10, "zero à esquerda"=0). Ironia/exagero ("nota mil", "menos infinito") NÃO é nota: peça a real. Sem nota ainda → null.
- reason: o motivo consolidado até agora (o porquê da nota), juntando o que a pessoa já disse. null se ainda não há.
- topic: se NESTA resposta você vai perguntar sobre um aspecto novo, dê um rótulo curto pra ele ("preço", "conteúdo", "bug"); senão null. Serve pra você não se repetir.
- next — escolha com critério:
  - "ask_score": ainda NÃO há nota clara → peça ou confirme a nota, tom leve.
  - "probe": já tem nota, mas o motivo está REALMENTE vazio (só "sei lá", "sl", emoji, "nada", "complicado") ou há contradição (nota alta + reclamação) → faça UMA pergunta nova. Detrator (0-6) merece empatia; na contradição, aponte a incoerência com gentileza.
  - "close": FECHE assim que tiver a nota E QUALQUER motivo concreto — mesmo curto ("o app cai", "faltam questões", "passei na prova", "suporte some"). Se a pessoa deu VÁRIOS motivos de uma vez, reconheça-os e feche (não peça mais). Promotor com elogio claro: feche rápido e caloroso. Detrator vago que você JÁ tentou aprofundar 1x e mesmo assim não abriu: feche reconhecendo a frustração dele (não um "obrigado pela honestidade" seco).
  - "handoff": a pessoa está furiosa, relata problema grave/bloqueante, ou pede pra falar com uma pessoa/humano/atendente.
  - "opt_out": a pessoa pede pra parar de receber as mensagens/pesquisas.
- SE O CLIENTE FIZER UMA PERGUNTA ("quem é você?", "como cancelo?"): responda em 1 frase (ou diga que vai encaminhar ao time, se não souber) e RETOME a nota na MESMA mensagem. Uma pergunta NÃO vira handoff.
- reply: sua próxima mensagem ao cliente. UMA ideia por vez, 1-2 frases, tom humano e caloroso, no máximo 1 emoji. Adapte o tom à nota (detrator = empatia sincera, sem "Massa!"; promotor = comemore de leve). Ao FECHAR, agradeça CURTO e ESPECÍFICO refletindo o que a pessoa falou — varie sempre, nunca uma frase decorada.

Regras de ouro:
- O ERRO MAIS COMUM é APROFUNDAR DEMAIS. Na dúvida entre perguntar de novo e fechar, FECHE. Aprofunde no máximo 1 vez; só insista numa 2ª se for detrator E a 1ª não trouxe NADA de concreto.
- NUNCA repita (nem reformule) uma pergunta sobre algo que já está em "já perguntei sobre" ou que o cliente já respondeu.
- Não agradeça várias vezes nem encha. Se a pessoa se irritar com a pesquisa ("já respondi", "para de perguntar"), feche educado na hora.
- Não invente fatos sobre a empresa (preço, política, prazos). Não use markdown."""


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
        if kind not in ("score", "opt_out", "question", "unclear", "handoff"):
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

    @staticmethod
    def _has_relevant_kb(chunks: list) -> bool:
        """True se há contexto utilizável: ao menos 1 trecho com conteúdo e cujo
        melhor score passa do piso do brain. KB vazio OU só ruído fraco ⇒ False.

        Trechos sem atributo `score` (dublês simples) contam como relevantes desde
        que tenham conteúdo — o filtro de score é a 2ª trava sobre o do retriever."""
        if not chunks:
            return False
        for c in chunks:
            content = (getattr(c, "content", "") or "").strip()
            if not content:
                continue
            score = getattr(c, "score", None)
            if score is None or float(score) >= BRAIN_MIN_RELEVANT_SCORE:
                return True
        return False

    async def answer_from_context(self, question: str, chunks: list) -> Optional[str]:
        """Resposta grounded a uma dúvida, usando SÓ os trechos recuperados.

        chunks: itens com .title e .content (RetrievedChunk). Sem chunks (ou só
        ruído abaixo do piso) ou LLM julgando não-respondível ⇒ None (quem chama
        cai no fallback honesto / genérico). Para a resposta HONESTA explícita
        nesse caso (sem depender do chamador), use `answer_question_grounded`.
        """
        if not self._has_relevant_kb(chunks):
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

    async def answer_question_grounded(self, question: str, chunks: list) -> Optional[str]:
        """RAG com FALLBACK HONESTO explícito (NO_KB_FALLBACK).

        - Há contexto relevante e o LLM consegue responder grounded ⇒ devolve a resposta.
        - SEM contexto relevante (KB vazio OU score abaixo do piso): NÃO chama o LLM e,
          se NO_KB_FALLBACK_ENABLED, devolve a mensagem honesta (`HONEST_NO_KB_MSG`) —
          jamais inventa um fato. Com a flag OFF, devolve None (comportamento antigo).
        - Há contexto, mas o LLM julga não-respondível: também cai no honesto (a info
          existe na base mas não cobre a pergunta — melhor encaminhar do que alucinar).
        """
        if not self._has_relevant_kb(chunks):
            # NO_KB_FALLBACK: caminho honesto explícito, sem gastar uma chamada de LLM.
            return HONEST_NO_KB_MSG if _no_kb_fallback_enabled() else None
        answer = await self.answer_from_context(question, chunks)
        if answer:
            return answer
        # Tinha contexto mas o LLM não se sentiu seguro: honesto > inventado.
        return HONEST_NO_KB_MSG if _no_kb_fallback_enabled() else None

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

    async def compose_reason_prompt(
        self, score: Optional[int], survey_name: str, question_text: str = ""
    ) -> Optional[str]:
        """Gera a pergunta de MOTIVO com o tom adaptado à nota (empatia p/ detrator,
        comemoração p/ promotor). None ⇒ quem chama usa o texto fixo do survey."""
        if score is None:
            return None
        user = (
            f"Pesquisa: {survey_name!r}\n"
            f"Pergunta da nota: {question_text!r}\n"
            f"Nota que o cliente ACABOU de dar: {score} (de 0 a 10)"
        )
        data = await self.llm.chat_json(_REASON_PROMPT_SYSTEM, user)
        if not data:
            return None
        msg = data.get("message")
        if not msg or not str(msg).strip():
            return None
        return str(msg).strip()[:300]

    async def decide_followup(
        self,
        answer_text: str,
        score: Optional[int],
        survey_name: str,
        sentiment: Optional[str] = None,
    ) -> Optional[str]:
        """Decide UMA pergunta de aprofundamento — ou None (fecha).

        Mais assertivo com detrator (insiste mesmo em comentário vago/de brincadeira)
        e detecta contradição nota×comentário (sentiment ajuda). Best-effort.
        """
        user = (
            f"Pesquisa: {survey_name!r}\n"
            f"Nota dada: {score if score is not None else 'sem nota'}\n"
            f"Sentimento detectado: {sentiment or 'não classificado'}\n"
            f"Comentário do cliente: {answer_text!r}"
        )
        data = await self.llm.chat_json(_FOLLOWUP_SYSTEM, user)
        if not data or not data.get("should_followup"):
            return None
        q = data.get("question")
        if not q or not str(q).strip():
            return None
        return str(q).strip()[:300]

    async def run_survey_turn(
        self,
        *,
        survey_name: str,
        nps_question: str,
        history: list[tuple[str, str]],
        score: Optional[int],
        reason: Optional[str],
        topics: list[str],
        followups: int,
    ) -> Optional[dict[str, Any]]:
        """O cérebro do Survey Agent: lê a conversa inteira + o estado e decide o
        próximo turno (capturar/corrigir nota, aprofundar, fechar, escalar) numa
        única chamada. `history` = [(direction, body)] em ordem cronológica, com a
        mensagem atual do cliente no fim. Retorna o dict validado ou None (fallback)."""
        convo = "\n".join(
            f"{'CLIENTE' if str(d).lower().startswith('in') else 'VOCÊ'}: {b}"
            for d, b in history
        ) or "(ainda sem mensagens)"
        user = (
            f"Pesquisa: {survey_name!r} — pergunta da nota: {nps_question!r}\n"
            f"ESTADO ATUAL: nota={score if score is not None else 'ainda não dada'}; "
            f"motivo até agora={reason or 'nenhum'}; "
            f"já perguntei sobre={', '.join(topics) if topics else 'nada'}; "
            f"rodadas de aprofundamento já feitas={followups}\n\n"
            f"CONVERSA (a última linha é a mensagem atual do cliente):\n{convo}"
        )
        data = await self.llm.chat_json(
            _SURVEY_AGENT_SYSTEM, user, temperature=0.5, max_tokens=500
        )
        if not data:
            return None

        nxt = data.get("next")
        if nxt not in ("ask_score", "probe", "close", "handoff", "opt_out"):
            return None
        reply = data.get("reply")
        if not reply or not str(reply).strip():
            return None

        score_out = data.get("score")
        if score_out is not None and (not isinstance(score_out, int) or not (0 <= score_out <= 10)):
            score_out = None
        reason_out = data.get("reason")
        reason_out = str(reason_out).strip()[:2000] if reason_out and str(reason_out).strip() else None
        topic_out = data.get("topic")
        topic_out = str(topic_out).strip().lower()[:40] if topic_out and str(topic_out).strip() else None

        return {
            "score": score_out,
            "reason": reason_out,
            "topic": topic_out,
            "next": nxt,
            "reply": str(reply).strip()[:600],
        }
