"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type Tema, type ThemesAggregate } from "@/lib/api";

// ===== ordenação ============================================================

type SortKey = "dor" | "volume" | "negativos";

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "dor", label: "Por dor (volume × negatividade)" },
  { key: "volume", label: "Por volume" },
  { key: "negativos", label: "Por nº de negativos" },
];

// ===== períodos =============================================================

const PERIOD_OPTIONS: { days: number; label: string }[] = [
  { days: 7, label: "Últimos 7 dias" },
  { days: 30, label: "Últimos 30 dias" },
  { days: 90, label: "Últimos 90 dias" },
];

// ===== helpers de cálculo ===================================================

/** Fração negativa do tema (0–1). Usada para o "índice de dor" e o destaque. */
function negShare(t: Tema): number {
  return t.count > 0 ? t.sentiment.negativo / t.count : 0;
}

/** Índice de dor: volume ponderado pela negatividade. Prioriza o que dói mais. */
function painScore(t: Tema): number {
  return t.count * negShare(t);
}

/** Compara temas pela chave de ordenação (desc). Desempata por volume. */
function compareThemes(a: Tema, b: Tema, key: SortKey): number {
  let av: number;
  let bv: number;
  if (key === "volume") {
    av = a.count;
    bv = b.count;
  } else if (key === "negativos") {
    av = a.sentiment.negativo;
    bv = b.sentiment.negativo;
  } else {
    av = painScore(a);
    bv = painScore(b);
  }
  if (bv !== av) return bv - av;
  return b.count - a.count;
}

const fmtNum = new Intl.NumberFormat("pt-BR");

// ===== barra de distribuição de sentimento ==================================

const SENT_SEGMENTS: { key: keyof Tema["sentiment"]; cls: string; label: string }[] = [
  { key: "negativo", cls: "neg", label: "negativo" },
  { key: "neutro", cls: "neu", label: "neutro" },
  { key: "positivo", cls: "pos", label: "positivo" },
];

function SentimentBar({ tema }: { tema: Tema }) {
  const { positivo, neutro, negativo } = tema.sentiment;
  const known = positivo + neutro + negativo;
  // Quando a IA ainda não classificou tudo, o resto vira "sem classificação".
  const unclassified = Math.max(0, tema.count - known);
  const total = known + unclassified || 1;

  return (
    <div className="tema-sent">
      <div
        className="tema-sent-bar"
        role="img"
        aria-label={`Sentimento: ${negativo} negativo, ${neutro} neutro, ${positivo} positivo${
          unclassified ? `, ${unclassified} sem classificação` : ""
        }`}
      >
        {SENT_SEGMENTS.map((s) => {
          const v = tema.sentiment[s.key];
          if (!v) return null;
          return (
            <span
              key={s.key}
              className={`seg ${s.cls}`}
              style={{ width: `${(v / total) * 100}%` }}
            />
          );
        })}
        {unclassified > 0 && (
          <span className="seg none" style={{ width: `${(unclassified / total) * 100}%` }} />
        )}
      </div>
      <div className="tema-sent-legend">
        {SENT_SEGMENTS.map((s) => {
          const v = tema.sentiment[s.key];
          if (!v) return null;
          return (
            <span key={s.key} className={`leg ${s.cls}`}>
              <span className="dot" />
              {fmtNum.format(v)} {s.label}
              {v === 1 ? "" : "s"}
            </span>
          );
        })}
        {unclassified > 0 && (
          <span className="leg none">
            <span className="dot" />
            {fmtNum.format(unclassified)} sem classificação
          </span>
        )}
      </div>
    </div>
  );
}

// ===== card de um tema ======================================================

