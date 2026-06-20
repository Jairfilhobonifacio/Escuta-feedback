"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Search, AlertTriangle, Info, Mail, Plus, X, SlidersHorizontal } from "lucide-react";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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

type BadgeVariant = "default" | "positive" | "neutral" | "negative" | "outline" | "accent";

/** Mapeia perfil da Bizzu -> variante do Badge shadcn. Cobre variações de grafia. */
function perfilMeta(perfil: string | null): { variant: BadgeVariant; label: string } | null {
  if (!perfil) return null;
  const key = perfil.toLowerCase();
  if (key.includes("risco")) return { variant: "negative", label: perfil };
  if (key.includes("promot")) return { variant: "positive", label: perfil };
  if (key.includes("silenc")) return { variant: "outline", label: perfil };
  if (key.includes("ativ") || key.includes("engaj")) return { variant: "accent", label: perfil };
  return { variant: "neutral", label: perfil };
}

function perfilBadge(perfil: string | null) {
  const m = perfilMeta(perfil);
  if (!m) return <span className="faint">—</span>;
  return <Badge variant={m.variant}>{m.label.replace(/_/g, " ")}</Badge>;
}

/** NPS por faixa: ≤6 detrator, 7-8 passivo, 9-10 promotor. */
function npsTag(score: number | null) {
  if (score === null || score === undefined) return <span className="faint">—</span>;
  const variant: BadgeVariant = score <= 6 ? "negative" : score <= 8 ? "neutral" : "positive";
  const label = score <= 6 ? "detrator" : score <= 8 ? "passivo" : "promotor";
  return (
    <Badge variant={variant} className="gap-1.5">
      <span className="font-mono font-bold tabular-nums">{score}</span>
      {label}
    </Badge>
  );
}

/** Estado da assinatura (snapshot partner) -> badge legível com cor por situação. */
const ESTADO_META: Record<string, { variant: BadgeVariant; label: string }> = {
  active_paying: { variant: "positive", label: "Pagante" },
  past_due: { variant: "negative", label: "Em atraso" },
  paid_without_access: { variant: "neutral", label: "Pago s/ acesso" },
  complimentary: { variant: "outline", label: "Cortesia" },
  cancelled: { variant: "negative", label: "Cancelado" },
};

function estadoBadge(estado: string | null) {
  if (!estado) return <span className="faint">—</span>;
  const m = ESTADO_META[estado];
  if (!m) return <Badge variant="neutral">{estado.replace(/_/g, " ")}</Badge>;
  return <Badge variant={m.variant}>{m.label}</Badge>;
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

/** Linha-fantasma da tabela durante o load. Recebe `cols` (nº de colunas visíveis)
    para espelhar a tabela atual (5 essenciais, ou 10 com os detalhes abertos) e a
    transição conteúdo↔skeleton não "pular". */
function SkeletonRow({ cols }: { cols: number }) {
  return (
    <tr aria-hidden>
      <td>
        <div className="cell-person">
          <div className="sk-circle" />
          <div className="cell-person-txt" style={{ flex: 1 }}>
            <div className="sk-line sk-sm w-70" style={{ margin: "2px 0" }} />
            <div className="sk-line sk-sm w-40" style={{ margin: "2px 0" }} />
          </div>
        </div>
      </td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div className="sk-line" style={{ width: 70, margin: 0 }} />
          <div className="sk-line sk-sm" style={{ width: 24, margin: 0 }} />
        </div>
      </td>
      <td><div className="sk-line w-50" style={{ margin: 0 }} /></td>
      <td><div className="sk-line w-60" style={{ margin: 0 }} /></td>
      <td><div className="sk-line w-70" style={{ margin: 0 }} /></td>
      {cols > 5 && (
        <>
          <td><div className="sk-line w-60" style={{ margin: 0 }} /></td>
          <td><div className="sk-line w-50" style={{ margin: 0 }} /></td>
          <td><div className="sk-line" style={{ width: 56, margin: 0 }} /></td>
          <td><div className="sk-line w-50" style={{ margin: 0 }} /></td>
          <td><div className="sk-line" style={{ width: 28, margin: 0 }} /></td>
        </>
      )}
    </tr>
  );
}

/** SVG discreto p/ o estado vazio (grupo de pessoas, stroke=currentColor). */
const EMPTY_PEOPLE = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M16 19a4 4 0 0 0-8 0" />
    <circle cx="12" cy="8" r="3" />
    <path d="M5 19a3 3 0 0 1 3-3" />
    <path d="M19 19a3 3 0 0 0-3-3" />
  </svg>
);

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

/** Recortes de alcance — o segmentado que define quem aparece por padrão.
    'sim' (contatáveis no WhatsApp) é o DEFAULT: esconde grupos/fixos/inválidos.
    'nao' = leads só-e-mail (winback legítimo). '' = todos (inclui o lixo). */
