"use client";

import { useCallback, useEffect, useState } from "react";
import { Reveal, Stagger, StaggerItem } from "@/components/Motion";
import {
  central as centralApi,
  type CentralOverview,
  type CentralNpsResponse,
  type CentralNpsItem,
} from "@/lib/api";

/* ============================================================================
   MONITORAR — a tela principal do painel (a home redireciona pra cá).

   Pensada pra uma reunião: bate o olho e entende. De cima pra baixo:
     1) Título "Monitorar" + uma linha de contexto.
     2) Os 4 NÚMEROS GRANDES e honestos sobre a BASE TOTAL de contatos:
        Abordados · Responderam · Não responderam · Cancelaram. Quando é um
        recorte (Cancelaram é um segmento), o número mostra o denominador.
     3) O NPS — média + promotores/neutros/detratores.
     4) As RESPOSTAS dos clientes, limpas: nome, nota, texto e data.

   Clareza acima de tudo: muito respiro, hierarquia óbvia, nada poluído.
   Reusa o design system Bizzu (card/kpi/badge/score-pill) e os tokens de tema
   (CSS vars). Sem emoji literal (bundler Windows) — só ícones SVG inline.

   Consome 2 endpoints sob /api/central (overview / nps). Cada bloco degrada
   com elegância (skeleton no load; erro só quando o overview — a espinha —
   falha). Os buckets do NPS vêm em INGLÊS (promoter/passive/detractor) e a
   comparação É FEITA EM INGLÊS — não regredir isso.
   ========================================================================== */

function npsClass(nps: number | null): string {
  if (nps === null) return "nps-none";
  if (nps >= 50) return "nps-good";
  if (nps >= 0) return "nps-mid";
  return "nps-bad";
}

