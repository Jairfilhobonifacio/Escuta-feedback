/** Cliente da API do Escuta (FastAPI).
 *
 * Base RELATIVA por padrão: string vazia → as chamadas viram `/api/...`
 * same-origin e caem no proxy BFF (`app/api/[...path]/route.ts`), que injeta a
 * chave server-side (X-Panel-Key) e fala com o FastAPI — o browser nunca vê a
 * chave nem cruza CORS. Para apontar direto ao backend (debug), defina
 * NEXT_PUBLIC_API_URL (ex.: http://localhost:8000); em prod deixe vazio. */
const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
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
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  /** DELETE — backend responde 204 (sem corpo); por isso não tipamos o retorno. */
  del: (path: string) =>
    request<unknown>(path, { method: "DELETE" }),
};

/** Monta uma query string a partir de um objeto de filtros (pula undefined/null/"").
    Booleans viram 'true'/'false'. Prefixa com '?' só quando há ao menos um par.
    Aceita qualquer objeto (interfaces sem index signature inclusive). */
export function buildQuery(params: object | undefined): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

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
  /** Acompanhamento — quantos receberam (todas as respostas registradas da survey).
      0 quando nunca disparou. Exige API com o backend novo de contagens. */
  sent_count: number;
  /** Quantos já deram nota (status avançou de 'sent'/'expired' ou tem score). */
  answered_count: number;
  /** Enviados que ainda não responderam (sent_count - answered_count). */
  pending_count: number;
  /** Último disparo (ISO) ou null se a survey nunca rodou. */
  last_run_at: string | null;
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

/** Selo VIVO (derivado do estado do cliente) — READ-ONLY, não editável.
    O backend deriva de VIP/Detrator/Em risco/Novo/Renovação próxima e devolve
    rótulo + cor (hex) + motivo (texto p/ tooltip) + ícone (emoji ⭐⚠️🔻🌱🔁).
    Distingue-se dos selos MANUAIS de campanha (`selos: string[]`, editáveis). */
export interface SeloVivo {
  nome: string;
  /** Cor hex do selo (ex.: "#10b981"). */
  cor: string;
  /** Por que o selo está vivo (ex.: "NPS 10", "renova em 6 dias") — vai no tooltip. */
  motivo: string;
  /** Emoji do selo (⭐ ⚠️ 🔻 🌱 🔁). */
  icone: string;
}

/** Origem de um evento de selo na timeline (kind='selo'). Mapeada para PT na UI:
    manual="manual" · whatsapp_enviado="envio 1:1" · abordagem="abordagem registrada"
    · form="formulário" · inbound="resposta no WhatsApp" · regra="regra automática"
    · ia="sugestão da IA". Tipado aberto (string) para tolerar origens novas. */
export type SeloOrigem =
  | "manual"
  | "whatsapp_enviado"
  | "abordagem"
  | "form"
  | "inbound"
  | "regra"
  | "ia"
  | (string & {});

export interface Timeline360Item {
  /** 'feedback_item' = sinal de fonte externa; 'survey' = coletado no WhatsApp;
      'selo' = evento de histórico de selo (aplicado/removido), READ-ONLY. */
  kind: "feedback_item" | "survey" | "selo";
  /** Id do FeedbackItem — presente só em kind='feedback_item' (alvo do PATCH na 360 editável). */
  id?: string;
  source: string;
  type: string;
  survey_name?: string;
  score: number | null;
  bucket: string | null;
  text: string | null;
  status?: string;
  sentiment?: string | null;
  /** Grau de confiança da IA (só kind='feedback_item'; de ai_meta). Ausente =
      sem dado / API antiga → fallback gracioso. */
  confianca?: "alta" | "media" | "baixa" | null;
  /** A IA classificou com baixa confiança? (só kind='feedback_item'). */
  incerto?: boolean;
  /** Palpite de sentimento preservado quando `incerto` (só kind='feedback_item'). */
  sentiment_sugerido?: string | null;
  themes?: string[] | null;
  /** Estado de ação do feedback (só kind='feedback_item') — editável na 360. */
  action_status?: FeedbackStatus;
  /** Nota interna do operador (só kind='feedback_item') — editável na 360. */
  action_note?: string | null;
  /** Já abordamos o cliente sobre este feedback? (só kind='feedback_item'). */
  abordado?: boolean;
  /** "Reabordar este feedback em" (ISO/UTC) ou null — follow-up agendado
      (só kind='feedback_item'). Vencido = `follow_up_at <= agora`. */
  follow_up_at?: string | null;
  // --- Campos só de kind='selo' (histórico de selos) -------------------------
  /** Nome do selo aplicado/removido (só kind='selo'). */
  selo?: string;
  /** O que aconteceu com o selo (só kind='selo'). */
  acao?: "aplicado" | "removido";
  /** Quem fez (operador/sistema) ou null (só kind='selo'). */
  por?: string | null;
  /** De onde veio a ação do selo (só kind='selo'). */
  origem?: SeloOrigem;
  /** Operador que editou este feedback por último (só kind='feedback_item';
      do `feedback_log`). null/ausente = nunca editado / backend antigo. */
  editado_por?: string | null;
  /** Quando foi a última edição manual deste feedback (ISO/UTC) ou null. */
  editado_em?: string | null;
  at: string | null;
}

export interface Contact360 {
  contact: {
    id: string;
    name: string | null;
    phone: string;
    opt_in: boolean;
    /** Selos de campanha aplicados ao contato (chips editáveis no cabeçalho). */
    selos?: string[];
    /** Selos VIVOS derivados do estado (READ-ONLY) — chips automáticos no cabeçalho,
        distintos dos `selos` manuais. Ausente/vazio na API antiga (fallback gracioso). */
    selos_vivos?: SeloVivo[];
    /** Sem WhatsApp real? (phone vazio ou 'nowa-') — chip "só e-mail" no cabeçalho. */
    sem_whatsapp?: boolean;
  };
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

  // --- Índice de prioridade (volume × receita × gravidade) -------------------
  // Campos ADITIVOS e OPCIONAIS (FRENTE F1, `app/domain/prioridade.py`). Quando
  // ausentes (backend antigo ou cálculo ainda não disponível), a UI faz fallback
  // gracioso para `pain_score`/volume — nenhum consumidor existente quebra.
  /** nº de clientes distintos (COUNT(DISTINCT contact_id)) no cluster. */
  distinct_customers?: number;
  /** nº de clientes pagantes (partner.subscription) entre os distintos. */
  paying_customers?: number;
  /** Índice de prioridade final, 0–100. */
  priority_index?: number;
  /** Banda do índice — define o selo de prioridade. */
  priority_band?: "alta" | "media" | "baixa";
  /** Componentes normalizados (0–1) + pesos — explicam "por que essa prioridade". */
  priority_breakdown?: {
    volume_score: number;
    revenue_score: number;
    gravity_score: number;
    weights: { volume: number; revenue: number; gravity: number };
  };
}

/** Resposta de GET /api/feedbacks/clusters — descoberta de dores por significado. */
export interface ClustersResponse {
  clusters: FeedbackCluster[];
  total_items_clustered: number;
  total_unclustered: number;
}

/** Ordenação de GET /api/feedbacks/clusters:
    'prioridade' (priority_index desc — novo default) | 'dor' (pain_score desc) |
    'volume' (item_count desc) | 'recente' (created desc). */
export type ClustersSort = "prioridade" | "dor" | "volume" | "recente";

/** Filtros opcionais de GET /api/feedbacks/clusters.
    `days`: só clusters dos últimos N dias (null/0 = todos; default backend = 30). */
export interface ClustersFiltro {
  days?: number | null;
  sort?: ClustersSort;
}

// --- Clientes (todos os contatáveis da Bizzu) -------------------------------

/** Linha da tela Clientes — snapshot enriquecido pela API de Clientes da Bizzu. */
export interface Cliente {
  id: string;
  nome: string | null;
  whatsapp: string;
  opt_in: boolean;
  /** Tem WhatsApp REAL? false quando phone vazio ou começa com 'nowa-' (universo só-email). */
  tem_whatsapp: boolean;
  /** Estado da assinatura no snapshot partner (ex.: 'cancelled', 'active_paying') ou null. */
  estado: string | null;
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
  /** Selos da campanha win-back aplicados ao cliente (lista de nomes). [] quando não há. */
  selos: string[];
  /** Selos VIVOS derivados do estado (READ-ONLY): VIP/Detrator/Em risco/Novo/Renovação
      próxima. Distintos dos `selos` manuais. Ausente/vazio na API antiga (fallback gracioso). */
  selos_vivos?: SeloVivo[];
  /** Health Score (0-100) + banda + fatores que pesaram — Fase 1 CS. */
  health: number;
  health_band: "healthy" | "watch" | "at_risk";
  health_factors: { delta: number; label: string }[];
  criado_em: string | null;
}

