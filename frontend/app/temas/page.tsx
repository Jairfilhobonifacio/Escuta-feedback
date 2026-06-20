"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  api,
  type ClustersResponse,
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

      {/* Índice de dor (volume × negatividade) — mesma régua do "Mapa de dores".
          Sem sentimento classificado, mostra o volume como medida provisória. */}
      {painPending ? (
        <div
          className="cluster-pain"
          aria-label={`Sentimento pendente — ${tema.count} menções deste tema`}
        >
          <span className="cluster-pain-label">Volume (dor pendente)</span>
          <span className="cluster-pain-value">{fmtNum.format(tema.count)}</span>
        </div>
      ) : (
        <div className="cluster-pain" aria-label={`Índice de dor ${pain.toFixed(1)}`}>
          <span className="cluster-pain-label">Índice de dor</span>
          <span className="cluster-pain-value">{pain.toFixed(1)}</span>
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

// ===== barra de sentimento de um cluster ====================================
// Reusa o visual da SentimentBar de tags (.tema-sent*), mas o cluster só expõe
// neg_count vs item_count — então mostramos "negativos" × "demais".

function ClusterSentimentBar({ cluster }: { cluster: FeedbackCluster }) {
  const total = cluster.item_count || 1;
  const neg = Math.min(cluster.neg_count, cluster.item_count);
  const rest = Math.max(0, cluster.item_count - neg);
  // Sem nenhum negativo classificado num cluster com volume, "demais" na verdade é
  // "ainda sem classificação" — não é o mesmo que ter sido lido como não-negativo.
  const restLabel = neg === 0 && cluster.item_count > 0 ? "sem classificação" : "demais";

  return (
    <div className="tema-sent">
      <div
        className="tema-sent-bar"
        role="img"
        aria-label={`Sentimento do cluster: ${neg} negativo${neg === 1 ? "" : "s"}, ${rest} ${restLabel}`}
      >
        {neg > 0 && (
          <span className="seg neg" style={{ width: `${(neg / total) * 100}%` }} />
        )}
        {rest > 0 && (
          <span className="seg none" style={{ width: `${(rest / total) * 100}%` }} />
        )}
      </div>
      <div className="tema-sent-legend">
        {neg > 0 && (
          <span className="leg neg">
            <span className="dot" />
            {fmtNum.format(neg)} negativo{neg === 1 ? "" : "s"}
          </span>
        )}
        {rest > 0 && (
          <span className="leg none">
            <span className="dot" />
            {fmtNum.format(rest)} {restLabel}
          </span>
        )}
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
  // O "índice de dor" (volume × fração negativa) só é confiável quando os itens
  // têm sentimento POR ITEM classificado. Enquanto a IA não classificou (neg_count=0
  // num cluster com volume), pain_score sai 0.0 e a barra fica vazia — o que é
  // enganoso, ainda mais com o cluster rotulado como "negativo" pelo LLM. Nesse caso
  // tratamos o índice como PENDENTE e usamos o VOLUME como medida de dor.
  const hasItemSentiment = cluster.neg_count > 0;
  const painPending = !hasItemSentiment && cluster.item_count > 0;
  // "Dor crítica" só quando há base por item (negativos de verdade) com volume — não
  // pode aparecer junto de um índice 0.0. Sem classificação, não cravamos "crítica".
  const isCritical =
    hasItemSentiment &&
    cluster.item_count >= 3 &&
    cluster.dominant_sentiment === "negativo";
  const title = cluster.label ?? "Cluster sem rótulo";

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
    <div className={`card tema-card ${isCritical ? "is-pain" : ""}`}>
      <div className="tema-head">
        <span className={`tema-rank ${rank <= 3 ? "top" : ""}`} aria-hidden>
          {rank}
        </span>
        <h2 className="tema-name" title={title}>
          {title}
        </h2>
        {isCritical && (
          <span
            className="badge detractor tema-flag"
            title="3+ feedbacks com sentimento predominantemente negativo"
          >
            🔥 dor crítica
          </span>
        )}
        {painPending && (
          <span
            className="badge tema-flag"
            title="Feedbacks ainda sem sentimento classificado pela IA — o índice de dor usa o volume por enquanto"
          >
            ⏳ sentimento pendente
          </span>
        )}
        <span className="tema-count" title="Feedbacks agrupados neste cluster">
          {fmtNum.format(cluster.item_count)}
          <span className="tema-count-unit">
            {cluster.item_count === 1 ? "feedback" : "feedbacks"}
          </span>
        </span>
      </div>

      {cluster.description && (
        <p className="cluster-desc" title={cluster.description}>
          {cluster.description}
        </p>
      )}

      {/* Índice de dor em destaque (volume × negatividade). Quando o sentimento
          por item ainda não foi classificado, o índice não é calculável — então
          mostramos o VOLUME como medida provisória de dor, deixando claro o motivo. */}
      {painPending ? (
        <div
          className="cluster-pain"
          aria-label={`Sentimento pendente — ${cluster.item_count} feedbacks neste cluster`}
        >
          <span className="cluster-pain-label">Volume (dor pendente)</span>
          <span className="cluster-pain-value">{fmtNum.format(cluster.item_count)}</span>
        </div>
      ) : (
        <div className="cluster-pain" aria-label={`Índice de dor ${cluster.pain_score.toFixed(1)}`}>
          <span className="cluster-pain-label">Índice de dor</span>
          <span className="cluster-pain-value">{cluster.pain_score.toFixed(1)}</span>
        </div>
      )}

      <ClusterSentimentBar cluster={cluster} />

      {cluster.top_themes.length > 0 && (
        <div className="theme-chips cluster-themes">
          {cluster.top_themes.map((t, i) => (
            <span key={`${t}-${i}`} className="chip">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="tema-foot cluster-foot">
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
      const raw = await api.get<ClustersResponse>(
        `/api/feedbacks/clusters?sort=dor&days=${days}`,
      );
      setClusterData(raw);
      setClusterErr(null);
    } catch (e) {
      setClusterErr(e instanceof Error ? e.message : String(e));
    } finally {
      setClusterLoading(false);
    }
  }, [days]);

  // Carrega só a aba ativa (e recarrega quando muda o período).
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
            As dores dos clientes agrupadas por significado — o que mais aparece e o que mais dói
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
                {clusters.length === 1 ? "dor" : "dores"} ·{" "}
                {fmtNum.format(clusterData?.total_items_clustered ?? 0)} agrupados
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
            <b>significado</b> (semântica), não por palavra exata. Cada cluster vira uma dor
            com um <b>índice de dor</b> (volume × negatividade) para priorizar.
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
        {isTags && (
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
                <div className="empty-illu">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M14.5 9.5 11 11l-1.5 3.5L13 13z" />
                  </svg>
                </div>
                <div className="empty-title">Nenhuma dor agrupada neste período</div>
                <p className="empty-sub">
                  Os clusters aparecem quando há feedbacks com texto suficiente para a IA
                  agrupar por significado. Tente um período maior ou volte após novas
                  respostas.
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
