/** Cliente da API do Escuta (FastAPI local). */

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* corpo não-JSON: mantém statusText */
    }
    throw new ApiError(res.status, detail);
  }
  // 204 / corpo vazio (ex.: DELETE): não tenta parsear JSON.
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  /** DELETE — backend responde 204 (sem corpo); por isso não tipamos o retorno. */
  del: (path: string) =>
    request<unknown>(path, { method: "DELETE" }),
};

// --- Tipos da API -----------------------------------------------------------

export interface Kpis {
  sent: number;
  answered: number;
  closed: number;
  response_rate: number | null;
  nps: number | null;
  promoters: number;
  passives: number;
  detractors: number;
}

export interface ResponseRow {
  id: string;
  contact_name: string | null;
  contact_phone: string;
  status: string;
  score: number | null;
  bucket: string | null;
  text: string | null;
  /** 'nps' | 'exit' — opcionais enquanto a API antiga (sem o dashboard v2) estiver no ar. */
  survey_type?: string;
  survey_name?: string;
  /** Enriquecimento por IA (SurveyBrain) — null/ausente = feedback antigo ou não classificado. */
  sentiment?: string | null;
  themes?: string[] | null;
  sent_at: string | null;
  closed_at: string | null;
}

/** Motivo de cancelamento respondido numa exit survey (sem nota). */
export interface ExitReason {
  contact_name: string | null;
  text: string;
  /** Enriquecimento por IA (SurveyBrain) — null/ausente = feedback antigo ou não classificado. */
  sentiment?: string | null;
  themes?: string[] | null;
  closed_at: string | null;
}

export interface ExitBlock {
  sent: number;
  answered: number;
  recent: ExitReason[];
}

export interface Dashboard {
  org: { slug: string; name: string };
  /** KPIs de NPS (apenas surveys type='nps'). `kpis` é alias retrocompat de `nps`. */
  kpis: Kpis;
  nps?: Kpis;
  /** Exit surveys (churn) — opcional enquanto a API antiga estiver no ar. */
  exit?: ExitBlock;
  recent: ResponseRow[];
}

export interface Survey {
  id: string;
  name: string;
  type: string;
  status: string;
  nps_question: string | null;
  reason_prompt: string | null;
  created_at: string | null;
}

export interface Contact {
  id: string;
  phone: string;
  name: string | null;
  opt_in: boolean;
  created_at: string | null;
}

export interface DispatchResult {
  run_id: string;
  survey: string;
  dispatched_to: { phone: string; name: string | null }[];
  count: number;
}

// --- Visão 360 (Mega Central de Dados) --------------------------------------

export interface Timeline360Item {
  /** 'feedback_item' = sinal ingerido de fonte externa; 'survey' = coletado no WhatsApp. */
  kind: "feedback_item" | "survey";
  source: string;
  type: string;
  survey_name?: string;
  score: number | null;
  bucket: string | null;
  text: string | null;
  status?: string;
  sentiment?: string | null;
  themes?: string[] | null;
  at: string | null;
}

export interface Contact360 {
  contact: { id: string; name: string | null; phone: string; opt_in: boolean };
  /** Snapshot da API de Clientes (assinatura/perfil/nps). null = ainda não sincronizado. */
  partner: Record<string, unknown> | null;
  summary: { total: number; feedback_items: number; survey_responses: number };
  timeline: Timeline360Item[];
}

// --- Temas (Top dores — clustering de feedbacks) ----------------------------

/** Distribuição de sentimento de um tema. Espelha `sentiment_breakdown` do backend. */
export interface ThemeSentiment {
  positivo: number;
  neutro: number;
  negativo: number;
}

/** Um tema agregado no período: nome (já normalizado pela IA), volume e sentimento. */
export interface Tema {
  name: string;
  count: number;
  sentiment: ThemeSentiment;
}

/** Resposta de GET /api/themes/aggregate — clustering v1 (survey + feedback). */
export interface ThemesAggregate {
  period_days: number;
  /** Soma das contagens de todos os temas (um feedback com N temas conta N vezes). */
  total: number;
  themes: Tema[];
}

// --- Clusters de dores (clustering semântico por significado) ----------------

