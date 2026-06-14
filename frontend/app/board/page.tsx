"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import {
  api,
  type Feedback,
  type FeedbackBoard,
  type FeedbackMoveInput,
  type FeedbackStatus,
  type Improvement,
} from "@/lib/api";

// ===== vocabulário ==========================================================

/** As 5 colunas do Kanban, na ordem do funil (esquerda → direita). */
const COLUMNS: { key: FeedbackStatus; label: string }[] = [
  { key: "novo", label: "Novo" },
  { key: "em_analise", label: "Em análise" },
  { key: "planejado", label: "Planejado" },
  { key: "resolvido", label: "Resolvido" },
  { key: "descartado", label: "Descartado" },
];

const STATUS_LABEL: Record<FeedbackStatus, string> = {
  novo: "Novo",
  em_analise: "Em análise",
  planejado: "Planejado",
  resolvido: "Resolvido",
  descartado: "Descartado",
};

const TYPE_LABEL: Record<string, string> = {
  nps: "NPS",
  churn: "Cancelamento",
  exit: "Exit survey",
  csat: "CSAT",
  elogio: "Elogio",
  sugestao: "Sugestão",
  bug: "Bug",
  outro: "Outro",
};

/** Times oferecidos no filtro de roteamento (espelha `team_tag` do backend). */
const TEAM_OPTIONS: { value: string; label: string }[] = [
  { value: "produto", label: "Produto" },
  { value: "suporte", label: "Suporte" },
  { value: "comercial", label: "Comercial" },
  { value: "cs", label: "CS" },
];

const TEAM_LABEL: Record<string, string> = Object.fromEntries(
  TEAM_OPTIONS.map((t) => [t.value, t.label]),
);

/** Estado vazio do board (antes do 1º load / em erro). */
const EMPTY_BOARD: FeedbackBoard = {
  columns: {
    novo: { count: 0, items: [] },
    em_analise: { count: 0, items: [] },
    planejado: { count: 0, items: [] },
    resolvido: { count: 0, items: [] },
    descartado: { count: 0, items: [] },
  },
};

function typeBadge(type: string) {
  const label = TYPE_LABEL[type] ?? type;
  const cls = type === "churn" || type === "exit" ? "t-exit" : "t-nps";
  return <span className={`badge type ${cls}`}>{label}</span>;
}

/** Faixa da barra de urgência: <30 verde, <60 amarelo, ≥60 vermelho. */
function urgencyClass(u: number): string {
  if (u >= 60) return "u-hi";
  if (u >= 30) return "u-mid";
  return "u-lo";
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

/** Trecho curto do texto pro card (o detalhe completo abre no modal). */
function snippet(text: string | null, max = 160): string {
  if (!text) return "";
  const t = text.trim();
  return t.length > max ? `${t.slice(0, max).trimEnd()}…` : t;
}

// ===== card de um feedback (arrastável) =====================================

function BoardCard({
  fb,
  dragging,
  onOpen,
  onDragStart,
  onDragEnd,
}: {
  fb: Feedback;
  dragging: boolean;
  onOpen: (fb: Feedback) => void;
  onDragStart: (fb: Feedback) => void;
  onDragEnd: () => void;
}) {
  return (
    <article
      className={`card board-card ${dragging ? "is-dragging" : ""}`}
      draggable
      onDragStart={(e) => {
        // guarda o id no payload (HTML5 DnD nativo) e marca o estado local.
        e.dataTransfer.setData("text/plain", fb.id);
        e.dataTransfer.effectAllowed = "move";
        onDragStart(fb);
      }}
      onDragEnd={onDragEnd}
      onClick={() => onOpen(fb)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(fb);
        }
      }}
      aria-label={`Feedback de ${fb.contato_nome || "sem nome"} — abrir detalhe`}
    >
      <div className="board-card-top cell-person">
        <Avatar name={fb.contato_nome} seed={fb.contato_id ?? fb.contato_whatsapp} size={26} />
        <span className="board-card-who">{fb.contato_nome || "sem contato"}</span>
        {typeBadge(fb.type)}
      </div>

      {fb.text ? (
        <p className="board-card-text">{snippet(fb.text)}</p>
      ) : (
        <p className="board-card-text empty-text">sem texto — só a nota</p>
      )}

      <div
        className={`board-urg ${urgencyClass(fb.urgencia)}`}
        title={`Urgência ${fb.urgencia}/100`}
        aria-hidden
      >
        <span style={{ width: `${Math.min(100, Math.max(0, fb.urgencia))}%` }} />
      </div>

      {(fb.team_tag || fb.assignee) && (
        <div className="board-card-meta">
          {fb.team_tag && (
            <span className="chip team">{TEAM_LABEL[fb.team_tag] ?? fb.team_tag}</span>
          )}
          {fb.assignee && <span className="chip person">@{fb.assignee}</span>}
        </div>
      )}
    </article>
  );
}

// ===== modal de detalhe / mover =============================================

