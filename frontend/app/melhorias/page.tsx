"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Modal from "@/components/Modal";
import {
  api,
  clusters,
  melhorias,
  type FeedbackCluster,
  type Improvement,
  type ImprovementEffort,
  type ImprovementInput,
  type ImprovementRoadmapItem,
  type ImprovementStatus,
  type NotifyRecipient,
  type NotifyResult,
} from "@/lib/api";

// emoji em .ts/.tsx só via \u{...} (o bundler do Next no Windows corrompe literais).
const EMOJI_PULL = "\u{1F3AF}"; // 🎯 — "puxar dor para o roadmap"
const EMOJI_HEART = "\u{1F49C}"; // 💜 — loop fechado (flash de sucesso)

// ===== vocabulário (estágios / esforço) =====================================

/** Estágios na ordem do funil (ideia → entregue). Cada um com rótulo humano e a
    classe de badge que melhor representa o "calor" (neutro → promotor → gold). */
const STAGES: { key: ImprovementStatus; label: string; badge: string }[] = [
  { key: "ideia", label: "Ideia", badge: "neutral" },
  { key: "planejada", label: "Planejada", badge: "open" },
  { key: "em_andamento", label: "Em andamento", badge: "passive" },
  { key: "entregue", label: "Entregue", badge: "promoter" },
  { key: "descartada", label: "Descartada", badge: "detractor" },
];

const STAGE_LABEL: Record<string, string> = Object.fromEntries(
  STAGES.map((s) => [s.key, s.label]),
);
const STAGE_BADGE: Record<string, string> = Object.fromEntries(
  STAGES.map((s) => [s.key, s.badge]),
);

const EFFORTS: { key: ImprovementEffort; label: string }[] = [
  { key: "P", label: "P · pequeno" },
  { key: "M", label: "M · médio" },
  { key: "G", label: "G · grande" },
  { key: "XG", label: "XG · enorme" },
];

const fmtNum = new Intl.NumberFormat("pt-BR");
const fmtDate = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" });

/** Lê o timestamp tolerando o drift `_at` (spec) × `_em` (backend atual). */
function notifiedAt(imp: Improvement): string | null {
  return imp.notified_at ?? imp.notified_em ?? null;
}

function fmtMaybeDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : fmtDate.format(d);
}

/** Mapeia o sentimento dominante do cluster para a classe + rótulo do badge .sent. */
function sentimentBadge(s: string | null): { cls: string; label: string } | null {
  switch (s) {
    case "negativo":
      return { cls: "s-neg", label: "negativo" };
    case "neutro":
      return { cls: "s-neu", label: "neutro" };
    case "positivo":
      return { cls: "s-pos", label: "positivo" };
    default:
      return null;
  }
}

// ===== card de uma melhoria na lista priorizada =============================

