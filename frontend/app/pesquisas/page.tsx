"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Contact, type DispatchResult, type Survey } from "@/lib/api";

export default function PesquisasPage() {
  const [surveys, setSurveys] = useState<Survey[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // form de criação
  const [name, setName] = useState("");
  const [npsQ, setNpsQ] = useState("De 0 a 10, o quanto você recomendaria a gente pra um amigo?");
  const [reasonQ, setReasonQ] = useState("Massa! 🙌 Por quê? (pode mandar em texto)");
  const [saving, setSaving] = useState(false);

  // disparo
  const [picking, setPicking] = useState<string | null>(null); // survey id com painel aberto
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [dispatching, setDispatching] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        api.get<Survey[]>("/api/surveys"),
        api.get<Contact[]>("/api/contacts"),
      ]);
      setSurveys(s);
      setContacts(c);
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createSurvey(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFlash(null);
    try {
      await api.post<Survey>("/api/surveys", {
        name,
        nps_question: npsQ,
        reason_prompt: reasonQ,
      });
      setFlash({ kind: "ok", msg: `Pesquisa "${name}" criada.` });
      setName("");
      await load();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  function togglePick(id: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function dispatch(survey: Survey) {
    setDispatching(true);
    setFlash(null);
    try {
      const out = await api.post<DispatchResult>(`/api/surveys/${survey.id}/dispatch`, {
        contact_ids: Array.from(picked),
      });
      setFlash({
        kind: "ok",
        msg: `🚀 "${out.survey}" disparada para ${out.count} contato(s) no WhatsApp: ${out.dispatched_to
          .map((d) => d.name || d.phone)
          .join(", ")}`,
      });
      setPicking(null);
      setPicked(new Set());
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setDispatching(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Pesquisas</h1>
          <div className="page-sub">Crie campanhas com perguntas próprias e dispare pra quem você escolher</div>
        </div>
      </div>

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="two-col">
        <div className="card">
          {surveys.length === 0 && (
            <div className="empty">
              <div className="big">✦</div>
              Nenhuma pesquisa ainda — crie a primeira ao lado.
            </div>
          )}
          {surveys.map((s) => (
            <div key={s.id} className="survey-item">
              <div className="survey-name">
                {s.name}
                <span className={`badge ${s.status === "active" ? "promoter" : "neutral"}`}>{s.status}</span>
              </div>
              <div className="survey-q">
                <b>Pergunta:</b> {s.nps_question}
                <br />
                <b>Follow-up:</b> {s.reason_prompt}
              </div>
              <div style={{ marginTop: 10 }}>
                {picking === s.id ? (
                  <div className="contact-picker">
                    <div className="section-sub" style={{ marginBottom: 8 }}>
                      Enviar para ({picked.size} selecionado{picked.size === 1 ? "" : "s"}):
                    </div>
                    {contacts.length === 0 && (
                      <div className="faint" style={{ fontSize: 13 }}>
                        Nenhum contato — adicione na aba Contatos.
                      </div>
                    )}
                    {contacts.map((c) => (
                      <label key={c.id} className="pick-row">
                        <input
                          type="checkbox"
                          checked={picked.has(c.id)}
                          onChange={() => togglePick(c.id)}
                        />
                        <span>{c.name || "sem nome"}</span>
                        <span className="mono dim">{c.phone}</span>
                      </label>
                    ))}
                    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                      <button
                        className="btn sm"
                        disabled={picked.size === 0 || dispatching}
                        onClick={() => dispatch(s)}
                      >
                        {dispatching ? "Enviando…" : `Disparar agora (${picked.size})`}
                      </button>
                      <button className="btn ghost sm" onClick={() => setPicking(null)}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    className="btn ghost sm"
                    onClick={() => {
                      setPicking(s.id);
                      setPicked(new Set());
                    }}
                  >
                    📤 Disparar
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="card" style={{ padding: "18px 20px" }}>
          <h2 className="section-title">Nova pesquisa</h2>
          <p className="section-sub">Fluxo: pergunta de nota (0–10) → follow-up do motivo → agradecimento.</p>
          <form onSubmit={createSurvey}>
            <div className="field">
              <label>Nome da campanha</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ex.: NPS Junho — alunos ativos"
                required
              />
            </div>
            <div className="field">
              <label>Pergunta da nota (0–10)</label>
              <textarea value={npsQ} onChange={(e) => setNpsQ(e.target.value)} required />
            </div>
            <div className="field">
              <label>Follow-up (motivo)</label>
              <textarea value={reasonQ} onChange={(e) => setReasonQ(e.target.value)} required />
            </div>
            <button className="btn" disabled={saving}>
              {saving ? "Criando…" : "Criar pesquisa"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
