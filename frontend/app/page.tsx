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
  return <span className="badge neutral">{status}</span>;
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
  const total = k.promoters + k.passives + k.detractors;
  const pct = (n: number) => (total ? (n / total) * 100 : 0);

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

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Contato</th>
                <th>Nota</th>
                <th>Classificação</th>
                <th style={{ width: "40%" }}>Motivo</th>
                <th>Enviada</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.length === 0 && (
                <tr>
                  <td colSpan={5}>
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
                    <span className={`score-pill ${r.bucket ?? "none"}`}>{r.score ?? "·"}</span>
                  </td>
                  <td>{bucketBadge(r.bucket, r.status)}</td>
                  <td>{r.text ? r.text : <span className="faint">—</span>}</td>
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
