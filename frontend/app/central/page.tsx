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

   Composição (1 FOCO + satélites + ação): bate o olho e entende em 2s.
     1) Kicker + título "Monitorar" + régua de marca + linha de contexto.
     2) HERÓI: o NPS (número gigante em GOLD, fio gold no topo) — a ÚNICA
        mancha dominante. Ao lado, em escala ~2,3× menor, os 4 NÚMEROS
        satélites sobre a base total: Abordados · Responderam · Não
        responderam · Cancelaram. "Cancelaram" mostra o denominador.
     3) Faixa "o que fazer agora" — ponte de AÇÃO (pills acionáveis).
     4) MÉTRICAS da operação: resolução, loops, tempo, follow-ups (+NPS/tema).
     5) RESPOSTAS dos clientes: badge em coluna fixa, fala, nota mono à direita.

   Cor de destaque (gold) RESERVADA ao focal (NPS). Indigo é estrutura/marca
   (régua, barras, faixa). Caminho do olho top→fim. Reusa o design system Bizzu
   e os tokens de tema (CSS vars). Sem emoji literal (bundler Windows).

   Consome 2 endpoints sob /api/central (overview / nps). Cada bloco degrada
   com elegância (skeleton no load; erro só quando o overview — a espinha —
   falha). Os buckets do NPS vêm em INGLÊS (promoter/passive/detractor) e a
   comparação É FEITA EM INGLÊS — não regredir isso.
   ========================================================================== */

/* ----------------------------------------------------------------------------
   MÉTRICAS NOVAS (bloco aditivo `metricas` do overview).
   `CentralOverview` em lib/api.ts ainda NÃO tipa esse bloco e não posso tocar
   nela — então tipo aqui INLINE e leio defensivamente (tudo opcional). Se o
   backend ainda não mandar `metricas`, nada disso renderiza (fallback gracioso).
   --------------------------------------------------------------------------- */
interface MetTaxaResolucao {
  fechados: number;
  total: number;
  /** % (1 casa) ou null quando total == 0. */
  percentual: number | null;
}
interface MetLoopsFechados {
  melhorias_avisadas: number;
  clientes_avisados: number;
}
interface MetTempo1aAbordagem {
  amostra: number;
  media_dias: number | null;
  mediana_dias: number | null;
}
interface MetNpsPorTema {
  cluster_id: string;
  tema: string;
  volume: number;
  com_nota: number;
  media: number | null;
  sentimento: string | null;
}
interface CentralMetricas {
  taxa_resolucao?: MetTaxaResolucao | null;
  loops_fechados?: MetLoopsFechados | null;
  tempo_1a_abordagem?: MetTempo1aAbordagem | null;
  nps_por_tema?: MetNpsPorTema[] | null;
  /** Follow-ups VENCIDOS (feedbacks com `follow_up_at <= agora`) — fila p/ hoje. */
  follow_up_pendentes?: number | null;
}
/** Overview + o bloco novo, sem alterar o tipo compartilhado. */
type OverviewComMetricas = CentralOverview & { metricas?: CentralMetricas | null };

/** Formata número curto (sem casas se inteiro, 1 casa se fracionário). */
function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(".", ",");
}

