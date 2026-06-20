// Helpers de FORMATAÇÃO para EXIBIÇÃO (credibilidade do painel):
//  - feedbackText(): traduz códigos de máquina (USER_CANCEL, PAYMENT_FAILED…)
//    para PT legível, e humaniza qualquer CÓDIGO_EM_CAIXA_ALTA desconhecido.
//  - maskPhone(): mascara o telefone para LISTAS em massa (privacidade/PII),
//    preservando DDI+DDD e os 4 últimos dígitos. Na FICHA do contato use o
//    telefone completo (o operador precisa contatar 1:1).

/** Códigos de motivo conhecidos (billing/churn da Bizzu) → rótulo humano em PT.
    Chaves em CAIXA_ALTA, como chegam no campo `text` dos feedbacks de cobrança. */
const FEEDBACK_CODE_LABELS: Record<string, string> = {
  USER_CANCEL: "Cancelou",
  PAYMENT_FAILED: "Falha no pagamento",
  GUARANTEE_REFUND: "Reembolso na garantia",
  // Variações/irmãos plausíveis do mesmo domínio — caem no rótulo certo se
  // aparecerem; os demais desconhecidos ainda são humanizados pelo fallback.
  PAYMENT_REFUSED: "Pagamento recusado",
  PAYMENT_REFUND: "Reembolso",
  SUBSCRIPTION_CANCELLED: "Assinatura cancelada",
  SUBSCRIPTION_CANCELED: "Assinatura cancelada",
  CARD_DECLINED: "Cartão recusado",
  CHARGEBACK: "Chargeback",
  TRIAL_EXPIRED: "Teste expirado",
  TRIAL_ENDED: "Teste encerrado",
  USER_REQUEST: "A pedido do cliente",
};

/** Um "código de máquina" é uma palavra única em CAIXA_ALTA com underscores/
    dígitos e sem espaços (ex.: USER_CANCEL, PAYMENT_FAILED_2). Texto normal de
    cliente (que tem espaços, acentos ou minúsculas) NÃO casa e passa intacto. */
function isMachineCode(s: string): boolean {
  return /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/.test(s) || /^[A-Z][A-Z0-9]{2,}$/.test(s);
}

/** Humaniza um código CAIXA_ALTA_COM_UNDERSCORE → Title Case sem underscore
    (ex.: PLAN_DOWNGRADE → "Plan Downgrade"). */
