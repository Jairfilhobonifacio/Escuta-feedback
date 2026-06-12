"""Testes do mapa PERFIL -> SURVEY (app/domain/segmentation/profile_surveys.py).

pytest PURO (stdlib, sem banco, sem WAHA). Garante o contrato que o disparo
seletivo (scripts/dispatch_by_profile.py) depende:
  - todos os perfis de profiles.py (os 13 numerados + o residual 'indefinido')
    têm entrada em PROFILE_TO_SURVEY;
  - churn_involuntario e indefinido -> None (não contatar);
  - todo nome de survey retornado (não-None) existe em seed_bizzu.SURVEYS;
  - perfil desconhecido -> None (não quebra; lado seguro).

Rodar: py -m pytest tests/test_profile_surveys.py -q
       (a partir de C:\\Users\\jboni\\Documents\\Projetos\\escuta)
"""
import os
import sys

# permite rodar standalone (sem instalar o pacote)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.segmentation import profiles  # noqa: E402
from app.domain.segmentation.profiles import (  # noqa: E402
    PROFILE_CHURN_INVOLUNTARIO,
    PROFILE_INDEFINIDO,
)
from app.domain.segmentation.profile_surveys import (  # noqa: E402
    PROFILE_TO_SURVEY,
    survey_for_profile,
)
from scripts.seed_bizzu import SURVEYS  # noqa: E402


def _all_profile_labels() -> set[str]:
    """Coleta TODOS os rótulos PROFILE_* declarados em profiles.py.

    Lê os atributos do módulo cujo nome começa com PROFILE_ — assim, se alguém
    adicionar um 14º perfil, ele entra aqui automaticamente e o teste de cobertura
    passa a exigir uma entrada correspondente em PROFILE_TO_SURVEY.
    """
    return {
        getattr(profiles, name)
        for name in dir(profiles)
        if name.startswith("PROFILE_")
    }


def _survey_names_in_seed() -> set[str]:
    return {spec["name"] for spec in SURVEYS}


def test_cobre_todos_os_perfis_declarados():
    # A taxonomia da reunião numera 13 perfis (1-13) MAIS o residual '0. indefinido':
    # 14 rótulos PROFILE_* no total em profiles.py. O contrato real é "todo rótulo
    # tem entrada", então amarramos a contagem ao próprio módulo (sem número mágico)
    # e exigimos cobertura 1:1 no mapa.
    labels = _all_profile_labels()
    assert len(labels) == 14  # 13 perfis + indefinido (residual)
    assert labels == set(PROFILE_TO_SURVEY.keys())


def test_todos_os_perfis_tem_entrada_no_mapa():
    labels = _all_profile_labels()
    faltando = labels - set(PROFILE_TO_SURVEY.keys())
    assert not faltando, f"perfis sem entrada em PROFILE_TO_SURVEY: {sorted(faltando)}"
    # E o mapa não inventa perfis que não existem em profiles.py.
    sobrando = set(PROFILE_TO_SURVEY.keys()) - labels
    assert not sobrando, f"chaves em PROFILE_TO_SURVEY que não são perfis válidos: {sorted(sobrando)}"


def test_churn_involuntario_e_indefinido_nao_contatam():
    assert PROFILE_TO_SURVEY[PROFILE_CHURN_INVOLUNTARIO] is None
    assert PROFILE_TO_SURVEY[PROFILE_INDEFINIDO] is None
    assert survey_for_profile(PROFILE_CHURN_INVOLUNTARIO) is None
    assert survey_for_profile(PROFILE_INDEFINIDO) is None


def test_todo_nome_de_survey_retornado_existe_no_seed():
    seed_names = _survey_names_in_seed()
    for profile, survey_name in PROFILE_TO_SURVEY.items():
        if survey_name is None:
            continue
        assert survey_name in seed_names, (
            f"perfil {profile!r} mapeia para survey {survey_name!r}, "
            f"que NÃO existe em seed_bizzu.SURVEYS ({sorted(seed_names)})"
        )


def test_survey_for_profile_perfil_desconhecido_retorna_none():
    assert survey_for_profile("perfil_que_nao_existe") is None
    assert survey_for_profile("") is None


def test_survey_for_profile_bate_com_o_mapa():
    # survey_for_profile é só um .get() sobre o mapa — garante que não diverge.
    for profile, expected in PROFILE_TO_SURVEY.items():
        assert survey_for_profile(profile) == expected
