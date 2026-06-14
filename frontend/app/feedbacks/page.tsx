"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import ConfirmDialog from "@/components/ConfirmDialog";
import AbordarModal, { waIcon } from "@/components/AbordarModal";
import {
  api,
  type Cliente,
  type Feedback,
  type FeedbackCounts,
  type FeedbackInput,
  type FeedbackPatch,
  type FeedbackStatus,
  type FeedbacksResponse,
} from "@/lib/api";

const PAGE_SIZE = 25;

const STATUS_TABS: { key: FeedbackStatus; label: string }[] = [
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

const EMPTY_COUNTS: FeedbackCounts = {
  novo: 0, em_analise: 0, planejado: 0, resolvido: 0, descartado: 0,
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

/** Tipos oferecidos ao criar/editar feedback (ordem do menu). */
const TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "nps", label: "NPS" },
  { value: "churn", label: "Cancelamento" },
  { value: "elogio", label: "Elogio" },
  { value: "sugestao", label: "Sugestão" },
  { value: "bug", label: "Bug" },
  { value: "outro", label: "Outro" },
];

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

const SENT_META: Record<string, { cls: string; label: string }> = {
  positivo: { cls: "s-pos", label: "positivo" },
  neutro: { cls: "s-neu", label: "neutro" },
  negativo: { cls: "s-neg", label: "negativo" },
};

function typeBadge(type: string) {
  const label = TYPE_LABEL[type] ?? type;
  const cls = type === "churn" || type === "exit" ? "t-exit" : "t-nps";
  return <span className={`badge type ${cls}`}>{label}</span>;
}

