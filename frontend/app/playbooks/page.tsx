"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  api,
  type Playbook,
  type PlaybookAction,
  type PlaybookInput,
  type PlaybookTrigger,
} from "@/lib/api";

// ===== Metadados dos enums (rótulos + config condicional por gatilho) ========

const TRIGGERS: { value: PlaybookTrigger; label: string; hint: string }[] = [
  { value: "nps_detractor", label: "Detrator de NPS", hint: "nota de NPS ≤ limite" },
  { value: "health_at_risk", label: "Conta em risco (Health)", hint: "banda de saúde igual a" },
  { value: "inactive_days", label: "Inatividade", hint: "sem feedback há X dias" },
  { value: "renewal_soon", label: "Renovação próxima", hint: "renova em até X dias" },
  { value: "churn_detected", label: "Cancelamento detectado", hint: "novo sinal de churn" },
];

const TRIGGER_LABEL: Record<PlaybookTrigger, string> = {
  nps_detractor: "Detrator de NPS",
  health_at_risk: "Conta em risco",
  inactive_days: "Inatividade",
  renewal_soon: "Renovação próxima",
  churn_detected: "Cancelamento",
};

const ACTIONS: { value: PlaybookAction; label: string }[] = [
  { value: "create_task", label: "Criar tarefa de CS" },
  { value: "alert_owner", label: "Alertar o dono (WhatsApp)" },
];

const ACTION_LABEL: Record<PlaybookAction, string> = {
  create_task: "criar tarefa",
  alert_owner: "alertar dono",
};

const PRIORITIES = [
  { value: "baixa", label: "Baixa" },
  { value: "normal", label: "Normal" },
  { value: "alta", label: "Alta" },
  { value: "urgente", label: "Urgente" },
];

const HEALTH_BANDS = [
  { value: "at_risk", label: "Em risco" },
  { value: "watch", label: "Atenção" },
];

/** Resumo legível "gatilho → ação" do card da regra. */
function ruleSummary(p: Playbook): string {
  return `${TRIGGER_LABEL[p.trigger_type] ?? p.trigger_type} → ${ACTION_LABEL[p.action_type] ?? p.action_type}`;
}

/** Estado bruto do form (strings p/ os inputs; vira config tipada no submit). */
interface FormState {
  name: string;
  description: string;
  trigger_type: PlaybookTrigger;
  // configs por gatilho (só a relevante é usada)
  max_score: string;
  band: string;
  inactive_days: string;
  days_before: string;
  action_type: PlaybookAction;
  title: string;
  priority: string;
  sla_hours: string;
  owner: string;
  enabled: boolean;
}

const BLANK_FORM: FormState = {
  name: "",
  description: "",
  trigger_type: "health_at_risk",
  max_score: "6",
  band: "at_risk",
  inactive_days: "14",
  days_before: "7",
  action_type: "create_task",
  title: "Abordar {nome}",
  priority: "alta",
  sla_hours: "24",
  owner: "cs",
  enabled: true,
};

/** Carrega um Playbook existente no estado do form (para edição). */
function formFromPlaybook(p: Playbook): FormState {
  const tc = p.trigger_config ?? {};
  const ac = p.action_config ?? {};
  const str = (v: unknown, fallback: string) =>
    v === null || v === undefined ? fallback : String(v);
  return {
    name: p.name,
    description: p.description ?? "",
    trigger_type: p.trigger_type,
    max_score: str(tc.max_score, "6"),
    band: str(tc.band, "at_risk"),
    inactive_days: str(tc.days, "14"),
    days_before: str(tc.days_before, "7"),
    action_type: p.action_type,
    title: str(ac.title, "Abordar {nome}"),
    priority: str(ac.priority, "alta"),
    sla_hours: str(ac.sla_hours, "24"),
    owner: str(ac.owner, "cs"),
    enabled: p.enabled,
  };
}

/** Monta o corpo da API (trigger_config/action_config) a partir do form. */
function buildPayload(f: FormState): PlaybookInput {
  let trigger_config: Record<string, unknown> = {};
  switch (f.trigger_type) {
    case "nps_detractor":
      trigger_config = { max_score: Number(f.max_score) || 6 };
      break;
    case "health_at_risk":
      trigger_config = { band: f.band || "at_risk" };
      break;
    case "inactive_days":
      trigger_config = { days: Number(f.inactive_days) || 14 };
      break;
    case "renewal_soon":
      trigger_config = { days_before: Number(f.days_before) || 7 };
      break;
    case "churn_detected":
      trigger_config = {};
      break;
  }

  const action_config: Record<string, unknown> = {};
  if (f.action_type === "create_task") {
    if (f.title.trim()) action_config.title = f.title.trim();
    if (f.priority) action_config.priority = f.priority;
    if (f.sla_hours.trim()) action_config.sla_hours = Number(f.sla_hours) || 24;
  }
  if (f.owner.trim()) action_config.owner = f.owner.trim();

  return {
    name: f.name.trim(),
    description: f.description.trim() || null,
    enabled: f.enabled,
    trigger_type: f.trigger_type,
    trigger_config,
    action_type: f.action_type,
    action_config,
  };
}