// --- Filtros "por tipo de cliente" (Clientes + Feedbacks) -------------------

/** Bucket de NPS derivado do score: promotor (>=9) | neutro (7-8) | detrator (<=6). */
export type NpsBucket = "promotor" | "neutro" | "detrator";

/** Banda do Health Score (Fase 1 CS). */
export type HealthBand = "healthy" | "watch" | "at_risk";

/** Estado da assinatura no snapshot partner (partner.subscription.state). */
export type EstadoAssinatura =
  | "cancelled"
  | "paid_without_access"
  | "active_paying"
  | "complimentary"
  | "past_due";

/** Filtro tem/sem WhatsApp REAL (celular BR válido pelo validador do backend). */
export type TemWhatsappFiltro = "sim" | "nao";

/** Filtros opcionais de GET /api/clientes (query string; ausentes = sem filtro).
    `estado` é aplicado em SQL; `nps_bucket`/`health_band`/`tem_whatsapp` são POST-FILTER. */
export interface ClienteFiltro {
  /** Trecho no nome OU no whatsapp. */
  search?: string;
  /** partner.profile, ex.: 'ativo_promotor', 'churn_pos_uso'. */
  perfil?: string;
  /** partner.subscription.planType, 'mensal' | 'anual'. */
  plan_type?: string;
  /** partner.subscription.state. */
  estado?: EstadoAssinatura;
  nps_bucket?: NpsBucket;
  health_band?: HealthBand;
  tem_whatsapp?: TemWhatsappFiltro;
  /** Já abordados (selo 'contatado'): 'sim' = só abordados, 'nao' = só não-abordados.
      A UI mantém o refino client-side como fallback caso o backend ignore o param. */
  abordado?: TemWhatsappFiltro;
}

/** Filtros opcionais de GET /api/feedbacks (query string; ausentes = sem filtro).
    Todos aplicados em SQL (no feed E nas contagens, para o total bater). */
export interface FeedbackFiltro {
  status?: FeedbackStatus;
  /** 'nps' | 'churn' | ... */
  type?: string;
  source?: string;
  /** 'positivo' | 'neutro' | 'negativo' */
  sentiment?: string;
  /** Drill-down da tela Temas (match exato do elemento). */
  theme?: string;
  /** Feedbacks de contatos com aquele selo aplicado. */
  selo?: string;
  cluster_id?: string;
  assignee?: string;
  team_tag?: string;
  abordado?: boolean;
  /** 'hoje' | '7d' | '30d' — recorte de `abordado_em`. */
  abordado_periodo?: string;
  /** Fila de follow-up: true = só os VENCIDOS (`follow_up_at <= agora`);
      false = só os sem follow-up ou agendados no futuro. Ausente = não filtra. */
  follow_up_vencido?: boolean;
  /** Filtros "por tipo de cliente" (sobre o contato juntado). */
  estado?: EstadoAssinatura;
  perfil?: string;
  plan_type?: string;
  tem_whatsapp?: TemWhatsappFiltro;
  nps_bucket?: NpsBucket;
  search?: string;
  sort?: "urgencia" | "recente";
  limit?: number;
  offset?: number;
}

// --- Feedbacks (inbox de monitoramento) -------------------------------------

/** Estados do fluxo de ACOMPANHAMENTO sobre um feedback (vocabulário de relacionamento,
    não de bug-tracker). Espelha os defaults de ACTION_STATUSES do backend; os valores são
    dirigidos pelo servidor (string livre), então um status custom/legado também aparece
    em runtime — daí FeedbackCounts ser indexável por qualquer chave. */
export type FeedbackStatus =
  | "a_abordar"
  | "aguardando_retorno"
  | "em_acompanhamento"
  | "resolvido"
  | "sem_retorno"
  | "descartado";

/** Um feedback no feed cronológico — coletado no WhatsApp ou ingerido de fonte externa. */
export interface Feedback {
  id: string;
  contato_id: string | null;
  contato_nome: string | null;
  contato_whatsapp: string | null;
  /** Selos de campanha do CONTATO (status win-back no inbox). [] quando não há. */
  selos: string[];
  source: string;
  /** 'nps' | 'churn' | ... */
  type: string;
  score: number | null;
  /** 'promoter' | 'passive' | 'detractor' | null */
  nps_bucket: string | null;
  /** 'positivo' | 'neutro' | 'negativo' | null (IA) */
  sentiment: string | null;
  /** Grau de confiança da classificação de IA (derivado de ai_meta). Ausente
      na API antiga / quando a flag SENTIMENT_PT_V2 está OFF → fallback gracioso. */
  confianca?: "alta" | "media" | "baixa" | null;
  /** A IA classificou com baixa confiança? Quando true, NÃO chutamos o sentimento
      (fica null) e convidamos o operador a revisar. Default ausente = false. */
  incerto?: boolean;
  /** Palpite de sentimento preservado quando `incerto` (a IA não chuta o campo
      `sentiment`, mas guarda a sugestão aqui para o operador ver). */
  sentiment_sugerido?: string | null;
  themes: string[] | null;
  text: string | null;
  action_status: FeedbackStatus;
  action_note: string | null;
  /** Quem do time cuida (slug/email) — roteamento do Board. null = sem dono. */
  assignee: string | null;
  /** Time responsável (produto|suporte|comercial|cs) — roteamento do Board. */
  team_tag: string | null;
  /** Já abordamos esse cliente sobre o feedback? (controle interno do time) */
  abordado: boolean;
  /** Quando foi marcado como abordado (ISO) ou null. */
  abordado_em: string | null;
  /** "Reabordar este feedback em" (ISO, UTC) — follow-up agendado, ou null.
      Vencido = `follow_up_at <= agora`. Ausente na API antiga (fallback gracioso). */
  follow_up_at?: string | null;
  occurred_em: string | null;
  created_em: string | null;
  /** Score de urgência 0-100 (sentimento + perfil + recência) — ordena o inbox. */
  urgencia: number;
  // --- Enriquecimento SÓ do card do Board (GET /api/boards/{id}/items) ---------
  // Estes campos vêm preenchidos APENAS quando o Feedback é um card de board
  // (`_enrich_feedback_cards` do backend). No feed normal (/api/feedbacks) eles
  // não aparecem — por isso opcionais. assignee/team_tag/improvement_id/abordado
  // já existem acima e também são reafirmados pelo backend no card do board.
  /** Operador que editou o feedback por último (do `feedback_log` em
      profile_data, exposto pelo backend após o login de operador). null/ausente
      = nunca editado manualmente ou backend antigo. */
  editado_por?: string | null;
  /** Quando foi a última edição manual (ISO/UTC) ou null/ausente. */
  editado_em?: string | null;
  /** Existe alguma CsTask vinculada a este feedback? (card do board) */
  tem_tarefa?: boolean;
  /** Status da CsTask MAIS RECENTE vinculada, ou null se não há tarefa. */
  tarefa_status?: TarefaStatus | null;
  /** Id da Improvement vinculada (ou null). Exposto pelo backend (_feedback_out). */
  improvement_id?: string | null;
  /** Título da Improvement vinculada (via improvement_id), ou null. */
  melhoria_titulo?: string | null;
  /** Label do FeedbackCluster (dor) vinculado (via cluster_id), ou null. */
  dor_label?: string | null;
  /** Nº de Message (conversa) do contato; 0 se sem contato/sem mensagens. */
  conversa_count?: number;
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
  /** Data do evento na linha do tempo (ISO ou 'YYYY-MM-DD'); ausente/null = agora.
      O backend rejeita data no futuro (422). */
  occurred_at?: string | null;
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
  /** "Reabordar em" (ISO-8601 UTC) — agenda o follow-up; `null` LIMPA o agendamento.
      AUSENTE do corpo = não mexe no follow-up atual. */
  follow_up_at?: string | null;
  /** Roteamento do Board (Camada 2). */
  assignee?: string | null;
  team_tag?: string | null;
  /** Vínculo de melhoria (Camada 3): uuid de Improvement da org, ou null p/ DESVINCULAR.
      AUSENTE do corpo = mantém o vínculo atual; NÃO mexe no action_status (backend). */
  improvement_id?: string | null;
}