function sentimentBadge(s: string | null) {
  if (!s) return null;
  const m = SENT_META[s];
  if (!m) return null;
  return <span className={`badge sent ${m.cls}`}>{m.label}</span>;
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

// ===== Modal de edição (PATCH de text/type/score/sentiment/themes) ==========

function EditFeedbackModal({
  feedback,
  onCancel,
  onSaved,
}: {
  feedback: Feedback;
  onCancel: () => void;
  onSaved: (updated: Feedback) => void;
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
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
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
          <button type="button" className="btn ghost" onClick={onCancel} disabled={saving}>
            Cancelar
          </button>
          <button type="submit" className="btn" disabled={saving}>
            {saving ? "Salvando…" : "Salvar alterações"}
          </button>
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
}: {
  onCancel: () => void;
  onCreated: (created: Feedback) => void;
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
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
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
          <button type="button" className="btn ghost" onClick={onCancel} disabled={saving}>
            Cancelar
          </button>
          <button type="submit" className="btn" disabled={saving}>
            {saving ? "Criando…" : "Criar feedback"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ===== Card de um feedback ==================================================

function FeedbackCard({
  fb,
  onPatched,
  onEdit,
  onDelete,
  onAbordar,
}: {
  fb: Feedback;
  onPatched: (updated: Feedback, previousStatus: FeedbackStatus) => void;
  onEdit: (fb: Feedback) => void;
  onDelete: (fb: Feedback) => void;
  onAbordar: (fb: Feedback) => void;
}) {
  const [note, setNote] = useState(fb.action_note ?? "");
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [abordadoSaving, setAbordadoSaving] = useState(false);

  // Mantém o input de nota em sincronia quando o card é reconciliado de fora
  // (ex.: edição via modal) sem pisar no que o usuário está digitando.
  useEffect(() => {
    if (!saving) setNote(fb.action_note ?? "");
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

  function onStatusChange(e: React.ChangeEvent<HTMLSelectElement>) {
    patch({ action_status: e.target.value as FeedbackStatus });
  }

  function commitNote() {
    const trimmed = note.trim();
    if (trimmed === (fb.action_note ?? "").trim()) return;
    patch({ action_note: trimmed });
  }

  return (
    <div className={`card fb-card ${fb.abordado ? "is-abordado" : ""}`}>
      <div className="fb-top">
        <Avatar name={fb.contato_nome} seed={fb.contato_id ?? fb.contato_whatsapp} size={30} />
        {fb.urgencia >= 70 && (
          <span className="badge detractor" title={`Urgência ${fb.urgencia}/100`}>🔥 urgente</span>
        )}
        {fb.contato_id ? (
          <Link href={`/contatos/${fb.contato_id}`} className="fb-who">
            {fb.contato_nome || "sem nome"}
          </Link>
        ) : (
          <span className="fb-who">{fb.contato_nome || "sem contato"}</span>
        )}
        <span className="mono dim fb-phone">{fb.contato_whatsapp}</span>
        {typeBadge(fb.type)}
        <span className="dim" style={{ fontSize: 12 }}>
          via {SOURCE_LABEL[fb.source] ?? fb.source}
        </span>
        {fb.score !== null && fb.score !== undefined && (
          <span className={`score-pill ${fb.nps_bucket ?? bucketFor(fb.score)}`}>{fb.score}</span>
        )}
        {sentimentBadge(fb.sentiment)}
        {fb.abordado && (
          <span className="badge abordado" title={fb.abordado_em ? `Abordado em ${fmtDate(fb.abordado_em)}` : "Abordado"}>
            ✅ abordado
          </span>
        )}
        <span className="fb-when">{fmtDate(fb.occurred_em ?? fb.created_em)}</span>
      </div>

      {fb.text ? (
        <div className="fb-text">“{fb.text}”</div>
      ) : (
        <div className="fb-text empty-text">sem texto — só a nota</div>
      )}
      {themeChips(fb.themes)}

      <div className="fb-actions">
        <span className="act-label">Status</span>
        <select value={fb.action_status} onChange={onStatusChange} disabled={saving}>
          {STATUS_TABS.map((s) => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>
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

        <div className="fb-card-tools">
          <button
            type="button"
            className="btn-wa-sm"
            onClick={() => onAbordar(fb)}
            disabled={!fb.contato_whatsapp}
            title="Abordar no WhatsApp"
          >
            {waIcon} WhatsApp
          </button>
          <button
            type="button"
            className={`toggle-abordado ${fb.abordado ? "on" : ""}`}
            onClick={toggleAbordado}
            disabled={abordadoSaving}
            aria-pressed={fb.abordado}
            title={fb.abordado ? "Marcar como não abordado" : "Marcar como abordado"}
          >
            {abordadoSaving ? "…" : fb.abordado ? "✅ Abordado" : "Marcar abordado"}
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={() => onEdit(fb)}
            title="Editar feedback"
            aria-label="Editar feedback"
          >
            ✏️
          </button>
          <button
            type="button"
            className="icon-btn danger"
            onClick={() => onDelete(fb)}
            title="Excluir feedback"
            aria-label="Excluir feedback"
          >
            🗑️
          </button>
        </div>

        {saving && <span className="dim" style={{ fontSize: 12 }}>salvando…</span>}
        {justSaved && !saving && <span className="act-saved">✓ salvo</span>}
        {error && <span className="badge detractor" title={error}>erro ao salvar</span>}
      </div>
    </div>
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

  // filtros
  const [status, setStatus] = useState<FeedbackStatus | "">("");
  const [type, setType] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [abordado, setAbordado] = useState<"" | "sim" | "nao">("");
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

  // overlays (criar / editar / excluir)
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Feedback | null>(null);
  const [deleting, setDeleting] = useState<Feedback | null>(null);
  const [abordando, setAbordando] = useState<Feedback | null>(null);

  const offsetRef = useRef(0);

  const buildQs = useCallback(
    (offset: number) => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      if (type) qs.set("type", type);
      if (sentiment) qs.set("sentiment", sentiment);
      if (source) qs.set("source", source);
      if (search.trim()) qs.set("search", search.trim());
      if (abordado) qs.set("abordado", abordado === "sim" ? "true" : "false");
      // Deep-links da tela Temas: cluster de dores e tema exato (filtro JSONB).
      if (clusterId) qs.set("cluster_id", clusterId);
      if (theme) qs.set("theme", theme);
      qs.set("limit", String(PAGE_SIZE));
      qs.set("offset", String(offset));
      return qs.toString();
    },
    [status, type, sentiment, source, search, abordado, clusterId, theme],
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
  const hasFilters = !!(type || sentiment || source || search || abordado || clusterId || theme);

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
          <button type="button" className="btn" onClick={() => setCreating(true)}>
            <span aria-hidden>＋</span> Novo feedback
          </button>
        </div>
      </div>

      {/* Abas por status, com contagens de counts_by_status */}
      <div className="status-tabs">
        <button
          className={`status-tab ${status === "" ? "active" : ""}`}
          onClick={() => setStatus("")}
        >
          Todos
        </button>
        {STATUS_TABS.map((s) => (
          <button
            key={s.key}
            className={`status-tab ${status === s.key ? "active" : ""}`}
            onClick={() => setStatus(s.key)}
          >
            {s.label}
            <span className="tab-count">{counts[s.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {/* Filtros adicionais */}
      <div className="toolbar">
        <label className="search">
          <span className="ico">🔍</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar no texto, nome ou WhatsApp…"
          />
        </label>
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Filtrar por tipo">
          <option value="">Todos os tipos</option>
          <option value="nps">NPS</option>
          <option value="churn">Cancelamento</option>
        </select>
        <select
          value={sentiment}
          onChange={(e) => setSentiment(e.target.value)}
          aria-label="Filtrar por sentimento"
        >
          <option value="">Todo sentimento</option>
          <option value="positivo">Positivo</option>
          <option value="neutro">Neutro</option>
          <option value="negativo">Negativo</option>
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Filtrar por origem">
          <option value="">Toda origem</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="bizzu_app">App Bizzu</option>
          <option value="bizzu_billing">Cobrança</option>
          <option value="bizzu_support">Suporte</option>
        </select>
        <select
          value={abordado}
          onChange={(e) => setAbordado(e.target.value as "" | "sim" | "nao")}
          aria-label="Filtrar por abordado"
        >
          <option value="">Abordado: todos</option>
          <option value="nao">Não abordados</option>
          <option value="sim">Já abordados</option>
        </select>
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

      {!err && visible.length === 0 ? (
        <div className="card">
          <div className="empty">
            <div className="big">📭</div>
            {loading
              ? "Carregando…"
              : status
              ? `Nenhum feedback em "${STATUS_LABEL[status]}".`
              : hasFilters
              ? "Nenhum feedback bate com os filtros."
              : "Nenhum feedback ainda."}
            {!loading && !status && !hasFilters && (
              <div className="empty-cta">
                <button type="button" className="btn" onClick={() => setCreating(true)}>
                  <span aria-hidden>＋</span> Adicionar o primeiro
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="feed">
          {visible.map((fb) => (
            <FeedbackCard
              key={fb.id}
              fb={fb}
              onPatched={onPatched}
              onEdit={setEditing}
              onDelete={setDeleting}
              onAbordar={setAbordando}
            />
          ))}
        </div>
      )}

      {hasMore && !status && (
        <div className="load-more">
          <button className="btn ghost" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Carregando…" : "Carregar mais"}
          </button>
        </div>
      )}

      {creating && (
        <CreateFeedbackModal
          onCancel={() => setCreating(false)}
          onCreated={onCreated}
        />
      )}
      {editing && (
        <EditFeedbackModal
          feedback={editing}
          onCancel={() => setEditing(null)}
          onSaved={onEdited}
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
          quote={deleting.text}
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
