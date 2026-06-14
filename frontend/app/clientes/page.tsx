"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import { api, type Cliente } from "@/lib/api";

/** Mapeia perfil da Bizzu -> classe de badge. Cobre variações de grafia. */
function perfilMeta(perfil: string | null): { cls: string; label: string } | null {
  if (!perfil) return null;
  const key = perfil.toLowerCase();
  if (key.includes("risco")) return { cls: "p-risco", label: perfil };
  if (key.includes("promot")) return { cls: "p-promotor", label: perfil };
  if (key.includes("silenc")) return { cls: "p-silencioso", label: perfil };
  if (key.includes("ativ") || key.includes("engaj")) return { cls: "p-ativo", label: perfil };
  return { cls: "p-neutro", label: perfil };
}

function perfilBadge(perfil: string | null) {
  const m = perfilMeta(perfil);
  if (!m) return <span className="faint">—</span>;
  return <span className={`badge perfil ${m.cls}`}>{m.label.replace(/_/g, " ")}</span>;
}

/** NPS por faixa: ≤6 detrator, 7-8 passivo, 9-10 promotor. */
function npsTag(score: number | null) {
  if (score === null || score === undefined) return <span className="nps-tag none">—</span>;
  const cls = score <= 6 ? "detractor" : score <= 8 ? "passive" : "promoter";
  const label = score <= 6 ? "detrator" : score <= 8 ? "passivo" : "promotor";
  return (
    <span className={`nps-tag ${cls}`}>
      <span className="nps-num">{score}</span>
      {label}
    </span>
  );
}

function renovaCell(dias: number | null) {
  if (dias === null || dias === undefined) return <span className="faint">—</span>;
  const soon = dias <= 7;
  return (
    <span className={soon ? "renova-soon" : "dim"}>
      {dias <= 0 ? "vencido" : `${dias} dia${dias === 1 ? "" : "s"}`}
    </span>
  );
}

const TIPO_LABEL: Record<string, string> = {
  nps: "NPS",
  churn: "Cancelamento",
  exit: "Exit survey",
  csat: "CSAT",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit",
  });
}

export default function ClientesPage() {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState("");
  const [perfil, setPerfil] = useState("");
  const [planType, setPlanType] = useState("");
  const [soRisco, setSoRisco] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (search.trim()) qs.set("search", search.trim());
      if (perfil) qs.set("perfil", perfil);
      if (planType) qs.set("plan_type", planType);
      const path = `/api/clientes${qs.toString() ? `?${qs}` : ""}`;
      // Aceita array puro OU { items } (defensivo contra desvio do backend).
      const raw = await api.get<Cliente[] | { items: Cliente[] }>(path);
      setClientes(Array.isArray(raw) ? raw : raw.items ?? []);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [search, perfil, planType]);

  // Debounce na busca; filtros de select disparam imediato.
  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  // Opções de filtro derivadas dos dados carregados (sem hard-code).
  const perfilOptions = useMemo(
    () => [...new Set(clientes.map((c) => c.perfil).filter(Boolean) as string[])].sort(),
    [clientes],
  );
  const planOptions = useMemo(
    () => [...new Set(clientes.map((c) => c.plan_type).filter(Boolean) as string[])].sort(),
    [clientes],
  );

  // Fila de risco: contas que não estão saudáveis, pior Health primeiro.
  const emRiscoCount = useMemo(
    () => clientes.filter((c) => c.health_band !== "healthy").length,
    [clientes],
  );
  const visiveis = useMemo(() => {
    if (!soRisco) return clientes;
    return [...clientes]
      .filter((c) => c.health_band !== "healthy")
      .sort((a, b) => a.health - b.health);
  }, [clientes, soRisco]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Clientes</h1>
          <div className="page-sub">Todos os clientes contatáveis por WhatsApp — perfil, plano e NPS</div>
        </div>
        {!loading && <span className="refresh-note">{clientes.length} clientes</span>}
      </div>

      <div className="note">
        <span className="note-ico">ℹ️</span>
        <span>
          Clientes <b>sem telefone</b> cadastrado na Bizzu (131) não aparecem aqui — não são
          contatáveis por WhatsApp, então ficam fora do alcance das pesquisas.
        </span>
      </div>

      <div className="toolbar">
        <label className="search">
          <span className="ico">🔍</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome ou WhatsApp…"
          />
        </label>
        <select value={perfil} onChange={(e) => setPerfil(e.target.value)} aria-label="Filtrar por perfil">
          <option value="">Todos os perfis</option>
          {perfilOptions.map((p) => (
            <option key={p} value={p}>{p.replace(/_/g, " ")}</option>
          ))}
        </select>
        <select value={planType} onChange={(e) => setPlanType(e.target.value)} aria-label="Filtrar por plano">
          <option value="">Todos os planos</option>
          {planOptions.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <button
          type="button"
          className={`risk-chip ${soRisco ? "on" : ""}`}
          onClick={() => setSoRisco((v) => !v)}
          aria-pressed={soRisco}
          title="Mostrar só contas que precisam de atenção — pior Health primeiro"
        >
          ⚠️ Em risco <span className="risk-n">{emRiscoCount}</span>
        </button>
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar os clientes ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Saúde</th>
                <th>Perfil</th>
                <th>Plano</th>
                <th>NPS</th>
                <th>Renova em</th>
                <th>Último feedback</th>
                <th>Feedbacks</th>
              </tr>
            </thead>
            <tbody>
              {!err && visiveis.length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <div className="empty">
                      <div className="big">👥</div>
                      {loading
                        ? "Carregando…"
                        : soRisco
                        ? "Nenhuma conta em risco 🎉"
                        : search || perfil || planType
                        ? "Nenhum cliente bate com os filtros."
                        : "Nenhum cliente contatável ainda."}
                    </div>
                  </td>
                </tr>
              )}
              {visiveis.map((c) => (
                <tr key={c.id}>
                  <td>
                    <div className="cell-person">
                      <Avatar name={c.nome} seed={c.id} />
                      <div className="cell-person-txt">
                        <Link href={`/contatos/${c.id}`} className="row-link">
                          {c.nome || "sem nome"}
                        </Link>
                        <span className="mono cell-person-sub">{c.whatsapp}</span>
                      </div>
                    </div>
                  </td>
                  <td>{healthCell(c.health, c.health_band, c.health_factors)}</td>
                  <td>{perfilBadge(c.perfil)}</td>
                  <td className="dim">
                    {c.plano || c.plan_type || <span className="faint">—</span>}
                  </td>
                  <td>{npsTag(c.nps_score)}</td>
                  <td>{renovaCell(c.dias_para_renovar)}</td>
                  <td className="dim">
                    {c.ultimo_feedback_em ? (
                      <>
                        {fmtDate(c.ultimo_feedback_em)}
                        {c.ultimo_feedback_tipo && (
                          <div className="faint" style={{ fontSize: 11.5 }}>
                            {TIPO_LABEL[c.ultimo_feedback_tipo] ?? c.ultimo_feedback_tipo}
                          </div>
                        )}
                      </>
                    ) : (
                      <span className="faint">nunca</span>
                    )}
                  </td>
                  <td className="dim">{c.total_feedbacks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
