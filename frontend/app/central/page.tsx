"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Reveal, Stagger, StaggerItem } from "@/components/Motion";
import {
  central as centralApi,
  type CentralOverview,
  type CentralNpsResponse,
  type CentralFeedbacksResponse,
  type CentralFeedbackItem,
  type CentralSegmento,
} from "@/lib/api";

/* ============================================================================
   CENTRAL DE FEEDBACKS — visão consolidada de acompanhamento (a tela que o
   Felipe apresenta ao Lucas). Clareza acima de tudo: números-herói no topo,
   feedbacks por sentimento (Positivo · Neutro · Negativo), segmentação de
   acompanhamento (Cancelaram × Ativos) com plano de ação editável, e a lista
   detalhada de quem deu NPS.

   Consome 3 endpoints sob /api/central (overview / nps / feedbacks). Cada bloco
   degrada com elegância (skeletons no load, estado vazio claro, erro só quando
   o overview — a espinha — falha). Reusa o design system Bizzu (card/kpi/badge/
   score-pill/chip/cmp-*) e as animações de entrada (Reveal/Stagger).

   Emoji em .tsx só via escape \u{...} (bundler Windows) — aqui usamos ícones
   SVG (lucide via traço inline) e nenhum emoji literal.
   ========================================================================== */

// --- vocabulário de fontes (rótulo + cor de acento) --------------------------
const FONTE_META: Record<string, { label: string; cor: string }> = {
  whatsapp: { label: "WhatsApp", cor: "var(--indigo-light)" },
  app: { label: "App", cor: "var(--gold-soft)" },
  billing: { label: "Billing", cor: "var(--detractor)" },
  forms: { label: "Forms", cor: "var(--text-dim)" },
  exit: { label: "Cancelamento", cor: "var(--detractor)" },
  nps: { label: "NPS", cor: "var(--indigo-light)" },
};

function fonteLabel(fonte: string): string {
  return FONTE_META[fonte]?.label ?? fonte;
}
function fonteCor(fonte: string): string {
  return FONTE_META[fonte]?.cor ?? "var(--text-dim)";
}

// --- colunas de sentimento (ordem + identidade) ------------------------------
const SENT_COLS: {
  key: "positivo" | "neutro" | "negativo";
  label: string;
  cls: string;
  cor: string;
}[] = [
  { key: "positivo", label: "Positivo", cls: "s-pos", cor: "var(--promoter)" },
  { key: "neutro", label: "Neutro", cls: "s-neu", cor: "var(--passive)" },
  { key: "negativo", label: "Negativo", cls: "s-neg", cor: "var(--detractor)" },
];

function npsClass(nps: number | null): string {
  if (nps === null) return "nps-none";
  if (nps >= 50) return "nps-good";
  if (nps >= 0) return "nps-mid";
  return "nps-bad";
}

function bucketBadge(bucket: string) {
  if (bucket === "promotor") return <span className="badge promoter">promotor</span>;
  if (bucket === "neutro") return <span className="badge passive">neutro</span>;
  return <span className="badge detractor">detrator</span>;
}

