"use client";

import { useCallback, useEffect, useId, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import { healthCell } from "@/components/HealthCell";
import Modal from "@/components/Modal";
import SeloPopover from "@/components/SeloPopover";
import { Button } from "@/components/ui/button";
import {
  boards as boardsApi,
  feedbacks as feedbacksApi,
  melhorias as melhoriasApi,
  BOARD_CAMPOS_POR_ENTIDADE,
  type Board,
  type BoardCampo,
  type BoardClienteCard,
  type BoardColuna,
  type BoardEntidade,
  type BoardInput,
  type BoardItemFiltro,
  type BoardItems,
  type BoardItemsColuna,
  type BoardMelhoriaCard,
  type BoardTarefaCard,
  type EstadoAssinatura,
  type Feedback,
  type HealthBand,
  type ImprovementEffort,
  type ImprovementStatus,
  type Improvement,
  type NpsBucket,
  type TarefaPriority,
  type TarefaStatus,
  type TemWhatsappFiltro,
} from "@/lib/api";

// ===== visual do Kanban (Trello-like) =======================================
// Só estilo — reusa os tokens de tema (CSS vars) do globals.css via var(--…),
// sem editar globals. Aplicados inline para vencer as regras .board-* legadas
// e dar cara de quadro: trilho horizontal com respiro, lanes definidas com faixa
// de cor por coluna, cabeçalho claro e cards arejados. Não muda lógica/queries,
// nem o drag-and-drop (classes e handlers seguem intactos).

/** Trilho do quadro: lanes lado a lado, gap generoso e scroll horizontal suave. */
const BOARD_TRACK_STYLE: React.CSSProperties = {
  display: "flex",
  flexWrap: "nowrap",
  alignItems: "flex-start",
  gap: 20,
  overflowX: "auto",
  overflowY: "visible",
  paddingBottom: 14,
  scrollBehavior: "smooth",
  scrollSnapType: "x proximity",
};

/** Uma "lista" do quadro: largura fixa (lane), fundo de coluna sutil, cantos
    arredondados e topo achatado p/ acomodar a faixa de cor (borderTop por coluna). */
const BOARD_LANE_STYLE: React.CSSProperties = {
  flex: "0 0 auto",
  width: 312,
  minWidth: 280,
  maxWidth: 340,
  background: "var(--ink)",
  borderRadius: "var(--radius)",
  borderTopLeftRadius: "var(--radius-xs)",
  borderTopRightRadius: "var(--radius-xs)",
  padding: "10px 12px 16px",
  scrollSnapAlign: "start",
};

/** Cabeçalho da lista: nome + contador, com respiro e divisor discreto. */
const BOARD_HEAD_STYLE: React.CSSProperties = {
  padding: "8px 2px 12px",
  marginBottom: 12,
};

/** Pilha de cards: respiro generoso entre cards. */
const BOARD_BODY_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

/** Card do quadro: superfície branca, cantos arredondados, padding confortável
    e sombra suave em repouso (o hover discreto já vem do globals via .board-card:hover). */
const BOARD_CARD_STYLE: React.CSSProperties = {
  padding: "13px 15px",
  borderRadius: "var(--radius-sm)",
  boxShadow: "var(--edge), var(--shadow-sm)",
};

/** Contador da coluna: chip arredondado tingido pela cor da própria lista. */
function countChipStyle(cor: string): React.CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: 22,
    height: 22,
    padding: "0 8px",
    borderRadius: 999,
    fontFamily: "var(--mono)",
    fontSize: 12,
    fontWeight: 600,
    lineHeight: 1,
    color: cor,
    background: "color-mix(in srgb, " + cor + " 13%, transparent)",
    border: "1px solid color-mix(in srgb, " + cor + " 28%, transparent)",
  };
}

// ===== vocabulário ==========================================================

const ENTIDADE_LABEL: Record<BoardEntidade, string> = {
  feedback: "Feedbacks",
  cliente: "Clientes",
  tarefa: "Tarefas",
  melhoria: "Melhorias",
};

const CAMPO_LABEL: Record<BoardCampo, string> = {
  action_status: "Status da ação",
  selo: "Selo de campanha",
  estado: "Estado da assinatura",
  perfil: "Perfil",
  status: "Status",
};

/** Opções de "Agrupar por" no select do modal, por entidade (com texto-guia). */
const CAMPO_OPCOES: Record<BoardEntidade, { valor: BoardCampo; label: string }[]> = {
  feedback: [
    { valor: "action_status", label: "Status da ação (move o feedback)" },
    { valor: "selo", label: "Selo de campanha (aplica selo ao contato)" },
  ],
  cliente: [
    { valor: "selo", label: "Selo de campanha (aplica selo ao cliente)" },
    { valor: "estado", label: "Estado da assinatura (read-only)" },
    { valor: "perfil", label: "Perfil (read-only)" },
  ],
  tarefa: [{ valor: "status", label: "Status da tarefa (move a tarefa)" }],
  melhoria: [{ valor: "status", label: "Status da melhoria (move a melhoria)" }],
};

/** Campos read-only: o board mostra, mas não dá para arrastar (vem da API). */
const CAMPOS_READONLY: ReadonlySet<BoardCampo> = new Set<BoardCampo>(["estado", "perfil"]);

// ===== opções da barra de filtros (espelham os filtros das telas Clientes/Tarefas) ==

/** Estados de assinatura (snapshot partner) — mesmos rótulos da tela Clientes. */
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

const PRIORITY_OPCOES: { value: TarefaPriority; label: string }[] = [
  { value: "urgente", label: "Urgente" },
  { value: "alta", label: "Alta" },
  { value: "normal", label: "Normal" },
  { value: "baixa", label: "Baixa" },
];

const EFFORT_OPCOES: { value: ImprovementEffort; label: string }[] = [
  { value: "P", label: "P (pequeno)" },
  { value: "M", label: "M (médio)" },
  { value: "G", label: "G (grande)" },
  { value: "XG", label: "XG (enorme)" },
];

/** Sugestões de coluna por (entidade, campo) — preenche o formulário. */
const SUGESTOES: Record<BoardEntidade, Partial<Record<BoardCampo, BoardColuna[]>>> = {
  feedback: {
    action_status: [
      { id: "novo", nome: "Novo", valor: "novo", cor: "#6c5ce7" },
      { id: "em_analise", nome: "Em análise", valor: "em_analise", cor: "#6c5ce7" },
      { id: "planejado", nome: "Planejado", valor: "planejado", cor: "#6c5ce7" },
      { id: "resolvido", nome: "Resolvido", valor: "resolvido", cor: "#6c5ce7" },
      { id: "descartado", nome: "Descartado", valor: "descartado", cor: "#6c5ce7" },
    ],
    selo: [
      { id: "contatado", nome: "Contatado", valor: "contatado", cor: "#6c5ce7" },
      { id: "respondeu", nome: "Respondeu", valor: "respondeu", cor: "#22c55e" },
      { id: "cortesia", nome: "Cortesia", valor: "cortesia", cor: "#f5a623" },
      { id: "reativou", nome: "Reativou", valor: "reativou", cor: "#06b6d4" },
    ],
  },
  cliente: {
    selo: [
      { id: "contatado", nome: "Contatado", valor: "contatado", cor: "#6c5ce7" },
      { id: "respondeu", nome: "Respondeu", valor: "respondeu", cor: "#22c55e" },
      { id: "cortesia", nome: "Cortesia", valor: "cortesia", cor: "#f5a623" },
      { id: "reativou", nome: "Reativou", valor: "reativou", cor: "#06b6d4" },
    ],
    estado: [
      { id: "cancelled", nome: "Cancelou", valor: "cancelled", cor: "#ef4444" },
      { id: "paid_without_access", nome: "Pagou sem acesso", valor: "paid_without_access", cor: "#f5a623" },
      { id: "active_paying", nome: "Ativo", valor: "active_paying", cor: "#22c55e" },
    ],
    perfil: [
      { id: "em_risco", nome: "Em risco", valor: "em_risco", cor: "#ef4444" },
      { id: "silencioso", nome: "Silencioso", valor: "silencioso", cor: "#75727f" },
      { id: "promotor", nome: "Promotor", valor: "promotor", cor: "#6c5ce7" },
      { id: "churn", nome: "Churn", valor: "churn", cor: "#e06666" },
    ],
  },
  tarefa: {
    status: [
      { id: "aberta", nome: "Aberta", valor: "aberta", cor: "#6c5ce7" },
      { id: "em_andamento", nome: "Em andamento", valor: "em_andamento", cor: "#06b6d4" },
      { id: "concluida", nome: "Concluída", valor: "concluida", cor: "#22c55e" },
      { id: "adiada", nome: "Adiada", valor: "adiada", cor: "#f5a623" },
    ],
  },
  melhoria: {
    status: [
      { id: "ideia", nome: "Ideia", valor: "ideia", cor: "#75727f" },
      { id: "planejada", nome: "Planejada", valor: "planejada", cor: "#6c5ce7" },
      { id: "em_andamento", nome: "Em andamento", valor: "em_andamento", cor: "#06b6d4" },
      { id: "entregue", nome: "Entregue", valor: "entregue", cor: "#22c55e" },
      { id: "descartada", nome: "Descartada", valor: "descartada", cor: "#e06666" },
    ],
  },
};

