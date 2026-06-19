"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Search, Flame, MessageCircle } from "lucide-react";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import AbordarModal, { waIcon, type AbordarTarget } from "@/components/AbordarModal";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  api,
  tarefas as tarefasApi,
  type Tarefa,
  type TarefaCounts,
  type TarefaPriority,
  type TarefaStatus,
  type TarefasResponse,
} from "@/lib/api";

const PAGE_SIZE = 50;

const EMPTY_COUNTS: TarefaCounts = { aberta: 0, em_andamento: 0, concluida: 0, adiada: 0 };

/** Abas por status (espelha o padrão de status-tabs do inbox de Feedbacks). */
const STATUS_TABS: { key: TarefaStatus; label: string }[] = [
  { key: "aberta", label: "Aberta" },
  { key: "em_andamento", label: "Em andamento" },
  { key: "concluida", label: "Concluída" },
  { key: "adiada", label: "Adiada" },
];

const STATUS_OPTIONS: { value: TarefaStatus; label: string }[] = STATUS_TABS.map((s) => ({
  value: s.key,
  label: s.label,
}));

const STATUS_LABEL: Record<TarefaStatus, string> = {
  aberta: "Aberta",
  em_andamento: "Em andamento",
  concluida: "Concluída",
  adiada: "Adiada",
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

/** Badge de prioridade — urgente/alta puxam vermelho, normal/baixa neutro. */
function priorityBadge(p: TarefaPriority) {
  const variant = p === "urgente" || p === "alta" ? "negative" : "neutral";
  return (
    <Badge variant={variant} title={`Prioridade ${PRIORITY_LABEL[p]}`}>
      {PRIORITY_LABEL[p]}
    </Badge>
  );
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

/** Linha-fantasma da fila durante o load: 8 colunas espelhando a linha real. */
function SkeletonRow() {
  return (
    <tr aria-hidden>
      <td>
        <div className="cell-person">
          <div className="sk-circle" />
          <div className="cell-person-txt" style={{ flex: 1 }}>
            <div className="sk-line sk-sm w-70" style={{ margin: "2px 0" }} />
            <div className="sk-line sk-sm w-50" style={{ margin: "2px 0" }} />
          </div>
        </div>
      </td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div className="sk-line" style={{ width: 70, margin: 0 }} />
        </div>
      </td>
      <td>
        <div className="sk-line w-80" style={{ margin: "2px 0" }} />
        <div className="sk-line sk-sm w-50" style={{ margin: "6px 0 2px" }} />
      </td>
      <td><div className="sk-line w-60" style={{ margin: 0 }} /></td>
      <td><div className="sk-line w-50" style={{ margin: 0 }} /></td>
      <td><div className="sk-line w-70" style={{ margin: 0 }} /></td>
      <td><div className="sk-line" style={{ width: 90, height: 30, margin: 0 }} /></td>
      <td><div className="sk-line" style={{ width: 96, height: 30, margin: 0 }} /></td>
    </tr>
  );
}

/** SVG discreto p/ a fila vazia: checklist (stroke=currentColor). */
const EMPTY_TASKS = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M9 11l3 3L22 4" />
    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
  </svg>
);

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
  index,
  onPatched,
  onAbordar,
}: {
  t: Tarefa;
  index: number;
  onPatched: (updated: Tarefa, previousStatus: TarefaStatus) => void;
  onAbordar: (t: Tarefa) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const now = useMemo(() => new Date(), []);
  const triggerType = (t.meta?.trigger_type as string | undefined) ?? null;

  async function changeStatus(next: TarefaStatus) {
    const prev = t.status;
    if (next === prev) return;
    setSaving(true);
    setError(null);
    const optimistic: Tarefa = { ...t, status: next };
    onPatched(optimistic, prev);
    try {
      const updated = await api.patch<Tarefa>(`/api/tarefas/${t.id}`, { status: next });
      // O PATCH não devolve feedback_preview — preserva o que já tínhamos do GET.
      onPatched({ ...updated, feedback_preview: updated.feedback_preview ?? t.feedback_preview }, prev);
    } catch (e) {
      onPatched(t, prev); // reverte
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr
      className="reveal"
      style={{ ["--i" as string]: Math.min(index, 12) } as React.CSSProperties}
    >
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
              <Badge variant="outline">{TRIGGER_LABEL[triggerType] ?? triggerType}</Badge>
            )}
            {priorityBadge(t.priority)}
            {t.feedback_id && (
              <Badge variant="neutral" title="Tarefa nasceu de um feedback do cliente">
                <MessageCircle size={11} aria-hidden /> do feedback
              </Badge>
            )}
          </div>
          {t.reason && (
            <span className="dim" style={{ fontSize: 12 }}>{t.reason}</span>
          )}
          {/* Trecho do feedback vinculado (quando houver) — fecha o loop com a dor real. */}
          {t.feedback_preview && (
            <span
              className="dim"
              style={{
                fontSize: 12, fontStyle: "italic",
                borderLeft: "2px solid var(--charcoal-2)", paddingLeft: 8, marginTop: 2,
                color: "var(--text-dim)", textWrap: "pretty",
              }}
              title={t.feedback_preview}
            >
              {"\u{201C}"}{t.feedback_preview}{"\u{201D}"}
            </span>
          )}
        </div>
      </td>
      <td>
        {t.playbook_id ? (
          <span className="chip">{t.playbook_nome || "playbook"}</span>
        ) : (
          <span className="faint" title="Tarefa criada manualmente ou gerada de feedback">manual</span>
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
        {error && (
          <div className="badge detractor" title={error} style={{ marginTop: 6 }}>
            erro ao salvar
          </div>
        )}
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
  // Busca por contato (nome/WhatsApp) + título/motivo — client-side por cima do lote.
  const [search, setSearch] = useState("");

  // "Gerar tarefas das dores"
  const [gerando, setGerando] = useState(false);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

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

  /** Gera tarefas a partir das dores (feedbacks churn + negativo sem tarefa) e recarrega. */
  async function gerarDasDores() {
    if (gerando) return;
    setGerando(true);
    setFlash(null);
    try {
      const res = await tarefasApi.gerarDeFeedbacks({ tipo: "churn", sentimento: "negativo" });
      if (res.criadas > 0) {
        const plural = res.criadas === 1 ? "tarefa criada" : "tarefas criadas";
        const extra =
          res.ja_existiam > 0
            ? ` (${res.ja_existiam} ${res.ja_existiam === 1 ? "feedback já tinha" : "feedbacks já tinham"} tarefa).`
            : ".";
        setFlash({
          kind: "ok",
          text: `${"\u{2705}"} ${res.criadas} ${plural} a partir das dores${extra}`,
        });
      } else if (res.ja_existiam > 0) {
        setFlash({
          kind: "ok",
          text: `${"\u{1F44D}"} Nada novo: as dores recentes (cancelamento + negativo) já viraram tarefa.`,
        });
      } else {
        setFlash({
          kind: "ok",
          text: `${"\u{1F44C}"} Nenhuma dor de cancelamento negativa pendente no momento.`,
        });
      }
      // Mostra as recém-criadas no topo: volta para "Todas" + ordena por mais recentes.
      if (res.criadas > 0) {
        setStatus("");
        setSort("recente");
      }
      await load();
    } catch (e) {
      setFlash({
        kind: "err",
        text: `Não consegui gerar as tarefas (${e instanceof Error ? e.message : String(e)}).`,
      });
    } finally {
      setGerando(false);
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

  // Busca client-side (contato/título/motivo) por cima do que veio do backend.
  const q = search.trim().toLowerCase();
  const visible = useMemo(() => {
    if (!q) return items;
    return items.filter((t) =>
      [t.contato_nome, t.contato_whatsapp, t.title, t.reason, t.owner, t.feedback_preview]
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
      <Reveal className="page-head">
        <div>
          <h1 className="page-title">Tarefas</h1>
          <div className="page-sub">
            Fila priorizada de CS — contas a abordar hoje, geradas pelos playbooks, criadas à mão ou puxadas das dores
          </div>
        </div>
        <div className="page-head-actions">
          {!loading && <span className="refresh-note">{total} no total</span>}
          <Button
            onClick={gerarDasDores}
            disabled={gerando}
            title="Cria tarefas a partir dos feedbacks de cancelamento negativos que ainda não viraram tarefa"
          >
            <Flame size={15} aria-hidden />
            {gerando ? "Gerando…" : "Gerar tarefas das dores"}
          </Button>
        </div>
      </Reveal>

      {flash && (
        <div className={`flash ${flash.kind === "ok" ? "ok" : "err"}`}>{flash.text}</div>
      )}

      {/* KPIs */}
      <Reveal delay={0.05} className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
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
      </Reveal>

      {/* Abas por status, com contagens de counts_by_status */}
      <Reveal delay={0.08} className="status-tabs">
        <button
          type="button"
          className={`status-tab ${status === "" ? "active" : ""}`}
          onClick={() => setStatus("")}
        >
          Todas
        </button>
        {STATUS_TABS.map((s) => (
          <button
            type="button"
            key={s.key}
            className={`status-tab ${status === s.key ? "active" : ""}`}
            onClick={() => setStatus(s.key)}
          >
            {s.label}
            <span className="tab-count">{counts[s.key] ?? 0}</span>
          </button>
        ))}
      </Reveal>

      {/* Toolbar de filtros */}
      <Reveal delay={0.1} className="toolbar">
        <label className="search">
          <span className="ico"><Search size={15} aria-hidden /></span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por contato, tarefa, motivo…"
          />
        </label>
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
      </Reveal>

      {err && (
        <div className="flash err">
          Não consegui carregar as tarefas ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      <Reveal delay={0.13} className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Saúde</th>
                <th>Tarefa</th>
                <th>Playbook</th>
                <th>Dono</th>
                <th>SLA</th>
                <th>Status</th>
                <th>Ação</th>
              </tr>
            </thead>
            <tbody aria-busy={loading || undefined}>
              {loading && items.length === 0 &&
                Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)}
              {!loading && !err && visible.length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <div className="empty">
                      <div className="empty-illu">{EMPTY_TASKS}</div>
                      <div className="empty-title">
                        {status
                          ? `Nada em "${STATUS_LABEL[status as TarefaStatus]}"`
                          : hasFilters
                          ? "Nenhuma tarefa com esses filtros"
                          : "Fila vazia"}
                      </div>
                      <p className="empty-sub">
                        {status
                          ? "Nenhuma tarefa neste status agora."
                          : hasFilters
                          ? "Tente afrouxar a busca ou trocar os filtros."
                          : "Nenhuma tarefa pendente \u{2014} puxe as dores recentes para começar."}
                      </p>
                      {!status && !hasFilters && (
                        <div className="empty-cta">
                          <Button onClick={gerarDasDores} disabled={gerando}>
                            <Flame size={15} aria-hidden />
                            {gerando ? "Gerando…" : "Gerar tarefas das dores"}
                          </Button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
              {(!loading || items.length > 0) && visible.map((t, i) => (
                <TarefaRow key={t.id} t={t} index={i} onPatched={onPatched} onAbordar={setAbordando} />
              ))}
            </tbody>
          </table>
        </div>
      </Reveal>

      {hasMore && (
        <div className="load-more">
          <Button variant="ghost" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Carregando…" : "Carregar mais"}
          </Button>
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
