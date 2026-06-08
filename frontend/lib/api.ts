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
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
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
