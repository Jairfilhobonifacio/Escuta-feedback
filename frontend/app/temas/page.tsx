"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  api,
  type ClustersResponse,
  type ClustersSort,
  type FeedbackCluster,
  type Improvement,
  type Tema,
  type ThemesAggregate,
} from "@/lib/api";
import { Stagger, StaggerItem } from "@/components/Motion";
import { Button } from "@/components/ui/button";

// ===== abas (por tag × por significado) =====================================

type TabKey = "tags" | "clusters";

// ===== ordenação ============================================================

type SortKey = "dor" | "volume" | "negativos";

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "dor", label: "Por dor (volume × negatividade)" },
  { key: "volume", label: "Por volume" },
  { key: "negativos", label: "Por nº de negativos" },
];

// Ordenação do "Mapa de dores" (clusters). O backend (F1) ordena por
// `priority_index` quando recebe `sort=prioridade` (default da tela).
const CLUSTER_SORT_OPTIONS: { key: ClustersSort; label: string }[] = [
  { key: "prioridade", label: "Por prioridade" },
  { key: "dor", label: "Por dor (volume × negatividade)" },
  { key: "volume", label: "Por volume" },
  { key: "recente", label: "Mais recentes" },
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

// ===== prioridade da dor (selo + barra do índice) ===========================
// O índice (volume × receita × gravidade) vem PRONTO do backend (F1) em
// `priority_index`/`priority_band`. Aqui só traduzimos a banda em selo visual.
// Tudo é tolerante à ausência dos campos: backend antigo → fallback gracioso.

type PriorityBand = "alta" | "media" | "baixa";

/** Selo de prioridade: rótulo, ícone (SVG da marca) e classe de cor do card. */
const PRIORITY_SELO: Record<
  PriorityBand,
  { label: string; icon: string; cls: string; alt: string }
> = {
  alta: { label: "Prioridade Alta", icon: "/illustrations/priority-alta.svg", cls: "pri-alta", alt: "Prioridade alta" },
  media: { label: "Prioridade Média", icon: "/illustrations/priority-media.svg", cls: "pri-media", alt: "Prioridade média" },
  baixa: { label: "Prioridade Baixa", icon: "/illustrations/priority-baixa.svg", cls: "pri-baixa", alt: "Prioridade baixa" },
};

/** Banda só quando o backend a manda E é uma das três conhecidas. */
function priorityBand(cluster: FeedbackCluster): PriorityBand | null {
  const b = cluster.priority_band;
  return b === "alta" || b === "media" || b === "baixa" ? b : null;
}

/** Rótulo PT-BR do sentimento dominante (para a linha "📊/💳/🔴"). */
function sentimentLabel(s: string | null): { txt: string; cls: "neg" | "neu" | "pos" } {
  if (s === "negativo") return { txt: "negativo", cls: "neg" };
  if (s === "positivo") return { txt: "positivo", cls: "pos" };
  return { txt: "neutro", cls: "neu" };
}

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
  // Mesmo "índice de dor" dos clusters (volume × fração negativa): deixa o card
  // de tema legível como entrada de um mapa de dores, não só uma contagem.
  const pain = painScore(tema);
  // Sem nenhum feedback negativo classificado, o índice sai 0.0 mesmo com volume —
  // sinaliza que o sentimento ainda não foi processado, em vez de cravar "0 de dor".
  const knownSent = tema.sentiment.positivo + tema.sentiment.neutro + tema.sentiment.negativo;
  const painPending = neg === 0 && knownSent < tema.count;

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

      {/* Índice de dor (volume × negatividade) — mesma régua e MESMO layout do
          "Mapa de dores": rótulo + trilho proporcional + número (mono) ANCORADO
          no fim da barra (barra + valor = um bloco só). O trilho mostra a fração
          negativa, que é o que puxa o índice. Sem sentimento classificado, vira
          "volume (dor pendente)". */}
      {painPending ? (
        <div
          className="pain-index"
          aria-label={`Sentimento pendente — ${tema.count} menções deste tema`}
        >
          <span className="pain-index-lbl">Volume (dor pendente)</span>
          <span className="pain-index-track" aria-hidden />
          <span className="pain-index-val">{fmtNum.format(tema.count)}</span>
        </div>
      ) : (
        <div className="pain-index" aria-label={`Índice de dor ${pain.toFixed(1)}`}>
          <span className="pain-index-lbl">Índice de dor</span>
          <span className="pain-index-track">
            <span
              className="pain-index-fill"
              style={{ width: `${Math.max(2, Math.round(share * 100))}%` }}
            />
          </span>
          <span className="pain-index-val">{pain.toFixed(1)}</span>
        </div>
      )}

      <SentimentBar tema={tema} />

      <div className="tema-foot">
        {/* Deep-link pelo filtro de tema (JSONB) do inbox — casa com a tag exata
            que a IA colou, não com uma busca textual aproximada. */}
        <Link
          href={`/feedbacks?theme=${encodeURIComponent(tema.name)}`}
          className="tema-link"
        >
          Ver feedbacks deste tema
          <span aria-hidden> →</span>
        </Link>
      </div>
    </div>
  );
}