function CardDetailModal({
  fb,
  improvements,
  onClose,
  onMoved,
}: {
  fb: Feedback;
  improvements: Improvement[];
  onClose: () => void;
  onMoved: (updated: Feedback, previousStatus: FeedbackStatus) => void;
}) {
  const titleId = useId();
  const [status, setStatus] = useState<FeedbackStatus>(fb.action_status);
  // O contrato de Feedback não expõe o vínculo de melhoria (é server-side), então
  // o select começa vazio; escolher aqui cria/atualiza o vínculo no move.
  const [improvementId, setImprovementId] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isPlanejado = status === "planejado";

  async function move(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const body: FeedbackMoveInput = { status };
    if (isPlanejado && improvementId) body.improvement_id = improvementId;

    const previousStatus = fb.action_status;
    try {
      const updated = await api.post<Feedback>(`/api/feedbacks/${fb.id}/move`, body);
      onMoved(updated, previousStatus);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title="Detalhe do feedback" onClose={onClose} labelledById={titleId}>
      <form onSubmit={move}>
        <div className="modal-body">
          <div className="board-detail-head cell-person">
            <Avatar name={fb.contato_nome} seed={fb.contato_id ?? fb.contato_whatsapp} size={34} />
            <div className="cell-person-txt">
              {fb.contato_id ? (
                <Link href={`/contatos/${fb.contato_id}`} className="board-detail-who">
                  {fb.contato_nome || "sem nome"}
                </Link>
              ) : (
                <span className="board-detail-who">{fb.contato_nome || "sem contato"}</span>
              )}
              <span className="mono dim">{fb.contato_whatsapp || "—"}</span>
            </div>
            {typeBadge(fb.type)}
            {fb.urgencia >= 60 && (
              <span className="badge detractor" title={`Urgência ${fb.urgencia}/100`}>🔥 urgente</span>
            )}
          </div>

          {fb.text ? (
            <div className="board-detail-text">“{fb.text}”</div>
          ) : (
            <div className="board-detail-text empty-text">sem texto — só a nota interna</div>
          )}

          <div className="board-detail-facts">
            <span>Urgência <b className="mono">{fb.urgencia}</b>/100</span>
            <span>Registrado <b>{fmtDate(fb.occurred_em ?? fb.created_em)}</b></span>
            {fb.team_tag && <span>Time <b>{TEAM_LABEL[fb.team_tag] ?? fb.team_tag}</b></span>}
            {fb.assignee && <span>Responsável <b>@{fb.assignee}</b></span>}
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-status`}>Mover para…</label>
            <select
              id={`${titleId}-status`}
              value={status}
              onChange={(e) => setStatus(e.target.value as FeedbackStatus)}
            >
              {COLUMNS.map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </div>

          {isPlanejado && (
            <div className="field">
              <label htmlFor={`${titleId}-imp`}>Vincular a uma melhoria (opcional)</label>
              <select
                id={`${titleId}-imp`}
                value={improvementId}
                onChange={(e) => setImprovementId(e.target.value)}
              >
                <option value="">— sem melhoria —</option>
                {improvements.map((imp) => (
                  <option key={imp.id} value={imp.id}>{imp.title}</option>
                ))}
              </select>
            </div>
          )}

          {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button type="submit" className="btn" disabled={saving}>
            {saving ? "Movendo…" : "Mover"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ===== página ===============================================================

export default function BoardPage() {
  const [board, setBoard] = useState<FeedbackBoard>(EMPTY_BOARD);
  const [improvements, setImprovements] = useState<Improvement[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // filtros (roteamento)
  const [teamTag, setTeamTag] = useState("");
  const [assignee, setAssignee] = useState("");

  // drag-and-drop
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overColumn, setOverColumn] = useState<FeedbackStatus | null>(null);

  // detalhe
  const [opened, setOpened] = useState<Feedback | null>(null);

  // Conjunto de assignees presentes no board (popula o filtro dinamicamente).
  const assigneeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const col of Object.values(board.columns)) {
      for (const it of col.items) if (it.assignee) set.add(it.assignee);
    }
    return Array.from(set).sort();
  }, [board]);

  const buildQs = useCallback(() => {
    const qs = new URLSearchParams();
    if (teamTag) qs.set("team_tag", teamTag);
    if (assignee) qs.set("assignee", assignee);
    const s = qs.toString();
    return s ? `?${s}` : "";
  }, [teamTag, assignee]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await api.get<FeedbackBoard>(`/api/feedbacks/board${buildQs()}`);
      // tolera colunas ausentes na resposta (preenche com vazias).
      setBoard({ columns: { ...EMPTY_BOARD.columns, ...(raw.columns ?? {}) } });
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [buildQs]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  // Melhorias só para o select "Mover para planejado" (best-effort, silencioso).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await api.get<Improvement[]>("/api/improvements");
        if (!cancelled) setImprovements(Array.isArray(rows) ? rows : []);
      } catch {
        if (!cancelled) setImprovements([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  /** Aplica o resultado de um move (modal ou drop) ao estado local. */
  const applyMove = useCallback(
    (updated: Feedback, previousStatus: FeedbackStatus) => {
      setBoard((prev) => {
        const columns = { ...prev.columns };
        const from = previousStatus;
        const to = updated.action_status;
        // remove o card da coluna de origem
        const fromItems = columns[from].items.filter((it) => it.id !== updated.id);
        const movedOut = columns[from].items.length !== fromItems.length;
        columns[from] = {
          count: movedOut ? Math.max(0, columns[from].count - 1) : columns[from].count,
          items: fromItems,
        };
        // insere/atualiza na coluna de destino
        const toItems = columns[to].items.filter((it) => it.id !== updated.id);
        const alreadyInDest = columns[to].items.length !== toItems.length;
        columns[to] = {
          count: from === to || alreadyInDest ? columns[to].count : columns[to].count + 1,
          items: [updated, ...toItems],
        };
        return { columns };
      });
    },
    [],
  );

  /** Optimistic move por drag-and-drop: move já, reverte se a API falhar. */
  const moveByDrop = useCallback(
    async (id: string, toStatus: FeedbackStatus) => {
      // localiza o card e sua coluna de origem
      let card: Feedback | undefined;
      let fromStatus: FeedbackStatus | undefined;
      for (const c of COLUMNS) {
        const hit = board.columns[c.key].items.find((it) => it.id === id);
        if (hit) { card = hit; fromStatus = c.key; break; }
      }
      if (!card || !fromStatus || fromStatus === toStatus) return;

      const previousStatus = fromStatus;
      // 1) otimista: aplica localmente
      applyMove({ ...card, action_status: toStatus }, previousStatus);
      try {
        // 2) confirma no servidor e reconcilia com a versão canônica
        const updated = await api.post<Feedback>(`/api/feedbacks/${id}/move`, {
          status: toStatus,
        } satisfies FeedbackMoveInput);
        applyMove(updated, previousStatus);
        setErr(null);
      } catch (e) {
        // 3) reverte (volta o card pra coluna de origem)
        applyMove({ ...card, action_status: previousStatus }, toStatus);
        setErr(e instanceof Error ? e.message : String(e));
      }
    },
    [board, applyMove],
  );

  function onColumnDrop(e: React.DragEvent, col: FeedbackStatus) {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain") || draggingId;
    setOverColumn(null);
    setDraggingId(null);
    if (id) void moveByDrop(id, col);
  }

  const total = COLUMNS.reduce((sum, c) => sum + (board.columns[c.key]?.count ?? 0), 0);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Board</h1>
          <div className="page-sub">
            Triagem do feedback — arraste para mover entre as etapas
          </div>
        </div>
        <div className="page-head-actions">
          {!loading && <span className="refresh-note">{total} no board</span>}
        </div>
      </div>

      {/* Filtros de roteamento */}
      <div className="toolbar">
        <select
          value={teamTag}
          onChange={(e) => setTeamTag(e.target.value)}
          aria-label="Filtrar por time"
        >
          <option value="">Todos os times</option>
          {TEAM_OPTIONS.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <select
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
          aria-label="Filtrar por responsável"
        >
          <option value="">Todos os responsáveis</option>
          {assignee && !assigneeOptions.includes(assignee) && (
            <option value={assignee}>@{assignee}</option>
          )}
          {assigneeOptions.map((a) => (
            <option key={a} value={a}>@{a}</option>
          ))}
        </select>
      </div>

      {err && (
        <div className="flash err">
          Não consegui falar com o board ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      <div className="board-cols">
        {COLUMNS.map((c) => {
          const col = board.columns[c.key];
          const isOver = overColumn === c.key;
          return (
            <section
              key={c.key}
              className={`board-col ${isOver ? "is-over" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (overColumn !== c.key) setOverColumn(c.key);
              }}
              onDragLeave={(e) => {
                // só limpa se realmente saiu da coluna (não ao entrar num filho)
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setOverColumn((cur) => (cur === c.key ? null : cur));
                }
              }}
              onDrop={(e) => onColumnDrop(e, c.key)}
              aria-label={`Coluna ${c.label}`}
            >
              <header className="board-col-head">
                <span className="board-col-name">{c.label}</span>
                <span className="badge neutral">{col?.count ?? 0}</span>
              </header>

              <div className="board-col-body">
                {(col?.items ?? []).map((fb) => (
                  <BoardCard
                    key={fb.id}
                    fb={fb}
                    dragging={draggingId === fb.id}
                    onOpen={setOpened}
                    onDragStart={(f) => setDraggingId(f.id)}
                    onDragEnd={() => { setDraggingId(null); setOverColumn(null); }}
                  />
                ))}

                {(col?.count ?? 0) === 0 && !loading && (
                  <div className="board-col-empty">vazio</div>
                )}
                {(col?.count ?? 0) > (col?.items?.length ?? 0) && (
                  <div className="board-col-more">
                    + {(col!.count - col!.items.length)} mais (top 12 por urgência)
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>

      {opened && (
        <CardDetailModal
          fb={opened}
          improvements={improvements}
          onClose={() => setOpened(null)}
          onMoved={applyMove}
        />
      )}
    </div>
  );
}
