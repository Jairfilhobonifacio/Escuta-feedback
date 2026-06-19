import * as React from "react";
import { cn } from "@/lib/utils";

/* Input — campo de texto base (tema claro) com acabamento Bizzu. Campo "inset"
   na superfície (leve sombra interna no topo) p/ ler como recesso, borda forte
   clara que tinge de indigo no hover, foco com borda indigo + anel de marca
   (--ring-indigo) idêntico aos campos legados. Mapeado aos tokens do globals.css. */
const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-10 w-full rounded-md border border-border-strong bg-surface-base px-[13px] text-sm text-ink",
        "shadow-[inset_0_1px_2px_rgba(26,24,48,0.04)]",
        "placeholder:text-ink-ghost",
        "outline-none transition-[border-color,box-shadow] duration-150 ease-[var(--ease)]",
        "hover:border-[var(--text-faint)]",
        "focus:border-[var(--indigo)] focus:shadow-[var(--ring-indigo)]",
        "disabled:cursor-not-allowed disabled:opacity-55",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