// ===== card de um cluster (aba "Por significado") ===========================

// Estado da ação "Virar melhoria" de um card de dor.
type PromoteState =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "done"; id: string; title: string }
  | { phase: "error"; msg: string };

function ClusterCard({ cluster, rank }: { cluster: FeedbackCluster; rank: number }) {
  // O índice de prioridade (volume × receita × gravidade) vem PRONTO do backend
  // (F1) em `priority_index`/`priority_band`. Quando o backend ainda não manda
  // esses campos, caímos no índice de dor antigo (pain_score) — fallback gracioso.
  const band = priorityBand(cluster);
  const hasPriority = band !== null && typeof cluster.priority_index === "number";
  const selo = band ? PRIORITY_SELO[band] : null;

  // O sentimento por item só é confiável quando há negativos classificados. Sem isso
  // (neg_count=0 num cluster com volume), pain_score sai 0.0 — sinalizamos "pendente".
  const hasItemSentiment = cluster.neg_count > 0;
  const painPending = !hasPriority && !hasItemSentiment && cluster.item_count > 0;

  // Acento do card pela banda (alta=vermelho, média=âmbar, baixa=indigo). Sem
  // prioridade, mantém a régua antiga: "dor crítica" = vermelho (.is-pain).
  const isCritical =
    !hasPriority &&
    hasItemSentiment &&
    cluster.item_count >= 3 &&
    cluster.dominant_sentiment === "negativo";
  const cardCls = selo ? selo.cls : isCritical ? "is-pain" : "";

  const title = cluster.label ?? "Cluster sem rótulo";
  const sent = sentimentLabel(cluster.dominant_sentiment);

  // Valor e largura da barra. Com prioridade: índice 0–100 → % direta (92 → 92%).
  // Sem prioridade: usa pain_score como antes (sem barra proporcional confiável).
  const indexValue = hasPriority ? (cluster.priority_index as number) : cluster.pain_score;
  const barPct = hasPriority ? Math.max(2, Math.min(100, indexValue)) : 0;

  // Contagens da linha de meta. `distinct_customers`/`paying_customers` são do F1;
  // sem eles, cai para o volume de itens (clientes ≈ feedbacks) — nunca quebra.
  const customers = cluster.distinct_customers ?? cluster.item_count;
  const paying = cluster.paying_customers ?? 0;

  // Já existe uma melhoria pra essa dor? (FK no cluster). Se sim, o botão vira link.
  const [promote, setPromote] = useState<PromoteState>(() =>
    cluster.improvement_id ? { phase: "done", id: cluster.improvement_id, title } : { phase: "idle" },
  );

  // Cria a melhoria a partir da dor: o backend vincula os feedbacks e é idempotente
  // (se a dor já tem melhoria, devolve a mesma). Não recarrega a aba — feedback local.
  async function virarMelhoria() {
    setPromote({ phase: "saving" });
    try {
      const imp = await api.post<Improvement>("/api/improvements/from-cluster", {
        cluster_id: cluster.id,
      });
      setPromote({ phase: "done", id: imp.id, title: imp.title });
    } catch (e) {
      setPromote({ phase: "error", msg: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className={`card tema-card pain-card ${cardCls}`}>
      <div className="pain-head">
        <span className={`tema-rank ${rank <= 3 ? "top" : ""}`} aria-hidden>
          {rank}
        </span>
        <h2 className="tema-name" title={title}>
          {title}
        </h2>

        {/* Selo de prioridade (ícone da marca + rótulo) — empurrado p/ a direita.
            Sem banda do backend, mostramos o estado "sentimento pendente" no lugar. */}
        {selo ? (
          <span
            className={`pri-selo ${selo.cls}`}
            title={
              cluster.priority_breakdown
                ? `Volume ${Math.round(cluster.priority_breakdown.volume_score * 100)}% · ` +
                  `Receita ${Math.round(cluster.priority_breakdown.revenue_score * 100)}% · ` +
                  `Gravidade ${Math.round(cluster.priority_breakdown.gravity_score * 100)}%`
                : selo.label
            }
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="pri-selo-ico" src={selo.icon} alt="" aria-hidden width={14} height={14} />
            {selo.label}
          </span>
        ) : painPending ? (
          <span
            className="badge tema-flag"
            title="Feedbacks ainda sem sentimento classificado pela IA — a prioridade usa volume por enquanto"
          >
            ⏳ sentimento pendente
          </span>
        ) : isCritical ? (
          <span className="badge detractor tema-flag" title="3+ feedbacks predominantemente negativos">
            🔥 dor crítica
          </span>
        ) : null}
      </div>

      {/* Linha de meta: clientes · pagantes · sentimento dominante. */}
      <div className="pain-meta" aria-label={`${customers} clientes, ${paying} pagantes, sentimento ${sent.txt}`}>
        <span className="pain-meta-item">
          📊 <b className="pain-meta-num">{fmtNum.format(customers)}</b>{" "}
          {customers === 1 ? "cliente" : "clientes"}
        </span>
        <span className="pain-meta-sep" aria-hidden>·</span>
        <span className="pain-meta-item">
          💳 <b className="pain-meta-num">{fmtNum.format(paying)}</b>{" "}
          {paying === 1 ? "pagante" : "pagantes"}
        </span>
        <span className="pain-meta-sep" aria-hidden>·</span>
        <span className={`pain-meta-item pain-sent ${sent.cls}`}>
          <span className="pain-sent-dot" aria-hidden />
          {sent.txt}
        </span>
      </div>

      {/* Índice de dor: rótulo + barra proporcional ao índice + número no fim.
          Sem prioridade do backend, vira "volume (dor pendente)" ou o pain_score. */}
      {hasPriority || !painPending ? (
        <div className="pain-index" aria-label={`Índice de dor ${indexValue.toFixed(hasPriority ? 0 : 1)}`}>
          <span className="pain-index-lbl">Índice de dor</span>
          <span className="pain-index-track">
            <span className="pain-index-fill" style={{ width: `${barPct}%` }} />
          </span>
          <span className="pain-index-val">
            {hasPriority ? Math.round(indexValue) : indexValue.toFixed(1)}
          </span>
        </div>
      ) : (
        <div className="pain-index" aria-label={`Sentimento pendente — ${cluster.item_count} feedbacks`}>
          <span className="pain-index-lbl">Volume (dor pendente)</span>
          <span className="pain-index-track" aria-hidden />
          <span className="pain-index-val">{fmtNum.format(cluster.item_count)}</span>
        </div>
      )}

      <div className="tema-foot cluster-foot pain-foot">
        <Link href={`/feedbacks?cluster_id=${encodeURIComponent(cluster.id)}`} className="tema-link">
          Ver feedbacks
          <span aria-hidden> →</span>
        </Link>

        {promote.phase === "done" ? (
          <Link href="/melhorias" className="btn ghost sm promote-done" title="Ver no roadmap de Melhorias">
            ✓ no roadmap →
          </Link>
        ) : (
          <Button
            variant="default"
            size="sm"
            className="promote-btn"
            onClick={virarMelhoria}
            disabled={promote.phase === "saving"}
            title="Criar uma melhoria a partir desta dor e vincular os feedbacks"
          >
            {promote.phase === "saving" ? "Criando…" : "💡 Virar melhoria"}
          </Button>
        )}
      </div>

      {promote.phase === "done" && (
        <div className="flash ok cluster-flash">
          Melhoria <b>{promote.title}</b> criada com os feedbacks vinculados.{" "}
          <Link href="/melhorias" className="row-link">
            ver em Melhorias →
          </Link>
        </div>
      )}
      {promote.phase === "error" && (
        <div className="flash err cluster-flash">Não consegui criar a melhoria ({promote.msg}).</div>
      )}
    </div>
  );
}

// ===== skeleton (mesma silhueta do card de tema/dor) =======================

/** Placeholder de um card de tema/dor enquanto carrega — título + barra de
   volume + barra de sentimento + rodapé, com shimmer. */
function TemaCardSkeleton() {
  return (
    <div className="card tema-card" aria-busy="true">
      <div className="tema-head" style={{ alignItems: "center" }}>
        <div className="sk-circle" style={{ ["--sk-size" as string]: "26px" } as React.CSSProperties} />
        <div className="sk-line w-50" style={{ margin: 0 }} />
      </div>
      <div className="sk-line w-full" style={{ height: 8, marginTop: 14 }} />
      <div className="sk-line w-80" style={{ height: 8 }} />
      <div className="sk-line w-40" style={{ marginTop: 14 }} />
    </div>
  );
}

/** Grid de skeletons reaproveitado pelas duas abas. */
function TemaGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="tema-grid" aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <TemaCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ===== página ===============================================================

const TAB_OPTIONS: { key: TabKey; label: string }[] = [
  { key: "clusters", label: "Mapa de dores" },
  { key: "tags", label: "Por tema" },
];

export default function TemasPage() {
  // Abre no "Mapa de dores" (clusters por significado) — é a leitura que o dono
  // pediu: as dores agrupadas e ordenadas pelo que mais dói. A aba "Por tema"
  // (contagem de tags) fica como visão secundária.
  const [tab, setTab] = useState<TabKey>("clusters");
  const [days, setDays] = useState(30);

  // --- aba "Por tag" (contagem de tags da IA) ---
  const [data, setData] = useState<ThemesAggregate | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<SortKey>("dor");

  // --- aba "Por significado" (clusters de dores) ---
  const [clusterData, setClusterData] = useState<ClustersResponse | null>(null);
  const [clusterErr, setClusterErr] = useState<string | null>(null);
  const [clusterLoading, setClusterLoading] = useState(true);
  // Default = prioridade (volume × receita × gravidade): a leitura que o mockup pede.
  const [clusterSort, setClusterSort] = useState<ClustersSort>("prioridade");

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

  const loadClusters = useCallback(async () => {
    setClusterLoading(true);
    try {
      let raw: ClustersResponse;
      try {
        raw = await api.get<ClustersResponse>(
          `/api/feedbacks/clusters?sort=${clusterSort}&days=${days}`,
        );
      } catch (e) {
        // Backend antigo (F1 ainda não no ar) não conhece sort=prioridade e
        // responde 422. Em vez de quebrar a tela, refazemos a busca por "dor"
        // (sempre aceito): os cards já caem no fallback gracioso sem os campos
        // de prioridade. Qualquer outro erro continua propagando.
        if (clusterSort === "prioridade" && e instanceof Error && "status" in e && e.status === 422) {
          raw = await api.get<ClustersResponse>(
            `/api/feedbacks/clusters?sort=dor&days=${days}`,
          );
        } else {
          throw e;
        }
      }
      setClusterData(raw);
      setClusterErr(null);
    } catch (e) {
      setClusterErr(e instanceof Error ? e.message : String(e));
    } finally {
      setClusterLoading(false);
    }
  }, [days, clusterSort]);

  // Carrega só a aba ativa (e recarrega quando muda o período ou a ordenação).
  useEffect(() => {
    if (tab === "tags") load();
    else loadClusters();
  }, [tab, load, loadClusters]);

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

  const clusters = clusterData?.clusters ?? [];
  const isTags = tab === "tags";

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Mapeamento</h1>
          <div className="page-sub">
            {isTags
              ? "As dores dos clientes agrupadas por significado — o que mais aparece e o que mais dói"
              : "As dores dos clientes, agrupadas por significado e priorizadas."}
          </div>
        </div>
        {isTags
          ? !loading && !err && themes.length > 0 && (
              <span className="refresh-note">
                {fmtNum.format(themes.length)}{" "}
                {themes.length === 1 ? "tema" : "temas"} · {fmtNum.format(totalNeg)} negativos
              </span>
            )
          : !clusterLoading && !clusterErr && clusters.length > 0 && (
              <span className="refresh-note">
                {fmtNum.format(clusters.length)}{" "}
                {clusters.length === 1 ? "dor" : "dores"} · agrupadas de{" "}
                {fmtNum.format(clusterData?.total_items_clustered ?? 0)} feedbacks
                {clusterSort === "prioridade" ? " · ordenadas por prioridade" : ""}
              </span>
            )}
      </div>

      {/* Switcher de visão: contagem de tags × clusters por significado */}
      <div className="status-tabs" role="tablist" aria-label="Modo de agrupamento">
        {TAB_OPTIONS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`status-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="note">
        <span className="note-ico">💡</span>
        {isTags ? (
          <span>
            Visão por <b>tema</b>: as tags que a IA extrai e normaliza do texto dos feedbacks.
            Cada tema mostra seu <b>índice de dor</b> (volume × negatividade) — quem tem{" "}
            <b>volume e maioria negativa</b> é o que mais vale corrigir no produto.
          </span>
        ) : (
          <span>
            As dores são descobertas automaticamente agrupando feedbacks por{" "}
            <b>significado</b> (semântica), não por palavra exata. A ordem segue a{" "}
            <b>prioridade</b> — volume de clientes × receita (pagantes) × gravidade.
          </span>
        )}
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
        {isTags ? (
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
        ) : (
          <label className="tema-control">
            <span className="tema-control-lbl">Ordenar</span>
            <select
              value={clusterSort}
              onChange={(e) => setClusterSort(e.target.value as ClustersSort)}
              aria-label="Ordenar dores"
            >
              {CLUSTER_SORT_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {isTags ? (
        <>
          {err && (
            <div className="flash err">
              Não consegui carregar os temas ({err}). A API está rodando em{" "}
              <span className="mono">localhost:8000</span>?
            </div>
          )}

          {!err && loading && sorted.length === 0 ? (
            <TemaGridSkeleton />
          ) : !err && sorted.length === 0 ? (
            <div className="card">
              <div className="empty">
                <div className="empty-illu">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3.4 13.4A2 2 0 0 1 2.8 12V4.8A2 2 0 0 1 4.8 2.8H12a2 2 0 0 1 1.4.6l7.2 7.2a2 2 0 0 1 0 2.8z" />
                    <circle cx="7.5" cy="7.5" r="1.2" />
                  </svg>
                </div>
                <div className="empty-title">Nenhum tema classificado neste período</div>
                <p className="empty-sub">
                  Os temas aparecem aqui assim que a IA classificar os feedbacks. Tente um
                  período maior ou volte depois de novas respostas.
                </p>
              </div>
            </div>
          ) : (
            <Stagger className="tema-grid">
              {sorted.map((t, i) => (
                <StaggerItem key={t.name}>
                  <TemaCard tema={t} rank={i + 1} maxCount={maxCount} />
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </>
      ) : (
        <>
          {clusterErr && (
            <div className="flash err">
              Não consegui carregar as dores ({clusterErr}). A API está rodando em{" "}
              <span className="mono">localhost:8000</span>?
            </div>
          )}

          {!clusterErr && clusterLoading && clusters.length === 0 ? (
            <TemaGridSkeleton />
          ) : !clusterErr && clusters.length === 0 ? (
            <div className="card">
              <div className="empty">
                <div className="empty-illu-scene">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src="/illustrations/empty-mapeamento.svg"
                    alt=""
                    aria-hidden
                    width={200}
                    height={150}
                  />
                </div>
                <div className="empty-title">Nenhuma dor mapeada ainda.</div>
                <p className="empty-sub">
                  Conforme os feedbacks chegam, agrupamos as dores aqui — por significado e
                  priorizadas. Tente um período maior ou volte após novas respostas.
                </p>
              </div>
            </div>
          ) : (
            <Stagger className="tema-grid">
              {clusters.map((c, i) => (
                <StaggerItem key={c.id}>
                  <ClusterCard cluster={c} rank={i + 1} />
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </>
      )}
    </div>
  );
}
