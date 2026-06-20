"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Reveal, Stagger, StaggerItem } from "@/components/Motion";
import {
  api,
  campanha as campanhaApi,
  feedbacks as feedbacksApi,
  tarefas as tarefasApi,
  clusters as clustersApi,
  type Dashboard,
  type CampanhaStats,
  type FeedbacksResponse,
  type TarefasResponse,
  type ClustersResponse,
} from "@/lib/api";

/** Snapshot da "Voz do cliente & Tarefas" — agrega 3 endpoints já existentes
    (feedbacks, tarefas, clusters) num bloco compacto. Cada parte é best-effort:
    se um endpoint falhar, aquele campo fica null e a sub-seção some sem derrubar
    o resto da tela. Emoji em escape \u{...} (bundler Windows). */
interface VozTarefasSnapshot {
  feedbacks: FeedbacksResponse | null;
  tarefas: TarefasResponse | null;
  clusters: ClustersResponse | null;
}

/** Buckets de alcance do validador (app/domain/contacts/whatsapp.py · alcance()).
    Ordem fixa de exibição; só `whatsapp` conta como "com WhatsApp" (celular BR
    válido) — fixo/grupo NÃO contam. Emoji em escape \u{...} (bundler Windows). */
const ALCANCE_META: { key: string; label: string; emoji: string; cor: string }[] = [
  { key: "whatsapp", label: "Celular / WhatsApp", emoji: "\u{1F4AC}", cor: "var(--indigo-light)" },
  { key: "so_email", label: "Só e-mail", emoji: "\u{2709}\u{FE0F}", cor: "var(--text-dim)" },
  { key: "fixo", label: "Telefone fixo", emoji: "\u{260E}\u{FE0F}", cor: "var(--passive)" },
  { key: "grupo", label: "Grupo", emoji: "\u{1F465}", cor: "var(--passive)" },
  { key: "sem_contato", label: "Sem contato", emoji: "\u{1F6AB}", cor: "var(--text-faint)" },
  { key: "invalido", label: "Inválido", emoji: "\u{26A0}\u{FE0F}", cor: "var(--text-faint)" },
];

/** Etapas do funil da campanha em ordem, com a cor de acento de cada uma.
    Espelha o backend; "a contatar" recebe `faltam`. */
const CMP_ETAPA_META: Record<string, { cor: string }> = {
  "a contatar": { cor: "var(--text-faint)" },
  contatado: { cor: "var(--indigo)" },
  respondeu: { cor: "var(--indigo-light)" },
  cortesia: { cor: "var(--passive)" },
  reativou: { cor: "var(--gold)" },
};

function cmpPct(n: number, total: number): number {
  return total > 0 ? (n / total) * 100 : 0;
}

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

/** Skeleton do dashboard enquanto o /api/dashboard não respondeu — espelha a
   forma real (hero do NPS + fila de KPIs), com shimmer, em vez de "Carregando…". */
