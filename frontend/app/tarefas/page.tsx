"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import AbordarModal, { waIcon, type AbordarTarget } from "@/components/AbordarModal";
import {
  api,
  type Tarefa,
  type TarefaCounts,
  type TarefaPriority,
  type TarefaStatus,
  type TarefasResponse,
} from "@/lib/api";

const PAGE_SIZE = 50;

const EMPTY_COUNTS: TarefaCounts = { aberta: 0, em_andamento: 0, concluida: 0, adiada: 0 };

const STATUS_OPTIONS: { value: TarefaStatus; label: string }[] = [
  { value: "aberta", label: "Aberta" },
  { value: "em_andamento", label: "Em andamento" },
  { value: "concluida", label: "Concluída" },
  { value: "adiada", label: "Adiada" },
];

const STATUS_LABEL: Record<TarefaStatus, string> = {
  aberta: "Aberta",
  em_andamento: "Em andamento",
  concluida: "Concluída",
  adiada: "Adiada",
};

/** Classe de badge por status (reusa a paleta de badges do globals.css). */
const STATUS_BADGE: Record<TarefaStatus, string> = {
  aberta: "open",
  em_andamento: "passive",
  concluida: "promoter",
  adiada: "neutral",
};

const PRIORITY_OPTIONS: { value: TarefaPriority; label: string }[] = [
  { value: "baixa", label: "Baixa" },
  { value: "normal", label: "Normal" },
  { value: "alta", label: "Alta" },
  { value: "urgente", label: "Urgente" },
];

const PRIORITY_LABEL: Record<TarefaPriority, string> = {
  baixa: "Baixa",
  normal: "Normal",
  alta: "Alta",
  urgente: "Urgente",
};

/** Badge de prioridade — urgente/alta puxam vermelho, normal neutro, baixa apagado. */
function priorityBadge(p: TarefaPriority) {
  const cls = p === "urgente" || p === "alta" ? "detractor" : p === "normal" ? "neutral" : "neutral";
  return <span className={`badge ${cls}`} title={`Prioridade ${PRIORITY_LABEL[p]}`}>{PRIORITY_LABEL[p]}</span>;
}

/** Rótulo legível do gatilho que originou a tarefa (lido de `meta.trigger_type`). */
const TRIGGER_LABEL: Record<string, string> = {
  nps_detractor: "Detrator",
  health_at_risk: "Conta em risco",
  inactive_days: "Inatividade",
  renewal_soon: "Renovação próxima",
  churn_detected: "Cancelamento",
};

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function isSameDay(iso: string | null, ref: Date): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return (
    d.getFullYear() === ref.getFullYear() &&
    d.getMonth() === ref.getMonth() &&
    d.getDate() === ref.getDate()
  );
}

/** Célula de SLA (due_at): mono; vermelho (`.renova-soon`) se vencida e ainda aberta. */
function slaCell(t: Tarefa, now: Date) {
  if (!t.due_at) return <span className="faint">—</span>;
  const due = new Date(t.due_at);
  const open = t.status !== "concluida" && t.status !== "adiada";
  const overdue = open && due.getTime() < now.getTime();
  return (
    <span className={`mono ${overdue ? "renova-soon" : "dim"}`} title={fmtDateTime(t.due_at)}>
      {fmtDateTime(t.due_at)}
    </span>
  );
}

/** Adapta uma Tarefa ao alvo mínimo que o AbordarModal precisa. */
function toAbordarTarget(t: Tarefa): AbordarTarget {
  return {
    contato_id: t.contato_id,
    contato_nome: t.contato_nome,
    contato_whatsapp: t.contato_whatsapp,
    abordado: false,
  };
}

// ===== Linha da fila ========================================================