/** Primeiro campo válido de uma entidade (default ao trocar o tipo de board). */
function campoDefault(entidade: BoardEntidade): BoardCampo {
  return BOARD_CAMPOS_POR_ENTIDADE[entidade][0];
}

/** Colunas sugeridas para um par (entidade, campo) — fallback p/ a 1ª sugestão. */
function sugestaoColunas(entidade: BoardEntidade, campo: BoardCampo): BoardColuna[] {
  return SUGESTOES[entidade][campo] ?? [];
}

const TYPE_LABEL: Record<string, string> = {
  nps: "NPS",
  churn: "Cancelamento",
  exit: "Exit survey",
  csat: "CSAT",
  elogio: "Elogio",
  sugestao: "Sugestão",
  bug: "Bug",
  outro: "Outro",
};

function typeBadge(type: string) {
  const label = TYPE_LABEL[type] ?? type;
  const cls = type === "churn" || type === "exit" ? "t-exit" : "t-nps";
  return <span className={`badge type ${cls}`}>{label}</span>;
}

/** Faixa da barra de urgência: <30 verde, <60 amarelo, >=60 vermelho. */
function urgencyClass(u: number): string {
  if (u >= 60) return "u-hi";
  if (u >= 30) return "u-mid";
  return "u-lo";
}

/** Mapeia perfil da Bizzu -> classe de badge (mesma lógica da tela Clientes). */
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
  if (!m) return null;
  return <span className={`badge perfil ${m.cls}`}>{m.label.replace(/_/g, " ")}</span>;
}

/** Trecho curto do texto pro card (o detalhe completo abre no contato). */
function snippet(text: string | null, max = 160): string {
  if (!text) return "";
  const t = text.trim();
  return t.length > max ? `${t.slice(0, max).trimEnd()}…` : t;
}

// ===== conexões do card (Fase A: chips) + ações (Fase B: menu) ===============

/** Rótulo curto de status de tarefa pro chip de conexão. */
const TAREFA_STATUS_LABEL: Record<TarefaStatus, string> = {
  aberta: "aberta",
  em_andamento: "andamento",
  concluida: "concluída",
  adiada: "adiada",
};

/** Prioridade de tarefa -> classe de badge (reusa a paleta de perfil) + rótulo. */
const TAREFA_PRIORITY_META: Record<TarefaPriority, { cls: string; label: string }> = {
  baixa: { cls: "p-neutro", label: "baixa" },
  normal: { cls: "p-ativo", label: "normal" },
  alta: { cls: "p-silencioso", label: "alta" },
  urgente: { cls: "p-risco", label: "urgente" },
};

/** Esforço de melhoria -> rótulo legível pro chip. */
const EFFORT_LABEL: Record<string, string> = {
  P: "P (pequeno)",
  M: "M (médio)",
  G: "G (grande)",
  XG: "XG (enorme)",
};

/** Times sugeridos no seletor de "Atribuir" (vocabulário aberto: backend aceita
    qualquer string; estes são só atalhos). */
const TEAM_TAGS = ["produto", "suporte", "comercial", "cs"] as const;

/** Formata uma data ISO para "dd/mm" curto pro card (vazio se null/inválida). */
function dataCurta(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Encurta um título de melhoria/dor pro chip (não polui o card). */
function curto(s: string, max = 22): string {
  const t = s.trim();
  return t.length > max ? `${t.slice(0, max).trimEnd()}…` : t;
}

/** Chips de conexão do card de FEEDBACK (Fase A). Só renderiza o que veio
    preenchido (campos do `_enrich_feedback_cards`). Discreto: reusa .chip/.badge. */
function FeedbackConexoes({ fb }: { fb: Feedback }) {
  const temTarefa = fb.tem_tarefa === true;
  const tarefaStatus = fb.tarefa_status ?? null;
  const melhoria = fb.melhoria_titulo ?? null;
  const dor = fb.dor_label ?? null;
  const conversa = fb.conversa_count ?? 0;
  const team = fb.team_tag;
  const dono = fb.assignee;

  const nada =
    !temTarefa && !melhoria && !dor && conversa <= 0 && !fb.abordado && !team && !dono;
  if (nada) return null;

  return (
    <div className="board-card-meta" style={{ marginTop: 8 }}>
      {temTarefa && (
        <span className="chip" title="Tarefa de CS vinculada">
          <span aria-hidden>{"\u{2713}"}</span>&nbsp;tarefa
          {tarefaStatus ? ` · ${TAREFA_STATUS_LABEL[tarefaStatus]}` : ""}
        </span>
      )}
      {melhoria && (
        <span className="chip selo-mini" title={`Melhoria: ${melhoria}`}>
          <span aria-hidden>{"\u{1F3AF}"}</span>&nbsp;{curto(melhoria)}
        </span>
      )}
      {dor && (
        <span className="chip" title={`Dor: ${dor}`}>
          <span aria-hidden>{"\u{1F525}"}</span>&nbsp;{curto(dor)}
        </span>
      )}
      {conversa > 0 && (
        <span className="chip" title={`${conversa} mensagens na conversa`}>
          <span aria-hidden>{"\u{1F4AC}"}</span>&nbsp;{conversa}
        </span>
      )}
      {fb.abordado && <span className="badge abordado">abordado</span>}
      {team && <span className="chip team">{team}</span>}
      {dono && (
        <span className="chip person" title={`Responsável: ${dono}`}>
          {dono}
        </span>
      )}
    </div>
  );
}

/** Chips de conexão do card de CLIENTE (Fase A). Counts sempre presentes
    (`_cliente_card`); só mostra os > 0 pra não poluir. */
function ClienteConexoes({ cli }: { cli: BoardClienteCard }) {
  const fbs = cli.feedbacks_count;
  const tarefas = cli.tarefas_abertas;
  const conversa = cli.conversa_count;
  if (fbs <= 0 && tarefas <= 0 && conversa <= 0) return null;
  return (
    <div className="board-card-meta" style={{ marginTop: 8 }}>
      {fbs > 0 && (
        <span className="chip" title={`${fbs} feedbacks`}>
          <span aria-hidden>{"\u{1F4DD}"}</span>&nbsp;{fbs}
        </span>
      )}
      {tarefas > 0 && (
        <span className="chip" title={`${tarefas} tarefas abertas`}>
          <span aria-hidden>{"\u{2713}"}</span>&nbsp;{tarefas}
        </span>
      )}
      {conversa > 0 && (
        <span className="chip" title={`${conversa} mensagens na conversa`}>
          <span aria-hidden>{"\u{1F4AC}"}</span>&nbsp;{conversa}
        </span>
      )}
    </div>
  );
}

/** Sub-painel aberto dentro do menu de ações. */
type AcaoMenu = null | "menu" | "melhoria" | "atribuir";

/** Menu de ações do card de FEEDBACK (Fase B). Fica FORA do <Link> do card e
    bloqueia o drag/click do card (stopPropagation). Após cada ação: flash + pede
    recarga ao pai (`onChanged`). Reusa .selo-add / .selo-pop / .field. */
function FeedbackAcoes({
  fb,
  onChanged,
  destacarVincular = false,
}: {
  fb: Feedback;
  /** Pede ao pai que recarregue os items do board (re-enriquece os chips). */
  onChanged: () => void;
  /** Nudge sutil: feedback "planejado" sem melhoria vinculada — evidencia o CTA
      "vincular melhoria" no corpo do card (reusa a MESMA ação `abrirMelhorias`). */
  destacarVincular?: boolean;
}) {
  const [aberto, setAberto] = useState<AcaoMenu>(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<{ ok: boolean; msg: string } | null>(null);
  const [melhoriasList, setMelhoriasList] = useState<Improvement[] | null>(null);
  const [assignee, setAssignee] = useState(fb.assignee ?? "");
  const [team, setTeam] = useState(fb.team_tag ?? "");

  // Flash some sozinho.
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2200);
    return () => clearTimeout(t);
  }, [flash]);

  function fechar() {
    setAberto(null);
  }

  function falhou(e: unknown) {
    setFlash({ ok: false, msg: e instanceof Error ? e.message : String(e) });
  }

  async function criarTarefa() {
    if (!fb.contato_id) {
      setFlash({ ok: false, msg: "Sem contato — não dá para criar tarefa." });
      return;
    }
    setBusy(true);
    try {
      await feedbacksApi.criarTarefa({
        contact_id: fb.contato_id,
        feedback_id: fb.id,
        title: `Abordar feedback: ${snippet(fb.text, 60) || fb.type}`,
      });
      setFlash({ ok: true, msg: "Tarefa criada." });
      fechar();
      onChanged();
    } catch (e) {
      falhou(e);
    } finally {
      setBusy(false);
    }
  }

  async function abrirMelhorias() {
    setAberto("melhoria");
    if (melhoriasList !== null) return;
    try {
      const rows = await melhoriasApi.list();
      setMelhoriasList(rows);
    } catch (e) {
      setMelhoriasList([]);
      falhou(e);
    }
  }

  async function vincular(id: string | null) {
    setBusy(true);
    try {
      await feedbacksApi.vincularMelhoria(fb.id, id);
      setFlash({ ok: true, msg: id ? "Melhoria vinculada." : "Melhoria desvinculada." });
      fechar();
      onChanged();
    } catch (e) {
      falhou(e);
    } finally {
      setBusy(false);
    }
  }

  async function salvarAtribuicao() {
    setBusy(true);
    try {
      await feedbacksApi.atribuir(fb.id, {
        assignee: assignee.trim() || null,
        team_tag: team.trim() || null,
      });
      setFlash({ ok: true, msg: "Atribuição salva." });
      fechar();
      onChanged();
    } catch (e) {
      falhou(e);
    } finally {
      setBusy(false);
    }
  }

  // Impede que clicar nas ações inicie drag ou navegue pelo link do card.
  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  return (
    <>
      {/* Nudge sutil (board action_status, coluna "planejado", sem melhoria):
          chip discreto que abre a MESMA ação de vincular melhoria do menu. */}
      {destacarVincular && (
        <button
          type="button"
          className="board-vincular-cta"
          onClick={(e) => {
            stop(e);
            abrirMelhorias();
          }}
          onMouseDown={stop}
          onDragStart={stop}
          draggable={false}
          disabled={busy}
          title="Conecte este feedback planejado a uma melhoria do roadmap"
        >
          <span aria-hidden>{"\u{1F517}"}</span>&nbsp;vincular melhoria
        </button>
      )}

      {/* Kebab + menu de ações: o painel vive num PORTAL (SeloPopover) ancorado ao
          botão — não é mais cortado/empilhado dentro da coluna. O invólucro fica no
          canto sup. direito do card e bloqueia drag/click do card. */}
      <div
        style={{ position: "absolute", top: 10, right: 10, zIndex: 6 }}
        draggable={false}
        onDragStart={stop}
        onMouseDown={stop}
        onClick={stop}
      >
        <SeloPopover
          open={aberto !== null}
          onOpenChange={(o) => setAberto(o ? "menu" : null)}
          align="right"
          minWidth={aberto === "atribuir" ? 240 : 220}
          trigger={({ open: isOpen, toggle }) => (
            <button
              type="button"
              className="selo-add"
              style={{ padding: "3px 8px", borderRadius: 7, lineHeight: 1 }}
              onClick={toggle}
              aria-expanded={isOpen}
              aria-label="Ações do feedback"
              disabled={busy}
            >
              {"\u{22EF}"}
            </button>
          )}
        >
          {aberto === "menu" && (
            <div className="selo-pop-list" style={{ marginBottom: 0, paddingBottom: 0, borderBottom: "none" }}>
              <button
                type="button"
                className="selo-pop-item"
                onClick={criarTarefa}
                disabled={busy || !fb.contato_id}
                title={fb.contato_id ? "" : "Sem contato vinculado"}
              >
                <span aria-hidden>{"\u{2713}"}</span> Criar tarefa
              </button>
              <button
                type="button"
                className="selo-pop-item"
                onClick={abrirMelhorias}
                disabled={busy}
              >
                <span aria-hidden>{"\u{1F3AF}"}</span> Vincular melhoria
              </button>
              <button
                type="button"
                className="selo-pop-item"
                onClick={() => {
                  setAssignee(fb.assignee ?? "");
                  setTeam(fb.team_tag ?? "");
                  setAberto("atribuir");
                }}
                disabled={busy}
              >
                <span aria-hidden>{"\u{1F465}"}</span> Atribuir
              </button>
              {fb.contato_id && (
                <Link
                  href={`/contatos/${fb.contato_id}`}
                  className="selo-pop-item"
                  draggable={false}
                >
                  <span aria-hidden>{"\u{1F4AC}"}</span> Abrir conversa
                </Link>
              )}
            </div>
          )}

          {aberto === "melhoria" &&
            (melhoriasList === null ? (
              <div className="picker-empty">Carregando melhorias…</div>
            ) : melhoriasList.length === 0 ? (
              <div className="picker-empty">Nenhuma melhoria no roadmap ainda.</div>
            ) : (
              <div className="selo-pop-list" style={{ marginBottom: 0, paddingBottom: 0, borderBottom: "none" }}>
                {fb.improvement_id != null && (
                  <button
                    type="button"
                    className="selo-pop-item"
                    onClick={() => vincular(null)}
                    disabled={busy}
                  >
                    <span aria-hidden>{"\u{2715}"}</span> Desvincular
                    {fb.melhoria_titulo ? ` (${curto(fb.melhoria_titulo, 18)})` : ""}
                  </button>
                )}
                {melhoriasList.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className="selo-pop-item"
                    onClick={() => vincular(m.id)}
                    disabled={busy}
                    aria-current={fb.improvement_id != null && fb.improvement_id === m.id}
                  >
                    <span aria-hidden>{"\u{1F3AF}"}</span> {curto(m.title, 30)}
                  </button>
                ))}
              </div>
            ))}

          {aberto === "atribuir" && (
            <>
              <div className="field" style={{ marginBottom: 10 }}>
                <label>Responsável</label>
                <input
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                  placeholder="slug ou e-mail"
                  disabled={busy}
                />
              </div>
              <div className="field" style={{ marginBottom: 10 }}>
                <label>Time</label>
                <select value={team} onChange={(e) => setTeam(e.target.value)} disabled={busy}>
                  <option value="">sem time</option>
                  {TEAM_TAGS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button type="button" className="btn ghost sm" onClick={fechar} disabled={busy}>
                  Cancelar
                </button>
                <button type="button" className="btn sm" onClick={salvarAtribuicao} disabled={busy}>
                  {busy ? "Salvando…" : "Salvar"}
                </button>
              </div>
            </>
          )}
        </SeloPopover>

        {flash && (
          <div
            className={`flash ${flash.ok ? "ok" : "err"}`}
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              right: 0,
              zIndex: 7,
              minWidth: 200,
              marginBottom: 0,
              whiteSpace: "normal",
            }}
          >
            {flash.msg}
          </div>
        )}
      </div>
    </>
  );
}