const ALCANCE_OPCOES: { value: TemWhatsappFiltro | ""; label: string; hint: string }[] = [
  { value: "sim", label: "Contatáveis", hint: "Com WhatsApp válido — quem dá para abordar" },
  { value: "nao", label: "Winback", hint: "Só e-mail — leads de reativação por e-mail" },
  { value: "", label: "Todos", hint: "Inclui grupos, fixos e inválidos (não-clientes)" },
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
                <X size={11} strokeWidth={2.4} aria-hidden />
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
          <Plus size={12} strokeWidth={2.2} aria-hidden /> selo
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
            <Button
              size="sm"
              onClick={() => aplicar(novo, cor)}
              disabled={busy || !novo.trim()}
            >
              Criar
            </Button>
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
  // Alcance: DEFAULT 'sim' (contatáveis). Esconde grupos/fixos/inválidos do webhook.
  const [temWa, setTemWa] = useState<TemWhatsappFiltro | "">("sim");
  // Refinos client-side (não fazem parte do ClienteFiltro do backend).
  const [seloFiltro, setSeloFiltro] = useState("");
  const [soRisco, setSoRisco] = useState(false);
  // UI: filtros avançados recolhidos + colunas de detalhe recolhidas (densidade).
  const [filtrosAbertos, setFiltrosAbertos] = useState(false);
  const [detalhes, setDetalhes] = useState(false);

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

  // Fila de risco REAL: só a banda 'at_risk' (acionável), não "tudo que não é healthy".
  const emRiscoCount = useMemo(
    () => clientes.filter((c) => c.health_band === "at_risk").length,
    [clientes],
  );
  const visiveis = useMemo(() => {
    let base = clientes;
    if (seloFiltro) base = base.filter((c) => c.selos.includes(seloFiltro));
    if (!soRisco) return base;
    return [...base]
      .filter((c) => c.health_band === "at_risk")
      .sort((a, b) => a.health - b.health);
  }, [clientes, soRisco, seloFiltro]);

  // Quantos do conjunto carregado são "só e-mail" (sem WhatsApp real). Só faz sentido
  // alertar quando o recorte atual mistura não-contatáveis (alcance != 'sim').
  const semWaCount = useMemo(
    () => clientes.filter((c) => !c.tem_whatsapp).length,
    [clientes],
  );

  // Filtros avançados ativos (os que ficam dentro do painel recolhível).
  const avancadosAtivos =
    [perfil, planType, estado, npsBucket, healthBand, seloFiltro].filter(Boolean).length;

  // Há algum filtro ativo? (controla "limpar filtros" e o texto do vazio). O alcance
  // só conta como filtro quando NÃO está no default 'sim' (contatáveis).
  const algumFiltro =
    !!search || avancadosAtivos > 0 || temWa !== "sim" || soRisco;

  const limparFiltros = useCallback(() => {
    setSearch("");
    setPerfil("");
    setPlanType("");
    setEstado("");
    setNpsBucket("");
    setHealthBand("");
    setTemWa("sim");
    setSeloFiltro("");
    setSoRisco(false);
  }, []);

  const recorteLabel =
    temWa === "sim" ? "contatáveis" : temWa === "nao" ? "winback (só e-mail)" : "no total";
  const colCount = detalhes ? 10 : 5;

  return (
    <div>
      <Reveal className="page-head">
        <div>
          <h1 className="page-title">Clientes</h1>
          <div className="page-sub">
            Por padrão, só quem dá para abordar (WhatsApp válido) — grupos, fixos e
            inválidos ficam de fora. Troque o alcance para ver o winback ou todos.
          </div>
        </div>
        {!loading && (
          <span className="refresh-note">
            {clientes.length} {recorteLabel}
          </span>
        )}
      </Reveal>

      {temWa === "nao" && semWaCount > 0 && (
        <Reveal delay={0.04} className="note">
          <span className="note-ico"><Info size={16} aria-hidden /></span>
          <span>
            Estes <b>{semWaCount}</b> são leads <b>só de e-mail</b> — fora do alcance das
            pesquisas por WhatsApp, mas alvo do win-back por e-mail.
          </span>
        </Reveal>
      )}

      <Reveal delay={0.07} className="toolbar">
        <label className="search">
          <span className="ico"><Search size={15} aria-hidden /></span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome ou WhatsApp…"
          />
        </label>

        {/* Alcance — segmentado: Contatáveis (default) · Winback · Todos */}
        <div
          role="group"
          aria-label="Recorte de alcance"
          className="inline-flex items-center gap-0.5 rounded-[var(--radius-sm)] border border-[var(--charcoal-2)] bg-[var(--ink-800)] p-1"
        >
          {ALCANCE_OPCOES.map((o) => {
            const on = temWa === o.value;
            return (
              <button
                key={o.label}
                type="button"
                onClick={() => setTemWa(o.value)}
                aria-pressed={on}
                title={o.hint}
                className={[
                  "rounded-[calc(var(--radius-sm)-3px)] px-3 py-[7px] text-[13px] font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--indigo)]",
                  on
                    ? "bg-[image:var(--grad-indigo)] text-white shadow-[var(--btn-indigo-shadow)]"
                    : "text-[var(--text-faint)] hover:text-[var(--text)]",
                ].join(" ")}
              >
                {o.label}
              </button>
            );
          })}
        </div>

        {/* Em risco REAL (banda at_risk) — atalho de fila acionável */}
        <button
          type="button"
          className={`risk-chip ${soRisco ? "on" : ""}`}
          onClick={() => setSoRisco((v) => !v)}
          aria-pressed={soRisco}
          title="Mostrar só contas em risco real (at_risk) — pior Health primeiro"
        >
          <AlertTriangle size={15} aria-hidden /> Em risco <span className="risk-n">{emRiscoCount}</span>
        </button>

        {/* Filtros avançados — recolhidos por padrão (densidade) */}
        <button
          type="button"
          onClick={() => setFiltrosAbertos((v) => !v)}
          aria-expanded={filtrosAbertos}
          className={[
            "inline-flex items-center gap-2 rounded-[var(--radius-sm)] border px-3 py-[10px] text-[13.5px] font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--indigo)]",
            filtrosAbertos || avancadosAtivos > 0
              ? "border-[var(--promoter-line)] bg-[var(--promoter-soft)] text-[var(--indigo-light)]"
              : "border-[var(--charcoal-2)] bg-[var(--ink-800)] text-[var(--text-dim)] hover:text-[var(--text)]",
          ].join(" ")}
        >
          <SlidersHorizontal size={15} aria-hidden /> Filtros
          {avancadosAtivos > 0 && <span className="risk-n">{avancadosAtivos}</span>}
        </button>

        {algumFiltro && (
          <Button variant="ghost" size="sm" onClick={limparFiltros}>
            Limpar filtros
          </Button>
        )}
      </Reveal>

      {/* Painel de filtros avançados — só monta quando aberto */}
      {filtrosAbertos && (
        <Reveal className="toolbar" style={{ marginTop: -6 }}>
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
          <select value={seloFiltro} onChange={(e) => setSeloFiltro(e.target.value)} aria-label="Filtrar por selo">
            <option value="">Todos os selos</option>
            {seloOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </Reveal>
      )}

      <div className="count-line">
        {loading ? (
          "Carregando…"
        ) : (
          <>
            <b>{visiveis.length}</b> cliente{visiveis.length === 1 ? "" : "s"}
            {algumFiltro ? " com os filtros atuais" : ` ${recorteLabel}`}
          </>
        )}
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar os clientes ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      <Reveal delay={0.1} className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Saúde</th>
                <th>Assinatura</th>
                <th>Último feedback</th>
                {detalhes && (
                  <>
                    <th>Perfil</th>
                    <th>Plano</th>
                    <th>NPS</th>
                    <th>Renova em</th>
                    <th>Feedbacks</th>
                  </>
                )}
                <th>
                  <button
                    type="button"
                    onClick={() => setDetalhes((v) => !v)}
                    aria-expanded={detalhes}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--indigo-light)] hover:underline"
                  >
                    {detalhes ? "− menos colunas" : "+ mais colunas"}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody aria-busy={loading || undefined}>
              {loading && clientes.length === 0 &&
                Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} cols={colCount} />)}
              {!loading && !err && visiveis.length === 0 && (
                <tr>
                  <td colSpan={colCount}>
                    <div className="empty">
                      <div className="empty-illu">{EMPTY_PEOPLE}</div>
                      <div className="empty-title">
                        {soRisco
                          ? "Nenhuma conta em risco"
                          : algumFiltro
                          ? "Nenhum cliente com esses filtros"
                          : "Nenhum cliente contatável ainda"}
                      </div>
                      <p className="empty-sub">
                        {soRisco
                          ? "Nenhuma conta na banda de risco neste recorte \u{2014} bom trabalho."
                          : algumFiltro
                          ? "Tente afrouxar a busca ou limpar os filtros."
                          : "Quando houver clientes contatáveis, eles aparecem aqui."}
                      </p>
                      {algumFiltro && (
                        <div className="empty-cta">
                          <Button variant="ghost" size="sm" onClick={limparFiltros}>
                            Limpar filtros
                          </Button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
              {(!loading || clientes.length > 0) && visiveis.map((c, i) => (
                <tr
                  key={c.id}
                  className="reveal"
                  style={{ ["--i" as string]: Math.min(i, 12) } as React.CSSProperties}
                >
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
                            <Mail size={12} aria-hidden style={{ display: "inline", verticalAlign: "-2px" }} /> só e-mail
                          </span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td>{healthCell(c.health, c.health_band, c.health_factors)}</td>
                  <td>{estadoBadge(c.estado)}</td>
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
                  {detalhes && (
                    <>
                      <td>{perfilBadge(c.perfil)}</td>
                      <td className="dim">
                        {c.plano || c.plan_type || <span className="faint">—</span>}
                      </td>
                      <td>{npsTag(c.nps_score)}</td>
                      <td>{renovaCell(c.dias_para_renovar)}</td>
                      <td className="dim">{c.total_feedbacks}</td>
                    </>
                  )}
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
      </Reveal>
    </div>
  );
}
