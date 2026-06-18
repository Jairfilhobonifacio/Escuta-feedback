"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import {
  clientes as clientesApi,
  campanha as campanhaApi,
  type Cliente,
  type Selo,
  type ClienteFiltro,
  type EstadoAssinatura,
  type NpsBucket,
  type HealthBand,
  type TemWhatsappFiltro,
} from "@/lib/api";

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

/** Rótulos legíveis dos estados de assinatura (snapshot partner). */
const ESTADO_OPCOES: { value: EstadoAssinatura; label: string }[] = [
  { value: "active_paying", label: "Pagante ativo" },
  { value: "past_due", label: "Em atraso" },
  { value: "paid_without_access", label: "Pago sem acesso" },
  { value: "complimentary", label: "Cortesia" },
  { value: "cancelled", label: "Cancelado" },
];

const NPS_OPCOES: { value: NpsBucket; label: string }[] = [
  { value: "promotor", label: "Promotores" },
  { value: "neutro", label: "Neutros" },
  { value: "detrator", label: "Detratores" },
];

const HEALTH_OPCOES: { value: HealthBand; label: string }[] = [
  { value: "healthy", label: "Saudável" },
  { value: "watch", label: "Atenção" },
  { value: "at_risk", label: "Em risco" },
];

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit",
  });
}

/** Cor de um selo a partir do catálogo (fallback indigo). */
function corDoSelo(catalogo: Selo[], nome: string): string {
  return catalogo.find((s) => s.nome === nome)?.cor || "var(--indigo)";
}

/** Célula de selos: chips coloridos + controle "+ selo" (aplicar do catálogo ou
    criar novo). Aplica via POST /api/contacts/{id}/selos e avisa o pai para
    atualizar a linha localmente (sem recarregar a lista inteira). */