// ===== card de um feedback (arrastável) =====================================

function BoardCard({
  fb,
  dragging,
  onDragStart,
  onDragEnd,
  onChanged,
  colunaPlanejado = false,
  compact = false,
}: {
  fb: Feedback;
  dragging: boolean;
  onDragStart: (fb: Feedback) => void;
  onDragEnd: () => void;
  /** Pede recarga dos items do board após uma ação do menu (Fase B). */
  onChanged: () => void;
  /** true só no board de action_status, na coluna cujo valor é "planejado".
      Combinado com improvement_id == null, liga o nudge de vincular melhoria. */
  colunaPlanejado?: boolean;
  /** Board Follow-up (Trello simples do dono): card ENXUTO — só nome + 1 linha do
      texto + 1 chip (o tipo). Sem barra de urgência, sem a pilha de chips de conexão
      e sem o menu de ações. Tira o ruído da visão padrão. */
  compact?: boolean;
}) {
  // Nudge da esteira do roadmap: feedback PLANEJADO ainda sem melhoria vinculada.
  const destacarVincular = !compact && colunaPlanejado && fb.improvement_id == null;
  const inner = compact ? (
    <>
      <div className="board-card-top cell-person">
        <Avatar name={fb.contato_nome} seed={fb.contato_id ?? fb.contato_whatsapp} size={24} />
        <span className="board-card-who">{fb.contato_nome || "sem contato"}</span>
      </div>
      {fb.text ? (
        <p className="board-card-text board-card-text-1">{snippet(fb.text, 90)}</p>
      ) : (
        <p className="board-card-text board-card-text-1 empty-text">sem texto {"—"} só a nota</p>
      )}
      <div className="board-card-meta">{typeBadge(fb.type)}</div>
    </>
  ) : (
    <>
      <div className="board-card-top cell-person">
        <Avatar name={fb.contato_nome} seed={fb.contato_id ?? fb.contato_whatsapp} size={26} />
        <span className="board-card-who">{fb.contato_nome || "sem contato"}</span>
        {typeBadge(fb.type)}
      </div>

      {fb.text ? (
        <p className="board-card-text">{snippet(fb.text)}</p>
      ) : (
        <p className="board-card-text empty-text">sem texto {"—"} só a nota</p>
      )}

      <div
        className={`board-urg ${urgencyClass(fb.urgencia)}`}
        title={`Urgência ${fb.urgencia}/100`}
        aria-hidden
      >
        <span style={{ width: `${Math.min(100, Math.max(0, fb.urgencia))}%` }} />
      </div>

      {fb.selos.length > 0 && (
        <div className="board-card-meta">
          {fb.selos.map((s) => (
            <span key={s} className="chip selo-mini">{s}</span>
          ))}
        </div>
      )}

      {/* Fase A: chips de conexão (tarefa/melhoria/dor/conversa/abordado/dono) */}
      <FeedbackConexoes fb={fb} />
    </>
  );

  return (
    <article
      className={`card board-card ${compact ? "board-card-compact" : ""} ${dragging ? "is-dragging" : ""}`}
      style={{ ...BOARD_CARD_STYLE, position: "relative" }}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", fb.id);
        e.dataTransfer.effectAllowed = "move";
        onDragStart(fb);
      }}
      onDragEnd={onDragEnd}
      aria-label={`Feedback de ${fb.contato_nome || "sem nome"}`}
    >
      {fb.contato_id ? (
        <Link href={`/contatos/${fb.contato_id}`} className="board-card-link" draggable={false}>
          {inner}
        </Link>
      ) : (
        inner
      )}

      {/* Fase B: menu de ações — escondido na visão enxuta (compact). Fora do <Link>,
          não dispara drag/navegação; o kebab fica fixo no topo-direito; o nudge
          `destacarVincular` evidencia o CTA de melhoria quando planejado sem melhoria. */}
      {!compact && (
        <FeedbackAcoes fb={fb} onChanged={onChanged} destacarVincular={destacarVincular} />
      )}
    </article>
  );
}