function TarefaRow({
  t,
  onPatched,
  onAbordar,
}: {
  t: Tarefa;
  onPatched: (updated: Tarefa, previousStatus: TarefaStatus) => void;
  onAbordar: (t: Tarefa) => void;
}) {
  const [saving, setSaving] = useState(false);
  const now = useMemo(() => new Date(), []);
  const triggerType = (t.meta?.trigger_type as string | undefined) ?? null;

  async function changeStatus(next: TarefaStatus) {
    const prev = t.status;
    if (next === prev) return;
    setSaving(true);
    const optimistic: Tarefa = { ...t, status: next };
    onPatched(optimistic, prev);
    try {
      const updated = await api.patch<Tarefa>(`/api/tarefas/${t.id}`, { status: next });
      onPatched(updated, prev);
    } catch {
      onPatched(t, prev); // reverte
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td>
        <div className="cell-person">
          <Avatar name={t.contato_nome} seed={t.contato_id ?? t.contato_whatsapp} />
          <div className="cell-person-txt">
            {t.contato_id ? (
              <Link href={`/contatos/${t.contato_id}`} className="row-link">
                {t.contato_nome || "sem nome"}
              </Link>
            ) : (
              <span className="row-link">{t.contato_nome || "sem contato"}</span>
            )}
            <span className="mono cell-person-sub">{t.contato_whatsapp || "sem WhatsApp"}</span>
          </div>
        </div>
      </td>
      <td>
        {t.health !== null && t.health_band
          ? healthCell(t.health, t.health_band)
          : <span className="faint">—</span>}
      </td>
      <td>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="row-link" style={{ fontWeight: 600 }}>{t.title}</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            {triggerType && (
              <span className="badge type">{TRIGGER_LABEL[triggerType] ?? triggerType}</span>
            )}
            {priorityBadge(t.priority)}
          </div>
          {t.reason && (
            <span className="dim" style={{ fontSize: 12 }}>{t.reason}</span>
          )}
        </div>
      </td>
      <td>
        {t.playbook_id ? (
          <span className="chip">{t.playbook_nome || "playbook"}</span>
        ) : (
          <span className="faint" title="Tarefa criada manualmente">manual</span>
        )}
      </td>
      <td className="dim">{t.owner || <span className="faint">—</span>}</td>
      <td>{slaCell(t, now)}</td>
      <td>
        <select
          className="status-cell-select"
          value={t.status}
          onChange={(e) => changeStatus(e.target.value as TarefaStatus)}
          disabled={saving}
          aria-label="Status da tarefa"
          style={{
            fontFamily: "inherit", fontSize: 13, color: "var(--text)",
            background: "var(--ink)", border: "1px solid var(--charcoal-2)",
            borderRadius: "var(--radius-xs)", padding: "7px 11px", minHeight: 36, cursor: "pointer",
          }}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </td>
      <td>
        <button
          type="button"
          className="btn-wa-sm"
          onClick={() => onAbordar(t)}
          disabled={!t.contato_whatsapp}
          title="Abordar no WhatsApp"
        >
          {waIcon} WhatsApp
        </button>
      </td>
    </tr>
  );
}

// ===== Página ===============================================================

export default function TarefasPage() {
  const [items, setItems] = useState<Tarefa[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<TarefaCounts>(EMPTY_COUNTS);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // filtros
  const [status, setStatus] = useState<TarefaStatus | "">("");
  const [owner, setOwner] = useState("");
  const [priority, setPriority] = useState<TarefaPriority | "">("");
  const [sort, setSort] = useState<"prioridade" | "recente" | "sla">("prioridade");
  const [search, setSearch] = useState("");

  // overlay de abordagem
  const [abordando, setAbordando] = useState<Tarefa | null>(null);

  const buildQs = useCallback(
    (offset: number) => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      if (owner) qs.set("owner", owner);
      if (priority) qs.set("priority", priority);
      if (sort) qs.set("sort", sort);
      qs.set("limit", String(PAGE_SIZE));
      qs.set("offset", String(offset));
      return qs.toString();
    },
    [status, owner, priority, sort],
  );

  function normalize(raw: TarefasResponse | Tarefa[]): {
    items: Tarefa[];
    total: number;
    counts: TarefaCounts;
  } {
    if (Array.isArray(raw)) {
      return { items: raw, total: raw.length, counts: EMPTY_COUNTS };
    }
    return {
      items: raw.items ?? [],
      total: raw.total ?? (raw.items?.length ?? 0),
      counts: { ...EMPTY_COUNTS, ...(raw.counts_by_status ?? {}) },
    };
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await api.get<TarefasResponse | Tarefa[]>(`/api/tarefas?${buildQs(0)}`);
      const n = normalize(raw);
      setItems(n.items);
      setTotal(n.total);
      setCounts(n.counts);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [buildQs]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const raw = await api.get<TarefasResponse | Tarefa[]>(`/api/tarefas?${buildQs(items.length)}`);
      const n = normalize(raw);
      setItems((prev) => [...prev, ...n.items]);
      setTotal(n.total);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  const onPatched = useCallback((updated: Tarefa, previousStatus: TarefaStatus) => {
    setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
    if (updated.status !== previousStatus) {
      setCounts((c) => ({
        ...c,
        [previousStatus]: Math.max(0, (c[previousStatus] ?? 0) - 1),
        [updated.status]: (c[updated.status] ?? 0) + 1,
      }));
    }
  }, []);

  // Donos presentes nos dados carregados (filtro sem hard-code).
  const ownerOptions = useMemo(
    () => [...new Set(items.map((t) => t.owner).filter(Boolean) as string[])].sort(),
    [items],
  );

  // Busca client-side (cliente/título/motivo) por cima do que veio do backend.
  const q = search.trim().toLowerCase();
  const visible = useMemo(() => {
    if (!q) return items;
    return items.filter((t) =>
      [t.contato_nome, t.contato_whatsapp, t.title, t.reason, t.owner]
        .filter(Boolean)
        .some((v) => (v as string).toLowerCase().includes(q)),
    );
  }, [items, q]);

  // KPIs: Abertas (autoritativo via counts) · Vencidas e Concluídas hoje (derivadas dos itens).
  const now = useMemo(() => new Date(), [items]);
  const vencidas = useMemo(
    () =>
      items.filter(
        (t) =>
          t.status !== "concluida" &&
          t.status !== "adiada" &&
          t.due_at &&
          new Date(t.due_at).getTime() < now.getTime(),
      ).length,
    [items, now],
  );
  const concluidasHoje = useMemo(
    () => items.filter((t) => t.status === "concluida" && isSameDay(t.atualizada_em, now)).length,
    [items, now],
  );

  const hasMore = items.length < total && !q;
  const hasFilters = !!(status || owner || priority || search);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Tarefas</h1>
          <div className="page-sub">
            Fila priorizada de CS — contas a abordar hoje, geradas pelos playbooks ou criadas à mão
          </div>
        </div>
        {!loading && <span className="refresh-note">{total} no total</span>}
      </div>

      {/* KPIs */}
      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="card kpi">
          <div className="kpi-label">Abertas</div>
          <div className="kpi-value">{counts.aberta}</div>
          <div className="kpi-hint">aguardando ação</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Vencidas</div>
          <div className="kpi-value" style={{ color: vencidas > 0 ? "var(--detractor)" : undefined }}>
            {vencidas}
          </div>
          <div className="kpi-hint">SLA estourado (carregadas)</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Concluídas hoje</div>
          <div className="kpi-value">{concluidasHoje}</div>
          <div className="kpi-hint">fechadas no dia (carregadas)</div>
        </div>
      </div>

      {/* Toolbar de filtros */}
      <div className="toolbar">
        <label className="search">
          <span className="ico">🔍</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por cliente, tarefa, motivo…"
          />
        </label>
        <select value={status} onChange={(e) => setStatus(e.target.value as TarefaStatus | "")} aria-label="Filtrar por status">
          <option value="">Todos os status</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="Filtrar por dono">
          <option value="">Todos os donos</option>
          {ownerOptions.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
        <select value={priority} onChange={(e) => setPriority(e.target.value as TarefaPriority | "")} aria-label="Filtrar por prioridade">
          <option value="">Toda prioridade</option>
          {PRIORITY_OPTIONS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as "prioridade" | "recente" | "sla")} aria-label="Ordenar">
          <option value="prioridade">Por prioridade</option>
          <option value="sla">Por SLA</option>
          <option value="recente">Mais recentes</option>
        </select>
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar as tarefas ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Saúde</th>
                <th>Motivo</th>
                <th>Playbook</th>
                <th>Dono</th>
                <th>SLA</th>
                <th>Status</th>
                <th>Ação</th>
              </tr>
            </thead>
            <tbody>
              {!err && visible.length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <div className="empty">
                      <div className="big">✅</div>
                      {loading
                        ? "Carregando…"
                        : hasFilters
                        ? "Nenhuma tarefa bate com os filtros."
                        : "Fila vazia — nenhuma tarefa pendente 🎉"}
                    </div>
                  </td>
                </tr>
              )}
              {visible.map((t) => (
                <TarefaRow key={t.id} t={t} onPatched={onPatched} onAbordar={setAbordando} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {hasMore && (
        <div className="load-more">
          <button className="btn ghost" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Carregando…" : "Carregar mais"}
          </button>
        </div>
      )}

      {abordando && (
        <AbordarModal
          target={toAbordarTarget(abordando)}
          onClose={() => setAbordando(null)}
        />
      )}
    </div>
  );
}