/** Corpo (todos opcionais) do POST /api/feedbacks/{id}/sugerir-resposta — pede um
    RASCUNHO de resposta à IA. NUNCA envia nada; o operador revisa e envia manual. */
export interface SugerirRespostaIn {
  /** Viés de tom; null/ausente = automático pela nota/sentimento. */
  tom?: "acolhedor" | "resolutivo" | "agradecimento" | null;
  /** Nota livre do operador (ex.: "ofereça 1 mês grátis"); tratada como DADO
      (anti-injection) e truncada no backend. */
  instrucao_extra?: string | null;
}

/** Resposta do POST /api/feedbacks/{id}/sugerir-resposta. */
export interface SugerirRespostaResult {
  /** Texto pronto para o operador revisar (1-4 frases, PT-BR, tom da marca). */
  rascunho: string;
  /** Sempre true — sinaliza à UI que é sugestão, não ação (a IA nunca envia). */
  is_rascunho: boolean;
  /** "ai" = veio do modelo; "fallback" = LLM indisponível → texto neutro determinístico. */
  fonte: "ai" | "fallback";
  /** Modelo usado, ou null no fallback. */
  modelo: string | null;
}

/** Contagens por status para as abas do inbox. */
/** Contagens por status no feed. Indexável por qualquer chave de status (defaults de
    acompanhamento + status custom da org + legado), pois o backend devolve
    `counts_by_status` keado dinamicamente pela lista efetiva de status. */
export type FeedbackCounts = Record<string, number>;

/** Resposta paginada de /api/feedbacks. */
export interface FeedbacksResponse {
  items: Feedback[];
  total: number;
  counts_by_status: FeedbackCounts;
}

// --- Camada 2: Board (Kanban de triagem) ------------------------------------

/** Uma coluna do Board: total da coluna + os feedbacks mais urgentes dela. */
export interface FeedbackBoardColumn {
  /** Total de feedbacks na coluna (não só os carregados em `items`). */
  count: number;
  /** Top N (12) mais urgentes da coluna — o que aparece como card. */
  items: Feedback[];
}

/** Resposta de GET /api/feedbacks/board — itens agrupados por `action_status`. */
export interface FeedbackBoard {
  columns: Record<FeedbackStatus, FeedbackBoardColumn>;
}

/** Corpo do POST /api/feedbacks/{id}/move (o "drag-and-drop": 1 req por card).
    `improvement_id` só é usado quando `status === "planejado"` (vincula a melhoria). */
export interface FeedbackMoveInput {
  status: FeedbackStatus;
  improvement_id?: string | null;
  assignee?: string | null;
}

// --- Boards dinâmicos (kanbans customizados em Organization.settings) --------

/** Entidade que um board agrupa: 'feedback' (FeedbackItem, board clássico),
    'cliente' (Contact), 'tarefa' (CsTask) ou 'melhoria' (Improvement). Ausente no
    backend antigo => 'feedback' (retrocompat). */
export type BoardEntidade = "feedback" | "cliente" | "tarefa" | "melhoria";

/** Campo que um board agrupa.
    - entidade='feedback': 'action_status' | 'selo'.
    - entidade='cliente':  'selo' | 'estado' | 'perfil'.
    - entidade='tarefa':   'status' (CsTask.status).
    - entidade='melhoria': 'status' (Improvement.status).
    ATENÇÃO: há 2 conceitos "status" — o de feedback é 'action_status'; o de
    tarefa/melhoria é 'status'. O tipo é a UNIÃO de todos; a validação por entidade é
    feita no backend (422). */
export type BoardCampo = "action_status" | "selo" | "estado" | "perfil" | "status";

/** Campos válidos por entidade — espelha BOARD_CAMPOS_POR_ENTIDADE do backend. */
export const BOARD_CAMPOS_POR_ENTIDADE: Record<BoardEntidade, BoardCampo[]> = {
  feedback: ["action_status", "selo"],
  cliente: ["selo", "estado", "perfil"],
  tarefa: ["status"],
  melhoria: ["status"],
};

/** Uma coluna de um board (config). `valor` = action_status/selo/estado/perfil. */
export interface BoardColuna {
  id: string;
  nome: string;
  valor: string;
  cor?: string;
}

/** Um board customizado (config). Espelha Organization.settings["boards"][i].
    `entidade` ausente => 'feedback' (boards salvos antes deste campo). */
export interface Board {
  id: string;
  nome: string;
  entidade: BoardEntidade;
  campo: BoardCampo;
  colunas: BoardColuna[];
}

/** Corpo do POST /api/boards (criar board). */
export interface BoardInput {
  nome: string;
  entidade: BoardEntidade;
  campo: BoardCampo;
  colunas: BoardColuna[];
}

/** Corpo parcial do PATCH /api/boards/{id}. */
export interface BoardPatch {
  nome?: string;
  colunas?: BoardColuna[];
}

/** Card de CLIENTE num board entidade='cliente' (mesma forma do GET /api/clientes).
    Espelha `_cliente_card` do backend. */
export interface BoardClienteCard {
  id: string;
  nome: string | null;
  whatsapp: string | null;
  /** Tem WhatsApp REAL? false quando phone vazio ou começa com 'nowa-' (só-email). */
  tem_whatsapp: boolean;
  perfil: string | null;
  /** Estado da assinatura no snapshot partner (ex.: 'cancelled') ou null. */
  estado: string | null;
  health: number;
  health_band: "healthy" | "watch" | "at_risk";
  /** Selos de campanha aplicados ao cliente. [] quando não há. */
  selos: string[];
  // --- Conexões do cliente (calculadas EM LOTE pelo backend) ------------------
  /** Nº de FeedbackItem do contato na org. */
  feedbacks_count: number;
  /** Nº de CsTask do contato NÃO concluídas (status != 'concluida'). */
  tarefas_abertas: number;
  /** Nº de Message (conversa) do contato. */
  conversa_count: number;
}

/** Card de TAREFA num board entidade='tarefa'. Espelha `_tarefa_card` do backend
    (dict enxuto — espelha o essencial de `TarefaOut`). `feedback_preview` é o trecho
    (≈140 chars) do feedback vinculado ou null. O status muda via PATCH /api/tarefas/{id}
    (não há board-move de tarefa). */
export interface BoardTarefaCard {
  id: string;
  titulo: string;
  status: TarefaStatus;
  priority: TarefaPriority;
  owner: string | null;
  contato_id: string | null;
  contato_nome: string | null;
  /** Data-limite (ISO) ou null. */
  due_at: string | null;
  /** FeedbackItem vinculado (cs_tasks.feedback_item_id) ou null. */
  feedback_id: string | null;
  /** Trecho do feedback vinculado (≈140 chars com '…') ou null. */
  feedback_preview: string | null;
}

/** Card de MELHORIA num board entidade='melhoria'. Espelha `_melhoria_card` do backend
    (dict enxuto). `feedback_count` = nº de FeedbackItem com improvement_id == id (em
    lote). `priority_score` é derivado só no /improvements/roadmap (não é coluna do
    modelo) — omitido pelo backend aqui, por isso opcional. O status muda via PATCH
    /api/improvements/{id} (não há board-move de melhoria). */
export interface BoardMelhoriaCard {
  id: string;
  titulo: string;
  status: ImprovementStatus;
  /** Quantos feedbacks pediram essa melhoria (calculado em lote pelo backend). */
  feedback_count: number;
  effort?: ImprovementEffort | null;
  /** Data-alvo (ISO) ou null. */
  target_date?: string | null;
  /** Omitido pelo card do board; presente só no /improvements/roadmap. */
  priority_score?: number;
}

/** Uma coluna do board JÁ com os cards (resposta de GET /api/boards/{id}/items).
    Os cards são `Feedback[]` (entidade='feedback'), `BoardClienteCard[]`
    (entidade='cliente'), `BoardTarefaCard[]` (entidade='tarefa') ou
    `BoardMelhoriaCard[]` (entidade='melhoria') — decida pela `entidade` do BoardItems
    pai. */
export interface BoardItemsColuna extends BoardColuna {
  /** Total real de cards na coluna (não só os carregados em `items`). */
  count: number;
  /** Top N da coluna — feedbacks (urgência), clientes (health asc), tarefas
      (prioridade+SLA) ou melhorias (feedback_count desc). */
  items: Feedback[] | BoardClienteCard[] | BoardTarefaCard[] | BoardMelhoriaCard[];
}

/** Resposta de GET /api/boards/{id}/items — colunas com cards. */
export interface BoardItems {
  id: string;
  nome: string;
  entidade: BoardEntidade;
  campo: BoardCampo;
  colunas: BoardItemsColuna[];
}

