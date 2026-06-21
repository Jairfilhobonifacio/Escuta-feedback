"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import {
  ListChecks,
  MoreHorizontal,
  Pencil,
  Trash2,
  Check,
  CalendarClock,
  CalendarPlus,
  CalendarX,
} from "lucide-react";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import ConfirmDialog from "@/components/ConfirmDialog";
import AbordarModal, { waIcon } from "@/components/AbordarModal";
import { Stagger, StaggerItem } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { feedbackText, maskPhone } from "@/lib/format";
import {
  api,
  campanha as campanhaApi,
  config as configApi,
  feedbacks as feedbacksApi,
  type Cliente,
  type ConfigItem,
  type EstadoAssinatura,
  type Feedback,
  type FeedbackCounts,
  type FeedbackInput,
  type FeedbackPatch,
  type FeedbackStatus,
  type FeedbacksResponse,
  type NpsBucket,
  type TemWhatsappFiltro,
} from "@/lib/api";

const PAGE_SIZE = 25;

/** Estados de assinatura oferecidos no filtro "por tipo de cliente" (partner.subscription.state). */
const ESTADO_OPTIONS: { value: EstadoAssinatura; label: string }[] = [
  { value: "active_paying", label: "Pagando (ativo)" },
  { value: "past_due", label: "Em atraso" },
  { value: "paid_without_access", label: "Pago sem acesso" },
  { value: "complimentary", label: "Cortesia" },
  { value: "cancelled", label: "Cancelado" },
];

/** Perfis de feedback (partner.profile) — taxonomia estável da segmentação Bizzu. */
const PERFIL_OPTIONS: { value: string; label: string }[] = [
  { value: "embaixador", label: "Embaixador" },
  { value: "ativo_promotor", label: "Ativo promotor" },
  { value: "ativo_passivo", label: "Ativo passivo" },
  { value: "ativo_em_risco", label: "Ativo em risco" },
  { value: "ativo_recente", label: "Ativo recente" },
  { value: "ativo_silencioso", label: "Ativo silencioso" },
  { value: "ativo_fiel", label: "Ativo fiel" },
  { value: "cortesia", label: "Cortesia" },
  { value: "vai_expirar", label: "Vai expirar" },
  { value: "churn_pos_uso", label: "Churn pós-uso" },
  { value: "churn_rapido", label: "Churn rápido" },
  { value: "churn_involuntario", label: "Churn involuntário" },
  { value: "churn_outro", label: "Churn outro" },
  { value: "indefinido", label: "Indefinido" },
];

/** Selos de campanha win-back sugeridos no controle "+ selo" do card. */
const SELOS_CAMPANHA = ["contatado", "respondeu", "cortesia", "reativou"];

/** FALLBACK dos status (usado se GET /api/config falhar). Espelha os defaults de
    ACOMPANHAMENTO do backend (key/label/cor); o conjunto efetivo — defaults + custom
    da org — vem de config.get() e é passado por props. */
const STATUS_TABS_FALLBACK: ConfigItem[] = [
  { key: "a_abordar", label: "A abordar", cor: "#6366f1" },
  { key: "aguardando_retorno", label: "Aguardando retorno", cor: "#f59e0b" },
  { key: "em_acompanhamento", label: "Em acompanhamento", cor: "#3b82f6" },
  { key: "resolvido", label: "Resolvido", cor: "#10b981" },
  { key: "sem_retorno", label: "Sem retorno", cor: "#94a3b8" },
  { key: "descartado", label: "Descartado", cor: "#64748b" },
];

const EMPTY_COUNTS: FeedbackCounts = {
  a_abordar: 0, aguardando_retorno: 0, em_acompanhamento: 0,
  resolvido: 0, sem_retorno: 0, descartado: 0,
};

/** Labels fixos de fallback p/ tipos legados/sem custom (badge e textos). */
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

/** FALLBACK dos tipos oferecidos ao criar/editar/filtrar (se config.get falhar).
    O conjunto efetivo vem de config.get() e é passado por props. */
const TYPE_OPTIONS_FALLBACK: ConfigItem[] = [
  { key: "nps", label: "NPS" },
  { key: "churn", label: "Cancelamento" },
  { key: "elogio", label: "Elogio" },
  { key: "sugestao", label: "Sugestão" },
  { key: "bug", label: "Bug" },
  { key: "outro", label: "Outro" },
];

/** Constrói {key: label} a partir de uma lista de vocabulário (para badges/labels). */
function labelMap(items: ConfigItem[]): Record<string, string> {
  const m: Record<string, string> = {};
  for (const it of items) m[it.key] = it.label;
  return m;
}

/** Garante que o valor ATUAL (ex.: um tipo legado fora do vocabulário) apareça no
    select, para a edição não "perder" o valor selecionado. */
function withCurrent(items: ConfigItem[], current: string | null | undefined): ConfigItem[] {
  if (!current || items.some((it) => it.key === current)) return items;
  return [...items, { key: current, label: TYPE_LABEL[current] ?? current }];
}

const SOURCE_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  bizzu_app: "app Bizzu",
  bizzu_billing: "cobrança",
  bizzu_support: "suporte",
  manual: "manual",
};

const SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "manual", label: "Manual" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "bizzu_app", label: "App Bizzu" },
  { value: "bizzu_billing", label: "Cobrança" },
  { value: "bizzu_support", label: "Suporte" },
];

const SENT_META: Record<string, { cls: string; label: string; color: string }> = {
  positivo: { cls: "s-pos", label: "positivo", color: "var(--promoter)" },
  neutro: { cls: "s-neu", label: "neutro", color: "var(--passive)" },
  negativo: { cls: "s-neg", label: "negativo", color: "var(--detractor)" },
};

function typeBadge(type: string, typeLabels?: Record<string, string>) {
  const label = typeLabels?.[type] ?? TYPE_LABEL[type] ?? type;
  const cls = type === "churn" || type === "exit" ? "t-exit" : "t-nps";
  return <span className={`badge type ${cls}`}>{label}</span>;
}

function sentimentBadge(s: string | null) {
  if (!s) return null;
  const m = SENT_META[s];
  if (!m) return null;
  return <span className={`badge sent ${m.cls}`}>{m.label}</span>;
}

/** Ponto de sentimento (cor) que abre o cabeçalho do card — o realce visual nº 1
   "de relance". Sem sentimento ainda, fica um ponto neutro discreto. */
function SentimentDot({ s }: { s: string | null }) {
  const color = (s && SENT_META[s]?.color) || "var(--charcoal-2)";
  const label = (s && SENT_META[s]?.label) || "sem sentimento";
  return (
    <span
      className="fb-sent-dot"
      style={{ background: color }}
      title={`Sentimento: ${label}`}
      aria-label={`Sentimento: ${label}`}
    />
  );
}

/** Cor default da pílula de status quando o config não traz `cor` (ou status legado). */
const STATUS_DOT_FALLBACK = "#94a3b8";

/** Badge de STATUS de acompanhamento tingido pela COR do status (vinda do /api/config).
    Mostra a etapa "de relance" no card. Status legado/fora do vocabulário ainda
    renderiza: cai no label cru da key e numa cor neutra de fallback. */
function statusBadge(status: string, statusOptions: ConfigItem[]) {
  if (!status) return null;
  const it = statusOptions.find((s) => s.key === status);
  const cor = it?.cor || STATUS_DOT_FALLBACK;
  const label = it?.label ?? status;
  return (
    <span
      className="badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        color: cor,
        background: `color-mix(in srgb, ${cor} 12%, transparent)`,
        borderColor: `color-mix(in srgb, ${cor} 32%, transparent)`,
      }}
      title={`Status: ${label}`}
    >
      <span
        aria-hidden
        style={{ width: 8, height: 8, borderRadius: "50%", background: cor, flexShrink: 0 }}
      />
      {label}
    </span>
  );
}

