"use client";

// ============================================================================
// ScatterMap — "Mapa de dores" 2D (scatter + lista rankeada) do /mapeamento.
// SVG inline puro (viewBox responsivo), zero lib nova, cores só via var(--…).
// Eixo X = volume (clientes) · Eixo Y = impacto 0–100 (índice de prioridade).
// Quadrantes com rótulo de AÇÃO (ATACAR AGORA…) — o gráfico vira decisão.
// Degradação graciosa: sem priority_index/distinct/paying cai em
// pain_score/item_count/dominant_sentiment (idêntico aos cards). Nunca lança.
// ============================================================================

import { type CSSProperties, useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { FeedbackCluster } from "@/lib/api";

// ---- geometria do SVG (números da spec §2/§11) -----------------------------
const VB_W = 800;
const VB_H = 500;
const M_L = 56;
const M_R = 24;
const M_T = 28;
const M_B = 52;
const PLOT_X0 = M_L; // 56
const PLOT_X1 = VB_W - M_R; // 776
const PLOT_Y0 = M_T; // 28
const PLOT_Y1 = VB_H - M_B; // 448
const R_MIN = 6;
const R_MAX = 26;
const VOLUME_REF = 10; // app/domain/prioridade.py:volume_ref → divisória X em /2 = 5

type Band = "alta" | "media" | "baixa";

// Tokens de cor por band (todos existentes em globals.css — zero cor nova).
const BAND_FILL: Record<Band, string> = {
  alta: "var(--detractor)",
  media: "var(--gold-fill)",
  baixa: "var(--indigo)",
};
const BAND_STROKE: Record<Band, string> = {
  alta: "var(--detractor-line)",
  media: "var(--passive-line)",
  baixa: "var(--promoter-line)",
};
const BAND_STROKE_W: Record<Band, number> = { alta: 2, media: 1.5, baixa: 1.5 };
// Cor de texto/índice na lista (AA garantido — âmbar puro não passa em texto).
const BAND_TEXT: Record<Band, string> = {
  alta: "var(--detractor)",
  media: "var(--gold)",
  baixa: "var(--indigo-light)",
};
const BAND_LABEL: Record<Band, string> = { alta: "Alta", media: "Média", baixa: "Baixa" };

// ---- helpers numéricos (puros, à prova de null) ----------------------------
function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

/** Arredonda o teto para um número "redondo" (1/2/5 × 10^n) — eixo legível. */
function niceCeil(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = Math.pow(10, exp);
  const f = v / base;
  const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return nf * base;
}

function median(nums: number[]): number {
  if (nums.length === 0) return 0;
  const s = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[mid];
}

/** Percentil simples (0–100) sobre cópia ordenada. */
function percentile(nums: number[], p: number): number {
  if (nums.length === 0) return 0;
  const s = [...nums].sort((a, b) => a - b);
  const idx = clamp(Math.round((p / 100) * (s.length - 1)), 0, s.length - 1);
  return s[idx];
}

/** Band do cluster; ausente → deriva do sentimento dominante (fallback §5). */
function deriveBand(c: FeedbackCluster): Band {
  const b = c.priority_band;
  if (b === "alta" || b === "media" || b === "baixa") return b;
  if (c.dominant_sentiment === "negativo") return "alta";
  if (c.dominant_sentiment === "positivo") return "baixa";
  return "media"; // neutro/null
}

/** Volume bruto = distinct_customers ?? item_count (item_count nunca null). */
function volumeOf(c: FeedbackCluster): number {
  return c.distinct_customers ?? c.item_count;
}

// ---- ponto pré-calculado (uma passada de O(n)) -----------------------------
interface Pt {
  c: FeedbackCluster;
  band: Band;
  cx: number;
  cy: number;
  r: number;
  vol: number;
  /** Impacto 0–100 já resolvido pela cascata de fallback (§3). */
  impact: number;
  /** Ponto sem sentimento medido (volume mas neg_count 0 e sem prioridade). */
  pending: boolean;
  /** Rótulo do quadrante ("ATACAR AGORA"…) para tooltip/aria. */
  quadrant: string;
}

const QUAD = {
  attack: "ATACAR AGORA",
  watch: "VIGIAR / NICHO",
  plan: "PLANEJAR",
  monitor: "MONITORAR",
} as const;

export default function ScatterMap({ clusters }: { clusters: FeedbackCluster[] }) {
  const router = useRouter();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const activeId = hoveredId ?? pinnedId;

  // --- pré-cálculo de escalas + posições (memo: só refaz se a lista mudar) ---
  const model = useMemo(() => {
    const volumes = clusters.map(volumeOf);
    const xRaw = volumes.filter((v) => Number.isFinite(v));
    const xMax = xRaw.length ? Math.max(...xRaw) : 0;
    // 1–2 clusters: garante régua mínima 10 (spec §10).
    const xMaxEff = Math.max(niceCeil(xMax), 10);
    // Cauda longa → sqrt (comprime sem opacidade enganosa do log). Começa linear.
    const xMed = median(xRaw);
    const useSqrt = xMed > 0 && xMax / xMed > 8;

    const scaleX = (v: number): number => {
      const t = useSqrt
        ? Math.sqrt(clamp(v, 0, xMaxEff)) / Math.sqrt(xMaxEff)
        : clamp(v, 0, xMaxEff) / xMaxEff;
      return PLOT_X0 + t * (PLOT_X1 - PLOT_X0);
    };

    // Y é régua FIXA 0–100 invertida (100 no topo) — comparável entre sessões.
    const maxPain = Math.max(1, ...clusters.map((c) => c.pain_score));
    const impactOf = (c: FeedbackCluster): number => {
      if (typeof c.priority_index === "number") return clamp(c.priority_index, 0, 100);
      const g = c.priority_breakdown?.gravity_score;
      if (typeof g === "number") return clamp(g * 100, 0, 100);
      return clamp((100 * c.pain_score) / maxPain, 0, 100);
    };
    const scaleY = (impact: number): number =>
      PLOT_Y1 - (clamp(impact, 0, 100) / 100) * (PLOT_Y1 - PLOT_Y0);

    // Raio = paying_customers (área ∝ valor). Todos 0 → raio fixo (não mente).
    const pays = clusters.map((c) => c.paying_customers ?? 0);
    const hasRevenue = pays.some((p) => p > 0);
    const payRef = Math.max(8, percentile(pays, 90));
    const radiusOf = (pay: number): number =>
      hasRevenue
        ? R_MIN + (R_MAX - R_MIN) * Math.sqrt(clamp(pay, 0, payRef) / payRef)
        : 9;

    // Divisória X: max(5, xMaxEff/2) = volume_ref/2 de prioridade.py.
    const xDivVal = Math.max(VOLUME_REF / 2, xMaxEff / 2);
    const xDivPx = scaleX(xDivVal);
    const yDivPx = scaleY(50); // ponto médio do índice

    const pts: Pt[] = clusters.map((c) => {
      const band = deriveBand(c);
      const vol = volumeOf(c);
      const impact = impactOf(c);
      const r = radiusOf(c.paying_customers ?? 0);
      // Clamp do centro para a bolha nunca vazar nem ser cortada (§2).
      const cx = clamp(scaleX(vol), PLOT_X0 + R_MAX, PLOT_X1 - R_MAX);
      const cy = clamp(scaleY(impact), PLOT_Y0 + R_MAX, PLOT_Y1 - R_MAX);
      const pending =
        c.priority_index === undefined && c.neg_count === 0 && vol > 0;
      const hiVol = vol >= xDivVal;
      const hiImpact = impact >= 50;
      const quadrant = hiImpact
        ? hiVol
          ? QUAD.attack
          : QUAD.watch
        : hiVol
          ? QUAD.plan
          : QUAD.monitor;
      return { c, band, cx, cy, r, vol, impact, pending, quadrant };
    });

    // Lista ordenada por priority_index desc (fallback pain_score) — ranking
    // exato mesmo quando o eixo Y caiu em fallback.
    const ranked = [...pts].sort((a, b) => {
      const ai = a.c.priority_index ?? a.c.pain_score;
      const bi = b.c.priority_index ?? b.c.pain_score;
      return bi - ai;
    });

    // Ticks de X em valores ORIGINAIS (mesmo com sqrt no posicionamento).
    const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const val = Math.round(f * xMaxEff);
      return { val, px: scaleX(val) };
    });

    return { hasRevenue, xDivPx, yDivPx, pts, ranked, xTicks, xMaxEff, useSqrt };
  }, [clusters]);

  // Mapa id→ponto para o realce cruzado lista↔scatter.
  const byId = useMemo(() => {
    const m = new Map<string, Pt>();
    for (const p of model.pts) m.set(p.c.id, p);
    return m;
  }, [model.pts]);

  const onPick = useCallback(
    (id: string) => {
      setPinnedId((cur) => (cur === id ? null : id));
      router.push(`/feedbacks?cluster_id=${encodeURIComponent(id)}`);
    },
    [router],
  );

  // Retorna null se houver < 2 clusters com dados (spec: não desenha vazio).
  if (clusters.length < 2) return null;

  const active = activeId ? byId.get(activeId) ?? null : null;
  const yTicks = [0, 25, 50, 75, 100];

  return (
    <div className="map2d">
      {/* ---- coluna esquerda: scatter ---- */}
      <div className="map2d-plot card">
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          preserveAspectRatio="xMidYMid meet"
          role="group"
          aria-label="Mapa de dores: volume de clientes por impacto"
          style={{ width: "100%", height: "auto", display: "block" }}
        >
          {/* fundos de quadrante (atrás de tudo) */}
          <rect
            x={model.xDivPx}
            y={PLOT_Y0}
            width={PLOT_X1 - model.xDivPx}
            height={model.yDivPx - PLOT_Y0}
            fill="var(--detractor-soft)"
          />
          <rect
            x={model.xDivPx}
            y={PLOT_Y0}
            width={PLOT_X1 - model.xDivPx}
            height={model.yDivPx - PLOT_Y0}
            fill="none"
            stroke="var(--detractor-line)"
            strokeWidth={1}
          />
          <rect
            x={PLOT_X0}
            y={PLOT_Y0}
            width={model.xDivPx - PLOT_X0}
            height={model.yDivPx - PLOT_Y0}
            fill="var(--passive-soft)"
          />
          <rect
            x={model.xDivPx}
            y={model.yDivPx}
            width={PLOT_X1 - model.xDivPx}
            height={PLOT_Y1 - model.yDivPx}
            fill="var(--promoter-soft)"
          />
          {/* inf-esq MONITORAR = transparente (sem rect) */}

          {/* rótulos de ação por quadrante (uppercase, ghost, atrás dos pontos) */}
          <text x={PLOT_X1 - 8} y={PLOT_Y0 + 16} textAnchor="end" className="map2d-quad">
            {QUAD.attack}
          </text>
          <text x={PLOT_X0 + 8} y={PLOT_Y0 + 16} textAnchor="start" className="map2d-quad">
            {QUAD.watch}
          </text>
          <text x={PLOT_X1 - 8} y={PLOT_Y1 - 8} textAnchor="end" className="map2d-quad">
            {QUAD.plan}
          </text>
          <text x={PLOT_X0 + 8} y={PLOT_Y1 - 8} textAnchor="start" className="map2d-quad">
            {QUAD.monitor}
          </text>

          {/* grade horizontal (impacto) + ticks Y */}
          {yTicks.map((t) => {
            const py = PLOT_Y1 - (t / 100) * (PLOT_Y1 - PLOT_Y0);
            return (
              <g key={`y${t}`}>
                <line
                  x1={PLOT_X0}
                  y1={py}
                  x2={PLOT_X1}
                  y2={py}
                  stroke="var(--charcoal)"
                  strokeWidth={1}
                />
                <text x={PLOT_X0 - 8} y={py + 4} textAnchor="end" className="map2d-tick">
                  {t}
                </text>
              </g>
            );
          })}

          {/* ticks X (valores originais) */}
          {model.xTicks.map((t, i) => (
            <text
              key={`x${i}`}
              x={t.px}
              y={PLOT_Y1 + 18}
              textAnchor="middle"
              className="map2d-tick"
            >
              {t.val}
            </text>
          ))}

          {/* divisórias medianas (semânticas, tracejadas) */}
          <line
            x1={PLOT_X0}
            y1={model.yDivPx}
            x2={PLOT_X1}
            y2={model.yDivPx}
            stroke="var(--charcoal-2)"
            strokeWidth={1}
            strokeDasharray="4 4"
            opacity={0.7}
          />
          <line
            x1={model.xDivPx}
            y1={PLOT_Y0}
            x2={model.xDivPx}
            y2={PLOT_Y1}
            stroke="var(--charcoal-2)"
            strokeWidth={1}
            strokeDasharray="4 4"
            opacity={0.7}
          />

          {/* eixos */}
          <line x1={PLOT_X0} y1={PLOT_Y1} x2={PLOT_X1} y2={PLOT_Y1} stroke="var(--charcoal-2)" strokeWidth={1} />
          <line x1={PLOT_X0} y1={PLOT_Y0} x2={PLOT_X0} y2={PLOT_Y1} stroke="var(--charcoal-2)" strokeWidth={1} />

          {/* títulos dos eixos */}
          <text x={(PLOT_X0 + PLOT_X1) / 2} y={VB_H - 14} textAnchor="middle" className="map2d-axis">
            {model.useSqrt ? "Volume de clientes (escala √)" : "Volume de clientes"}
          </text>
          <text
            x={16}
            y={(PLOT_Y0 + PLOT_Y1) / 2}
            textAnchor="middle"
            className="map2d-axis"
            transform={`rotate(-90 16 ${(PLOT_Y0 + PLOT_Y1) / 2})`}
          >
            Impacto (0–100)
          </text>

          {/* pontos — ativo por último (z-order), demais esmaecem */}
          {model.pts
            .slice()
            .sort((a, b) => (a.c.id === activeId ? 1 : b.c.id === activeId ? -1 : 0))
            .map((p) => {
              const isActive = p.c.id === activeId;
              const dim = activeId !== null && !isActive ? 0.35 : 1;
              const fill = p.pending ? "var(--text-ghost)" : BAND_FILL[p.band];
              const stroke = p.pending ? "var(--text-ghost)" : BAND_STROKE[p.band];
              const idx =
                typeof p.c.priority_index === "number"
                  ? Math.round(p.c.priority_index)
                  : p.c.pain_score.toFixed(1);
              return (
                <g
                  key={p.c.id}
                  opacity={dim}
                  tabIndex={0}
                  role="img"
                  aria-label={`${p.c.label ?? "Cluster sem rótulo"}: ${p.vol} clientes, impacto ${Math.round(p.impact)}/100, prioridade ${BAND_LABEL[p.band]}`}
                  onMouseEnter={() => setHoveredId(p.c.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onFocus={() => setHoveredId(p.c.id)}
                  onBlur={() => setHoveredId(null)}
                  onClick={() => onPick(p.c.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onPick(p.c.id);
                    } else if (e.key === "Escape") {
                      setPinnedId(null);
                    }
                  }}
                  style={{ cursor: "pointer" }}
                >
                  {/* hit-area de toque invisível (r ≥ 16) */}
                  <circle cx={p.cx} cy={p.cy} r={Math.max(p.r, 16)} fill="transparent" />
                  {isActive && (
                    <circle
                      cx={p.cx}
                      cy={p.cy}
                      r={p.r * 1.5 + 4}
                      fill="none"
                      stroke="var(--indigo)"
                      strokeWidth={2}
                      opacity={0.5}
                    />
                  )}
                  <circle
                    cx={p.cx}
                    cy={p.cy}
                    r={isActive ? p.r * 1.5 : p.r}
                    fill={fill}
                    fillOpacity={0.55}
                    stroke={stroke}
                    strokeWidth={BAND_STROKE_W[p.band]}
                    strokeDasharray={p.pending ? "3 3" : undefined}
                  />
                  <title>{`${p.c.label ?? "Cluster sem rótulo"} · ${p.quadrant} · ${p.vol} clientes · idx ${idx}`}</title>
                </g>
              );
            })}
        </svg>

        {/* tooltip HTML (tipografia/sombra reais) — só quando há ativo */}
        {active && (
          <TooltipCard pt={active} />
        )}

        {/* legenda (uma linha) */}
        <div className="map2d-legend">
          <span style={{ color: "var(--detractor)" }}>●</span> Alta
          <span className="map2d-sep">·</span>
          <span style={{ color: "var(--gold-fill)" }}>●</span> Média
          <span className="map2d-sep">·</span>
          <span style={{ color: "var(--indigo)" }}>●</span> Baixa
          {model.hasRevenue && (
            <>
              <span className="map2d-sep">·</span>
              <span style={{ color: "var(--text-faint)" }}>● ⬤</span> tamanho = pagantes
            </>
          )}
        </div>
      </div>

      {/* ---- coluna direita: lista rankeada ---- */}
      <ul className="map2d-list card" role="listbox" aria-label="Dores ordenadas por prioridade">
        {model.ranked.map((p, i) => {
          const isActive = p.c.id === activeId;
          const rank = i + 1;
          // Número e barra (idxPct) compartilham a MESMA base 0–100: no fallback sem
          // priority_index usamos p.impact (já normalizado), nunca o pain_score cru —
          // senão a barra contaria uma história e o número outra.
          const idxNum =
            typeof p.c.priority_index === "number"
              ? Math.round(p.c.priority_index)
              : Math.round(p.impact);
          const idxPct = clamp(
            typeof p.c.priority_index === "number" ? p.c.priority_index : p.impact,
            0,
            100,
          );
          return (
            <li
              key={p.c.id}
              role="option"
              aria-selected={isActive}
              tabIndex={0}
              className={`map2d-row${isActive ? " active" : ""}`}
              style={{ borderLeftColor: BAND_FILL[p.band] }}
              onMouseEnter={() => setHoveredId(p.c.id)}
              onMouseLeave={() => setHoveredId(null)}
              onFocus={() => setHoveredId(p.c.id)}
              onBlur={() => setHoveredId(null)}
              onClick={() => onPick(p.c.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onPick(p.c.id);
                } else if (e.key === "Escape") {
                  setPinnedId(null);
                }
              }}
            >
              <span className={`map2d-rank${rank <= 3 ? " top" : ""}`}>{rank}</span>
              <span className="map2d-dot" style={{ background: BAND_FILL[p.band] }} aria-hidden />
              <span className="map2d-label" title={p.c.label ?? "Cluster sem rótulo"}>
                {p.c.label ?? "Cluster sem rótulo"}
                <span className="map2d-sub">
                  📊 {p.c.distinct_customers ?? p.c.item_count} clientes · 💳{" "}
                  {p.c.paying_customers ?? 0} pagantes
                  {p.pending && " · ⏳ sentimento pendente"}
                </span>
                <span className="map2d-track" aria-hidden>
                  <span
                    className="map2d-fill"
                    style={{ width: `${idxPct}%`, background: BAND_FILL[p.band] }}
                  />
                </span>
              </span>
              <span className="map2d-idx" style={{ color: BAND_TEXT[p.band] }}>
                {typeof idxNum === "number" && Number.isInteger(idxNum)
                  ? idxNum
                  : idxNum.toFixed(1)}
              </span>
              <span className="map2d-chev" aria-hidden>▸</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---- tooltip card (posicionado sobre o SVG; anti-overflow esquerda/direita) -
function TooltipCard({ pt }: { pt: Pt }) {
  // % horizontal do ponto na área de plot → decide o lado da abertura.
  const xPct = ((pt.cx - PLOT_X0) / (PLOT_X1 - PLOT_X0)) * 100;
  const yPct = ((pt.cy - PLOT_Y0) / (PLOT_Y1 - PLOT_Y0)) * 100;
  const openLeft = xPct > 70;
  const side: CSSProperties = openLeft
    ? { right: `${100 - xPct}%`, transform: "translate(-8px, -50%)" }
    : { left: `${xPct}%`, transform: "translate(8px, -50%)" };
  const bd = pt.c.priority_breakdown;
  const idxTxt =
    typeof pt.c.priority_index === "number"
      ? `Índice de dor ${Math.round(pt.c.priority_index)}`
      : `Dor ${pt.c.pain_score.toFixed(1)}`;

  return (
    <div
      className="map2d-tip"
      style={{ ...side, top: `${yPct}%` }}
      role="tooltip"
    >
      <div className="map2d-tip-title">
        {pt.c.label ?? "Cluster sem rótulo"}
        <span className="map2d-tip-chip">{pt.quadrant}</span>
      </div>
      <div className="map2d-tip-row mono">
        📊 {pt.c.distinct_customers ?? pt.c.item_count} clientes · 💳 {pt.c.paying_customers ?? 0} pagantes
      </div>
      <div className="map2d-tip-row">{idxTxt}</div>
      {bd && (
        <div className="map2d-tip-row map2d-tip-bd">
          Volume {Math.round(bd.volume_score * 100)}% · Receita {Math.round(bd.revenue_score * 100)}% · Gravidade {Math.round(bd.gravity_score * 100)}%
        </div>
      )}
    </div>
  );
}