function SelosCell({
  cliente,
  catalogo,
  onApplied,
  onRemoved,
}: {
  cliente: Cliente;
  catalogo: Selo[];
  onApplied: (clienteId: string, nome: string, cor: string) => void;
  onRemoved: (clienteId: string, nome: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [novo, setNovo] = useState("");
  const [cor, setCor] = useState("#6c5ce7");
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // Fecha o picker ao clicar fora.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Selos do catálogo ainda não aplicados a este cliente (candidatos a aplicar).
  const disponiveis = catalogo.filter((s) => !cliente.selos.includes(s.nome));

  async function aplicar(nome: string, corSelo?: string) {
    const alvo = nome.trim();
    if (!alvo || busy) return;
    setBusy(true);
    try {
      await campanhaApi.applySelo(cliente.id, { nome: alvo, cor: corSelo });
      onApplied(cliente.id, alvo, corSelo || corDoSelo(catalogo, alvo));
      setNovo("");
      setOpen(false);
    } catch {
      /* erro silencioso — o estado não muda, o operador tenta de novo */
    } finally {
      setBusy(false);
    }
  }

  async function remover(nome: string) {
    if (busy) return;
    setBusy(true);
    try {
      await campanhaApi.removeSeloFromContact(cliente.id, nome);
      onRemoved(cliente.id, nome);
    } catch {
      /* erro silencioso */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="selos-cell" ref={boxRef}>
      <div className="selos-chips">
        {cliente.selos.map((nome) => {
          const c = corDoSelo(catalogo, nome);
          return (
            <span
              key={nome}
              className="selo-chip"
              style={{
                borderColor: c,
                color: c,
                background: `color-mix(in srgb, ${c} 14%, transparent)`,
              }}
            >
              <span className="selo-dot" style={{ background: c }} />
              {nome}
              <button
                type="button"
                className="selo-x"
                onClick={() => remover(nome)}
                aria-label={`Remover selo ${nome}`}
                disabled={busy}
              >
                {"\u{2715}"}
              </button>
            </span>
          );
        })}
        <button
          type="button"
          className="selo-add"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label="Aplicar selo"
        >
          {"\u{FF0B}"} selo
        </button>
      </div>

      {open && (
        <div className="selo-pop">
          {disponiveis.length > 0 && (
            <div className="selo-pop-list">
              {disponiveis.map((s) => (
                <button
                  key={s.nome}
                  type="button"
                  className="selo-pop-item"
                  onClick={() => aplicar(s.nome, s.cor)}
                  disabled={busy}
                >
                  <span className="selo-dot" style={{ background: s.cor }} />
                  {s.nome}
                </button>
              ))}
            </div>
          )}
          <div className="selo-pop-create">
            <input
              type="color"
              value={cor}
              onChange={(e) => setCor(e.target.value)}
              aria-label="Cor do novo selo"
              className="selo-color"
            />
            <input
              value={novo}
              onChange={(e) => setNovo(e.target.value)}
              placeholder="Novo selo…"
              onKeyDown={(e) => {
                if (e.key === "Enter") aplicar(novo, cor);
              }}
            />
            <button
              type="button"
              className="btn sm"
              onClick={() => aplicar(novo, cor)}
              disabled={busy || !novo.trim()}
            >
              Criar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ClientesPage() {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [catalogo, setCatalogo] = useState<Selo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Filtros server-side (vão para /api/clientes via ClienteFiltro).
  const [search, setSearch] = useState("");
  const [perfil, setPerfil] = useState("");
  const [planType, setPlanType] = useState("");
  const [estado, setEstado] = useState<EstadoAssinatura | "">("");
  const [npsBucket, setNpsBucket] = useState<NpsBucket | "">("");
  const [healthBand, setHealthBand] = useState<HealthBand | "">("");
  const [temWa, setTemWa] = useState<TemWhatsappFiltro | "">("");
  // Refinos client-side (não fazem parte do ClienteFiltro do backend).
  const [seloFiltro, setSeloFiltro] = useState("");
  const [soRisco, setSoRisco] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const filtro: ClienteFiltro = {
        search: search.trim() || undefined,
        perfil: perfil || undefined,
        plan_type: planType || undefined,
        estado: estado || undefined,
        nps_bucket: npsBucket || undefined,
        health_band: healthBand || undefined,
        tem_whatsapp: temWa || undefined,
      };
      const lista = await clientesApi.list(filtro);
      // Defensivo: a API antiga pode não devolver `selos`; garante array em runtime
      // (vários pontos fazem c.selos.includes/.map sem checar).
      setClientes(lista.map((c) => ({ ...c, selos: c.selos ?? [] })));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [search, perfil, planType, estado, npsBucket, healthBand, temWa]);

  // Catálogo de selos — carregado uma vez (best-effort; sem ele os chips usam cor default).
  const loadCatalogo = useCallback(async () => {
    try {
      const sel = await campanhaApi.listSelos();
      setCatalogo(sel.catalogo);
    } catch {
      /* sem catálogo: chips caem na cor default */
    }
  }, []);

  useEffect(() => {
    loadCatalogo();
  }, [loadCatalogo]);

  // Debounce na busca; filtros de select disparam (quase) imediato pelo mesmo timer.
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
  // Opções de selo: união do catálogo + selos já aplicados aos clientes carregados.
  const seloOptions = useMemo(() => {
    const set = new Set<string>(catalogo.map((s) => s.nome));
    for (const c of clientes) for (const s of c.selos) set.add(s);
    return [...set].sort();
  }, [catalogo, clientes]);

  // Aplica/remove selo localmente após a chamada à API (sem recarregar a lista).
  const onSeloApplied = useCallback((id: string, nome: string, cor: string) => {
    setClientes((prev) =>
      prev.map((c) =>
        c.id === id && !c.selos.includes(nome) ? { ...c, selos: [...c.selos, nome] } : c,
      ),
    );
    setCatalogo((prev) =>
      prev.some((s) => s.nome === nome) ? prev : [...prev, { nome, cor }],
    );
  }, []);
  const onSeloRemoved = useCallback((id: string, nome: string) => {
    setClientes((prev) =>
      prev.map((c) => (c.id === id ? { ...c, selos: c.selos.filter((s) => s !== nome) } : c)),
    );
  }, []);

  // Fila de risco: contas que não estão saudáveis, pior Health primeiro.
  const emRiscoCount = useMemo(
    () => clientes.filter((c) => c.health_band !== "healthy").length,
    [clientes],
  );
  const visiveis = useMemo(() => {
    let base = clientes;
    if (seloFiltro) base = base.filter((c) => c.selos.includes(seloFiltro));
    if (!soRisco) return base;
    return [...base]
      .filter((c) => c.health_band !== "healthy")
      .sort((a, b) => a.health - b.health);
  }, [clientes, soRisco, seloFiltro]);

  // Quantos do conjunto carregado são "só e-mail" (sem WhatsApp real).
  const semWaCount = useMemo(
    () => clientes.filter((c) => !c.tem_whatsapp).length,
    [clientes],
  );

  // Há algum filtro ativo? (controla o botão "limpar filtros" e o texto do vazio).
  const algumFiltro =
    !!search ||
    !!perfil ||
    !!planType ||
    !!estado ||
    !!npsBucket ||
    !!healthBand ||
    !!temWa ||
    !!seloFiltro ||
    soRisco;

  const limparFiltros = useCallback(() => {
    setSearch("");
    setPerfil("");
    setPlanType("");
    setEstado("");
    setNpsBucket("");
    setHealthBand("");
    setTemWa("");
    setSeloFiltro("");
    setSoRisco(false);
  }, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Clientes</h1>
          <div className="page-sub">Todos os clientes — perfil, plano, NPS, selos e alcance (WhatsApp vs. só e-mail)</div>
        </div>
        {!loading && <span className="refresh-note">{clientes.length} clientes</span>}
      </div>

      {semWaCount > 0 && (
        <div className="note">
          <span className="note-ico">{"\u{2139}\u{FE0F}"}</span>
          <span>
            <b>{semWaCount}</b> cliente{semWaCount === 1 ? "" : "s"} <b>sem WhatsApp</b> (só e-mail) no universo
            atual — fora do alcance das pesquisas por WhatsApp, mas alvo do win-back por e-mail. Use o filtro
            de alcance para isolá-los.
          </span>
        </div>
      )}

      <div className="toolbar">
        <label className="search">
          <span className="ico">{"\u{1F50D}"}</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome ou WhatsApp…"
          />
        </label>
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value as EstadoAssinatura | "")}
          aria-label="Filtrar por estado da assinatura"
        >
          <option value="">Toda assinatura</option>
          {ESTADO_OPCOES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select value={planType} onChange={(e) => setPlanType(e.target.value)} aria-label="Filtrar por plano">
          <option value="">Todos os planos</option>
          {planOptions.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select value={perfil} onChange={(e) => setPerfil(e.target.value)} aria-label="Filtrar por perfil">
          <option value="">Todos os perfis</option>
          {perfilOptions.map((p) => (
            <option key={p} value={p}>{p.replace(/_/g, " ")}</option>
          ))}
        </select>
        <select
          value={npsBucket}
          onChange={(e) => setNpsBucket(e.target.value as NpsBucket | "")}
          aria-label="Filtrar por faixa de NPS"
        >
          <option value="">Todo NPS</option>
          {NPS_OPCOES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={healthBand}
          onChange={(e) => setHealthBand(e.target.value as HealthBand | "")}
          aria-label="Filtrar por banda de saúde"
        >
          <option value="">Toda saúde</option>
          {HEALTH_OPCOES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={temWa}
          onChange={(e) => setTemWa(e.target.value as TemWhatsappFiltro | "")}
          aria-label="Filtrar por alcance no WhatsApp"
        >
          <option value="">Todo alcance</option>
          <option value="sim">Com WhatsApp</option>
          <option value="nao">Sem WhatsApp (só e-mail)</option>
        </select>
        <select value={seloFiltro} onChange={(e) => setSeloFiltro(e.target.value)} aria-label="Filtrar por selo">
          <option value="">Todos os selos</option>
          {seloOptions.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button
          type="button"
          className={`risk-chip ${soRisco ? "on" : ""}`}
          onClick={() => setSoRisco((v) => !v)}
          aria-pressed={soRisco}
          title="Mostrar só contas que precisam de atenção — pior Health primeiro"
        >
          {"\u{26A0}\u{FE0F}"} Em risco <span className="risk-n">{emRiscoCount}</span>
        </button>
        {algumFiltro && (
          <button type="button" className="btn ghost sm" onClick={limparFiltros}>
            Limpar filtros
          </button>
        )}
      </div>

      <div className="count-line">
        {loading ? (
          "Carregando…"
        ) : (
          <>
            <b>{visiveis.length}</b> cliente{visiveis.length === 1 ? "" : "s"}
            {algumFiltro ? " com os filtros atuais" : " no total"}
          </>
        )}
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
                <th>Selos</th>
              </tr>
            </thead>
            <tbody>
              {!err && visiveis.length === 0 && (
                <tr>
                  <td colSpan={9}>
                    <div className="empty">
                      <div className="big">{"\u{1F465}"}</div>
                      {loading
                        ? "Carregando…"
                        : soRisco
                        ? "Nenhuma conta em risco \u{1F389}"
                        : algumFiltro
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
                        {c.tem_whatsapp ? (
                          <span className="mono cell-person-sub">{c.whatsapp}</span>
                        ) : (
                          <span className="cell-person-sub cliente-nowa" title="Sem WhatsApp — universo só e-mail">
                            {"\u{2709}\u{FE0F}"} só e-mail
                          </span>
                        )}
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
                  <td>
                    <SelosCell
                      cliente={c}
                      catalogo={catalogo}
                      onApplied={onSeloApplied}
                      onRemoved={onSeloRemoved}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
