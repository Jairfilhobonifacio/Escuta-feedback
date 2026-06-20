"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Reveal, Stagger, StaggerItem } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  api,
  clientes as clientesApi,
  type Cliente,
  type ClienteFiltro,
  type DispatchResult,
  type EstadoAssinatura,
  type NpsBucket,
  type Survey,
} from "@/lib/api";

// emoji em .ts/.tsx só via \u{...} (o bundler do Next no Windows corrompe literais).
const EMOJI_ROCKET = "\u{1F680}"; // 🚀 — disparo (mensagem de sucesso)
const EMOJI_HANDS = "\u{1F64C}"; // 🙌 — follow-up padrão (texto enviado ao cliente)

/** Estados de assinatura legíveis (mesmos rótulos da tela Clientes). */
const ESTADO_OPCOES: { value: EstadoAssinatura; label: string }[] = [
  { value: "active_paying", label: "Pagante ativo" },
  { value: "past_due", label: "Em atraso" },
  { value: "paid_without_access", label: "Pago sem acesso" },
  { value: "complimentary", label: "Cortesia" },
  { value: "cancelled", label: "Cancelado" },
];

const NPS_OPCOES: { value: NpsBucket; label: string }[] = [
  { value: "promotor", label: "Promotores" },
  { value: "neutro", label: "Neutros" },
  { value: "detrator", label: "Detratores" },
];

