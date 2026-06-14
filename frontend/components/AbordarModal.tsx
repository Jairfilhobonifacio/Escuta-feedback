"use client";

import { useId, useState } from "react";
import Avatar from "@/components/Avatar";
import Modal from "@/components/Modal";
import {
  fillTemplate,
  isCustom,
  loadSenderName,
  loadTemplates,
  saveCustomTemplates,
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
}: {
  target: AbordarTarget;
  onClose: () => void;
  /** Persiste "abordado=true". Chamado ao abrir o WhatsApp se a marcação estiver ligada.
      Se ausente, o modal só compõe/abre a conversa (sem persistir nada). */
  onMarcarAbordado?: () => void | Promise<void>;
}) {
  const titleId = useId();
  const [templates, setTemplates] = useState<MsgTemplate[]>(() => loadTemplates());
  const [tplId, setTplId] = useState(templates[0]?.id ?? "principal");
  const [seuNome, setSeuNome] = useState(() => loadSenderName());
  const [msg, setMsg] = useState(() =>
    fillTemplate(templates[0]?.body ?? "", { nome: target.contato_nome, seuNome: loadSenderName() }),
  );
  const [copied, setCopied] = useState(false);
  const [marcar, setMarcar] = useState(!target.abordado);

  const podeMarcar = !!onMarcarAbordado && !target.abordado;
  const phoneDigits = (target.contato_whatsapp || "").replace(/\D/g, "");
  const semWhats = phoneDigits.length < 8;

  function pickTemplate(id: string) {
    setTplId(id);
    const t = templates.find((x) => x.id === id);
    setMsg(fillTemplate(t?.body ?? "", { nome: target.contato_nome, seuNome }));
  }

  function onSeuNome(v: string) {
    setSeuNome(v);
    saveSenderName(v);
    const t = templates.find((x) => x.id === tplId);
    setMsg(fillTemplate(t?.body ?? "", { nome: target.contato_nome, seuNome: v }));
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

        <div className="field">
          <label htmlFor={`${titleId}-msg`}>Mensagem (edite à vontade)</label>
          <textarea
            id={`${titleId}-msg`}
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            style={{ minHeight: 184 }}
          />
          <div className="abordar-tpl-actions">
            <button type="button" className="btn ghost sm" onClick={salvarComoTemplate}>
              ＋ Salvar como modelo
            </button>
            {isCustom(tplId) && (
              <button type="button" className="btn ghost sm" onClick={excluirTemplate}>
                Excluir modelo
              </button>
            )}
            <button type="button" className="btn ghost sm" onClick={copiar}>
              {copied ? "Copiado ✓" : "Copiar"}
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
