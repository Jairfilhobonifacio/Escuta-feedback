"use client";

import { useCallback, useEffect, useState } from "react";
import { Reveal, Stagger, StaggerItem } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api, type Contact, type DispatchResult, type Survey } from "@/lib/api";

// emoji em .ts/.tsx só via \u{...} (o bundler do Next no Windows corrompe literais).
const EMOJI_ROCKET = "\u{1F680}"; // 🚀 — disparo (mensagem de sucesso)
const EMOJI_HANDS = "\u{1F64C}"; // 🙌 — follow-up padrão (texto enviado ao cliente)

/** Placeholder de um item de pesquisa enquanto a lista carrega (nome + perguntas
   + ação), espelhando a silhueta do .survey-item real com shimmer. */
function SurveyRowSkeleton() {
  return (
    <div className="survey-item" aria-busy="true">
      <div className="sk-line w-50" style={{ marginTop: 4 }} />
      <div className="sk-line w-90" style={{ marginTop: 10 }} />
      <div className="sk-line w-70" />
      <div className="sk-line" style={{ width: 120, marginTop: 12 }} />
    </div>
  );
}

export default function PesquisasPage() {
  const [surveys, setSurveys] = useState<Survey[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // form de criação
  const [name, setName] = useState("");
  const [npsQ, setNpsQ] = useState("De 0 a 10, o quanto você recomendaria a gente pra um amigo?");
  const [reasonQ, setReasonQ] = useState(`Massa! ${EMOJI_HANDS} Por quê? (pode mandar em texto)`);
  const [saving, setSaving] = useState(false);

  // disparo
  const [picking, setPicking] = useState<string | null>(null); // survey id com painel aberto
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [dispatching, setDispatching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        api.get<Survey[]>("/api/surveys"),
        api.get<Contact[]>("/api/contacts"),
      ]);
      setSurveys(s);
      setContacts(c);
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
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
        msg: `${EMOJI_ROCKET} "${out.survey}" disparada para ${out.count} contato(s) no WhatsApp: ${out.dispatched_to
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

  const ativas = surveys.filter((s) => s.status === "active").length;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Pesquisas</h1>
          <div className="page-sub">Crie campanhas com perguntas próprias e dispare pra quem você escolher</div>
        </div>
        {!loading && surveys.length > 0 && (
          <span className="refresh-note">
            {surveys.length} {surveys.length === 1 ? "pesquisa" : "pesquisas"}
            {ativas > 0 ? ` · ${ativas} ativa${ativas === 1 ? "" : "s"}` : ""}
          </span>
        )}
      </div>

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="two-col">
        {/* ----- coluna: lista de pesquisas ----- */}
        <Reveal className="card psq-list-card">
          <div className="psq-list-head">
            <div>
              <div className="section-title">Suas pesquisas</div>
              <div className="card-head-sub">
                Cada pesquisa vira uma conversa no WhatsApp — nota, motivo e agradecimento.
              </div>
            </div>
            {!loading && surveys.length > 0 && (
              <Badge variant="outline" className="psq-count">
                {surveys.length}
              </Badge>
            )}
          </div>

          {loading ? (
            <div aria-busy="true">
              {Array.from({ length: 3 }).map((_, i) => (
                <SurveyRowSkeleton key={i} />
              ))}
            </div>
          ) : surveys.length === 0 ? (
            <div className="empty">
              <div className="empty-illu">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <path d="M14 2v6h6" />
                  <path d="M9 13h6M9 17h4" />
                </svg>
              </div>
              <div className="empty-title">Nenhuma pesquisa ainda</div>
              <p className="empty-sub">
                Crie a primeira ao lado: uma pergunta de nota (0–10), o follow-up do motivo e o
                agradecimento. Depois é só disparar pra quem você escolher.
              </p>
            </div>
          ) : (
            <Stagger>
              {surveys.map((s) => (
                <StaggerItem key={s.id} className="survey-item">
                  <div className="survey-name">
                    {s.name}
                    <Badge variant={s.status === "active" ? "positive" : "neutral"}>
                      {s.status}
                    </Badge>
                  </div>
                  <div className="survey-q">
                    <b>Pergunta:</b> {s.nps_question}
                    <br />
                    <b>Follow-up:</b> {s.reason_prompt}
                  </div>
                  <div style={{ marginTop: 12 }}>
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
                          <Button
                            variant="accent"
                            size="sm"
                            disabled={picked.size === 0 || dispatching}
                            onClick={() => dispatch(s)}
                          >
                            {dispatching ? "Enviando\u{2026}" : `Disparar agora (${picked.size})`}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setPicking(null)}>
                            Cancelar
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setPicking(s.id);
                          setPicked(new Set());
                        }}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="m22 2-7 20-4-9-9-4Z" />
                          <path d="M22 2 11 13" />
                        </svg>
                        Disparar
                      </Button>
                    )}
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </Reveal>

        {/* ----- coluna: nova pesquisa ----- */}
        <Reveal delay={0.08} className="card psq-form-card">
          <h2 className="section-title">Nova pesquisa</h2>
          <p className="section-sub">Fluxo: pergunta de nota (0–10) → follow-up do motivo → agradecimento.</p>

          {/* mini-preview do fluxo da conversa — dá hierarquia e preenche o espaço */}
          <div className="psq-flow" aria-hidden>
            <span className="psq-flow-step">
              <span className="psq-flow-dot one" />
              Nota 0–10
            </span>
            <span className="psq-flow-arrow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14" />
                <path d="m12 5 7 7-7 7" />
              </svg>
            </span>
            <span className="psq-flow-step">
              <span className="psq-flow-dot two" />
              Motivo
            </span>
            <span className="psq-flow-arrow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14" />
                <path d="m12 5 7 7-7 7" />
              </svg>
            </span>
            <span className="psq-flow-step">
              <span className="psq-flow-dot three" />
              Obrigado
            </span>
          </div>

          <form onSubmit={createSurvey}>
            <div className="field">
              <label htmlFor="psq-name">Nome da campanha</label>
              <Input
                id="psq-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ex.: NPS Junho — alunos ativos"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="psq-nps">Pergunta da nota (0–10)</label>
              <textarea id="psq-nps" value={npsQ} onChange={(e) => setNpsQ(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="psq-reason">Follow-up (motivo)</label>
              <textarea id="psq-reason" value={reasonQ} onChange={(e) => setReasonQ(e.target.value)} required />
            </div>
            <Button type="submit" disabled={saving} className="w-full">
              {saving ? "Criando\u{2026}" : "Criar pesquisa"}
            </Button>
          </form>
        </Reveal>
      </div>

      <style jsx>{`
        .psq-list-card { padding: 0; overflow: hidden; }
        .psq-list-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          padding: 18px 20px 16px;
          border-bottom: 1px solid var(--charcoal);
          background: linear-gradient(180deg, rgba(108, 92, 231, 0.035), transparent 92%);
        }
        :global(.psq-count) {
          font-family: var(--mono);
          font-size: 12px;
          padding: 2px 9px;
        }
        .psq-form-card { padding: 18px 20px; }
        /* mini-preview do fluxo da conversa */
        .psq-flow {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          padding: 11px 13px;
          margin: 4px 0 18px;
          background: var(--ink);
          border: 1px solid var(--charcoal);
          border-radius: var(--radius-sm);
        }
        .psq-flow-step {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          font-size: 12px;
          font-weight: 600;
          color: var(--text-dim);
        }
        .psq-flow-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .psq-flow-dot.one { background: var(--gold-fill); }
        .psq-flow-dot.two { background: var(--indigo); }
        .psq-flow-dot.three { background: var(--indigo-light); }
        .psq-flow-arrow {
          display: inline-flex;
          color: var(--text-ghost);
        }
        .psq-flow-arrow svg { width: 15px; height: 15px; }
      `}</style>
    </div>
  );
}
