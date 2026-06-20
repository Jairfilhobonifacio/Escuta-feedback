"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Search,
  AlertTriangle,
  Info,
  Mail,
  Plus,
  X,
  SlidersHorizontal,
  MessageCircle,
  PhoneOff,
  CheckCircle2,
} from "lucide-react";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import { Reveal } from "@/components/Motion";
import SeloPopover from "@/components/SeloPopover";
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

/** Canal de contato do cliente — derivado client-side espelhando o validador
    canônico do backend (app/domain/contacts/whatsapp.py):
    - 'whatsapp'   tem celular BR válido (tem_whatsapp === true) → abordável no zap.
    - 'email'      placeholder 'nowa-…' que o sync grava p/ churn SÓ-E-MAIL.
    - 'sem'        vazio / fixo / grupo / inválido → não dá para abordar 1:1. */
type Canal = "whatsapp" | "email" | "sem";

function canalDoCliente(c: Cliente): Canal {
  if (c.tem_whatsapp) return "whatsapp";
  if ((c.whatsapp || "").startsWith("nowa-")) return "email";
  return "sem";
}

/** Selo que o envio 1:1 aplica ao contato (WhatsappSendResult.selos). É o sinal
    "já abordamos" — não há filtro server-side, então conta-se client-side. */
const SELO_CONTATADO = "contatado";

function foiAbordado(c: Cliente): boolean {
  return c.selos.includes(SELO_CONTATADO);
}

/** Badge de canal por linha — bate o olho e sabe como falar com a pessoa.
    WhatsApp em verde (não há token de marca verde; cor inline emerald),
    e-mail e sem-contato discretos nos tokens do tema. */
