"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Modal from "@/components/Modal";
import Avatar from "@/components/Avatar";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

/** Destinatário do "fechar o loop" + campos opcionais que o backend pode mandar
 *  para o chip "pagante" (a tipagem canônica vive em lib/api.ts e é off-limits
 *  aqui; estendemos INLINE e lemos defensivamente — sem o campo, sem o chip). */
type LoopRecipient = NotifyRecipient & {
  pagante?: boolean | null;
  is_paying?: boolean | null;
  plano?: string | null;
};

function isPaying(r: LoopRecipient): boolean {
  return r.pagante === true || r.is_paying === true;
}

// ===== vocabulário (estágios / esforço / colunas do Kanban) =================

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

/** As 3 colunas do Kanban "Você pediu, a gente fez". Cada coluna agrega um ou
    mais estágios; "descartada" fica fora (não é fluxo de entrega). */
const COLUMNS: {
  key: "ideias" | "fazendo" | "entregue";
  label: string;
  /** Para onde o card vai ao cair nesta coluna (estágio canônico da coluna). */
  drop: ImprovementStatus;
  statuses: ImprovementStatus[];
}[] = [
  { key: "ideias", label: "Ideias", drop: "ideia", statuses: ["ideia", "planejada"] },
  { key: "fazendo", label: "Fazendo", drop: "em_andamento", statuses: ["em_andamento"] },
  { key: "entregue", label: "Entregue", drop: "entregue", statuses: ["entregue"] },
];

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

/** Mascara o miolo do telefone p/ a lista do modal (cuidado com a pessoa):
    mantém DDI/DDD e os 4 últimos dígitos, oculta o resto. "+5524998365809"
    → "+55 24 9****-5809". Tolera formatos curtos/sem dígitos. */
