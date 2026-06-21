"use client";

import { useId, useState } from "react";
import { Sparkles } from "lucide-react";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import { ApiError, campanha, feedbacks as feedbacksApi } from "@/lib/api";
import {
  fillTemplate,
  isCustom,
  loadFormUrl,
  loadOferta,
  loadSenderName,
  loadTemplates,
  saveCustomTemplates,
  saveFormUrl,
  saveOferta,
  saveSenderName,
  waLink,
  type MsgTemplate,
} from "@/lib/templates";

/* Abordagem por WhatsApp (compor mensagem a partir de modelos + abrir wa.me +
   opcionalmente marcar como abordado). Extraído de app/feedbacks/page.tsx.

   Generalizado: depende só de um alvo mínimo (`AbordarTarget`) e de um callback
   opcional `onMarcarAbordado` que persiste a marcação. A tela Feedbacks passa o
   Feedback (que satisfaz AbordarTarget) + um onMarcarAbordado que faz o PATCH no
   feedback — comportamento idêntico ao anterior. A fila de Tarefas reusa o mesmo
   modal com um objeto adaptador {contato_id, contato_nome, contato_whatsapp, abordado:false}. */

export interface AbordarTarget {
  contato_id: string | null;
  contato_nome: string | null;
  contato_whatsapp: string | null;
  abordado: boolean;
}

/** Balãozinho de chat (mesmo traço do ícone "Feedbacks" da sidebar). */
export const waIcon = (
  <svg
    viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
    strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden
  >
    <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
  </svg>
);