function themeChips(themes: string[] | null) {
  if (!themes || themes.length === 0) return null;
  return (
    <div className="theme-chips">
      {themes.map((t, i) => (
        <span key={`${t}-${i}`} className="chip">{t}</span>
      ))}
    </div>
  );
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

/** Deriva o bucket de NPS a partir do score (espelha o que o backend devolve). */
function bucketFor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "none";
  if (score <= 6) return "detractor";
  if (score <= 8) return "passive";
  return "promoter";
}

/** "nps, churn" -> ["nps","churn"]. Vazio -> null (campo limpo). */
function parseThemes(raw: string): string[] | null {
  const arr = raw.split(",").map((t) => t.trim()).filter(Boolean);
  return arr.length ? arr : null;
}

// ===== Follow-up ("Reabordar em...") ========================================
// Agenda quando reabordar um feedback (`follow_up_at`, ISO/UTC). Vencido =
// follow_up_at <= agora → DESTACADO em vermelho. PATCH /api/feedbacks/{id}
// {follow_up_at}; null limpa.

/** Só data (DD/MM) do follow-up, no fuso local. */
function fmtFollowUp(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** ISO (UTC) daqui a N dias inteiros (à meia-noite local do dia-alvo). */
function isoEmDias(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  d.setHours(9, 0, 0, 0); // 9h local — horário comercial, não meia-noite.
  return d.toISOString();
}

/** Info derivada do follow-up de um feedback: tem? está vencido? rótulo curto. */
function followUpInfo(iso: string | null | undefined): {
  agendado: boolean;
  vencido: boolean;
  label: string;
} {
  if (!iso) return { agendado: false, vencido: false, label: "" };
  const t = new Date(iso).getTime();
  const vencido = t <= Date.now();
  return { agendado: true, vencido, label: fmtFollowUp(iso) };
}

/** datetime-local (sem 'Z') a partir de um Date, no fuso local. */
function toDateInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Pílula que mostra "reabordar em DD/MM" — vermelha quando vencida. Clicável
    para abrir o menu (passada como trigger). */
function FollowUpPill({
  iso,
  onClick,
}: {
  iso: string | null | undefined;
  onClick?: () => void;
}) {
  const info = followUpInfo(iso);
  if (!info.agendado) return null;
  const cls = info.vencido ? "fb-followup-pill is-overdue" : "fb-followup-pill";
  const title = info.vencido
    ? `Follow-up vencido (era ${info.label}) — reabordar agora`
    : `Reabordar em ${info.label}`;
  return (
    <button type="button" className={cls} onClick={onClick} title={title}>
      <CalendarClock size={12} aria-hidden />
      {info.vencido ? `venceu ${info.label}` : `reabordar ${info.label}`}
    </button>
  );
}

/** Menu "Reabordar em…" (3 dias / 7 dias / escolher data / limpar). Seta
    follow_up_at via callback. Fecha no clique fora e no Esc. */
function ReabordarMenu({
  current,
  onSchedule,
  onClear,
  busy,
  triggerClassName,
  triggerLabel,
}: {
  current: string | null | undefined;
  onSchedule: (iso: string) => void;
  onClear: () => void;
  busy?: boolean;
  triggerClassName?: string;
  triggerLabel?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [dateVal, setDateVal] = useState(() => toDateInputValue(new Date()));
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function close() {
    setOpen(false);
    setPicking(false);
  }

  function agendarDias(dias: number) {
    onSchedule(isoEmDias(dias));
    close();
  }

  function confirmarData() {
    if (!dateVal) return;
    // datetime-local sem fuso → meia-feira local às 9h, depois UTC.
    const d = new Date(`${dateVal}T09:00`);
    onSchedule(d.toISOString());
    close();
  }

  return (
    <div className="fb-reabordar" ref={boxRef}>
      <button
        type="button"
        className={triggerClassName ?? "fb-reabordar-btn"}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        title="Agendar quando reabordar este feedback"
      >
        <CalendarClock size={14} aria-hidden />
        {triggerLabel ?? "Reabordar em…"}
      </button>
      {open && (
        <div className="fb-reabordar-pop" role="menu">
          {!picking ? (
            <>
              <button type="button" role="menuitem" className="fb-reabordar-item" onClick={() => agendarDias(3)}>
                <CalendarPlus size={14} aria-hidden /> Em 3 dias
              </button>
              <button type="button" role="menuitem" className="fb-reabordar-item" onClick={() => agendarDias(7)}>
                <CalendarPlus size={14} aria-hidden /> Em 7 dias
              </button>
              <button type="button" role="menuitem" className="fb-reabordar-item" onClick={() => setPicking(true)}>
                <CalendarClock size={14} aria-hidden /> Escolher data…
              </button>
              {current && (
                <button
                  type="button"
                  role="menuitem"
                  className="fb-reabordar-item danger"
                  onClick={() => {
                    onClear();
                    close();
                  }}
                >
                  <CalendarX size={14} aria-hidden /> Limpar follow-up
                </button>
              )}
            </>
          ) : (
            <div className="fb-reabordar-pick">
              <label className="fb-reabordar-pick-lbl">Reabordar em</label>
              <input
                type="date"
                value={dateVal}
                min={toDateInputValue(new Date())}
                onChange={(e) => setDateVal(e.target.value)}
                className="fb-reabordar-date"
              />
              <div className="fb-reabordar-pick-actions">
                <button type="button" className="btn ghost sm" onClick={() => setPicking(false)}>
                  Voltar
                </button>
                <button type="button" className="btn sm" onClick={confirmarData} disabled={!dateVal}>
                  Agendar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ===== Modal de edição (PATCH de text/type/score/sentiment/themes) ==========

function EditFeedbackModal({
  feedback,
  onCancel,
  onSaved,
  typeOptions,
}: {
  feedback: Feedback;
  onCancel: () => void;
  onSaved: (updated: Feedback) => void;
  typeOptions: ConfigItem[];
}) {
  const titleId = useId();
  const [type, setType] = useState(feedback.type);
  const [score, setScore] = useState(
    feedback.score === null || feedback.score === undefined ? "" : String(feedback.score),
  );
  const [text, setText] = useState(feedback.text ?? "");
  const [sentiment, setSentiment] = useState(feedback.sentiment ?? "");
  const [themes, setThemes] = useState((feedback.themes ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isNps = type === "nps";

  function validate(): string | null {
    if (isNps && score !== "") {
      const n = Number(score);
      if (!Number.isInteger(n) || n < 0 || n > 10) {
        return "A nota (NPS) precisa ser um inteiro de 0 a 10.";
      }
    }
    return null;
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) { setError(v); return; }
    setSaving(true);
    setError(null);

    const body: FeedbackPatch = {
      type,
      text: text.trim() || null,
      sentiment: sentiment || null,
      themes: parseThemes(themes),
      // score só faz sentido para NPS; fora disso, limpa.
      score: isNps && score !== "" ? Number(score) : null,
    };

    try {
      const updated = await api.patch<Feedback>(`/api/feedbacks/${feedback.id}`, body);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title="Editar feedback" onClose={onCancel} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="form-row-2">
            <div className="field">
              <label htmlFor={`${titleId}-type`}>Tipo</label>
              <select
                id={`${titleId}-type`}
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                {withCurrent(typeOptions, feedback.type).map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
            </div>
            {isNps && (
              <div className="field">
                <label htmlFor={`${titleId}-score`}>Nota (0–10)</label>
                <input
                  id={`${titleId}-score`}
                  type="number"
                  min={0}
                  max={10}
                  inputMode="numeric"
                  value={score}
                  onChange={(e) => setScore(e.target.value)}
                  placeholder="ex.: 9"
                />
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-text`}>Texto</label>
            <textarea
              id={`${titleId}-text`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="O que o cliente disse…"
            />
          </div>

          <div className="form-row-2">
            <div className="field">
              <label htmlFor={`${titleId}-sent`}>Sentimento</label>
              <select
                id={`${titleId}-sent`}
                value={sentiment}
                onChange={(e) => setSentiment(e.target.value)}
              >
                <option value="">— não definido —</option>
                <option value="positivo">Positivo</option>
                <option value="neutro">Neutro</option>
                <option value="negativo">Negativo</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${titleId}-themes`}>Temas</label>
              <input
                id={`${titleId}-themes`}
                value={themes}
                onChange={(e) => setThemes(e.target.value)}
                placeholder="preço, suporte, app… (separe por vírgula)"
              />
            </div>
          </div>

          {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
        </div>
        <div className="modal-foot">
          <Button variant="ghost" type="button" onClick={onCancel} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Salvando…" : "Salvar alterações"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ===== Autocomplete de cliente (criar feedback) =============================

function ClientePicker({
  onPick,
  picked,
  onClear,
}: {
  onPick: (c: Cliente) => void;
  picked: Cliente | null;
  onClear: () => void;
}) {
  const fieldId = useId();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Cliente[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (picked || q.trim().length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const raw = await api.get<Cliente[] | { items: Cliente[] }>(
          `/api/clientes?search=${encodeURIComponent(q.trim())}`,
        );
        if (cancelled) return;
        setResults((Array.isArray(raw) ? raw : raw.items ?? []).slice(0, 8));
        setOpen(true);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 280);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, picked]);

  if (picked) {
    return (
      <div className="picked-cliente">
        <div className="picked-info">
          <span className="picked-name">{picked.nome || "sem nome"}</span>
          <span className="mono dim">{picked.whatsapp}</span>
        </div>
        <button type="button" className="btn ghost sm" onClick={onClear}>
          Trocar
        </button>
      </div>
    );
  }

  return (
    <div className="cliente-picker">
      <label className="search picker-search">
        <span className="ico">🔍</span>
        <input
          id={fieldId}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          placeholder="Busque pelo nome ou WhatsApp do cliente…"
          autoComplete="off"
        />
      </label>
      {open && q.trim().length >= 2 && (
        <div className="picker-results" role="listbox">
          {loading && <div className="picker-empty">Buscando…</div>}
          {!loading && results.length === 0 && (
            <div className="picker-empty">
              Nenhum cliente. Use os campos abaixo para um contato fora da base.
            </div>
          )}
          {results.map((c) => (
            <button
              type="button"
              key={c.id}
              className="picker-row"
              role="option"
              aria-selected={false}
              onClick={() => { onPick(c); setOpen(false); setQ(""); }}
            >
              <span className="picker-row-name">{c.nome || "sem nome"}</span>
              <span className="mono dim">{c.whatsapp}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ===== Modal de criação (POST) ==============================================

function CreateFeedbackModal({
  onCancel,
  onCreated,
  typeOptions,
}: {
  onCancel: () => void;
  onCreated: (created: Feedback) => void;
  typeOptions: ConfigItem[];
}) {
  const titleId = useId();
  const [cliente, setCliente] = useState<Cliente | null>(null);
  // contato fora da base (quando não há cliente selecionado)
  const [novoNome, setNovoNome] = useState("");
  const [novoWhats, setNovoWhats] = useState("");

  const [source, setSource] = useState("manual");
  const [type, setType] = useState("nps");
  const [score, setScore] = useState("");
  const [text, setText] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [themes, setThemes] = useState("");
  const [abordado, setAbordado] = useState(false);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isNps = type === "nps";

  function validate(): string | null {
    if (!cliente && !novoWhats.trim()) {
      return "Selecione um cliente ou informe o WhatsApp de um contato fora da base.";
    }
    if (isNps && score !== "") {
      const n = Number(score);
      if (!Number.isInteger(n) || n < 0 || n > 10) {
        return "A nota (NPS) precisa ser um inteiro de 0 a 10.";
      }
    }
    return null;
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) { setError(v); return; }
    setSaving(true);
    setError(null);

    const body: FeedbackInput = {
      source,
      type,
      text: text.trim() || null,
      sentiment: sentiment || null,
      themes: parseThemes(themes),
      score: isNps && score !== "" ? Number(score) : null,
      abordado,
      ...(cliente
        ? { contato_id: cliente.id }
        : { contato_whatsapp: novoWhats.trim(), contato_nome: novoNome.trim() || undefined }),
    };

    try {
      const created = await api.post<Feedback>("/api/feedbacks", body);
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title="Novo feedback" onClose={onCancel} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="field">
            <label>Cliente</label>
            <ClientePicker
              picked={cliente}
              onPick={setCliente}
              onClear={() => setCliente(null)}
            />
          </div>

          {!cliente && (
            <div className="off-base">
              <div className="off-base-hint">
                Contato fora da base (opcional se já escolheu um cliente acima):
              </div>
              <div className="form-row-2">
                <div className="field">
                  <label htmlFor={`${titleId}-nwhats`}>WhatsApp</label>
                  <input
                    id={`${titleId}-nwhats`}
                    value={novoWhats}
                    onChange={(e) => setNovoWhats(e.target.value)}
                    placeholder="ex.: 5577999450083"
                    inputMode="tel"
                  />
                </div>
                <div className="field">
                  <label htmlFor={`${titleId}-nnome`}>Nome</label>
                  <input
                    id={`${titleId}-nnome`}
                    value={novoNome}
                    onChange={(e) => setNovoNome(e.target.value)}
                    placeholder="ex.: Maria Souza"
                  />
                </div>
              </div>
            </div>
          )}

          <div className="form-row-2">
            <div className="field">
              <label htmlFor={`${titleId}-type`}>Tipo</label>
              <select
                id={`${titleId}-type`}
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                {withCurrent(typeOptions, type).map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
            </div>
            {isNps && (
              <div className="field">
                <label htmlFor={`${titleId}-score`}>Nota (0–10)</label>
                <input
                  id={`${titleId}-score`}
                  type="number"
                  min={0}
                  max={10}
                  inputMode="numeric"
                  value={score}
                  onChange={(e) => setScore(e.target.value)}
                  placeholder="ex.: 9"
                />
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-text`}>Texto</label>
            <textarea
              id={`${titleId}-text`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="O que o cliente disse…"
            />
          </div>

          <div className="form-row-3">
            <div className="field">
              <label htmlFor={`${titleId}-source`}>Origem</label>
              <select
                id={`${titleId}-source`}
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                {SOURCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${titleId}-sent`}>Sentimento</label>
              <select
                id={`${titleId}-sent`}
                value={sentiment}
                onChange={(e) => setSentiment(e.target.value)}
              >
                <option value="">— não definido —</option>
                <option value="positivo">Positivo</option>
                <option value="neutro">Neutro</option>
                <option value="negativo">Negativo</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${titleId}-themes`}>Temas</label>
              <input
                id={`${titleId}-themes`}
                value={themes}
                onChange={(e) => setThemes(e.target.value)}
                placeholder="preço, suporte…"
              />
            </div>
          </div>

          <label className="check-row">
            <input
              type="checkbox"
              checked={abordado}
              onChange={(e) => setAbordado(e.target.checked)}
            />
            <span>Já abordei esse cliente sobre o feedback</span>
          </label>

          {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
        </div>
        <div className="modal-foot">
          <Button variant="ghost" type="button" onClick={onCancel} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Criando…" : "Criar feedback"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ===== Selos de campanha do contato (chips + aplicar direto no card) =========

function SeloControl({
  fb,
  onSelosChanged,
}: {
  fb: Feedback;
  onSelosChanged: (selos: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Sem contato não há onde aplicar selo.
  if (!fb.contato_id) return null;
  const contatoId = fb.contato_id;
  // A API pode não devolver `selos` (feedbacks antigos / antes do backend novo) — defensivo.
  const selosFb = fb.selos ?? [];

  const disponiveis = SELOS_CAMPANHA.filter((s) => !selosFb.includes(s));

  async function aplicar(nome: string) {
    if (busy) return;
    setBusy(true);
    try {
      const out = await campanhaApi.applySelo(contatoId, { nome });
      onSelosChanged(out.selos);
      setOpen(false);
    } catch {
      /* erro silencioso — o operador tenta de novo */
    } finally {
      setBusy(false);
    }
  }

  async function remover(nome: string) {
    if (busy) return;
    setBusy(true);
    try {
      const out = await campanhaApi.removeSeloFromContact(contatoId, nome);
      // O DELETE responde { selos }; tipamos como unknown no helper, então normalizamos.
      const selos = (out as { selos?: string[] })?.selos;
      onSelosChanged(Array.isArray(selos) ? selos : selosFb.filter((s) => s !== nome));
    } catch {
      /* erro silencioso */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fb-selos" ref={boxRef}>
      {selosFb.map((nome) => (
        <span key={nome} className="selo-chip">
          <span className="selo-dot" style={{ background: "var(--indigo)" }} />
          {nome}
          <button
            type="button"
            className="selo-x"
            onClick={() => remover(nome)}
            aria-label={`Remover selo ${nome}`}
            disabled={busy}
          >
            {"\u{2715}"}
          </button>
        </span>
      ))}
      <button
        type="button"
        className="selo-add"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Marcar selo de campanha"
        disabled={busy}
      >
        {"\u{FF0B}"} selo
      </button>
      {open && (
        <div className="selo-pop fb-selo-pop">
          {disponiveis.length === 0 ? (
            <div className="picker-empty">Todos os selos de campanha já aplicados.</div>
          ) : (
            <div className="selo-pop-list">
              {disponiveis.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="selo-pop-item"
                  onClick={() => aplicar(s)}
                  disabled={busy}
                >
                  <span className="selo-dot" style={{ background: "var(--indigo)" }} />
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ===== Menu "⋯" do card (ações secundárias agrupadas) =======================

interface KebabItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  /** Marca visual de estado ligado (ex.: "abordado" já ativo). */
  active?: boolean;
}

/** Menu discreto que recolhe as ações secundárias (tarefa, abordado, editar,
   excluir) atrás de um único botão "⋯" — tira 4 botões empilhados do card.
   Fecha no clique fora e no Esc; foco volta ao gatilho. */
function KebabMenu({ items, label }: { items: KebabItem[]; label: string }) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="fb-kebab" ref={boxRef}>
      <button
        type="button"
        className="fb-kebab-btn"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
      >
        <MoreHorizontal size={18} aria-hidden />
      </button>
      {open && (
        <div className="fb-kebab-pop" role="menu">
          {items.map((it) => (
            <button
              key={it.key}
              type="button"
              role="menuitem"
              className={`fb-kebab-item${it.danger ? " danger" : ""}${it.active ? " active" : ""}`}
              onClick={() => {
                it.onClick();
                setOpen(false);
              }}
              disabled={it.disabled}
            >
              <span className="fb-kebab-ico" aria-hidden>{it.icon}</span>
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ===== Card de um feedback ==================================================

function FeedbackCard({
  fb,
  onPatched,
  onEdit,
  onDelete,
  onAbordar,
  onSelosChanged,
  statusOptions,
  typeLabels,
}: {
  fb: Feedback;
  onPatched: (updated: Feedback, previousStatus: FeedbackStatus) => void;
  onEdit: (fb: Feedback) => void;
  onDelete: (fb: Feedback) => void;
  onAbordar: (fb: Feedback) => void;
  onSelosChanged: (id: string, selos: string[]) => void;
  statusOptions: ConfigItem[];
  typeLabels: Record<string, string>;
}) {
  // Corrige um typo gravado em dados antigos ("repsposta") só na exibição/edição.
  const fixNote = (s: string | null | undefined) =>
    (s ?? "").replace(/repsposta/gi, "resposta");
  const [note, setNote] = useState(fixNote(fb.action_note));
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [abordadoSaving, setAbordadoSaving] = useState(false);
  // Criar tarefa direto do card (espelha o /board): ocupado + flash transitório.
  const [tarefaSaving, setTarefaSaving] = useState(false);
  const [tarefaFlash, setTarefaFlash] = useState<{ ok: boolean; msg: string } | null>(null);

  // O flash da tarefa some sozinho (mesma cadência do "✓ salvo").
  useEffect(() => {
    if (!tarefaFlash) return;
    const t = setTimeout(() => setTarefaFlash(null), 2200);
    return () => clearTimeout(t);
  }, [tarefaFlash]);

  // Mantém o input de nota em sincronia quando o card é reconciliado de fora
  // (ex.: edição via modal) sem pisar no que o usuário está digitando.
  useEffect(() => {
    if (!saving) setNote(fixNote(fb.action_note));
    // fixNote é estável (definido no corpo); depende só de fb.action_note/saving.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fb.action_note, saving]);

  async function patch(body: FeedbackPatch) {
    const previousStatus = fb.action_status;
    setSaving(true);
    setError(null);
    const optimistic: Feedback = { ...fb, ...body };
    onPatched(optimistic, previousStatus);
    try {
      const updated = await api.patch<Feedback>(`/api/feedbacks/${fb.id}`, body);
      onPatched(updated, previousStatus);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 1500);
    } catch (e) {
      onPatched(fb, previousStatus);
      setNote(fb.action_note ?? "");
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function toggleAbordado() {
    const next = !fb.abordado;
    const previousStatus = fb.action_status;
    setAbordadoSaving(true);
    setError(null);
    // Otimista: já mostra o novo estado (incl. carimbo local de data).
    const optimistic: Feedback = {
      ...fb,
      abordado: next,
      abordado_em: next ? new Date().toISOString() : null,
    };
    onPatched(optimistic, previousStatus);
    try {
      const updated = await api.patch<Feedback>(`/api/feedbacks/${fb.id}`, { abordado: next });
      onPatched(updated, previousStatus);
    } catch (e) {
      onPatched(fb, previousStatus); // reverte
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAbordadoSaving(false);
    }
  }

  async function criarTarefa() {
    // Guarda de contato: sem contato não há a quem vincular a tarefa.
    if (!fb.contato_id) {
      setTarefaFlash({ ok: false, msg: "Sem contato — não dá para criar tarefa." });
      return;
    }
    setTarefaSaving(true);
    setTarefaFlash(null);
    // Título derivado, igual ao /board: trecho do texto (60 chars) ou o tipo.
    const trecho = (fb.text ?? "").trim().slice(0, 60);
    try {
      await feedbacksApi.criarTarefa({
        contact_id: fb.contato_id,
        feedback_id: fb.id,
        title: `Abordar feedback: ${trecho || fb.type}`,
      });
      setTarefaFlash({ ok: true, msg: "Tarefa criada." });
    } catch (e) {
      setTarefaFlash({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setTarefaSaving(false);
    }
  }

  function onStatusChange(e: React.ChangeEvent<HTMLSelectElement>) {
    patch({ action_status: e.target.value as FeedbackStatus });
  }

  function commitNote() {
    const trimmed = note.trim();
    if (trimmed === (fb.action_note ?? "").trim()) return;
    patch({ action_note: trimmed });
  }

  // Follow-up ("reabordar em…"): grava follow_up_at via PATCH (null limpa).
  function agendarFollowUp(iso: string) {
    patch({ follow_up_at: iso });
  }
  function limparFollowUp() {
    patch({ follow_up_at: null });
  }

  const isChurn = fb.type === "churn" || fb.type === "exit";
  const followUp = followUpInfo(fb.follow_up_at);

  // Ações secundárias recolhidas no menu "⋯": tirar tarefa, alternar abordado,
  // editar e excluir — saem da frente para o card respirar.
  const kebabItems: KebabItem[] = [
    {
      key: "tarefa",
      label: tarefaSaving ? "Criando tarefa…" : "Criar tarefa",
      icon: <ListChecks size={15} aria-hidden />,
      onClick: criarTarefa,
      disabled: tarefaSaving || !fb.contato_id,
    },
    {
      key: "abordado",
      label: fb.abordado ? "Desmarcar abordado" : "Marcar como abordado",
      icon: <Check size={15} aria-hidden />,
      onClick: toggleAbordado,
      disabled: abordadoSaving,
      active: fb.abordado,
    },
    {
      key: "editar",
      label: "Editar feedback",
      icon: <Pencil size={15} aria-hidden />,
      onClick: () => onEdit(fb),
    },
    {
      key: "excluir",
      label: "Excluir feedback",
      icon: <Trash2 size={15} aria-hidden />,
      onClick: () => onDelete(fb),
      danger: true,
    },
  ];

  return (
    <div className={`card fb-card ${fb.abordado ? "is-abordado" : ""}`}>
      {/* Cabeçalho enxuto: quem + sentimento (cor) + nota, com a data à direita.
         O resto da metainformação desce para a faixa de chips, mais discreta. */}
      <div className="fb-top">
        <SentimentDot s={fb.sentiment} />
        <Avatar name={fb.contato_nome} seed={fb.contato_id ?? fb.contato_whatsapp} size={28} />
        {fb.contato_id ? (
          <Link href={`/contatos/${fb.contato_id}`} className="fb-who">
            {fb.contato_nome || "sem nome"}
          </Link>
        ) : (
          <span className="fb-who">{fb.contato_nome || "sem contato"}</span>
        )}
        {fb.score !== null && fb.score !== undefined && (
          <span className={`score-pill sm ${fb.nps_bucket ?? bucketFor(fb.score)}`} title={`Nota ${fb.score}`}>
            {fb.score}
          </span>
        )}
        {fb.urgencia >= 70 && (
          <span className="badge detractor fb-chip-sm" title={`Urgência ${fb.urgencia}/100`}>urgente</span>
        )}
        {/* Estado "abordado" de 1ª classe: chip verde VISÍVEL no cabeçalho quando
           já abordamos o cliente — clicável para desmarcar (mesmo toggle otimista). */}
        {fb.abordado && (
          <button
            type="button"
            className="fb-abordado-chip"
            onClick={toggleAbordado}
            disabled={abordadoSaving}
            title="Abordado — clique para desmarcar"
            aria-pressed="true"
          >
            <Check size={13} aria-hidden /> Abordado
          </button>
        )}
        <span className="fb-when">{fmtDate(fb.occurred_em ?? fb.created_em)}</span>
      </div>

      {/* O TEXTO é o herói: maior, com respiro. */}
      {fb.text ? (
        <div className="fb-text">“{feedbackText(fb.text)}”</div>
      ) : (
        <div className="fb-text empty-text">sem texto — só a nota</div>
      )}

      {/* Faixa de metainformação discreta: telefone, tipo/origem, churn, temas,
         selos. Tudo secundário — não compete com o texto. */}
      <div className="fb-meta">
        <span className="mono fb-phone" title="Telefone mascarado — abra a ficha do contato para o número completo">
          {maskPhone(fb.contato_whatsapp)}
        </span>
        <span className="fb-meta-sep" aria-hidden>·</span>
        <span className="fb-meta-src">{(typeLabels[fb.type] ?? TYPE_LABEL[fb.type] ?? fb.type)} · via {SOURCE_LABEL[fb.source] ?? fb.source}</span>
        {isChurn && <span className="badge detractor fb-chip-sm">Churn</span>}
        {followUp.agendado && <FollowUpPill iso={fb.follow_up_at} />}
        {themeChips(fb.themes)}
        {fb.editado_por && (
          <span
            className="fb-edited"
            title={`Editado manualmente${fb.editado_em ? ` em ${fmtDate(fb.editado_em)}` : ""}`}
          >
            editado por {fb.editado_por}
          </span>
        )}
        <SeloControl fb={fb} onSelosChanged={(selos) => onSelosChanged(fb.id, selos)} />
      </div>

      {/* Rodapé de ação enxuto: STATUS (colorido) + WhatsApp (ação primária) +
         menu "⋯" com o resto. A nota fica numa 2ª linha sutil. */}
      <div className="fb-actions">
        <span className="act-label">Status</span>
        <select className="fb-status-select" value={fb.action_status} onChange={onStatusChange} disabled={saving}>
          {withCurrent(statusOptions, fb.action_status).map((s) => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>

        {saving && <span className="dim" style={{ fontSize: 12 }}>salvando…</span>}
        {justSaved && !saving && <span className="act-saved">✓ salvo</span>}
        {error && <span className="badge detractor" title={error}>erro ao salvar</span>}
        {tarefaFlash && (
          tarefaFlash.ok ? (
            <span className="act-saved">✓ {tarefaFlash.msg}</span>
          ) : (
            <span className="badge detractor" title={tarefaFlash.msg}>{tarefaFlash.msg}</span>
          )
        )}

        <div className="fb-card-tools">
          {/* Quando ainda NÃO abordado: botão discreto mas visível no rodapé para
             marcar — sem precisar abrir o "⋯" (estado que o dono monitora de perto). */}
          {!fb.abordado && (
            <button
              type="button"
              className="fb-marcar-abordado"
              onClick={toggleAbordado}
              disabled={abordadoSaving}
              title="Marcar como abordado"
            >
              <Check size={14} aria-hidden /> Marcar abordado
            </button>
          )}
          <ReabordarMenu
            current={fb.follow_up_at}
            onSchedule={agendarFollowUp}
            onClear={limparFollowUp}
            busy={saving}
            triggerClassName={`fb-reabordar-btn${followUp.vencido ? " is-overdue" : ""}`}
            triggerLabel={
              followUp.agendado
                ? followUp.vencido
                  ? `Venceu ${followUp.label}`
                  : `Reabordar ${followUp.label}`
                : "Reabordar em…"
            }
          />
          <button
            type="button"
            className="btn-wa-sm"
            onClick={() => onAbordar(fb)}
            disabled={!fb.contato_whatsapp}
            title="Abordar no WhatsApp"
          >
            {waIcon} WhatsApp
          </button>
          <KebabMenu items={kebabItems} label="Mais ações" />
        </div>
      </div>

      {/* Nota da ação — discreta, na própria linha; só ganha foco se a pessoa quiser. */}
      <input
        className="fb-note-input"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={commitNote}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        placeholder="Nota da ação (opcional)…"
        disabled={saving}
        aria-label="Nota da ação"
      />
    </div>
  );
}

// ===== Skeleton de carregamento (espelha a forma do card) ===================

/** Placeholder de um card do inbox enquanto a 1ª página carrega — mesma silhueta
   (avatar + cabeçalho + citação + rodapé de ação), com shimmer. */
function FeedbackCardSkeleton() {
  return (
    <div className="card fb-card" aria-busy="true">
      <div className="fb-top" style={{ alignItems: "center" }}>
        <div className="sk-circle" style={{ ["--sk-size" as string]: "10px" } as React.CSSProperties} />
        <div className="sk-circle" style={{ ["--sk-size" as string]: "28px" } as React.CSSProperties} />
        <div className="sk-line w-30" style={{ margin: 0, maxWidth: 150 }} />
        <div className="sk-line w-30" style={{ margin: 0, maxWidth: 70, marginLeft: "auto" }} />
      </div>
      <div className="sk-line sk-lg w-90" style={{ marginTop: 16 }} />
      <div className="sk-line sk-lg w-60" />
      <div className="fb-actions" style={{ marginTop: 16, borderTop: "none", paddingTop: 0 }}>
        <div className="sk-line" style={{ margin: 0, width: 150, height: 34 }} />
        <div className="sk-line" style={{ margin: 0, width: 110, height: 34, marginLeft: "auto" }} />
      </div>
    </div>
  );
}

// ===== Painel de filtros avançados (Modal) ==================================

/** Os ~9 filtros que poluíam a barra moram aqui, num Modal reusado (Esc/backdrop/
   foco já vêm do componente). Os filtros aplicam AO VIVO (a página re-carrega
   por efeito) — então "Aplicar" só fecha; "Limpar" zera tudo de uma vez. */
function FiltersModal({
  type, setType,
  sentiment, setSentiment,
  source, setSource,
  abordado, setAbordado,
  selo, setSelo,
  estado, setEstado,
  planType, setPlanType,
  perfil, setPerfil,
  npsBucket, setNpsBucket,
  temWhatsapp, setTemWhatsapp,
  typeOptions,
  activeCount,
  onClear,
  onClose,
}: {
  type: string; setType: (v: string) => void;
  typeOptions: ConfigItem[];
  sentiment: string; setSentiment: (v: string) => void;
  source: string; setSource: (v: string) => void;
  abordado: "" | "sim" | "nao" | "hoje" | "7d" | "30d";
  setAbordado: (v: "" | "sim" | "nao" | "hoje" | "7d" | "30d") => void;
  selo: string; setSelo: (v: string) => void;
  estado: EstadoAssinatura | ""; setEstado: (v: EstadoAssinatura | "") => void;
  planType: string; setPlanType: (v: string) => void;
  perfil: string; setPerfil: (v: string) => void;
  npsBucket: NpsBucket | ""; setNpsBucket: (v: NpsBucket | "") => void;
  temWhatsapp: TemWhatsappFiltro | ""; setTemWhatsapp: (v: TemWhatsappFiltro | "") => void;
  activeCount: number;
  onClear: () => void;
  onClose: () => void;
}) {
  const titleId = useId();
  return (
    <Modal title="Filtros" onClose={onClose} labelledById={titleId}>
      <div className="modal-body">
        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-type`}>Tipo</label>
            <select id={`${titleId}-type`} value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">Todos os tipos</option>
              {withCurrent(typeOptions, type).map((o) => (
                <option key={o.key} value={o.key}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-sent`}>Sentimento</label>
            <select id={`${titleId}-sent`} value={sentiment} onChange={(e) => setSentiment(e.target.value)}>
              <option value="">Todo sentimento</option>
              <option value="positivo">Positivo</option>
              <option value="neutro">Neutro</option>
              <option value="negativo">Negativo</option>
            </select>
          </div>
        </div>

        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-source`}>Origem</label>
            <select id={`${titleId}-source`} value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">Toda origem</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="bizzu_app">App Bizzu</option>
              <option value="bizzu_billing">Cobrança</option>
              <option value="bizzu_support">Suporte</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-abordado`}>Abordado</label>
            <select
              id={`${titleId}-abordado`}
              value={abordado}
              onChange={(e) =>
                setAbordado(e.target.value as "" | "sim" | "nao" | "hoje" | "7d" | "30d")
              }
            >
              <option value="">Abordado: todos</option>
              <option value="nao">Não abordados</option>
              <option value="sim">Já abordados</option>
              <option value="hoje">Abordados hoje</option>
              <option value="7d">Últimos 7 dias</option>
              <option value="30d">Últimos 30 dias</option>
            </select>
          </div>
        </div>

        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-selo`}>Selo de campanha</label>
            <select id={`${titleId}-selo`} value={selo} onChange={(e) => setSelo(e.target.value)}>
              <option value="">Todos os selos</option>
              {SELOS_CAMPANHA.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-estado`}>Assinatura do cliente</label>
            <select
              id={`${titleId}-estado`}
              value={estado}
              onChange={(e) => setEstado(e.target.value as EstadoAssinatura | "")}
            >
              <option value="">Toda assinatura</option>
              {ESTADO_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-plan`}>Plano do cliente</label>
            <select id={`${titleId}-plan`} value={planType} onChange={(e) => setPlanType(e.target.value)}>
              <option value="">Todos os planos</option>
              <option value="mensal">Mensal</option>
              <option value="anual">Anual</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-perfil`}>Perfil do cliente</label>
            <select id={`${titleId}-perfil`} value={perfil} onChange={(e) => setPerfil(e.target.value)}>
              <option value="">Todos os perfis</option>
              {PERFIL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-nps`}>Faixa de NPS</label>
            <select
              id={`${titleId}-nps`}
              value={npsBucket}
              onChange={(e) => setNpsBucket(e.target.value as NpsBucket | "")}
            >
              <option value="">Todo NPS</option>
              <option value="promotor">Promotores</option>
              <option value="neutro">Neutros</option>
              <option value="detrator">Detratores</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-reach`}>Alcance no WhatsApp</label>
            <select
              id={`${titleId}-reach`}
              value={temWhatsapp}
              onChange={(e) => setTemWhatsapp(e.target.value as TemWhatsappFiltro | "")}
            >
              <option value="">Todo alcance</option>
              <option value="sim">Com WhatsApp</option>
              <option value="nao">Sem WhatsApp (só e-mail)</option>
            </select>
          </div>
        </div>
      </div>
      <div className="modal-foot">
        <Button
          variant="ghost"
          onClick={onClear}
          disabled={activeCount === 0}
        >
          Limpar filtros
        </Button>
        <Button onClick={onClose}>
          {activeCount > 0 ? `Aplicar (${activeCount})` : "Fechar"}
        </Button>
      </div>
    </Modal>
  );
}

// ===== Página ===============================================================

export default function FeedbacksPage() {
  const [items, setItems] = useState<Feedback[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<FeedbackCounts>(EMPTY_COUNTS);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // Vocabulários da org (status + tipos) — defaults + custom, via GET /api/config.
  // Iniciam nos FALLBACKS para a tela já renderizar; trocam quando o config chega.
  const [statusOptions, setStatusOptions] = useState<ConfigItem[]>(STATUS_TABS_FALLBACK);
  const [typeOptions, setTypeOptions] = useState<ConfigItem[]>(TYPE_OPTIONS_FALLBACK);

  useEffect(() => {
    let alive = true;
    configApi
      .get()
      .then((cfg) => {
        if (!alive) return;
        // Fallback defensivo: se a lista vier vazia, mantém os fallbacks.
        if (cfg.action_statuses?.length) setStatusOptions(cfg.action_statuses);
        if (cfg.feedback_types?.length) setTypeOptions(cfg.feedback_types);
      })
      .catch(() => {
        /* sem config (API antiga / offline): segue com os fallbacks. */
      });
    return () => {
      alive = false;
    };
  }, []);

  // Labels efetivos dos tipos e status (para badges e o estado vazio).
  const typeLabels = useMemo(() => labelMap(typeOptions), [typeOptions]);
  const statusLabels = useMemo(() => labelMap(statusOptions), [statusOptions]);

  // Ordenação do feed. "urgencia" (default) usa o priority_index que a IA calcula
  // (mais urgente no topo); "recente" volta à ordem cronológica. Vira ?sort=… na API.
  const [sort, setSort] = useState<"urgencia" | "recente">("urgencia");
  // filtros. `status` é string aberta: além dos fixos, pode ser um status custom.
  const [status, setStatus] = useState<string>("");
  const [type, setType] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  // Filtro "Abordado": um único estado. "" = todos; sim/nao viram ?abordado=true|false;
  // hoje/7d/30d viram ?abordado_periodo=... (nunca os dois juntos).
  const [abordado, setAbordado] = useState<
    "" | "sim" | "nao" | "hoje" | "7d" | "30d"
  >("");
  // Filtro por selo de campanha do contato (status win-back no inbox).
  const [selo, setSelo] = useState("");
  // Fila de follow-up: aba "para hoje" mostra só os VENCIDOS (follow_up_at <= agora).
  const [followUpVencido, setFollowUpVencido] = useState(false);
  // Filtros "por tipo de cliente" do AUTOR do feedback (snapshot partner do contato):
  // estado da assinatura, plano (mensal/anual), perfil de segmentação, alcance no
  // WhatsApp e faixa de NPS. Todos viram query params em /api/feedbacks.
  const [estado, setEstado] = useState<EstadoAssinatura | "">("");
  const [planType, setPlanType] = useState("");
  const [perfil, setPerfil] = useState("");
  const [temWhatsapp, setTemWhatsapp] = useState<TemWhatsappFiltro | "">("");
  const [npsBucket, setNpsBucket] = useState<NpsBucket | "">("");
  // Deep-links da tela Temas (lidos da URL uma vez, no mount):
  // ?cluster_id=<id> (cluster de dores) e ?theme=<tag> (tema exato no JSONB).
  const [clusterId, setClusterId] = useState("");
  const [theme, setTheme] = useState("");

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const c = sp.get("cluster_id");
    const th = sp.get("theme");
    if (c) setClusterId(c);
    if (th) setTheme(th);
  }, []);

  // overlays (criar / editar / excluir) + painel de filtros avançados
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Feedback | null>(null);
  const [deleting, setDeleting] = useState<Feedback | null>(null);
  const [abordando, setAbordando] = useState<Feedback | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const offsetRef = useRef(0);

  const buildQs = useCallback(
    (offset: number) => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      if (type) qs.set("type", type);
      if (sentiment) qs.set("sentiment", sentiment);
      if (source) qs.set("source", source);
      if (search.trim()) qs.set("search", search.trim());
      if (abordado === "sim" || abordado === "nao") {
        qs.set("abordado", abordado === "sim" ? "true" : "false");
      } else if (abordado) {
        // hoje | 7d | 30d → recorte "abordados por período" (já filtra abordado=true).
        qs.set("abordado_periodo", abordado);
      }
      if (selo) qs.set("selo", selo);
      // Fila de follow-up: só os vencidos (follow_up_at <= agora).
      if (followUpVencido) qs.set("follow_up_vencido", "true");
      // Filtros "por tipo de cliente" do autor (sobre o contato juntado).
      if (estado) qs.set("estado", estado);
      if (planType) qs.set("plan_type", planType);
      if (perfil) qs.set("perfil", perfil);
      if (temWhatsapp) qs.set("tem_whatsapp", temWhatsapp);
      if (npsBucket) qs.set("nps_bucket", npsBucket);
      // Deep-links da tela Temas: cluster de dores e tema exato (filtro JSONB).
      if (clusterId) qs.set("cluster_id", clusterId);
      if (theme) qs.set("theme", theme);
      // Ordenação (urgência = priority_index da IA; recente = cronológico).
      qs.set("sort", sort);
      qs.set("limit", String(PAGE_SIZE));
      qs.set("offset", String(offset));
      return qs.toString();
    },
    [
      status, type, sentiment, source, search, abordado, selo, followUpVencido,
      estado, planType, perfil, temWhatsapp, npsBucket,
      clusterId, theme, sort,
    ],
  );

  function normalize(raw: FeedbacksResponse | Feedback[]): {
    items: Feedback[];
    total: number;
    counts: FeedbackCounts;
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
      const raw = await api.get<FeedbacksResponse | Feedback[]>(
        `/api/feedbacks?${buildQs(0)}`,
      );
      const n = normalize(raw);
      setItems(n.items);
      setTotal(n.total);
      setCounts(n.counts);
      offsetRef.current = n.items.length;
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
      const raw = await api.get<FeedbacksResponse | Feedback[]>(
        `/api/feedbacks?${buildQs(offsetRef.current)}`,
      );
      const n = normalize(raw);
      setItems((prev) => [...prev, ...n.items]);
      offsetRef.current += n.items.length;
      setTotal(n.total);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  const onPatched = useCallback(
    (updated: Feedback, previousStatus: FeedbackStatus) => {
      setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
      if (updated.action_status !== previousStatus) {
        setCounts((c) => ({
          ...c,
          [previousStatus]: Math.max(0, (c[previousStatus] ?? 0) - 1),
          [updated.action_status]: (c[updated.action_status] ?? 0) + 1,
        }));
      }
    },
    [],
  );

  /** Substitui o card após edição via modal (sem mexer em contagens de status). */
  const onEdited = useCallback((updated: Feedback) => {
    setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
    setEditing(null);
  }, []);

  /** Atualiza os selos do contato em TODOS os cards do mesmo contato (selo é do contato). */
  const onSelosChanged = useCallback((id: string, selos: string[]) => {
    setItems((prev) => {
      const card = prev.find((it) => it.id === id);
      const contatoId = card?.contato_id;
      if (!contatoId) return prev.map((it) => (it.id === id ? { ...it, selos } : it));
      return prev.map((it) => (it.contato_id === contatoId ? { ...it, selos } : it));
    });
  }, []);

  /** Insere um feedback novo no topo do feed e atualiza contagens. */
  const onCreated = useCallback((created: Feedback) => {
    setItems((prev) => [created, ...prev]);
    setTotal((t) => t + 1);
    setCounts((c) => ({
      ...c,
      [created.action_status]: (c[created.action_status] ?? 0) + 1,
    }));
    setCreating(false);
  }, []);

  /** Remove o card excluído e atualiza contagens. */
  const onDeleted = useCallback((id: string) => {
    setItems((prev) => {
      const gone = prev.find((it) => it.id === id);
      if (gone) {
        setCounts((c) => ({
          ...c,
          [gone.action_status]: Math.max(0, (c[gone.action_status] ?? 0) - 1),
        }));
        setTotal((t) => Math.max(0, t - 1));
      }
      return prev.filter((it) => it.id !== id);
    });
    setDeleting(null);
  }, []);

  // Quando filtramos por status, esconde cards que saíram do bucket após o PATCH.
  const visible = status ? items.filter((it) => it.action_status === status) : items;
  const hasMore = visible.length < total;
  const hasFilters = !!(
    type || sentiment || source || search || abordado || selo || followUpVencido ||
    estado || planType || perfil || temWhatsapp || npsBucket ||
    clusterId || theme
  );

  // Filtros AVANÇADOS = os que vivem no painel "Filtros" (busca/status/deep-link
  // ficam de fora — têm controle próprio visível). Conta quantos estão ativos
  // para o selo no botão e decide se mostramos o atalho "Limpar filtros".
  const advancedFilterCount = [
    type, sentiment, source, abordado, selo,
    estado, planType, perfil, npsBucket, temWhatsapp,
  ].filter(Boolean).length;

  const clearAdvancedFilters = useCallback(() => {
    setType("");
    setSentiment("");
    setSource("");
    setAbordado("");
    setSelo("");
    setEstado("");
    setPlanType("");
    setPerfil("");
    setNpsBucket("");
    setTemWhatsapp("");
  }, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Feedbacks</h1>
          <div className="page-sub">
            Inbox de monitoramento — leia, decida a melhoria e marque o status
          </div>
        </div>
        <div className="page-head-actions">
          {!loading && <span className="refresh-note">{total} no total</span>}
          <Button onClick={() => setCreating(true)}>
            <span aria-hidden>＋</span> Novo feedback
          </Button>
        </div>
      </div>

      {/* Abas por status, com contagens de counts_by_status. As abas com count 0
         ficam apagadas (não competem); a ativa é bem destacada. Todas clicáveis. */}
      <div className="status-tabs">
        <button
          className={`status-tab ${status === "" && !followUpVencido ? "active" : ""}`}
          onClick={() => {
            setStatus("");
            setFollowUpVencido(false);
          }}
        >
          Todos
        </button>
        {statusOptions.map((s) => {
          const n = (counts as unknown as Record<string, number>)[s.key] ?? 0;
          const isActive = status === s.key && !followUpVencido;
          return (
            <button
              key={s.key}
              className={`status-tab ${isActive ? "active" : ""} ${n === 0 && !isActive ? "is-empty" : ""}`}
              onClick={() => {
                setFollowUpVencido(false);
                setStatus(s.key);
              }}
            >
              {s.label}
              <span className="tab-count">{n}</span>
            </button>
          );
        })}
        {/* Fila de follow-up: mostra só os feedbacks com reabordagem VENCIDA. */}
        <button
          className={`status-tab fb-followup-tab ${followUpVencido ? "active" : ""}`}
          onClick={() => {
            setStatus("");
            setFollowUpVencido(true);
          }}
          title="Feedbacks com follow-up agendado para hoje ou antes"
        >
          <CalendarClock size={13} aria-hidden style={{ verticalAlign: "-2px", marginRight: 5 }} />
          Follow-up (para hoje)
        </button>
      </div>

      {/* Barra enxuta: só BUSCA + botão "Filtros" (os avançados ficam no painel).
         Os ~9 dropdowns moraram aqui e quebravam em 3 linhas — agora colapsados. */}
      <div className="toolbar">
        <label className="search">
          <span className="ico">🔍</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar no texto, nome ou WhatsApp…"
          />
        </label>
        <label className="fb-sort" title="Ordenar o inbox">
          <span className="fb-sort-label">Ordenar</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as "urgencia" | "recente")}
            aria-label="Ordenar feedbacks"
          >
            <option value="urgencia">Mais urgentes</option>
            <option value="recente">Mais recentes</option>
          </select>
        </label>
        <Button
          variant="secondary"
          onClick={() => setShowFilters(true)}
          aria-haspopup="dialog"
          className="gap-2"
        >
          <span aria-hidden>⚙</span>
          Filtros
          {advancedFilterCount > 0 && (
            <span className="tab-count" style={{ background: "var(--indigo)", color: "#fff" }}>
              {advancedFilterCount}
            </span>
          )}
        </Button>
        {advancedFilterCount > 0 && (
          <Button variant="ghost" onClick={clearAdvancedFilters}>
            Limpar filtros
          </Button>
        )}
      </div>

      {/* Filtro vindo da tela Temas (deep-link): mostra e permite limpar. */}
      {(clusterId || theme) && (
        <div className="note">
          <span className="note-ico">🔎</span>
          <span>
            {clusterId ? (
              <>Filtrando pelos feedbacks de uma <b>dor</b> (cluster) específica.</>
            ) : (
              <>
                Filtrando pelo tema <b>{theme}</b>.
              </>
            )}
          </span>
          <button
            type="button"
            className="btn ghost sm"
            style={{ marginLeft: "auto" }}
            onClick={() => {
              setClusterId("");
              setTheme("");
            }}
          >
            Limpar filtro
          </button>
        </div>
      )}

      {err && (
        <div className="flash err">
          Não consegui carregar os feedbacks ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {!err && loading && visible.length === 0 ? (
        <div className="feed fb-feed" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <FeedbackCardSkeleton key={i} />
          ))}
        </div>
      ) : !err && visible.length === 0 ? (
        <div className="card fb-feed">
          <div className="empty">
            <div className="empty-illu">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 5h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
                <path d="M4 7l8 6 8-6" />
              </svg>
            </div>
            <div className="empty-title">
              {followUpVencido
                ? "Nenhum follow-up para hoje"
                : status
                ? `Nada em "${statusLabels[status] ?? status}"`
                : hasFilters
                ? "Nenhum feedback bate com os filtros"
                : "Nenhum feedback ainda"}
            </div>
            <p className="empty-sub">
              {followUpVencido
                ? "Tudo em dia! Nenhum feedback tem reabordagem vencida. Agende um follow-up pelo menu “Reabordar em…” de um card."
                : status
                ? "Mude de aba ou ajuste os filtros para ver outros feedbacks."
                : hasFilters
                ? "Tente afrouxar os filtros ou limpar a busca."
                : "Os feedbacks do WhatsApp caem aqui. Você também pode registrar um manualmente."}
            </p>
            {!status && !hasFilters && (
              <div className="empty-cta">
                <Button onClick={() => setCreating(true)}>
                  <span aria-hidden>＋</span> Adicionar o primeiro
                </Button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <Stagger className="feed fb-feed">
          {visible.map((fb) => (
            <StaggerItem key={fb.id}>
              <FeedbackCard
                fb={fb}
                onPatched={onPatched}
                onEdit={setEditing}
                onDelete={setDeleting}
                onAbordar={setAbordando}
                onSelosChanged={onSelosChanged}
                statusOptions={statusOptions}
                typeLabels={typeLabels}
              />
            </StaggerItem>
          ))}
        </Stagger>
      )}

      {hasMore && !status && (
        <div className="load-more">
          <Button variant="ghost" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Carregando…" : "Carregar mais"}
          </Button>
        </div>
      )}

      {showFilters && (
        <FiltersModal
          type={type} setType={setType}
          sentiment={sentiment} setSentiment={setSentiment}
          source={source} setSource={setSource}
          abordado={abordado} setAbordado={setAbordado}
          selo={selo} setSelo={setSelo}
          estado={estado} setEstado={setEstado}
          planType={planType} setPlanType={setPlanType}
          perfil={perfil} setPerfil={setPerfil}
          npsBucket={npsBucket} setNpsBucket={setNpsBucket}
          temWhatsapp={temWhatsapp} setTemWhatsapp={setTemWhatsapp}
          typeOptions={typeOptions}
          activeCount={advancedFilterCount}
          onClear={clearAdvancedFilters}
          onClose={() => setShowFilters(false)}
        />
      )}
      {creating && (
        <CreateFeedbackModal
          onCancel={() => setCreating(false)}
          onCreated={onCreated}
          typeOptions={typeOptions}
        />
      )}
      {editing && (
        <EditFeedbackModal
          feedback={editing}
          onCancel={() => setEditing(null)}
          onSaved={onEdited}
          typeOptions={typeOptions}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Excluir feedback?"
          message={
            <>
              Essa ação é permanente. O feedback de{" "}
              <b>{deleting.contato_nome || "sem nome"}</b> será removido do inbox.
            </>
          }
          quote={feedbackText(deleting.text)}
          confirmLabel="Sim, excluir"
          confirmingLabel="Excluindo…"
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            await api.del(`/api/feedbacks/${deleting.id}`);
            onDeleted(deleting.id);
          }}
        />
      )}
      {abordando && (
        <AbordarModal
          target={abordando}
          onClose={() => setAbordando(null)}
          onMarcarAbordado={async () => {
            if (abordando.abordado) return;
            const prev = abordando.action_status;
            const optimistic: Feedback = {
              ...abordando,
              abordado: true,
              abordado_em: new Date().toISOString(),
            };
            onPatched(optimistic, prev);
            try {
              const updated = await api.patch<Feedback>(
                `/api/feedbacks/${abordando.id}`,
                { abordado: true },
              );
              onPatched(updated, prev);
            } catch {
              onPatched(abordando, prev);
            }
          }}
        />
      )}
    </div>
  );
}
