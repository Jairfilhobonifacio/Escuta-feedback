"""Mapa PERFIL -> SURVEY (função pura — sem I/O, sem SQLAlchemy).

Liga a "árvore de perfis" (app/domain/segmentation/profiles.py) às surveys de
WhatsApp definidas no seed (scripts/seed_bizzu.py). É a tabela de roteamento que
o disparo seletivo por perfil (scripts/dispatch_by_profile.py) consulta para
decidir QUAL survey mandar para QUEM.

Decisões de design:
  - As CHAVES são as constantes PROFILE_* (importadas de profiles.py), nunca
    strings soltas — assim um rename de perfil quebra aqui no import, não em runtime.
  - Os VALORES são o `name` da Survey (str), idêntico ao usado em SURVEYS no seed;
    None = "não contatar este perfil" (sem survey associada).
  - Os 13 perfis estão COBERTOS explicitamente. Qualquer perfil novo em profiles.py
    sem entrada aqui é pego pelo teste de cobertura (tests/test_profile_surveys.py).

PURA: dado um rótulo de perfil, devolve o nome da survey (ou None). Sem efeitos.
"""
from __future__ import annotations

from app.domain.segmentation.profiles import (
    PROFILE_ATIVO_EM_RISCO,
    PROFILE_ATIVO_FIEL,
    PROFILE_ATIVO_PASSIVO,
    PROFILE_ATIVO_PROMOTOR,
    PROFILE_ATIVO_RECENTE,
    PROFILE_ATIVO_SILENCIOSO,
    PROFILE_CHURN_INVOLUNTARIO,
    PROFILE_CHURN_OUTRO,
    PROFILE_CHURN_POS_USO,
    PROFILE_CHURN_RAPIDO,
    PROFILE_CORTESIA,
    PROFILE_EMBAIXADOR,
    PROFILE_INDEFINIDO,
    PROFILE_VAI_EXPIRAR,
)

# Nomes de survey — DEVEM bater com os `name` em scripts/seed_bizzu.py::SURVEYS.
SURVEY_NPS_BIZZU = "NPS Bizzu"
SURVEY_EXIT_BIZZU = "Exit Bizzu"
SURVEY_CSAT_ONBOARDING_BIZZU = "CSAT Onboarding Bizzu"
SURVEY_ESCUTA_DETRATOR_BIZZU = "Escuta de Detrator Bizzu"
SURVEY_RETENCAO_BIZZU = "Retenção Bizzu"
SURVEY_INDICACAO_BIZZU = "Indicação Bizzu"
# Campanha do plano ANUAL ATIVO (docs/campanhas/mensagens-anuais-ativos.md).
SURVEY_CHECKIN_BIZZU = "Check-in Bizzu"