/** Filtros opcionais de GET /api/boards/{id}/items (query string; ausentes = board
    inteiro). Mesmo vocabulário de `ClienteFiltro`/`FeedbackFiltro`/`TarefaFiltro`, mas
    APLICADO ANTES do agrupamento no backend, então tanto `items` QUANTO `count` de cada
    coluna refletem o filtro. Cada campo só vale para a(s) entidade(s) a que pertence; os
    demais o backend ignora sem erro. Espelha `BoardItemFilters` de app/api/boards.py. */
export interface BoardItemFiltro {
  /** feedback + cliente (via o CONTATO): partner.subscription.state. */
  estado?: EstadoAssinatura;
  /** feedback + cliente (via o CONTATO): partner.subscription.planType. */
  plan_type?: string;
  /** feedback + cliente (via o CONTATO): partner.profile. */
  perfil?: string;
  /** feedback + cliente (via o CONTATO): tem WhatsApp REAL ('sim'/'nao'). */
  tem_whatsapp?: TemWhatsappFiltro;
  /** feedback + cliente (via o CONTATO): faixa de NPS. */
  nps_bucket?: NpsBucket;
  /** Só feedback (coluna do FeedbackItem). */
  team_tag?: string;
  /** Só feedback (coluna do FeedbackItem). */
  assignee?: string;
  /** Só feedback (coluna do FeedbackItem). */
  abordado?: boolean;
  /** Só cliente (post-filter sobre o card). */
  health_band?: HealthBand;
  /** Só tarefa (coluna do CsTask). */
  owner?: string;
  /** Só tarefa (coluna do CsTask). */
  priority?: TarefaPriority;
  /** Só melhoria (coluna do Improvement). */
  effort?: ImprovementEffort;
}

/** Corpo do POST /api/feedbacks/{id}/board-move (drag-and-drop de feedback).
    campo='action_status' seta o status; campo='selo' aplica o selo ao contato. */
export interface BoardMoveInput {
  campo: BoardCampo;
  valor: string;
  /** Item C — reorder manual dentro da coluna (só campo='action_status').
      `position` = índice 0-based de destino; `board_id` é retrocompat (ignorado
      na persistência). Opcionais p/ não quebrar os call-sites que só movem de coluna. */
  board_id?: string;
  position?: number;
}

/** Corpo do POST /api/contacts/{id}/board-move (drag-and-drop de cliente).
    campo='selo' aplica o selo ao contato; campo='estado'|'perfil' é read-only (409). */
export interface ContactBoardMoveInput {
  campo: BoardCampo;
  valor: string;
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
  /** FeedbackItem vinculado (coluna cs_tasks.feedback_item_id) ou null. */
  feedback_id: string | null;
  /** Texto do feedback vinculado truncado em 140 chars (com '…') — null se sem texto.
      Só vem preenchido no GET e no POST; é sempre null no retorno do PATCH. */
  feedback_preview: string | null;
  criada_em: string | null;
  atualizada_em: string | null;
}

/** Corpo do POST /api/tarefas (tarefa manual).
    NOTA: o backend nomeia o contato como `contact_id` e o vínculo como `feedback_id`
    (não `contato_id`/`feedback_item_id`). */
