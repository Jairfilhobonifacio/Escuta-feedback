"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bug,
  CalendarClock,
  CalendarPlus,
  CalendarX,
  Check,
  ChevronDown,
  FileText,
  Gauge,
  HandHeart,
  Lightbulb,
  Mail,
  MessageCircle,
  MessageSquare,
  Phone,
  Search,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  StickyNote,
  Tag,
  ThumbsUp,
  Trash2,
  UserX,
  X,
  Users,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import SeloPopover from "@/components/SeloPopover";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { feedbackText, churnReasonLabel, perfilLabel } from "@/lib/format";
import {
  api,
  campanha as campanhaApi,
  config as configApi,
  contacts as contactsApi,
  feedbacks as feedbacksApi,
  whatsapp as whatsappApi,
  type ConfigItem,
  type Contact360,
  type Feedback,
  type FeedbackInput,
  type FeedbackPatch,
  type FeedbackStatus,
  type SeloSugestao,
  type SeloVivo,
  type SeloOrigem,
  type Timeline360Item,
  type WhatsappSendPreview,
  type WhatsappThread,
} from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  nps: "NPS",
  csat: "CSAT",
  churn: "Cancelamento",
  exit: "Exit survey",
  ticket: "Atendimento",
  report: "Report de questão",
  edital_request: "Pedido de edital",
  elogio: "Elogio",
  sugestao: "Sugestão",
  bug: "Bug",
  nota: "Nota",
  abordagem: "Abordagem",
  outro: "Outro",
};

/** Ícone + cor por TIPO de evento, para diferenciar os marcos "de relance" na
    timeline. `accent` é uma cor CSS (token da paleta) usada no ícone e no halo do
    selo; `tone` mapeia o vínculo semântico (negativo/positivo/neutro/marca). Tipos
    fora do mapa caem no default neutro (MessageSquare). */
interface TypeVisual {
  Icon: LucideIcon;
  accent: string;
  soft: string;
  line: string;
}
const TYPE_VISUAL: Record<string, TypeVisual> = {
  nps: { Icon: Gauge, accent: "var(--indigo-light)", soft: "var(--promoter-soft)", line: "var(--promoter-line)" },
  csat: { Icon: Gauge, accent: "var(--indigo-light)", soft: "var(--promoter-soft)", line: "var(--promoter-line)" },
  churn: { Icon: UserX, accent: "var(--detractor)", soft: "var(--detractor-soft)", line: "var(--detractor-line)" },
  exit: { Icon: UserX, accent: "var(--detractor)", soft: "var(--detractor-soft)", line: "var(--detractor-line)" },
  bug: { Icon: Bug, accent: "var(--detractor)", soft: "var(--detractor-soft)", line: "var(--detractor-line)" },
  report: { Icon: Bug, accent: "var(--detractor)", soft: "var(--detractor-soft)", line: "var(--detractor-line)" },
  elogio: { Icon: ThumbsUp, accent: "var(--indigo-light)", soft: "var(--promoter-soft)", line: "var(--promoter-line)" },
  sugestao: { Icon: Lightbulb, accent: "var(--gold-soft)", soft: "var(--passive-soft)", line: "var(--passive-line)" },
  edital_request: { Icon: FileText, accent: "var(--gold-soft)", soft: "var(--passive-soft)", line: "var(--passive-line)" },
  nota: { Icon: StickyNote, accent: "var(--text-dim)", soft: "rgba(86, 84, 107, 0.08)", line: "var(--charcoal-2)" },
  abordagem: { Icon: HandHeart, accent: "var(--indigo-light)", soft: "var(--promoter-soft)", line: "var(--promoter-line)" },
  ticket: { Icon: MessageCircle, accent: "var(--text-dim)", soft: "rgba(86, 84, 107, 0.08)", line: "var(--charcoal-2)" },
};
const TYPE_VISUAL_DEFAULT: TypeVisual = {
  Icon: MessageSquare,
  accent: "var(--text-dim)",
  soft: "rgba(86, 84, 107, 0.08)",
  line: "var(--charcoal-2)",
};
function typeVisual(type: string): TypeVisual {
  return TYPE_VISUAL[type] ?? TYPE_VISUAL_DEFAULT;
}

/** Selo do tipo de evento: ícone + rótulo num chip tingido pela cor do tipo, p/ os
    marcos saltarem aos olhos (assinatura/feedback/nota/abordagem/cancelamento). */
function TypeMark({ type }: { type: string }) {
  const v = typeVisual(type);
  const label = TYPE_LABEL[type] ?? type;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-[7px] border px-2.5 py-1 text-[12px] font-semibold leading-none"
      style={{ color: v.accent, background: v.soft, borderColor: v.line }}
    >
      <v.Icon size={13} strokeWidth={2.2} aria-hidden />
      {label}
    </span>
  );
}

/** FALLBACK dos tipos oferecidos ao registrar feedback à mão (se GET /api/config
    falhar). O conjunto efetivo — defaults + custom da org — vem de config.get()
    (feedback_types) e é passado por props ao modal. */
const TYPE_OPTIONS_FALLBACK: ConfigItem[] = [
  { key: "nota", label: "Nota" },
  { key: "abordagem", label: "Abordagem" },
  { key: "elogio", label: "Elogio" },
  { key: "sugestao", label: "Sugestão" },
  { key: "bug", label: "Bug" },
  { key: "churn", label: "Cancelamento" },
  { key: "outro", label: "Outro" },
];

/** Garante que um `key` (ex.: vindo de dado custom fora do vocabulário carregado)
    apareça no select, para não "perder" o valor default selecionado. */
function withKey(items: ConfigItem[], key: string | null | undefined): ConfigItem[] {
  if (!key || items.some((it) => it.key === key)) return items;
  return [...items, { key, label: key }];
}

/** ISO (UTC) -> valor de <input type="datetime-local"> no fuso local (sem 'Z'). */
function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const SOURCE_LABEL: Record<string, string> = {
  bizzu_app: "app Bizzu",
  bizzu_billing: "cobrança",
  bizzu_support: "suporte",
  whatsapp: "WhatsApp",
  manual: "manual",
};

const SENT_META: Record<string, { cls: string; label: string }> = {
  positivo: { cls: "s-pos", label: "positivo" },
  neutro: { cls: "s-neu", label: "neutro" },
  negativo: { cls: "s-neg", label: "negativo" },
};

/** FALLBACK dos status (usado se GET /api/config falhar). Espelha os defaults de
    ACOMPANHAMENTO do backend (key/label/cor); o conjunto efetivo — defaults + custom
    da org — vem de config.get() e é passado por props. */
const STATUS_OPTIONS_FALLBACK: ConfigItem[] = [
  { key: "a_abordar", label: "A abordar", cor: "#6366f1" },
  { key: "aguardando_retorno", label: "Aguardando retorno", cor: "#f59e0b" },
  { key: "em_acompanhamento", label: "Em acompanhamento", cor: "#3b82f6" },
  { key: "resolvido", label: "Resolvido", cor: "#10b981" },
  { key: "sem_retorno", label: "Sem retorno", cor: "#94a3b8" },
  { key: "descartado", label: "Descartado", cor: "#64748b" },
];

/** Garante que o status ATUAL (ex.: um custom fora do vocabulário carregado)
    apareça no select, para a edição não "perder" o valor selecionado. */
function withCurrentStatus(items: ConfigItem[], current: string | null | undefined): ConfigItem[] {
  if (!current || items.some((it) => it.key === current)) return items;
  return [...items, { key: current, label: current }];
}

/** Selos de campanha win-back sugeridos no controle do cabeçalho. */
const SELOS_CAMPANHA = ["contatado", "respondeu", "cortesia", "reativou"];

/** Origem de um evento de selo → texto em PT (para a frase humana na timeline). */
const SELO_ORIGEM_LABEL: Record<string, string> = {
  inbound: "resposta no WhatsApp",
  whatsapp_enviado: "envio 1:1",
  abordagem: "abordagem registrada",
  form: "formulário",
  manual: "manual",
  regra: "regra automática",
  ia: "sugestão da IA",
};