function DashboardSkeleton() {
  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="page-sub">carregando o pulso da operação…</div>
        </div>
        <span className="refresh-note">atualiza a cada 30s</span>
      </div>

      <div className="card hero-nps" aria-busy="true">
        <div className="hero-gauge" style={{ display: "grid", placeItems: "center", gap: 14 }}>
          <div className="sk-card" style={{ width: 240, height: 130, borderRadius: 999 }} />
          <div className="sk-line w-40" />
        </div>
        <div className="hero-meta" style={{ width: "100%" }}>
          <div className="hero-dist">
            <div className="sk-line w-30" />
            <div className="sk-card" style={{ height: 16, borderRadius: 999, margin: "10px 0" }} />
            <div className="sk-line w-80" />
          </div>
          <div className="hero-funnel" style={{ marginTop: 18 }}>
            <div className="sk-line w-40" />
            <div className="sk-line w-full" />
            <div className="sk-line w-70" />
            <div className="sk-line w-50" />
          </div>
        </div>
      </div>

      <div className="cmp-cards">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="card kpi" aria-busy="true">
            <div className="sk-line sk-sm w-60" />
            <div className="sk-line sk-lg w-30" style={{ margin: "12px 0" }} />
            <div className="sk-line sk-sm w-80" />
          </div>
        ))}
      </div>
    </div>
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
  // Campanha & Alcance é independente do dashboard de NPS: se /campanha/stats
  // falhar, o bloco some sem derrubar os KPIs/NPS que já funcionam.
  const [cmp, setCmp] = useState<CampanhaStats | null>(null);
  // Voz do cliente & Tarefas: cada endpoint é best-effort e independente — uma
  // falha derruba só a sua sub-seção, nunca a tela.
  const [voz, setVoz] = useState<VozTarefasSnapshot>({
    feedbacks: null,
    tarefas: null,
    clusters: null,
  });

  const load = useCallback(async () => {
    try {
      setData(await api.get<Dashboard>("/api/dashboard"));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
    try {
      setCmp(await campanhaApi.stats());
    } catch {
      /* stats da campanha é best-effort: não polui o erro principal */
    }
    // Cada endpoint da "Voz do cliente & Tarefas" degrada sozinho (null no erro).
    // limit: 1 — só queremos os totais/contagens, não o feed inteiro.
    // days: 3650 — todas as dores da org (não só as recentes do default backend).
    const [fb, tf, cl] = await Promise.all([
      feedbacksApi.list({ limit: 1 }).catch(() => null),
      tarefasApi.list({ limit: 1 }).catch(() => null),
      clustersApi.list({ days: 3650 }).catch(() => null),
    ]);
    setVoz({ feedbacks: fb, tarefas: tf, clusters: cl });
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  // Maior valor entre as etapas do funil — escala as barras proporcionalmente.
  const maxFunil = useMemo(
    () => (cmp ? Math.max(1, ...cmp.funil.map((f) => f.count)) : 1),
    [cmp],
  );

  // Dores (clusters): total e quantas ainda SEM melhoria (improvement_id null).
  const dores = useMemo(() => {
    if (!voz.clusters) return null;
    const lista = voz.clusters.clusters;
    const semMelhoria = lista.filter((c) => c.improvement_id === null).length;
    return { total: lista.length, semMelhoria };
  }, [voz.clusters]);

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

  if (!data) return <DashboardSkeleton />;

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

      <Reveal className="card hero-nps">
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
      </Reveal>

      {cmp && (
        <>
          {/* Cards de números: universo + recorte com/sem WhatsApp real */}
          <Stagger className="cmp-cards" delayChildren={0.08}>
            <StaggerItem className="card kpi">
              <div className="kpi-label">Universo</div>
              <div className="kpi-value">{cmp.universo}</div>
              <div className="kpi-hint">clientes que cancelaram</div>
              <div className="cmp-wa-split">
                <span
                  className="cmp-wa wa-on"
                  title="Alcançáveis no WhatsApp = celular BR válido (fixo e grupo NÃO contam)"
                >
                  {"\u{1F4AC}"} {cmp.com_whatsapp} com WhatsApp
                </span>
                <span
                  className="cmp-wa wa-off"
                  title="Resto do universo: só e-mail, fixo, grupo, sem contato ou inválido"
                >
                  {"\u{2709}\u{FE0F}"} {cmp.sem_whatsapp} sem WhatsApp
                </span>
              </div>
            </StaggerItem>
            <StaggerItem className="card kpi">
              <div className="kpi-label">Contatados</div>
              <div className="kpi-value">{cmp.contatados}</div>
              <div className="kpi-hint">
                {cmp.universo > 0
                  ? `${Math.round(cmpPct(cmp.contatados, cmp.universo))}% do universo`
                  : "—"}
              </div>
            </StaggerItem>
            <StaggerItem className="card kpi">
              <div className="kpi-label">Responderam</div>
              <div className="kpi-value">{cmp.responderam}</div>
              <div className="kpi-hint">voltaram a falar com a gente</div>
            </StaggerItem>
            <StaggerItem className="card kpi">
              <div className="kpi-label">Cortesia</div>
              <div className="kpi-value">{cmp.cortesia}</div>
              <div className="kpi-hint">ganharam a oferta</div>
            </StaggerItem>
            <StaggerItem className="card kpi">
              <div className="kpi-label">Reativaram</div>
              <div className="kpi-value cmp-reativou">{cmp.reativaram}</div>
              <div className="kpi-hint">voltaram a assinar</div>
            </StaggerItem>
          </Stagger>

          {/* Quebra do universo por alcance (some se a API não mandar por_alcance) */}
          {(() => {
            const porAlcance = cmp.por_alcance ?? {};
            const rows = ALCANCE_META.filter((m) => (porAlcance[m.key] ?? 0) > 0).map(
              (m) => ({ ...m, n: porAlcance[m.key] as number }),
            );
            if (rows.length === 0) return null;
            return (
              <Reveal className="card cmp-block">
                <div className="card-head">
                  <div>
                    <div className="section-title">Campanha &amp; Alcance</div>
                    <div className="card-head-sub">
                      como dá pra falar com cada um dos {cmp.universo} cancelados ·{" "}
                      <strong>com WhatsApp</strong> = só celular BR válido (fixo e grupo
                      NÃO contam)
                    </div>
                  </div>
                </div>
                <div className="cmp-pad">
                  <ul className="cmp-canal-list reveal-stagger">
                    {rows.map((r) => (
                      <li key={r.key} className="cmp-canal-row reveal">
                        <span className="cmp-canal-name">
                          <span aria-hidden="true">{r.emoji} </span>
                          {r.label}
                        </span>
                        <span className="cmp-alcance-meta">
                          <span className="cmp-canal-n mono" style={{ color: r.cor }}>
                            {r.n}
                          </span>
                          <span className="cmp-alcance-pct">
                            {Math.round(cmpPct(r.n, cmp.universo))}%
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            );
          })()}

          {/* Funil da campanha — a contatar → contatado → respondeu → cortesia → reativou */}
          {cmp.funil.length > 0 && (
            <Reveal className="card cmp-block">
              <div className="card-head">
                <div>
                  <div className="section-title">Funil da campanha</div>
                  <div className="card-head-sub">
                    do universo de cancelados até a reativação · {cmp.faltam} ainda a
                    contatar · {cmp.com_whatsapp} com WhatsApp, {cmp.sem_whatsapp} sem
                    WhatsApp
                  </div>
                </div>
              </div>
              <div className="cmp-funnel reveal-stagger">
                {cmp.funil.map((f) => (
                  <div className="cmp-fn-step reveal" key={f.etapa}>
                    <div className="cmp-fn-top">
                      <span className="cmp-fn-label">{f.etapa}</span>
                      <span className="cmp-fn-n mono">{f.count}</span>
                    </div>
                    <div className="cmp-fn-track">
                      <span
                        className="cmp-fn-fill"
                        style={{
                          width: `${cmpPct(f.count, maxFunil)}%`,
                          background: CMP_ETAPA_META[f.etapa]?.cor ?? "var(--indigo)",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Reveal>
          )}
        </>
      )}

      {/* Voz do cliente & Tarefas — pulso operacional puxado de endpoints já
          existentes (feedbacks/tarefas/clusters). Cada sub-bloco degrada sozinho:
          se o endpoint falhou, o snapshot é null e a sub-seção some. */}
      {(voz.feedbacks || voz.tarefas || dores) && (
        <Reveal className="card cmp-block">
          <div className="card-head">
            <div>
              <div className="section-title">Voz do cliente &amp; Tarefas</div>
              <div className="card-head-sub">
                fila a triar, tarefas de CS em aberto e quantas dores ainda sem
                melhoria · pulso operacional do loop
              </div>
            </div>
          </div>
          <div className="cmp-pad" style={{ display: "grid", gap: 18 }}>
            {/* Feedbacks — total + fila a triar (novo) e quebra por status */}
            {voz.feedbacks && (() => {
              const c = voz.feedbacks.counts_by_status;
              const linhas: { label: string; n: number; cor: string }[] = [
                { label: "A abordar", n: c.a_abordar, cor: "var(--detractor)" },
                { label: "Em acompanhamento", n: c.em_acompanhamento, cor: "var(--gold)" },
                { label: "Resolvidos", n: c.resolvido, cor: "var(--indigo-light)" },
              ];
              return (
                <div>
                  <div className="hero-dist-head" style={{ marginBottom: 10 }}>
                    <span className="hero-eyebrow">
                      {"\u{1F4E5}"} Feedbacks
                    </span>
                    <span className="hero-dist-total mono">
                      {voz.feedbacks.total} no total
                    </span>
                  </div>
                  <ul className="cmp-canal-list">
                    {linhas.map((r) => (
                      <li key={r.label} className="cmp-canal-row">
                        <span className="cmp-canal-name">{r.label}</span>
                        <span className="cmp-canal-n mono" style={{ color: r.cor }}>
                          {r.n}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })()}

            {/* Tarefas de CS — total + por status (aberta/em_andamento/concluida) */}
            {voz.tarefas && (() => {
              const c = voz.tarefas.counts_by_status;
              const linhas: { label: string; n: number; cor: string }[] = [
                { label: "Abertas", n: c.aberta, cor: "var(--gold)" },
                { label: "Em andamento", n: c.em_andamento, cor: "var(--indigo-light)" },
                { label: "Concluídas", n: c.concluida, cor: "var(--text-dim)" },
              ];
              return (
                <div>
                  <div className="hero-dist-head" style={{ marginBottom: 10 }}>
                    <span className="hero-eyebrow">
                      {"\u{2705}"} Tarefas de CS
                    </span>
                    <span className="hero-dist-total mono">
                      {voz.tarefas.total} no total
                    </span>
                  </div>
                  <ul className="cmp-canal-list">
                    {linhas.map((r) => (
                      <li key={r.label} className="cmp-canal-row">
                        <span className="cmp-canal-name">{r.label}</span>
                        <span className="cmp-canal-n mono" style={{ color: r.cor }}>
                          {r.n}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })()}

            {/* Dores (clusters) — total + quantas ainda SEM melhoria vinculada */}
            {dores && (
              <div>
                <div className="hero-dist-head" style={{ marginBottom: 10 }}>
                  <span className="hero-eyebrow">
                    {"\u{1F525}"} Dores mapeadas
                  </span>
                  <span className="hero-dist-total mono">
                    {dores.total} no total
                  </span>
                </div>
                <ul className="cmp-canal-list">
                  <li className="cmp-canal-row">
                    <span className="cmp-canal-name">Sem melhoria no roadmap</span>
                    <span
                      className="cmp-alcance-meta"
                      title="Dores (clusters) que ainda não viraram melhoria (improvement_id nulo)"
                    >
                      <span
                        className="cmp-canal-n mono"
                        style={{ color: dores.semMelhoria > 0 ? "var(--detractor)" : "var(--indigo-light)" }}
                      >
                        {dores.semMelhoria}
                      </span>
                      <span className="cmp-alcance-pct">
                        de {dores.total}
                      </span>
                    </span>
                  </li>
                </ul>
              </div>
            )}
          </div>
        </Reveal>
      )}

      <Reveal className="card exit-card">
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
            <div className="empty-illu">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                <path d="M9 10h6" />
              </svg>
            </div>
            <div className="empty-title">Nenhum cancelamento respondido</div>
            <p className="empty-sub">
              Quando alguém responder a exit survey ao cancelar, o motivo aparece aqui.
            </p>
          </div>
        ) : (
          <ul className="exit-list reveal-stagger">
            {exit.recent.map((m, i) => (
              <li
                key={i}
                className="exit-item reveal"
                style={{ ["--i" as string]: i } as React.CSSProperties}
              >
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
      </Reveal>

      <Reveal className="card" delay={0.05}>
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
                      <div className="empty-illu">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M4 4h16v12H5.2L4 17.2z" />
                          <path d="M8 9h8M8 12h5" />
                        </svg>
                      </div>
                      <div className="empty-title">Nenhuma pesquisa enviada ainda</div>
                      <p className="empty-sub">
                        Crie uma pesquisa em <b>Pesquisas</b> e dispare para começar a ouvir os clientes.
                      </p>
                    </div>
                  </td>
                </tr>
              )}
              {data.recent.map((r, i) => (
                <tr
                  key={r.id}
                  className="reveal"
                  style={{ ["--i" as string]: i } as React.CSSProperties}
                >
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
      </Reveal>
    </div>
  );
}