// ===== Campo de config condicional ao gatilho ===============================

function TriggerConfigField({
  form,
  set,
}: {
  form: FormState;
  set: <K extends keyof FormState>(k: K, v: FormState[K]) => void;
}) {
  switch (form.trigger_type) {
    case "nps_detractor":
      return (
        <div className="field">
          <label>Nota máxima (≤) considerada detratora</label>
          <input
            type="number" min={0} max={10} inputMode="numeric"
            value={form.max_score}
            onChange={(e) => set("max_score", e.target.value)}
          />
        </div>
      );
    case "health_at_risk":
      return (
        <div className="field">
          <label>Banda de saúde</label>
          <select value={form.band} onChange={(e) => set("band", e.target.value)}>
            {HEALTH_BANDS.map((b) => (
              <option key={b.value} value={b.value}>{b.label}</option>
            ))}
          </select>
        </div>
      );
    case "inactive_days":
      return (
        <div className="field">
          <label>Dias sem feedback</label>
          <input
            type="number" min={1} inputMode="numeric"
            value={form.inactive_days}
            onChange={(e) => set("inactive_days", e.target.value)}
          />
        </div>
      );
    case "renewal_soon":
      return (
        <div className="field">
          <label>Dias antes da renovação</label>
          <input
            type="number" min={1} inputMode="numeric"
            value={form.days_before}
            onChange={(e) => set("days_before", e.target.value)}
          />
        </div>
      );
    case "churn_detected":
      return (
        <div className="off-base-hint" style={{ marginBottom: 15 }}>
          Sem configuração — dispara a cada novo sinal de cancelamento.
        </div>
      );
  }
}

// ===== Página ===============================================================