function seloOrigemLabel(origem?: SeloOrigem): string | null {
  if (!origem) return null;
  return SELO_ORIGEM_LABEL[origem] ?? origem;
}

/** Chip de selo VIVO (derivado do estado, READ-ONLY) — distinto do selo manual
    (`.selo-chip` com "x"): borda TRACEJADA + leve opacidade + emoji, SEM "x".
    `title` = motivo (tooltip). Espelha o chip da tela Clientes. */
function SeloVivoChip({ selo }: { selo: SeloVivo }) {
  const c = selo.cor || "var(--indigo)";
  return (
    <span
      className="selo-chip"
      title={selo.motivo ? `${selo.nome} · ${selo.motivo} (automático)` : `${selo.nome} (automático)`}
      style={{
        borderColor: c,
        borderStyle: "dashed",
        color: c,
        background: `color-mix(in srgb, ${c} 10%, transparent)`,
        opacity: 0.92,
      }}
    >
      {selo.icone ? (
        <span aria-hidden style={{ fontSize: 11, lineHeight: 1 }}>{selo.icone}</span>
      ) : (
        <span className="selo-dot" style={{ background: c }} />
      )}
      {selo.nome}
    </span>
  );
}

function sentimentBadge(s?: string | null) {
  if (!s) return null;
  const m = SENT_META[s];
  if (!m) return null;
  return <span className={`badge sent ${m.cls}`}>{m.label}</span>;
}

/** Cor default da pílula de status quando o config não traz `cor` (ou status legado). */
const STATUS_DOT_FALLBACK = "#94a3b8";

/** Badge de STATUS de acompanhamento tingido pela COR do status (vinda do /api/config),
    para a etapa do cliente saltar aos olhos na timeline. Status legado/fora do
    vocabulário ainda renderiza: label cru da key + cor neutra de fallback. */
