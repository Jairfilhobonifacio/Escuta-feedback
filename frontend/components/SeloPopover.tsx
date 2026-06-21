"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/* ============================================================================
   SeloPopover — popover ancorado que VIVE NUM PORTAL no <body>.

   Por quê: o antigo popover de selos era um <div position:absolute> irmão do
   gatilho, dentro da célula. Em três lugares isso quebrava (o "+selo bugado"
   do dono, img-2):
     • na tabela de Clientes ele era CORTADO pelo ancestral com overflow
       (.card{overflow:hidden} + .table-wrap{overflow-x:auto}) e ficava ATRÁS
       das linhas seguintes (mesmo z-index, pintura por ordem de DOM) — daí o
       "+selo" fantasma aparecendo no meio da lista;
     • no card do Board e no cabeçalho da ficha, o mesmo empilhamento frágil.

   Solução de raiz: o painel é renderizado via createPortal direto no <body> com
   position:fixed, ancorado ao retângulo do gatilho. Assim ESCAPA de qualquer
   overflow/stacking de ancestral. Fecha ao clicar fora (contando o nó do portal)
   e no Esc; reposiciona no scroll/resize. Reusa as classes .selo-* existentes.

   O conteúdo do painel (lista de selos, "Novo selo…", etc.) é passado como
   children — cada tela monta o seu, o componente cuida de abrir/fechar/posicionar.
   ========================================================================== */

export function SeloPopover({
  trigger,
  children,
  open,
  onOpenChange,
  panelClassName = "",
  align = "left",
  minWidth = 220,
}: {
  /** Render-prop do gatilho: recebe o estado aberto p/ aria-expanded. */
  trigger: (args: { open: boolean; toggle: () => void }) => React.ReactNode;
  /** Conteúdo do painel (lista/inputs). Só monta quando aberto. */
  children: React.ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Classe extra no painel (ex.: largura mínima maior). */
  panelClassName?: string;
  /** Alinha a borda do painel à esquerda (default) ou à direita do gatilho. */
  align?: "left" | "right";
  minWidth?: number;
}) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const toggle = () => onOpenChange(!open);

  // Calcula a posição fixa a partir do retângulo do gatilho. Abre por baixo;
  // alinha à esquerda ou à direita; mantém dentro da viewport (clamp lateral +
  // flip vertical: vira pra cima quando não cabe embaixo — ex.: card no rodapé).
  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vw = document.documentElement.clientWidth;
      const vh = document.documentElement.clientHeight;
      const margin = 8;
      const gap = 6;
      const width = Math.max(minWidth, panelRef.current?.offsetWidth ?? minWidth);
      let left = align === "right" ? r.right - width : r.left;
      // Não deixar vazar pelas bordas laterais da viewport.
      left = Math.min(Math.max(margin, left), Math.max(margin, vw - width - margin));
      // Vertical: por baixo por padrão; se a altura real não couber, vira pra cima.
      // Em último caso (nem em cima cabe) cola na borda inferior com a margem.
      const h = panelRef.current?.offsetHeight ?? 0;
      const below = r.bottom + gap;
      let top = below;
      if (h && below + h > vh - margin) {
        const above = r.top - gap - h;
        top = above >= margin ? above : Math.max(margin, vh - margin - h);
      }
      setPos({ top, left });
    }
    place();
    // Re-mede após o painel montar: offsetHeight só existe no 2º paint, então o
    // flip vertical depende deste reposicionamento (sem ele a altura seria 0).
    const raf = requestAnimationFrame(place);
    window.addEventListener("resize", place);
    // captura o scroll de QUALQUER ancestral (tabela com overflow, etc.)
    window.addEventListener("scroll", place, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, align, minWidth]);

  // Fecha ao clicar fora — considerando que o painel está NO PORTAL (fora do
  // ref do gatilho), então checamos gatilho E painel.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (anchorRef.current?.contains(t)) return;
      if (panelRef.current?.contains(t)) return;
      onOpenChange(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onOpenChange(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onOpenChange]);

  return (
    <span ref={anchorRef} className="selo-anchor">
      {trigger({ open, toggle })}
      {open && mounted && pos
        ? createPortal(
            <div
              ref={panelRef}
              className={`selo-pop selo-pop-portal ${panelClassName}`}
              style={{ position: "fixed", top: pos.top, left: pos.left, minWidth }}
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

export default SeloPopover;