function canalBadge(canal: Canal) {
  if (canal === "whatsapp") {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[11px] font-semibold leading-none shadow-[var(--edge)]"
        style={{
          color: "#157a4e",
          borderColor: "rgba(16, 160, 96, 0.30)",
          background: "rgba(16, 160, 96, 0.10)",
        }}
        title="Celular válido — abordável por WhatsApp"
      >
        <MessageCircle size={12} strokeWidth={2.2} aria-hidden /> WhatsApp
      </span>
    );
  }
  if (canal === "email") {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-sm border border-[var(--charcoal-2)] bg-[var(--ink-800)] px-2 py-0.5 text-[11px] font-semibold leading-none text-[var(--text-dim)] shadow-[var(--edge)]"
        title="Sem WhatsApp — só e-mail (alvo de win-back por e-mail)"
      >
        <Mail size={12} strokeWidth={2.2} aria-hidden /> Só e-mail
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-sm border border-dashed border-[var(--charcoal-2)] px-2 py-0.5 text-[11px] font-semibold leading-none text-[var(--text-faint)]"
      title="Sem contato abordável (vazio, fixo, grupo ou inválido)"
    >
      <PhoneOff size={12} strokeWidth={2.2} aria-hidden /> Sem contato
    </span>
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
      <td><div className="sk-line" style={{ width: 84, height: 20, borderRadius: 6, margin: 0 }} /></td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div className="sk-line" style={{ width: 70, margin: 0 }} />
          <div className="sk-line sk-sm" style={{ width: 24, margin: 0 }} />
        </div>
      </td>
      <td><div className="sk-line w-50" style={{ margin: 0 }} /></td>
      <td><div className="sk-line w-60" style={{ margin: 0 }} /></td>
      <td><div className="sk-line w-70" style={{ margin: 0 }} /></td>
      {cols > 6 && (
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
    <div className="selos-cell">
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
        <SeloPopover
          open={open}
          onOpenChange={setOpen}
          trigger={({ open: isOpen, toggle }) => (
            <button
              type="button"
              className="selo-add"
              onClick={toggle}
              aria-expanded={isOpen}
              aria-label="Aplicar selo"
            >
              <Plus size={12} strokeWidth={2.2} aria-hidden /> selo
            </button>
          )}
        >
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
        </SeloPopover>
      </div>
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
  // Chip de canal ativo (faixa clicável no topo). '' = sem recorte de canal.
  // 'whatsapp'/'email'/'sem' = canal derivado; 'abordados' = selo 'contatado'.
  // Espelha-se no alcance (temWa) p/ o backend trazer o conjunto certo.
  const [canalChip, setCanalChip] = useState<"" | Canal | "abordados">("");
  // Base COMPLETA (sem o filtro tem_whatsapp) só para os contadores dos chips —
  // assim "Só e-mail (N)"/"Sem contato (N)" têm número certo mesmo no recorte
  // 'Contatáveis'. Carregada em paralelo, respeitando busca + filtros avançados.
  const [base, setBase] = useState<Cliente[]>([]);
  // UI: filtros avançados recolhidos + colunas de detalhe recolhidas (densidade).
  const [filtrosAbertos, setFiltrosAbertos] = useState(false);
  const [detalhes, setDetalhes] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Filtros comuns às duas chamadas (busca + avançados), SEM tem_whatsapp.
      const comum: ClienteFiltro = {
        search: search.trim() || undefined,
        perfil: perfil || undefined,
        plan_type: planType || undefined,
        estado: estado || undefined,
        nps_bucket: npsBucket || undefined,
        health_band: healthBand || undefined,
      };
      // Defensivo: a API antiga pode não devolver `selos`; garante array em runtime
      // (vários pontos fazem c.selos.includes/.map sem checar).
      const norm = (xs: Cliente[]) => xs.map((c) => ({ ...c, selos: c.selos ?? [] }));
      // Lista visível (com o alcance atual) + base completa p/ os contadores dos
      // chips, em paralelo. A base ignora tem_whatsapp de propósito.
      const [lista, baseLista] = await Promise.all([
        clientesApi.list({ ...comum, tem_whatsapp: temWa || undefined }),
        clientesApi.list(comum),
      ]);
      setClientes(norm(lista));
      setBase(norm(baseLista));
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

  // Contadores dos chips de canal — calculados sobre a BASE completa (todo o
  // universo do recorte de busca/avançados), independentes do alcance atual.
  const canalCounts = useMemo(() => {
    let wa = 0,
      email = 0,
      sem = 0,
      abordados = 0;
    for (const c of base) {
      const canal = canalDoCliente(c);
      if (canal === "whatsapp") wa++;
      else if (canal === "email") email++;
      else sem++;
      if (foiAbordado(c)) abordados++;
    }
    return { whatsapp: wa, email, sem, abordados };
  }, [base]);

  // Clique num chip de canal: alterna o recorte e ALINHA o alcance (temWa) para o
  // backend trazer o conjunto certo (WhatsApp→'sim'; e-mail/sem→'nao'; abordados/
  // limpar→'' = todos). O refino fino acontece client-side em `visiveis`.
  const aplicarCanal = useCallback((alvo: Canal | "abordados") => {
    setCanalChip((atual) => {
      const novo = atual === alvo ? "" : alvo;
      setTemWa(novo === "whatsapp" ? "sim" : novo === "email" || novo === "sem" ? "nao" : "");
      return novo;
    });
  }, []);

  const visiveis = useMemo(() => {
    let arr = clientes;
    if (seloFiltro) arr = arr.filter((c) => c.selos.includes(seloFiltro));
    // Recorte do chip de canal (sobre a lista já trazida pelo alcance).
    if (canalChip === "abordados") arr = arr.filter(foiAbordado);
    else if (canalChip) arr = arr.filter((c) => canalDoCliente(c) === canalChip);
    if (!soRisco) return arr;
    return [...arr]
      .filter((c) => c.health_band === "at_risk")
      .sort((a, b) => a.health - b.health);
  }, [clientes, soRisco, seloFiltro, canalChip]);

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
    !!search || avancadosAtivos > 0 || temWa !== "sim" || soRisco || !!canalChip;

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
    setCanalChip("");
  }, []);

  // Trocar o alcance pelo segmentado limpa o chip de canal (evita estado
  // contraditório, ex.: chip "Só e-mail" ligado e alcance "Contatáveis").
  const aplicarAlcance = useCallback((v: TemWhatsappFiltro | "") => {
    setTemWa(v);
    setCanalChip("");
  }, []);

  const recorteLabel =
    temWa === "sim" ? "contatáveis" : temWa === "nao" ? "winback (só e-mail)" : "no total";
  // Colunas visíveis: Cliente, Canal, Saúde, Assinatura, Último feedback (5
  // essenciais) + 5 detalhes quando abertos + a coluna de selos/ações = 6 / 11.
  const colCount = detalhes ? 11 : 6;

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

      {/* Faixa de canais — contadores CLICÁVEIS: filtra a lista na hora e deixa
          claro como falar com cada cliente. Contagem sobre a base completa. */}
      <Reveal delay={0.05} className="flex flex-wrap items-stretch gap-2.5 mt-1 mb-4">
        {([
          {
            key: "whatsapp" as const,
            label: "Com WhatsApp",
            n: canalCounts.whatsapp,
            icon: <MessageCircle size={16} strokeWidth={2.1} aria-hidden />,
            accent: "#10a060",
            hint: "Celular válido — abordável por WhatsApp",
          },
          {
            key: "email" as const,
            label: "Só e-mail",
            n: canalCounts.email,
            icon: <Mail size={16} strokeWidth={2.1} aria-hidden />,
            accent: "var(--indigo)",
            hint: "Sem WhatsApp — leads de reativação por e-mail",
          },
          {
            key: "sem" as const,
            label: "Sem contato",
            n: canalCounts.sem,
            icon: <PhoneOff size={16} strokeWidth={2.1} aria-hidden />,
            accent: "var(--text-faint)",
            hint: "Vazio, fixo, grupo ou inválido — não dá para abordar 1:1",
          },
          {
            key: "abordados" as const,
            label: "Abordados",
            n: canalCounts.abordados,
            icon: <CheckCircle2 size={16} strokeWidth={2.1} aria-hidden />,
            accent: "#10a060",
            hint: "Já abordados (selo 'contatado') — clique para ver",
          },
        ]).map((chip) => {
          const on = canalChip === chip.key;
          return (
            <button
              key={chip.key}
              type="button"
              onClick={() => aplicarCanal(chip.key)}
              aria-pressed={on}
              title={chip.hint}
              className={[
                "group flex min-w-[148px] flex-1 items-center gap-3 rounded-[var(--radius-sm)] border px-3.5 py-3 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--indigo)]",
                on
                  ? "border-[var(--promoter-line)] bg-[var(--promoter-soft)]"
                  : "border-[var(--charcoal-2)] bg-[var(--ink-800)] hover:border-[var(--text-faint)]",
              ].join(" ")}
            >
              <span
                className="grid h-9 w-9 shrink-0 place-items-center rounded-[calc(var(--radius-sm)-3px)]"
                style={{
                  color: chip.accent,
                  background: `color-mix(in srgb, ${chip.accent} 12%, transparent)`,
                }}
              >
                {chip.icon}
              </span>
              <span className="flex flex-col">
                <span className="font-mono text-[19px] font-bold leading-none tabular-nums text-[var(--text)]">
                  {chip.n}
                </span>
                <span className="mt-1 text-[12.5px] font-medium leading-none text-[var(--text-dim)]">
                  {chip.label}
                </span>
              </span>
            </button>
          );
        })}
      </Reveal>

      {temWa === "nao" && !canalChip && semWaCount > 0 && (
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
                onClick={() => aplicarAlcance(o.value)}
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
                <th>Canal</th>
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
                          <span className="cell-person-sub faint">—</span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td>{canalBadge(canalDoCliente(c))}</td>
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