function ImprovementCard({
  imp,
  busy,
  onChangeStage,
  onCloseLoop,
  className = "",
  style,
}: {
  imp: ImprovementRoadmapItem;
  busy: boolean;
  onChangeStage: (status: ImprovementStatus) => void;
  onCloseLoop: () => void;
  /** Permite aplicar .reveal direto no .survey-item (preserva :first/:last-child). */
  className?: string;
  style?: React.CSSProperties;
}) {
  const badgeCls = STAGE_BADGE[imp.status] ?? "neutral";
  const delivered = imp.status === "entregue";
  const notified = notifiedAt(imp);
  const canCloseLoop = delivered && !notified;
  const target = fmtMaybeDate(imp.target_date);

  return (
    <div className={`survey-item ${className}`.trim()} style={style}>
      <div className="survey-name">
        {imp.title}
        <span className={`badge ${badgeCls}`}>{STAGE_LABEL[imp.status] ?? imp.status}</span>
        {notified && (
          <span className="badge abordado" title="Clientes já foram avisados">
            ✓ loop fechado
          </span>
        )}
      </div>

      {imp.description && <div className="survey-q">{imp.description}</div>}

      {/* métricas: nº de pedidos + score de prioridade */}
      <div className="imp-metrics">
        <span className="imp-demand" title="Feedbacks vinculados a esta melhoria">
          <b className="mono">{fmtNum.format(imp.feedback_count)}</b>{" "}
          {imp.feedback_count === 1 ? "cliente pediu isso" : "clientes pediram isso"}
        </span>
        {typeof imp.priority_score === "number" && (
          <span className="imp-score" title="Prioridade: pedidos × urgência × negatividade da dor">
            <span className="imp-score-lbl">prioridade</span>
            <span className="imp-score-val mono">{imp.priority_score.toFixed(1)}</span>
          </span>
        )}
      </div>

      {/* chips: esforço + dor de origem (clicável → Temas) + data-alvo */}
      {(imp.effort || imp.cluster_label || target) && (
        <div className="theme-chips imp-chips">
          {imp.effort && (
            <span className="chip" title="Esforço estimado">
              esforço {imp.effort}
            </span>
          )}
          {imp.cluster_label && (
            <Link
              href="/temas"
              className="chip imp-chip-link"
              title="Ver a dor de origem em Temas (Por significado)"
            >
              🎯 {imp.cluster_label}
            </Link>
          )}
          {target && (
            <span className="chip" title="Data-alvo">
              📅 {target}
            </span>
          )}
        </div>
      )}

      {/* ações: trocar estágio + fechar o loop */}
      <div className="imp-actions">
        <label className="imp-stage">
          <span className="act-label">Estágio</span>
          <select
            value={imp.status}
            disabled={busy}
            onChange={(e) => onChangeStage(e.target.value as ImprovementStatus)}
            aria-label={`Estágio de "${imp.title}"`}
          >
            {STAGES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        {canCloseLoop && (
          <button
            type="button"
            className="btn-wa-sm imp-close-loop"
            onClick={onCloseLoop}
            disabled={busy}
            title="Avisar quem pediu que a melhoria saiu"
          >
            ✓ Fechar o loop
          </button>
        )}
        {delivered && notified && (
          <span className="act-saved">clientes avisados ✓</span>
        )}
      </div>
    </div>
  );
}

// ===== modal "fechar o loop" (preview + confirmar envio) ====================

function RecipientRow({ r, kind }: { r: NotifyRecipient; kind: "send" | "skip" }) {
  const reasonLabel: Record<string, string> = {
    sem_whatsapp: "sem WhatsApp",
    sem_opt_in: "sem opt-in",
    cooldown: "enviado há pouco",
  };
  return (
    <div className={`notify-row ${kind === "skip" ? "is-skip" : ""}`}>
      <div className="notify-row-head">
        <span className="notify-who">{r.contato_nome || "sem nome"}</span>
        <span className="mono dim notify-phone">{r.contato_whatsapp}</span>
        {kind === "skip" && r.reason && (
          <span className="badge neutral notify-reason">{reasonLabel[r.reason] ?? r.reason}</span>
        )}
      </div>
      {kind === "send" && r.mensagem && <p className="confirm-quote notify-msg">{r.mensagem}</p>}
    </div>
  );
}

function CloseLoopModal({
  imp,
  preview,
  sending,
  error,
  onConfirm,
  onClose,
}: {
  imp: Improvement;
  preview: NotifyResult | null;
  sending: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const loading = preview === null && error === null;
  const willSend = preview?.would_send ?? [];
  const skipped = preview?.skipped ?? [];

  return (
    <Modal title="Fechar o loop" onClose={onClose} labelledById="close-loop-title">
      <div className="modal-body">
        <p className="confirm-text">
          Avisar pelo WhatsApp quem pediu <b>{imp.title}</b> que a melhoria saiu
          {preview?.theme ? (
            <>
              {" "}
              (mensagem personalizada com o tema <b>{preview.theme}</b>)
            </>
          ) : null}
          .
        </p>

        {error && <div className="flash err">{error}</div>}

        {loading && <div className="empty">Montando o preview…</div>}

        {!loading && !error && (
          <>
            <div className="notify-block">
              <div className="notify-block-head">
                <span className="act-label">
                  Vão receber ({willSend.length})
                </span>
              </div>
              {willSend.length === 0 ? (
                <p className="picker-empty">
                  Ninguém elegível agora (sem opt-in, sem WhatsApp ou em cooldown). Nada será
                  enviado.
                </p>
              ) : (
                willSend.map((r) => <RecipientRow key={r.contato_id} r={r} kind="send" />)
              )}
            </div>

            {skipped.length > 0 && (
              <div className="notify-block">
                <div className="notify-block-head">
                  <span className="act-label">Fora desta vez ({skipped.length})</span>
                </div>
                {skipped.map((r) => (
                  <RecipientRow key={r.contato_id} r={r} kind="skip" />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="modal-foot">
        <button type="button" className="btn ghost" onClick={onClose} disabled={sending}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-wa"
          onClick={onConfirm}
          disabled={loading || sending || willSend.length === 0}
          title={willSend.length === 0 ? "Ninguém elegível para receber" : "Enviar de verdade"}
        >
          {sending ? "Enviando…" : `Confirmar envio (${willSend.length})`}
        </button>
      </div>
    </Modal>
  );
}

// ===== painel "Puxar dos temas" (dores pendentes → roadmap) =================

/** Uma dor pendente (cluster sem melhoria) na lista do painel "Puxar dos temas". */
function PendingPainRow({
  cluster,
  busy,
  onPull,
  className = "",
  style,
}: {
  cluster: FeedbackCluster;
  busy: boolean;
  onPull: () => void;
  /** Permite aplicar .reveal direto no .survey-item (preserva :first/:last-child). */
  className?: string;
  style?: React.CSSProperties;
}) {
  const title = cluster.label ?? "Dor sem rótulo";
  const sent = sentimentBadge(cluster.dominant_sentiment);

  return (
    <div className={`survey-item ${className}`.trim()} style={style}>
      <div className="survey-name">
        {title}
        {sent && <span className={`badge sent ${sent.cls}`}>{sent.label}</span>}
      </div>

      {cluster.description && <div className="survey-q">{cluster.description}</div>}

      <div className="imp-metrics">
        <span className="imp-demand" title="Feedbacks agrupados nesta dor">
          <b className="mono">{fmtNum.format(cluster.item_count)}</b>{" "}
          {cluster.item_count === 1 ? "cliente pediu isso" : "clientes pediram isso"}
        </span>
        <span className="imp-score" title="Índice de dor: volume × fração negativa">
          <span className="imp-score-lbl">dor</span>
          <span className="imp-score-val mono">{cluster.pain_score.toFixed(1)}</span>
        </span>
      </div>

      {cluster.top_themes.length > 0 && (
        <div className="theme-chips imp-chips">
          {cluster.top_themes.slice(0, 4).map((t, i) => (
            <span key={`${t}-${i}`} className="chip">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="imp-actions">
        <button
          type="button"
          className="btn sm imp-close-loop"
          onClick={onPull}
          disabled={busy}
          title="Criar uma melhoria a partir desta dor e vincular os feedbacks"
        >
          {busy ? "Puxando…" : `${EMOJI_PULL} Puxar para o roadmap`}
        </button>
      </div>
    </div>
  );
}

function PullFromThemes({
  pains,
  loading,
  error,
  busyId,
  onPull,
}: {
  pains: FeedbackCluster[];
  loading: boolean;
  error: string | null;
  busyId: string | null;
  onPull: (cluster: FeedbackCluster) => void;
}) {
  return (
    <div className="card" style={{ padding: "18px 20px" }}>
      <h2 className="section-title">Puxar dos temas</h2>
      <p className="section-sub">
        Dores descobertas por significado que ainda não viraram melhoria — as mais
        doloridas primeiro. Puxe uma para o roadmap já com os feedbacks vinculados.
      </p>

      {error && (
        <div className="flash err">
          Não consegui carregar as dores ({error}).
        </div>
      )}

      {!error && loading ? (
        <div className="imp-list" style={{ margin: "0 -20px -18px" }} aria-busy="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <ImprovementRowSkeleton key={i} />
          ))}
        </div>
      ) : !error && pains.length === 0 ? (
        <div className="empty">
          <div className="empty-illu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          </div>
          <div className="empty-title">Nenhuma dor pendente</div>
          <p className="empty-sub">
            Tudo já está no roadmap. Quando novos feedbacks formarem uma dor em{" "}
            <b>Temas → Por significado</b>, ela aparece aqui para ser puxada.
          </p>
        </div>
      ) : (
        !error && (
          <div className="imp-list" style={{ margin: "0 -20px -18px" }}>
            {pains.map((c, i) => (
              <PendingPainRow
                key={c.id}
                cluster={c}
                busy={busyId === c.id}
                onPull={() => onPull(c)}
                className="reveal"
                style={{ ["--i" as string]: i } as React.CSSProperties}
              />
            ))}
          </div>
        )
      )}
    </div>
  );
}

// ===== skeletons (espelham a forma dos itens) ===============================

/** Placeholder de um item da lista priorizada (título + métricas + chips). */
function ImprovementRowSkeleton() {
  return (
    <div className="survey-item" aria-busy="true">
      <div className="sk-line w-60" style={{ marginTop: 4 }} />
      <div className="sk-line w-90" />
      <div className="imp-metrics" style={{ marginTop: 10 }}>
        <div className="sk-line" style={{ width: 130, margin: 0 }} />
        <div className="sk-line" style={{ width: 80, margin: 0 }} />
      </div>
    </div>
  );
}

/** Lista de skeletons dentro de um card (usada na coluna do roadmap). */
function ImprovementListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="card imp-list" aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <ImprovementRowSkeleton key={i} />
      ))}
    </div>
  );
}

// ===== página ===============================================================

export default function MelhoriasPage() {
  const [items, setItems] = useState<ImprovementRoadmapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // id da melhoria com PATCH/notify em voo (trava os controles do card)
  const [busyId, setBusyId] = useState<string | null>(null);

  // filtro de estágio
  const [filter, setFilter] = useState<ImprovementStatus | "todos">("todos");

  // form de criação
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [effort, setEffort] = useState<ImprovementEffort | "">("");
  const [targetDate, setTargetDate] = useState("");
  const [stage, setStage] = useState<ImprovementStatus>("ideia");
  const [saving, setSaving] = useState(false);

  // modal "fechar o loop"
  const [loopFor, setLoopFor] = useState<Improvement | null>(null);
  const [preview, setPreview] = useState<NotifyResult | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  // painel "Puxar dos temas" — dores (clusters) sem melhoria ainda
  const [pains, setPains] = useState<FeedbackCluster[]>([]);
  const [painsLoading, setPainsLoading] = useState(true);
  const [painsErr, setPainsErr] = useState<string | null>(null);
  // id do cluster sendo puxado (trava só o botão daquela dor)
  const [pullingId, setPullingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = filter === "todos" ? "" : `?status=${filter}`;
      const rows = await api.get<ImprovementRoadmapItem[]>(`/api/improvements/roadmap${qs}`);
      setItems(rows);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  // Carrega as dores pendentes: days alto (todo o histórico), ordenadas por dor;
  // filtra clusters sem melhoria e com itens, do mais dolorido pro menos.
  const loadPains = useCallback(async () => {
    setPainsLoading(true);
    try {
      const res = await clusters.list({ days: 3650, sort: "dor" });
      const pend = res.clusters
        .filter((c) => c.improvement_id == null && c.item_count > 0)
        .sort((a, b) => b.pain_score - a.pain_score);
      setPains(pend);
      setPainsErr(null);
    } catch (e) {
      setPainsErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPainsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPains();
  }, [loadPains]);

  // total de pedidos no roadmap — número-âncora do cabeçalho
  const totalDemand = useMemo(
    () => items.reduce((s, it) => s + (it.feedback_count || 0), 0),
    [items],
  );

  async function createImprovement(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFlash(null);
    try {
      const body: ImprovementInput = {
        title: title.trim(),
        description: description.trim() || null,
        effort: effort || null,
        target_date: targetDate || null,
        status: stage,
      };
      await api.post<Improvement>("/api/improvements", body);
      setFlash({ kind: "ok", msg: `Melhoria "${title.trim()}" criada.` });
      setTitle("");
      setDescription("");
      setEffort("");
      setTargetDate("");
      setStage("ideia");
      await load();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  async function changeStage(imp: ImprovementRoadmapItem, status: ImprovementStatus) {
    if (status === imp.status) return;
    setBusyId(imp.id);
    setFlash(null);
    try {
      await api.patch<Improvement>(`/api/improvements/${imp.id}`, { status });
      setFlash({ kind: "ok", msg: `"${imp.title}" → ${STAGE_LABEL[status] ?? status}.` });
      await load();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  }

  // "Puxar para o roadmap": cria a melhoria a partir da dor (idempotente) e
  // recarrega o roadmap E a lista de dores (a puxada some, pois ganha improvement_id).
  async function pullFromCluster(cluster: FeedbackCluster) {
    setPullingId(cluster.id);
    setFlash(null);
    const label = cluster.label ?? "Dor sem rótulo";
    try {
      const imp = await melhorias.fromCluster(cluster.id);
      setFlash({
        kind: "ok",
        msg: `${EMOJI_PULL} "${imp.title || label}" entrou no roadmap com os feedbacks vinculados.`,
      });
      await Promise.all([load(), loadPains()]);
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setPullingId(null);
    }
  }

  // Abre o modal e busca o preview (notify SEM confirm = não envia, não grava).
  async function openCloseLoop(imp: Improvement) {
    setLoopFor(imp);
    setPreview(null);
    setPreviewErr(null);
    try {
      const res = await api.post<NotifyResult>(`/api/improvements/${imp.id}/notify`, {});
      setPreview(res);
    } catch (e) {
      setPreviewErr(e instanceof Error ? e.message : String(e));
    }
  }

  function closeLoopModal() {
    setLoopFor(null);
    setPreview(null);
    setPreviewErr(null);
    setSending(false);
  }

  // Confirma: notify COM confirm=true = envia de verdade + grava notified_at.
  async function confirmCloseLoop() {
    if (!loopFor) return;
    setSending(true);
    try {
      const res = await api.post<NotifyResult>(
        `/api/improvements/${loopFor.id}/notify?confirm=true`,
        {},
      );
      const n = res.sent_count ?? res.would_send.length;
      setFlash({
        kind: "ok",
        msg: `${EMOJI_HEART} Loop fechado: ${n} cliente${n === 1 ? "" : "s"} avisado${n === 1 ? "" : "s"} no WhatsApp.`,
      });
      closeLoopModal();
      await load();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
      setSending(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Melhorias</h1>
          <div className="page-sub">
            O roadmap que nasce das dores dos clientes — priorize, entregue e feche o loop avisando
            quem pediu
          </div>
        </div>
        {!loading && !err && items.length > 0 && (
          <span className="refresh-note">
            {fmtNum.format(items.length)} {items.length === 1 ? "melhoria" : "melhorias"} ·{" "}
            {fmtNum.format(totalDemand)} pedidos
          </span>
        )}
      </div>

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="two-col">
        {/* ---- esquerda: lista priorizada ---- */}
        <div>
          <div className="status-tabs" role="tablist" aria-label="Filtrar por estágio">
            {(["todos", ...STAGES.map((s) => s.key)] as (ImprovementStatus | "todos")[]).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={filter === k}
                className={`status-tab ${filter === k ? "active" : ""}`}
                onClick={() => setFilter(k)}
              >
                {k === "todos" ? "Todas" : STAGE_LABEL[k]}
              </button>
            ))}
          </div>

          {err && (
            <div className="flash err">
              Não consegui carregar o roadmap ({err}). A API está rodando em{" "}
              <span className="mono">localhost:8000</span>?
            </div>
          )}

          {!err && loading && items.length === 0 ? (
            <ImprovementListSkeleton />
          ) : !err && items.length === 0 ? (
            <div className="card">
              <div className="empty">
                <div className="empty-illu">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M9 18h6" />
                    <path d="M10 21h4" />
                    <path d="M12 3a6 6 0 0 0-4 10.5c.6.6 1 1.4 1 2.5h6c0-1.1.4-1.9 1-2.5A6 6 0 0 0 12 3z" />
                  </svg>
                </div>
                <div className="empty-title">
                  {filter === "todos"
                    ? "Nenhuma melhoria ainda"
                    : `Nada em "${STAGE_LABEL[filter] ?? filter}"`}
                </div>
                <p className="empty-sub">
                  Crie uma ao lado, ou vá em <b>Temas → Por significado</b> e use{" "}
                  <b>“Virar melhoria”</b> numa dor para começar o roadmap já com os feedbacks
                  vinculados.
                </p>
              </div>
            </div>
          ) : (
            !err && (
              <div className="card imp-list">
                {items.map((imp, i) => (
                  <ImprovementCard
                    key={imp.id}
                    imp={imp}
                    busy={busyId === imp.id}
                    onChangeStage={(s) => changeStage(imp, s)}
                    onCloseLoop={() => openCloseLoop(imp)}
                    className="reveal"
                    style={{ ["--i" as string]: i } as React.CSSProperties}
                  />
                ))}
              </div>
            )
          )}
        </div>

        {/* ---- direita: puxar dos temas + criar melhoria ---- */}
        <div className="imp-side">
          <PullFromThemes
            pains={pains}
            loading={painsLoading}
            error={painsErr}
            busyId={pullingId}
            onPull={pullFromCluster}
          />

          <div className="card" style={{ padding: "18px 20px" }}>
            <h2 className="section-title">Nova melhoria</h2>
          <p className="section-sub">
            Registre algo que você vai construir. Vincule a dores depois pela aba Temas.
          </p>
          <form onSubmit={createImprovement}>
            <div className="field">
              <label>Título</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="ex.: Reduzir tempo de carregamento do simulado"
                required
                maxLength={200}
              />
            </div>
            <div className="field">
              <label>Descrição (opcional)</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="O que vai mudar e por quê"
                maxLength={4000}
              />
            </div>
            <div className="form-row-2">
              <div className="field">
                <label>Esforço</label>
                <select value={effort} onChange={(e) => setEffort(e.target.value as ImprovementEffort | "")}>
                  <option value="">—</option>
                  {EFFORTS.map((ef) => (
                    <option key={ef.key} value={ef.key}>
                      {ef.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Data-alvo</label>
                <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label>Estágio inicial</label>
              <select value={stage} onChange={(e) => setStage(e.target.value as ImprovementStatus)}>
                {STAGES.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <button className="btn" disabled={saving || !title.trim()}>
              {saving ? "Criando…" : "Criar melhoria"}
            </button>
          </form>
          </div>
        </div>
      </div>

      {loopFor && (
        <CloseLoopModal
          imp={loopFor}
          preview={preview}
          sending={sending}
          error={previewErr}
          onConfirm={confirmCloseLoop}
          onClose={closeLoopModal}
        />
      )}
    </div>
  );
}