/** Classe do score-pill por bucket textual da Central. */
function pillClass(bucket: string): string {
  if (bucket === "promotor") return "promoter";
  if (bucket === "neutro") return "passive";
  return "detractor";
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pct(n: number, total: number): number {
  return total > 0 ? (n / total) * 100 : 0;
}

// --- chips de filtro de fonte/sentimento (segmented control simples) ---------
type Chip<T extends string> = { value: T | ""; label: string };

function FilterChips<T extends string>({
  chips,
  value,
  onChange,
  ariaLabel,
}: {
  chips: Chip<T>[];
  value: T | "";
  onChange: (v: T | "") => void;
  ariaLabel: string;
}) {
  return (
    <div className="status-tabs" role="group" aria-label={ariaLabel} style={{ marginBottom: 0 }}>
      {chips.map((c) => (
        <button
          key={c.value || "todos"}
          type="button"
          className={`status-tab${value === c.value ? " active" : ""}`}
          aria-pressed={value === c.value}
          onClick={() => onChange(c.value)}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

// --- bloco de segmento (Cancelaram / Ativos) com plano de ação editável ------
/** Mini-funil de acompanhamento: total → abordados → responderam. */
function SegmentoCard({
  seg,
  accent,
  storageKey,
  placeholder,
}: {
  seg: CentralSegmento;
  accent: string;
  storageKey: string;
  placeholder: string;
}) {
  const [plano, setPlano] = useState("");
  const [saved, setSaved] = useState(false);

  // Plano de ação por grupo é acompanhamento CONTÍNUO — persiste local (sem backend).
  useEffect(() => {
    try {
      setPlano(localStorage.getItem(storageKey) ?? "");
    } catch {
      /* localStorage indisponível (SSR/sandbox): segue com vazio */
    }
  }, [storageKey]);

  const onPlano = (v: string) => {
    setPlano(v);
    try {
      localStorage.setItem(storageKey, v);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1200);
    } catch {
      /* sem persistência: a edição segue válida só na sessão */
    }
  };

  const taxaResp = seg.abordados > 0 ? Math.round(pct(seg.responderam, seg.abordados)) : null;

  const linhas: { label: string; n: number; cor: string; hint?: string }[] = [
    { label: "Abordados", n: seg.abordados, cor: accent, hint: `${Math.round(pct(seg.abordados, seg.total))}% do grupo` },
    { label: "Responderam", n: seg.responderam, cor: "var(--indigo-light)", hint: taxaResp !== null ? `${taxaResp}% de quem foi abordado` : undefined },
    { label: "Não responderam", n: seg.nao_responderam, cor: "var(--text-faint)" },
  ];

  return (
    <div className="card cmp-block" style={{ marginBottom: 0 }}>
      <div className="card-head">
        <div>
          <div className="section-title">{seg.rotulo}</div>
          <div className="card-head-sub">
            {seg.total} cliente{seg.total === 1 ? "" : "s"} no grupo · acompanhamento contínuo
          </div>
        </div>
        <span className="exit-counter" style={{ borderColor: accent, color: accent }}>
          {seg.total}
        </span>
      </div>

      <div className="cmp-pad" style={{ display: "grid", gap: 16 }}>
        {/* mini-funil do segmento */}
        <ul className="cmp-canal-list">
          {linhas.map((r) => (
            <li key={r.label} className="cmp-canal-row">
              <span className="cmp-canal-name">{r.label}</span>
              <span className="cmp-alcance-meta">
                <span className="cmp-canal-n mono" style={{ color: r.cor }}>
                  {r.n}
                </span>
                {r.hint && <span className="cmp-alcance-pct">{r.hint}</span>}
              </span>
            </li>
          ))}
        </ul>

        {/* barra de progresso: abordados sobre o total */}
        <div>
          <div className="fn-track">
            <span
              className="fn-fill"
              style={{ width: `${pct(seg.abordados, seg.total)}%`, background: accent }}
            />
          </div>
          <div className="hero-gauge-cap" style={{ marginTop: 8, textAlign: "left" }}>
            {seg.abordados} de {seg.total} já abordados · faltam{" "}
            <span className="mono">{Math.max(0, seg.total - seg.abordados)}</span>
          </div>
        </div>

        {/* plano de ação editável (acompanhamento contínuo, salvo local) */}
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={storageKey}>
            Plano de ação / próximo passo
            {saved && <span className="act-saved" style={{ marginLeft: 8 }}>salvo</span>}
          </label>
          <textarea
            id={storageKey}
            value={plano}
            onChange={(e) => onPlano(e.target.value)}
            placeholder={placeholder}
            rows={3}
          />
        </div>
      </div>
    </div>
  );
}

// --- skeletons ---------------------------------------------------------------
function CentralSkeleton() {
  return (
    <div aria-busy="true">
      <div className="kpi-grid">
        <div className="card kpi kpi-nps">
          <div className="sk-line sk-sm w-50" />
          <div className="sk-line sk-lg w-40" style={{ height: 40, margin: "14px 0" }} />
          <div className="sk-line sk-sm w-80" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card kpi">
            <div className="sk-line sk-sm w-60" />
            <div className="sk-line sk-lg w-30" style={{ margin: "12px 0" }} />
            <div className="sk-line sk-sm w-80" />
          </div>
        ))}
      </div>
      <div className="central-cols" style={{ marginBottom: 18 }}>
        {SENT_COLS.map((c) => (
          <div key={c.key} className="card cmp-block" style={{ marginBottom: 0 }}>
            <div className="card-head">
              <div style={{ flex: 1 }}>
                <div className="sk-line w-40" style={{ height: 12 }} />
              </div>
            </div>
            <div className="cmp-pad" style={{ display: "grid", gap: 12 }}>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i}>
                  <div className="sk-line w-70" />
                  <div className="sk-line w-full" style={{ height: 9 }} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- cartão de um feedback dentro de uma coluna de sentimento ----------------
function FeedbackMini({ f }: { f: CentralFeedbackItem }) {
  return (
    <div className="central-fb reveal">
      <div className="central-fb-top">
        <span className="central-fb-who">{f.nome || <span className="faint">sem nome</span>}</span>
        <span className="central-fb-src" style={{ color: fonteCor(f.fonte) }}>
          {fonteLabel(f.fonte)}
        </span>
      </div>
      {f.texto ? (
        <p className="central-fb-text">{f.texto}</p>
      ) : (
        <p className="central-fb-text empty-text">sem texto</p>
      )}
      <div className="central-fb-meta">
        <span className="central-fb-when">{fmtDate(f.em)}</span>
        {f.abordado && <span className="badge abordado">abordado</span>}
      </div>
    </div>
  );
}

export default function CentralPage() {
  const [overview, setOverview] = useState<CentralOverview | null>(null);
  const [npsList, setNpsList] = useState<CentralNpsResponse | null>(null);
  const [feed, setFeed] = useState<CentralFeedbacksResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // filtros do bloco "Feedbacks por sentimento"
  const [fFonte, setFFonte] = useState<string>("");
  const [fAbordado, setFAbordado] = useState<"" | "sim" | "nao">("");

  const loadCore = useCallback(async () => {
    try {
      const [ov, nps] = await Promise.all([centralApi.overview(), centralApi.nps()]);
      setOverview(ov);
      setNpsList(nps);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // feedbacks reagem aos filtros (fonte/abordado) — chamada própria
  const loadFeed = useCallback(async () => {
    try {
      const res = await centralApi.feedbacks({
        fonte: fFonte || undefined,
        abordado: fAbordado === "" ? undefined : fAbordado === "sim",
      });
      setFeed(res);
    } catch {
      /* feedbacks é best-effort: a falha não derruba o overview/NPS */
      setFeed({ total: 0, items: [] });
    }
  }, [fFonte, fAbordado]);

  useEffect(() => {
    loadCore();
    const t = setInterval(loadCore, 30_000);
    return () => clearInterval(t);
  }, [loadCore]);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  // fontes disponíveis nos chips de filtro (vem do overview.por_fonte)
  const fonteChips = useMemo<Chip<string>[]>(() => {
    const base: Chip<string>[] = [{ value: "", label: "Todas as fontes" }];
    const fontes = overview ? Object.keys(overview.feedbacks.por_fonte) : [];
    for (const f of fontes) base.push({ value: f, label: fonteLabel(f) });
    return base;
  }, [overview]);

  // agrupa os feedbacks (já filtrados pelo backend) por sentimento p/ as colunas
  const porSentimento = useMemo(() => {
    const groups: Record<string, CentralFeedbackItem[]> = { positivo: [], neutro: [], negativo: [] };
    for (const it of feed?.items ?? []) {
      const s = it.sentimento ?? "";
      if (s in groups) groups[s].push(it);
    }
    return groups;
  }, [feed]);

  if (err) {
    return (
      <div>
        <div className="page-head">
          <h1 className="page-title">Central de Feedbacks</h1>
        </div>
        <div className="flash err">
          Não consegui carregar a Central ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      </div>
    );
  }

  if (!overview || !npsList) {
    return (
      <div>
        <div className="page-head">
          <div>
            <h1 className="page-title">Central de Feedbacks</h1>
            <div className="page-sub">consolidando a voz do cliente…</div>
          </div>
          <span className="refresh-note">atualiza a cada 30s</span>
        </div>
        <CentralSkeleton />
      </div>
    );
  }

  const { nps, feedbacks: fb, abordagem, segmentos } = overview;
  const npsTotal = nps.promotores + nps.neutros + nps.detratores;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Central de Feedbacks</h1>
          <div className="page-sub">
            Visão consolidada da voz do cliente — NPS, feedbacks por sentimento e o
            acompanhamento de quem cancelou e de quem está ativo.
          </div>
        </div>
        <span className="refresh-note">atualiza a cada 30s</span>
      </div>

      {/* 1) NÚMEROS REAIS — NPS herói + distribuição + totais de abordagem */}
      <Stagger className="kpi-grid" stagger={0.05}>
        <StaggerItem className="card kpi kpi-nps">
          <div className="kpi-label">NPS médio</div>
          <div className={`kpi-value ${npsClass(nps.media)}`}>{nps.media ?? "—"}</div>
          <div className="kpi-hint">
            {nps.deram} de {abordagem.contatos_total} deram nota
          </div>
          {npsTotal > 0 && (
            <>
              <div className="dist-bar" style={{ marginTop: 14 }}>
                <span style={{ width: `${pct(nps.promotores, npsTotal)}%`, background: "var(--promoter)" }} />
                <span style={{ width: `${pct(nps.neutros, npsTotal)}%`, background: "var(--passive)" }} />
                <span style={{ width: `${pct(nps.detratores, npsTotal)}%`, background: "var(--detractor)" }} />
              </div>
              <div className="dist-legend" style={{ marginTop: 10, flexWrap: "wrap", gap: 12 }}>
                <span><span className="dot" style={{ background: "var(--promoter)" }} />Promot. {nps.promotores}</span>
                <span><span className="dot" style={{ background: "var(--passive)" }} />Neutros {nps.neutros}</span>
                <span><span className="dot" style={{ background: "var(--detractor)" }} />Detrat. {nps.detratores}</span>
              </div>
            </>
          )}
        </StaggerItem>

        <StaggerItem className="card kpi">
          <div className="kpi-label">Feedbacks</div>
          <div className="kpi-value">{fb.total}</div>
          <div className="kpi-hint">{fb.com_texto} com texto</div>
        </StaggerItem>

        <StaggerItem className="card kpi">
          <div className="kpi-label">Abordados</div>
          <div className="kpi-value">{abordagem.abordados}</div>
          <div className="kpi-hint">
            {abordagem.contatos_total > 0
              ? `${Math.round(pct(abordagem.abordados, abordagem.contatos_total))}% dos contatos`
              : "de " + abordagem.contatos_total + " contatos"}
          </div>
        </StaggerItem>

        <StaggerItem className="card kpi">
          <div className="kpi-label">Responderam</div>
          <div className="kpi-value nps-good">{abordagem.responderam}</div>
          <div className="kpi-hint">voltaram a falar com a gente</div>
        </StaggerItem>

        <StaggerItem className="card kpi">
          <div className="kpi-label">Não responderam</div>
          <div className="kpi-value">{abordagem.nao_responderam}</div>
          <div className="kpi-hint">aguardando retorno</div>
        </StaggerItem>
      </Stagger>

      {/* 2) FEEDBACKS POR SENTIMENTO — colunas Positivo · Neutro · Negativo */}
      <Reveal className="card cmp-block">
        <div className="card-head" style={{ flexWrap: "wrap", rowGap: 12 }}>
          <div>
            <div className="section-title">Feedbacks por sentimento</div>
            <div className="card-head-sub">
              o que cada cliente disse, com o motivo e a fonte · filtre por fonte e por
              abordagem
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <FilterChips
              chips={fonteChips}
              value={fFonte}
              onChange={setFFonte}
              ariaLabel="Filtrar por fonte"
            />
            <FilterChips
              chips={[
                { value: "", label: "Todos" },
                { value: "sim", label: "Abordados" },
                { value: "nao", label: "Não abordados" },
              ]}
              value={fAbordado}
              onChange={setFAbordado}
              ariaLabel="Filtrar por abordagem"
            />
          </div>
        </div>

        {!feed ? (
          <div className="cmp-pad">
            <div className="sk-line w-60" />
            <div className="sk-line w-full" />
            <div className="sk-line w-80" />
          </div>
        ) : feed.items.length === 0 ? (
          <div className="empty">
            <div className="empty-illu">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                <path d="M8 9h8M8 12h5" />
              </svg>
            </div>
            <div className="empty-title">Nenhum feedback com esse filtro</div>
            <p className="empty-sub">
              Ajuste a fonte ou a abordagem acima para ver os feedbacks classificados.
            </p>
          </div>
        ) : (
          <div className="central-cols central-cols-flush">
            {SENT_COLS.map((col) => {
              const items = porSentimento[col.key];
              return (
                <div key={col.key} className="central-col">
                  <div className="central-col-head">
                    <span className={`badge sent ${col.cls}`}>{col.label}</span>
                    <span className="central-col-n mono">{items.length}</span>
                  </div>
                  <div className="central-col-body reveal-stagger">
                    {items.length === 0 ? (
                      <p className="central-col-empty">sem feedbacks aqui</p>
                    ) : (
                      items.map((f) => <FeedbackMini key={`${f.contact_id}-${f.em}`} f={f} />)
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Reveal>

      {/* 3) SEGMENTAÇÃO — Cancelaram × Ativos, com plano de ação por grupo */}
      <Reveal className="central-seg-head" style={{ marginBottom: 12 }}>
        <div className="section-title">Acompanhamento por segmento</div>
        <div className="section-sub" style={{ marginBottom: 0 }}>
          Dois mundos a cuidar de forma contínua: quem cancelou (resgate) e quem está
          ativo (retenção). Abaixo, o que já fizemos e qual o próximo passo de cada um.
        </div>
      </Reveal>
      <div className="central-cols central-cols-2">
        <SegmentoCard
          seg={segmentos.churn}
          accent="var(--detractor)"
          storageKey="central:plano:churn"
          placeholder="Ex.: oferecer 3 meses com desconto; ligar para os 5 de maior LTV; pedir o motivo a quem ainda não respondeu…"
        />
        <SegmentoCard
          seg={segmentos.ativos}
          accent="var(--indigo)"
          storageKey="central:plano:ativos"
          placeholder="Ex.: agradecer promotores e pedir indicação; abordar neutros com novidades; checar os detratores 1:1…"
        />
      </div>

      {/* 4) NPS DETALHADO — quem deu nota, com cor por bucket e motivo */}
      <Reveal className="card" style={{ marginTop: 18 }}>
        <div className="card-head">
          <div>
            <div className="section-title">NPS detalhado</div>
            <div className="card-head-sub">
              cada pessoa que deu nota, a classificação e o motivo
            </div>
          </div>
          <span className="exit-counter">
            média{" "}
            <span className={`mono ${npsClass(npsList.media)}`} style={{ marginLeft: 4 }}>
              {npsList.media ?? "—"}
            </span>
          </span>
        </div>
        {npsList.items.length === 0 ? (
          <div className="empty">
            <div className="empty-illu">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 3v18h18" />
                <path d="m7 14 3-3 3 3 5-6" />
              </svg>
            </div>
            <div className="empty-title">Ninguém deu nota ainda</div>
            <p className="empty-sub">
              Assim que os clientes responderem ao NPS, eles aparecem aqui com a nota e o
              motivo.
            </p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Nota</th>
                  <th>Classificação</th>
                  <th>Fonte</th>
                  <th style={{ width: "40%" }}>Motivo</th>
                  <th>Quando</th>
                </tr>
              </thead>
              <tbody>
                {npsList.items.map((it, i) => (
                  <tr
                    key={`${it.contact_id}-${it.em}`}
                    className="reveal"
                    style={{ ["--i" as string]: i } as React.CSSProperties}
                  >
                    <td>
                      <div>{it.nome || <span className="faint">sem nome</span>}</div>
                      <div className="mono dim">{it.telefone}</div>
                    </td>
                    <td>
                      <span className={`score-pill ${pillClass(it.bucket)}`}>{it.score}</span>
                    </td>
                    <td>{bucketBadge(it.bucket)}</td>
                    <td>
                      <span className="dim" style={{ color: fonteCor(it.fonte) }}>
                        {fonteLabel(it.fonte)}
                      </span>
                    </td>
                    <td>{it.motivo ? it.motivo : <span className="faint">—</span>}</td>
                    <td className="dim">{fmtDate(it.em)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Reveal>

      <p className="count-line">
        Fonte: NPS, feedbacks classificados pela IA e o histórico de abordagens da
        operação. Os planos de ação por segmento ficam salvos neste navegador.
      </p>

      <style jsx>{`
        /* grid de colunas reutilizável — sentimento (3) e segmentos (2) */
        .central-cols {
          display: grid;
          gap: 14px;
          align-items: start;
        }
        .central-cols-2 {
          grid-template-columns: repeat(2, 1fr);
        }
        /* 3 colunas de sentimento; "flush" = dentro de um card, com divisores */
        .central-cols:not(.central-cols-2) {
          grid-template-columns: repeat(3, 1fr);
        }
        .central-cols-flush {
          gap: 0;
          border-top: 1px solid var(--charcoal);
        }
        .central-col {
          min-width: 0;
          padding: 16px 18px 18px;
          border-right: 1px solid var(--charcoal);
        }
        .central-col:last-child {
          border-right: none;
        }
        .central-col-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 14px;
        }
        .central-col-n {
          font-family: var(--mono);
          font-size: 13px;
          font-weight: 600;
          color: var(--text-faint);
        }
        .central-col-body {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .central-col-empty {
          font-size: 12.5px;
          color: var(--text-ghost);
          font-style: italic;
          margin: 6px 2px;
        }

        /* cartão compacto de um feedback dentro da coluna */
        .central-fb {
          padding: 12px 13px;
          background: var(--ink);
          border: 1px solid var(--charcoal);
          border-radius: var(--radius-sm);
          transition-property: border-color, box-shadow, transform;
          transition-duration: 150ms;
          transition-timing-function: var(--ease);
        }
        .central-fb:hover {
          border-color: var(--charcoal-2);
          box-shadow: var(--shadow-sm);
        }
        .central-fb-top {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 6px;
        }
        .central-fb-who {
          font-family: var(--font-display);
          font-weight: 600;
          font-size: 13px;
          letter-spacing: -0.2px;
          color: var(--text);
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .central-fb-src {
          font-size: 10.5px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.6px;
          white-space: nowrap;
          flex-shrink: 0;
        }
        .central-fb-text {
          font-size: 13px;
          line-height: 1.55;
          color: var(--text);
          margin: 0;
          text-wrap: pretty;
        }
        .central-fb-text.empty-text {
          color: var(--text-faint);
          font-style: italic;
        }
        .central-fb-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 8px;
        }
        .central-fb-when {
          font-size: 11.5px;
          color: var(--text-faint);
        }

        /* cabeçalho da seção de segmentos (fora de card) */
        .central-seg-head {
          margin-top: 22px;
        }

        @media (max-width: 980px) {
          .central-cols:not(.central-cols-2),
          .central-cols-2 {
            grid-template-columns: 1fr;
          }
          .central-cols-flush {
            border-top: none;
          }
          .central-col {
            border-right: none;
            border-bottom: 1px solid var(--charcoal);
          }
          .central-col:last-child {
            border-bottom: none;
          }
        }
      `}</style>
    </div>
  );
}