function humanizeCode(code: string): string {
  return code
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Texto de feedback pronto para exibir:
 *  - null / "" / só espaços → "" (quem chama decide o placeholder).
 *  - código conhecido (USER_CANCEL…) → rótulo PT do mapa.
 *  - código desconhecido em CAIXA_ALTA → Title Case sem underscore.
 *  - qualquer outro texto (fala do cliente) → intacto (apenas trim das bordas).
 */
export function feedbackText(raw: string | null): string {
  if (raw == null) return "";
  const t = raw.trim();
  if (!t) return "";
  const mapped = FEEDBACK_CODE_LABELS[t];
  if (mapped) return mapped;
  if (isMachineCode(t)) return humanizeCode(t);
  return t;
}

/** Motivos de churn/cancelamento (snapshot partner.subscription.cancellationReason
    da API de Clientes da Bizzu) → rótulo humano em PT. Chaves em CAIXA_ALTA, como
    chegam no campo `cancellationReason`. Reusa o vocabulário de FEEDBACK_CODE_LABELS
    e acrescenta os motivos próprios de cancelamento. */
const CHURN_REASON_LABELS: Record<string, string> = {
  GUARANTEE_REFUND: "Reembolso na garantia",
  USER_CANCEL: "Cancelou",
  PAYMENT_FAILED: "Falha no pagamento",
  USER_REQUEST: "A pedido do cliente",
  SUBSCRIPTION_CANCELLED: "Assinatura cancelada",
  SUBSCRIPTION_CANCELED: "Assinatura cancelada",
  PAYMENT_REFUSED: "Pagamento recusado",
  PAYMENT_REFUND: "Reembolso",
  CARD_DECLINED: "Cartão recusado",
  CHARGEBACK: "Chargeback",
  TRIAL_EXPIRED: "Teste expirado",
  TRIAL_ENDED: "Teste encerrado",
  INVOLUNTARY: "Involuntário",
  PRICE: "Preço",
  MISSING_FEATURES: "Faltou recurso",
  NO_LONGER_NEEDED: "Não precisa mais",
};

/**
 * Motivo de churn pronto para exibir (card "Perfil & assinatura" e timeline):
 *  - null / "" / só espaços → "" (quem chama decide o placeholder).
 *  - código conhecido (GUARANTEE_REFUND…) → rótulo PT do mapa.
 *  - código desconhecido em CAIXA_ALTA → Title Case sem underscore (fallback).
 *  - qualquer outro texto (já legível) → intacto (apenas trim das bordas).
 */
export function churnReasonLabel(raw: string | null | undefined): string {
  if (raw == null) return "";
  const t = raw.trim();
  if (!t) return "";
  const mapped = CHURN_REASON_LABELS[t.toUpperCase()];
  if (mapped) return mapped;
  if (isMachineCode(t)) return humanizeCode(t);
  return t;
}

/** Perfis de cliente derivados pela Bizzu (campo `profile` do snapshot partner)
    → rótulo humano em PT. Os valores reais vêm de /api/clientes:
    ativo_*, churn_*, cortesia, vai_expirar, indefinido. */
const PERFIL_LABELS: Record<string, string> = {
  ativo_promotor: "Ativo promotor",
  ativo_em_risco: "Ativo em risco",
  ativo_passivo: "Ativo passivo",
  ativo_recente: "Ativo recente",
  ativo_silencioso: "Ativo silencioso",
  churn_rapido: "Churn rápido",
  churn_pos_uso: "Churn pós-uso",
  churn_involuntario: "Churn involuntário",
  churn_outro: "Outro churn",
  vai_expirar: "Vai expirar",
  cortesia: "Cortesia",
  indefinido: "Indefinido",
};

/**
 * Perfil do cliente pronto para exibir:
 *  - null / "" → "" (quem chama decide o placeholder).
 *  - perfil conhecido (churn_rapido…) → rótulo PT do mapa.
 *  - qualquer outro snake_case → Title Case (1ª palavra capitalizada, sem '_').
 */
export function perfilLabel(raw: string | null | undefined): string {
  if (raw == null) return "";
  const t = raw.trim();
  if (!t) return "";
  const mapped = PERFIL_LABELS[t.toLowerCase()];
  if (mapped) return mapped;
  const spaced = t.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Mascara um telefone para LISTAS em massa (não vaza o número inteiro em prints).
 * Preserva o que ajuda a reconhecer/segmentar (DDI + DDD) e os 4 últimos dígitos.
 *   "5585999058955" → "55 85 •••• 8955"
 *   "85999058955"   → "85 •••• 8955"
 *   "999058955"     → "•••• 8955"
 * Placeholders sem número real (ex.: "nowa-<uuid>" do churn só-e-mail) e valores
 * vazios/curtos NÃO são telefones → vira "sem WhatsApp" / "" (não estraga o dado).
 * Na FICHA do contato, mostre o telefone completo (contato 1:1).
 */
export function maskPhone(phone: string | null | undefined): string {
  if (phone == null) return "";
  const raw = phone.trim();
  if (!raw) return "";

  // Placeholder de contato só-e-mail (o sync grava "nowa-…" quando não há celular).
  if (/^nowa-/i.test(raw)) return "sem WhatsApp";

  const digits = raw.replace(/\D/g, "");
  // Sem dígitos suficientes para mascarar com sentido (fixo curto/ruído): esconde.
  if (digits.length < 4) return "••••";

  const last4 = digits.slice(-4);
  const rest = digits.slice(0, -4);

  // Número de celular BR típico: 55 (DDI) + 2 (DDD) + 9 dígitos = 13.
  if (rest.length >= 4) {
    // DDI BR (55) + DDD → "55 85 •••• 8955".
    const ddi = rest.slice(0, 2);
    const ddd = rest.slice(2, 4);
    return `${ddi} ${ddd} •••• ${last4}`;
  }
  if (rest.length >= 2) {
    // Só DDD (sem DDI) → "85 •••• 8955".
    return `${rest.slice(0, 2)} •••• ${last4}`;
  }
  // Pouco contexto: mostra só o final mascarado.
  return `•••• ${last4}`;
}