/** Data ISO -> "há X dias" curto (para o "último disparo" no card). */
function relativo(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const dias = Math.floor((Date.now() - t) / 86_400_000);
  if (dias <= 0) return "hoje";
  if (dias === 1) return "ontem";
  if (dias < 30) return `há ${dias} dias`;
  const meses = Math.floor(dias / 30);
  return meses === 1 ? "há 1 mês" : `há ${meses} meses`;
}

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
  const [loading, setLoading] = useState(true);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // form de criação
  const [name, setName] = useState("");
  const [npsQ, setNpsQ] = useState("De 0 a 10, o quanto você recomendaria a gente pra um amigo?");
  const [reasonQ, setReasonQ] = useState(`Massa! ${EMOJI_HANDS} Por quê? (pode mandar em texto)`);
  const [saving, setSaving] = useState(false);

  // disparo — seleção de público a partir de /api/clientes (lista rica + filtros)
  const [picking, setPicking] = useState<string | null>(null); // survey id com painel aberto
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [dispatching, setDispatching] = useState(false);

  // público: filtros do picker (reusa GET /api/clientes)
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [loadingClientes, setLoadingClientes] = useState(false);
  const [busca, setBusca] = useState("");
  const [estado, setEstado] = useState<EstadoAssinatura | "">("");
  const [npsBucket, setNpsBucket] = useState<NpsBucket | "">("");

  const loadSurveys = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api.get<Survey[]>("/api/surveys");
      setSurveys(s);
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSurveys();
  }, [loadSurveys]);

  // Carrega o público (clientes) com os filtros atuais — só enquanto um picker
  // está aberto. Debounce na busca; estado/nps refazem na hora.
  useEffect(() => {
    if (picking === null) return;
    let cancel = false;
    setLoadingClientes(true);
    const filtro: ClienteFiltro = {
      search: busca.trim() || undefined,
      estado: estado || undefined,
      nps_bucket: npsBucket || undefined,
    };
    const t = setTimeout(async () => {
      try {
        const rows = await clientesApi.list(filtro);
        if (!cancel) setClientes(rows);
      } catch (e) {
        if (!cancel) setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
      } finally {
        if (!cancel) setLoadingClientes(false);
      }
    }, 250);
    return () => {
      cancel = true;
      clearTimeout(t);
    };
  }, [picking, busca, estado, npsBucket]);

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
      await loadSurveys();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  function abrirPicker(surveyId: string) {
    setPicking(surveyId);
    setPicked(new Set());
    setBusca("");
    setEstado("");
    setNpsBucket("");
    setClientes([]);
  }

  function togglePick(id: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /** Marca/desmarca todos os clientes atualmente filtrados (visíveis na lista). */
  function toggleTodosFiltrados() {
    const ids = clientes.map((c) => c.id);
    const todosMarcados = ids.length > 0 && ids.every((id) => picked.has(id));
    setPicked((prev) => {
      const next = new Set(prev);
      if (todosMarcados) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
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
      // recarrega para o acompanhamento (contagens) refletir o novo disparo
      await loadSurveys();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setDispatching(false);
    }
  }

  const ativas = surveys.filter((s) => s.status === "active").length;

  // estado de "selecionar todos" para o rótulo do botão
  const idsFiltrados = useMemo(() => clientes.map((c) => c.id), [clientes]);
  const todosFiltradosMarcados =
    idsFiltrados.length > 0 && idsFiltrados.every((id) => picked.has(id));

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

                  {/* Acompanhamento — enviados / responderam / pendentes (badges
                      reusam .tab-count; estilo de pílula via utilitários inline).
                      Só aparece quando a pesquisa já disparou (sent_count > 0). */}
                  {s.sent_count > 0 && (
                    <div className="flex flex-wrap items-center gap-2" style={{ marginTop: 12 }}>
                      <span
                        className="tab-count inline-flex items-center gap-1 rounded-full border border-[var(--charcoal-2)] bg-[var(--ink-800)] px-2.5 py-0.5 text-[12px] font-semibold text-[var(--text-dim)]"
                        title="Contatos para quem a pesquisa foi enviada"
                      >
                        {s.sent_count} enviada{s.sent_count === 1 ? "" : "s"}
                      </span>
                      <span
                        className="tab-count inline-flex items-center gap-1 rounded-full border border-[var(--promoter-line)] bg-[var(--promoter-soft)] px-2.5 py-0.5 text-[12px] font-semibold text-[var(--indigo-light)]"
                        title="Quantos já deram nota"
                      >
                        {s.answered_count} respondeu{s.answered_count === 1 ? "" : "ram"}
                      </span>
                      <span
                        className="tab-count inline-flex items-center gap-1 rounded-full border border-[var(--charcoal-2)] bg-[var(--ink-800)] px-2.5 py-0.5 text-[12px] font-semibold text-[var(--text-dim)]"
                        title="Enviados que ainda não responderam"
                      >
                        {s.pending_count} pendente{s.pending_count === 1 ? "" : "s"}
                      </span>
                      {relativo(s.last_run_at) && (
                        <span className="faint" style={{ fontSize: 12 }}>
                          último disparo {relativo(s.last_run_at)}
                        </span>
                      )}
                    </div>
                  )}

                  <div style={{ marginTop: 12 }}>
                    {picking === s.id ? (
                      <div className="contact-picker">
                        <div className="section-sub" style={{ marginBottom: 8 }}>
                          Escolha o público ({picked.size} selecionado{picked.size === 1 ? "" : "s"}):
                        </div>

                        {/* Busca + filtros-chave (reusam ClienteFiltro de /api/clientes) */}
                        <div className="toolbar" style={{ marginBottom: 10 }}>
                          <Input
                            value={busca}
                            onChange={(e) => setBusca(e.target.value)}
                            placeholder={"Buscar por nome ou telefone\u{2026}"}
                            aria-label="Buscar clientes por nome ou telefone"
                          />
                          <select
                            value={estado}
                            onChange={(e) => setEstado(e.target.value as EstadoAssinatura | "")}
                            aria-label="Filtrar por estado da assinatura"
                          >
                            <option value="">Toda assinatura</option>
                            {ESTADO_OPCOES.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                          <select
                            value={npsBucket}
                            onChange={(e) => setNpsBucket(e.target.value as NpsBucket | "")}
                            aria-label="Filtrar por faixa de NPS"
                          >
                            <option value="">Todo NPS</option>
                            {NPS_OPCOES.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                        </div>

                        <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 text-[12px] font-semibold uppercase tracking-[0.04em] text-[var(--indigo-light)] hover:underline disabled:opacity-50"
                            onClick={toggleTodosFiltrados}
                            disabled={loadingClientes || idsFiltrados.length === 0}
                          >
                            {todosFiltradosMarcados ? "Limpar seleção" : "Selecionar todos os filtrados"}
                            {idsFiltrados.length > 0 ? ` (${idsFiltrados.length})` : ""}
                          </button>
                          {loadingClientes && <span className="faint" style={{ fontSize: 12 }}>{"Carregando\u{2026}"}</span>}
                        </div>

                        {!loadingClientes && clientes.length === 0 && (
                          <div className="faint" style={{ fontSize: 13 }}>
                            Nenhum cliente para esses filtros.
                          </div>
                        )}

                        <div style={{ maxHeight: 320, overflowY: "auto" }}>
                          {clientes.map((c) => (
                            <label key={c.id} className="pick-row">
                              <input
                                type="checkbox"
                                checked={picked.has(c.id)}
                                onChange={() => togglePick(c.id)}
                              />
                              <span>{c.nome || "sem nome"}</span>
                              <span className="mono dim">{c.whatsapp}</span>
                              {!c.tem_whatsapp && (
                                <Badge variant="outline" className="ml-auto">só e-mail</Badge>
                              )}
                              {!c.opt_in && (
                                <Badge variant="neutral" className={c.tem_whatsapp ? "ml-auto" : ""}>sem opt-in</Badge>
                              )}
                            </label>
                          ))}
                        </div>

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
                        onClick={() => abrirPicker(s.id)}
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
