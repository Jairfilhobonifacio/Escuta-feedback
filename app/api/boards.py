"""BOARDS CRUD DINÂMICO — kanbans customizados pelo operador.

Tudo sem migration e sem tocar o schema: os boards vivem em
`Organization.settings["boards"]` = lista de:

    {
      "id": "<uuid>",
      "nome": "Triagem",
      "entidade": "feedback" | "cliente",   # ausente => "feedback" (retrocompat)
      "campo": <ver abaixo, por entidade>,
      "colunas": [{"id", "nome", "valor", "cor"?}, ...]
    }

Cada board agrupa uma ENTIDADE:

- entidade == "feedback" (default quando ausente): cards são FeedbackItem.
  - `campo == "action_status"`: cada coluna agrupa os FeedbackItem cujo
    `action_status == coluna.valor` (o board "operacional", como o board fixo do
    admin.py mas agora editável e com colunas livres).
  - `campo == "selo"`: cada coluna agrupa os feedbacks dos CONTATOS que têm o selo
    `coluna.valor` aplicado (o board "campanha win-back" sobre os selos da camada
    de campanha — reusa a mesma noção de selo de profile_data["selos"]).

- entidade == "cliente": cards são Contact (mesma forma do GET /api/clientes).
  - `campo == "selo"`:   contato com `coluna.valor` em profile_data["selos"].
  - `campo == "estado"`: contato com partner.subscription.state == coluna.valor.
  - `campo == "perfil"`: contato com partner.profile == coluna.valor (ou startswith
    para a coluna "churn"). Estado e perfil são READ-ONLY (vêm da API de Clientes).

- entidade == "tarefa" (Fase C): cards são CsTask agrupadas por `campo == "status"`
  (CsTask.status: aberta/em_andamento/concluida/adiada). O status muda via
  PATCH /api/tarefas/{id} (não há board-move de tarefa).

- entidade == "melhoria" (Fase C): cards são Improvement agrupadas por
  `campo == "status"` (Improvement.status: ideia/planejada/em_andamento/entregue/
  descartada). O status muda via PATCH /api/improvements/{id} (não há board-move).

Padrão obrigatório COPIA-EDITA-REATRIBUI para marcar o JSONB sujo (idem
campanha.py): s = dict(org.settings or {}); s["boards"] = nova_lista; org.settings = s.

O router é montado com prefixo /api no main.py, então as rotas são SEM o /api.
Reusa `_get_org` (admin.py), `_feedback_out`/`compute_urgencia` (admin.py) e a
lógica de selos do campanha.py (catálogo + aplicação em contato).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import (
    ACTION_STATUSES,
    _feedback_out,
    _get_org,
    _nps_bucket_label,
    _partner_fields,
)
from app.api.campanha import (
    _selos_do_contato,
    _set_selos_do_contato,
    _upsert_catalogo,
)
from app.api.tasks import _PRIORITY_RANK, _feedback_preview
from app.db import get_session
from app.domain.contacts.whatsapp import classify_phone, tem_whatsapp
from app.domain.cs.health import compute_health
from app.models.cluster import FeedbackCluster
from app.models.core import Contact, Organization
from app.models.feedback import FeedbackItem
from app.models.improvement import Improvement
from app.models.playbook import CsTask
from app.models.survey import Message

router = APIRouter(tags=["boards"])

# Entidade que um board agrupa: 'feedback' (FeedbackItem, o board clássico),
# 'cliente' (Contact), 'tarefa' (CsTask) ou 'melhoria' (Improvement). Ausente =>
# 'feedback' (retrocompat com os boards já salvos). Fase C — "board universal": os 3
# kanbans (board, tarefas, melhorias) viram UM motor agrupando entidades diferentes.
ENTIDADE_FEEDBACK = "feedback"
ENTIDADE_CLIENTE = "cliente"
ENTIDADE_TAREFA = "tarefa"
ENTIDADE_MELHORIA = "melhoria"
BOARD_ENTIDADES: tuple[str, ...] = (
    ENTIDADE_FEEDBACK,
    ENTIDADE_CLIENTE,
    ENTIDADE_TAREFA,
    ENTIDADE_MELHORIA,
)

# Campos válidos POR ENTIDADE. Para feedback: 'action_status' = workflow do feedback;
# 'selo' = selo de campanha aplicado ao CONTATO (como hoje). Para cliente: 'selo' =
# selo aplicado ao contato; 'estado' = subscription.state do snapshot partner; 'perfil'
# = partner.profile do snapshot. Para tarefa/melhoria: 'status' = a COLUNA de status já
# existente (CsTask.status: aberta/em_andamento/concluida/adiada; Improvement.status:
# ideia/planejada/em_andamento/entregue/descartada). ATENÇÃO: há 2 conceitos "status" —
# o de feedback é 'action_status'; o de tarefa/melhoria é 'status'. Validado na API.
BOARD_CAMPOS_POR_ENTIDADE: dict[str, tuple[str, ...]] = {
    ENTIDADE_FEEDBACK: ("action_status", "selo"),
    ENTIDADE_CLIENTE: ("selo", "estado", "perfil"),
    ENTIDADE_TAREFA: ("status",),
    ENTIDADE_MELHORIA: ("status",),
}

# União de todos os campos conhecidos (retrocompat: BOARD_CAMPOS continua sendo o
# vocabulário de feedback usado pelo board-move de feedback).
BOARD_CAMPOS: tuple[str, ...] = BOARD_CAMPOS_POR_ENTIDADE[ENTIDADE_FEEDBACK]

# Quantos cards mostrar por coluna (os mais urgentes/recentes). `count` traz o total
# real; `items` é o recorte priorizado para a tela não estourar (≈30, mesma ideia do
# board fixo do admin.py, mas mais cards porque o board dinâmico pode ter menos colunas).
BOARD_ITEMS_PER_COLUMN = 30

_COR_DEFAULT = "#6366f1"  # token --indigo do design system do painel.


# --- Boards default (quando a org ainda não tem nenhum board salvo) -----------


# Selos do board "Follow-up" (Trello simples do dono): grupo MUTUAMENTE EXCLUSIVO.
# Aplicar um remove os outros dois do contato (single-membership = card vive em UMA
# coluna só). "nao_respondeu" = abordado e ainda sem resposta. Reusa o mecanismo de
# selo existente (catálogo + profile_data["selos"]); a exclusividade é aplicada no move.
FOLLOWUP_SELO_CONTATADO = "contatado"
FOLLOWUP_SELO_RESPONDEU = "respondeu"
FOLLOWUP_SELO_NAO_RESPONDEU = "nao_respondeu"
FOLLOWUP_SELOS: tuple[str, ...] = (
    FOLLOWUP_SELO_CONTATADO,
    FOLLOWUP_SELO_RESPONDEU,
    FOLLOWUP_SELO_NAO_RESPONDEU,
)


def _board_default_followup() -> dict[str, Any]:
    """Board default que ABRE por padrão em /board: o "Trello simples" do dono.

    3 colunas de acompanhamento por SELO (mecanismo de campanha já existente):
    Contatados (selo 'contatado'), Respondidos ('respondeu') e Não responderam
    ('nao_respondeu' = abordado e ainda sem resposta). Os 3 selos formam um grupo
    mutuamente exclusivo (ver FOLLOWUP_SELOS): mover um card aplica o selo da coluna
    e remove os outros dois — o card vive em UMA coluna só (single-membership Trello).
    """
    etapas = [
        (FOLLOWUP_SELO_CONTATADO, "Contatados", "#6c5ce7"),
        (FOLLOWUP_SELO_RESPONDEU, "Respondidos", "#22c55e"),
        (FOLLOWUP_SELO_NAO_RESPONDEU, "Não responderam", "#82809a"),
    ]
    return {
        "id": "default-followup",
        "nome": "Follow-up",
        "entidade": ENTIDADE_FEEDBACK,
        "campo": "selo",
        "colunas": [
            {"id": valor, "nome": nome, "valor": valor, "cor": cor} for valor, nome, cor in etapas
        ],
    }


def _board_default_triagem() -> dict[str, Any]:
    """Board operacional default: 1 coluna por action_status do funil do admin.py."""
    return {
        "id": "default-triagem",
        "nome": "Triagem",
        "entidade": ENTIDADE_FEEDBACK,
        "campo": "action_status",
        "colunas": [
            {"id": s, "nome": s.replace("_", " ").capitalize(), "valor": s, "cor": _COR_DEFAULT}
            for s in ACTION_STATUSES
        ],
    }


def _board_default_winback() -> dict[str, Any]:
    """Board de campanha default (sobre FEEDBACKS): 1 coluna por etapa de selo win-back."""
    etapas = [
        ("contatado", "Contatado", "#6366f1"),
        ("respondeu", "Respondeu", "#22c55e"),
        ("cortesia", "Cortesia", "#ffd700"),
        ("reativou", "Reativou", "#06b6d4"),
    ]
    return {
        "id": "default-winback",
        "nome": "Campanha win-back",
        "entidade": ENTIDADE_FEEDBACK,
        "campo": "selo",
        "colunas": [
            {"id": valor, "nome": nome, "valor": valor, "cor": cor} for valor, nome, cor in etapas
        ],
    }


def _board_default_winback_clientes() -> dict[str, Any]:
    """Board win-back default por CLIENTE: 1 coluna por etapa de selo win-back."""
    etapas = [
        ("contatado", "Contatado", "#6366f1"),
        ("respondeu", "Respondeu", "#22c55e"),
        ("cortesia", "Cortesia", "#ffd700"),
        ("reativou", "Reativou", "#06b6d4"),
    ]
    return {
        "id": "default-clientes-winback",
        "nome": "Win-back (clientes)",
        "entidade": ENTIDADE_CLIENTE,
        "campo": "selo",
        "colunas": [
            {"id": valor, "nome": nome, "valor": valor, "cor": cor} for valor, nome, cor in etapas
        ],
    }


def _board_default_cancelados_estado() -> dict[str, Any]:
    """Board default por CLIENTE agrupado pelo estado da assinatura (snapshot partner)."""
    etapas = [
        ("cancelled", "Cancelou", "#ef4444"),
        ("paid_without_access", "Pagou sem acesso", "#ffd700"),
        ("active_paying", "Ativo", "#22c55e"),
    ]
    return {
        "id": "default-clientes-estado",
        "nome": "Cancelados por estado",
        "entidade": ENTIDADE_CLIENTE,
        "campo": "estado",
        "colunas": [
            {"id": valor, "nome": nome, "valor": valor, "cor": cor} for valor, nome, cor in etapas
        ],
    }


def _board_default_tarefas() -> dict[str, Any]:
    """Board default de TAREFAS de CS: 1 coluna por status da fila (CsTask.status)."""
    etapas = [
        ("aberta", "Aberta", "#6366f1"),
        ("em_andamento", "Em andamento", "#06b6d4"),
        ("concluida", "Concluída", "#22c55e"),
        ("adiada", "Adiada", "#f59e0b"),
    ]
    return {
        "id": "default-tarefas",
        "nome": "Tarefas (CS)",
        "entidade": ENTIDADE_TAREFA,
        "campo": "status",
        "colunas": [
            {"id": valor, "nome": nome, "valor": valor, "cor": cor} for valor, nome, cor in etapas
        ],
    }


def _board_default_roadmap() -> dict[str, Any]:
    """Board default de MELHORIAS (roadmap): 1 coluna por estágio (Improvement.status)."""
    etapas = [
        ("ideia", "Ideia", "#6366f1"),
        ("planejada", "Planejada", "#06b6d4"),
        ("em_andamento", "Em andamento", "#f59e0b"),
        ("entregue", "Entregue", "#22c55e"),
        ("descartada", "Descartada", "#ef4444"),
    ]
    return {
        "id": "default-roadmap",
        "nome": "Roadmap",
        "entidade": ENTIDADE_MELHORIA,
        "campo": "status",
        "colunas": [
            {"id": valor, "nome": nome, "valor": valor, "cor": cor} for valor, nome, cor in etapas
        ],
    }


def _boards_default() -> list[dict[str, Any]]:
    # Follow-up vem PRIMEIRO: é o board que abre por padrão em /board (o "Trello
    # simples" do dono). Os demais seguem na ordem canônica anterior.
    return [
        _board_default_followup(),
        _board_default_triagem(),
        _board_default_winback(),
        _board_default_winback_clientes(),
        _board_default_cancelados_estado(),
        _board_default_tarefas(),
        _board_default_roadmap(),
    ]


# --- Acesso/normalização dos boards no settings (copia-edita-reatribui) -------


def _normalize_coluna(raw: Any) -> dict[str, Any] | None:
    """Normaliza uma coluna {id, nome, valor, cor?}, tolerante a sujeira; None se inválida."""
    if not isinstance(raw, dict):
        return None
    valor = raw.get("valor")
    if valor is None or str(valor).strip() == "":
        return None
    valor_s = str(valor).strip()
    nome = str(raw.get("nome") or valor_s).strip() or valor_s
    cid = str(raw.get("id") or valor_s).strip() or valor_s
    cor = str(raw.get("cor") or _COR_DEFAULT).strip() or _COR_DEFAULT
    return {"id": cid, "nome": nome, "valor": valor_s, "cor": cor}


def _normalize_board(raw: Any) -> dict[str, Any] | None:
    """Normaliza um board do settings, tolerante a sujeira; None se inválido.

    `entidade` ausente => 'feedback' (retrocompat: boards salvos antes deste campo).
    `campo` precisa ser compatível com a `entidade` (BOARD_CAMPOS_POR_ENTIDADE).
    """
    if not isinstance(raw, dict):
        return None
    bid = str(raw.get("id") or "").strip()
    nome = str(raw.get("nome") or "").strip()
    entidade = str(raw.get("entidade") or ENTIDADE_FEEDBACK).strip() or ENTIDADE_FEEDBACK
    campo = str(raw.get("campo") or "").strip()
    if not bid or not nome or entidade not in BOARD_ENTIDADES:
        return None
    if campo not in BOARD_CAMPOS_POR_ENTIDADE[entidade]:
        return None
    colunas: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for c in raw.get("colunas") or []:
        nc = _normalize_coluna(c)
        if nc is None:
            continue
        # Dedup por `valor` (mantém a 1ª): colunas com valor repetido viram clones e
        # quebram o drag-drop (card duplica/some). Descarta as repetições.
        if nc["valor"] in vistos:
            continue
        vistos.add(nc["valor"])
        colunas.append(nc)
    return {"id": bid, "nome": nome, "entidade": entidade, "campo": campo, "colunas": colunas}


def _boards(org: Organization) -> list[dict[str, Any]]:
    """Boards salvos da org (normalizados), tolerante a None/sujeira. [] se nenhum."""
    raw = (org.settings or {}).get("boards")
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for b in raw:
            nb = _normalize_board(b)
            if nb is not None:
                out.append(nb)
    return out


def _set_boards(org: Organization, boards: list[dict[str, Any]]) -> None:
    """Reatribui a lista de boards no settings (marca o JSONB como sujo)."""
    s = dict(org.settings or {})
    s["boards"] = boards
    org.settings = s


def _default_ids() -> set[str]:
    return {b["id"] for b in _boards_default()}


def _removed_defaults(org: Organization) -> list[str]:
    """Ids de boards DEFAULT que o operador deletou de propósito (tombstones) — para
    não reaparecerem no merge da listagem. Tolerante a sujeira."""
    raw = (org.settings or {}).get("boards_defaults_removidos")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str) and x.strip()]


def _set_removed_defaults(org: Organization, ids: list[str]) -> None:
    """Reatribui a lista de defaults removidos no settings (marca o JSONB como sujo)."""
    s = dict(org.settings or {})
    s["boards_defaults_removidos"] = ids
    org.settings = s


def _visible_boards(org: Organization) -> list[dict[str, Any]]:
    """Boards visíveis = defaults (não removidos, versão editada se materializada) na
    ordem canônica + boards customizados na ordem em que foram criados.

    Materializar/editar UM board nunca esconde os outros defaults: a listagem sempre
    mescla os salvos com os defaults pendentes (em vez de devolver só os salvos)."""
    persisted = _boards(org)
    by_id = {b["id"]: b for b in persisted}
    removidos = set(_removed_defaults(org))
    out: list[dict[str, Any]] = []
    for d in _boards_default():
        if d["id"] in removidos:
            continue
        out.append(by_id.get(d["id"], d))  # versão materializada (editada) tem prioridade
    default_ids = _default_ids()
    for b in persisted:
        if b["id"] not in default_ids:
            out.append(b)
    return out


def _find_board(org: Organization, board_id: str) -> dict[str, Any] | None:
    """Acha um board por id — primeiro nos salvos, senão nos defaults (sem persistir).
    Um default que foi deletado (tombstone) não é encontrado."""
    for b in _boards(org):
        if b["id"] == board_id:
            return b
    if board_id in _removed_defaults(org):
        return None
    for b in _boards_default():
        if b["id"] == board_id:
            return b
    return None


# --- CRUD ---------------------------------------------------------------------


class ColunaIn(BaseModel):
    id: str | None = Field(default=None, max_length=60)
    nome: str | None = Field(default=None, max_length=80)
    valor: str = Field(min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=32)


class BoardIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    # Entidade agrupada pelo board. Ausente => 'feedback' (retrocompat).
    entidade: str = Field(default=ENTIDADE_FEEDBACK, max_length=20)
    campo: str = Field(min_length=1, max_length=40)
    colunas: list[ColunaIn] = Field(default_factory=list)


class BoardPatchIn(BaseModel):
    """PATCH parcial: nome e/ou colunas. `model_fields_set` distingue ausente de null."""

    nome: str | None = Field(default=None, min_length=1, max_length=80)
    colunas: list[ColunaIn] | None = None


def _colunas_from_in(colunas: list[ColunaIn]) -> list[dict[str, Any]]:
    """Converte colunas do corpo (Pydantic) em colunas normalizadas para persistir."""
    out: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for c in colunas:
        valor = (c.valor or "").strip()
        if not valor:
            continue
        # Dedup por `valor` (mantém a 1ª): valores repetidos viram colunas-clone e
        # quebram o drag-drop (card duplica/some). Descarta as repetições.
        if valor in vistos:
            continue
        vistos.add(valor)
        nome = (c.nome or "").strip() or valor
        cid = (c.id or "").strip() or valor
        cor = (c.cor or "").strip() or _COR_DEFAULT
        out.append({"id": cid, "nome": nome, "valor": valor, "cor": cor})
    return out


@router.get("/boards")
async def list_boards(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Lista os boards da org: os 6 defaults (Triagem por action_status, Campanha
    win-back por selo, Win-back/clientes por selo, Cancelados por estado, Tarefas (CS)
    por status, Roadmap por status) mesclados com os boards customizados. Editar/criar um
    board nunca esconde os demais defaults; só um DELETE explícito de um default o remove
    (via tombstone). Defaults não são persistidos até serem editados."""
    org = await _get_org(session)
    return _visible_boards(org)