// ===== card de um cliente (arrastável só quando o campo permite) ============

function ClienteCard({
  cli,
  draggable,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  cli: BoardClienteCard;
  /** false p/ campos read-only (estado/perfil): card não arrasta. */
  draggable: boolean;
  dragging: boolean;
  onDragStart: (cli: BoardClienteCard) => void;
  onDragEnd: () => void;
}) {
  const inner = (
    <>
      <div className="board-card-top cell-person">
        <Avatar name={cli.nome} seed={cli.id} size={26} />
        <span className="board-card-who">{cli.nome || "sem nome"}</span>
        {perfilBadge(cli.perfil)}
      </div>

      <div className="board-cli-contact">
        {cli.tem_whatsapp ? (
          <span className="board-cli-wa mono">{cli.whatsapp}</span>
        ) : (
          <span className="chip board-cli-onlyemail" title="Sem WhatsApp — universo só e-mail">
            só e-mail
          </span>
        )}
      </div>

      <div className="board-cli-health">{healthCell(cli.health, cli.health_band)}</div>

      {cli.selos.length > 0 && (
        <div className="board-card-meta">
          {cli.selos.map((s) => (
            <span key={s} className="chip selo-mini">{s}</span>
          ))}
        </div>
      )}

      {/* Fase A: chips de conexão do cliente (feedbacks/tarefas abertas/conversa) */}
      <ClienteConexoes cli={cli} />
    </>
  );

  return (
    <article
      className={`card board-card board-cli-card ${draggable ? "" : "is-readonly"} ${
        dragging ? "is-dragging" : ""
      }`}
      style={BOARD_CARD_STYLE}
      draggable={draggable}
      onDragStart={
        draggable
          ? (e) => {
              e.dataTransfer.setData("text/plain", cli.id);
              e.dataTransfer.effectAllowed = "move";
              onDragStart(cli);
            }
          : undefined
      }
      onDragEnd={draggable ? onDragEnd : undefined}
      aria-label={`Cliente ${cli.nome || "sem nome"}`}
    >
      <Link href={`/contatos/${cli.id}`} className="board-card-link" draggable={false}>
        {inner}
      </Link>
    </article>
  );
}

// ===== card de uma tarefa (arrastável — drop muda o status) =================

function TarefaCard({
  tarefa,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  tarefa: BoardTarefaCard;
  dragging: boolean;
  onDragStart: (t: BoardTarefaCard) => void;
  onDragEnd: () => void;
}) {
  const prio = TAREFA_PRIORITY_META[tarefa.priority];
  const due = dataCurta(tarefa.due_at);
  const inner = (
    <>
      <div className="board-card-top cell-person">
        <span className="board-card-who">{tarefa.titulo || "sem título"}</span>
        {prio && <span className={`badge perfil ${prio.cls}`}>{prio.label}</span>}
      </div>

      <div className="board-card-meta" style={{ marginTop: 8 }}>
        {tarefa.contato_nome && (
          <span className="chip person" title={`Contato: ${tarefa.contato_nome}`}>
            <span aria-hidden>{"\u{1F464}"}</span>&nbsp;{curto(tarefa.contato_nome, 18)}
          </span>
        )}
        {tarefa.owner && (
          <span className="chip person" title={`Responsável: ${tarefa.owner}`}>
            {curto(tarefa.owner, 16)}
          </span>
        )}
        {due && (
          <span className="chip" title={`Prazo: ${tarefa.due_at}`}>
            <span aria-hidden>{"\u{1F4C5}"}</span>&nbsp;{due}
          </span>
        )}
      </div>

      {(tarefa.feedback_id || tarefa.feedback_preview) && (
        <div className="board-card-meta" style={{ marginTop: 6 }}>
          <span
            className="chip selo-mini"
            title={tarefa.feedback_preview ?? "Feedback vinculado"}
          >
            <span aria-hidden>{"\u{1F4DD}"}</span>&nbsp;
            {tarefa.feedback_preview ? curto(tarefa.feedback_preview, 28) : "feedback"}
          </span>
        </div>
      )}
    </>
  );

  return (
    <article
      className={`card board-card ${dragging ? "is-dragging" : ""}`}
      style={BOARD_CARD_STYLE}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", tarefa.id);
        e.dataTransfer.effectAllowed = "move";
        onDragStart(tarefa);
      }}
      onDragEnd={onDragEnd}
      aria-label={`Tarefa ${tarefa.titulo || "sem título"}`}
    >
      {tarefa.contato_id ? (
        <Link href={`/contatos/${tarefa.contato_id}`} className="board-card-link" draggable={false}>
          {inner}
        </Link>
      ) : (
        inner
      )}
    </article>
  );
}

// ===== card de uma melhoria (arrastável — drop muda o status) ===============

function MelhoriaCard({
  melhoria,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  melhoria: BoardMelhoriaCard;
  dragging: boolean;
  onDragStart: (m: BoardMelhoriaCard) => void;
  onDragEnd: () => void;
}) {
  const pediram = melhoria.feedback_count;
  const effort = melhoria.effort ? EFFORT_LABEL[melhoria.effort] ?? melhoria.effort : null;
  const target = dataCurta(melhoria.target_date);
  return (
    <article
      className={`card board-card ${dragging ? "is-dragging" : ""}`}
      style={BOARD_CARD_STYLE}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", melhoria.id);
        e.dataTransfer.effectAllowed = "move";
        onDragStart(melhoria);
      }}
      onDragEnd={onDragEnd}
      aria-label={`Melhoria ${melhoria.titulo || "sem título"}`}
    >
      <div className="board-card-top cell-person">
        <span className="board-card-who">
          <span aria-hidden>{"\u{1F3AF}"}</span>&nbsp;{melhoria.titulo || "sem título"}
        </span>
      </div>

      <div className="board-card-meta" style={{ marginTop: 8 }}>
        {pediram > 0 && (
          <span className="chip" title={`${pediram} feedbacks pediram esta melhoria`}>
            <span aria-hidden>{"\u{1F465}"}</span>&nbsp;{pediram} pediram
          </span>
        )}
        {effort && (
          <span className="chip" title={`Esforço: ${effort}`}>
            <span aria-hidden>{"\u{1F4AA}"}</span>&nbsp;{effort}
          </span>
        )}
        {target && (
          <span className="chip" title={`Data-alvo: ${melhoria.target_date}`}>
            <span aria-hidden>{"\u{1F4C5}"}</span>&nbsp;{target}
          </span>
        )}
      </div>
    </article>
  );
}

// ===== modal de criar / editar board ========================================