function TemaCard({ tema, rank, maxCount }: { tema: Tema; rank: number; maxCount: number }) {
  const neg = tema.sentiment.negativo;
  const share = negShare(tema);
  // Dor "alta" = bom volume com maioria negativa. Vira destaque visual.
  const isPain = neg >= 2 && share >= 0.5;
  const barPct = maxCount > 0 ? Math.max(6, (tema.count / maxCount) * 100) : 0;

  return (
    <div className={`card tema-card ${isPain ? "is-pain" : ""}`}>
      <div className="tema-head">
        <span className={`tema-rank ${rank <= 3 ? "top" : ""}`} aria-hidden>
          {rank}
        </span>
        <h2 className="tema-name" title={tema.name}>
          {tema.name}
        </h2>
        {isPain && (
          <span className="badge detractor tema-flag" title="Volume relevante com maioria negativa">
            🔥 dor a priorizar
          </span>
        )}
        <span className="tema-count" title="Feedbacks que citaram este tema no período">
          {fmtNum.format(tema.count)}
          <span className="tema-count-unit">
            {tema.count === 1 ? "menção" : "menções"}
          </span>
        </span>
      </div>

      {/* barra de volume relativo ao tema mais citado */}
      <div className="tema-volume" aria-hidden>
        <span className="tema-volume-fill" style={{ width: `${barPct}%` }} />
      </div>

      <SentimentBar tema={tema} />

      <div className="tema-foot">
        {/* Deep-link best-effort: o filtro do inbox busca no TEXTO/nome, não na tag de
            tema, então pode não casar 1:1. Ainda assim é o caminho mais útil hoje. */}
        <Link
          href={`/feedbacks?search=${encodeURIComponent(tema.name)}`}
          className="tema-link"
        >
          Ver feedbacks deste tema
          <span aria-hidden> →</span>
        </Link>
      </div>
    </div>
  );
}

// ===== página ===============================================================

export default function TemasPage() {
  const [data, setData] = useState<ThemesAggregate | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [days, setDays] = useState(30);
  const [sort, setSort] = useState<SortKey>("dor");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await api.get<ThemesAggregate>(`/api/themes/aggregate?days=${days}`);
      setData(raw);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const themes = data?.themes ?? [];

  // Ordenação derivada durante o render (sem efeito/estado extra). toSorted é
  // imutável — não pisa no array original do estado.
  const sorted = useMemo(
    () => themes.toSorted((a, b) => compareThemes(a, b, sort)),
    [themes, sort],
  );

  const maxCount = useMemo(
    () => themes.reduce((m, t) => Math.max(m, t.count), 0),
    [themes],
  );

  // Total de menções negativas no período — número-âncora da tela.
  const totalNeg = useMemo(
    () => themes.reduce((s, t) => s + t.sentiment.negativo, 0),
    [themes],
  );

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Temas</h1>
          <div className="page-sub">
            O que mais aparece nos feedbacks, agrupado por tema — priorize as dores
          </div>
        </div>
        {!loading && !err && themes.length > 0 && (
          <span className="refresh-note">
            {fmtNum.format(themes.length)}{" "}
            {themes.length === 1 ? "tema" : "temas"} · {fmtNum.format(totalNeg)} negativos
          </span>
        )}
      </div>

      <div className="note">
        <span className="note-ico">💡</span>
        <span>
          Os temas são extraídos e normalizados pela IA a partir do texto dos feedbacks.
          Conforme mais respostas são classificadas, o ranking fica mais rico — quem tem{" "}
          <b>volume e maioria negativa</b> é o que mais vale corrigir no produto.
        </span>
      </div>

      <div className="toolbar">
        <label className="tema-control">
          <span className="tema-control-lbl">Período</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            aria-label="Período de análise"
          >
            {PERIOD_OPTIONS.map((p) => (
              <option key={p.days} value={p.days}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="tema-control">
          <span className="tema-control-lbl">Ordenar</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            aria-label="Ordenar temas"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar os temas ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {!err && sorted.length === 0 ? (
        <div className="card">
          <div className="empty">
            <div className="big">🏷️</div>
            {loading
              ? "Carregando temas…"
              : "Nenhum tema classificado neste período ainda."}
            {!loading && (
              <div className="empty-sub">
                Os temas aparecem aqui assim que a IA classificar os feedbacks. Tente um
                período maior ou volte depois de novas respostas.
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="tema-grid">
          {sorted.map((t, i) => (
            <TemaCard key={t.name} tema={t} rank={i + 1} maxCount={maxCount} />
          ))}
        </div>
      )}
    </div>
  );
}
