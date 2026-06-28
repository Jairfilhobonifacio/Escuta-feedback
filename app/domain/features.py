"""Central de Controle do Agente — feature flags por ORGANIZAÇÃO em runtime.

O env (`settings`) é o DEFAULT (e, para as perigosas, o PISO/kill-switch). O painel
grava overrides por org em `Organization.settings["features"][key]`, lidos em runtime
SEM re-deploy. Duas semânticas:

- SEGURA: o painel controla LIVREMENTE. `override` vence; sem override, vale o env.
  (O dono precisa conseguir LIGAR mesmo com o env OFF.)
- PERIGOSA (`DANGEROUS`): o env é PISO/kill-switch. O painel NUNCA liga o que o deploy
  desligou (protege contra ban do WhatsApp / custo Groq). Só fica ON se o env permitir
  E (override ou env) — e o painel ainda pode DESLIGAR.

Reusa o padrão de config por-org já existente (copia-edita-reatribui o dict do JSONB
para marcá-lo sujo; SEM migration).
"""
from __future__ import annotations

from typing import Any

from app.config import settings

# Features que o painel NUNCA pode LIGAR sozinho: o env é piso/kill-switch. Protege
# contra ban do WhatsApp (envio real) e custo de Groq disparados fora do deploy.
DANGEROUS: set[str] = {"voc_agent_enabled", "voc_whatsapp_tool_enabled"}

# Catálogo das features gerenciáveis pela Central do Agente — rótulos/descrições na
# LINGUAGEM DO DONO (não jargão de código). `grupo` organiza a UI.
#
# NOTA (Fase 1): `sentiment_pt_v2_enabled` e `correction_loop_enabled` são lidos no
# brain.py de forma GLOBAL (sem `org` à mão no call-site) — o override por-org já é
# gravado e aparece no GET, mas o gate efetivo dessas duas ainda é por ENV até o
# refactor que leva `org` ao construtor do brain. As demais seguras já respeitam o
# override por-org em runtime.
FEATURES: list[dict[str, Any]] = [
    {
        "key": "response_suggestion_enabled",
        "label": "Sugerir resposta com IA",
        "grupo": "Atendimento automático",
        "descricao": (
            "Gera um rascunho de resposta para você revisar e enviar. Nunca envia "
            "sozinho — é só um atalho para você não começar do zero."
        ),
        "dangerous": False,
    },
    {
        "key": "playbooks_inline_enabled",
        "label": "Playbooks automáticos na hora do evento",
        "grupo": "Atendimento automático",
        "descricao": (
            "Dispara os playbooks de CS no momento do evento (ex.: um cliente detrator "
            "já vira tarefa na hora, sem você precisar rodar nada na mão)."
        ),
        "dangerous": False,
    },
    {
        "key": "esteira_enabled",
        "label": "Esteira automática do quadro",
        "grupo": "Organização",
        "descricao": (
            "Ao concluir uma tarefa ou entregar uma melhoria, resolve sozinho os "
            "feedbacks ligados a ela — o quadro anda sem trabalho repetido."
        ),
        "dangerous": False,
    },
    {
        "key": "clustering_inline_enabled",
        "label": "Agrupar dores em tempo real",
        "grupo": "Inteligência",
        "descricao": (
            "Indexa cada feedback assim que ele chega, para o Mapeamento de dores ficar "
            "sempre atualizado (em vez de só quando você reprocessa em lote)."
        ),
        "dangerous": False,
    },
    {
        "key": "sentiment_pt_v2_enabled",
        "label": "Leitura de sentimento (PT) mais fina",
        "grupo": "Inteligência",
        "descricao": (
            "Entende melhor ironia, negação e gíria em português — e, quando fica em "
            "dúvida, prefere não chutar a marcar errado."
        ),
        "dangerous": False,
    },
    {
        "key": "correction_loop_enabled",
        "label": "Aprender com as suas correções",
        "grupo": "Inteligência",
        "descricao": (
            "Usa as classificações que você corrigiu na mão como exemplo, para a IA "
            "acertar mais nas próximas parecidas."
        ),
        "dangerous": False,
    },
    {
        "key": "voc_agent_enabled",
        "label": "Agente de conversa autônomo",
        "grupo": "Atendimento automático",
        "descricao": (
            "Deixa a IA conduzir a conversa da pesquisa sozinha. Liberado só pelo deploy "
            "(risco de custo) — por isso pode aparecer travado aqui."
        ),
        "dangerous": True,
    },
    {
        "key": "voc_whatsapp_tool_enabled",
        "label": "Deixar o agente enviar WhatsApp",
        "grupo": "Atendimento automático",
        "descricao": (
            "Permite o agente enviar mensagens no WhatsApp por conta própria. Liberado "
            "só pelo deploy (risco de banimento) — por isso pode aparecer travado aqui."
        ),
        "dangerous": True,
    },
]

_BY_KEY: dict[str, dict[str, Any]] = {f["key"]: f for f in FEATURES}


def _override(org: Any, key: str) -> Any:
    """Override por-org de `key` em settings["features"], ou None se não houver."""
    feats = (getattr(org, "settings", None) or {}).get("features") or {}
    return feats.get(key)


def feature_enabled(org: Any, key: str) -> bool:
    """A feature `key` está LIGADA para esta org? (ver semântica no topo do módulo)."""
    env_default = bool(getattr(settings, key, False))
    override = _override(org, key)
    effective = override if override is not None else env_default
    if key in DANGEROUS:
        # Env é PISO/kill-switch: só liga se o deploy permitir.
        return env_default and bool(effective)
    return bool(effective)


def feature_locked(key: str) -> bool:
    """Travada = perigosa com o env OFF (o painel não consegue ligar)."""
    return key in DANGEROUS and not bool(getattr(settings, key, False))


def agent_config_view(org: Any) -> list[dict[str, Any]]:
    """Snapshot do catálogo + estado por org para a Central do Agente (contrato do GET)."""
    return [
        {
            "key": f["key"],
            "label": f["label"],
            "grupo": f["grupo"],
            "descricao": f["descricao"],
            "enabled": feature_enabled(org, f["key"]),
            "locked": feature_locked(f["key"]),
        }
        for f in FEATURES
    ]


def set_feature(org: Any, key: str, enabled: bool) -> None:
    """Grava o override por-org de `key` (copia-edita-reatribui o JSONB; SEM migration).

    - `KeyError` se `key` não está no catálogo (o endpoint traduz para 422).
    - Se a feature está TRAVADA (perigosa + env OFF), NÃO altera nada (no-op): o painel
      nunca liga o que o deploy desligou.
    """
    if key not in _BY_KEY:
        raise KeyError(key)
    if feature_locked(key):
        return
    s = dict(getattr(org, "settings", None) or {})
    feats = dict(s.get("features") or {})
    feats[key] = bool(enabled)
    s["features"] = feats
    org.settings = s  # reatribui p/ marcar o JSONB sujo (padrão boards/config).