# Roteamento perfil -> survey. None = perfil que NÃO deve ser contatado.
# Cobre os 13 perfis de profiles.py (falha de cobertura é pega no teste).
#
# Contrato (depended por dispatch_by_profile.py + tests/test_profile_surveys.py):
# os VALORES são str | None (o `name` PRIMÁRIO da survey). A alternância
# Check-in vs Indicação para os "fãs do produto" NÃO muda este contrato — vive
# em PROFILE_SURVEY_ROTATION + survey_cycle_for_profile (abaixo), opt-in do
# disparo. Assim survey_for_profile continua devolvendo um único nome estável.
PROFILE_TO_SURVEY: dict[str, str | None] = {
    # --- Ativos sem sinal forte: NPS padrão ---
    PROFILE_ATIVO_SILENCIOSO: SURVEY_NPS_BIZZU,
    PROFILE_ATIVO_PASSIVO: SURVEY_NPS_BIZZU,
    PROFILE_CORTESIA: SURVEY_NPS_BIZZU,
    # --- Onboarding (recém-chegado) ---
    PROFILE_ATIVO_RECENTE: SURVEY_CSAT_ONBOARDING_BIZZU,
    # --- Detrator ativo: escuta urgente ---
    PROFILE_ATIVO_EM_RISCO: SURVEY_ESCUTA_DETRATOR_BIZZU,
    # --- Ainda com acesso, prestes a expirar: retenção ---
    PROFILE_VAI_EXPIRAR: SURVEY_RETENCAO_BIZZU,
    # --- Fãs do produto: pedido de indicação/depoimento (default) ---
    # ativo_fiel/embaixador também recebem 'Check-in Bizzu' (relacionamento) na
    # alternância por cooldown — ver PROFILE_SURVEY_ROTATION. O PRIMÁRIO aqui segue
    # 'Indicação Bizzu' (não quebra os mapeamentos/contagens existentes).
    PROFILE_ATIVO_PROMOTOR: SURVEY_INDICACAO_BIZZU,
    PROFILE_ATIVO_FIEL: SURVEY_INDICACAO_BIZZU,
    PROFILE_EMBAIXADOR: SURVEY_INDICACAO_BIZZU,
    # --- Já cancelaram (voluntário): exit survey de churn ---
    PROFILE_CHURN_RAPIDO: SURVEY_EXIT_BIZZU,
    PROFILE_CHURN_POS_USO: SURVEY_EXIT_BIZZU,
    PROFILE_CHURN_OUTRO: SURVEY_EXIT_BIZZU,
    # --- Não contatar (já em winback por e-mail / dado anômalo) ---
    PROFILE_CHURN_INVOLUNTARIO: None,
    PROFILE_INDEFINIDO: None,
}

# Alternância (rotação) opcional perfil -> [surveys] em ORDEM DE PREFERÊNCIA.
# Mecanismo de "Check-in vs Indicação": para os fãs do produto (ativo_fiel/
# embaixador), o disparo alterna entre RELACIONAMENTO ('Check-in Bizzu' — só um oi
# + ouvir) e PEDIDO ('Indicação Bizzu' — depoimento/indicação). Política:
#   - manda a 1ª survey da lista cujo cooldown esteja OK para o contato;
#   - como ambas têm cooldown de 7 dias (e o Check-in é periódico, 60-90 dias),
#     na prática não se pede indicação duas vezes seguidas sem antes um check-in
#     leve — alterna naturalmente conforme o histórico de cada contato.
# Quem NÃO está aqui usa só o PROFILE_TO_SURVEY (lista de 1). Os nomes têm de
# existir em seed_bizzu.SURVEYS (garantido pelos testes de cobertura).
PROFILE_SURVEY_ROTATION: dict[str, list[str]] = {
    PROFILE_ATIVO_FIEL: [SURVEY_CHECKIN_BIZZU, SURVEY_INDICACAO_BIZZU],
    PROFILE_EMBAIXADOR: [SURVEY_CHECKIN_BIZZU, SURVEY_INDICACAO_BIZZU],
}


def survey_for_profile(profile: str) -> str | None:
    """Devolve o `name` da survey PRIMÁRIA para o perfil, ou None (= não contatar).

    PURA. Perfil desconhecido (fora de PROFILE_TO_SURVEY) -> None: nunca lança,
    o pior caso é "não contatar", que é o lado seguro.
    """
    return PROFILE_TO_SURVEY.get(profile)


def survey_cycle_for_profile(profile: str) -> list[str]:
    """Lista de surveys candidatas ao perfil, em ORDEM DE PREFERÊNCIA (alternância).

    PURA. Para perfis com rotação configurada (PROFILE_SURVEY_ROTATION) devolve as
    alternativas (ex.: ativo_fiel -> ['Check-in Bizzu', 'Indicação Bizzu']); para os
    demais, a survey primária embrulhada numa lista de 1 (ou [] se = não contatar /
    perfil desconhecido). O disparo escolhe a 1ª da lista com cooldown OK — é assim
    que "Check-in vs Indicação" se decide sem estado global, por contato.
    """
    rotation = PROFILE_SURVEY_ROTATION.get(profile)
    if rotation:
        return list(rotation)
    primary = PROFILE_TO_SURVEY.get(profile)
    return [primary] if primary is not None else []