export interface TarefaInput {
  contact_id: string;
  title: string;
  reason?: string | null;
  priority?: TarefaPriority;
  owner?: string | null;
  due_at?: string | null;
  /** Vincula a tarefa a um FeedbackItem da org (ex.: "abordar sobre este NPS"). */
  feedback_id?: string | null;
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

/** Ordenação de GET /api/tarefas:
    'prioridade' (urgente→baixa, depois due_at asc) | 'recente' (created desc) |
    'sla' (due_at asc, nulls por último). */
export type TarefaSort = "prioridade" | "recente" | "sla";

/** Filtros opcionais de GET /api/tarefas (query string; ausentes = sem filtro).
    Todos aplicados em SQL no backend. `contact_id`/`playbook_id` inválidos → 422. */
export interface TarefaFiltro {
  status?: TarefaStatus;
  owner?: string;
  priority?: TarefaPriority;
  contact_id?: string;
  playbook_id?: string;
  sort?: TarefaSort;
  limit?: number;
  offset?: number;
}

/** Corpo do POST /api/tarefas/gerar-de-feedbacks (gerar tarefas em lote a partir
    de feedbacks que ainda não têm tarefa vinculada). Todos opcionais; `undefined`
    (e null/"" via buildQuery não se aplica — vai no corpo) = não filtra aquela coluna.
    Defaults do backend: tipo="churn", sentimento="negativo", action_status=null, limite=50. */
export interface GerarDeFeedbacksInput {
  /** FeedbackItem.type — default "churn". */
  tipo?: string | null;
  /** FeedbackItem.sentiment — default "negativo". */
  sentimento?: string | null;
  /** FeedbackItem.action_status (ex.: "novo") — default null (não filtra). */
  action_status?: FeedbackStatus | null;
  /** Tamanho do lote desta rodada (1..500) — default 50. */
  limite?: number;
}

/** Resposta de POST /api/tarefas/gerar-de-feedbacks. Idempotente: rodar 2x não
    duplica. `tarefas` traz SÓ as CsTask criadas nesta chamada (mesmo shape do GET/POST). */
export interface GerarDeFeedbacksResult {
  /** Quantas tarefas foram criadas nesta rodada. */
  criadas: number;
  /** Feedbacks que casam os filtros mas já tinham tarefa (sinaliza idempotência). */
  ja_existiam: number;
  /** As tarefas criadas nesta chamada (vazio quando criadas=0). */
  tarefas: Tarefa[];
}

// --- Camada 3: Roadmap & Melhorias ("fechar o loop") ------------------------

/** Estágios de uma melhoria no roadmap (funil ideia → entregue). Espelha
    `IMPROVEMENT_STATUSES` do backend. */
export type ImprovementStatus =
  | "ideia"
  | "planejada"
  | "em_andamento"
  | "entregue"
  | "descartada";

/** Esforço estimado de uma melhoria. Sem enum no banco — validado na API. */
export type ImprovementEffort = "P" | "M" | "G" | "XG";

/** Uma melhoria do roadmap, vinculada (opcionalmente) a uma dor (cluster).
 *
 * NOTA de contrato (drift conhecido): o serializer atual do backend
 * (`_improvement_out`) devolve os timestamps com sufixo `_em`
 * (`created_em`/`delivered_em`/`notified_em`), enquanto a spec da Camada 3
 * usa `_at` (`delivered_at`/`notified_at`). Aceitamos AS DUAS formas aqui
 * (ambas opcionais) para a UI funcionar com a API atual e com a da spec; o
 * gate de "fechar o loop" lê `notified_at ?? notified_em`. */
export interface Improvement {
  id: string;
  title: string;
  description: string | null;
  status: ImprovementStatus;
  /** Quantos clientes pediram isso (feedbacks vinculados). */
  feedback_count: number;
  /** Dor de origem (cluster) ou null. */
  cluster_id?: string | null;
  /** Rótulo da dor ligada (vem no roadmap quando há cluster). */
  cluster_label?: string | null;
  effort?: ImprovementEffort | null;
  /** Data-alvo (ISO) exibida no roadmap. */
  target_date?: string | null;
  /** Quando virou "entregue" (ISO). `_at` = spec; `_em` = backend atual. */
  delivered_at?: string | null;
  delivered_em?: string | null;
  /** Quando avisamos os clientes ("você pediu, a gente fez") (ISO). */
  notified_at?: string | null;
  notified_em?: string | null;
  created_at?: string | null;
  created_em?: string | null;
}

/** Item da lista priorizada — GET /api/improvements/roadmap. Estende
    `Improvement` com os campos calculados do score. */
export interface ImprovementRoadmapItem extends Improvement {
  /** feedback_count × max(urgencia_media,1) × (1 + cluster_neg_fraction). */
  priority_score?: number;
  /** Média de urgência (0–100) dos feedbacks vinculados. */
  urgencia_media?: number;
  cluster_neg_fraction?: number;
}

/** Corpo do POST /api/improvements (criar melhoria). */
export interface ImprovementInput {
  title: string;
  description?: string | null;
  effort?: ImprovementEffort | null;
  target_date?: string | null;
  status?: ImprovementStatus;
}

/** Corpo parcial do PATCH /api/improvements/{id}. */
export interface ImprovementPatch {
  title?: string;
  description?: string | null;
  status?: ImprovementStatus;
  effort?: ImprovementEffort | null;
  target_date?: string | null;
  cluster_id?: string | null;
}

/** Um destinatário no preview do "fechar o loop". */
export interface NotifyRecipient {
  contato_id: string;
  contato_nome: string | null;
  contato_whatsapp: string;
  /** Texto que SERIA enviado (só em `would_send`). */
  mensagem?: string;
  /** Por que ficou de fora (só em `skipped`): sem_whatsapp | sem_opt_in | cooldown. */
  reason?: string;
}

/** Resposta de POST /api/improvements/{id}/notify (preview e envio).
    Sem `?confirm=true` é PREVIEW (não envia, não grava). */
export interface NotifyResult {
  improvement_id: string;
  preview: boolean;
  sent: boolean;
  /** Tema mais citado nos feedbacks (personaliza a mensagem) ou null. */
  theme: string | null;
  would_send: NotifyRecipient[];
  skipped: NotifyRecipient[];
  /** Presentes só no envio confirmado. */
  sent_count?: number;
  notified_em?: string | null;
}

// --- Camada de Campanha Win-back: selos, outreach, stats e forms ------------

/** Um selo no catálogo da org (etiqueta colorida da campanha). */
export interface Selo {
  nome: string;
  cor: string;
}

/** Resposta de GET /api/selos — catálogo + uso (nº de contatos por selo). */
export interface SelosResponse {
  catalogo: Selo[];
  /** {"<nome>": <n_contatos_com_o_selo>} — conta TODOS os contatos da org. */
  uso: Record<string, number>;
}

/** Uma abordagem 1:1 registrada no histórico do contato (Contact.profile_data["abordagens"]). */
export interface Abordagem {
  /** Quando foi a abordagem (ISO). */
  at: string;
  /** 'whatsapp' | 'ligacao' | 'email' | 'presencial' | 'outro' (vocabulário aberto). */
  canal: string;
  mensagem: string | null;
  /** Oferta apresentada (ex.: "3 meses grátis"). */
  oferta: string | null;
  status: string | null;
  /** Quem fez a abordagem. */
  por: string | null;
}

/** Corpo do POST /api/contacts/{id}/outreach (registrar uma abordagem). */
export interface OutreachInput {
  canal: string;
  mensagem?: string | null;
  oferta?: string | null;
  status?: string | null;
  por?: string | null;
}

/** Uma etapa do funil da campanha (a contatar → contatado → respondeu → cortesia → reativou). */
export interface CampanhaFunilStep {
  etapa: string;
  count: number;
}

/** Um tema citado pelo universo da campanha (com nº de feedbacks negativos). */
export interface CampanhaInsight {
  tema: string;
  count: number;
  /** Quantos desses feedbacks são de sentimento negativo. */
  neg: number;
}

/** Resposta de GET /api/campanha/stats — painel de monitoramento da win-back. */
export interface CampanhaStats {
  /** Total de contatos churn da org (universo da campanha). */
  universo: number;
  /** Recorte do universo com telefone REAL (alcançáveis no WhatsApp). */
  com_whatsapp: number;
  /** Recorte do universo só-e-mail (phone vazio ou 'nowa-'); com_whatsapp + sem_whatsapp == universo. */
  sem_whatsapp: number;
  /** Contagem do universo por bucket de alcance do validador
      (whatsapp | so_email | fixo | grupo | sem_contato | invalido) — só buckets > 0.
      sum(por_alcance) == universo e por_alcance.whatsapp == com_whatsapp. */
  por_alcance?: Record<string, number>;
  contatados: number;
  responderam: number;
  cortesia: number;
  reativaram: number;
  /** max(0, universo - contatados). */
  faltam: number;
  /** Contagem das abordagens por canal. */
  por_canal: Record<string, number>;
  /** Nº de contatos do universo por selo. */
  por_selo: Record<string, number>;
  /** Etapas do funil com counts (ordem do funil). */
  funil: CampanhaFunilStep[];
  /** Top ~8 temas do universo (count + negativos). */
  insights: CampanhaInsight[];
}

/** Uma linha de resposta de formulário a importar (POST /api/forms/import). */
export interface FormsRow {
  whatsapp?: string | null;
  nome?: string | null;
  email?: string | null;
  nota?: number | null;
  texto?: string | null;
}

/** Resultado de POST /api/forms/import (idempotente por external_id). */
export interface FormsImportResult {
  created: number;
  updated: number;
  skipped: number;
}

/** Uma sugestão de selo de NEGÓCIO proposta pela IA (analisa o cliente; NÃO aplica).
    `nome` é o rótulo do selo; `motivo` é a justificativa curta (vai no tooltip). */
export interface SeloSugestao {
  nome: string;
  motivo: string;
}

/** Resposta de POST /api/contacts/{id}/sugerir-selos — a IA propõe selos a aplicar.
    `sugestoes` pode vir vazia ([]) quando a IA não tem proposta ou está indisponível. */
export interface SugerirSelosResponse {
  sugestoes: SeloSugestao[];
}

/** Helpers tipados da camada de campanha (todos sob o prefixo /api). */
export const campanha = {
  /** Catálogo de selos + uso por contato. */
  listSelos: () => api.get<SelosResponse>("/api/selos"),
  /** Upsert de um selo no catálogo (idempotente por nome; cor atualiza). */
  createSelo: (body: Selo) => api.post<{ catalogo: Selo[] }>("/api/selos", body),
  /** Remove o selo do catálogo E de todos os contatos que o têm. */
  deleteSelo: (nome: string) => api.del(`/api/selos/${encodeURIComponent(nome)}`),
  /** Aplica um selo a um contato (cria no catálogo se for novo). */
  applySelo: (contactId: string, body: { nome: string; cor?: string | null }) =>
    api.post<{ contato_id: string; selos: string[] }>(
      `/api/contacts/${contactId}/selos`,
      body,
    ),
  /** A IA analisa o cliente e PROPÕE selos de negócio (não aplica). Pode devolver
      `{sugestoes: []}` quando não há proposta ou a IA está indisponível. */
  sugerirSelos: (contactId: string) =>
    api.post<SugerirSelosResponse>(`/api/contacts/${contactId}/sugerir-selos`, {}),
  /** Remove o selo daquele contato (não mexe no catálogo). */
  removeSeloFromContact: (contactId: string, nome: string) =>
    api.del(`/api/contacts/${contactId}/selos/${encodeURIComponent(nome)}`),
  /** Registra uma abordagem 1:1 (e marca os feedbacks do contato como abordados). */
  addOutreach: (contactId: string, body: OutreachInput) =>
    api.post<{ abordagem: Abordagem }>(`/api/contacts/${contactId}/outreach`, body),
  /** Histórico de abordagens do contato (mais recente primeiro). */
  listOutreach: (contactId: string) =>
    api.get<Abordagem[]>(`/api/contacts/${contactId}/outreach`),
  /** Painel de monitoramento da campanha. */
  stats: () => api.get<CampanhaStats>("/api/campanha/stats"),
  /** Importa respostas de formulário (a porta; dados reais chegam depois). */
  importForms: (rows: FormsRow[]) =>
    api.post<FormsImportResult>("/api/forms/import", { rows }),
};

// --- WhatsApp da central (envio 1:1, gated por confirmação) ------------------

/** Estados possíveis da sessão WAHA (espelha o backend).
    WORKING = conectado · SCAN_QR_CODE = precisa escanear · STARTING/STOPPED/FAILED
    = transições · null = WAHA desligado/inalcançável. Tipado como `string | null`
    (não union fechada) para tolerar estados novos do WAHA sem quebrar a UI. */
export type WhatsappSessionStatus =
  | "WORKING"
  | "SCAN_QR_CODE"
  | "STARTING"
  | "STOPPED"
  | "FAILED"
  | (string & {})
  | null;

/** Resposta de GET /api/whatsapp/status — saúde do gateway WAHA.
    `conectado` é true só quando a sessão está plenamente ligada ('WORKING');
    WAHA off/erro -> false. `status` é o estado bruto da sessão (ou null se WAHA
    desligado). Não expõe segredos (sem api_key). */
export interface WhatsappStatus {
  conectado: boolean;
  status: WhatsappSessionStatus;
  session: string;
  base_url: string;
}

/** Resposta de GET /api/whatsapp/qr — QR code para parear a sessão.
    `qr` é um data-uri pronto para <img src> ("data:image/png;base64,…") ou null
    (sessão já conectada, ainda iniciando, ou WAHA desligado). `status` acompanha
    o estado da sessão para a UI decidir parar o polling (vira 'WORKING'). */
export interface WhatsappQr {
  qr: string | null;
  status: WhatsappSessionStatus;
}

/** Resposta dos comandos de sessão (start/stop/restart). `ok` indica se o WAHA
    aceitou o comando; `status` é o estado da sessão logo após o comando (ou null). */
export interface WhatsappSessionResult {
  ok: boolean;
  status: WhatsappSessionStatus;
}

/** Corpo do POST /api/contacts/{id}/whatsapp/send (preview e envio).
    `confirm` é injetado pelos helpers (false no preview, true no envio). */
export interface WhatsappSendInput {
  texto: string;
  oferta?: string | null;
  por?: string | null;
}

/** Resposta de PREVIEW (sem confirm): NÃO envia nada, devolve o que SERIA enviado. */
export interface WhatsappSendPreview {
  preview: true;
  para: string;
  /** Telefone é celular BR válido? (validador do backend). */
  tem_whatsapp: boolean;
  /** Dá para enviar 1:1? = não-grupo E (tem_whatsapp OU já recebemos inbound dele).
      É o gate REAL do "Enviar de verdade" (substitui tem_whatsapp no botão). */
  alcancavel: boolean;
  /** Telefone é um JID de grupo/comunidade? Grupo nunca recebe mensagem 1:1. */
  is_grupo: boolean;
  texto: string;
  /** Sessão WAHA conectada agora? — outro gate do "Enviar de verdade". */
  waha_conectado: boolean;
}

/** Resposta de ENVIO confirmado (confirm=true) — só vem quando WAHA conectado + número válido. */
export interface WhatsappSendResult {
  enviado: true;
  para: string;
  texto: string;
  /** A abordagem 1:1 registrada no histórico do contato (canal='whatsapp'). */
  abordagem: Abordagem;
  /** Selos do contato após o envio (inclui 'contatado'). */
  selos: string[];
  channel_msg_id: string | null;
}

/** Um item da lista de conversas (coluna esquerda do painel de chat). */
export interface WhatsappConversation {
  contact_id: string;
  nome: string | null;
  whatsapp: string | null;
  tem_whatsapp: boolean;
  /** Telefone é um JID de grupo/comunidade do WhatsApp? */
  is_grupo: boolean;
  estado: string | null;
  selos: string[];
  total: number;
  ultima_mensagem: string;
  ultima_em: string | null;
  ultima_direction: "inbound" | "outbound";
}

export interface WhatsappConversationsResponse {
  conversations: WhatsappConversation[];
  total: number;
}

/** Uma mensagem da thread (balão). */
export interface WhatsappThreadMsg {
  id: string;
  direction: "inbound" | "outbound";
  body: string;
  at: string | null;
}

/** Thread de um contato: cabeçalho do contato + mensagens cronológicas (asc). */
export interface WhatsappThread {
  contact: {
    id: string;
    nome: string | null;
    whatsapp: string | null;
    tem_whatsapp: boolean;
    /** Dá para enviar 1:1? = não-grupo E (tem_whatsapp OU já recebemos inbound). */
    alcancavel: boolean;
    /** Telefone é um JID de grupo/comunidade do WhatsApp? */
    is_grupo: boolean;
    estado: string | null;
    selos: string[];
    opt_in: boolean;
    /** Operador assumiu a conversa? Quando true, o bot fica pausado p/ este contato. */
    needs_human_handoff: boolean;
  };
  mensagens: WhatsappThreadMsg[];
}

export interface WhatsappImportPreviewMessage {
  direction: "inbound" | "outbound";
  body: string;
  at: string | null;
  already_imported: boolean;
}

export interface WhatsappImportResult {
  preview: boolean;
  imported: boolean;
  chat_id: string | null;
  resolved_phone: string | null;
  found: number;
  new: number;
  already_imported: number;
  messages: WhatsappImportPreviewMessage[];
}

/** Helpers tipados do WhatsApp da central. Envio é GATED:
    `sendPreview` nunca envia; `sendConfirm` só envia com WAHA conectado (409) e
    telefone celular válido (422). */
export const whatsapp = {
  /** Status do gateway WAHA (best-effort; WAHA off -> conectado=false). */
  status: () => api.get<WhatsappStatus>("/api/whatsapp/status"),
  /** QR code para parear a sessão (data-uri ou null). Faça polling enquanto o
      status for 'SCAN_QR_CODE'; pare quando virar 'WORKING'. */
  qr: () => api.get<WhatsappQr>("/api/whatsapp/qr"),
  /** Inicia a sessão do WhatsApp (gera o QR). Idempotente no backend. */
  startSession: () =>
    api.post<WhatsappSessionResult>("/api/whatsapp/session/start", {}),
  /** Desconecta/para a sessão do WhatsApp (desfaz o pareamento). */
  stopSession: () =>
    api.post<WhatsappSessionResult>("/api/whatsapp/session/stop", {}),
  /** Reinicia a sessão (stop+start) — útil quando ela trava em FAILED. */
  restartSession: () =>
    api.post<WhatsappSessionResult>("/api/whatsapp/session/restart", {}),
  /** Lista de conversas (1 por contato com mensagem), ordenada pela última msg desc.
      `excluirGrupos=true` injeta `excluir_grupos=true` e omite contatos classe 'group'. */
  conversations: (search?: string, excluirGrupos?: boolean) =>
    api.get<WhatsappConversationsResponse>(
      `/api/whatsapp/conversations${buildQuery({
        search,
        excluir_grupos: excluirGrupos ? true : undefined,
      })}`,
    ),
  /** Thread cronológica de um contato (balões). */
  thread: (contactId: string) =>
    api.get<WhatsappThread>(`/api/contacts/${contactId}/whatsapp/thread`),
  /** PREVIEW: procura o chat WAHA do contato e informa quantas mensagens seriam
      importadas. NÃO grava nada. */
  importPreview: (contactId: string, limit = 100) =>
    api.post<WhatsappImportResult>(`/api/contacts/${contactId}/whatsapp/import`, {
      limit,
      confirm: false,
    }),
  /** IMPORTAÇÃO REAL: grava no transcript apenas mensagens novas, após preview. */
  importConfirm: (contactId: string, limit = 100) =>
    api.post<WhatsappImportResult>(`/api/contacts/${contactId}/whatsapp/import`, {
      limit,
      confirm: true,
    }),
  /** Liga/desliga o hand-off humano: ativar=true PAUSA o bot p/ este contato (operador
      assume a conversa pelo Chat); false devolve ao fluxo automático. Idempotente. */
  handoff: (contactId: string, ativar: boolean) =>
    api.post<{ contact_id: string; needs_human_handoff: boolean }>(
      `/api/contacts/${contactId}/whatsapp/handoff`,
      { ativar },
    ),
  /** PREVIEW: NÃO envia nada; devolve o que SERIA enviado + se WAHA está conectado. */
  sendPreview: (contactId: string, body: WhatsappSendInput) =>
    api.post<WhatsappSendPreview>(`/api/contacts/${contactId}/whatsapp/send`, {
      ...body,
      confirm: false,
    }),
  /** ENVIO REAL (confirm=true): 409 se WAHA off, 422 se telefone não-celular. */
  sendConfirm: (contactId: string, body: WhatsappSendInput) =>
    api.post<WhatsappSendResult>(`/api/contacts/${contactId}/whatsapp/send`, {
      ...body,
      confirm: true,
    }),
};

/** Helpers tipados dos BOARDS dinâmicos (CRUD + items + board-move). */
export const boards = {
  /** Lista os boards da org (defaults se vazia). */
  list: () => api.get<Board[]>("/api/boards"),
  /** Cria um board (id gerado pelo backend). */
  create: (body: BoardInput) => api.post<Board>("/api/boards", body),
  /** Edita nome e/ou colunas de um board (materializa defaults se necessário). */
  patch: (id: string, body: BoardPatch) => api.patch<Board>(`/api/boards/${id}`, body),
  /** Remove um board (idempotente; pode remover o último — volta aos defaults). */
  remove: (id: string) => api.del(`/api/boards/${id}`),
  /** Cards de cada coluna do board (top ~30 por urgência / ~40 por health, com count
      total). Filtros opcionais (`BoardItemFiltro`) viram query string e são aplicados
      ANTES do agrupamento no backend, então items E counts de cada coluna refletem o
      filtro; campos que não valem para a entidade do board são ignorados sem erro. */
  items: (id: string, filtro?: BoardItemFiltro) =>
    api.get<BoardItems>(`/api/boards/${id}/items${buildQuery(filtro)}`),
  /** Move um card de FEEDBACK: campo=action_status seta status; campo=selo aplica selo. */
  move: (feedbackId: string, body: BoardMoveInput) =>
    api.post<Feedback>(`/api/feedbacks/${feedbackId}/board-move`, body),
  /** Move um card de CLIENTE: campo=selo aplica o selo ao contato (retorna {id, selos}).
      campo=estado|perfil é read-only (vem da API de Clientes) — backend responde 409. */
  moveContato: (contatoId: string, body: ContactBoardMoveInput) =>
    api.post<{ id: string; selos: string[] }>(
      `/api/contacts/${contatoId}/board-move`,
      body,
    ),
  /** Move um card de TAREFA (board entidade='tarefa') trocando o status no drop.
      NÃO há board-move de tarefa: o status muda via PATCH /api/tarefas/{id} (reusa
      `tarefas.patch`). Retorna a Tarefa atualizada (TarefaOut do PATCH). */
  moveTarefa: (tarefaId: string, status: TarefaStatus) =>
    tarefas.patch(tarefaId, { status }),
  /** Move um card de MELHORIA (board entidade='melhoria') trocando o status no drop.
      NÃO há board-move de melhoria: o status muda via PATCH /api/improvements/{id}
      (reusa `melhorias.patch`). Retorna a Improvement atualizada. */
  moveMelhoria: (melhoriaId: string, status: ImprovementStatus) =>
    melhorias.patch(melhoriaId, { status }),
};

/** Helpers tipados de CLIENTES (lista rica + filtros por tipo de cliente). */
export const clientes = {
  /** Lista de clientes contatáveis. Filtros opcionais viram query string. */
  list: (filtro?: ClienteFiltro) =>
    api.get<Cliente[]>(`/api/clientes${buildQuery(filtro)}`),
};

/** Helpers tipados de CONTATOS (a ficha 360 é buscada direto via `api.get`). */
export const contacts = {
  /** Exclui um contato e TODO o seu histórico (irreversível). Backend responde 204. */
  remove: (id: string) => api.del(`/api/contacts/${id}`),
};

/** Helpers tipados de FEEDBACKS (feed + contagens + filtros + ações do Board). */
export const feedbacks = {
  /** Feed paginado de feedbacks. Filtros opcionais viram query string. */
  list: (filtro?: FeedbackFiltro) =>
    api.get<FeedbacksResponse>(`/api/feedbacks${buildQuery(filtro)}`),
  /** Cria um feedback manual (201). Exige contato_id OU (contato_whatsapp + nome). */
  create: (body: FeedbackInput) => api.post<Feedback>("/api/feedbacks", body),
  /** PATCH parcial de um feedback (`FeedbackPatch`): só o que vier no corpo é tocado.
      Retorna o item no formato do feed (já com assignee/team_tag/improvement_id). */
  patch: (id: string, body: FeedbackPatch) =>
    api.patch<Feedback>(`/api/feedbacks/${id}`, body),
  /** ATRIBUIR: seta dono/time do feedback (string vazia → null no backend).
      Envie só os campos que quer mudar; ambos null/"" limpam. */
  atribuir: (id: string, body: { assignee?: string | null; team_tag?: string | null }) =>
    api.patch<Feedback>(`/api/feedbacks/${id}`, body),
  /** VINCULAR MELHORIA: liga o feedback a uma Improvement da org (uuid) — NÃO mexe no
      action_status. `null` DESVINCULA. 404 se a melhoria não existir/for de outra org;
      422 se o uuid for malformado. */
  vincularMelhoria: (id: string, improvementId: string | null) =>
    api.patch<Feedback>(`/api/feedbacks/${id}`, { improvement_id: improvementId }),
  /** CRIAR TAREFA A PARTIR do feedback: POST /api/tarefas com `feedback_id` vinculado.
      Reusa o contrato de `TarefaInput` (contact_id obrigatório; title obrigatório). */
  criarTarefa: (
    body: { contact_id: string; title: string } & Partial<Omit<TarefaInput, "contact_id" | "title">> & {
      feedback_id: string;
    },
  ) => api.post<Tarefa>("/api/tarefas", body),
  /** SUGERIR RESPOSTA (IA): pede um RASCUNHO de resposta a este feedback. Nunca
      envia nada — o operador revisa e dispara manual. Pode lançar ApiError(503)
      quando a feature está desligada/LLM não configurado (a UI esconde o botão);
      404 se o feedback não for da org; 422 se o uuid for inválido. */
  sugerirResposta: (id: string, body?: SugerirRespostaIn) =>
    api.post<SugerirRespostaResult>(`/api/feedbacks/${id}/sugerir-resposta`, body ?? {}),
};

/** Helpers tipados de TAREFAS de CS (fila priorizada + filtros). */
export const tarefas = {
  /** Fila paginada de tarefas. Filtros opcionais viram query string. */
  list: (filtro?: TarefaFiltro) =>
    api.get<TarefasResponse>(`/api/tarefas${buildQuery(filtro)}`),
  /** Cria uma tarefa manual (201). `feedback_id` vincula a um FeedbackItem da org. */
  create: (body: TarefaInput) => api.post<Tarefa>("/api/tarefas", body),
  /** Edição parcial (status/owner/priority/due_at/snoozed_until/notes). */
  patch: (id: string, body: TarefaPatch) =>
    api.patch<Tarefa>(`/api/tarefas/${id}`, body),
  /** Gera tarefas em lote a partir de feedbacks sem tarefa vinculada (201).
      Idempotente: rodar 2x não duplica (feedbacks já tratados caem em `ja_existiam`).
      Corpo todo opcional — usa os defaults do backend (churn/negativo/limite 50). */
  gerarDeFeedbacks: (body?: GerarDeFeedbacksInput) =>
    api.post<GerarDeFeedbacksResult>("/api/tarefas/gerar-de-feedbacks", body ?? {}),
};

/** Helpers tipados das DORES (clusters por significado). */
export const clusters = {
  /** Lista as dores (clusters) da org + métricas. `days`/`sort` viram query string. */
  list: (filtro?: ClustersFiltro) =>
    api.get<ClustersResponse>(`/api/feedbacks/clusters${buildQuery(filtro)}`),
};

/** Helpers tipados das MELHORIAS (roadmap + "puxar dor para o roadmap"). */
export const melhorias = {
  /** Lista as melhorias da org (cada uma com feedback_count). */
  list: () => api.get<Improvement[]>("/api/improvements"),
  /** Roadmap priorizado (por priority_score desc). `status` filtra por estágio. */
  roadmap: (status?: ImprovementStatus) =>
    api.get<ImprovementRoadmapItem[]>(`/api/improvements/roadmap${buildQuery({ status })}`),
  /** Cria uma melhoria avulsa (status nasce 'ideia' por padrão). */
  create: (body: ImprovementInput) =>
    api.post<Improvement>("/api/improvements", body),
  /** Edita parcialmente uma melhoria (status, effort, target_date, cluster_id...). */
  patch: (id: string, body: ImprovementPatch) =>
    api.patch<Improvement>(`/api/improvements/${id}`, body),
  /** "Puxar para o roadmap": cria a melhoria A PARTIR de uma dor (cluster) e
      vincula os feedbacks dela. Idempotente: se a dor já virou melhoria, devolve
      a existente. Retorna o mesmo shape de Improvement (201). */
  fromCluster: (clusterId: string, title?: string) =>
    api.post<Improvement>("/api/improvements/from-cluster", { cluster_id: clusterId, title }),
};

// --- Central de Feedbacks (visão consolidada de acompanhamento) --------------
// Tela-resumo que o Felipe apresenta: NPS + feedbacks por sentimento +
// segmentação (churn × ativos) + lista detalhada de NPS. Três endpoints sob
// /api/central; o backend está sendo feito em paralelo (mesmo contrato abaixo).

/** Bloco de NPS do overview — contagens por bucket + média e sem-resposta. */
export interface CentralNps {
  /** Quantos clientes deram nota (responderam o NPS). */
  deram: number;
  /** Média do NPS (score líquido −100…+100) ou null se ninguém deu nota. */
  media: number | null;
  promotores: number;
  neutros: number;
  detratores: number;
  /** Clientes que receberam mas ainda NÃO deram nota. */
  sem_resposta: number;
}

/** Bloco de feedbacks do overview — total, com texto e quebras por fonte/sentimento. */
export interface CentralFeedbacks {
  total: number;
  /** Quantos feedbacks vieram com texto (não só nota). */
  com_texto: number;
  /** {"whatsapp": n, "app": n, "billing": n, "forms": n, ...} — só fontes > 0. */
  por_fonte: Record<string, number>;
  por_sentimento: {
    positivo: number;
    neutro: number;
    negativo: number;
    /** Sem sentimento classificado (IA não rodou / sem texto). */
    sem: number;
  };
}

/** Bloco de abordagem do overview — quantos contatos foram abordados/responderam. */
export interface CentralAbordagem {
  contatos_total: number;
  abordados: number;
  responderam: number;
  nao_responderam: number;
}

/** Um segmento de acompanhamento (churn ou ativos) — números do funil de contato. */
export interface CentralSegmento {
  /** Rótulo amigável do segmento (ex.: "Cancelaram", "Ativos"). */
  rotulo: string;
  total: number;
  abordados: number;
  responderam: number;
  nao_responderam: number;
}

/** Resposta de GET /api/central/overview — os números-herói da Central. */
export interface CentralOverview {
  nps: CentralNps;
  feedbacks: CentralFeedbacks;
  abordagem: CentralAbordagem;
  segmentos: {
    churn: CentralSegmento;
    ativos: CentralSegmento;
  };
}

/** Bucket textual do NPS de um item da lista detalhada. */
export type CentralNpsBucket = "promoter" | "passive" | "detractor";

/** Uma linha da lista de quem deu NPS — GET /api/central/nps. */
export interface CentralNpsItem {
  contact_id: string;
  nome: string | null;
  telefone: string;
  score: number;
  bucket: CentralNpsBucket;
  /** Motivo/justificativa da nota (texto livre) ou null. */
  motivo: string | null;
  fonte: string;
  /** Quando deu a nota (ISO) ou null. */
  em: string | null;
}

/** Resposta de GET /api/central/nps — média + lista de quem deu nota. */
export interface CentralNpsResponse {
  media: number | null;
  items: CentralNpsItem[];
}

/** Uma linha da lista de feedbacks por sentimento — GET /api/central/feedbacks. */
export interface CentralFeedbackItem {
  contact_id: string;
  nome: string | null;
  fonte: string;
  /** 'positivo' | 'neutro' | 'negativo' | null (IA) — agrupa as colunas. */
  sentimento: string | null;
  /** 'nps' | 'churn' | ... */
  tipo: string;
  /** Motivo/contexto do feedback (texto livre) ou null. */
  texto: string | null;
  abordado: boolean;
  em: string | null;
  /** Estado de ação (novo/em_analise/resolvido/...) ou null. */
  estado: string | null;
}

/** Resposta de GET /api/central/feedbacks — total + itens filtrados. */
export interface CentralFeedbacksResponse {
  total: number;
  items: CentralFeedbackItem[];
}

/** Filtros opcionais de GET /api/central/feedbacks (query string; ausentes = tudo). */
export interface CentralFeedbackFiltro {
  /** 'positivo' | 'neutro' | 'negativo' | 'sem' */
  sentimento?: string;
  /** 'whatsapp' | 'app' | 'billing' | 'forms' | ... */
  fonte?: string;
  abordado?: boolean;
}

/** Item da fila "quem abordar primeiro" (GET /api/central/fila). */
export interface CentralFilaItem {
  contato_id: string;
  nome: string | null;
  phone: string | null;
  opt_in: boolean | null;
  /** Health Score 0-100 (Fase 1). */
  health: number;
  /** Banda do Health Score: 'at_risk' | 'watch' | 'healthy'. */
  banda: string;
  nps: number | null;
  perfil: string | null;
  /** Dias desde o último sinal (ou cadastro); null se desconhecido. */
  dias_silencio: number | null;
  /** Frase curta do porquê (ex.: "em risco (24) · sem contato há 40 dias"). */
  motivo: string;
  /** Score de prioridade (maior = abordar antes). */
  prioridade: number;
}

/** Resposta de GET /api/central/fila — top N + total + contagem por banda. */
export interface CentralFilaResponse {
  itens: CentralFilaItem[];
  total: number;
  por_banda: { at_risk: number; watch: number };
  limit: number;
}

/** Helpers tipados da CENTRAL DE FEEDBACKS (visão consolidada). */
export const central = {
  /** Números-herói: NPS + feedbacks + abordagem + segmentos (churn/ativos). */
  overview: () => api.get<CentralOverview>("/api/central/overview"),
  /** Lista detalhada de quem deu NPS (nome, nota, bucket, motivo). */
  nps: () => api.get<CentralNpsResponse>("/api/central/nps"),
  /** Fila "quem abordar primeiro": contatos em risco × silêncio, não-abordados. */
  fila: (limit?: number) =>
    api.get<CentralFilaResponse>(
      `/api/central/fila${buildQuery(limit != null ? { limit } : undefined)}`,
    ),
  /** Feedbacks por sentimento + fonte. Filtros opcionais viram query string. */
  feedbacks: (filtro?: CentralFeedbackFiltro) =>
    api.get<CentralFeedbacksResponse>(`/api/central/feedbacks${buildQuery(filtro)}`),
};

// --- Vocabulários customizáveis por org (Configurações) ---------------------
// O backend serve os DEFAULTS do produto somados aos itens custom que a org criou
// (mesmo shape para os três grupos). Cada lista é uma sequência de {key,label}; só
// `action_statuses` carrega `cor` (usada nas pílulas/badges de status). A tela de
// Configurações lê tudo daqui (GET) e grava SÓ os custom de cada lista (PUT).

/** Um item de vocabulário. `cor` só vem/é aceita em `action_statuses` (status). */
export interface ConfigItem {
  key: string;
  label: string;
  /** Cor da pílula (hex, ex.: "#6366f1") — só em action_statuses. */
  cor?: string;
}

/** Resposta de GET /api/config — defaults do produto + custom da org, por lista.
    São SEMPRE as listas EFETIVAS (já mescladas); a UI não recebe a separação. */
export interface ConfigResponse {
  /** Estados do fluxo de ação sobre um feedback (com cor). */
  action_statuses: ConfigItem[];
  /** Tipos de feedback (nps, churn, bug, …). */
  feedback_types: ConfigItem[];
  /** Origens/fontes de feedback (whatsapp, manual, …). */
  feedback_origins: ConfigItem[];
}

/** Corpo do PUT /api/config — envie SÓ os CUSTOMIZADOS de cada lista.
    Campo AUSENTE = não mexe naquela lista; `[]` = limpa os custom dela.
    Colidir uma `key` custom com a de um default → 422 (tratado na UI). */
export interface ConfigUpdate {
  action_statuses?: ConfigItem[];
  feedback_types?: ConfigItem[];
  feedback_origins?: ConfigItem[];
}

/** Helpers tipados das CONFIGURAÇÕES (vocabulários customizáveis da org). */
export const config = {
  /** Listas efetivas (defaults + custom da org) dos três vocabulários. */
  get: () => api.get<ConfigResponse>("/api/config"),
  /** Salva SÓ os customizados (por lista). Retorna as listas efetivas resultantes.
      Pode lançar ApiError(422) em caso de colisão de key com um default. */
  update: (body: ConfigUpdate) => api.put<ConfigResponse>("/api/config", body),
};

// --- Auth do OPERADOR (login por cookie httpOnly via BFF) -------------------
// O JWT nunca chega ao JS: o BFF (`app/api/[...path]/route.ts`) grava/lê o
// cookie `escuta_session` (httpOnly). Aqui só falamos os contratos públicos.

/** Corpo do POST /api/auth/login (usuário + senha do operador). */
export interface LoginInput {
  user: string;
  password: string;
}

/** Resposta do login VIA BFF — o token NÃO volta ao browser (fica no cookie);
    o BFF responde só `{ok, user}`. (O FastAPI por baixo devolve `{token,...}`,
    mas isso não cruza para o cliente.) */
export interface LoginResult {
  ok: true;
  user: string;
}

/** Resposta de GET /api/auth/me — identidade do operador logado. */
export interface MeResult {
  user: string;
  /** `exp` do token corrente (unix seconds). */
  exp: number;
}

/** Helpers tipados de AUTH. Erros propagam como `ApiError`:
    401 = credenciais inválidas / sessão ausente; 503 = login não configurado. */
export const auth = {
  /** Faz login. Em 200 o cookie httpOnly já está setado pelo BFF. */
  login: (body: LoginInput) => api.post<LoginResult>("/api/auth/login", body),
  /** Encerra a sessão (BFF apaga o cookie). Idempotente. */
  logout: () => api.post<{ ok: true }>("/api/auth/logout", {}),
  /** Quem está logado (valida o JWT no FastAPI). 401 se sessão ausente/expirada. */
  me: () => api.get<MeResult>("/api/auth/me"),
};