/** Mapeia sentimento do tema p/ a classe de pílula de score já existente. */
function sentPill(sent: string | null): string {
  if (sent === "positivo") return "promoter";
  if (sent === "negativo") return "detractor";
  return "passive";
}

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
      <div className="mon-top">
        <div className="card mon-hero-nps">
          <div className="sk-line sk-sm w-40" />
          <div className="sk-line sk-lg" style={{ height: 84, width: 160, margin: "20px 0 16px" }} />
          <div className="sk-line sk-sm w-80" />
        </div>
        <div className="mon-sats">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card mon-sat">
              <div className="sk-line sk-sm w-60" />
              <div className="sk-line sk-lg w-40" style={{ height: 34, margin: "12px 0 10px" }} />
              <div className="sk-line sk-sm w-80" />
            </div>
          ))}
        </div>
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
          <div className="mon-head-left">
            <span className="mon-kicker">Monitorar a operação</span>
            <h1 className="page-title">Monitorar</h1>
            <span className="mon-rule" aria-hidden />
          </div>
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
          <div className="mon-head-left">
            <span className="mon-kicker">Monitorar a operação</span>
            <h1 className="page-title">Monitorar</h1>
            <span className="mon-rule" aria-hidden />
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

  // Bloco novo do backend (aditivo). Leitura defensiva: cada métrica só aparece
  // se vier com os campos que precisa — senão a seção inteira/ o card somem.
  const met = (overview as OverviewComMetricas).metricas ?? null;
  const mTaxa = met?.taxa_resolucao ?? null;
  const mLoops = met?.loops_fechados ?? null;
  const mTempo = met?.tempo_1a_abordagem ?? null;
  // Só temas que têm nota (sem nota não dá NPS); o backend já ordena por volume.
  // Limito a poucos para manter a leitura "bato o olho e entendo".
  const mTemas = (met?.nps_por_tema ?? [])
    .filter((t) => t && t.com_nota > 0 && t.media !== null)
    .slice(0, 6);
  // Fila de follow-up: feedbacks com reabordagem vencida (para hoje). Indicador
  // honesto — só aparece quando o backend manda o número E há pendência.
  const followUpPendentes = met?.follow_up_pendentes ?? 0;
  const temMetricas = !!(mTaxa || mLoops || mTempo || mTemas.length > 0 || followUpPendentes > 0);

  // Os 4 números SATÉLITES, sobre a BASE TOTAL. "Cancelaram" é um recorte da
  // base (segmento churn) → mostra o denominador no rótulo de apoio.
  const SATS: {
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
  // Follow-ups vencidos entram PRIMEIRO (são "para hoje", a ação mais imediata).
  const destaques = buildDestaques(overview);
  if (followUpPendentes > 0) {
    destaques.unshift({
      id: "follow-up-pendentes",
      sev: "alert",
      text: `${followUpPendentes} follow-up${followUpPendentes === 1 ? "" : "s"} para reabordar hoje`,
    });
  }

  return (
    <div>
      <div className="page-head">
        <div className="mon-head-left">
          <span className="mon-kicker">Monitorar a operação</span>
          <h1 className="page-title">Monitorar</h1>
          <span className="mon-rule" aria-hidden />
          <div className="page-sub">
            De relance: quantos clientes a gente abordou, quantos responderam, quantos
            ainda não e quantos cancelaram — e o que eles disseram.
          </div>
        </div>
        <span className="refresh-note">atualiza a cada 30s</span>
      </div>

      {/* 1) FOCO + SATÉLITES — o NPS é o herói (gold, gigante); os 4 números
         sobre a base total recuam ao redor, ~2,3× menores. */}
      <div className="mon-top">
        {/* HERÓI: NPS — média + distribuição/buckets dentro do próprio card */}
        <Reveal className="card mon-hero-nps">
          <div className="mon-hero-eyebrow">NPS da operação</div>
          <div className={`mon-hero-value ${npsClass(nps.media)}`}>
            {nps.media ?? "—"}
            <span className="mon-hero-unit">/10</span>
          </div>
          <div className="mon-hero-cap">
            {nps.deram} de {base} deram nota
          </div>

          {npsTotal > 0 ? (
            <div className="mon-hero-dist">
              <div className="dist-bar">
                <span style={{ width: `${pct(nps.promotores, npsTotal)}%`, background: "var(--promoter)" }} />
                <span style={{ width: `${pct(nps.neutros, npsTotal)}%`, background: "var(--passive)" }} />
                <span style={{ width: `${pct(nps.detratores, npsTotal)}%`, background: "var(--detractor)" }} />
              </div>
              <div className="mon-hero-legend">
                <div className="mon-hero-leg">
                  <span className="dot" style={{ background: "var(--promoter)" }} />
                  <span className="mon-hero-leg-n mono">{nps.promotores}</span>
                  <span className="mon-hero-leg-l">Promotores</span>
                </div>
                <div className="mon-hero-leg">
                  <span className="dot" style={{ background: "var(--passive)" }} />
                  <span className="mon-hero-leg-n mono">{nps.neutros}</span>
                  <span className="mon-hero-leg-l">Neutros</span>
                </div>
                <div className="mon-hero-leg">
                  <span className="dot" style={{ background: "var(--detractor)" }} />
                  <span className="mon-hero-leg-n mono">{nps.detratores}</span>
                  <span className="mon-hero-leg-l">Detratores</span>
                </div>
              </div>
            </div>
          ) : (
            <p className="mon-empty-inline">Ainda sem notas de NPS para distribuir.</p>
          )}
        </Reveal>

        {/* SATÉLITES: os 4 números sobre a base total, em grade 2×2 */}
        <Stagger className="mon-sats" stagger={0.06}>
          {SATS.map((h) => (
            <StaggerItem key={h.label} className="card mon-sat">
              <span className="mon-sat-accent" style={{ background: h.accent }} aria-hidden />
              <div className="mon-sat-label">{h.label}</div>
              <div className={`mon-sat-value ${h.cls ?? ""}`}>{h.n}</div>
              <div className="mon-sat-sub">{h.sub}</div>
            </StaggerItem>
          ))}
        </Stagger>
      </div>

      {/* 2) FAIXA "O QUE FAZER AGORA" — ponte de ação, computada client-side dos
         números que já chegam. Pills pequenas; cor por severidade. Some se vazia. */}
      {destaques.length > 0 && (
        <Reveal className="mon-act" aria-label="Destaques: o que fazer agora">
          <span className="mon-act-bar" aria-hidden />
          <span className="mon-act-label">O que fazer agora</span>
          <div className="mon-act-pills">
            {destaques.map((d) => {
              const isAlert = d.sev === "alert";
              return (
                <span key={d.id} className={`mon-act-pill ${isAlert ? "alert" : "watch"}`}>
                  <span className="mon-act-dot" aria-hidden />
                  {d.text}
                </span>
              );
            })}
          </div>
        </Reveal>
      )}

      {/* 3) MÉTRICAS DA OPERAÇÃO — taxa de resolução, loops fechados e tempo
         até a 1ª abordagem (+ NPS por tema). Vêm do bloco novo `metricas` do
         overview. Toda a seção some se o backend ainda não mandar nada. */}
      {temMetricas && (
        <Reveal className="mon-section">
          <div className="mon-section-head">
            <div className="section-title">Métricas da operação</div>
            <span className="mon-rule sm" aria-hidden />
            <div className="card-head-sub">
              o quanto a gente resolve, fecha o ciclo e quão rápido aborda
            </div>
          </div>

          <Stagger className="mon-met-grid" stagger={0.06}>
            {/* Taxa de resolução */}
            {mTaxa && (
              <StaggerItem className="card mon-sat mon-met">
                <span className="mon-sat-accent" style={{ background: "var(--indigo)" }} aria-hidden />
                <div className="mon-sat-label">Taxa de resolução</div>
                <div
                  className={`mon-sat-value ${
                    mTaxa.percentual === null
                      ? "nps-none"
                      : mTaxa.percentual >= 60
                      ? "nps-good"
                      : mTaxa.percentual >= 30
                      ? "nps-mid"
                      : "nps-bad"
                  }`}
                >
                  {mTaxa.percentual === null ? "—" : `${fmtNum(mTaxa.percentual)}%`}
                </div>
                <div className="mon-sat-sub">
                  {mTaxa.total > 0
                    ? `${mTaxa.fechados} de ${mTaxa.total} feedbacks fechados`
                    : "ainda sem feedbacks para fechar"}
                </div>
              </StaggerItem>
            )}

            {/* Loops fechados */}
            {mLoops && (
              <StaggerItem className="card mon-sat mon-met">
                <span className="mon-sat-accent" style={{ background: "var(--promoter)" }} aria-hidden />
                <div className="mon-sat-label">Loops fechados</div>
                <div className="mon-sat-value nps-good">{fmtNum(mLoops.melhorias_avisadas)}</div>
                <div className="mon-sat-sub">
                  {mLoops.melhorias_avisadas === 1 ? "melhoria avisada" : "melhorias avisadas"}
                  {" · "}
                  {mLoops.clientes_avisados}{" "}
                  {mLoops.clientes_avisados === 1 ? "cliente avisado" : "clientes avisados"}
                </div>
              </StaggerItem>
            )}

            {/* Tempo até a 1ª abordagem */}
            {mTempo && (
              <StaggerItem className="card mon-sat mon-met">
                <span className="mon-sat-accent" style={{ background: "var(--indigo-light)" }} aria-hidden />
                <div className="mon-sat-label">Tempo até 1ª abordagem</div>
                <div className={`mon-sat-value ${mTempo.media_dias === null ? "nps-none" : ""}`}>
                  {mTempo.media_dias === null ? (
                    "—"
                  ) : (
                    <>
                      {fmtNum(mTempo.media_dias)}
                      <span className="mon-sat-unit">{mTempo.media_dias === 1 ? "dia" : "dias"}</span>
                    </>
                  )}
                </div>
                <div className="mon-sat-sub">
                  {mTempo.amostra > 0
                    ? `mediana ${fmtNum(mTempo.mediana_dias)} · ${mTempo.amostra} ${
                        mTempo.amostra === 1 ? "abordagem" : "abordagens"
                      }`
                    : "ainda sem abordagens medidas"}
                </div>
              </StaggerItem>
            )}

            {/* Follow-ups para hoje (vencidos) — atalho para a fila na tela
               Feedbacks. Só aparece quando há pendência. */}
            {followUpPendentes > 0 && (
              <StaggerItem className="card mon-sat mon-met">
                <span className="mon-sat-accent" style={{ background: "var(--detractor)" }} aria-hidden />
                <div className="mon-sat-label">Follow-ups para hoje</div>
                <div className="mon-sat-value nps-bad">{fmtNum(followUpPendentes)}</div>
                <div className="mon-sat-sub">
                  <a href="/feedbacks" className="mon-followup-link">
                    {followUpPendentes === 1 ? "feedback a reabordar" : "feedbacks a reabordar"} — abrir a fila →
                  </a>
                </div>
              </StaggerItem>
            )}
          </Stagger>

          {/* NPS por tema — mini-lista (só temas com nota). */}
          {mTemas.length > 0 && (
            <div className="card mon-resp mon-temas">
              <div className="card-head">
                <div>
                  <div className="section-title">NPS por tema</div>
                  <div className="card-head-sub">a nota média de quem tocou em cada assunto</div>
                </div>
              </div>
              <ul className="mon-temas-list">
                {mTemas.map((t) => (
                  <li key={t.cluster_id} className="mon-temas-item">
                    <span className={`score-pill ${sentPill(t.sentimento)}`}>{fmtNum(t.media)}</span>
                    <div className="mon-temas-txt">
                      <div className="mon-temas-name">
                        {t.tema || <span className="faint">sem rótulo</span>}
                      </div>
                      <div className="mon-temas-meta">
                        {t.com_nota} de {t.volume} {t.volume === 1 ? "menção" : "menções"} com nota
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Reveal>
      )}

      {/* 4) AS RESPOSTAS — badge em coluna fixa, fala, nota mono à direita. */}
      <Reveal className="mon-section">
        <div className="mon-section-head">
          <div className="section-title">Respostas dos clientes</div>
          <span className="mon-rule sm" aria-hidden />
          <div className="card-head-sub">o que cada pessoa disse, com a nota e quando</div>
        </div>

        <div className="card mon-resp">
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
                  <div className="mon-resp-nota">
                    <span className="mon-resp-nota-lbl">nota</span>
                    <span className={`mon-resp-nota-n ${pillClass(it.bucket)}`}>{it.score}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Reveal>

      <p className="count-line">
        Base de {base} contatos · NPS e respostas reais dos clientes da operação.
      </p>

    </div>
  );
}
