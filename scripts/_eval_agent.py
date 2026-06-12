"""EVAL HARNESS — mede a inteligência do Survey Agent do Escuta com LLM REAL (Groq).

Para cada persona em .specs/survey_personas.json:
 1. Simula a conversa turno a turno, replicando FIELMENTE o estado de _run_agent.
 2. Junta o transcript real, o score final, o reason final e como/se fechou.
 3. Chama um LLM-JUIZ (mesmo Groq) que pontua inteligência/captura/tom etc.

NÃO toca banco, NÃO manda WhatsApp, NÃO importa o resolver (replica o estado aqui).
Rode com: $env:PYTHONUTF8='1'; py scripts/_eval_agent.py
"""
from __future__ import annotations

# --- PEGADINHAS OBRIGATÓRIAS (ordem importa) -------------------------------
import truststore  # noqa: E402

truststore.inject_into_ssl()  # senão Groq dá CERTIFICATE_VERIFY_FAILED nesta máquina

import os  # noqa: E402
import sys  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)  # ANTES de importar app.*


def _load_dotenv() -> None:
    path = os.path.join(_ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

import asyncio  # noqa: E402
import json  # noqa: E402

from app.config import settings  # noqa: E402
from app.domain.survey.brain import SurveyBrain  # noqa: E402
from app.services.llm import GroqLLM  # noqa: E402

# --- Constantes do cenário --------------------------------------------------
NPS_QUESTION = "De 0 a 10, o quanto você recomendaria o Bizzu pra um amigo concurseiro?"
SURVEY_NAME = "NPS Bizzu"
PERSONAS_PATH = os.path.join(_ROOT, ".specs", "survey_personas.json")
CRITICAL = {"corrige-nota", "contradicao-nota-texto", "furioso-handoff", "detrator-vago-empatia-2a"}

TERMINAL = ("close", "handoff", "opt_out")

# Espaçamento entre chamadas Groq. O limite que morde no free-tier é TOKENS POR
# MINUTO (TPM=12000), não requests: cada turno usa ~1100-1600 tokens (system grande
# + transcript). ~12s/chamada mantém o consumo < 12k/min com folga. Ajustável por env.
SLEEP_BETWEEN_CALLS = float(os.getenv("EVAL_SLEEP", "13"))


def nps_bucket(score: int | None) -> str | None:
    if score is None:
        return None
    if score <= 6:
        return "detrator"
    if score <= 8:
        return "passivo"
    return "promotor"


async def _retry_call(coro_factory, *, what: str, attempts: int = 4):
    """Chama um factory de coroutine que devolve dict|None. Como GroqLLM engole o
    429 e devolve None, tratamos None como POSSÍVEL rate-limit e re-tentamos com
    backoff crescente (o limite é TPM, então esperar a janela de 60s resolve).
    Distingue 'None real' (resposta inválida) de rate-limit só na prática: após
    todas as tentativas, devolve None."""
    delay = 20.0
    for i in range(attempts):
        out = await coro_factory()
        if out is not None:
            return out
        if i < attempts - 1:
            print(f"        [retry {what}: None (provável 429 TPM) — aguardando {delay:.0f}s]",
                  flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 65.0)
    return None


async def simulate_persona(brain: SurveyBrain, persona: dict) -> dict:
    """Roda a conversa turno a turno replicando o estado de _run_agent. Sem banco."""
    # Estado local inicial (espelho da linha pendente)
    score: int | None = None
    reason: str | None = None
    topics: list[str] = []
    turns = 0
    # history: 1ª linha = a pergunta NPS que o bot mandou (out)
    history: list[tuple[str, str]] = [("out", NPS_QUESTION)]

    transcript: list[tuple[str, str]] = [("BOT", NPS_QUESTION)]
    closed_via: str | None = None
    fell_back = False

    for msg in persona["mensagens_cliente"]:
        history.append(("in", msg))
        transcript.append(("CLIENTE", msg))

        try:
            d = await _retry_call(
                lambda: brain.run_survey_turn(
                    survey_name=SURVEY_NAME,
                    nps_question=NPS_QUESTION,
                    history=history,
                    score=score,
                    reason=reason,
                    topics=topics,
                    followups=turns,
                ),
                what=f"turn:{persona['id']}",
            )
        except Exception as exc:  # noqa: BLE001
            transcript.append(("BOT", f"<<EXCEPTION: {exc!r}>>"))
            fell_back = True
            break
        finally:
            await asyncio.sleep(SLEEP_BETWEEN_CALLS)

        if d is None:
            transcript.append(("BOT", "<<FALLBACK: brain devolveu None>>"))
            fell_back = True
            # No app, cairia na máquina de estados. Para o eval, paramos aqui
            # e anotamos — fallback num caso difícil já é um sinal.
            break

        # --- replica o estado de _run_agent FIELMENTE ---
        nxt = d["next"]
        # Anti-loop do resolver
        if turns >= 5 and nxt not in TERMINAL:
            nxt = "close"

        transcript.append(("BOT", d["reply"]))
        history.append(("out", d["reply"]))

        if nxt == "opt_out":
            turns += 1
            closed_via = "opt_out"
            break
        if nxt == "handoff":
            # _handle_handoff: NÃO grava nota, encerra como handoff
            turns += 1
            closed_via = "handoff"
            break

        # score MUTÁVEL (corrige 10 -> 1)
        if d["score"] is not None:
            score = d["score"]
        if d["reason"]:
            reason = d["reason"]
        if d["topic"]:
            topics = list(dict.fromkeys([*topics, d["topic"]]))
        turns += 1

        if nxt == "close":
            closed_via = "close"
            break

    return {
        "id": persona["id"],
        "titulo": persona["titulo"],
        "score_final": score,
        "bucket_final": nps_bucket(score),
        "reason_final": reason,
        "topics": topics,
        "turns": turns,
        "closed_via": closed_via,
        "fell_back": fell_back,
        "transcript": transcript,
        "nota_esperada": persona["nota_esperada"],
        "comportamento": persona["comportamento_esperado_do_bot"],
        "descricao": persona["descricao"],
        "num_msgs_cliente": len(persona["mensagens_cliente"]),
    }


JUDGE_SYSTEM = """Você é um avaliador rigoroso de agentes de pesquisa NPS por WhatsApp (português brasileiro).
Recebe: a DESCRIÇÃO de uma persona difícil, o COMPORTAMENTO ESPERADO do bot, a NOTA QUE DEVERIA FICAR REGISTRADA,
o TRANSCRIPT REAL da conversa (CLIENTE/BOT) e o SCORE FINAL que o agente efetivamente registrou.

Avalie SÓ pelo transcript real. Seja honesto e duro: um bom humano tira 5; um robô de respostas prontas tira 1-2.
Responda SOMENTE com JSON válido:

{"nota_inteligencia": <inteiro 1-5>,
 "nota_capturada_correta": <true|false>,
 "repetiu_pergunta": <true|false>,
 "fechou_na_hora_certa": <true|false>,
 "tom_adequado": <true|false>,
 "problemas": ["<curto>", "..."],
 "veredito": "<1 frase>"}

Critérios:
- nota_inteligencia: 5 = indistinguível de um ótimo pesquisador humano (lê contexto, adapta tom, não se repete, fecha na hora). 1 = burro/robótico/surdo ao contexto.
- nota_capturada_correta: o SCORE FINAL bate com a nota_esperada? (null esperado e null registrado também conta como correto).
- repetiu_pergunta: o bot repetiu a MESMA pergunta (ou quase a mesma frase) em turnos diferentes?
- fechou_na_hora_certa: encerrou no momento certo — nem cedo demais (perdendo o motivo do detrator) nem tarde demais (enchendo o cliente)? Para handoff/opt-out, escalou/saiu quando devia?
- tom_adequado: empatia em nota baixa (sem "Massa!"/festa), comemoração leve em nota alta, acolhimento na fúria? Não comemorou uma nota baixa nem foi surdo a uma reclamação grave?
- problemas: liste objetivamente o que o bot errou (vazio se impecável). Cite a falha concreta do transcript.
- veredito: 1 frase resumindo o desempenho."""


async def judge_persona(llm: GroqLLM, result: dict) -> dict:
    transcript_txt = "\n".join(f"{who}: {body}" for who, body in result["transcript"])
    comportamento = "\n".join(f"- {c}" for c in result["comportamento"])
    nota_esp = result["nota_esperada"]
    user = (
        f"PERSONA: {result['titulo']}\n"
        f"DESCRIÇÃO: {result['descricao']}\n\n"
        f"COMPORTAMENTO ESPERADO DO BOT:\n{comportamento}\n\n"
        f"NOTA QUE DEVERIA FICAR REGISTRADA (answer_score): "
        f"{nota_esp if nota_esp is not None else 'null (nenhuma — opt-out/handoff)'}\n"
        f"SCORE QUE O AGENTE REGISTROU DE FATO: "
        f"{result['score_final'] if result['score_final'] is not None else 'null'}\n"
        f"COMO ENCERROU: {result['closed_via'] or 'não encerrou / fallback'}\n\n"
        f"TRANSCRIPT REAL:\n{transcript_txt}"
    )
    data = await _retry_call(
        lambda: llm.chat_json(JUDGE_SYSTEM, user, temperature=0.1, max_tokens=600),
        what=f"judge:{result['id']}",
    )
    await asyncio.sleep(SLEEP_BETWEEN_CALLS)
    if not data:
        return {
            "nota_inteligencia": None,
            "nota_capturada_correta": None,
            "repetiu_pergunta": None,
            "fechou_na_hora_certa": None,
            "tom_adequado": None,
            "problemas": ["<juiz indisponível — Groq devolveu None>"],
            "veredito": "<juiz indisponível>",
        }
    return data


def _bool_flag(v, true_s: str, false_s: str) -> str:
    if v is True:
        return true_s
    if v is False:
        return false_s
    return "?"


async def main() -> None:
    if not settings.groq_api_key:
        print("ERRO: GROQ_API_KEY ausente no ambiente/.env")
        sys.exit(1)
    print(f"Modelo Groq: {settings.groq_model}")
    print(f"Chave: ...{settings.groq_api_key[-6:]}\n")

    with open(PERSONAS_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    personas = data["personas"]
    print(f"Carregadas {len(personas)} personas.\n")

    llm = GroqLLM(settings.groq_api_key, settings.groq_model)
    brain = SurveyBrain(llm)

    results = []
    for i, p in enumerate(personas, 1):
        print(f"[{i}/{len(personas)}] Simulando '{p['id']}' "
              f"({len(p['mensagens_cliente'])} msgs do cliente)...", flush=True)
        res = await simulate_persona(brain, p)
        print(f"    → simulada: closed_via={res['closed_via']}, "
              f"turns={res['turns']}, fallback={res['fell_back']}. Julgando...", flush=True)
        verdict = await judge_persona(llm, res)
        res["judge"] = verdict
        results.append(res)
        ni = verdict.get("nota_inteligencia")
        print(f"    → juiz: inteligência={ni}/5, "
              f"capturou_certo={verdict.get('nota_capturada_correta')}\n", flush=True)

    _print_report(results)

    # dump bruto p/ inspeção posterior, se quiser
    out_path = os.path.join(_ROOT, "scripts", "_eval_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(
            [{k: v for k, v in r.items() if k != "comportamento"} for r in results],
            fh, ensure_ascii=False, indent=2,
        )
    print(f"\n[dump bruto salvo em {out_path}]")


def _print_report(results: list[dict]) -> None:
    line = "=" * 78
    print("\n\n" + line)
    print("RELATÓRIO — EVAL DO SURVEY AGENT (LLM REAL · Groq)")
    print(line)

    # --- Agregado ---
    ints = [r["judge"].get("nota_inteligencia") for r in results
            if isinstance(r["judge"].get("nota_inteligencia"), int)]
    avg = (sum(ints) / len(ints)) if ints else float("nan")
    capt_ok = sum(1 for r in results if r["judge"].get("nota_capturada_correta") is True)
    repetiu = sum(1 for r in results if r["judge"].get("repetiu_pergunta") is True)
    fechou_ok = sum(1 for r in results if r["judge"].get("fechou_na_hora_certa") is True)
    tom_ok = sum(1 for r in results if r["judge"].get("tom_adequado") is True)
    fb = sum(1 for r in results if r["fell_back"])
    n = len(results)

    print("\n### AGREGADO")
    print(f"Média de nota_inteligência (juiz): {avg:.2f} / 5   (n={len(ints)} válidas)")
    print(f"Notas capturadas corretas:        {capt_ok}/{n}")
    print(f"Fechou na hora certa:             {fechou_ok}/{n}")
    print(f"Tom adequado:                     {tom_ok}/{n}")
    print(f"Repetiu pergunta (ruim):          {repetiu}/{n}")
    print(f"Caiu em fallback (brain None):    {fb}/{n}")

    # --- Por persona (tabela) ---
    print("\n### POR PERSONA")
    hdr = f"{'id':<26} {'score':>5} {'esp':>4} {'IQ':>3} {'cap':>4} {'rep':>4} {'fech':>5} {'tom':>4}  veredito"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        j = r["judge"]
        esp = r["nota_esperada"]
        sc = r["score_final"]
        sc_s = str(sc) if sc is not None else "—"
        esp_s = str(esp) if esp is not None else "—"
        cap = _bool_flag(j.get("nota_capturada_correta"), "ok", "X")
        rep = _bool_flag(j.get("repetiu_pergunta"), "SIM", "nao")
        fch = _bool_flag(j.get("fechou_na_hora_certa"), "ok", "X")
        tom = _bool_flag(j.get("tom_adequado"), "ok", "X")
        iq = j.get("nota_inteligencia")
        iq_s = str(iq) if iq is not None else "?"
        flag = "" if sc == esp else "  <<NOTA!"
        ver = (j.get("veredito") or "")[:60]
        print(f"{r['id']:<26} {sc_s:>5} {esp_s:>4} {iq_s:>3} {cap:>4} {rep:>4} {fch:>5} {tom:>4}  {ver}{flag}")

    # --- Detalhe + problemas por persona ---
    print("\n### PROBLEMAS APONTADOS PELO JUIZ (por persona)")
    for r in results:
        j = r["judge"]
        probs = j.get("problemas") or []
        head = (f"\n[{r['id']}] score={r['score_final']} (esp {r['nota_esperada']}) · "
                f"closed={r['closed_via']} · IQ={j.get('nota_inteligencia')}/5")
        print(head)
        print(f"  reason_final: {r['reason_final']!r}")
        if probs:
            for pr in probs:
                print(f"  - {pr}")
        else:
            print("  - (sem problemas apontados)")

    # --- Transcripts dos 4 críticos ---
    print("\n\n" + line)
    print("TRANSCRIPTS REAIS — 4 CENÁRIOS CRÍTICOS")
    print(line)
    for r in results:
        if r["id"] not in CRITICAL:
            continue
        print(f"\n{'─' * 78}")
        print(f"### {r['id']} — {r['titulo']}")
        print(f"esperado: nota={r['nota_esperada']} | registrado: nota={r['score_final']} "
              f"({r['bucket_final']}) | encerrou: {r['closed_via']}")
        print(f"reason_final: {r['reason_final']!r}")
        print(f"{'─' * 78}")
        for who, body in r["transcript"]:
            print(f"  {who:<8}: {body}")
        j = r["judge"]
        print(f"  >>> JUIZ: IQ={j.get('nota_inteligencia')}/5 · "
              f"capturou_certo={j.get('nota_capturada_correta')} · "
              f"repetiu={j.get('repetiu_pergunta')} · fechou_certo={j.get('fechou_na_hora_certa')} · "
              f"tom_ok={j.get('tom_adequado')}")
        print(f"  >>> veredito: {j.get('veredito')}")


if __name__ == "__main__":
    asyncio.run(main())
