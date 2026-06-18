/* Templates de mensagem para abordagem 1:1 (win-back / churn) no WhatsApp.
   Placeholders: {nome} = primeiro nome do cliente · {seu_nome} = quem envia.
   Os default vivem no código; o operador pode salvar os seus (localStorage) — CRUD leve.

   IMPORTANTE: emojis e travessões usam escapes Unicode (\u{...}) em vez de literais.
   O bundler corrompia os emojis literais (surrogate pairs viravam "�" no runtime);
   em ASCII o source fica imune e o JS materializa o caractere certo. */

export type MsgTemplate = { id: string; label: string; body: string };

const WAVE = "\u{1F44B}"; // mao acenando
const MIC = "\u{1F399}\u{FE0F}"; // microfone
const HEART = "\u{1F499}"; // coracao azul
const DASH = "\u{2014}"; // travessao (em-dash)
const BULLET = "\u{2022}"; // bullet

export const DEFAULT_TEMPLATES: MsgTemplate[] = [
  {
    id: "principal",
    label: "Churn — principal (recomendada)",
    body: `Oi {nome}, tudo bem? Aqui é o {seu_nome}, da Bizzu ${WAVE}

Vi que você cancelou e não vim te oferecer nada ${DASH} vim te ouvir, de verdade. Entender por que você saiu é o que faz a gente melhorar pra quem fica.

Posso te perguntar 2 coisinhas?
${BULLET} O que pesou pra você decidir cancelar?
${BULLET} Tem algo que faria você voltar a estudar com a gente?

Responde do jeito que for mais fácil: texto ou áudio ${MIC}. E se você topar, a gente marca uma call rápida (uns 10 min) no seu horário.

Tua resposta vai direto pra quem constrói a Bizzu. Valeu demais ${HEART}`,
  },
  {
    id: "curta",
    label: "Churn — curta (1º contato)",
    body: `Oi {nome}! ${WAVE} aqui é o {seu_nome}, da Bizzu.

Vi que você cancelou e queria entender, sem rodeio: o que te fez sair? pode ser 100% sincero ${DASH} é assim que a gente melhora.

(se for mais fácil, manda um áudio ${MIC}; e se topar, marco uma call rapidinha pra te ouvir)`,
  },
  {
    id: "cedo",
    label: "Churn — cancelou cedo",
    body: `Oi {nome}! ${WAVE} aqui é o {seu_nome}, da Bizzu. Vi que você testou a Bizzu e acabou cancelando logo no comecinho ${DASH} e fiquei curioso (de boa): o que faltou pra fazer sentido pra você de cara? Qualquer crítica ajuda demais. Pode ser texto ou áudio ${MIC}, e se quiser a gente troca uma ideia rápida numa call.`,
  },
  {
    id: "uso",
    label: "Churn — usou e parou",
    body: `Oi {nome}! ${WAVE} aqui é o {seu_nome}, da Bizzu. Você ficou um tempo estudando com a gente e acabou saindo ${DASH} queria muito entender o que mudou. O que pesou na decisão de parar? e tem algo que faria você voltar? Me conta do seu jeito (texto ou áudio ${MIC}); se topar, marco uma call rápida pra te ouvir melhor ${HEART}`,
  },
  {
    id: "oferta",
    label: "Win-back \u{2014} oferta (responder form)",
    body: `Oi {nome}! ${WAVE} aqui é o {seu_nome}, da Bizzu.

A gente sentiu sua falta por aqui ${DASH} e quer muito te ouvir pra melhorar. Topa responder um formulário rapidinho contando o que te fez sair? São 2 minutinhos: {form_url}

E como agradecimento, separei pra você: {oferta} ${HEART}

Qualquer dúvida é só me chamar por aqui. Valeu demais!`,
  },
  {
    id: "branco",
    label: "Em branco (escrever do zero)",
    body: ``,
  },
];

const LS_KEY = "escuta_msg_templates_v1";
const LS_SENDER = "escuta_sender_name";
const LS_OFERTA = "escuta_campanha_oferta";
const LS_FORM_URL = "escuta_campanha_form_url";

/** Default (código) + customizados (localStorage). */
export function loadTemplates(): MsgTemplate[] {
  if (typeof window === "undefined") return DEFAULT_TEMPLATES;
  try {
    const custom = JSON.parse(localStorage.getItem(LS_KEY) || "[]") as MsgTemplate[];
    return [...DEFAULT_TEMPLATES, ...custom.filter((t) => t && t.id && t.label)];
  } catch {
    return DEFAULT_TEMPLATES;
  }
}

/** Persiste só os customizados (id começa com "u"). */
export function saveCustomTemplates(all: MsgTemplate[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(LS_KEY, JSON.stringify(all.filter((t) => isCustom(t.id))));
}

export function isCustom(id: string): boolean {
  return id.startsWith("u");
}

export function loadSenderName(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(LS_SENDER) || "";
}

export function saveSenderName(name: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(LS_SENDER, name);
}

/** Oferta da campanha win-back (ex.: "3 meses grátis"), lembrada entre abordagens. */
export function loadOferta(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(LS_OFERTA) || "";
}

export function saveOferta(oferta: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(LS_OFERTA, oferta);
}

/** Link do formulário da campanha, lembrado entre abordagens. */
export function loadFormUrl(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(LS_FORM_URL) || "";
}

export function saveFormUrl(url: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(LS_FORM_URL, url);
}

/** Substitui {nome}/{seu_nome}/{oferta}/{form_url} e limpa lacunas quando vazio. */
export function fillTemplate(
  body: string,
  vars: {
    nome?: string | null;
    seuNome?: string | null;
    oferta?: string | null;
    formUrl?: string | null;
  },
): string {
  const primeiro = (vars.nome || "").trim().split(/\s+/)[0] || "";
  const seu = (vars.seuNome || "").trim();
  const oferta = (vars.oferta || "").trim();
  const formUrl = (vars.formUrl || "").trim();

  let out = body;
  // Lacunas de {oferta}/{form_url} vazios: quando o valor não veio, removemos o
  // token JUNTO do conector ": " que o antecede (ex.: "São 2 minutinhos: {form_url}"
  // -> "São 2 minutinhos."). Feito ANTES da substituição, sobre o token literal, é
  // mais robusto do que caçar dois-pontos órfãos no texto já preenchido.
  if (!oferta) out = out.replace(/[ \t]*:?[ \t]*\{oferta\}/g, "");
  if (!formUrl) out = out.replace(/[ \t]*:?[ \t]*\{form_url\}/g, "");

  out = out
    .replaceAll("{nome}", primeiro)
    .replaceAll("{seu_nome}", seu)
    .replaceAll("{oferta}", oferta)
    .replaceAll("{form_url}", formUrl);
  // sem nome do cliente: "Oi , " -> "Oi, " · "Oi ! " -> "Oi! "
  out = out.replace(/Oi , /g, "Oi, ").replace(/Oi ! /g, "Oi! ");
  // sem o nome de quem envia: "aqui é o , da" -> "aqui é da"
  out = out.replace(/aqui é o , da/g, "aqui é da");
  // colapsa espaços duplos e 3+ quebras de linha sobrando após a limpeza.
  out = out.replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n");
  return out;
}

/** Link wa.me com o texto já codificado (só dígitos no telefone). */
export function waLink(phone: string | null | undefined, text: string): string {
  const digits = (phone || "").replace(/\D/g, "");
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}
