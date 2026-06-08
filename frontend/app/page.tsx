"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Dashboard } from "@/lib/api";

function npsClass(nps: number | null): string {
  if (nps === null) return "nps-none";
  if (nps >= 50) return "nps-good";
  if (nps >= 0) return "nps-mid";
  return "nps-bad";
}

function bucketBadge(bucket: string | null, status: string) {
  if (bucket === "promoter") return <span className="badge promoter">promotor</span>;
  if (bucket === "passive") return <span className="badge passive">neutro</span>;
  if (bucket === "detractor") return <span className="badge detractor">detrator</span>;
  if (status === "sent") return <span className="badge open">aguardando nota</span>;
  if (status === "awaiting_reason") return <span className="badge open">aguardando motivo</span>;
  if (status === "closed") return <span className="badge neutral">concluída</span>;
  return <span className="badge neutral">{status}</span>;
}

function typeBadge(type: string) {
  if (type === "exit") return <span className="badge type t-exit">Exit</span>;
  return <span className="badge type t-nps">NPS</span>;
}

const SENT_META: Record<string, { cls: string; label: string }> = {
  positivo: { cls: "s-pos", label: "positivo" },
  neutro: { cls: "s-neu", label: "neutro" },
  negativo: { cls: "s-neg", label: "negativo" },
};

/** Badge de sentimento da IA. Retorna null se ausente/desconhecido (não polui). */
function sentimentBadge(sentiment?: string | null) {
  if (!sentiment) return null;
  const m = SENT_META[sentiment];
  if (!m) return null;
  return <span className={`badge sent ${m.cls}`}>{m.label}</span>;
}

/** Chips de tema da IA. Retorna null se a lista estiver vazia/ausente. */
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

/** Conta os temas de todas as respostas e devolve os mais citados (desc). */
function topThemes(rows: { themes?: string[] | null }[], limit = 5): [string, number][] {
  const counts = new Map<string, number>();
  for (const r of rows) {
    for (const t of r.themes ?? []) {
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit);
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.get<Dashboard>("/api/dashboard"));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  if (err) {
    return (
      <div>
        <div className="page-head">
          <h1 className="page-title">Dashboard</h1>
        </div>
        <div className="flash err">
          Não consegui falar com a API ({err}). A API está rodando em <span className="mono">localhost:8000</span>?
        </div>
      </div>
    );
  }

  if (!data) return <div className="empty">Carregando…</div>;

  const k = data.kpis;
  const exit = data.exit ?? { sent: 0, answered: 0, recent: [] };
  const total = k.promoters + k.passives + k.detractors;
  const pct = (n: number) => (total ? (n / total) * 100 : 0);
  const themesTop = topThemes(data.recent);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="page-sub">
            {data.org.name} · feedbacks via WhatsApp
          </div>
        </div>
        <span className="refresh-note">atualiza a cada 30s</span>
      </div>

      <div className="kpi-grid">
        <div className="card kpi kpi-nps">
          <div className="kpi-label">NPS</div>
          <div className={`kpi-value ${npsClass(k.nps)}`}>{k.nps ?? "—"}</div>
          <div className="kpi-hint">% promotores − % detratores</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Enviadas</div>
          <div className="kpi-value">{k.sent}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Respondidas</div>
          <div className="kpi-value">{k.answered}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Taxa de resposta</div>
          <div className="kpi-value">{k.response_rate !== null ? `${k.response_rate}%` : "—"}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Concluídas</div>
          <div className="kpi-value">{k.closed}</div>
        </div>
      </div>

      <div className="card dist">
        <div className="section-title">Distribuição</div>
        <div className="dist-bar">
          <span style={{ width: `${pct(k.promoters)}%`, background: "var(--promoter)" }} />
          <span style={{ width: `${pct(k.passives)}%`, background: "var(--passive)" }} />
          <span style={{ width: `${pct(k.detractors)}%`, background: "var(--detractor)" }} />
        </div>
        <div className="dist-legend">
          <span><span className="dot" style={{ background: "var(--promoter)" }} />Promotores {k.promoters}</span>
          <span><span className="dot" style={{ background: "var(--passive)" }} />Neutros {k.passives}</span>
          <span><span className="dot" style={{ background: "var(--detractor)" }} />Detratores {k.detractors}</span>
        </div>
      </div>

      <div className="card exit-card">
        <div className="card-head">
          <div>
            <div className="section-title">Motivos de cancelamento</div>
            <div className="card-head-sub">o que clientes responderam na exit survey ao cancelar</div>
          </div>
          <span className="exit-counter">
            {exit.answered}/{exit.sent} respondida{exit.answered === 1 ? "" : "s"}
          </span>
        </div>
        {exit.recent.length === 0 ? (
          <div className="empty">
            <div className="big">🎉</div>
            Nenhum cancelamento respondido ainda.
          </div>
        ) : (
          <ul className="exit-list">
            {exit.recent.map((m, i) => (
              <li key={i} className="exit-item">
                <div className="exit-quote">“{m.text}”</div>
                <div className="exit-meta">
                  {m.contact_name || "sem nome"} · {fmtDate(m.closed_at)}
                  {sentimentBadge(m.sentiment) && <> · {sentimentBadge(m.sentiment)}</>}
                </div>
                {themeChips(m.themes)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <div className="section-title">Respostas recentes</div>
        </div>
        {themesTop.length > 0 && (
          <div className="themes-summary">
            <span className="themes-summary-label">Temas mais citados</span>
            <div className="theme-chips">
              {themesTop.map(([t, n]) => (
                <span key={t} className="chip">
                  {t}<span className="chip-count">{n}</span>
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Contato</th>
                <th>Pesquisa</th>
                <th>Nota</th>
                <th>Classificação</th>
                <th>Sentimento</th>
                <th style={{ width: "30%" }}>Motivo</th>
                <th>Enviada</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <div className="empty">
                      <div className="big">📭</div>
                      Nenhuma pesquisa enviada ainda. Crie uma em <b>Pesquisas</b> e dispare.
                    </div>
                  </td>
                </tr>
              )}
              {data.recent.map((r) => (
                <tr key={r.id}>
                  <td>
                    <div>{r.contact_name || <span className="faint">sem nome</span>}</div>
                    <div className="mono dim">{r.contact_phone}</div>
                  </td>
                  <td>
                    {r.survey_type ? typeBadge(r.survey_type) : <span className="faint">—</span>}
                    {r.survey_name && <div className="dim survey-cell-name">{r.survey_name}</div>}
                  </td>
                  <td>
                    <span className={`score-pill ${r.bucket ?? "none"}`}>{r.score ?? "·"}</span>
                  </td>
                  <td>{bucketBadge(r.bucket, r.status)}</td>
                  <td>{sentimentBadge(r.sentiment) ?? <span className="faint">—</span>}</td>
                  <td>
                    {r.text ? r.text : <span className="faint">—</span>}
                    {themeChips(r.themes)}
                  </td>
                  <td className="dim">{fmtDate(r.sent_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