/** Um cluster de dores agrupado por significado. Espelha `ClusterOut` (§4 da spec).
    `pain_score = item_count * neg_fraction`; `label`/`description`/`dominant_sentiment`
    podem ser null (LLM best-effort não rotulou ainda). */
export interface FeedbackCluster {
  id: string;
  label: string | null;
  description: string | null;
  /** 'positivo' | 'neutro' | 'negativo' | null (sentimento mais frequente no cluster) */
  dominant_sentiment: string | null;
  item_count: number;
  /** Quantos itens do cluster têm sentimento negativo. */
  neg_count: number;
  /** Índice de dor: volume × fração negativa. */
  pain_score: number;
  /** Tags/temas mais frequentes entre os itens do cluster. */
  top_themes: string[];
  /** Melhoria ligada a esta dor (usado no Roadmap depois) ou null. */
  improvement_id: string | null;
  created_at: string | null;
}

/** Resposta de GET /api/feedbacks/clusters — descoberta de dores por significado. */
export interface ClustersResponse {
  clusters: FeedbackCluster[];
  total_items_clustered: number;
  total_unclustered: number;
}

// --- Clientes (todos os contatáveis da Bizzu) -------------------------------

/** Linha da tela Clientes — snapshot enriquecido pela API de Clientes da Bizzu. */
export interface Cliente {
  id: string;
  nome: string | null;
  whatsapp: string;
  opt_in: boolean;
  /** 'em_risco' | 'promotor' | 'silencioso' | ... — perfil derivado pela Bizzu. */
  perfil: string | null;
  plano: string | null;
  plan_type: string | null;
  nps_score: number | null;
  dias_para_renovar: number | null;
  ultimo_feedback_em: string | null;
  /** 'nps' | 'churn' | ... tipo do feedback mais recente. */
  ultimo_feedback_tipo: string | null;
  total_feedbacks: number;
  /** Health Score (0-100) + banda + fatores que pesaram — Fase 1 CS. */
  health: number;
  health_band: "healthy" | "watch" | "at_risk";
  health_factors: { delta: number; label: string }[];
  criado_em: string | null;
}

// --- Feedbacks (inbox de monitoramento) -------------------------------------

/** Estados do fluxo de ação sobre um feedback. */
export type FeedbackStatus =
  | "novo"
  | "em_analise"
  | "planejado"
  | "resolvido"
  | "descartado";

/** Um feedback no feed cronológico — coletado no WhatsApp ou ingerido de fonte externa. */
export interface Feedback {
  id: string;
  contato_id: string | null;
  contato_nome: string | null;
  contato_whatsapp: string | null;
  source: string;
  /** 'nps' | 'churn' | ... */
  type: string;
  score: number | null;
  /** 'promoter' | 'passive' | 'detractor' | null */
  nps_bucket: string | null;
  /** 'positivo' | 'neutro' | 'negativo' | null (IA) */
  sentiment: string | null;
  themes: string[] | null;
  text: string | null;
  action_status: FeedbackStatus;
  action_note: string | null;
  /** Já abordamos esse cliente sobre o feedback? (controle interno do time) */
  abordado: boolean;
  /** Quando foi marcado como abordado (ISO) ou null. */
  abordado_em: string | null;
  occurred_em: string | null;
  created_em: string | null;
  /** Score de urgência 0-100 (sentimento + perfil + recência) — ordena o inbox. */
  urgencia: number;
}

/** Corpo do POST /api/feedbacks (criar feedback manual). */
export interface FeedbackInput {
  /** Use contato_id OU (contato_whatsapp + contato_nome) para cliente fora da base. */
  contato_id?: string;
  contato_whatsapp?: string;
  contato_nome?: string;
  source?: string;
  type: string;
  score?: number | null;
  text?: string | null;
  sentiment?: string | null;
  themes?: string[] | null;
  abordado?: boolean;
}

/** Corpo parcial do PATCH /api/feedbacks/{id}. */
export interface FeedbackPatch {
  action_status?: FeedbackStatus;
  action_note?: string;
  abordado?: boolean;
  text?: string | null;
  type?: string;
  score?: number | null;
  sentiment?: string | null;
  themes?: string[] | null;
}