function statusBadge(status: string | null | undefined, statusOptions: ConfigItem[]) {
  if (!status) return null;
  const it = statusOptions.find((s) => s.key === status);
  const cor = it?.cor || STATUS_DOT_FALLBACK;
  const label = it?.label ?? status;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-[7px] border px-2.5 py-1 text-[12px] font-semibold leading-none"
      style={{
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

function themeChips(themes?: string[] | null) {
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

// ===== Follow-up ("Reabordar em...") ========================================
// Agenda quando reabordar um feedback (`follow_up_at`, ISO/UTC) direto na
// timeline. Vencido = follow_up_at <= agora → DESTACADO. PATCH /api/feedbacks/
// {id} {follow_up_at}; null limpa. Espelha o controle da tela Feedbacks.

/** Info do follow-up: tem? vencido? rótulo curto (DD/MM, fuso local). */
function followUpInfo(iso: string | null | undefined): {
  agendado: boolean;
  vencido: boolean;
  label: string;
} {
  if (!iso) return { agendado: false, vencido: false, label: "" };
  const label = new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  return { agendado: true, vencido: new Date(iso).getTime() <= Date.now(), label };
}

/** ISO (UTC) daqui a N dias, às 9h local (horário comercial). */
function isoEmDias(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  d.setHours(9, 0, 0, 0);
  return d.toISOString();
}

/** Date → valor de <input type="date"> no fuso local. */
function toDateInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Menu "Reabordar em…" (3 dias / 7 dias / escolher data / limpar) da timeline.
    Seta follow_up_at via callback; fecha no clique fora e no Esc. */
function ReabordarMenu({
  current,
  onSchedule,
  onClear,
  busy,
}: {
  current: string | null | undefined;
  onSchedule: (iso: string) => void;
  onClear: () => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [dateVal, setDateVal] = useState(() => toDateInputValue(new Date()));
  const boxRef = useRef<HTMLDivElement>(null);
  const info = followUpInfo(current);

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
    onSchedule(new Date(`${dateVal}T09:00`).toISOString());
    close();
  }

  const triggerCls = `fb-reabordar-btn${info.vencido ? " is-overdue" : ""}`;
  const triggerLabel = info.agendado
    ? info.vencido
      ? `Venceu ${info.label}`
      : `Reabordar ${info.label}`
    : "Reabordar em…";

  return (
    <div className="fb-reabordar" ref={boxRef}>
      <button
        type="button"
        className={triggerCls}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        title="Agendar quando reabordar este feedback"
      >
        <CalendarClock size={14} aria-hidden />
        {triggerLabel}
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

function field(label: string, value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div key={label}>
      <span className="lbl">{label}</span>
      <span className="val">{String(value)}</span>
    </div>
  );
}

/** Balão de conversa p/ o vazio do chat (stroke=currentColor). */
const EMPTY_CHAT = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </svg>
);

/** Conexão interrompida p/ o erro do chat (stroke=currentColor). */
const EMPTY_CHAT_OFF = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
    <line x1="12" y1="2" x2="12" y2="12" />
  </svg>
);

/** SVG discreto p/ a timeline vazia (folha/registro, stroke=currentColor). */
const EMPTY_TIMELINE = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
    <path d="M9 13h6M9 17h4" />
  </svg>
);

/** Esqueleto da ficha inteira (cabeçalho + grid de perfil + timeline) enquanto
    o GET /360 não volta. Espelha a forma real para a troca não "saltar". */
function Skeleton360() {
  return (
    <div aria-busy aria-hidden>
      <div className="card c360-profile">
        <div className="card-head">
          <div style={{ flex: 1 }}>
            <div className="sk-line w-30" style={{ margin: "2px 0" }} />
            <div className="sk-line sk-sm w-40" style={{ margin: "6px 0 2px" }} />
          </div>
        </div>
        <div className="c360-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i}>
              <div className="sk-line sk-sm w-50" style={{ margin: "2px 0 8px" }} />
              <div className="sk-line w-70" style={{ margin: 0 }} />
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}>
            <div className="sk-line w-40" style={{ margin: "2px 0" }} />
            <div className="sk-line sk-sm w-60" style={{ margin: "6px 0 2px" }} />
          </div>
        </div>
        <ul className="tl">
          {Array.from({ length: 4 }).map((_, i) => (
            <li key={i} className="tl-item">
              <span className="tl-dot" aria-hidden />
              <div className="tl-top" style={{ gap: 9 }}>
                <div className="sk-line" style={{ width: 54, margin: 0 }} />
                <div className="sk-line" style={{ width: 70, margin: 0 }} />
              </div>
              <div className="sk-line w-90" style={{ marginTop: 12 }} />
              <div className="sk-line w-60" style={{ marginTop: 2 }} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Só a data (sem hora) para campos de assinatura (currentPeriodEnd/respondedAt). */
function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

/** Forma do snapshot partner.subscription (espelha `_build_partner_profile` do sync;
    são EXATAMENTE estes campos — não há data de assinatura nem valor no snapshot). */
interface PartnerSub {
  state?: string | null;
  active?: boolean | null;
  cancelled?: boolean | null;
  complimentary?: boolean | null;
  planType?: string | null;
  cancellationReason?: string | null;
  daysAsSubscriber?: number | null;
  currentPeriodEnd?: string | null;
}

/** Rótulo legível do estado da assinatura (espelha ESTADO_META da tela Clientes). */
const SUB_STATE_LABEL: Record<string, string> = {
  active_paying: "Pagante ativo",
  past_due: "Em atraso",
  paid_without_access: "Pago sem acesso",
  complimentary: "Cortesia",
  cancelled: "Cancelado",
};

/** Plano mensal/anual → ciclo de cobrança legível (o snapshot só traz planType). */
function cicloLabel(planType?: string | null): string | null {
  if (!planType) return null;
  const k = planType.toLowerCase();
  if (k.includes("anu")) return "Anual";
  if (k.includes("mens")) return "Mensal";
  return planType;
}

/** Badge de status da assinatura (verde pagante/cortesia, vermelho cancelado/atraso). */
function subStatusBadge(sub: PartnerSub) {
  const state = sub.state ?? null;
  const label = state ? SUB_STATE_LABEL[state] ?? state.replace(/_/g, " ") : null;
  if (!label) return null;
  const variant: "positive" | "negative" | "neutral" =
    sub.active ? "positive" : sub.cancelled || state === "past_due" ? "negative" : "neutral";
  return (
    <div>
      <span className="lbl">Status da assinatura</span>
      <span className="val">
        <Badge variant={variant}>{label}</Badge>
        {sub.complimentary && <Badge variant="neutral" style={{ marginLeft: 6 }}>cortesia</Badge>}
      </span>
    </div>
  );
}

function ProfileCard({ partner }: { partner: Record<string, unknown> }) {
  const sub = ((partner.subscription as PartnerSub | undefined) ?? {}) as PartnerSub;
  const nps = (partner.nps as Record<string, unknown> | undefined) ?? {};
  // currentPeriodEnd é a renovação (assinatura ativa) ou o fim do acesso (cancelada).
  const renovaLabel = sub.active && !sub.cancelled ? "Renova em" : "Fim do ciclo";
  return (
    <Reveal delay={0.04} className="card c360-profile">
      <div className="card-head">
        <div className="section-title">Perfil &amp; assinatura</div>
        <div className="card-head-sub">snapshot da API de Clientes</div>
      </div>
      <div className="c360-grid">
        {field("Perfil", perfilLabel(partner.profile as string | null) || null)}
        {subStatusBadge(sub)}
        {field("Ciclo", cicloLabel(sub.planType))}
        {sub.currentPeriodEnd != null && field(renovaLabel, fmtDay(sub.currentPeriodEnd))}
        {field("Dias de casa", sub.daysAsSubscriber)}
        {field("NPS (nota)", nps.score)}
        {field("Motivo de churn", churnReasonLabel(sub.cancellationReason) || null)}
      </div>
    </Reveal>
  );
}

// ===== Sugestões de selo pela IA (cabeçalho) =================================
// Botão "Sugerir selos (IA)" que chama POST /sugerir-selos (a IA PROPÕE selos de
// negócio, não aplica). As sugestões aparecem como CHIPS clicáveis, com visual de
// SUGESTÃO (borda pontilhada âmbar + ✨) distinto dos selos VIVOS (dashed + emoji) e
// dos MANUAIS (borda sólida + ponto). Clicar numa sugestão aplica via applySelo,
// some da lista e recarrega a ficha. Estados graciosos: loading / vazio / IA off.

function SugestoesSelos({
  contactId,
  selos,
  onApplied,
}: {
  contactId: string;
  /** Selos manuais já aplicados — sugestões já aplicadas são filtradas para fora. */
  selos: string[];
  /** Após aplicar uma sugestão: recarrega a ficha (selos vivos/timeline atualizam). */
  onApplied: () => void;
}) {
  // 'idle' antes de pedir; 'loading' enquanto busca; 'done' com sugestoes resolvidas;
  // 'error' quando a chamada falha (IA indisponível).
  const [estado, setEstado] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [sugestoes, setSugestoes] = useState<SeloSugestao[]>([]);
  // Nome da sugestão em processo de aplicação (desabilita só o chip clicado).
  const [aplicando, setAplicando] = useState<string | null>(null);
  const [aplicado, setAplicado] = useState<string | null>(null);

  async function pedir() {
    if (estado === "loading") return;
    setEstado("loading");
    setAplicado(null);
    try {
      const out = await campanhaApi.sugerirSelos(contactId);
      // Filtra fora o que o cliente já tem (a IA pode repetir um selo existente).
      const novas = (out.sugestoes ?? []).filter((s) => !selos.includes(s.nome));
      setSugestoes(novas);
      setEstado("done");
    } catch {
      setSugestoes([]);
      setEstado("error");
    }
  }

  async function aplicar(s: SeloSugestao) {
    if (aplicando) return;
    setAplicando(s.nome);
    try {
      await campanhaApi.applySelo(contactId, { nome: s.nome });
      // Some da lista de sugestões e recarrega a ficha (selo vira "manual"/"vivo").
      setSugestoes((prev) => prev.filter((x) => x.nome !== s.nome));
      setAplicado(s.nome);
      onApplied();
    } catch {
      /* erro silencioso: a sugestão fica para nova tentativa. */
    } finally {
      setAplicando(null);
    }
  }

  return (
    <div className="mt-2.5 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={pedir}
          disabled={estado === "loading"}
          aria-busy={estado === "loading"}
          title="A IA analisa este cliente e sugere selos de negócio"
          className="inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-[5px] text-[11.5px] font-semibold leading-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gold,#b45309)] disabled:cursor-progress"
          style={{
            color: "var(--gold, #b45309)",
            borderColor: "color-mix(in srgb, var(--gold, #b45309) 45%, transparent)",
            background: "color-mix(in srgb, var(--gold, #b45309) 8%, transparent)",
          }}
        >
          <Sparkles size={13} strokeWidth={2.2} aria-hidden />
          {estado === "loading"
            ? "Analisando…"
            : estado === "done" || estado === "error"
              ? "Sugerir de novo"
              : "Sugerir selos (IA)"}
        </button>
        {aplicado && (
          <span
            className="inline-flex items-center gap-1 text-[11.5px] font-medium"
            style={{ color: "var(--indigo-light)" }}
          >
            <Check size={12} strokeWidth={2.6} aria-hidden /> {aplicado} aplicado
          </span>
        )}
      </div>

      {estado === "loading" && (
        <div className="flex flex-wrap gap-2" aria-busy aria-hidden>
          {[88, 116, 72].map((w, i) => (
            <span
              key={i}
              className="sk-line"
              style={{ width: w, height: 24, borderRadius: 999, margin: 0 }}
            />
          ))}
        </div>
      )}

      {estado === "error" && (
        <p className="m-0 text-[12px]" style={{ color: "var(--text-faint)" }}>
          IA indisponível agora — tente de novo em instantes.
        </p>
      )}

      {estado === "done" && sugestoes.length === 0 && (
        <p className="m-0 text-[12px]" style={{ color: "var(--text-faint)" }}>
          Nenhuma sugestão no momento.
        </p>
      )}

      {estado === "done" && sugestoes.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {sugestoes.map((s) => {
            const gold = "var(--gold, #b45309)";
            const busy = aplicando === s.nome;
            return (
              <button
                key={s.nome}
                type="button"
                onClick={() => aplicar(s)}
                disabled={busy}
                title={s.motivo ? `${s.motivo} — clique para aplicar` : "Clique para aplicar"}
                aria-label={`Aplicar selo sugerido ${s.nome}`}
                className="selo-chip transition-colors disabled:cursor-progress"
                style={{
                  borderStyle: "dashed",
                  borderColor: `color-mix(in srgb, ${gold} 55%, transparent)`,
                  color: gold,
                  background: `color-mix(in srgb, ${gold} 9%, transparent)`,
                }}
              >
                <Sparkles size={11} strokeWidth={2.2} aria-hidden />
                {s.nome}
                {busy ? (
                  <span aria-hidden style={{ opacity: 0.7 }}>{"…"}</span>
                ) : (
                  <Plus size={11} strokeWidth={2.4} aria-hidden style={{ opacity: 0.8 }} />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ===== Selos do contato (cabeçalho) =========================================

function ContatoSelos({
  contactId,
  selos,
  selosVivos,
  onChanged,
  onApplied,
}: {
  contactId: string;
  selos: string[];
  /** Selos vivos derivados do estado (READ-ONLY) — renderizados antes dos manuais. */
  selosVivos: SeloVivo[];
  onChanged: (selos: string[]) => void;
  /** Recarrega a ficha inteira (usado após aplicar uma sugestão da IA). */
  onApplied: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const disponiveis = SELOS_CAMPANHA.filter((s) => !selos.includes(s));

  async function aplicar(nome: string) {
    if (busy) return;
    setBusy(true);
    try {
      const out = await campanhaApi.applySelo(contactId, { nome });
      onChanged(out.selos);
      setOpen(false);
    } catch {
      /* erro silencioso */
    } finally {
      setBusy(false);
    }
  }
  async function remover(nome: string) {
    if (busy) return;
    setBusy(true);
    try {
      const out = await campanhaApi.removeSeloFromContact(contactId, nome);
      const next = (out as { selos?: string[] })?.selos;
      onChanged(Array.isArray(next) ? next : selos.filter((s) => s !== nome));
    } catch {
      onChanged(selos.filter((s) => s !== nome));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    <div className="c360-selos">
      {/* Selos VIVOS (automáticos, read-only) primeiro; depois um separador sutil
          e os selos MANUAIS (editáveis, com "x" + "+selo"). */}
      {selosVivos.map((sv) => (
        <SeloVivoChip key={`vivo-${sv.nome}`} selo={sv} />
      ))}
      {selosVivos.length > 0 && selos.length > 0 && (
        <span
          aria-hidden
          style={{
            width: 1,
            alignSelf: "stretch",
            margin: "1px 2px",
            background: "var(--charcoal-2)",
          }}
        />
      )}
      {selos.map((nome) => (
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
            <X size={11} strokeWidth={2.4} aria-hidden />
          </button>
        </span>
      ))}
      <SeloPopover
        open={open}
        onOpenChange={setOpen}
        trigger={({ open: isOpen, toggle }) => (
          <button
            type="button"
            className="selo-add"
            onClick={toggle}
            aria-expanded={isOpen}
            aria-label="Aplicar selo de campanha"
            disabled={busy}
          >
            <Plus size={12} strokeWidth={2.2} aria-hidden /> selo
          </button>
        )}
      >
        {disponiveis.length === 0 ? (
          <div className="picker-empty">Todos os selos de campanha já aplicados.</div>
        ) : (
          <div className="selo-pop-list" style={{ marginBottom: 0, paddingBottom: 0, borderBottom: "none" }}>
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
      </SeloPopover>
    </div>
    <SugestoesSelos contactId={contactId} selos={selos} onApplied={onApplied} />
    </>
  );
}

// ===== Modal de edição de texto/nota de um item ==============================

function EditItemModal({
  item,
  onClose,
  onSaved,
}: {
  item: Timeline360Item;
  onClose: () => void;
  onSaved: (id: string, patch: { text: string | null; action_note: string | null }) => void;
}) {
  const titleId = useId();
  const [text, setText] = useState(item.text ?? "");
  const [note, setNote] = useState(item.action_note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!item.id) return;
    setSaving(true);
    setError(null);
    const nextText = text.trim() || null;
    // action_note: o backend faz `.strip() or None`; "" zera a nota.
    const nextNote = note.trim();
    const body: FeedbackPatch = { text: nextText, action_note: nextNote };
    try {
      await api.patch<Feedback>(`/api/feedbacks/${item.id}`, body);
      onSaved(item.id, { text: nextText, action_note: nextNote || null });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title="Editar evento" onClose={onClose} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="field">
            <label htmlFor={`${titleId}-text`}>O que o cliente disse</label>
            <textarea
              id={`${titleId}-text`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="O que o cliente disse…"
            />
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-note`}>Nota interna (só o time vê)</label>
            <textarea
              id={`${titleId}-note`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Anotação do time sobre este evento…"
            />
          </div>
          {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
        </div>
        <div className="modal-foot">
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Cor da bolinha do status (vinda do /api/config) p/ tingir o select e o swatch.
    Status sem `cor` (ou fora do vocabulário) cai no neutro de fallback. */
function statusColor(key: string, statusOptions: ConfigItem[]): string {
  return statusOptions.find((s) => s.key === key)?.cor || STATUS_DOT_FALLBACK;
}

// ===== Modal de REGISTRAR feedback do cliente (FeedbackItem manual) ==========
// O cliente é FIXO (a própria ficha): não pedimos cliente. Cobre tipo + sentimento
// + texto + data + status inicial + "já abordei". Cria via POST /api/feedbacks com
// o contato fixo. O backend cria o item já em 'a_abordar' (default do modelo) e NÃO
// aceita action_status no POST; se o operador escolher OUTRO status inicial, aplicamos
// via PATCH logo após (best-effort).

function RegistrarFeedbackModal({
  contactId,
  typeOptions,
  statusOptions,
  onClose,
  onAdded,
}: {
  contactId: string;
  typeOptions: ConfigItem[];
  statusOptions: ConfigItem[];
  onClose: () => void;
  /** Chamado após criar — o pai recarrega a ficha (a timeline re-ordena por data). */
  onAdded: () => void;
}) {
  const titleId = useId();
  // Default de tipo: primeiro do vocabulário (mantém "nota" no topo do fallback).
  const [type, setType] = useState(() => typeOptions[0]?.key ?? "nota");
  const [sentiment, setSentiment] = useState("");
  const [text, setText] = useState("");
  // datetime-local começa em "agora" (fuso local); o operador pode recuar a data.
  const [quando, setQuando] = useState(() => toLocalInputValue(new Date()));
  // Status inicial: começa em 'a_abordar' (= o que o backend cria por default). Se o
  // operador trocar, aplicamos via PATCH após o POST (ver `save`).
  const [status, setStatus] = useState<string>(
    () => statusOptions[0]?.key ?? "a_abordar",
  );
  const [abordado, setAbordado] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (saving || !text.trim()) return;
    setSaving(true);
    setError(null);
    // datetime-local é "horário de parede" sem fuso; new Date() o lê no fuso local
    // e toISOString() o manda em UTC — alinhado ao que o backend espera.
    const occurred = quando ? new Date(quando) : null;
    const body: FeedbackInput = {
      contato_id: contactId,
      type,
      text: text.trim() || null,
      source: "manual",
      sentiment: sentiment || null,
      occurred_at: occurred ? occurred.toISOString() : null,
      abordado,
    };
    try {
      const created = await feedbacksApi.create(body);
      // O POST não aceita action_status (nasce 'a_abordar'); se o operador pediu outro
      // status inicial, aplicamos num PATCH imediato — best-effort, não desfaz o
      // feedback já criado se falhar.
      if (status && status !== created.action_status) {
        try {
          await feedbacksApi.patch(created.id, { action_status: status as FeedbackStatus });
        } catch {
          /* status inicial é refinamento; o feedback já existe — segue. */
        }
      }
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title="Registrar feedback" onClose={onClose} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="form-row-2">
            <div className="field">
              <label htmlFor={`${titleId}-type`}>Tipo</label>
              <select id={`${titleId}-type`} value={type} onChange={(e) => setType(e.target.value)}>
                {withKey(typeOptions, type).map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
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
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-text`}>O que o cliente disse</label>
            <textarea
              id={`${titleId}-text`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ex.: ligou reclamando da cobrança; elogiou o suporte; pediu desconto…"
            />
          </div>

          <div className="form-row-2">
            <div className="field">
              <label htmlFor={`${titleId}-quando`}>Quando</label>
              <input
                id={`${titleId}-quando`}
                type="datetime-local"
                value={quando}
                max={toLocalInputValue(new Date())}
                onChange={(e) => setQuando(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor={`${titleId}-status`}>Status inicial</label>
              <div className="inline-flex items-center gap-2">
                {/* Swatch tingido pela COR do status escolhido (do /api/config) —
                    deixa a etapa "saltar aos olhos" já na criação. */}
                <span
                  aria-hidden
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: statusColor(status, statusOptions),
                  }}
                />
                <select
                  id={`${titleId}-status`}
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  style={{ flex: 1 }}
                >
                  {withCurrentStatus(statusOptions, status).map((s) => (
                    <option key={s.key} value={s.key}>{s.label}</option>
                  ))}
                </select>
              </div>
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
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving || !text.trim()}>
            {saving ? "Registrando…" : "Registrar feedback"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ===== Modal de CONFIRMAÇÃO de exclusão do contato ===========================

function DeleteContactModal({
  contactId,
  contactName,
  onClose,
  onDeleted,
}: {
  contactId: string;
  contactName: string;
  onClose: () => void;
  /** Chamado após DELETE 204 — o pai redireciona para /clientes. */
  onDeleted: () => void;
}) {
  const titleId = useId();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmar() {
    if (deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await contactsApi.remove(contactId);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  }

  return (
    <Modal title="Excluir contato" onClose={onClose} labelledById={titleId}>
      <div className="modal-body">
        <p style={{ margin: 0, lineHeight: 1.5 }}>
          Tem certeza que quer excluir <b>{contactName}</b>? Isso apaga o contato e
          <b> todo o histórico</b> (feedbacks, conversas, abordagens, selos) —{" "}
          <b>não dá para desfazer</b>.
        </p>
        {error && <div className="flash err" style={{ marginTop: 14, marginBottom: 0 }}>{error}</div>}
      </div>
      <div className="modal-foot">
        <Button type="button" variant="ghost" onClick={onClose} disabled={deleting}>
          Cancelar
        </Button>
        <button
          type="button"
          className="btn"
          onClick={confirmar}
          disabled={deleting}
          style={{
            background: "var(--detractor, #dc2626)",
            color: "#fff",
            borderColor: "transparent",
          }}
        >
          {deleting ? "Excluindo\u{2026}" : "Excluir definitivamente"}
        </button>
      </div>
    </Modal>
  );
}

// ===== Linha da timeline (editável quando é feedback_item) ===================

function TimelineRow({
  t,
  index,
  onPatch,
  onEdit,
  statusOptions,
}: {
  t: Timeline360Item;
  index: number;
  onPatch: (id: string, patch: FeedbackPatch) => Promise<void>;
  onEdit: (t: Timeline360Item) => void;
  statusOptions: ConfigItem[];
}) {
  const [busy, setBusy] = useState(false);
  const v = typeVisual(t.type);
  // Cor do ponto da trilha: prioriza o sentimento (neg/pos/neu); sem sentimento,
  // herda a cor do TIPO via estilo inline, para o marco "saltar aos olhos".
  const dotCls =
    t.sentiment === "negativo" ? "neg" : t.sentiment === "positivo" ? "pos" : t.sentiment === "neutro" ? "neu" : "";
  const dotStyle: React.CSSProperties = dotCls
    ? {}
    : { background: v.accent, boxShadow: `0 0 0 2px ${v.line}` };
  const editable = t.kind === "feedback_item" && !!t.id;
  const fu = followUpInfo(t.follow_up_at);

  async function run(patch: FeedbackPatch) {
    if (!t.id) return;
    setBusy(true);
    try {
      await onPatch(t.id, patch);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      className="tl-item reveal"
      style={{ paddingTop: 22, paddingBottom: 22, ["--i" as string]: Math.min(index, 12) } as React.CSSProperties}
    >
      <span className={`tl-dot ${dotCls}`} style={dotStyle} aria-hidden />
      <div className="tl-top" style={{ rowGap: 8 }}>
        <TypeMark type={t.type} />
        {t.score !== null && t.score !== undefined && (
          <span className={`score-pill ${t.bucket ?? "none"}`}>{t.score}</span>
        )}
        {sentimentBadge(t.sentiment)}
        {editable && t.incerto && (
          <button
            type="button"
            className="fb-incerto-chip"
            onClick={() => onEdit(t)}
            title={
              t.sentiment_sugerido
                ? `A IA não teve certeza (talvez "${t.sentiment_sugerido}"). Clique para revisar.`
                : "A IA classificou com baixa confiança. Clique para revisar."
            }
          >
            <Pencil size={11} aria-hidden /> incerto — revisar
          </button>
        )}
        {editable && statusBadge(t.action_status, statusOptions)}
        {t.abordado && (
          <Badge variant="positive">
            <Check size={11} strokeWidth={2.6} aria-hidden /> abordado
          </Badge>
        )}
        {editable && fu.agendado && (
          <span
            className={`fb-followup-pill${fu.vencido ? " is-overdue" : ""}`}
            title={fu.vencido ? `Follow-up vencido (era ${fu.label})` : `Reabordar em ${fu.label}`}
          >
            <CalendarClock size={12} aria-hidden />
            {fu.vencido ? `venceu ${fu.label}` : `reabordar ${fu.label}`}
          </span>
        )}
        {t.status === "ingested" && <Badge variant="neutral">do app</Badge>}
        <span className="tl-when" style={{ fontWeight: 500 }}>{fmtDate(t.at)}</span>
      </div>
      {t.text && (
        <div
          className="tl-text"
          style={{ marginTop: 12, paddingLeft: 11, borderLeft: `2px solid ${v.line}` }}
        >
          “{feedbackText(t.text)}”
        </div>
      )}
      {editable && t.action_note && (
        <div className="tl-note">
          <span className="tl-note-tag">nota do time</span>
          {/* Corrige um typo gravado em dados antigos ("repsposta") só na exibição. */}
          {t.action_note.replace(/repsposta/gi, "resposta")}
        </div>
      )}
      {themeChips(t.themes)}
      {t.editado_por && (
        <div className="tl-edited" title="Edição manual do feedback">
          editado por {t.editado_por}
          {t.editado_em ? ` · ${fmtDate(t.editado_em)}` : ""}
        </div>
      )}
      <div className="tl-src">
        via {SOURCE_LABEL[t.source] ?? t.source}
        {t.survey_name ? ` · ${t.survey_name}` : ""}
      </div>

      {editable && (
        <div className="tl-actions">
          <span className="act-label">Status</span>
          <select
            value={t.action_status ?? "a_abordar"}
            onChange={(e) => run({ action_status: e.target.value as FeedbackStatus })}
            disabled={busy}
            aria-label="Status da ação"
          >
            {withCurrentStatus(statusOptions, t.action_status ?? "a_abordar").map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
          <button
            type="button"
            className={`toggle-abordado ${t.abordado ? "on" : ""}`}
            onClick={() => run({ abordado: !t.abordado })}
            disabled={busy}
            aria-pressed={t.abordado}
            title={t.abordado ? "Marcar como não abordado" : "Marcar como abordado"}
          >
            {busy ? "…" : t.abordado ? (
              <>
                <Check size={13} strokeWidth={2.4} aria-hidden /> Abordado
              </>
            ) : (
              "Marcar abordado"
            )}
          </button>
          <ReabordarMenu
            current={t.follow_up_at}
            onSchedule={(iso) => run({ follow_up_at: iso })}
            onClear={() => run({ follow_up_at: null })}
            busy={busy}
          />
          <button
            type="button"
            className="icon-btn"
            onClick={() => onEdit(t)}
            title="Editar texto"
            aria-label="Editar texto"
          >
            <Pencil size={14} aria-hidden />
          </button>
        </div>
      )}
    </li>
  );
}

// ===== Marco de assinatura na timeline (renovação / fim de ciclo) ============
// Derivado de partner.subscription.currentPeriodEnd (data REAL do snapshot). Não é
// um feedback: não é editável e tem um visual próprio (ícone de ciclo, sem "via").

interface SubMarker {
  at: string;
  label: string;
  /** É futuro (renovação a vir) ou passado (ciclo encerrado)? muda o texto. */
  future: boolean;
}

/** Extrai o marco de assinatura do snapshot partner, ou null se não houver data. */
function subMarkerFromPartner(partner: Record<string, unknown> | null): SubMarker | null {
  if (!partner) return null;
  const sub = (partner.subscription as PartnerSub | undefined) ?? {};
  const end = sub.currentPeriodEnd;
  if (!end) return null;
  const future = new Date(end).getTime() > Date.now();
  const ativa = !!sub.active && !sub.cancelled;
  const label = ativa
    ? future ? "Renova em" : "Renovação venceu em"
    : future ? "Acesso até" : "Ciclo encerrado em";
  return { at: end, label, future };
}

function SubscriptionRow({ marker, index }: { marker: SubMarker; index: number }) {
  // Marco de assinatura: cor de marca (indigo), distinta dos feedbacks.
  const accent = "var(--indigo-light)";
  const soft = "var(--promoter-soft)";
  const line = "var(--promoter-line)";
  return (
    <li
      className="tl-item reveal"
      style={{ paddingTop: 22, paddingBottom: 22, ["--i" as string]: Math.min(index, 12) } as React.CSSProperties}
    >
      <span className="tl-dot" style={{ background: accent, boxShadow: `0 0 0 2px ${line}` }} aria-hidden />
      <div className="tl-top" style={{ rowGap: 8 }}>
        <span
          className="inline-flex items-center gap-1.5 rounded-[7px] border px-2.5 py-1 text-[12px] font-semibold leading-none"
          style={{ color: accent, background: soft, borderColor: line }}
        >
          <RefreshCw size={13} strokeWidth={2.2} aria-hidden />
          assinatura
        </span>
        <span className="tl-when" style={{ fontWeight: 500 }}>{fmtDate(marker.at)}</span>
      </div>
      <div
        className="tl-text"
        style={{ fontStyle: "normal", marginTop: 12, paddingLeft: 11, borderLeft: `2px solid ${line}` }}
      >
        {marker.label} {fmtDay(marker.at)}
      </div>
      <div className="tl-src">via API de Clientes</div>
    </li>
  );
}

// ===== Evento de SELO na timeline (histórico aplicado/removido) ===============
// kind='selo' do /360. READ-ONLY (não editável). Visual discreto: ponto neutro +
// chip com ícone Tag + frase humana a partir de acao+selo+origem+at. Ex.:
// Selo "respondeu" aplicado · resposta no WhatsApp · 20/06.

function SeloEventRow({ t, index }: { t: Timeline360Item; index: number }) {
  // Aplicado = tom de marca (indigo); removido = neutro/apagado.
  const removido = t.acao === "removido";
  const accent = removido ? "var(--text-faint)" : "var(--indigo-light)";
  const soft = removido ? "rgba(86, 84, 107, 0.08)" : "var(--promoter-soft)";
  const line = removido ? "var(--charcoal-2)" : "var(--promoter-line)";
  const origem = seloOrigemLabel(t.origem);
  const acaoTxt = removido ? "removido" : "aplicado";
  return (
    <li
      className="tl-item reveal"
      style={{ paddingTop: 22, paddingBottom: 22, ["--i" as string]: Math.min(index, 12) } as React.CSSProperties}
    >
      <span className="tl-dot" style={{ background: accent, boxShadow: `0 0 0 2px ${line}` }} aria-hidden />
      <div className="tl-top" style={{ rowGap: 8 }}>
        <span
          className="inline-flex items-center gap-1.5 rounded-[7px] border px-2.5 py-1 text-[12px] font-semibold leading-none"
          style={{ color: accent, background: soft, borderColor: line }}
        >
          <Tag size={13} strokeWidth={2.2} aria-hidden />
          selo
        </span>
        <span className="tl-when" style={{ fontWeight: 500 }}>{fmtDate(t.at)}</span>
      </div>
      <div className="tl-text" style={{ fontStyle: "normal", marginTop: 12, paddingLeft: 11, borderLeft: `2px solid ${line}` }}>
        Selo <b>“{t.selo ?? "—"}”</b> {acaoTxt}
        {origem ? <span className="faint"> · {origem}</span> : null}
        {t.por ? <span className="faint"> · por {t.por}</span> : null}
      </div>
    </li>
  );
}

// ===== Enviar WhatsApp 1:1 (gated por confirmação; preview por padrão) =======

function EnviarWhatsapp({
  contactId,
  onSent,
}: {
  contactId: string;
  /** Chamado após um ENVIO confirmado — recarrega a ficha (selo/abordagem novos). */
  onSent: () => void;
}) {
  const fieldId = useId();
  const [texto, setTexto] = useState("");
  const [oferta, setOferta] = useState("");
  const [por, setPor] = useState("");
  const [preview, setPreview] = useState<WhatsappSendPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  // Qualquer edição invalida um preview antigo (evita "Enviar de verdade" sobre
  // texto que mudou depois do preview).
  function onChange<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPreview(null);
      setOkMsg(null);
    };
  }

  const body = {
    texto,
    oferta: oferta.trim() || undefined,
    por: por.trim() || undefined,
  };

  async function preVisualizar() {
    if (busy || !texto.trim()) return;
    setBusy(true);
    setError(null);
    setOkMsg(null);
    try {
      setPreview(await whatsappApi.sendPreview(contactId, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function enviarDeVerdade() {
    if (busy || !podeEnviar) return;
    setBusy(true);
    setError(null);
    setOkMsg(null);
    try {
      const out = await whatsappApi.sendConfirm(contactId, body);
      // \u{2705} = check verde
      setOkMsg(`\u{2705} Enviado para ${out.para}.`);
      setPreview(null);
      setTexto("");
      setOferta("");
      setPor("");
      onSent(); // recarrega a ficha (novo selo 'contatado' + abordagem)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // Botão "Enviar de verdade" só habilita com preview feito, WAHA conectado E
  // contato ALCANÇÁVEL (celular válido OU já mandou mensagem; grupo nunca).
  const podeEnviar = !!preview && preview.waha_conectado && preview.alcancavel;

  return (
    <section>
      <div className="card-head" style={{ borderBottom: "none", paddingBottom: 0 }}>
        <div>
          <div className="section-title inline-flex items-center gap-2" style={{ fontSize: 14.5 }}>
            <MessageCircle size={16} aria-hidden /> Enviar WhatsApp
          </div>
          <div className="card-head-sub">
            mensagem 1:1 — o envio real depende do WAHA conectado
          </div>
        </div>
      </div>

      <div className="px-[var(--pad-card-x)] pb-[var(--s-5)] pt-[var(--s-4)]">
      <div className="field">
        <label htmlFor={`${fieldId}-texto`}>Mensagem</label>
        <textarea
          id={`${fieldId}-texto`}
          value={texto}
          onChange={(e) => onChange(setTexto)(e.target.value)}
          placeholder="Olá! Tudo bem? Vi que você…"
          maxLength={4000}
        />
      </div>
      <div className="wa-send-row">
        <div className="field">
          <label htmlFor={`${fieldId}-oferta`}>Oferta (opcional)</label>
          <input
            id={`${fieldId}-oferta`}
            value={oferta}
            onChange={(e) => onChange(setOferta)(e.target.value)}
            placeholder="ex.: 3 meses grátis"
            maxLength={200}
          />
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-por`}>Por (opcional)</label>
          <input
            id={`${fieldId}-por`}
            value={por}
            onChange={(e) => onChange(setPor)(e.target.value)}
            placeholder="seu nome"
            maxLength={120}
          />
        </div>
      </div>

      <div className="wa-send-actions">
        <Button
          type="button"
          variant="ghost"
          onClick={preVisualizar}
          disabled={busy || !texto.trim()}
        >
          {busy && !okMsg ? "Verificando\u{2026}" : "Pré-visualizar"}
        </Button>
        <button
          type="button"
          className="btn btn-wa"
          onClick={enviarDeVerdade}
          disabled={busy || !podeEnviar}
          title={
            !preview
              ? "Pré-visualize primeiro"
              : !preview.waha_conectado
                ? "WAHA desligado — só preview por enquanto"
                : !preview.alcancavel
                  ? (preview.is_grupo ? "Grupos não recebem mensagem 1:1" : "Contato não está no WhatsApp")
                  : "Enviar a mensagem de verdade"
          }
        >
          Enviar de verdade
        </button>
      </div>

      {preview && (
        <div className="wa-preview">
          <div className="wa-preview-head">
            <span className="lbl inline-flex items-center gap-1.5">
              <Search size={13} aria-hidden /> Pré-visualização (nada foi enviado)
            </span>
          </div>
          <div className="wa-preview-body">
            <div className="wa-preview-to">
              Para <span className="mono">{preview.para || "\u{2014}"}</span>
            </div>
            <div className="wa-preview-msg">{"“"}{preview.texto}{"”"}</div>
          </div>
          <div className="wa-preview-gates">
            <Badge variant={preview.waha_conectado ? "positive" : "neutral"}>
              {preview.waha_conectado ? (
                <><Check size={11} strokeWidth={2.6} aria-hidden /> WAHA conectado</>
              ) : (
                <><WifiOff size={11} aria-hidden /> WAHA desligado</>
              )}
            </Badge>
            <Badge variant={preview.alcancavel ? "positive" : preview.is_grupo ? "neutral" : "negative"}>
              {preview.alcancavel ? (
                <><Check size={11} strokeWidth={2.6} aria-hidden /> alcançável</>
              ) : preview.is_grupo ? (
                <><Users size={11} aria-hidden /> grupo (sem 1:1)</>
              ) : (
                <><Mail size={11} aria-hidden /> sem WhatsApp</>
              )}
            </Badge>
          </div>
          {!podeEnviar && (
            <div className="wa-preview-note">
              {!preview.waha_conectado
                ? "O WAHA está desligado agora — o botão de envio fica bloqueado. Ligue a sessão do WhatsApp para enviar de verdade."
                : preview.is_grupo
                  ? "Isto é um grupo/comunidade — não dá para enviar mensagem 1:1."
                  : "Este contato não está no WhatsApp — não dá para enviar."}
            </div>
          )}
        </div>
      )}

      {okMsg && <div className="flash ok" style={{ marginTop: 14, marginBottom: 0 }}>{okMsg}</div>}
      {error && <div className="flash err" style={{ marginTop: 14, marginBottom: 0 }}>{error}</div>}
      </div>
    </section>
  );
}

// ===== Conversa no WhatsApp (histórico real da thread, só leitura) ===========

function ConversaWhatsapp({ contactId }: { contactId: string }) {
  const [thread, setThread] = useState<WhatsappThread | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    whatsappApi
      .thread(contactId)
      .then((t) => {
        if (alive) setThread(t);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [contactId]);

  // Rola para a última mensagem (mais recente) quando a thread carrega.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread]);

  const mensagens = thread?.mensagens ?? [];

  return (
    <section className="border-t border-[var(--charcoal)]">
      <div className="card-head" style={{ borderBottom: "none" }}>
        <div>
          <div className="section-title inline-flex items-center gap-2" style={{ fontSize: 14.5 }}>
            <Phone size={16} aria-hidden /> Conversa no WhatsApp
          </div>
          <div className="card-head-sub">histórico real das mensagens trocadas com este cliente</div>
        </div>
        {thread && mensagens.length > 0 && (
          <span className="exit-counter">
            {mensagens.length} {mensagens.length === 1 ? "mensagem" : "mensagens"}
          </span>
        )}
      </div>

      {loading && (
        <div style={{ padding: "16px 20px" }} aria-busy aria-hidden>
          {[72, 58, 80].map((w, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: i % 2 ? "flex-end" : "flex-start",
                marginBottom: 12,
              }}
            >
              <div className="sk-card" style={{ width: `${w}%`, height: 40, borderRadius: 14 }} />
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="empty">
          <div className="empty-illu">{EMPTY_CHAT_OFF}</div>
          <div className="empty-title">Não consegui carregar a conversa</div>
          <p className="empty-sub">{error}</p>
        </div>
      )}

      {!loading && !error && mensagens.length === 0 && (
        <div className="empty">
          <div className="empty-illu">{EMPTY_CHAT}</div>
          <div className="empty-title">Nenhuma mensagem ainda</div>
          <p className="empty-sub">Quando vocês conversarem no WhatsApp, o histórico aparece aqui.</p>
        </div>
      )}

      {!loading && !error && mensagens.length > 0 && (
        <div
          className="chat-thread"
          ref={threadRef}
          style={{ maxHeight: 360, borderRadius: "var(--radius-sm)" }}
        >
          {mensagens.map((m) => (
            <div key={m.id} className={`chat-bubble ${m.direction}`}>
              <div className="chat-bubble-body">{m.body}</div>
              <div className="chat-bubble-time">{fmtDate(m.at)}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ===== Seção de WhatsApp recolhível (envio + conversa) =======================
// Enquanto o WAHA está FORA, envio e conversa não funcionam — então esta seção
// vem RECOLHIDA por padrão, num bloco discreto que não rouba espaço da linha do
// tempo (o foco do registro manual). O operador expande quando quiser; e quando o
// WAHA voltar é só abrir e usar normalmente. NÃO removemos nada — só re-priorizamos.

function WhatsappSection({
  contactId,
  onSent,
}: {
  contactId: string;
  onSent: () => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <Reveal delay={0.08} className="card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center gap-3 px-[var(--pad-card-x)] py-[var(--s-4)] text-left transition-colors hover:bg-[var(--ink-800)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--indigo)]"
      >
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-[calc(var(--radius-sm)-3px)] text-[var(--text-faint)]"
          style={{ background: "color-mix(in srgb, var(--text-faint) 12%, transparent)" }}
          aria-hidden
        >
          <MessageCircle size={17} aria-hidden />
        </span>
        <span className="flex flex-col gap-0.5">
          <span className="section-title" style={{ margin: 0 }}>Enviar WhatsApp &amp; conversa</span>
          <span className="inline-flex items-center text-[12.5px] font-medium text-[var(--text-faint)]">
            <WifiOff size={12} aria-hidden style={{ verticalAlign: "-1px", marginRight: 5 }} />
            indisponível — WhatsApp desconectado
          </span>
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-[var(--indigo-light)]">
          {open ? "ocultar" : "mostrar"}
          <ChevronDown
            size={17}
            aria-hidden
            className="transition-transform duration-150"
            style={{ transform: open ? "rotate(180deg)" : "none" }}
          />
        </span>
      </button>

      {open && (
        <div id={panelId} className="border-t border-[var(--charcoal)]">
          <EnviarWhatsapp contactId={contactId} onSent={onSent} />
          <ConversaWhatsapp contactId={contactId} />
        </div>
      )}
    </Reveal>
  );
}

export default function Contact360Page() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;
  const [data, setData] = useState<Contact360 | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<Timeline360Item | null>(null);
  const [addingEvent, setAddingEvent] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Vocabulários efetivos da org (defaults + custom) p/ os dropdowns da timeline e
  // do modal de registro. Iniciam nos fallbacks; trocam quando GET /api/config chega.
  // Falha = segue nos fallbacks.
  const [statusOptions, setStatusOptions] = useState<ConfigItem[]>(STATUS_OPTIONS_FALLBACK);
  const [typeOptions, setTypeOptions] = useState<ConfigItem[]>(TYPE_OPTIONS_FALLBACK);

  useEffect(() => {
    let alive = true;
    configApi
      .get()
      .then((cfg) => {
        if (!alive) return;
        if (cfg.action_statuses?.length) setStatusOptions(cfg.action_statuses);
        if (cfg.feedback_types?.length) setTypeOptions(cfg.feedback_types);
      })
      .catch(() => {
        /* sem config (API antiga / offline): mantém os fallbacks. */
      });
    return () => {
      alive = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setData(await api.get<Contact360>(`/api/contacts/${id}/360`));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // PATCH de um item da timeline; atualiza o estado local sem recarregar tudo.
  const patchItem = useCallback(async (itemId: string, patch: FeedbackPatch) => {
    const updated = await api.patch<Feedback>(`/api/feedbacks/${itemId}`, patch);
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        timeline: prev.timeline.map((t) =>
          t.id === itemId
            ? {
                ...t,
                action_status: updated.action_status,
                abordado: updated.abordado,
                text: updated.text,
                sentiment: updated.sentiment,
                themes: updated.themes,
                score: updated.score,
                bucket: updated.nps_bucket,
                follow_up_at: updated.follow_up_at,
                editado_por: updated.editado_por,
                editado_em: updated.editado_em,
              }
            : t,
        ),
      };
    });
  }, []);

  const onItemEdited = useCallback(
    (itemId: string, patch: { text: string | null; action_note: string | null }) => {
      setData((prev) =>
        prev
          ? { ...prev, timeline: prev.timeline.map((t) => (t.id === itemId ? { ...t, ...patch } : t)) }
          : prev,
      );
      setEditingItem(null);
    },
    [],
  );

  // Após criar um evento manual: fecha o modal e recarrega a ficha (a timeline
  // re-ordena por data e o resumo/contagens batem com o backend).
  const onEventAdded = useCallback(() => {
    setAddingEvent(false);
    load();
  }, [load]);

  const onSelosChanged = useCallback((selos: string[]) => {
    setData((prev) => (prev ? { ...prev, contact: { ...prev.contact, selos } } : prev));
  }, []);

  const selos = data?.contact.selos ?? [];
  const selosVivos = data?.contact.selos_vivos ?? [];
  const semWhatsapp = data?.contact.sem_whatsapp ?? false;
  // Marco de assinatura (renovação / fim de ciclo) derivado do snapshot partner —
  // entra na timeline na posição cronológica certa (timeline vem desc do backend).
  const subMarker = subMarkerFromPartner(data?.partner ?? null);

  return (
    <div>
      <Reveal className="page-head">
        <div className="c360-head">
          <Link href="/clientes" className="back-link inline-flex items-center gap-1.5">
            <ArrowLeft size={15} aria-hidden /> Clientes
          </Link>
          <div className="c360-head-row">
            <Avatar name={data?.contact.name} seed={id} size={52} />
            <div>
              <h1 className="page-title">{data?.contact.name || data?.contact.phone || "Cliente"}</h1>
              {data && (
                <div className="page-sub inline-flex items-center gap-2 flex-wrap">
                  <span className="mono">{data.contact.phone}</span>
                  <span aria-hidden>·</span>
                  {data.contact.opt_in ? (
                    <span className="inline-flex items-center gap-1">
                      opt-in <Check size={13} strokeWidth={2.4} aria-hidden style={{ color: "var(--indigo-light)" }} />
                    </span>
                  ) : (
                    "sem opt-in"
                  )}
                  {semWhatsapp && (
                    <Badge variant="neutral" title="Sem WhatsApp — universo só e-mail">
                      <Mail size={11} aria-hidden /> sem WhatsApp
                    </Badge>
                  )}
                </div>
              )}
              {data && id && (
                <div className="c360-selos-row">
                  <ContatoSelos
                    contactId={id}
                    selos={selos}
                    selosVivos={selosVivos}
                    onChanged={onSelosChanged}
                    onApplied={load}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
        {data && (
          <div className="inline-flex items-center gap-3">
            <span className="refresh-note">{data.summary.total} interações</span>
            {id && (
              <button
                type="button"
                onClick={() => setDeleting(true)}
                title="Excluir contato e todo o histórico"
                aria-label="Excluir contato"
                className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-transparent px-2 py-1 text-[12.5px] font-medium text-[var(--text-faint)] transition-colors hover:border-[var(--charcoal-2)] hover:text-[var(--detractor,#dc2626)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--detractor,#dc2626)]"
              >
                <Trash2 size={14} aria-hidden /> Excluir
              </button>
            )}
          </div>
        )}
      </Reveal>

      {err && (
        <div className="flash err">
          Não consegui carregar a ficha ({err}). A API está rodando em <span className="mono">localhost:8000</span>?
        </div>
      )}

      {!err && !data && <Skeleton360 />}

      {data && (
        <div className="c360-body">
          {data.partner && <ProfileCard partner={data.partner} />}

          {/* ACOMPANHAMENTO — o coração da ficha (onde se registra e acompanha o
             cliente). Vem logo após o perfil e com destaque visual próprio:
             filete indigo à esquerda + título maior. */}
          <Reveal
            delay={0.1}
            className="card overflow-hidden"
            style={{ borderLeft: "3px solid var(--indigo)" }}
          >
            <div className="card-head">
              <div>
                <div className="section-title" style={{ fontSize: 18 }}>Acompanhamento do cliente</div>
                <div className="card-head-sub">
                  Tudo que aconteceu com este cliente — registre aqui cada conversa, nota e próximo passo.
                </div>
              </div>
              <div className="tl-head-actions">
                <span className="exit-counter">
                  {data.summary.feedback_items} sinais · {data.summary.survey_responses} pesquisas
                </span>
                {id && (
                  <Button type="button" onClick={() => setAddingEvent(true)}>
                    <Plus size={15} strokeWidth={2.4} aria-hidden /> Registrar feedback
                  </Button>
                )}
              </div>
            </div>
            {data.timeline.length === 0 && !subMarker ? (
              <div className="empty">
                <div className="empty-illu">{EMPTY_TIMELINE}</div>
                <div className="empty-title">Sem feedback ainda</div>
                <p className="empty-sub">
                  Quando este cliente responder a uma pesquisa ou falar com vocês, tudo aparece aqui —
                  ou registre você mesmo um evento à mão.
                </p>
                {id && (
                  <div className="empty-cta">
                    <Button type="button" size="sm" onClick={() => setAddingEvent(true)}>
                      <Plus size={14} strokeWidth={2.2} aria-hidden /> Registrar feedback
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <ul className="tl">
                {/* Funde feedbacks + marco de assinatura por data (desc, mais recente primeiro). */}
                {(() => {
                  type Entry =
                    | { kind: "fb"; key: string; ts: number; item: Timeline360Item }
                    | { kind: "selo"; key: string; ts: number; item: Timeline360Item }
                    | { kind: "sub"; key: string; ts: number; marker: SubMarker };
                  // Eventos de selo (kind='selo') viram entradas próprias (read-only);
                  // os demais (feedback_item/survey) seguem como 'fb' editável.
                  const entries: Entry[] = data.timeline.map((t, i) => ({
                    kind: t.kind === "selo" ? "selo" : "fb",
                    key: t.kind === "selo" ? `selo-${i}` : t.id ?? `fb-${i}`,
                    ts: t.at ? new Date(t.at).getTime() : 0,
                    item: t,
                  }));
                  if (subMarker) {
                    entries.push({
                      kind: "sub",
                      key: "sub-marker",
                      ts: new Date(subMarker.at).getTime(),
                      marker: subMarker,
                    });
                  }
                  entries.sort((a, b) => b.ts - a.ts);
                  return entries.map((e, i) =>
                    e.kind === "sub" ? (
                      <SubscriptionRow key={e.key} marker={e.marker} index={i} />
                    ) : e.kind === "selo" ? (
                      <SeloEventRow key={e.key} t={e.item} index={i} />
                    ) : (
                      <TimelineRow
                        key={e.key}
                        t={e.item}
                        index={i}
                        onPatch={patchItem}
                        onEdit={setEditingItem}
                        statusOptions={statusOptions}
                      />
                    ),
                  );
                })()}
              </ul>
            )}
          </Reveal>

          {/* WhatsApp recolhido no rodapé — envio + conversa, ambos dependem do
             WAHA (fora agora). Re-priorizado para não competir com a timeline. */}
          {id && <WhatsappSection contactId={id} onSent={load} />}
        </div>
      )}

      {editingItem && (
        <EditItemModal
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onSaved={onItemEdited}
        />
      )}

      {addingEvent && id && (
        <RegistrarFeedbackModal
          contactId={id}
          typeOptions={typeOptions}
          statusOptions={statusOptions}
          onClose={() => setAddingEvent(false)}
          onAdded={onEventAdded}
        />
      )}

      {deleting && id && (
        <DeleteContactModal
          contactId={id}
          contactName={data?.contact.name || data?.contact.phone || "este contato"}
          onClose={() => setDeleting(false)}
          onDeleted={() => router.push("/clientes")}
        />
      )}
    </div>
  );
}
