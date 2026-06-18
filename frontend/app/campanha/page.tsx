"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  campanha as campanhaApi,
  type CampanhaStats,
  type SelosResponse,
  type Selo,
} from "@/lib/api";

/* Painel de monitoramento da campanha win-back.
   Consome GET /api/campanha/stats: funil (universo → contatados → respondeu →
   cortesia → reativou; + faltam), cards de números, por_canal, por_selo (chips
   coloridos) e insights (top temas com nº de negativos). Reusa o design system
   (cards, kpi, chips, page-head) — identidade dark editorial Bizzu. */

/** Rótulos amigáveis dos canais conhecidos (fallback = o próprio nome). */
const CANAL_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  ligacao: "Ligação",
  email: "E-mail",
  presencial: "Presencial",
  outro: "Outro",
};

/** Etapas do funil em ordem, com a cor de acento de cada uma. As 5 etapas
    espelham o backend; "a contatar" recebe a etapa `faltam`. */
const ETAPA_META: Record<string, { cor: string }> = {
  "a contatar": { cor: "var(--text-faint)" },
  contatado: { cor: "var(--indigo)" },
  respondeu: { cor: "var(--indigo-light)" },
  cortesia: { cor: "var(--passive)" },
  reativou: { cor: "var(--gold)" },
};

/** Buckets de alcance do validador (app/domain/contacts/whatsapp.py · alcance()).
    Ordem fixa de exibição; label, emoji (escape \u{...}) e cor de acento por bucket.
    Só `whatsapp` conta como "com WhatsApp" (celular BR válido) — fixo/grupo NÃO. */
const ALCANCE_META: { key: string; label: string; emoji: string; cor: string }[] = [
  { key: "whatsapp", label: "Celular / WhatsApp", emoji: "\u{1F4AC}", cor: "var(--indigo-light)" },
  { key: "so_email", label: "Só e-mail", emoji: "\u{2709}\u{FE0F}", cor: "var(--text-dim)" },
  { key: "fixo", label: "Telefone fixo", emoji: "\u{260E}\u{FE0F}", cor: "var(--passive)" },
  { key: "grupo", label: "Grupo", emoji: "\u{1F465}", cor: "var(--passive)" },
  { key: "sem_contato", label: "Sem contato", emoji: "\u{1F6AB}", cor: "var(--text-faint)" },
  { key: "invalido", label: "Inválido", emoji: "\u{26A0}\u{FE0F}", cor: "var(--text-faint)" },
];

function pct(n: number, total: number): number {
  return total > 0 ? (n / total) * 100 : 0;
}

/** Cor de um selo a partir do catálogo (fallback indigo). */
function corDoSelo(catalogo: Selo[], nome: string): string {
  return catalogo.find((s) => s.nome === nome)?.cor || "var(--indigo)";
}