/** Contagens por status para as abas do inbox. */
export interface FeedbackCounts {
  novo: number;
  em_analise: number;
  planejado: number;
  resolvido: number;
  descartado: number;
}

/** Resposta paginada de /api/feedbacks. */
export interface FeedbacksResponse {
  items: Feedback[];
  total: number;
  counts_by_status: FeedbackCounts;
}

// --- Fase 2: Playbooks (regras gatilho → ação) ------------------------------

/** Gatilhos suportados por um playbook (espelha o enum `trigger_type` do backend). */
export type PlaybookTrigger =
  | "nps_detractor"
  | "health_at_risk"
  | "inactive_days"
  | "renewal_soon"
  | "churn_detected";

/** Ações suportadas por um playbook (espelha o enum `action_type` do backend). */
export type PlaybookAction = "create_task" | "alert_owner";

/** Uma regra de automação. Espelha `PlaybookOut` (§4 da spec). `*_config` são
    JSONB livres (ex.: trigger {band:"at_risk"} | {days:14}; action {priority,sla_hours,owner}). */
export interface Playbook {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  trigger_type: PlaybookTrigger;
  trigger_config: Record<string, unknown>;
  action_type: PlaybookAction;
  action_config: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

/** Corpo do POST /api/playbooks (criar regra). */
export interface PlaybookInput {
  name: string;
  description?: string | null;
  enabled?: boolean;
  trigger_type: PlaybookTrigger;
  trigger_config?: Record<string, unknown>;
  action_type: PlaybookAction;
  action_config?: Record<string, unknown>;
}

/** Corpo parcial do PATCH /api/playbooks/{id}. */
export interface PlaybookPatch {
  name?: string;
  description?: string | null;
  enabled?: boolean;
  trigger_type?: PlaybookTrigger;
  trigger_config?: Record<string, unknown>;
  action_type?: PlaybookAction;
  action_config?: Record<string, unknown>;
}

/** Relatório de uma rodada do motor — GET/POST /api/playbooks/run?dry_run=. */
export interface RunReport {
  evaluated: number;
  playbooks_run: number;
  tasks_would_create: unknown[];
  tasks_created: number;
  skipped_duplicate: number;
}

// --- Fase 2: Tarefas de CS (fila priorizada) --------------------------------

/** Estados de uma tarefa de CS (default `aberta`). */
export type TarefaStatus = "aberta" | "em_andamento" | "concluida" | "adiada";

/** Prioridade de uma tarefa (default `normal`). */
export type TarefaPriority = "baixa" | "normal" | "alta" | "urgente";

/** Uma tarefa concreta na fila de CS. Espelha `TarefaOut` (§4 da spec).
    `health`/`health_band` vêm recomputados inline pelo backend (reusa compute_health). */
export interface Tarefa {
  id: string;
  contato_id: string | null;
  contato_nome: string | null;
  contato_whatsapp: string | null;
  playbook_id: string | null;
  playbook_nome: string | null;
  title: string;
  reason: string | null;
  status: TarefaStatus;
  priority: TarefaPriority;
  owner: string | null;
  due_at: string | null;
  snoozed_until: string | null;
  notes: string | null;
  health: number | null;
  health_band: "healthy" | "watch" | "at_risk" | null;
  meta: Record<string, unknown> | null;
  criada_em: string | null;
  atualizada_em: string | null;
}

/** Corpo do POST /api/tarefas (tarefa manual). */
export interface TarefaInput {
  contato_id: string;
  title: string;
  reason?: string | null;
  priority?: TarefaPriority;
  owner?: string | null;
  due_at?: string | null;
}

/** Corpo parcial do PATCH /api/tarefas/{id}. */
export interface TarefaPatch {
  status?: TarefaStatus;
  owner?: string | null;
  priority?: TarefaPriority;
  due_at?: string | null;
  snoozed_until?: string | null;
  notes?: string | null;
}

/** Contagens por status para os KPIs/abas da fila de tarefas. */
export interface TarefaCounts {
  aberta: number;
  em_andamento: number;
  concluida: number;
  adiada: number;
}

/** Resposta paginada de GET /api/tarefas. */
export interface TarefasResponse {
  items: Tarefa[];
  total: number;
  counts_by_status: TarefaCounts;
}
