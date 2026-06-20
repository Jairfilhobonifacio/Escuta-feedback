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