export default function CampanhaPage() {
  const [stats, setStats] = useState<CampanhaStats | null>(null);
  const [selos, setSelos] = useState<SelosResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, sel] = await Promise.all([
        campanhaApi.stats(),
        campanhaApi.listSelos(),
      ]);
      setStats(s);
      setSelos(sel);
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

  const catalogo = selos?.catalogo ?? [];

  // Maior valor entre as etapas do funil — escala as barras proporcionalmente.
  const maxFunil = useMemo(() => {
    if (!stats) return 0;
    return Math.max(1, ...stats.funil.map((f) => f.count));
  }, [stats]);

  // Maior count entre os insights — escala as mini-barras de volume.
  const maxInsight = useMemo(() => {
    if (!stats || stats.insights.length === 0) return 1;
    return Math.max(1, ...stats.insights.map((i) => i.count));
  }, [stats]);

  if (err) {
    return (
      <div>
        <div className="page-head">
          <h1 className="page-title">Campanha</h1>
        </div>
        <div className="flash err">
          Não consegui carregar a campanha ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      </div>
    );
  }

  if (!stats) return <div className="empty">Carregando…</div>;

  const conv =
    stats.universo > 0 ? Math.round(pct(stats.contatados, stats.universo)) : null;
  const canais = Object.entries(stats.por_canal).sort((a, b) => b[1] - a[1]);
  const porSelo = Object.entries(stats.por_selo).sort((a, b) => b[1] - a[1]);

  // Quebra do universo por bucket de alcance (só os presentes em por_alcance,
  // na ordem fixa de ALCANCE_META). O backend só devolve buckets > 0; somam == universo.
  const porAlcance = stats.por_alcance ?? {};
  const alcanceRows = ALCANCE_META.filter((m) => (porAlcance[m.key] ?? 0) > 0).map(
    (m) => ({ ...m, n: porAlcance[m.key] as number }),
  );

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Campanha</h1>
          <div className="page-sub">
            Win-back de cancelados — quem já abordamos, quem respondeu e quem reativou
          </div>
        </div>
        <span className="refresh-note">atualiza a cada 30s</span>
      </div>

      {/* Cards de números */}
      <div className="cmp-cards">
        <div className="card kpi">
          <div className="kpi-label">Universo</div>
          <div className="kpi-value">{stats.universo}</div>
          <div className="kpi-hint">clientes que cancelaram</div>
          <div className="cmp-wa-split">
            <span
              className="cmp-wa wa-on"
              title="Alcançáveis no WhatsApp = celular BR válido (fixo e grupo NÃO contam)"
            >
              {"\u{1F4AC}"} {stats.com_whatsapp} com WhatsApp
            </span>
            <span
              className="cmp-wa wa-off"
              title="Resto do universo: só e-mail, fixo, grupo, sem contato ou inválido"
            >
              {"\u{2709}\u{FE0F}"} {stats.sem_whatsapp} sem WhatsApp
            </span>
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Contatados</div>
          <div className="kpi-value">{stats.contatados}</div>
          <div className="kpi-hint">{conv !== null ? `${conv}% do universo` : "—"}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Responderam</div>
          <div className="kpi-value">{stats.responderam}</div>
          <div className="kpi-hint">voltaram a falar com a gente</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Cortesia</div>
          <div className="kpi-value">{stats.cortesia}</div>
          <div className="kpi-hint">ganharam a oferta</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Reativaram</div>
          <div className="kpi-value cmp-reativou">{stats.reativaram}</div>
          <div className="kpi-hint">voltaram a assinar</div>
        </div>
      </div>

      {/* Quebra do universo por alcance — transparência dos números de WhatsApp */}
      {alcanceRows.length > 0 && (
        <div className="card cmp-block">
          <div className="card-head">
            <div>
              <div className="section-title">Universo por alcance</div>
              <div className="card-head-sub">
                como dá pra falar com cada um dos {stats.universo} cancelados ·{" "}
                <strong>com WhatsApp</strong> = só celular BR válido (fixo e grupo NÃO contam)
              </div>
            </div>
          </div>
          <div className="cmp-pad">
            <ul className="cmp-canal-list">
              {alcanceRows.map((r) => (
                <li key={r.key} className="cmp-canal-row">
                  <span className="cmp-canal-name">
                    <span aria-hidden="true">{r.emoji} </span>
                    {r.label}
                  </span>
                  <span className="cmp-alcance-meta">
                    <span className="cmp-canal-n mono" style={{ color: r.cor }}>
                      {r.n}
                    </span>
                    <span className="cmp-alcance-pct">
                      {Math.round(pct(r.n, stats.universo))}%
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Funil */}
      <div className="card cmp-block">
        <div className="card-head">
          <div>
            <div className="section-title">Funil da campanha</div>
            <div className="card-head-sub">
              do universo de cancelados até a reativação · {stats.faltam} ainda a contatar ·{" "}
              {stats.com_whatsapp} com WhatsApp, {stats.sem_whatsapp} sem WhatsApp
            </div>
          </div>
        </div>
        <div className="cmp-funnel">
          {stats.funil.map((f) => {
            const cor = ETAPA_META[f.etapa]?.cor ?? "var(--indigo)";
            return (
              <div className="cmp-fn-step" key={f.etapa}>
                <div className="cmp-fn-top">
                  <span className="cmp-fn-label">{f.etapa}</span>
                  <span className="cmp-fn-n mono">{f.count}</span>
                </div>
                <div className="cmp-fn-track">
                  <span
                    className="cmp-fn-fill"
                    style={{ width: `${pct(f.count, maxFunil)}%`, background: cor }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="cmp-two-col">
        {/* Por canal */}
        <div className="card cmp-block">
          <div className="card-head">
            <div className="section-title">Abordagens por canal</div>
          </div>
          <div className="cmp-pad">
            {canais.length === 0 ? (
              <div className="empty">Nenhuma abordagem registrada ainda.</div>
            ) : (
              <ul className="cmp-canal-list">
                {canais.map(([canal, n]) => (
                  <li key={canal} className="cmp-canal-row">
                    <span className="cmp-canal-name">{CANAL_LABEL[canal] ?? canal}</span>
                    <span className="cmp-canal-n mono">{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Por selo (chips coloridos) */}
        <div className="card cmp-block">
          <div className="card-head">
            <div className="section-title">Selos aplicados</div>
          </div>
          <div className="cmp-pad">
            {porSelo.length === 0 ? (
              <div className="empty">Nenhum selo aplicado no universo ainda.</div>
            ) : (
              <div className="cmp-selo-chips">
                {porSelo.map(([nome, n]) => {
                  const cor = corDoSelo(catalogo, nome);
                  return (
                    <span
                      key={nome}
                      className="selo-chip"
                      style={{
                        borderColor: cor,
                        color: cor,
                        background: `color-mix(in srgb, ${cor} 14%, transparent)`,
                      }}
                    >
                      <span className="selo-dot" style={{ background: cor }} />
                      {nome}
                      <span className="selo-chip-n mono">{n}</span>
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Insights — top temas com negativos */}
      <div className="card cmp-block">
        <div className="card-head">
          <div>
            <div className="section-title">Por que cancelaram</div>
            <div className="card-head-sub">
              temas mais citados pelo universo da campanha (· n.º de menções negativas)
            </div>
          </div>
        </div>
        <div className="cmp-pad">
          {stats.insights.length === 0 ? (
            <div className="empty">Ainda não há temas classificados nos cancelamentos.</div>
          ) : (
            <ul className="cmp-insight-list">
              {stats.insights.map((it) => (
                <li key={it.tema} className="cmp-insight-row">
                  <div className="cmp-insight-head">
                    <span className="cmp-insight-name">{it.tema}</span>
                    <span className="cmp-insight-counts">
                      <span className="mono">{it.count}</span>
                      {it.neg > 0 && (
                        <span className="cmp-insight-neg">· {it.neg} neg</span>
                      )}
                    </span>
                  </div>
                  <div className="cmp-insight-track">
                    <span
                      className="cmp-insight-fill"
                      style={{ width: `${pct(it.count, maxInsight)}%` }}
                    />
                    {it.neg > 0 && (
                      <span
                        className="cmp-insight-fill neg"
                        style={{ width: `${pct(it.neg, maxInsight)}%` }}
                      />
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="count-line">
        Fonte: feedbacks de cancelamento + selos e abordagens registradas na campanha.
      </p>
    </div>
  );
}