@router.post("/boards", status_code=201)
async def create_board(body: BoardIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Cria um board (id gerado). `entidade` ∈ {feedback, cliente} (default feedback).
    `campo` deve ser compatível com a entidade (422 se incompatível):
    feedback => {action_status, selo}; cliente => {selo, estado, perfil}. Colunas
    opcionais."""
    org = await _get_org(session)
    entidade = (body.entidade or ENTIDADE_FEEDBACK).strip() or ENTIDADE_FEEDBACK
    if entidade not in BOARD_ENTIDADES:
        raise HTTPException(
            status_code=422,
            detail=f"entidade inválida: '{body.entidade}' (use {', '.join(BOARD_ENTIDADES)})",
        )
    campos_ok = BOARD_CAMPOS_POR_ENTIDADE[entidade]
    campo = body.campo.strip()
    if campo not in campos_ok:
        raise HTTPException(
            status_code=422,
            detail=(
                f"campo inválido: '{body.campo}' para entidade '{entidade}' "
                f"(use {', '.join(campos_ok)})"
            ),
        )
    nome = body.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome do board não pode ser vazio")

    board = {
        "id": uuid.uuid4().hex,
        "nome": nome,
        "entidade": entidade,
        "campo": campo,
        "colunas": _colunas_from_in(body.colunas),
    }
    # Anexa o novo board aos salvos. Os defaults continuam aparecendo na listagem porque
    # GET /boards mescla salvos + defaults (ver _visible_boards), então criar não os apaga.
    boards = _boards(org) or []
    boards.append(board)
    _set_boards(org, boards)
    await session.commit()
    return board


@router.patch("/boards/{board_id}")
async def update_board(
    board_id: str, body: BoardPatchIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Edita nome e/ou colunas de um board. Editar um board DEFAULT o materializa nos
    settings (com o id default) — a partir daí ele é um board real, editável. 404 se
    o id não bate nem com um board salvo nem com um default."""
    org = await _get_org(session)
    sent = body.model_fields_set

    boards = _boards(org)
    target = next((b for b in boards if b["id"] == board_id), None)

    if target is None:
        # Talvez seja um default ainda não materializado — materializa e segue editando.
        default = next((b for b in _boards_default() if b["id"] == board_id), None)
        if default is None:
            raise HTTPException(status_code=404, detail="board não encontrado")
        target = default
        boards = [*boards, target]

    if "nome" in sent and body.nome is not None:
        nome = body.nome.strip()
        if not nome:
            raise HTTPException(status_code=422, detail="nome do board não pode ser vazio")
        target["nome"] = nome
    if "colunas" in sent and body.colunas is not None:
        target["colunas"] = _colunas_from_in(body.colunas)

    _set_boards(org, boards)
    # Editar um default ressuscita-o se estava com tombstone (senão sumiria do merge).
    if board_id in _default_ids():
        rem = _removed_defaults(org)
        if board_id in rem:
            _set_removed_defaults(org, [x for x in rem if x != board_id])
    await session.commit()
    return target


@router.delete("/boards/{board_id}", status_code=200)
async def delete_board(board_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Remove um board. Customizado: tira da lista salva. Default (materializado ou não):
    tira da lista salva E grava um tombstone para não reaparecer no merge da listagem.
    Idempotente: remover um id inexistente/já-removido é no-op com `removido=False`."""
    org = await _get_org(session)
    boards = _boards(org)
    novos = [b for b in boards if b["id"] != board_id]
    removido = len(novos) != len(boards)
    if removido:
        _set_boards(org, novos)

    # Default (mesmo nunca materializado): registra tombstone p/ sumir da listagem mesclada.
    if board_id in _default_ids():
        rem = _removed_defaults(org)
        if board_id not in rem:
            rem.append(board_id)
            _set_removed_defaults(org, rem)
            removido = True

    if removido:
        await session.commit()
    return {"removido": removido, "id": board_id}


# --- ITEMS por coluna ---------------------------------------------------------

# Status terminal de uma CsTask (não conta como "tarefa aberta" no card de cliente).
_CS_TASK_DONE = "concluida"


# --- FILTROS do board (Fase E) ------------------------------------------------
# Os filtros são query params OPCIONAIS de GET /boards/{id}/items. Ausentes => o board
# inteiro (comportamento anterior). São aplicados ao conjunto base ANTES do agrupamento,
# então TANTO os `items` QUANTO o `count` de cada coluna refletem o filtro (coerência
# total). O vocabulário ESPELHA o de admin.py:
#   - GET /api/feedbacks  -> _apply_contact_filters (estado/perfil/plan_type/tem_whatsapp/
#     nps_bucket via o CONTATO juntado) + colunas do FeedbackItem (team_tag/assignee/abordado);
#   - GET /api/clientes   -> estado/perfil/plan_type (JSON) + nps_bucket/health_band/
#     tem_whatsapp (post-filter sobre o card/contato).
# Aqui os conjuntos já são carregados inteiros e agrupados em Python, então aplicamos os
# mesmos predicados em Python (não há SQL a espelhar — só o vocabulário). Filtros que não
# se aplicam à entidade do board são IGNORADOS (no-op, sem erro).


class BoardItemFilters(BaseModel):
    """Filtros opcionais de GET /boards/{id}/items. Ausentes (None) = sem filtro.

    Mesmo vocabulário dos filtros de admin.py (list_feedbacks / list_clientes). Cada
    entidade só usa os que lhe dizem respeito; os demais são ignorados sem erro.
    """

    # Comuns "por tipo de cliente" (via o CONTATO): feedback + cliente.
    estado: str | None = None
    plan_type: str | None = None
    perfil: str | None = None
    tem_whatsapp: str | None = None  # 'sim' | 'nao'
    nps_bucket: str | None = None  # 'promotor' | 'neutro' | 'detrator'
    # Só feedback (colunas do FeedbackItem).
    team_tag: str | None = None
    assignee: str | None = None
    abordado: bool | None = None
    # Só cliente (post-filter sobre o card).
    health_band: str | None = None  # 'healthy' | 'watch' | 'at_risk'
    # Só tarefa (colunas do CsTask).
    owner: str | None = None
    priority: str | None = None
    # Só melhoria (coluna do Improvement).
    effort: str | None = None


def _plan_type_do_contato(contact: Contact) -> str | None:
    """partner.subscription.planType do snapshot, ou None (espelha list_clientes)."""
    sub = (((contact.profile_data or {}).get("partner") or {}).get("subscription") or {})
    pt = sub.get("planType")
    return str(pt) if pt else None


def _contato_passa_filtros(
    contact: Contact | None, f: BoardItemFilters, now: datetime
) -> bool:
    """True se o CONTATO casa os filtros "por tipo de cliente" (estado/perfil/plan_type/
    tem_whatsapp/nps_bucket). Espelha _apply_contact_filters + os post-filters de
    list_clientes, mas em Python (o conjunto já está carregado). Contato None nunca casa
    quando há algum desses filtros ativo (não dá para avaliar o snapshot partner)."""
    ativos = (
        f.estado is not None
        or f.perfil is not None
        or f.plan_type is not None
        or f.tem_whatsapp in ("sim", "nao")
        or f.nps_bucket in ("promotor", "neutro", "detrator")
    )
    if not ativos:
        return True
    if contact is None:
        return False
    if f.estado is not None and _estado_do_contato(contact) != f.estado:
        return False
    if f.perfil is not None and _perfil_do_contato(contact) != f.perfil:
        return False
    if f.plan_type is not None and _plan_type_do_contato(contact) != f.plan_type:
        return False
    if f.tem_whatsapp in ("sim", "nao"):
        quer = f.tem_whatsapp == "sim"
        if tem_whatsapp((contact.phone or "").strip()) != quer:
            return False
    if f.nps_bucket in ("promotor", "neutro", "detrator"):
        nps_score = _partner_fields(contact, now)["nps_score"]
        if _nps_bucket_label(nps_score) != f.nps_bucket:
            return False
    return True


def _feedback_passa_filtros(f_item: FeedbackItem, f: BoardItemFilters) -> bool:
    """True se o FeedbackItem casa os filtros que são COLUNAS do próprio item
    (team_tag/assignee/abordado) — espelha list_feedbacks."""
    if f.team_tag is not None and f_item.team_tag != f.team_tag:
        return False
    if f.assignee is not None and f_item.assignee != f.assignee:
        return False
    if f.abordado is not None and bool(f_item.abordado) != f.abordado:
        return False
    return True


# --- Enriquecimento dos cards EM LOTE (sem N+1) -------------------------------
# Cada helper roda UMA query agregada por dimensão (CsTask por feedback_item_id;
# Message por contact_id; Improvement/FeedbackCluster.title|label por id IN (...))
# e devolve um dict pronto para lookup em Python. Reusados pelos 3 handlers.


async def _tarefa_por_feedback(
    session: AsyncSession, org: Organization, feedback_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Mapa feedback_id -> status da CsTask MAIS RECENTE vinculada (uma query).

    Carrega (feedback_item_id, status, created_at) de todas as CsTask cujo
    feedback_item_id está no lote e, em Python, fica com o status da tarefa de
    created_at mais recente por feedback (desempate estável). Feedbacks sem tarefa
    simplesmente não aparecem no mapa.
    """
    if not feedback_ids:
        return {}
    rows = (
        await session.execute(
            select(CsTask.feedback_item_id, CsTask.status, CsTask.created_at).where(
                CsTask.organization_id == org.id,
                CsTask.feedback_item_id.in_(feedback_ids),
            )
        )
    ).all()
    best: dict[uuid.UUID, tuple[datetime | None, str]] = {}
    for fid, status, created in rows:
        if fid is None:
            continue
        prev = best.get(fid)
        # Tarefa mais recente vence; created_at None perde para qualquer datado.
        if prev is None or (created is not None and (prev[0] is None or created >= prev[0])):
            best[fid] = (created, status)
    return {fid: v[1] for fid, v in best.items()}


async def _conversa_count_por_contato(
    session: AsyncSession, org: Organization, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Mapa contact_id -> nº de Message do contato (uma query COUNT ... GROUP BY)."""
    if not contact_ids:
        return {}
    rows = (
        await session.execute(
            select(Message.contact_id, func.count())
            .where(Message.organization_id == org.id, Message.contact_id.in_(contact_ids))
            .group_by(Message.contact_id)
        )
    ).all()
    return {cid: int(n) for cid, n in rows if cid is not None}


async def _titulo_improvement_por_id(
    session: AsyncSession, org: Organization, improvement_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Mapa improvement_id -> Improvement.title (uma query WHERE id IN (...))."""
    if not improvement_ids:
        return {}
    rows = (
        await session.execute(
            select(Improvement.id, Improvement.title).where(
                Improvement.organization_id == org.id,
                Improvement.id.in_(improvement_ids),
            )
        )
    ).all()
    return {iid: title for iid, title in rows}


async def _label_cluster_por_id(
    session: AsyncSession, org: Organization, cluster_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """Mapa cluster_id -> FeedbackCluster.label (uma query WHERE id IN (...)), escopado
    por org (multi-tenant: nunca rotula com cluster de outra org)."""
    if not cluster_ids:
        return {}
    rows = (
        await session.execute(
            select(FeedbackCluster.id, FeedbackCluster.label).where(
                FeedbackCluster.organization_id == org.id,
                FeedbackCluster.id.in_(cluster_ids),
            )
        )
    ).all()
    return {clid: label for clid, label in rows}


async def _enrich_feedback_cards(
    session: AsyncSession, org: Organization, rows: list[tuple[FeedbackItem, Any]]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Calcula, EM LOTE, os campos extras de cada feedback do conjunto carregado.

    Junta as 4 dimensões (tarefa por feedback, conversa por contato, título de
    melhoria e label de dor por id) com 4 queries agregadas — uma por dimensão,
    nada de N+1 — e devolve {feedback_id: {campos extras}} pronto para mesclar no
    dict do card. Os ids para os IN(...) saem do próprio conjunto já carregado.
    """
    feedback_ids = [f.id for f, _ in rows]
    contact_ids = list({f.contact_id for f, _ in rows if f.contact_id is not None})
    improvement_ids = list({f.improvement_id for f, _ in rows if f.improvement_id is not None})
    cluster_ids = list({f.cluster_id for f, _ in rows if f.cluster_id is not None})

    tarefa_status = await _tarefa_por_feedback(session, org, feedback_ids)
    conversa = await _conversa_count_por_contato(session, org, contact_ids)
    titulos = await _titulo_improvement_por_id(session, org, improvement_ids)
    labels = await _label_cluster_por_id(session, org, cluster_ids)

    extras: dict[uuid.UUID, dict[str, Any]] = {}
    for f, _ in rows:
        st = tarefa_status.get(f.id)
        extras[f.id] = {
            "tem_tarefa": st is not None,
            "tarefa_status": st,
            "improvement_id": str(f.improvement_id) if f.improvement_id else None,
            "melhoria_titulo": titulos.get(f.improvement_id) if f.improvement_id else None,
            "dor_label": labels.get(f.cluster_id) if f.cluster_id else None,
            "conversa_count": conversa.get(f.contact_id, 0) if f.contact_id else 0,
            "assignee": f.assignee,
            "team_tag": f.team_tag,
            "abordado": f.abordado,
        }
    return extras


async def _items_action_status(
    session: AsyncSession, org: Organization, board: dict[str, Any],
    filters: BoardItemFilters,
) -> dict[str, Any]:
    """Para um board campo='action_status': por coluna, os feedbacks com aquele status.

    UMA query (feedbacks + contato juntado), agrupa em Python por action_status,
    ordena por urgência (mesma `_feedback_out` do feed), trunca em BOARD_ITEMS_PER_COLUMN.

    Os filtros (estado/perfil/plan_type/tem_whatsapp/nps_bucket via contato; team_tag/
    assignee/abordado via item) são aplicados ANTES do agrupamento, então items E counts
    de cada coluna refletem o filtro.
    """
    rows = (
        await session.execute(
            select(FeedbackItem, Contact)
            .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
            .where(FeedbackItem.organization_id == org.id)
        )
    ).all()

    now = datetime.now(timezone.utc)
    # Filtro ANTES do agrupamento (items E counts coerentes): contato + colunas do item.
    rows = [
        (f, c)
        for f, c in rows
        if _feedback_passa_filtros(f, filters) and _contato_passa_filtros(c, filters, now)
    ]
    # Campos ricos (tarefa/melhoria/dor/conversa/assignee/team_tag/abordado) EM LOTE.
    extras = await _enrich_feedback_cards(session, org, rows)
    by_status: dict[str, list[dict[str, Any]]] = {}
    for f, c in rows:
        card = _feedback_out(f, c, now)
        card.update(extras[f.id])
        by_status.setdefault(f.action_status, []).append(card)

    colunas_out: list[dict[str, Any]] = []
    for col in board["colunas"]:
        bucket = by_status.get(col["valor"], [])
        bucket.sort(key=lambda it: it["urgencia"], reverse=True)
        colunas_out.append(
            {
                "id": col["id"],
                "nome": col["nome"],
                "valor": col["valor"],
                "cor": col.get("cor", _COR_DEFAULT),
                "count": len(bucket),
                "items": bucket[:BOARD_ITEMS_PER_COLUMN],
            }
        )
    return {
        "id": board["id"],
        "nome": board["nome"],
        "entidade": board.get("entidade", ENTIDADE_FEEDBACK),
        "campo": board["campo"],
        "colunas": colunas_out,
    }


async def _items_selo(
    session: AsyncSession, org: Organization, board: dict[str, Any],
    filters: BoardItemFilters,
) -> dict[str, Any]:
    """Para um board campo='selo': por coluna, os feedbacks dos contatos com aquele selo.

    Carrega os contatos da org (mapa selo -> {contact_ids}) e os feedbacks + contato
    juntado numa query. Cada feedback entra na coluna se o selo da coluna está nos
    selos do seu contato (um feedback pode aparecer em mais de uma coluna se o contato
    tem vários selos — é o esperado: o card reflete o estado do contato na campanha).

    Os filtros (mesmos do board de feedback) são aplicados ANTES do agrupamento.
    """
    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars()
        .all()
    )
    selos_por_contato: dict[uuid.UUID, set[str]] = {
        c.id: set(_selos_do_contato(c)) for c in contacts
    }

    rows = (
        await session.execute(
            select(FeedbackItem, Contact)
            .outerjoin(Contact, Contact.id == FeedbackItem.contact_id)
            .where(FeedbackItem.organization_id == org.id)
        )
    ).all()

    now = datetime.now(timezone.utc)
    # Filtro ANTES do agrupamento (items E counts coerentes): contato + colunas do item.
    rows = [
        (f, c)
        for f, c in rows
        if _feedback_passa_filtros(f, filters) and _contato_passa_filtros(c, filters, now)
    ]
    # Campos ricos (tarefa/melhoria/dor/conversa/assignee/team_tag/abordado) EM LOTE.
    extras = await _enrich_feedback_cards(session, org, rows)
    valores = {col["valor"] for col in board["colunas"]}
    by_selo: dict[str, list[dict[str, Any]]] = {v: [] for v in valores}
    for f, c in rows:
        if f.contact_id is None:
            continue
        selos = selos_por_contato.get(f.contact_id, set())
        if not selos:
            continue
        base_out = None
        for v in valores:
            if v in selos:
                # Serializa uma vez por feedback, mas materializa uma CÓPIA por coluna —
                # senão o mesmo dict é compartilhado entre colunas (aliasing).
                if base_out is None:
                    base_out = _feedback_out(f, c, now)
                    base_out.update(extras[f.id])
                by_selo[v].append(dict(base_out))

    colunas_out: list[dict[str, Any]] = []
    for col in board["colunas"]:
        bucket = by_selo.get(col["valor"], [])
        bucket.sort(key=lambda it: it["urgencia"], reverse=True)
        colunas_out.append(
            {
                "id": col["id"],
                "nome": col["nome"],
                "valor": col["valor"],
                "cor": col.get("cor", _COR_DEFAULT),
                "count": len(bucket),
                "items": bucket[:BOARD_ITEMS_PER_COLUMN],
            }
        )
    return {
        "id": board["id"],
        "nome": board["nome"],
        "entidade": board.get("entidade", ENTIDADE_FEEDBACK),
        "campo": board["campo"],
        "colunas": colunas_out,
    }


# --- ITEMS de CLIENTE (entidade='cliente') ------------------------------------


# Quantos clientes mostrar por coluna (os piores por health primeiro). `count` é o
# total real; `items` é o recorte priorizado para a tela não estourar.
BOARD_CLIENTES_PER_COLUMN = 40


def _estado_do_contato(contact: Contact) -> str | None:
    """subscription.state do snapshot partner (`partner.subscription.state`), ou None."""
    sub = (((contact.profile_data or {}).get("partner") or {}).get("subscription") or {})
    state = sub.get("state")
    return str(state) if state else None


def _perfil_do_contato(contact: Contact) -> str | None:
    """perfil de segmentação do snapshot partner (`partner.profile`), ou None."""
    perfil = ((contact.profile_data or {}).get("partner") or {}).get("profile")
    return str(perfil) if perfil else None


def _cliente_card(
    contact: Contact,
    *,
    last_feedback_at: datetime | None,
    neg_count: int,
    pos_count: int,
    now: datetime,
    feedbacks_count: int = 0,
    tarefas_abertas: int = 0,
    conversa_count: int = 0,
) -> dict[str, Any]:
    """Card de CLIENTE para o board (mesma forma do GET /api/clientes do admin.py).

    Health via `compute_health` com os MESMOS sinais do /clientes (nps do snapshot,
    perfil, recência do último feedback, sentimento acumulado, estado da assinatura).
    As contagens (feedbacks/tarefas abertas/conversa) são calculadas EM LOTE pelo
    caller e injetadas aqui — o card só as expõe.
    """
    pf = _partner_fields(contact, now)
    estado = _estado_do_contato(contact)
    health = compute_health(
        nps_score=pf["nps_score"],
        perfil=pf["perfil"],
        last_feedback_at=last_feedback_at,
        neg_count=neg_count,
        pos_count=pos_count,
        subscription_state=estado,
        now=now,
    )
    phone = (contact.phone or "").strip()
    return {
        "id": str(contact.id),
        "nome": contact.name,
        "whatsapp": contact.phone,
        # Tem WhatsApp REAL? Só celular BR válido (fixo/grupo/placeholder/vazio => False).
        "tem_whatsapp": tem_whatsapp(phone),
        "perfil": pf["perfil"],
        "estado": estado,
        "health": health.score,
        "health_band": health.band,
        "selos": _selos_do_contato(contact),
        # Conexões do cliente (calculadas em lote pelo caller).
        "feedbacks_count": feedbacks_count,
        "tarefas_abertas": tarefas_abertas,
        "conversa_count": conversa_count,
    }


async def _feedbacks_count_por_contato(
    session: AsyncSession, org: Organization, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Mapa contact_id -> nº de FeedbackItem do contato na org (uma query GROUP BY)."""
    if not contact_ids:
        return {}
    rows = (
        await session.execute(
            select(FeedbackItem.contact_id, func.count())
            .where(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.contact_id.in_(contact_ids),
            )
            .group_by(FeedbackItem.contact_id)
        )
    ).all()
    return {cid: int(n) for cid, n in rows if cid is not None}


async def _tarefas_abertas_por_contato(
    session: AsyncSession, org: Organization, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Mapa contact_id -> nº de CsTask NÃO concluídas do contato (uma query GROUP BY)."""
    if not contact_ids:
        return {}
    rows = (
        await session.execute(
            select(CsTask.contact_id, func.count())
            .where(
                CsTask.organization_id == org.id,
                CsTask.contact_id.in_(contact_ids),
                CsTask.status != _CS_TASK_DONE,
            )
            .group_by(CsTask.contact_id)
        )
    ).all()
    return {cid: int(n) for cid, n in rows if cid is not None}


async def _items_cliente(
    session: AsyncSession, org: Organization, board: dict[str, Any],
    filters: BoardItemFilters,
) -> dict[str, Any]:
    """Para um board entidade='cliente': por coluna, os CONTATOS que casam o critério.

    - campo='selo':   contato com o selo `valor` em profile_data["selos"].
    - campo='estado': contato com partner.subscription.state == valor.
    - campo='perfil': contato com partner.profile == valor (ou startswith p/ 'churn').

    Carrega os contatos + agrega feedback (recência/sentimento) numa varredura, monta o
    card de cada contato uma vez, e distribui pelas colunas. `count` = total da coluna;
    `items` = top BOARD_CLIENTES_PER_COLUMN por health ASC (pior cliente primeiro).

    SANEAMENTO (Fase F): contatos cujo phone é classe 'group' (IDs de grupo/comunidade
    do WhatsApp, não leads 1:1) são EXCLUÍDOS do board de cliente — não some nada do
    banco, só não aparecem aqui. Filtros (estado/perfil/plan_type/tem_whatsapp/nps_bucket
    via contato; health_band post-filter sobre o card) aplicados ANTES do agrupamento,
    então items E counts de cada coluna refletem o filtro.
    """
    campo = board["campo"]
    now = datetime.now(timezone.utc)

    contacts = (
        (await session.execute(select(Contact).where(Contact.organization_id == org.id)))
        .scalars()
        .all()
    )
    # Fase F — saneamento: tira IDs de GRUPO/comunidade (phone classe 'group'); eles não
    # são clientes 1:1. (NÃO apaga nada; só não os lista nos boards de cliente.)
    contacts = [c for c in contacts if classify_phone((c.phone or "").strip()) != "group"]

    # Agregação de feedback por contato: último occurred/created + nº neg/pos (sinais
    # do Health Score, espelhando o GET /api/clientes). UMA query sobre os itens da org.
    last_at: dict[uuid.UUID, datetime] = {}
    neg: dict[uuid.UUID, int] = {}
    pos: dict[uuid.UUID, int] = {}
    fb_rows = (
        await session.execute(
            select(
                FeedbackItem.contact_id,
                FeedbackItem.occurred_at,
                FeedbackItem.created_at,
                FeedbackItem.sentiment,
            ).where(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.contact_id.is_not(None),
            )
        )
    ).all()
    for cid, occ, created, sentiment in fb_rows:
        when = occ or created
        if when is not None:
            prev = last_at.get(cid)
            if prev is None or when > prev:
                last_at[cid] = when
        if sentiment == "negativo":
            neg[cid] = neg.get(cid, 0) + 1
        elif sentiment == "positivo":
            pos[cid] = pos.get(cid, 0) + 1

    # Conexões do card de cliente EM LOTE (sem N+1): nº de feedbacks, tarefas abertas
    # e mensagens por contato — uma query agregada por dimensão.
    contact_ids = [c.id for c in contacts]
    fb_count = await _feedbacks_count_por_contato(session, org, contact_ids)
    tarefas_abertas = await _tarefas_abertas_por_contato(session, org, contact_ids)
    conversa = await _conversa_count_por_contato(session, org, contact_ids)

    # FILTRO ANTES do agrupamento (items E counts coerentes): mantém só os contatos que
    # casam os filtros "por tipo de cliente" (estado/perfil/plan_type/tem_whatsapp/
    # nps_bucket — espelha list_clientes) E o health_band (post-filter sobre o card,
    # avaliado abaixo com o card já calculado).
    contacts = [c for c in contacts if _contato_passa_filtros(c, filters, now)]

    # Card de cada contato (uma vez) + critério de pertencimento por contato.
    cards: dict[uuid.UUID, dict[str, Any]] = {}
    selos_por_contato: dict[uuid.UUID, set[str]] = {}
    estado_por_contato: dict[uuid.UUID, str | None] = {}
    perfil_por_contato: dict[uuid.UUID, str | None] = {}
    filtrados: list[Contact] = []
    for c in contacts:
        card = _cliente_card(
            c,
            last_feedback_at=last_at.get(c.id),
            neg_count=neg.get(c.id, 0),
            pos_count=pos.get(c.id, 0),
            now=now,
            feedbacks_count=fb_count.get(c.id, 0),
            tarefas_abertas=tarefas_abertas.get(c.id, 0),
            conversa_count=conversa.get(c.id, 0),
        )
        # health_band: post-filter sobre o card (espelha list_clientes).
        if filters.health_band is not None and card["health_band"] != filters.health_band:
            continue
        cards[c.id] = card
        selos_por_contato[c.id] = set(_selos_do_contato(c))
        estado_por_contato[c.id] = _estado_do_contato(c)
        perfil_por_contato[c.id] = _perfil_do_contato(c)
        filtrados.append(c)
    contacts = filtrados

    def _match(contact_id: uuid.UUID, valor: str) -> bool:
        if campo == "selo":
            return valor in selos_por_contato.get(contact_id, set())
        if campo == "estado":
            return estado_por_contato.get(contact_id) == valor
        # campo == "perfil": match exato OU prefixo quando a coluna agrupa 'churn'.
        perfil = (perfil_por_contato.get(contact_id) or "")
        if perfil == valor:
            return True
        return valor.lower() == "churn" and perfil.lower().startswith("churn")

    colunas_out: list[dict[str, Any]] = []
    for col in board["colunas"]:
        # Cópia por coluna: um contato pode cair em mais de uma coluna (ex.: vários
        # selos) e o card é o MESMO dict — sem a cópia, as colunas compartilham a
        # referência (aliasing).
        bucket = [dict(cards[c.id]) for c in contacts if _match(c.id, col["valor"])]
        # Pior cliente primeiro: health ASC (desempate estável por nome).
        bucket.sort(key=lambda it: (it["health"], (it["nome"] or "")))
        colunas_out.append(
            {
                "id": col["id"],
                "nome": col["nome"],
                "valor": col["valor"],
                "cor": col.get("cor", _COR_DEFAULT),
                "count": len(bucket),
                "items": bucket[:BOARD_CLIENTES_PER_COLUMN],
            }
        )
    return {
        "id": board["id"],
        "nome": board["nome"],
        "entidade": board.get("entidade", ENTIDADE_CLIENTE),
        "campo": board["campo"],
        "colunas": colunas_out,
    }


# --- ITEMS de TAREFA (entidade='tarefa') --------------------------------------


# Quantas tarefas mostrar por coluna (as mais prioritárias/urgentes primeiro). `count`
# é o total real; `items` é o recorte priorizado para a tela não estourar.
BOARD_TAREFAS_PER_COLUMN = 40


def _tarefa_card(
    task: CsTask,
    contato_nome: str | None,
    feedback_preview: str | None,
) -> dict[str, Any]:
    """Card de TAREFA para o board (dict enxuto — espelha o essencial de tasks._out).

    id, titulo (title), status, priority, owner, contato_nome (join Contact), due_at,
    feedback_id (cs_tasks.feedback_item_id) e o trecho do feedback vinculado se houver.
    """
    return {
        "id": str(task.id),
        "titulo": task.title,
        "status": task.status,
        "priority": task.priority,
        "owner": task.owner,
        "contato_id": str(task.contact_id) if task.contact_id else None,
        "contato_nome": contato_nome,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "feedback_id": str(task.feedback_item_id) if task.feedback_item_id else None,
        "feedback_preview": feedback_preview,
    }


async def _items_tarefa(
    session: AsyncSession, org: Organization, board: dict[str, Any],
    filters: BoardItemFilters,
) -> dict[str, Any]:
    """Para um board entidade='tarefa' (campo='status'): agrupa CsTask da org por status.

    Carrega as tarefas da org numa query, junta contato (nome) e o preview do feedback
    vinculado EM LOTE (uma query cada — sem N+1), monta o card de cada uma e distribui
    pelas colunas. Ordena cada coluna por prioridade (urgente→baixa) e, no desempate,
    por due_at asc (SLA mais próximo primeiro) — mesma intuição da fila /api/tarefas.
    `count` = total da coluna; `items` = top BOARD_TAREFAS_PER_COLUMN.

    Filtros owner/priority (colunas do CsTask) aplicados ANTES do agrupamento, então
    items E counts de cada coluna refletem o filtro.
    """
    tasks = (
        (await session.execute(select(CsTask).where(CsTask.organization_id == org.id)))
        .scalars()
        .all()
    )
    # Filtro ANTES do agrupamento (items E counts coerentes): colunas simples do modelo.
    if filters.owner is not None:
        tasks = [t for t in tasks if t.owner == filters.owner]
    if filters.priority is not None:
        tasks = [t for t in tasks if t.priority == filters.priority]

    # Junta contato (nome) e feedback vinculado (preview) EM LOTE — uma query cada.
    contact_ids = list({t.contact_id for t in tasks if t.contact_id is not None})
    nomes: dict[uuid.UUID, str | None] = {}
    if contact_ids:
        rows = (
            await session.execute(
                select(Contact.id, Contact.name).where(
                    Contact.organization_id == org.id,
                    Contact.id.in_(contact_ids),
                )
            )
        ).all()
        nomes = {cid: name for cid, name in rows}

    feedback_ids = list({t.feedback_item_id for t in tasks if t.feedback_item_id is not None})
    feedbacks: dict[uuid.UUID, FeedbackItem] = {}
    if feedback_ids:
        rows = (
            await session.execute(
                select(FeedbackItem).where(
                    FeedbackItem.id.in_(feedback_ids),
                    FeedbackItem.organization_id == org.id,
                )
            )
        ).scalars().all()
        feedbacks = {f.id: f for f in rows}

    by_status: dict[str, list[tuple[CsTask, dict[str, Any]]]] = {}
    for t in tasks:
        nome = nomes.get(t.contact_id) if t.contact_id else None
        preview = _feedback_preview(feedbacks.get(t.feedback_item_id)) if t.feedback_item_id else None
        card = _tarefa_card(t, nome, preview)
        by_status.setdefault(t.status, []).append((t, card))

    # due_at asc (nulls por último) no desempate da prioridade.
    far = datetime.max.replace(tzinfo=timezone.utc)

    def _sort_key(pair: tuple[CsTask, dict[str, Any]]):
        t = pair[0]
        return (_PRIORITY_RANK.get(t.priority, 2), t.due_at is None, t.due_at or far)

    colunas_out: list[dict[str, Any]] = []
    for col in board["colunas"]:
        bucket = by_status.get(col["valor"], [])
        bucket.sort(key=_sort_key)
        cards = [card for _, card in bucket]
        colunas_out.append(
            {
                "id": col["id"],
                "nome": col["nome"],
                "valor": col["valor"],
                "cor": col.get("cor", _COR_DEFAULT),
                "count": len(cards),
                "items": cards[:BOARD_TAREFAS_PER_COLUMN],
            }
        )
    return {
        "id": board["id"],
        "nome": board["nome"],
        "entidade": board.get("entidade", ENTIDADE_TAREFA),
        "campo": board["campo"],
        "colunas": colunas_out,
    }


# --- ITEMS de MELHORIA (entidade='melhoria') ----------------------------------


# Quantas melhorias mostrar por coluna (as com mais feedbacks primeiro). `count` é o
# total real; `items` é o recorte priorizado para a tela não estourar.
BOARD_MELHORIAS_PER_COLUMN = 40


async def _feedback_count_por_improvement(
    session: AsyncSession, org: Organization, improvement_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Mapa improvement_id -> nº de FeedbackItem vinculados (uma query GROUP BY)."""
    if not improvement_ids:
        return {}
    rows = (
        await session.execute(
            select(FeedbackItem.improvement_id, func.count())
            .where(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.improvement_id.in_(improvement_ids),
            )
            .group_by(FeedbackItem.improvement_id)
        )
    ).all()
    return {iid: int(n) for iid, n in rows if iid is not None}


def _melhoria_card(imp: Improvement, feedback_count: int) -> dict[str, Any]:
    """Card de MELHORIA para o board (dict enxuto).

    id, titulo (title), status, feedback_count (nº de FeedbackItem com improvement_id ==
    imp.id, calculado em LOTE pelo caller), effort, target_date. `priority_score` é
    derivado só no /improvements/roadmap (não é coluna do modelo) — omitido aqui.
    """
    return {
        "id": str(imp.id),
        "titulo": imp.title,
        "status": imp.status,
        "feedback_count": int(feedback_count),
        "effort": imp.effort,
        "target_date": imp.target_date.isoformat() if imp.target_date else None,
    }


async def _items_melhoria(
    session: AsyncSession, org: Organization, board: dict[str, Any],
    filters: BoardItemFilters,
) -> dict[str, Any]:
    """Para um board entidade='melhoria' (campo='status'): agrupa Improvement por status.

    Carrega as melhorias da org numa query, conta os feedbacks vinculados EM LOTE
    (improvement_id IN (...), sem N+1), monta o card e distribui pelas colunas. Ordena
    cada coluna por feedback_count desc (mais "pedida" primeiro; desempate estável por
    título). `count` = total da coluna; `items` = top BOARD_MELHORIAS_PER_COLUMN.

    Filtro effort (coluna do Improvement) aplicado ANTES do agrupamento, então items E
    counts de cada coluna refletem o filtro.
    """
    improvements = (
        (await session.execute(select(Improvement).where(Improvement.organization_id == org.id)))
        .scalars()
        .all()
    )
    # Filtro ANTES do agrupamento (items E counts coerentes): coluna simples do modelo.
    if filters.effort is not None:
        improvements = [imp for imp in improvements if imp.effort == filters.effort]

    counts = await _feedback_count_por_improvement(
        session, org, [imp.id for imp in improvements]
    )

    by_status: dict[str, list[dict[str, Any]]] = {}
    for imp in improvements:
        card = _melhoria_card(imp, counts.get(imp.id, 0))
        by_status.setdefault(imp.status, []).append(card)

    colunas_out: list[dict[str, Any]] = []
    for col in board["colunas"]:
        bucket = by_status.get(col["valor"], [])
        # Mais feedbacks primeiro (desempate estável por título).
        bucket.sort(key=lambda it: (-it["feedback_count"], (it["titulo"] or "")))
        colunas_out.append(
            {
                "id": col["id"],
                "nome": col["nome"],
                "valor": col["valor"],
                "cor": col.get("cor", _COR_DEFAULT),
                "count": len(bucket),
                "items": bucket[:BOARD_MELHORIAS_PER_COLUMN],
            }
        )
    return {
        "id": board["id"],
        "nome": board["nome"],
        "entidade": board.get("entidade", ENTIDADE_MELHORIA),
        "campo": board["campo"],
        "colunas": colunas_out,
    }


@router.get("/boards/{board_id}/items")
async def board_items(
    board_id: str,
    # --- Filtros opcionais (Fase E). Ausentes (None) = board inteiro (comportamento
    # anterior). Mesmo vocabulário dos filtros de admin.py (list_feedbacks/list_clientes).
    # Aplicados ANTES do agrupamento => items E counts de cada coluna refletem o filtro.
    # Filtros que não se aplicam à entidade do board são ignorados (no-op, sem erro).
    estado: str | None = None,
    plan_type: str | None = None,
    perfil: str | None = None,
    tem_whatsapp: str | None = None,
    nps_bucket: str | None = None,
    team_tag: str | None = None,
    assignee: str | None = None,
    abordado: bool | None = None,
    health_band: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    effort: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cards de cada coluna do board. Resolve o board (salvo OU default).

    entidade='cliente': cada coluna agrupa CONTATOS (por selo/estado/perfil) — cards de
    cliente, `items` = top por health ASC (pior primeiro). entidade='tarefa': agrupa
    CsTask por status (campo='status') — cards de tarefa, top por prioridade+SLA.
    entidade='melhoria': agrupa Improvement por status (campo='status') — cards de
    melhoria, top por feedback_count desc. entidade='feedback' (default):
    campo='action_status' agrupa por FeedbackItem.action_status==valor; campo='selo'
    agrupa pelos feedbacks de contatos com o selo==valor — `items` = top por urgência
    (= ordem do feed). `count` = total real da coluna.

    FILTROS (Fase E) — query params opcionais, aplicados ANTES do agrupamento (items E
    counts de cada coluna refletem o filtro); cada um só vale para a(s) entidade(s) a que
    pertence, os demais são ignorados sem erro:
    - feedback: estado, plan_type, perfil, tem_whatsapp ('sim'/'nao'), nps_bucket
      ('promotor'/'neutro'/'detrator') [via o CONTATO juntado, espelha list_feedbacks];
      team_tag, assignee, abordado (bool) [colunas do FeedbackItem].
    - cliente: estado, plan_type, perfil [JSON do snapshot], nps_bucket, tem_whatsapp,
      health_band ('healthy'/'watch'/'at_risk') [post-filter sobre o card] (espelha
      list_clientes).
    - tarefa: owner, priority (colunas do CsTask). melhoria: effort (coluna do Improvement)."""
    org = await _get_org(session)
    board = _find_board(org, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="board não encontrado")

    filters = BoardItemFilters(
        estado=estado,
        plan_type=plan_type,
        perfil=perfil,
        tem_whatsapp=tem_whatsapp,
        nps_bucket=nps_bucket,
        team_tag=team_tag,
        assignee=assignee,
        abordado=abordado,
        health_band=health_band,
        owner=owner,
        priority=priority,
        effort=effort,
    )

    entidade = board.get("entidade", ENTIDADE_FEEDBACK)
    if entidade == ENTIDADE_CLIENTE:
        return await _items_cliente(session, org, board, filters)
    if entidade == ENTIDADE_TAREFA:
        return await _items_tarefa(session, org, board, filters)
    if entidade == ENTIDADE_MELHORIA:
        return await _items_melhoria(session, org, board, filters)

    if board["campo"] == "action_status":
        return await _items_action_status(session, org, board, filters)
    return await _items_selo(session, org, board, filters)


# --- BOARD MOVE (drag-and-drop genérico) --------------------------------------


def _aplicar_selo(contact: Contact, valor: str) -> None:
    """Aplica o selo `valor` ao contato (idempotente). Se `valor` pertence ao grupo
    de follow-up (FOLLOWUP_SELOS), remove os OUTROS selos do grupo — single-membership:
    o card vive em UMA coluna só do board Follow-up (Trello). Selos fora do grupo são
    apenas acrescentados, como antes (multi-coluna por campanha)."""
    selos = _selos_do_contato(contact)
    if valor in FOLLOWUP_SELOS:
        # Tira os demais selos do grupo (mantém a ordem; remove duplicatas do grupo).
        outros_do_grupo = {s for s in FOLLOWUP_SELOS if s != valor}
        novos = [s for s in selos if s not in outros_do_grupo]
        if valor not in novos:
            novos.append(valor)
        if novos != selos:
            _set_selos_do_contato(contact, novos)
        return
    if valor not in selos:
        _set_selos_do_contato(contact, [*selos, valor])


class BoardMoveIn(BaseModel):
    """Move um feedback no board: aplica o `campo` com o `valor` da coluna destino.

    - campo='action_status': seta FeedbackItem.action_status = valor.
    - campo='selo': aplica o selo `valor` ao CONTATO do feedback (reusa a lógica de
      selos do campanha.py: garante o selo no catálogo + idempotente na lista do contato).
    """

    campo: str = Field(min_length=1, max_length=40)
    valor: str = Field(min_length=1, max_length=80)


@router.post("/feedbacks/{feedback_id}/board-move")
async def board_move(
    feedback_id: str, body: BoardMoveIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Aplica o movimento do card. campo='action_status' troca o status do feedback
    (valida o vocabulário ACTION_STATUSES); campo='selo' aplica o selo ao contato do
    feedback (cria o selo no catálogo se for novo; idempotente). Retorna o feedback no
    formato do feed (`_feedback_out`) + os selos atuais do contato. 422/404 nos erros."""
    org = await _get_org(session)
    try:
        fid = uuid.UUID(feedback_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    campo = body.campo.strip()
    valor = body.valor.strip()
    if campo not in BOARD_CAMPOS:
        raise HTTPException(
            status_code=422,
            detail=f"campo inválido: '{body.campo}' (use {', '.join(BOARD_CAMPOS)})",
        )
    if not valor:
        raise HTTPException(status_code=422, detail="valor não pode ser vazio")

    feedback = (
        await session.execute(
            select(FeedbackItem).where(
                FeedbackItem.id == fid, FeedbackItem.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="feedback não encontrado")

    contact = None
    if feedback.contact_id is not None:
        contact = (
            await session.execute(
                select(Contact).where(
                    Contact.id == feedback.contact_id,
                    Contact.organization_id == org.id,
                )
            )
        ).scalar_one_or_none()

    if campo == "action_status":
        if valor not in ACTION_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"action_status inválido: '{valor}' (use {', '.join(ACTION_STATUSES)})",
            )
        feedback.action_status = valor
    else:  # campo == "selo"
        if contact is None:
            raise HTTPException(
                status_code=422, detail="feedback sem contato — não dá para aplicar selo"
            )
        # Reusa a lógica de selos do campanha.py: garante no catálogo + idempotente.
        _upsert_catalogo(org, valor, None)
        _aplicar_selo(contact, valor)

    await session.commit()

    out = _feedback_out(feedback, contact)
    out["selos"] = _selos_do_contato(contact) if contact is not None else []
    return out


# --- BOARD MOVE de CLIENTE (entidade='cliente') -------------------------------


class ContactBoardMoveIn(BaseModel):
    """Move um CLIENTE no board de entidade='cliente'.

    - campo='selo': aplica o selo `valor` ao contato (reusa a lógica de selos do
      campanha.py: garante no catálogo + idempotente). Retorna {id, selos}.
    - campo ∈ {estado, perfil}: read-only — esses dados vêm do snapshot da API de
      Clientes, não dá para movê-los pela mão (409).
    """

    campo: str = Field(min_length=1, max_length=40)
    valor: str = Field(min_length=1, max_length=80)


@router.post("/contacts/{contact_id}/board-move")
async def contact_board_move(
    contact_id: str, body: ContactBoardMoveIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Aplica o movimento de um CLIENTE no board. campo='selo' aplica o selo ao contato
    (cria no catálogo se for novo; idempotente) e retorna {id, selos}. campo ∈
    {estado, perfil} é read-only (vem da API de Clientes) — 409. 422/404 nos demais
    erros."""
    org = await _get_org(session)
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id inválido")

    campo = body.campo.strip()
    valor = body.valor.strip()
    if campo not in BOARD_CAMPOS_POR_ENTIDADE[ENTIDADE_CLIENTE]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"campo inválido: '{body.campo}' para entidade 'cliente' "
                f"(use {', '.join(BOARD_CAMPOS_POR_ENTIDADE[ENTIDADE_CLIENTE])})"
            ),
        )
    if not valor:
        raise HTTPException(status_code=422, detail="valor não pode ser vazio")

    if campo in ("estado", "perfil"):
        raise HTTPException(
            status_code=409,
            detail="estado/perfil vem da API, nao da pra mover",
        )

    contact = (
        await session.execute(
            select(Contact).where(Contact.id == cid, Contact.organization_id == org.id)
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="contato não encontrado")

    # campo == "selo": reusa a lógica de selos do campanha.py (catálogo + idempotente).
    _upsert_catalogo(org, valor, None)
    _aplicar_selo(contact, valor)

    await session.commit()
    return {"id": str(contact.id), "selos": _selos_do_contato(contact)}