export default function AbordarModal({
  target,
  onClose,
  onMarcarAbordado,
  feedbackId,
}: {
  target: AbordarTarget;
  onClose: () => void;
  /** Persiste "abordado=true". Chamado ao abrir o WhatsApp se a marcação estiver ligada.
      Se ausente, o modal só compõe/abre a conversa (sem persistir nada). */
  onMarcarAbordado?: () => void | Promise<void>;
  /** Id do feedback que originou a abordagem. Quando presente E a feature de IA
      estiver ligada, mostra o botão "Sugerir resposta" (rascunho editável). */
  feedbackId?: string;
}) {
  const titleId = useId();
  const [templates, setTemplates] = useState<MsgTemplate[]>(() => loadTemplates());
  const [tplId, setTplId] = useState(templates[0]?.id ?? "principal");
  const [seuNome, setSeuNome] = useState(() => loadSenderName());
  const [oferta, setOferta] = useState(() => loadOferta());
  const [formUrl, setFormUrl] = useState(() => loadFormUrl());
  const [msg, setMsg] = useState(() =>
    fillTemplate(templates[0]?.body ?? "", {
      nome: target.contato_nome,
      seuNome: loadSenderName(),
      oferta: loadOferta(),
      formUrl: loadFormUrl(),
    }),
  );
  const [copied, setCopied] = useState(false);
  const [marcar, setMarcar] = useState(!target.abordado);

  // ----- Sugestão de resposta por IA (rascunho — NUNCA envia) ----------------
  // sugerindo: requisição em voo. sugestaoOff: a API respondeu 503 (feature
  // desligada/LLM off) → escondemos o botão de vez. fromAi: o último rascunho
  // veio do modelo (banner reforça "revise"). sugFlash: erro de rede/transitório.
  const [sugerindo, setSugerindo] = useState(false);
  const [sugestaoOff, setSugestaoOff] = useState(false);
  const [fromAi, setFromAi] = useState(false);
  const [sugFlash, setSugFlash] = useState<string | null>(null);

  const podeSugerir = !!feedbackId && !sugestaoOff;

  /** Pede um rascunho à IA e PREENCHE o textarea (editável — o operador revisa
      antes de abrir o WhatsApp). 503 = feature off → esconde o botão. */
  async function sugerirResposta() {
    if (!feedbackId || sugerindo) return;
    setSugerindo(true);
    setSugFlash(null);
    try {
      const out = await feedbacksApi.sugerirResposta(feedbackId, {});
      setMsg(out.rascunho);
      setFromAi(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setSugestaoOff(true); // feature desligada — some o botão de forma limpa
      } else {
        setSugFlash("Não consegui sugerir agora. Tente de novo em instantes.");
      }
    } finally {
      setSugerindo(false);
    }
  }

  const podeMarcar = !!onMarcarAbordado && !target.abordado;
  const phoneDigits = (target.contato_whatsapp || "").replace(/\D/g, "");
  const semWhats = phoneDigits.length < 8;

  /** Recompõe a mensagem com o template atual e os valores informados. */
  function recompose(over: {
    id?: string;
    seuNome?: string;
    oferta?: string;
    formUrl?: string;
  }) {
    const id = over.id ?? tplId;
    const t = templates.find((x) => x.id === id);
    setMsg(
      fillTemplate(t?.body ?? "", {
        nome: target.contato_nome,
        seuNome: over.seuNome ?? seuNome,
        oferta: over.oferta ?? oferta,
        formUrl: over.formUrl ?? formUrl,
      }),
    );
  }

  function pickTemplate(id: string) {
    setTplId(id);
    recompose({ id });
  }

  function onSeuNome(v: string) {
    setSeuNome(v);
    saveSenderName(v);
    recompose({ seuNome: v });
  }

  function onOferta(v: string) {
    setOferta(v);
    saveOferta(v);
    recompose({ oferta: v });
  }

  function onFormUrl(v: string) {
    setFormUrl(v);
    saveFormUrl(v);
    recompose({ formUrl: v });
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(msg);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard indisponível — ignora */
    }
  }

  function salvarComoTemplate() {
    const label = window.prompt("Nome do novo modelo:");
    if (!label || !label.trim()) return;
    const novo: MsgTemplate = { id: "u" + Date.now(), label: label.trim(), body: msg };
    const next = [...templates, novo];
    setTemplates(next);
    saveCustomTemplates(next);
    setTplId(novo.id);
  }

  function excluirTemplate() {
    if (!isCustom(tplId)) return;
    const next = templates.filter((t) => t.id !== tplId);
    setTemplates(next);
    saveCustomTemplates(next);
    pickTemplate(next[0]?.id ?? "principal");
  }

  function onOpenWhats() {
    if (marcar && podeMarcar) onMarcarAbordado?.();
    // Registra o toque no histórico da campanha (best-effort — não bloqueia o
    // abrir do WhatsApp nem trava o fluxo se a API estiver fora). O endpoint já
    // marca abordado=true nos feedbacks do contato; aqui guardamos o que foi dito.
    if (target.contato_id) {
      campanha
        .addOutreach(target.contato_id, {
          canal: "whatsapp",
          mensagem: msg,
          oferta: oferta.trim() || null,
        })
        .catch(() => {
          /* histórico é enriquecedor, nunca ponto de falha */
        });
    }
    onClose();
  }

  return (
    <Modal title="Abordar no WhatsApp" onClose={onClose} labelledById={titleId}>
      <div className="modal-body">
        <div className="abordar-who">
          <Avatar name={target.contato_nome} seed={target.contato_id ?? target.contato_whatsapp} size={40} />
          <div>
            <div className="abordar-name">{target.contato_nome || "sem nome"}</div>
            <div className="mono dim" style={{ fontSize: 12.5 }}>
              {target.contato_whatsapp || "sem WhatsApp"}
            </div>
          </div>
        </div>

        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-tpl`}>Modelo</label>
            <select id={`${titleId}-tpl`} value={tplId} onChange={(e) => pickTemplate(e.target.value)}>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-sender`}>Seu nome (assina a mensagem)</label>
            <input
              id={`${titleId}-sender`}
              value={seuNome}
              onChange={(e) => onSeuNome(e.target.value)}
              placeholder="ex.: Jair"
            />
          </div>
        </div>

        <div className="form-row-2">
          <div className="field">
            <label htmlFor={`${titleId}-oferta`}>Oferta {"{oferta}"}</label>
            <input
              id={`${titleId}-oferta`}
              value={oferta}
              onChange={(e) => onOferta(e.target.value)}
              placeholder="ex.: 3 meses grátis"
            />
          </div>
          <div className="field">
            <label htmlFor={`${titleId}-form`}>Link do formulário {"{form_url}"}</label>
            <input
              id={`${titleId}-form`}
              value={formUrl}
              onChange={(e) => onFormUrl(e.target.value)}
              placeholder="ex.: https://forms.gle/…"
            />
          </div>
        </div>

        <div className="field">
          <label htmlFor={`${titleId}-msg`}>Mensagem (edite à vontade)</label>
          <textarea
            id={`${titleId}-msg`}
            value={msg}
            onChange={(e) => {
              setMsg(e.target.value);
              // editou à mão → não é mais o rascunho cru da IA
              if (fromAi) setFromAi(false);
            }}
            style={{ minHeight: 184 }}
          />
          {fromAi && (
            <div className="abordar-ai-banner" role="status">
              <Sparkles size={13} aria-hidden />
              Rascunho da IA — revise antes de enviar. O envio é sempre manual.
            </div>
          )}
          {sugFlash && (
            <div className="flash err" style={{ marginTop: 8, marginBottom: 0 }}>
              {sugFlash}
            </div>
          )}
          <div className="abordar-tpl-actions">
            <button type="button" className="btn ghost sm" onClick={salvarComoTemplate}>
              ＋ Salvar como modelo
            </button>
            {isCustom(tplId) && (
              <button type="button" className="btn ghost sm" onClick={excluirTemplate}>
                Excluir modelo
              </button>
            )}
            {podeSugerir && (
              <button
                type="button"
                className="btn ghost sm abordar-ai-btn"
                onClick={sugerirResposta}
                disabled={sugerindo}
                title="Gerar um rascunho de resposta com IA (você revisa antes de enviar)"
              >
                <Sparkles size={14} aria-hidden />
                {sugerindo ? "Sugerindo…" : "Sugerir resposta"}
              </button>
            )}
            <button type="button" className="btn ghost sm" onClick={copiar}>
              {copied ? "Copiado!" : "Copiar"}
            </button>
          </div>
        </div>

        {onMarcarAbordado && (
          <label className="check-row">
            <input
              type="checkbox"
              checked={marcar}
              onChange={(e) => setMarcar(e.target.checked)}
              disabled={target.abordado}
            />
            <span>
              {target.abordado ? "Já marcado como abordado" : "Marcar como abordado ao abrir o WhatsApp"}
            </span>
          </label>
        )}

        {semWhats && (
          <div className="flash err" style={{ marginBottom: 0 }}>
            Esse contato não tem um WhatsApp válido para abrir a conversa.
          </div>
        )}
      </div>
      <div className="modal-foot">
        <button type="button" className="btn ghost" onClick={onClose}>Fechar</button>
        {semWhats ? (
          <button type="button" className="btn btn-wa" disabled>{waIcon} Abrir WhatsApp</button>
        ) : (
          <a
            className="btn btn-wa"
            href={waLink(target.contato_whatsapp, msg)}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onOpenWhats}
          >
            {waIcon} Abrir WhatsApp
          </a>
        )}
      </div>
    </Modal>
  );
}