function maskPhone(raw: string | null | undefined): string {
  const s = (raw || "").trim();
  if (!s) return "sem telefone";
  const digits = s.replace(/\D/g, "");
  if (digits.length < 6) return s; // curto demais p/ mascarar com sentido
  const last4 = digits.slice(-4);
  const ddi = digits.length >= 12 ? digits.slice(0, 2) : "";
  const ddd = digits.length >= 10 ? digits.slice(ddi.length, ddi.length + 2) : "";
  const lead = digits.length >= 11 ? "9" : "";
  const parts = [ddi && `+${ddi}`, ddd, `${lead}****-${last4}`].filter(Boolean);
  return parts.join(" ");
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

// ===== card de uma melhoria no Kanban =======================================

/** Chip "📊 N clientes pediram" — a demanda que justifica a melhoria. Mono no
    número (dado verificável), ícone de barras como glifo de volume. */
function DemandChip({ n }: { n: number }) {
  return (
    <span className="imp-demand-chip" title="Feedbacks vinculados a esta melhoria">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M5 20V10" />
        <path d="M12 20V4" />
        <path d="M19 20v-6" />
      </svg>
      <b className="mono">{fmtNum.format(n)}</b>
      <span>{n === 1 ? "cliente pediu" : "clientes pediram"}</span>
    </span>
  );
}

function ImprovementCard({
  imp,
  busy,
  onChangeStage,
  onCloseLoop,
}: {
  imp: ImprovementRoadmapItem;
  busy: boolean;
  onChangeStage: (status: ImprovementStatus) => void;
  onCloseLoop: () => void;
}) {
  const delivered = imp.status === "entregue";
  const notified = notifiedAt(imp);
  const canCloseLoop = delivered && !notified;
  const target = fmtMaybeDate(imp.target_date);

  return (
    <div className={`card board-card imp-card ${busy ? "is-busy" : ""}`.trim()}>
      <div className="imp-card-title">{imp.title}</div>

      {imp.description && <p className="board-card-text imp-card-desc">{imp.description}</p>}

      {/* a demanda: quantos clientes pediram isso */}
      <DemandChip n={imp.feedback_count} />

      {/* chips: esforço + dor de origem (clicável → Mapeamento) + data-alvo */}
      {(imp.effort || imp.cluster_label || target) && (
        <div className="board-card-meta imp-card-meta">
          {imp.effort && (
            <span className="chip" title="Esforço estimado">
              esforço {imp.effort}
            </span>
          )}
          {imp.cluster_label && (
            <Link
              href="/temas"
              className="chip imp-chip-link"
              title="Ver a dor de origem em Mapeamento (Por significado)"
            >
              {EMOJI_PULL} {imp.cluster_label}
            </Link>
          )}
          {target && (
            <span className="chip" title="Data-alvo">
              📅 {target}
            </span>
          )}
        </div>
      )}

      {/* faixa de loop: na coluna Entregue, convida a avisar quem pediu */}
      {canCloseLoop && (
        <div className="imp-loop-band">
          <span className="imp-loop-msg">
            <b className="mono">{fmtNum.format(imp.feedback_count)}</b>{" "}
            {imp.feedback_count === 1 ? "cliente esperando retorno" : "clientes esperando retorno"}
          </span>
          <button
            type="button"
            className="btn btn-wa sm imp-loop-cta"
            onClick={onCloseLoop}
            disabled={busy}
            title="Avisar pelo WhatsApp quem pediu que a melhoria saiu"
          >
            Avisar
          </button>
        </div>
      )}
      {delivered && notified && (
        <div className="imp-loop-done">
          <span className="badge promoter">✓ loop fechado</span>
          <span className="imp-loop-done-sub">clientes avisados</span>
        </div>
      )}

      {/* mover de coluna = trocar o estágio (PATCH status) */}
      <label className="imp-stage imp-card-stage">
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
    </div>
  );
}

// ===== Kanban: 3 colunas (Ideias / Fazendo / Entregue) ======================

function KanbanColumn({
  col,
  items,
  busyId,
  onChangeStage,
  onCloseLoop,
}: {
  col: (typeof COLUMNS)[number];
  items: ImprovementRoadmapItem[];
  busyId: string | null;
  onChangeStage: (imp: ImprovementRoadmapItem, status: ImprovementStatus) => void;
  onCloseLoop: (imp: Improvement) => void;
}) {
  return (
    <section className="board-col imp-col" aria-label={col.label}>
      <div className="board-col-head">
        <span className="board-col-name">{col.label}</span>
        <span className="board-col-count mono">{items.length}</span>
      </div>
      <div className="board-col-body">
        {items.length === 0 ? (
          <div className="board-col-empty">nada aqui</div>
        ) : (
          items.map((imp) => (
            <ImprovementCard
              key={imp.id}
              imp={imp}
              busy={busyId === imp.id}
              onChangeStage={(s) => onChangeStage(imp, s)}
              onCloseLoop={() => onCloseLoop(imp)}
            />
          ))
        )}
      </div>
    </section>
  );
}

// ===== modal "Avisar quem pediu" (preview + confirmar envio) ================

/** Linha de um destinatário que VAI receber: avatar + nome + telefone parcial
    + chip "pagante" (se o backend informar). Espelha o mockup_loop.png. */
function SendRecipientRow({ r }: { r: LoopRecipient }) {
  return (
    <div className="loop-recip">
      <Avatar name={r.contato_nome} seed={r.contato_id} size={36} />
      <div className="loop-recip-txt">
        <span className="loop-recip-name">{r.contato_nome || "sem nome"}</span>
        <span className="loop-recip-phone mono">{maskPhone(r.contato_whatsapp)}</span>
      </div>
      {isPaying(r) && <span className="badge promoter loop-recip-pag">pagante</span>}
    </div>
  );
}

/** Linha de quem ficou de fora desta vez, com o motivo. */
function SkipRecipientRow({ r }: { r: LoopRecipient }) {
  const reasonLabel: Record<string, string> = {
    sem_whatsapp: "sem WhatsApp",
    sem_opt_in: "sem opt-in",
    cooldown: "avisado há pouco",
  };
  return (
    <div className="loop-recip is-skip">
      <Avatar name={r.contato_nome} seed={r.contato_id} size={36} />
      <div className="loop-recip-txt">
        <span className="loop-recip-name">{r.contato_nome || "sem nome"}</span>
        <span className="loop-recip-phone mono">{maskPhone(r.contato_whatsapp)}</span>
      </div>
      {r.reason && (
        <span className="badge neutral loop-recip-reason">{reasonLabel[r.reason] ?? r.reason}</span>
      )}
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
  const [editing, setEditing] = useState(false);
  const loading = preview === null && error === null;
  const willSend = (preview?.would_send ?? []) as LoopRecipient[];
  const skipped = (preview?.skipped ?? []) as LoopRecipient[];

  // prévia da mensagem: a do 1º elegível representa o balão (todas seguem o
  // mesmo molde, personalizado pelo tema da dor no backend).
  const sampleMsg = willSend.find((r) => r.mensagem)?.mensagem ?? "";
  const now = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date());

  return (
    <Modal title="Avisar quem pediu" onClose={onClose} labelledById="close-loop-title">
      <div className="modal-body loop-body">
        {/* topo: a melhoria entregue */}
        <div className="loop-head-card">
          <span className="loop-head-ico" aria-hidden>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          </span>
          <div className="loop-head-txt">
            <span className="loop-head-kicker">Melhoria entregue</span>
            <span className="loop-head-title">{imp.title}</span>
          </div>
        </div>

        {error && (
          <div className="flash err">
            {error}. O WhatsApp pode estar desconectado — confira em <b>Conexão</b> e tente de novo.
          </div>
        )}

        {loading && <div className="empty loop-empty">Montando a lista de quem pediu…</div>}

        {!loading && !error && (
          <>
            {/* meio: quem pediu (vai receber) */}
            <div className="loop-section">
              <div className="loop-section-head">
                <span className="act-label">Quem pediu</span>
                <span className="loop-section-count">
                  {fmtNum.format(willSend.length)}{" "}
                  {willSend.length === 1 ? "cliente" : "clientes"}
                </span>
              </div>
              {willSend.length === 0 ? (
                <p className="picker-empty">
                  Ninguém elegível agora (sem opt-in, sem WhatsApp ou avisado há pouco). Nada
                  será enviado.
                </p>
              ) : (
                <div className="loop-recip-list">
                  {willSend.map((r) => (
                    <SendRecipientRow key={r.contato_id} r={r} />
                  ))}
                </div>
              )}
              {skipped.length > 0 && (
                <details className="loop-skip">
                  <summary>
                    + {fmtNum.format(skipped.length)}{" "}
                    {skipped.length === 1 ? "cliente fora desta vez" : "clientes fora desta vez"}
                  </summary>
                  <div className="loop-recip-list">
                    {skipped.map((r) => (
                      <SkipRecipientRow key={r.contato_id} r={r} />
                    ))}
                  </div>
                </details>
              )}
            </div>

            {/* prévia da mensagem do WhatsApp */}
            {sampleMsg && (
              <div className="loop-section">
                <div className="loop-section-head">
                  <span className="act-label">Prévia da mensagem</span>
                  {preview?.theme && (
                    <span className="loop-section-count">tema: {preview.theme}</span>
                  )}
                </div>
                <div className="wa-preview">
                  <div className="wa-bubble">
                    <p className="wa-bubble-text">{sampleMsg}</p>
                    <span className="wa-bubble-time mono">{now}</span>
                  </div>
                </div>
                {editing && (
                  <p className="loop-edit-note">
                    A mensagem é escrita automaticamente, na voz da Escuta, e personalizada
                    pelo tema da dor. A edição manual por envio chega em breve.
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>

      <div className="modal-foot loop-foot">
        <button
          type="button"
          className="btn ghost loop-edit-btn"
          onClick={() => setEditing((v) => !v)}
          disabled={loading || sending || !sampleMsg}
          aria-pressed={editing}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
          Editar mensagem
        </button>
        <button
          type="button"
          className="btn btn-wa loop-send-btn"
          onClick={onConfirm}
          disabled={loading || sending || willSend.length === 0}
          title={willSend.length === 0 ? "Ninguém elegível para receber" : "Enviar de verdade pelo WhatsApp"}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m22 2-7 20-4-9-9-4Z" />
            <path d="M22 2 11 13" />
          </svg>
          {sending ? "Enviando…" : `Enviar para os ${willSend.length}`}
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
}: {
  cluster: FeedbackCluster;
  busy: boolean;
  onPull: () => void;
}) {
  const title = cluster.label ?? "Dor sem rótulo";
  const sent = sentimentBadge(cluster.dominant_sentiment);

  return (
    <div className="survey-item">
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
        <Button
          size="sm"
          className="imp-close-loop"
          onClick={onPull}
          disabled={busy}
          title="Criar uma melhoria a partir desta dor e vincular os feedbacks"
        >
          {busy ? "Puxando…" : `${EMOJI_PULL} Puxar para o roadmap`}
        </Button>
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
            <b>Mapeamento → Por significado</b>, ela aparece aqui para ser puxada.
          </p>
        </div>
      ) : (
        !error && (
          <div className="imp-list" style={{ margin: "0 -20px -18px" }}>
            {pains.map((c) => (
              <PendingPainRow
                key={c.id}
                cluster={c}
                busy={busyId === c.id}
                onPull={() => onPull(c)}
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

/** Placeholder de um card de melhoria dentro de uma coluna do Kanban. */
function KanbanCardSkeleton() {
  return (
    <div className="card board-card imp-card" aria-busy="true">
      <div className="sk-line w-90" style={{ marginTop: 2 }} />
      <div className="sk-line w-60" style={{ marginTop: 10, height: 22, borderRadius: 999 }} />
    </div>
  );
}

// ===== página ===============================================================

export default function MelhoriasPage() {
  const [items, setItems] = useState<ImprovementRoadmapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  // sucesso de "loop fechado" → celebração com ilustração (some no próximo flash/ação)
  const [loopDone, setLoopDone] = useState<string | null>(null);

  // id da melhoria com PATCH/notify em voo (trava os controles do card)
  const [busyId, setBusyId] = useState<string | null>(null);

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
      const rows = await api.get<ImprovementRoadmapItem[]>(`/api/improvements/roadmap`);
      setItems(rows);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

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

  // agrupa as melhorias por coluna do Kanban (mantém a ordem priorizada do backend)
  const byColumn = useMemo(() => {
    const map: Record<string, ImprovementRoadmapItem[]> = { ideias: [], fazendo: [], entregue: [] };
    for (const it of items) {
      const col = COLUMNS.find((c) => c.statuses.includes(it.status));
      if (col) map[col.key].push(it);
    }
    return map;
  }, [items]);

  // melhorias entregues ainda sem aviso → número-âncora "loops abertos"
  const openLoops = useMemo(
    () => byColumn.entregue.filter((it) => !notifiedAt(it)).length,
    [byColumn],
  );

  async function createImprovement(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFlash(null);
    setLoopDone(null);
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
    setLoopDone(null);
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
    setLoopDone(null);
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
      setFlash(null);
      setLoopDone(
        `${n} cliente${n === 1 ? "" : "s"} avisado${n === 1 ? "" : "s"} no WhatsApp. Loop fechado.`,
      );
      closeLoopModal();
      await load();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
      setSending(false);
    }
  }

  const hasItems = items.length > 0;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Melhorias</h1>
          <div className="page-sub">Você pediu, a gente fez.</div>
        </div>
        {!loading && !err && hasItems && (
          <span className="refresh-note">
            {fmtNum.format(items.length)} {items.length === 1 ? "melhoria" : "melhorias"} ·{" "}
            {fmtNum.format(totalDemand)} pedidos
            {openLoops > 0 && (
              <>
                {" · "}
                <b>{fmtNum.format(openLoops)}</b> {openLoops === 1 ? "loop aberto" : "loops abertos"}
              </>
            )}
          </span>
        )}
      </div>

      {loopDone && (
        <div className="loop-celebrate" role="status">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/illustrations/sucesso-loop-fechado.svg" alt="" width={92} height={80} />
          <div className="loop-celebrate-txt">
            <div className="loop-celebrate-title">{EMOJI_HEART} Você pediu, a gente fez.</div>
            <p className="loop-celebrate-sub">{loopDone}</p>
          </div>
          <button
            type="button"
            className="loop-celebrate-close"
            onClick={() => setLoopDone(null)}
            aria-label="Fechar aviso"
          >
            ✕
          </button>
        </div>
      )}

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="two-col imp-layout">
        {/* ---- esquerda: o Kanban "Você pediu, a gente fez" ---- */}
        <div>
          {err && (
            <div className="flash err">
              Não consegui carregar o roadmap ({err}). A API está rodando em{" "}
              <span className="mono">localhost:8000</span>?
            </div>
          )}

          {!err && loading && !hasItems ? (
            <div className="board-cols imp-board" aria-busy="true">
              {COLUMNS.map((col) => (
                <section className="board-col imp-col" key={col.key} aria-label={col.label}>
                  <div className="board-col-head">
                    <span className="board-col-name">{col.label}</span>
                  </div>
                  <div className="board-col-body">
                    <KanbanCardSkeleton />
                    <KanbanCardSkeleton />
                  </div>
                </section>
              ))}
            </div>
          ) : !err && !hasItems ? (
            <div className="card">
              <div className="empty">
                <div className="empty-illu-scene">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/illustrations/empty-melhorias.svg" alt="" width={200} height={150} />
                </div>
                <div className="empty-title">Nenhuma melhoria ainda</div>
                <p className="empty-sub">
                  Vire uma dor recorrente em melhoria e feche o loop. Use{" "}
                  <b>Puxar dos temas</b> ao lado, ou crie uma na mão.
                </p>
              </div>
            </div>
          ) : (
            !err && (
              <Reveal>
                <div className="board-cols imp-board">
                  {COLUMNS.map((col) => (
                    <KanbanColumn
                      key={col.key}
                      col={col}
                      items={byColumn[col.key] ?? []}
                      busyId={busyId}
                      onChangeStage={changeStage}
                      onCloseLoop={openCloseLoop}
                    />
                  ))}
                </div>
              </Reveal>
            )
          )}
        </div>

        {/* ---- direita: puxar dos temas + criar melhoria ---- */}
        <div className="imp-side">
          <Reveal>
            <PullFromThemes
              pains={pains}
              loading={painsLoading}
              error={painsErr}
              busyId={pullingId}
              onPull={pullFromCluster}
            />
          </Reveal>

          <Reveal className="card" style={{ padding: "18px 20px" }} delay={0.05}>
            <h2 className="section-title">Nova melhoria</h2>
          <p className="section-sub">
            Registre algo que você vai construir. Vincule a dores depois pela aba Mapeamento.
          </p>
          <form onSubmit={createImprovement}>
            <div className="field">
              <label>Título</label>
              <Input
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
                <Input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
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
            <Button type="submit" disabled={saving || !title.trim()}>
              {saving ? "Criando…" : "Criar melhoria"}
            </Button>
          </form>
          </Reveal>
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
