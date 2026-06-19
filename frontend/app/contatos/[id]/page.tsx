"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Check,
  Mail,
  MessageCircle,
  Phone,
  Search,
  Pencil,
  Plus,
  X,
  Users,
  WifiOff,
} from "lucide-react";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  api,
  campanha as campanhaApi,
  whatsapp as whatsappApi,
  type Contact360,
  type Feedback,
  type FeedbackPatch,
  type FeedbackStatus,
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
  outro: "Outro",
};

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

const STATUS_OPTIONS: { key: FeedbackStatus; label: string }[] = [
  { key: "novo", label: "Novo" },
  { key: "em_analise", label: "Em análise" },
  { key: "planejado", label: "Planejado" },
  { key: "resolvido", label: "Resolvido" },
  { key: "descartado", label: "Descartado" },
];

/** Selos de campanha win-back sugeridos no controle do cabeçalho. */
const SELOS_CAMPANHA = ["contatado", "respondeu", "cortesia", "reativou"];

function typeBadge(type: string) {
  const label = TYPE_LABEL[type] ?? type;
  const cls = type === "churn" || type === "exit" ? "t-exit" : type === "nps" || type === "csat" ? "t-nps" : "";
  return <span className={`badge type ${cls}`}>{label}</span>;
}

function sentimentBadge(s?: string | null) {
  if (!s) return null;
  const m = SENT_META[s];
  if (!m) return null;
  return <span className={`badge sent ${m.cls}`}>{m.label}</span>;
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

function ProfileCard({ partner }: { partner: Record<string, unknown> }) {
  const sub = (partner.subscription as Record<string, unknown> | undefined) ?? {};
  const nps = (partner.nps as Record<string, unknown> | undefined) ?? {};
  return (
    <Reveal delay={0.04} className="card c360-profile">
      <div className="card-head">
        <div className="section-title">Perfil &amp; assinatura</div>
        <div className="card-head-sub">snapshot da API de Clientes</div>
      </div>
      <div className="c360-grid">
        {field("Perfil", partner.profile)}
        {field("Estado", sub.state)}
        {field("Plano", sub.planType)}
        {field("Dias de casa", sub.daysAsSubscriber)}
        {field("NPS (nota)", nps.score)}
        {field("Motivo de churn", sub.cancellationReason)}
      </div>
    </Reveal>
  );
}

// ===== Selos do contato (cabeçalho) =========================================

function ContatoSelos({
  contactId,
  selos,
  onChanged,
}: {
  contactId: string;
  selos: string[];
  onChanged: (selos: string[]) => void;
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
    <div className="c360-selos" ref={boxRef}>
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
      <button
        type="button"
        className="selo-add"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Aplicar selo de campanha"
        disabled={busy}
      >
        <Plus size={12} strokeWidth={2.2} aria-hidden /> selo
      </button>
      {open && (
        <div className="selo-pop">
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

// ===== Modal de edição de texto/nota de um item ==============================

function EditItemModal({
  item,
  onClose,
  onSaved,
}: {
  item: Timeline360Item;
  onClose: () => void;
  onSaved: (id: string, patch: { text: string | null }) => void;
}) {
  const titleId = useId();
  const [text, setText] = useState(item.text ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!item.id) return;
    setSaving(true);
    setError(null);
    const body: FeedbackPatch = { text: text.trim() || null };
    try {
      await api.patch<Feedback>(`/api/feedbacks/${item.id}`, body);
      onSaved(item.id, { text: text.trim() || null });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title="Editar feedback" onClose={onClose} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="field">
            <label htmlFor={`${titleId}-text`}>Texto</label>
            <textarea
              id={`${titleId}-text`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="O que o cliente disse…"
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

// ===== Linha da timeline (editável quando é feedback_item) ===================

function TimelineRow({
  t,
  index,
  onPatch,
  onEdit,
}: {
  t: Timeline360Item;
  index: number;
  onPatch: (id: string, patch: FeedbackPatch) => Promise<void>;
  onEdit: (t: Timeline360Item) => void;
}) {
  const [busy, setBusy] = useState(false);
  const dotCls =
    t.sentiment === "negativo" ? "neg" : t.sentiment === "positivo" ? "pos" : t.sentiment === "neutro" ? "neu" : "";
  const editable = t.kind === "feedback_item" && !!t.id;

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
      style={{ ["--i" as string]: Math.min(index, 12) } as React.CSSProperties}
    >
      <span className={`tl-dot ${dotCls}`} aria-hidden />
      <div className="tl-top">
        {typeBadge(t.type)}
        {t.score !== null && t.score !== undefined && (
          <span className={`score-pill ${t.bucket ?? "none"}`}>{t.score}</span>
        )}
        {sentimentBadge(t.sentiment)}
        {t.abordado && (
          <Badge variant="positive">
            <Check size={11} strokeWidth={2.6} aria-hidden /> abordado
          </Badge>
        )}
        {t.status === "ingested" && <Badge variant="neutral">do app</Badge>}
        <span className="tl-when">{fmtDate(t.at)}</span>
      </div>
      {t.text && <div className="tl-text">“{t.text}”</div>}
      {themeChips(t.themes)}
      <div className="tl-src">
        via {SOURCE_LABEL[t.source] ?? t.source}
        {t.survey_name ? ` · ${t.survey_name}` : ""}
      </div>

      {editable && (
        <div className="tl-actions">
          <span className="act-label">Status</span>
          <select
            value={t.action_status ?? "novo"}
            onChange={(e) => run({ action_status: e.target.value as FeedbackStatus })}
            disabled={busy}
            aria-label="Status da ação"
          >
            {STATUS_OPTIONS.map((s) => (
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
    <Reveal delay={0.08} className="card">
      <div className="card-head">
        <div>
          <div className="section-title inline-flex items-center gap-2">
            <MessageCircle size={17} aria-hidden /> Enviar WhatsApp
          </div>
          <div className="card-head-sub">
            mensagem 1:1 — o envio real depende do WAHA conectado
          </div>
        </div>
      </div>

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
    </Reveal>
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
    <Reveal delay={0.12} className="card">
      <div className="card-head">
        <div>
          <div className="section-title inline-flex items-center gap-2">
            <Phone size={17} aria-hidden /> Conversa no WhatsApp
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
    </Reveal>
  );
}

export default function Contact360Page() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [data, setData] = useState<Contact360 | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<Timeline360Item | null>(null);

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
              }
            : t,
        ),
      };
    });
  }, []);

  const onItemEdited = useCallback((itemId: string, patch: { text: string | null }) => {
    setData((prev) =>
      prev
        ? { ...prev, timeline: prev.timeline.map((t) => (t.id === itemId ? { ...t, ...patch } : t)) }
        : prev,
    );
    setEditingItem(null);
  }, []);

  const onSelosChanged = useCallback((selos: string[]) => {
    setData((prev) => (prev ? { ...prev, contact: { ...prev.contact, selos } } : prev));
  }, []);

  const selos = data?.contact.selos ?? [];
  const semWhatsapp = data?.contact.sem_whatsapp ?? false;

  return (
    <div>
      <Reveal className="page-head">
        <div className="c360-head">
          <Link href="/contatos" className="back-link inline-flex items-center gap-1.5">
            <ArrowLeft size={15} aria-hidden /> Contatos
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
                  <ContatoSelos contactId={id} selos={selos} onChanged={onSelosChanged} />
                </div>
              )}
            </div>
          </div>
        </div>
        {data && <span className="refresh-note">{data.summary.total} interações</span>}
      </Reveal>

      {err && (
        <div className="flash err">
          Não consegui carregar a ficha ({err}). A API está rodando em <span className="mono">localhost:8000</span>?
        </div>
      )}

      {!err && !data && <Skeleton360 />}

      {data && (
        <>
          {data.partner && <ProfileCard partner={data.partner} />}

          {id && <EnviarWhatsapp contactId={id} onSent={load} />}

          {id && <ConversaWhatsapp contactId={id} />}

          <Reveal delay={0.16} className="card">
            <div className="card-head">
              <div>
                <div className="section-title">Linha do tempo do cliente</div>
                <div className="card-head-sub">todas as fontes de feedback, unificadas e editáveis</div>
              </div>
              <span className="exit-counter">
                {data.summary.feedback_items} sinais · {data.summary.survey_responses} pesquisas
              </span>
            </div>
            {data.timeline.length === 0 ? (
              <div className="empty">
                <div className="empty-illu">{EMPTY_TIMELINE}</div>
                <div className="empty-title">Sem feedback ainda</div>
                <p className="empty-sub">
                  Quando este cliente responder a uma pesquisa ou falar com vocês, tudo aparece aqui.
                </p>
              </div>
            ) : (
              <ul className="tl">
                {data.timeline.map((t, i) => (
                  <TimelineRow
                    key={t.id ?? i}
                    t={t}
                    index={i}
                    onPatch={patchItem}
                    onEdit={setEditingItem}
                  />
                ))}
              </ul>
            )}
          </Reveal>
        </>
      )}

      {editingItem && (
        <EditItemModal
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onSaved={onItemEdited}
        />
      )}
    </div>
  );
}
