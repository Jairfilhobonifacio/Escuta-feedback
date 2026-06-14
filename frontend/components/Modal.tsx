"use client";

import { useEffect, useRef } from "react";

/* Modal genérico (Esc para fechar, backdrop clicável, trava o scroll do fundo,
   foco inicial no primeiro campo). Extraído de app/feedbacks/page.tsx para ser
   reusado pelas telas de Fase 2 (Tarefas / Playbooks). Comportamento idêntico. */

export default function Modal({
  title,
  onClose,
  children,
  labelledById,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  labelledById: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // trava o scroll do fundo enquanto o modal está aberto
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // foca o primeiro campo do diálogo
    const first = panelRef.current?.querySelector<HTMLElement>(
      "input, select, textarea, button",
    );
    first?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledById}
        ref={panelRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id={labelledById} className="modal-title">{title}</h2>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Fechar"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
