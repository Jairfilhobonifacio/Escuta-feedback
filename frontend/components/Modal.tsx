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
    // lembra quem tinha o foco p/ devolvê-lo ao fechar (acabamento de acessibilidade)
    const prevFocus = document.activeElement as HTMLElement | null;
    // foca o primeiro campo editável; se não houver, cai no primeiro botão —
    // evita abrir já com um botão destrutivo em foco
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
      "input, select, textarea, button",
    );
    const firstField = panelRef.current?.querySelector<HTMLElement>(
      "input, select, textarea",
    );
    (firstField ?? focusables?.[0])?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      // devolve o foco ao elemento que abriu o modal (se ainda existir no DOM)
      if (prevFocus && document.contains(prevFocus)) prevFocus.focus();
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