function BoardFormModal({
  board,
  onClose,
  onSaved,
}: {
  /** null = criar; senão edita (entidade e campo são imutáveis na edição). */
  board: Board | null;
  onClose: () => void;
  onSaved: (b: Board) => void;
}) {
  const titleId = useId();
  const editing = board !== null;
  const [nome, setNome] = useState(board?.nome ?? "");
  const [entidade, setEntidade] = useState<BoardEntidade>(board?.entidade ?? "feedback");
  const [campo, setCampo] = useState<BoardCampo>(board?.campo ?? "action_status");
  const [colunas, setColunas] = useState<BoardColuna[]>(
    board?.colunas?.length ? board.colunas : sugestaoColunas("feedback", "action_status"),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ao trocar o TIPO de board (só na criação): reseta o campo p/ o 1º válido da
  // nova entidade e recarrega as colunas sugeridas coerentes.
  function onEntidadeChange(next: BoardEntidade) {
    setEntidade(next);
    const novoCampo = campoDefault(next);
    setCampo(novoCampo);
    setColunas(sugestaoColunas(next, novoCampo));
  }

  // Ao trocar o campo (só na criação): recarrega as colunas sugeridas.
  function onCampoChange(next: BoardCampo) {
    setCampo(next);
    setColunas(sugestaoColunas(entidade, next));
  }

  function setCol(i: number, patch: Partial<BoardColuna>) {
    setColunas((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }
  function addCol() {
    setColunas((prev) => [...prev, { id: "", nome: "", valor: "", cor: "#6c5ce7" }]);
  }
  function removeCol(i: number) {
    setColunas((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const nomeT = nome.trim();
    if (!nomeT) {
      setError("Dê um nome ao board.");
      return;
    }
    const cols = colunas
      .map((c) => ({
        id: (c.id || c.valor).trim(),
        nome: (c.nome || c.valor).trim(),
        valor: c.valor.trim(),
        cor: c.cor,
      }))
      .filter((c) => c.valor);
    if (cols.length === 0) {
      setError("Adicione ao menos uma coluna com valor.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      let out: Board;
      if (editing) {
        out = await boardsApi.patch(board!.id, { nome: nomeT, colunas: cols });
      } else {
        const body: BoardInput = { nome: nomeT, entidade, campo, colunas: cols };
        out = await boardsApi.create(body);
      }
      onSaved(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  const valorPlaceholder =
    campo === "action_status"
      ? "valor (ex.: novo)"
      : campo === "estado"
        ? "estado (ex.: cancelled)"
        : campo === "perfil"
          ? "perfil (ex.: em_risco)"
          : "selo (ex.: contatado)";

  return (
    <Modal title={editing ? "Editar board" : "Novo board"} onClose={onClose} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="field">
            <label htmlFor={`${titleId}-nome`}>Nome do board</label>
            <input
              id={`${titleId}-nome`}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="ex.: Triagem, Win-back (clientes)"
            />
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-entidade`}>Tipo de board</label>
            <select
              id={`${titleId}-entidade`}
              value={entidade}
              onChange={(e) => onEntidadeChange(e.target.value as BoardEntidade)}
              disabled={editing}
            >
              <option value="feedback">Feedbacks (cards de feedback)</option>
              <option value="cliente">Clientes (cards de cliente)</option>
              <option value="tarefa">Tarefas (cards de tarefa)</option>
              <option value="melhoria">Melhorias (cards de melhoria)</option>
            </select>
            {editing && (
              <span className="dim" style={{ fontSize: 12 }}>
                O tipo de board não muda depois de criado.
              </span>
            )}
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-campo`}>Agrupar por</label>
            <select
              id={`${titleId}-campo`}
              value={campo}
              onChange={(e) => onCampoChange(e.target.value as BoardCampo)}
              disabled={editing}
            >
              {CAMPO_OPCOES[entidade].map((o) => (
                <option key={o.valor} value={o.valor}>
                  {o.label}
                </option>
              ))}
            </select>
            {editing && (
              <span className="dim" style={{ fontSize: 12 }}>
                O campo de agrupamento não muda depois de criado.
              </span>
            )}
            {!editing && entidade === "cliente" && CAMPOS_READONLY.has(campo) && (
              <span className="dim" style={{ fontSize: 12 }}>
                Estado e perfil vêm da API de Clientes — o board só visualiza (sem arrastar).
              </span>
            )}
          </div>

          <div className="field">
            <label>Colunas</label>
            <div className="board-col-editor">
              {colunas.map((c, i) => (
                <div className="board-col-row" key={i}>
                  <input
                    type="color"
                    value={c.cor || "#6c5ce7"}
                    onChange={(e) => setCol(i, { cor: e.target.value })}
                    aria-label="Cor da coluna"
                    className="selo-color"
                  />
                  <input
                    value={c.nome}
                    onChange={(e) => setCol(i, { nome: e.target.value })}
                    placeholder="Nome (rótulo)"
                    aria-label="Nome da coluna"
                  />
                  <input
                    value={c.valor}
                    onChange={(e) => setCol(i, { valor: e.target.value })}
                    placeholder={valorPlaceholder}
                    aria-label="Valor da coluna"
                    className="mono"
                  />
                  <button
                    type="button"
                    className="icon-btn danger"
                    onClick={() => removeCol(i)}
                    title="Remover coluna"
                    aria-label="Remover coluna"
                  >
                    {"\u{1F5D1}\u{FE0F}"}
                  </button>
                </div>
              ))}
              <Button variant="ghost" size="sm" onClick={addCol}>
                <span aria-hidden>{"\u{FF0B}"}</span> Adicionar coluna
              </Button>
            </div>
          </div>

          {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
        </div>
        <div className="modal-foot">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Salvando…" : editing ? "Salvar board" : "Criar board"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ===== modal "+ feedback" numa coluna (board Follow-up) =====================

/** Tipos de feedback oferecidos no "+ feedback" do board simples (subconjunto enxuto
    do vocabulário do backend — FEEDBACK_TYPES). "Outro" é o default neutro. */
const NOVO_CARD_TIPOS: { value: string; label: string }[] = [
  { value: "outro", label: "Outro" },
  { value: "nps", label: "NPS" },
  { value: "elogio", label: "Elogio" },
  { value: "sugestao", label: "Sugestão" },
  { value: "bug", label: "Problema / bug" },
  { value: "churn", label: "Cancelamento" },
];

/** Cria um feedback DENTRO de uma coluna do board Follow-up. Reusa o endpoint que já
    existe (POST /api/feedbacks via `feedbacksApi.create`) e, em seguida, aplica o selo
    da coluna ao contato (POST /api/feedbacks/{id}/board-move via `boardsApi.move`) — o
    mesmo fluxo manual de selo do board. Contato fora da base via WhatsApp + nome. */
function NovoCardModal({
  coluna,
  onClose,
  onCreated,
}: {
  coluna: BoardItemsColuna;
  onClose: () => void;
  onCreated: () => void;
}) {
  const titleId = useId();
  const [nome, setNome] = useState("");
  const [whats, setWhats] = useState("");
  const [tipo, setTipo] = useState("outro");
  const [texto, setTexto] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!whats.trim()) {
      setError("Informe o WhatsApp do contato.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await feedbacksApi.create({
        type: tipo,
        text: texto.trim() || null,
        contato_whatsapp: whats.trim(),
        contato_nome: nome.trim() || undefined,
        source: "manual",
      });
      // Aplica o selo da coluna ao contato (mesmo fluxo do drag-and-drop de selo).
      await boardsApi.move(created.id, { campo: "selo", valor: coluna.valor });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <Modal title={`Novo feedback · ${coluna.nome}`} onClose={onClose} labelledById={titleId}>
      <form onSubmit={save}>
        <div className="modal-body">
          <div className="form-row-2">
            <div className="field">
              <label htmlFor={`${titleId}-nome`}>Nome do cliente</label>
              <input
                id={`${titleId}-nome`}
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="ex.: Maria Souza"
              />
            </div>
            <div className="field">
              <label htmlFor={`${titleId}-whats`}>WhatsApp</label>
              <input
                id={`${titleId}-whats`}
                value={whats}
                onChange={(e) => setWhats(e.target.value)}
                placeholder="ex.: 5577999450083"
                inputMode="tel"
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-tipo`}>Tipo</label>
            <select id={`${titleId}-tipo`} value={tipo} onChange={(e) => setTipo(e.target.value)}>
              {NOVO_CARD_TIPOS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor={`${titleId}-texto`}>O que o cliente disse</label>
            <textarea
              id={`${titleId}-texto`}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="opcional…"
            />
          </div>

          {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
        </div>
        <div className="modal-foot">
          <Button variant="ghost" type="button" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Criando…" : "Criar feedback"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ===== página ===============================================================

export default function BoardPage() {
  const [boardList, setBoardList] = useState<Board[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [items, setItems] = useState<BoardItems | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // drag-and-drop
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overColumn, setOverColumn] = useState<string | null>(null);

  // modais
  const [editingBoard, setEditingBoard] = useState<Board | null>(null);
  const [creating, setCreating] = useState(false);

  // Filtros dos items (Fase E) — viram query string em GET /boards/{id}/items. Cada um
  // só vale para a(s) entidade(s) a que pertence (o backend ignora os demais sem erro);
  // a barra abaixo só renderiza os controles que fazem sentido para a entidade do board.
  const [fEstado, setFEstado] = useState<EstadoAssinatura | "">("");
  const [fPlanType, setFPlanType] = useState("");
  const [fPerfil, setFPerfil] = useState("");
  const [fTemWa, setFTemWa] = useState<TemWhatsappFiltro | "">("");
  const [fNps, setFNps] = useState<NpsBucket | "">("");
  const [fTeam, setFTeam] = useState("");
  const [fAssignee, setFAssignee] = useState("");
  const [fAbordado, setFAbordado] = useState<"" | "sim" | "nao">("");
  const [fHealth, setFHealth] = useState<HealthBand | "">("");
  const [fOwner, setFOwner] = useState("");
  const [fPriority, setFPriority] = useState<TarefaPriority | "">("");
  const [fEffort, setFEffort] = useState<ImprovementEffort | "">("");

  // Board Follow-up (o "Trello simples" do dono, default-followup): visão ENXUTA —
  // cards mínimos, barra de filtros recolhida (só busca) e "+ feedback" por coluna.
  const [busca, setBusca] = useState("");
  // Qual coluna está com o modal "+ feedback" aberto (null = nenhum).
  const [novoCardCol, setNovoCardCol] = useState<BoardItemsColuna | null>(null);

  const selected = boardList.find((b) => b.id === selectedId) ?? null;
  const isCliente = selected?.entidade === "cliente";
  const isTarefa = selected?.entidade === "tarefa";
  const isMelhoria = selected?.entidade === "melhoria";
  const isReadonly = selected ? CAMPOS_READONLY.has(selected.campo) : false;
  const isFeedback = !isCliente && !isTarefa && !isMelhoria;
  // O board Follow-up é de feedback+selo; identificado pelo id default (e tolerante a
  // qualquer board que o dono renomeie, contanto que o id seja o do default).
  const isFollowup = selected?.id === "default-followup";

  // Filtros "por tipo de cliente" (via o contato) valem para feedback e cliente.
  const mostraContatoFiltros = isFeedback || isCliente;

  // Monta o BoardItemFiltro a partir do estado (só os campos preenchidos). Reusa o mesmo
  // vocabulário do backend; campos inaplicáveis à entidade são ignorados lá sem erro.
  const buildFiltro = useCallback(
    (): BoardItemFiltro => ({
      estado: fEstado || undefined,
      plan_type: fPlanType.trim() || undefined,
      perfil: fPerfil.trim() || undefined,
      tem_whatsapp: fTemWa || undefined,
      nps_bucket: fNps || undefined,
      team_tag: fTeam.trim() || undefined,
      assignee: fAssignee.trim() || undefined,
      abordado: fAbordado === "" ? undefined : fAbordado === "sim",
      health_band: fHealth || undefined,
      owner: fOwner.trim() || undefined,
      priority: fPriority || undefined,
      effort: fEffort || undefined,
    }),
    [fEstado, fPlanType, fPerfil, fTemWa, fNps, fTeam, fAssignee, fAbordado, fHealth, fOwner, fPriority, fEffort],
  );

  const algumFiltro =
    !!fEstado || !!fPlanType || !!fPerfil || !!fTemWa || !!fNps || !!fTeam ||
    !!fAssignee || !!fAbordado || !!fHealth || !!fOwner || !!fPriority || !!fEffort;

  const limparFiltros = useCallback(() => {
    setFEstado("");
    setFPlanType("");
    setFPerfil("");
    setFTemWa("");
    setFNps("");
    setFTeam("");
    setFAssignee("");
    setFAbordado("");
    setFHealth("");
    setFOwner("");
    setFPriority("");
    setFEffort("");
  }, []);

  // Trocar de board e zerar os filtros no MESMO commit (batcheados antes do
  // paint). O vocabulário de filtro muda com a entidade, e fazer os dois juntos
  // garante que o efeito de recarga rode já com os filtros limpos — 1 só fetch,
  // sem vazar o recorte do board anterior.
  const selecionarBoard = useCallback(
    (id: string) => {
      // Ler o board atual e setar o novo + limpar filtros no mesmo commit, sem
      // efeitos colaterais dentro do updater (mantém o updater puro).
      setSelectedId((cur) => {
        if (cur !== id) limparFiltros();
        return id;
      });
    },
    [limparFiltros],
  );

  // Carrega a lista de boards (mantém a seleção quando possível). Se a seleção
  // mudar (board sumiu / 1ª carga), zera os filtros junto — mesmo commit.
  const loadBoards = useCallback(async () => {
    try {
      const rows = await boardsApi.list();
      setBoardList(rows);
      setSelectedId((cur) => {
        const next = cur && rows.some((b) => b.id === cur) ? cur : rows[0]?.id ?? "";
        if (cur !== next) limparFiltros();
        return next;
      });
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [limparFiltros]);

  useEffect(() => {
    loadBoards();
  }, [loadBoards]);

  // Carrega os cards do board selecionado, já com os filtros ativos (query string).
  // `filtro` permite forçar um recorte específico (ex.: `{}` logo após criar/salvar
  // um board, quando os filtros acabaram de ser limpos mas o estado ainda não
  // propagou) — sem isso, usa os filtros ativos via `buildFiltro()`.
  const loadItems = useCallback(async (id: string, filtro?: BoardItemFiltro) => {
    if (!id) {
      setItems(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await boardsApi.items(id, filtro ?? buildFiltro());
      setItems(data);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [buildFiltro]);

  // Recarrega quando muda o board OU qualquer filtro (loadItems depende de buildFiltro).
  // A troca de board já zera os filtros de forma SÍNCRONA (selecionarBoard /
  // loadBoards / onSaved), no mesmo commit do setSelectedId, então quando este
  // efeito roda os filtros já estão limpos — 1 único fetch, sem recorte do board
  // anterior. Trocar um filtro manualmente segue recarregando normalmente.
  useEffect(() => {
    loadItems(selectedId);
  }, [selectedId, loadItems]);

  /** Move otimista de FEEDBACK por drag-and-drop: aplica já, reverte se a API
      falhar. Opera pela IDENTIDADE da coluna (`col.id`). */
  const moveFeedbackByDrop = useCallback(
    async (feedbackId: string, toColId: string) => {
      if (!items || !selected) return;
      const toCol = items.colunas.find((col) => col.id === toColId);
      if (!toCol) return;
      const toValor = toCol.valor;
      // localiza o card e sua coluna de origem (pela identidade da coluna)
      let card: Feedback | undefined;
      let fromColId: string | undefined;
      for (const col of items.colunas) {
        const hit = (col.items as Feedback[]).find((it) => it.id === feedbackId);
        if (hit) {
          card = hit;
          fromColId = col.id;
          break;
        }
      }
      if (!card) return;

      const campo = selected.campo;
      // No-op: para selo, decide pelo ESTADO do contato (já tem o selo destino?);
      // para action_status, no-op por coluna de origem == destino.
      if (campo === "selo") {
        if (card.selos.includes(toValor)) return;
      } else if (fromColId === toColId) {
        return;
      }

      // 1) otimista
      setItems((prev) => {
        if (!prev) return prev;
        const colunas = prev.colunas.map((col) => {
          const colItems = col.items as Feedback[];
          if (campo === "action_status" && col.id === fromColId) {
            return {
              ...col,
              count: Math.max(0, col.count - 1),
              items: colItems.filter((it) => it.id !== feedbackId),
            };
          }
          if (col.id === toColId && !colItems.some((it) => it.id === feedbackId)) {
            const moved: Feedback = {
              ...card!,
              selos:
                campo === "selo" && !card!.selos.includes(toValor)
                  ? [...card!.selos, toValor]
                  : card!.selos,
            };
            return { ...col, count: col.count + 1, items: [moved, ...colItems] };
          }
          return col;
        });
        return { ...prev, colunas };
      });

      try {
        await boardsApi.move(feedbackId, { campo, valor: toValor });
        setErr(null);
        await loadItems(selected.id);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
        await loadItems(selected.id); // reverte ao estado canônico
      }
    },
    [items, selected, loadItems],
  );

  /** Move otimista de CLIENTE por drag-and-drop. Só para campo='selo' (estado e
      perfil são read-only — o card nem arrasta). Aplica o selo via moveContato. */
  const moveClienteByDrop = useCallback(
    async (contatoId: string, toColId: string) => {
      if (!items || !selected || selected.campo !== "selo") return;
      const toCol = items.colunas.find((col) => col.id === toColId);
      if (!toCol) return;
      const toValor = toCol.valor;

      let card: BoardClienteCard | undefined;
      for (const col of items.colunas) {
        const hit = (col.items as BoardClienteCard[]).find((it) => it.id === contatoId);
        if (hit) {
          card = hit;
          break;
        }
      }
      if (!card) return;
      // No-op: o cliente já tem o selo da coluna destino (aparece em N colunas).
      if (card.selos.includes(toValor)) return;

      // 1) otimista: acrescenta o card na coluna destino com o selo aplicado.
      setItems((prev) => {
        if (!prev) return prev;
        const colunas = prev.colunas.map((col) => {
          const colItems = col.items as BoardClienteCard[];
          if (col.id === toColId && !colItems.some((it) => it.id === contatoId)) {
            const moved: BoardClienteCard = { ...card!, selos: [...card!.selos, toValor] };
            return { ...col, count: col.count + 1, items: [moved, ...colItems] };
          }
          return col;
        });
        return { ...prev, colunas };
      });

      try {
        await boardsApi.moveContato(contatoId, { campo: "selo", valor: toValor });
        setErr(null);
        await loadItems(selected.id);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
        await loadItems(selected.id); // reverte ao estado canônico
      }
    },
    [items, selected, loadItems],
  );

  /** Move otimista de TAREFA por drag-and-drop: troca CsTask.status para o valor da
      coluna destino. Single-membership (sai da origem, entra no destino), igual ao
      action_status do feedback. Reverte e recarrega no erro. */
  const moveTarefaByDrop = useCallback(
    async (tarefaId: string, toColId: string) => {
      if (!items || !selected) return;
      const toCol = items.colunas.find((col) => col.id === toColId);
      if (!toCol) return;
      const toValor = toCol.valor as TarefaStatus;

      let card: BoardTarefaCard | undefined;
      let fromColId: string | undefined;
      for (const col of items.colunas) {
        const hit = (col.items as BoardTarefaCard[]).find((it) => it.id === tarefaId);
        if (hit) {
          card = hit;
          fromColId = col.id;
          break;
        }
      }
      if (!card || fromColId === toColId) return; // no-op: já está na coluna

      // 1) otimista: remove da origem, acrescenta na destino com o novo status.
      setItems((prev) => {
        if (!prev) return prev;
        const colunas = prev.colunas.map((col) => {
          const colItems = col.items as BoardTarefaCard[];
          if (col.id === fromColId) {
            return {
              ...col,
              count: Math.max(0, col.count - 1),
              items: colItems.filter((it) => it.id !== tarefaId),
            };
          }
          if (col.id === toColId && !colItems.some((it) => it.id === tarefaId)) {
            const moved: BoardTarefaCard = { ...card!, status: toValor };
            return { ...col, count: col.count + 1, items: [moved, ...colItems] };
          }
          return col;
        });
        return { ...prev, colunas };
      });

      try {
        await boardsApi.moveTarefa(tarefaId, toValor);
        setErr(null);
        await loadItems(selected.id);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
        await loadItems(selected.id); // reverte ao estado canônico
      }
    },
    [items, selected, loadItems],
  );

  /** Move otimista de MELHORIA por drag-and-drop: troca Improvement.status para o
      valor da coluna destino. Single-membership, igual à tarefa. Reverte no erro. */
  const moveMelhoriaByDrop = useCallback(
    async (melhoriaId: string, toColId: string) => {
      if (!items || !selected) return;
      const toCol = items.colunas.find((col) => col.id === toColId);
      if (!toCol) return;
      const toValor = toCol.valor as ImprovementStatus;

      let card: BoardMelhoriaCard | undefined;
      let fromColId: string | undefined;
      for (const col of items.colunas) {
        const hit = (col.items as BoardMelhoriaCard[]).find((it) => it.id === melhoriaId);
        if (hit) {
          card = hit;
          fromColId = col.id;
          break;
        }
      }
      if (!card || fromColId === toColId) return; // no-op: já está na coluna

      // 1) otimista: remove da origem, acrescenta na destino com o novo status.
      setItems((prev) => {
        if (!prev) return prev;
        const colunas = prev.colunas.map((col) => {
          const colItems = col.items as BoardMelhoriaCard[];
          if (col.id === fromColId) {
            return {
              ...col,
              count: Math.max(0, col.count - 1),
              items: colItems.filter((it) => it.id !== melhoriaId),
            };
          }
          if (col.id === toColId && !colItems.some((it) => it.id === melhoriaId)) {
            const moved: BoardMelhoriaCard = { ...card!, status: toValor };
            return { ...col, count: col.count + 1, items: [moved, ...colItems] };
          }
          return col;
        });
        return { ...prev, colunas };
      });

      try {
        await boardsApi.moveMelhoria(melhoriaId, toValor);
        setErr(null);
        await loadItems(selected.id);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
        await loadItems(selected.id); // reverte ao estado canônico
      }
    },
    [items, selected, loadItems],
  );

  function onColumnDrop(e: React.DragEvent, colId: string) {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain") || draggingId;
    setOverColumn(null);
    setDraggingId(null);
    if (!id || !selected) return;
    // Campos read-only não recebem drop (o card nem arrasta, mas defende aqui também).
    if (isReadonly) return;
    if (isCliente) {
      void moveClienteByDrop(id, colId);
    } else if (isTarefa) {
      void moveTarefaByDrop(id, colId);
    } else if (isMelhoria) {
      void moveMelhoriaByDrop(id, colId);
    } else {
      void moveFeedbackByDrop(id, colId);
    }
  }

  async function onDeleteBoard() {
    if (!selected) return;
    if (!window.confirm(`Excluir o board "${selected.nome}"?`)) return;
    try {
      await boardsApi.remove(selected.id);
      await loadBoards();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  const columns: BoardItemsColuna[] = items?.colunas ?? [];
  const total = columns.reduce((sum, c) => sum + c.count, 0);
  // Colunas read-only nunca devem virar drop-target.
  const dropEnabled = !isReadonly;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Board</h1>
          <div className="page-sub">
            {isFollowup
              ? "Acompanhamento dos clientes — arraste o card entre Contatados, Respondidos e Não responderam."
              : "Kanban dinâmico — arraste para mover entre as colunas"}
          </div>
        </div>
        <div className="page-head-actions">
          {!loading && items && (
            <span className="refresh-note">
              {total}{" "}
              {isCliente
                ? "no board (clientes)"
                : isTarefa
                  ? "no board (tarefas)"
                  : isMelhoria
                    ? "no board (melhorias)"
                    : "no board"}
            </span>
          )}
        </div>
      </div>

      {/* Seletor de board + CRUD */}
      <div className="toolbar board-toolbar">
        <select
          value={selectedId}
          onChange={(e) => selecionarBoard(e.target.value)}
          aria-label="Escolher board"
        >
          {boardList.length === 0 && <option value="">Sem boards</option>}
          {boardList.map((b) => (
            <option key={b.id} value={b.id}>
              {b.nome} {"·"} {ENTIDADE_LABEL[b.entidade]} {"·"} {CAMPO_LABEL[b.campo]}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={() => setCreating(true)}>
          <span aria-hidden>{"\u{FF0B}"}</span> Novo board
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setEditingBoard(selected)}
          disabled={!selected}
        >
          Editar
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDeleteBoard}
          disabled={!selected}
        >
          Excluir
        </Button>
      </div>

      {/* Board Follow-up: barra recolhida — só uma BUSCA (filtra os cards visíveis por
          nome/texto no cliente, sem a barra pesada de filtros). */}
      {selected && isFollowup && (
        <div className="toolbar board-busca">
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por nome ou texto…"
            aria-label="Buscar cards"
            className="board-busca-input"
          />
          {busca && (
            <Button variant="ghost" size="sm" onClick={() => setBusca("")}>
              Limpar
            </Button>
          )}
        </div>
      )}

      {/* Barra de filtros dos items (Fase E): só os controles que valem para a entidade
          do board selecionado. Aplicados ANTES do agrupamento no backend, então items E
          counts de cada coluna refletem o filtro. Recolhida no board Follow-up. */}
      {selected && !isFollowup && (
        <div className="toolbar board-filtros">
          {mostraContatoFiltros && (
            <>
              <select
                value={fEstado}
                onChange={(e) => setFEstado(e.target.value as EstadoAssinatura | "")}
                aria-label="Filtrar por estado da assinatura"
              >
                <option value="">Toda assinatura</option>
                {ESTADO_OPCOES.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <input
                value={fPerfil}
                onChange={(e) => setFPerfil(e.target.value)}
                placeholder="Perfil (ex.: em_risco)"
                aria-label="Filtrar por perfil"
                className="board-filtro-input"
              />
              <input
                value={fPlanType}
                onChange={(e) => setFPlanType(e.target.value)}
                placeholder="Plano (ex.: anual)"
                aria-label="Filtrar por plano"
                className="board-filtro-input"
              />
              <select
                value={fNps}
                onChange={(e) => setFNps(e.target.value as NpsBucket | "")}
                aria-label="Filtrar por faixa de NPS"
              >
                <option value="">Todo NPS</option>
                {NPS_OPCOES.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <select
                value={fTemWa}
                onChange={(e) => setFTemWa(e.target.value as TemWhatsappFiltro | "")}
                aria-label="Filtrar por alcance no WhatsApp"
              >
                <option value="">Todo alcance</option>
                <option value="sim">Com WhatsApp</option>
                <option value="nao">Sem WhatsApp (só e-mail)</option>
              </select>
            </>
          )}

          {isFeedback && (
            <>
              <input
                value={fTeam}
                onChange={(e) => setFTeam(e.target.value)}
                placeholder="Time (ex.: produto)"
                aria-label="Filtrar por time"
                className="board-filtro-input"
              />
              <input
                value={fAssignee}
                onChange={(e) => setFAssignee(e.target.value)}
                placeholder="Responsável"
                aria-label="Filtrar por responsável"
                className="board-filtro-input"
              />
              <select
                value={fAbordado}
                onChange={(e) => setFAbordado(e.target.value as "" | "sim" | "nao")}
                aria-label="Filtrar por abordado"
              >
                <option value="">Abordado: todos</option>
                <option value="sim">Já abordados</option>
                <option value="nao">Não abordados</option>
              </select>
            </>
          )}

          {isCliente && (
            <select
              value={fHealth}
              onChange={(e) => setFHealth(e.target.value as HealthBand | "")}
              aria-label="Filtrar por banda de saúde"
            >
              <option value="">Toda saúde</option>
              {HEALTH_OPCOES.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          )}

          {isTarefa && (
            <>
              <input
                value={fOwner}
                onChange={(e) => setFOwner(e.target.value)}
                placeholder="Responsável"
                aria-label="Filtrar por responsável da tarefa"
                className="board-filtro-input"
              />
              <select
                value={fPriority}
                onChange={(e) => setFPriority(e.target.value as TarefaPriority | "")}
                aria-label="Filtrar por prioridade"
              >
                <option value="">Toda prioridade</option>
                {PRIORITY_OPCOES.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </>
          )}

          {isMelhoria && (
            <select
              value={fEffort}
              onChange={(e) => setFEffort(e.target.value as ImprovementEffort | "")}
              aria-label="Filtrar por esforço"
            >
              <option value="">Todo esforço</option>
              {EFFORT_OPCOES.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          )}

          {algumFiltro && (
            <Button variant="ghost" size="sm" onClick={limparFiltros}>
              Limpar filtros
            </Button>
          )}
        </div>
      )}

      {err && (
        <div className="flash err">
          Não consegui falar com o board ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {/* Nota de selo: explica o efeito do drag nos boards de selo de CAMPANHA
          (multi-coluna). No board Follow-up (Trello simples) o card vive em UMA
          coluna só — a nota seria ruído, então fica escondida ali. */}
      {selected?.campo === "selo" && !isFollowup && (
        <div className="note">
          <span className="note-ico">{"\u{1F3F7}\u{FE0F}"}</span>
          <span>
            Board de <b>selo</b>: arrastar um card <b>aplica o selo</b> da coluna ao{" "}
            {isCliente ? "cliente" : "contato"} (o card pode continuar visível nas demais colunas
            cujos selos {isCliente ? "o cliente" : "o contato"} também tem).
          </span>
        </div>
      )}

      {isCliente && isReadonly && (
        <div className="note">
          <span className="note-ico">{"\u{1F512}"}</span>
          <span>
            Board <b>read-only</b>: {CAMPO_LABEL[selected!.campo].toLowerCase()} vem da API de
            Clientes, então os cards não são arrastáveis aqui. Use o board de <b>selo</b> para mover
            clientes na campanha.
          </span>
        </div>
      )}

      {loading && !items ? (
        <div className="board-cols board-track" style={BOARD_TRACK_STYLE} aria-busy="true">
          {Array.from({ length: 3 }).map((_, c) => (
            <section className="board-col board-lane" key={c} style={BOARD_LANE_STYLE}>
              <header className="board-col-head" style={BOARD_HEAD_STYLE}>
                <span className="board-col-name">
                  <span className="sk-line" style={{ width: 70, margin: 0, display: "inline-block" }} />
                </span>
              </header>
              <div className="board-col-body" style={BOARD_BODY_STYLE}>
                {Array.from({ length: c === 1 ? 3 : 2 }).map((_, k) => (
                  <div className="card board-card" key={k} aria-busy="true" style={BOARD_CARD_STYLE}>
                    <div className="board-card-top cell-person" style={{ alignItems: "center" }}>
                      <div className="sk-circle" style={{ ["--sk-size" as string]: "26px" } as React.CSSProperties} />
                      <div className="sk-line w-60" style={{ margin: 0 }} />
                    </div>
                    <div className="sk-line w-90" style={{ marginTop: 10 }} />
                    <div className="sk-line w-50" />
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
      <div className="board-cols board-track reveal-stagger" style={BOARD_TRACK_STYLE}>
        {columns.map((col, colIdx) => {
          // Highlight/drop pela IDENTIDADE da coluna (`col.id`), não por `col.valor`.
          const isOver = overColumn === col.id;
          // Nudge da esteira: só no board de feedback agrupado por action_status,
          // na coluna cujo VALOR é "planejado" (cards sem melhoria ganham o CTA).
          const colunaPlanejado =
            !isCliente &&
            !isTarefa &&
            !isMelhoria &&
            selected?.campo === "action_status" &&
            col.valor === "planejado";
          // Cor da lista (fallback p/ a marca quando a coluna não traz cor).
          const cor = col.cor || "var(--indigo)";
          return (
            <section
              key={col.id}
              className={`board-col board-lane reveal ${isOver ? "is-over" : ""}`}
              style={{
                ...BOARD_LANE_STYLE,
                ["--i" as string]: colIdx,
                // Faixa de cor da lista no topo (cue de "lista" do Trello).
                borderTop: `3px solid ${cor}`,
              } as React.CSSProperties}
              onDragOver={
                dropEnabled
                  ? (e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      if (overColumn !== col.id) setOverColumn(col.id);
                    }
                  : undefined
              }
              onDragLeave={
                dropEnabled
                  ? (e) => {
                      if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                        setOverColumn((cur) => (cur === col.id ? null : cur));
                      }
                    }
                  : undefined
              }
              onDrop={dropEnabled ? (e) => onColumnDrop(e, col.id) : undefined}
              aria-label={`Coluna ${col.nome}`}
            >
              <header className="board-col-head" style={BOARD_HEAD_STYLE}>
                <span
                  className="board-col-name"
                  style={{
                    color: cor,
                    fontSize: 12.5,
                    letterSpacing: "0.4px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 7,
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: 3,
                      background: cor,
                      flex: "0 0 auto",
                    }}
                  />
                  {col.nome}
                </span>
                <span style={countChipStyle(cor)}>{col.count}</span>
              </header>

              {/* "+ feedback" da coluna (board Follow-up): cria um feedback já com o
                  selo desta coluna aplicado (reusa POST /api/feedbacks + board-move). */}
              {isFollowup && (
                <button
                  type="button"
                  className="board-add-card"
                  onClick={() => setNovoCardCol(col)}
                  aria-label={`Adicionar feedback em ${col.nome}`}
                >
                  <span aria-hidden>{"\u{FF0B}"}</span> feedback
                </button>
              )}

              <div className="board-col-body" style={BOARD_BODY_STYLE}>
                {isCliente ? (
                  (col.items as BoardClienteCard[]).map((cli) => (
                    <ClienteCard
                      key={cli.id}
                      cli={cli}
                      draggable={!isReadonly}
                      dragging={draggingId === cli.id}
                      onDragStart={(c) => setDraggingId(c.id)}
                      onDragEnd={() => {
                        setDraggingId(null);
                        setOverColumn(null);
                      }}
                    />
                  ))
                ) : isTarefa ? (
                  (col.items as BoardTarefaCard[]).map((t) => (
                    <TarefaCard
                      key={t.id}
                      tarefa={t}
                      dragging={draggingId === t.id}
                      onDragStart={(c) => setDraggingId(c.id)}
                      onDragEnd={() => {
                        setDraggingId(null);
                        setOverColumn(null);
                      }}
                    />
                  ))
                ) : isMelhoria ? (
                  (col.items as BoardMelhoriaCard[]).map((m) => (
                    <MelhoriaCard
                      key={m.id}
                      melhoria={m}
                      dragging={draggingId === m.id}
                      onDragStart={(c) => setDraggingId(c.id)}
                      onDragEnd={() => {
                        setDraggingId(null);
                        setOverColumn(null);
                      }}
                    />
                  ))
                ) : (
                  (col.items as Feedback[])
                    .filter((fb) => {
                      // Busca client-side só no board Follow-up (barra recolhida).
                      if (!isFollowup || !busca.trim()) return true;
                      const q = busca.trim().toLowerCase();
                      return (
                        (fb.contato_nome || "").toLowerCase().includes(q) ||
                        (fb.text || "").toLowerCase().includes(q)
                      );
                    })
                    .map((fb) => (
                      <BoardCard
                        key={fb.id}
                        fb={fb}
                        dragging={draggingId === fb.id}
                        onDragStart={(f) => setDraggingId(f.id)}
                        onDragEnd={() => {
                          setDraggingId(null);
                          setOverColumn(null);
                        }}
                        onChanged={() => {
                          if (selected) void loadItems(selected.id);
                        }}
                        colunaPlanejado={colunaPlanejado}
                        compact={isFollowup}
                      />
                    ))
                )}

                {col.count === 0 && !loading && (
                  <div className="board-col-empty">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                      style={{ width: 22, height: 22, opacity: 0.7, margin: "0 auto 6px", display: "block" }}
                    >
                      <rect x="3" y="4" width="18" height="16" rx="2" />
                      <path d="M3 9h18" strokeDasharray="2 3" />
                    </svg>
                    <div>nada nesta coluna</div>
                  </div>
                )}
                {col.count > col.items.length && (
                  <div className="board-col-more">
                    + {col.count - col.items.length} mais (top {col.items.length} por{" "}
                    {isCliente
                      ? "health"
                      : isTarefa
                        ? "prioridade"
                        : isMelhoria
                          ? "feedbacks"
                          : "urgência"}
                    )
                  </div>
                )}
              </div>
            </section>
          );
        })}

        {columns.length === 0 && !loading && (
          <div className="card">
            <div className="empty">
              <div className="empty-illu">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="3" y="4" width="5" height="16" rx="1" />
                  <rect x="10" y="4" width="5" height="11" rx="1" />
                  <rect x="17" y="4" width="4" height="7" rx="1" />
                </svg>
              </div>
              <div className="empty-title">
                {boardList.length === 0 ? "Nenhum board ainda" : "Este board não tem colunas"}
              </div>
              <p className="empty-sub">
                {boardList.length === 0
                  ? "Crie um board para organizar feedbacks, clientes, tarefas ou melhorias em colunas."
                  : "Edite o board para adicionar colunas e começar a arrastar os cards."}
              </p>
              <div className="empty-cta">
                <Button
                  onClick={() => (boardList.length === 0 ? setCreating(true) : setEditingBoard(selected))}
                  disabled={boardList.length !== 0 && !selected}
                >
                  {boardList.length === 0 ? "Criar board" : "Editar colunas"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
      )}

      {(creating || editingBoard) && (
        <BoardFormModal
          board={creating ? null : editingBoard}
          onClose={() => {
            setCreating(false);
            setEditingBoard(null);
          }}
          onSaved={async (b) => {
            setCreating(false);
            setEditingBoard(null);
            await loadBoards();
            // Seleciona o board salvo zerando os filtros de forma síncrona, no
            // mesmo commit. Para troca de board, o efeito de recarga dispara com
            // filtros limpos (1 fetch). Para edição in-place (board salvo já era
            // o selecionado, efeito não re-dispara), recarrega explicitamente —
            // os filtros já foram limpos, então não vaza recorte antigo.
            selecionarBoard(b.id);
            await loadItems(b.id, {});
          }}
        />
      )}

      {/* "+ feedback" numa coluna do board Follow-up: cria o feedback e aplica o selo
          da coluna; ao concluir, recarrega os items do board. */}
      {novoCardCol && (
        <NovoCardModal
          coluna={novoCardCol}
          onClose={() => setNovoCardCol(null)}
          onCreated={() => {
            setNovoCardCol(null);
            if (selected) void loadItems(selected.id);
          }}
        />
      )}
    </div>
  );
}
