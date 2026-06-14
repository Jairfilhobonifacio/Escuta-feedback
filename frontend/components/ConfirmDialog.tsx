"use client";

import { useId, useState } from "react";
import Modal from "@/components/Modal";

/* Diálogo de confirmação genérico (ação destrutiva). Extraído de
   app/feedbacks/page.tsx e generalizado: a lógica de exclusão vem por `onConfirm`
   (async), então serve tanto p/ excluir feedback quanto p/ excluir um playbook.
   A tela Feedbacks passa um onConfirm que chama api.del(/api/feedbacks/{id}) —
   comportamento idêntico ao anterior. */

export default function ConfirmDialog({
  title,
  message,
  quote,
  confirmLabel = "Confirmar",
  confirmingLabel = "Processando…",
  onCancel,
  onConfirm,
}: {
  title: string;
  message: React.ReactNode;
  quote?: string | null;
  confirmLabel?: string;
  confirmingLabel?: string;
  onCancel: () => void;
  /** Executa a ação destrutiva. Se lançar, o erro é exibido e o diálogo permanece. */
  onConfirm: () => Promise<void>;
}) {
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <Modal title={title} onClose={onCancel} labelledById={titleId}>
      <div className="modal-body">
        <p className="confirm-text">{message}</p>
        {quote && <blockquote className="confirm-quote">“{quote}”</blockquote>}
        {error && <div className="flash err" style={{ marginBottom: 0 }}>{error}</div>}
      </div>
      <div className="modal-foot">
        <button type="button" className="btn ghost" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
        <button type="button" className="btn danger" onClick={confirm} disabled={busy}>
          {busy ? confirmingLabel : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