export default function PlaybooksPage() {
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [loading, setLoading] = useState(true);

  // form (criar / editar)
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(BLANK_FORM);
  const [saving, setSaving] = useState(false);

  // toggle em voo (evita clique duplo por linha)
  const [togglingId, setTogglingId] = useState<string | null>(null);

  // exclusão
  const [deleting, setDeleting] = useState<Playbook | null>(null);

  const set = useCallback(<K extends keyof FormState>(k: K, v: FormState[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await api.get<Playbook[] | { items: Playbook[] }>("/api/playbooks");
      setPlaybooks(Array.isArray(raw) ? raw : raw.items ?? []);
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function startCreate() {
    setEditingId(null);
    setForm(BLANK_FORM);
    setFlash(null);
  }

  function startEdit(p: Playbook) {
    setEditingId(p.id);
    setForm(formFromPlaybook(p));
    setFlash(null);
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setFlash({ kind: "err", msg: "Dê um nome à regra." });
      return;
    }
    setSaving(true);
    setFlash(null);
    const payload = buildPayload(form);
    try {
      if (editingId) {
        const updated = await api.patch<Playbook>(`/api/playbooks/${editingId}`, payload);
        setPlaybooks((prev) => prev.map((p) => (p.id === editingId ? updated : p)));
        setFlash({ kind: "ok", msg: `Regra "${updated.name}" atualizada.` });
      } else {
        const created = await api.post<Playbook>("/api/playbooks", payload);
        setPlaybooks((prev) => [created, ...prev]);
        setFlash({ kind: "ok", msg: `Regra "${created.name}" criada.` });
      }
      startCreate();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  async function toggleEnabled(p: Playbook) {
    setTogglingId(p.id);
    const next = !p.enabled;
    // otimista
    setPlaybooks((prev) => prev.map((x) => (x.id === p.id ? { ...x, enabled: next } : x)));
    try {
      const updated = await api.patch<Playbook>(`/api/playbooks/${p.id}`, { enabled: next });
      setPlaybooks((prev) => prev.map((x) => (x.id === p.id ? updated : x)));
    } catch (e) {
      // reverte
      setPlaybooks((prev) => prev.map((x) => (x.id === p.id ? p : x)));
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setTogglingId(null);
    }
  }

  const isEditing = editingId !== null;
  const editingName = useMemo(
    () => playbooks.find((p) => p.id === editingId)?.name ?? null,
    [playbooks, editingId],
  );

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Playbooks</h1>
          <div className="page-sub">
            Regras de automação: um gatilho (detrator, conta em risco, inatividade…) cria
            tarefas de CS ou alerta o dono
          </div>
        </div>
        {!loading && <span className="refresh-note">{playbooks.length} regras</span>}
      </div>

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="two-col">
        {/* Lista de regras */}
        <div className="card">
          {playbooks.length === 0 && (
            <div className="empty">
              <div className="big">⚙️</div>
              {loading ? "Carregando…" : "Nenhuma regra ainda — crie a primeira ao lado."}
            </div>
          )}
          {playbooks.map((p) => (
            <div key={p.id} className="survey-item">
              <div className="survey-name">
                {p.name}
                <span className={`badge ${p.enabled ? "promoter" : "neutral"}`}>
                  {p.enabled ? "ativo" : "inativo"}
                </span>
              </div>
              <div className="survey-q">
                <b>{ruleSummary(p)}</b>
                {p.description && (
                  <>
                    <br />
                    {p.description}
                  </>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className={`toggle-abordado ${p.enabled ? "on" : ""}`}
                  onClick={() => toggleEnabled(p)}
                  disabled={togglingId === p.id}
                  aria-pressed={p.enabled}
                  title={p.enabled ? "Desativar regra" : "Ativar regra"}
                >
                  {togglingId === p.id ? "…" : p.enabled ? "Ativo" : "Inativo"}
                </button>
                <button type="button" className="btn ghost sm" onClick={() => startEdit(p)}>
                  Editar
                </button>
                <button
                  type="button"
                  className="icon-btn danger"
                  onClick={() => setDeleting(p)}
                  title="Excluir regra"
                  aria-label="Excluir regra"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Form criar / editar */}
        <div className="card" style={{ padding: "18px 20px" }}>
          <h2 className="section-title">{isEditing ? "Editar regra" : "Nova regra"}</h2>
          <p className="section-sub">
            {isEditing
              ? `Ajustando "${editingName ?? ""}".`
              : "Defina o gatilho, o que ele observa e a ação a tomar."}
          </p>
          <form onSubmit={submit}>
            <div className="field">
              <label>Nome da regra</label>
              <input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="ex.: Resgatar contas em risco"
                required
              />
            </div>

            <div className="field">
              <label>Gatilho</label>
              <select
                value={form.trigger_type}
                onChange={(e) => set("trigger_type", e.target.value as PlaybookTrigger)}
              >
                {TRIGGERS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <TriggerConfigField form={form} set={set} />

            <div className="field">
              <label>Ação</label>
              <select
                value={form.action_type}
                onChange={(e) => set("action_type", e.target.value as PlaybookAction)}
              >
                {ACTIONS.map((a) => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
            </div>

            {form.action_type === "create_task" && (
              <>
                <div className="field">
                  <label>Título da tarefa (use {"{nome}"})</label>
                  <input
                    value={form.title}
                    onChange={(e) => set("title", e.target.value)}
                    placeholder="ex.: Abordar {nome}"
                  />
                </div>
                <div className="form-row-2">
                  <div className="field">
                    <label>Prioridade</label>
                    <select value={form.priority} onChange={(e) => set("priority", e.target.value)}>
                      {PRIORITIES.map((p) => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>SLA (horas)</label>
                    <input
                      type="number" min={1} inputMode="numeric"
                      value={form.sla_hours}
                      onChange={(e) => set("sla_hours", e.target.value)}
                      placeholder="ex.: 24"
                    />
                  </div>
                </div>
              </>
            )}

            <div className="field">
              <label>Dono padrão</label>
              <input
                value={form.owner}
                onChange={(e) => set("owner", e.target.value)}
                placeholder="ex.: cs (slug/telefone/e-mail do responsável)"
              />
            </div>

            <label className="check-row" style={{ marginBottom: 16 }}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => set("enabled", e.target.checked)}
              />
              <span>Regra ativa</span>
            </label>

            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn" disabled={saving}>
                {saving ? "Salvando…" : isEditing ? "Salvar alterações" : "Criar regra"}
              </button>
              {isEditing && (
                <button type="button" className="btn ghost" onClick={startCreate} disabled={saving}>
                  Cancelar
                </button>
              )}
            </div>
          </form>
        </div>
      </div>

      {deleting && (
        <ConfirmDialog
          title="Excluir regra?"
          message={
            <>
              Essa ação é permanente. A regra <b>{deleting.name}</b> deixará de gerar tarefas.
            </>
          }
          confirmLabel="Sim, excluir"
          confirmingLabel="Excluindo…"
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            await api.del(`/api/playbooks/${deleting.id}`);
            setPlaybooks((prev) => prev.filter((p) => p.id !== deleting.id));
            if (editingId === deleting.id) startCreate();
            setDeleting(null);
          }}
        />
      )}
    </div>
  );
}
