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

/** Gauge semicircular do NPS (−100…+100) — peça-âncora do dashboard.
   Arco track + arco preenchido (gradiente detrator→neutro→promotor) + ponta. */
function NpsGauge({ nps }: { nps: number | null }) {
  const t = Math.max(0, Math.min(1, ((nps ?? 0) + 100) / 200));
  const cx = 130, cy = 130, R = 110;
  const rad = (180 * (1 - t) * Math.PI) / 180;
  const px = cx + R * Math.cos(rad);
  const py = cy - R * Math.sin(rad);
  return (
    <svg viewBox="0 0 260 150" className="gauge" role="img" aria-label={`NPS ${nps ?? "indisponível"} de -100 a 100`}>
      <defs>
        <linearGradient id="npsArc" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--detractor)" />
          <stop offset="50%" stopColor="var(--passive)" />
          <stop offset="100%" stopColor="var(--promoter)" />
        </linearGradient>
      </defs>
      <path className="gauge-track" d={`M ${cx - R} ${cy} A ${R} ${R} 0 0 1 ${cx + R} ${cy}`} />
      {nps !== null && (
        <>
          <path className="gauge-fill" stroke="url(#npsArc)" d={`M ${cx - R} ${cy} A ${R} ${R} 0 0 1 ${px} ${py}`} />
          <circle className="gauge-dot" cx={px} cy={py} r={7.5} />
        </>
      )}
    </svg>
  );
}

/** Mini waveform — assinatura "Escuta" (ouvir o cliente). Decorativo. */
function Waveform() {
  const bars = [8, 16, 11, 22, 14, 28, 18, 34, 22, 40, 26, 44, 30, 38, 24, 30, 18, 26, 14, 34, 20, 42, 28, 36, 22, 28, 16, 22, 12, 18, 10, 14];
  const W = 6, G = 4;
  return (
    <svg className="wave" viewBox={`0 0 ${bars.length * (W + G)} 48`} preserveAspectRatio="none" aria-hidden focusable="false">
      {bars.map((h, i) => (
        <rect key={i} x={i * (W + G)} y={(48 - h) / 2} width={W} height={h} rx={3} />
      ))}
    </svg>
  );
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

      <div className="card hero-nps">
        <div className="hero-gauge">
          <NpsGauge nps={k.nps} />
          <div className="hero-gauge-center">
            <div className={`hero-gauge-val ${npsClass(k.nps)}`}>{k.nps ?? "—"}</div>
            <div className="hero-gauge-cap">NPS · score líquido</div>
          </div>
          <div className="hero-gauge-scale"><span>−100</span><span>0</span><span>+100</span></div>
        </div>

        <div className="hero-meta">
          <div className="hero-dist">
            <div className="hero-dist-head">
              <span className="hero-eyebrow">Distribuição</span>
              <span className="hero-dist-total mono">{total} resposta{total === 1 ? "" : "s"}</span>
            </div>
            <div className="dist-bar">
              <span style={{ width: `${pct(k.promoters)}%`, background: "var(--promoter)" }} />
              <span style={{ width: `${pct(k.passives)}%`, background: "var(--passive)" }} />
              <span style={{ width: `${pct(k.detractors)}%`, background: "var(--detractor)" }} />
            </div>
            <div className="dist-legend">
              <span><span className="dot" style={{ background: "var(--promoter)" }} />Promotores {k.promoters} <span className="faint">· {Math.round(pct(k.promoters))}%</span></span>
              <span><span className="dot" style={{ background: "var(--passive)" }} />Neutros {k.passives} <span className="faint">· {Math.round(pct(k.passives))}%</span></span>
              <span><span className="dot" style={{ background: "var(--detractor)" }} />Detratores {k.detractors} <span className="faint">· {Math.round(pct(k.detractors))}%</span></span>
            </div>
          </div>

          <div className="hero-funnel">
            <span className="hero-eyebrow">Funil de resposta</span>
            {[
              { n: k.sent, l: "Enviadas", w: 100, tag: null as string | null },
              { n: k.answered, l: "Respondidas", w: k.sent ? (k.answered / k.sent) * 100 : 0, tag: k.response_rate !== null ? `${k.response_rate}%` : null },
              { n: k.closed, l: "Concluídas", w: k.sent ? (k.closed / k.sent) * 100 : 0, tag: null },
            ].map((s) => (
              <div className="fn-step" key={s.l}>
                <div className="fn-top">
                  <span className="fn-n mono">{s.n}</span>
                  <span className="fn-l">{s.l}</span>
                  {s.tag && <span className="fn-tag">{s.tag}</span>}
                </div>
                <div className="fn-track"><span className="fn-fill" style={{ width: `${s.w}%` }} /></div>
              </div>
            ))}
          </div>
        </div>

        <Waveform />
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