/** Badge/pílula por bucket — comparação em INGLÊS (não regredir). */
function bucketBadge(bucket: string) {
  if (bucket === "promoter") return <span className="badge promoter">promotor</span>;
  if (bucket === "passive") return <span className="badge passive">neutro</span>;
  return <span className="badge detractor">detrator</span>;
}
function pillClass(bucket: string): string {
  if (bucket === "promoter") return "promoter";
  if (bucket === "passive") return "passive";
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

/* --- DESTAQUES: "o que fazer agora" -----------------------------------------
   Lê só os números que JÁ chegam no overview e devolve até alguns avisos
   ACIONÁVEIS (a ação primeiro, curto). Severidade dá a cor: "alert" = vermelho
   (detrator/churn, dói no caixa), "watch" = indigo (atenção, não urgente).
   Tudo que zera é OMITIDO — faixa vazia some. Sem dados novos, sem endpoints. */
type Severity = "alert" | "watch";
interface Destaque {
  id: string;
  sev: Severity;
  text: string;
}

function buildDestaques(ov: CentralOverview): Destaque[] {
  const { nps, abordagem, segmentos } = ov;
  const d: Destaque[] = [];

  if (nps.detratores > 0) {
    d.push({
      id: "detratores",
      sev: "alert",
      text: `${nps.detratores} ${nps.detratores === 1 ? "detrator" : "detratores"} — priorize abordar`,
    });
  }

  const churnPend = segmentos.churn.total - segmentos.churn.abordados;
  if (churnPend > 0) {
    d.push({
      id: "churn-pend",
      sev: "alert",
      text: `${churnPend} ${churnPend === 1 ? "cancelado" : "cancelados"} ainda não abordados`,
    });
  }

  if (abordagem.nao_responderam > 0) {
    d.push({
      id: "sem-resposta-abordados",
      sev: "watch",
      text: `${abordagem.nao_responderam} abordados sem resposta`,
    });
  }

  if (abordagem.abordados > 0) {
    d.push({
      id: "taxa-resposta",
      sev: "watch",
      text: `Taxa de resposta: ${Math.round(pct(abordagem.responderam, abordagem.abordados))}%`,
    });
  }

  if (nps.sem_resposta > 0) {
    d.push({
      id: "sem-nota",
      sev: "watch",
      text: `${nps.sem_resposta} ${nps.sem_resposta === 1 ? "cliente ainda sem nota" : "clientes ainda sem nota"}`,
    });
  }

  return d;
}

// --- skeleton da tela enquanto o overview não chegou -------------------------
function MonitorarSkeleton() {
  return (
    <div aria-busy="true">
      <div className="mon-hero">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card mon-num">
            <div className="sk-line sk-sm w-60" />
            <div className="sk-line sk-lg w-40" style={{ height: 52, margin: "18px 0 14px" }} />
            <div className="sk-line sk-sm w-80" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MonitorarPage() {
  const [overview, setOverview] = useState<CentralOverview | null>(null);
  const [npsList, setNpsList] = useState<CentralNpsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ov, nps] = await Promise.all([centralApi.overview(), centralApi.nps()]);
      setOverview(ov);
      setNpsList(nps);
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
          <h1 className="page-title">Monitorar</h1>
        </div>
        <div className="flash err">
          Não consegui carregar os números ({err}). A API está rodando em{" "}
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
            <h1 className="page-title">Monitorar</h1>
            <div className="page-sub">reunindo os números da operação…</div>
          </div>
          <span className="refresh-note">atualiza a cada 30s</span>
        </div>
        <MonitorarSkeleton />
      </div>
    );
  }

  const { nps, abordagem, segmentos } = overview;
  const npsTotal = nps.promotores + nps.neutros + nps.detratores;
  const base = abordagem.contatos_total;

  // Os 4 números-herói, sobre a BASE TOTAL. "Cancelaram" é um recorte da base
  // (segmento churn) → mostra o denominador no rótulo de apoio.
  const HERO: {
    label: string;
    n: number;
    sub: string;
    cls?: string;
    accent: string;
  }[] = [
    {
      label: "Abordados",
      n: abordagem.abordados,
      sub: base > 0 ? `${Math.round(pct(abordagem.abordados, base))}% da base de ${base}` : "—",
      accent: "var(--indigo)",
    },
    {
      label: "Responderam",
      n: abordagem.responderam,
      sub:
        abordagem.abordados > 0
          ? `${Math.round(pct(abordagem.responderam, abordagem.abordados))}% de quem foi abordado`
          : "voltaram a falar com a gente",
      cls: "nps-good",
      accent: "var(--indigo-light)",
    },
    {
      label: "Não responderam",
      n: abordagem.nao_responderam,
      sub: "abordados, ainda sem retorno",
      accent: "var(--text-faint)",
    },
    {
      label: "Cancelaram",
      n: segmentos.churn.total,
      sub: base > 0 ? `de ${base} na base` : "clientes que cancelaram",
      cls: "nps-bad",
      accent: "var(--detractor)",
    },
  ];

  // Faixa "o que fazer agora" — pills acionáveis a partir dos números acima.
  const destaques = buildDestaques(overview);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Monitorar</h1>
          <div className="page-sub">
            De relance: quantos clientes a gente abordou, quantos responderam, quantos
            ainda não e quantos cancelaram — e o que eles disseram.
          </div>
        </div>
        <span className="refresh-note">atualiza a cada 30s</span>
      </div>

      {/* 0) DESTAQUES — "o que fazer agora", computado client-side dos números
         que já chegam. Pills pequenas; cor por severidade. Some se vazio. */}
      {destaques.length > 0 && (
        <Reveal
          aria-label="Destaques: o que fazer agora"
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 8,
            margin: "0 0 18px",
          }}
        >
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 1,
              textTransform: "uppercase",
              color: "var(--text-faint)",
              marginRight: 2,
            }}
          >
            O que fazer agora
          </span>
          {destaques.map((d) => {
            const isAlert = d.sev === "alert";
            return (
              <span
                key={d.id}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "5px 11px",
                  borderRadius: 999,
                  fontSize: 12.5,
                  fontWeight: 600,
                  lineHeight: 1.25,
                  color: isAlert ? "var(--detractor)" : "var(--indigo-light)",
                  background: isAlert ? "var(--detractor-soft)" : "var(--promoter-soft)",
                  border: `1px solid ${isAlert ? "var(--detractor-line)" : "var(--promoter-line)"}`,
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: isAlert ? "var(--detractor)" : "var(--indigo)",
                  }}
                />
                {d.text}
              </span>
            );
          })}
        </Reveal>
      )}

      {/* 1) OS 4 NÚMEROS — grandes, honestos, sobre a base total */}
      <Stagger className="mon-hero" stagger={0.06}>
        {HERO.map((h) => (
          <StaggerItem key={h.label} className="card mon-num">
            <span className="mon-num-accent" style={{ background: h.accent }} aria-hidden />
            <div className="mon-num-label">{h.label}</div>
            <div className={`mon-num-value ${h.cls ?? ""}`}>{h.n}</div>
            <div className="mon-num-sub">{h.sub}</div>
          </StaggerItem>
        ))}
      </Stagger>

      {/* 2) NPS — média + promotores/neutros/detratores (buckets em inglês) */}
      <Reveal className="card mon-nps">
        <div className="mon-nps-score">
          <div className="mon-nps-eyebrow">NPS médio</div>
          <div className={`mon-nps-value ${npsClass(nps.media)}`}>{nps.media ?? "—"}</div>
          <div className="mon-nps-cap">
            {nps.deram} de {base} deram nota
          </div>
        </div>

        <div className="mon-nps-dist">
          {npsTotal > 0 ? (
            <>
              <div className="dist-bar">
                <span style={{ width: `${pct(nps.promotores, npsTotal)}%`, background: "var(--promoter)" }} />
                <span style={{ width: `${pct(nps.neutros, npsTotal)}%`, background: "var(--passive)" }} />
                <span style={{ width: `${pct(nps.detratores, npsTotal)}%`, background: "var(--detractor)" }} />
              </div>
              <div className="mon-nps-legend">
                <div className="mon-nps-leg">
                  <span className="dot" style={{ background: "var(--promoter)" }} />
                  <span className="mon-nps-leg-n mono">{nps.promotores}</span>
                  <span className="mon-nps-leg-l">Promotores</span>
                </div>
                <div className="mon-nps-leg">
                  <span className="dot" style={{ background: "var(--passive)" }} />
                  <span className="mon-nps-leg-n mono">{nps.neutros}</span>
                  <span className="mon-nps-leg-l">Neutros</span>
                </div>
                <div className="mon-nps-leg">
                  <span className="dot" style={{ background: "var(--detractor)" }} />
                  <span className="mon-nps-leg-n mono">{nps.detratores}</span>
                  <span className="mon-nps-leg-l">Detratores</span>
                </div>
              </div>
            </>
          ) : (
            <p className="mon-empty-inline">Ainda sem notas de NPS para distribuir.</p>
          )}
        </div>
      </Reveal>

      {/* 3) AS RESPOSTAS — nome, nota, texto, data. Limpo. */}
      <Reveal className="card mon-resp">
        <div className="card-head">
          <div>
            <div className="section-title">Respostas dos clientes</div>
            <div className="card-head-sub">o que cada pessoa disse, com a nota e quando</div>
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
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                <path d="M8 9h8M8 12h5" />
              </svg>
            </div>
            <div className="empty-title">Ninguém respondeu ainda</div>
            <p className="empty-sub">
              Assim que os clientes responderem, as falas aparecem aqui com nota e data.
            </p>
          </div>
        ) : (
          <ul className="mon-resp-list reveal-stagger">
            {npsList.items.map((it: CentralNpsItem, i) => (
              <li
                key={`${it.contact_id}-${it.em}-${i}`}
                className="mon-resp-item reveal"
                style={{ ["--i" as string]: i } as React.CSSProperties}
              >
                <span className={`score-pill ${pillClass(it.bucket)}`}>{it.score}</span>
                <div className="mon-resp-body">
                  <div className="mon-resp-top">
                    <span className="mon-resp-who">
                      {it.nome || <span className="faint">sem nome</span>}
                    </span>
                    {bucketBadge(it.bucket)}
                    <span className="mon-resp-when">{fmtDate(it.em)}</span>
                  </div>
                  {it.motivo ? (
                    <p className="mon-resp-text">“{it.motivo}”</p>
                  ) : (
                    <p className="mon-resp-text empty-text">sem comentário</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Reveal>

      <p className="count-line">
        Base de {base} contatos · NPS e respostas reais dos clientes da operação.
      </p>

    </div>
  );
}
