import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/* Badge — etiqueta compacta com acabamento Bizzu (realce de luz no topo via
   --edge, mesma linguagem das pílulas/badges legadas). Cores de sentimento
   alinhadas à marca: positive=indigo · neutral=gold · negative=vermelho
   dessaturado · outline/neutral discretos. As sólidas (default/accent) ganham
   gradiente + borda escurecida p/ relevo. Texto já escurecido (vars) p/ AA. */
const badgeVariants = cva(
  [
    "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5",
    "text-[11px] font-semibold leading-none tracking-[0.01em] whitespace-nowrap",
    "shadow-[var(--edge)]",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "border-[var(--indigo-deep)] bg-[image:var(--grad-indigo)] text-white",
        positive:
          "border-[color:var(--promoter-line)] bg-[color:var(--promoter-soft)] text-[color:var(--indigo-light)]",
        neutral:
          "border-[color:var(--passive-line)] bg-[color:var(--passive-soft)] text-[color:var(--gold-soft)]",
        negative:
          "border-[color:var(--detractor-line)] bg-[color:var(--detractor-soft)] text-[color:var(--detractor)]",
        outline: "border-border-strong bg-transparent text-ink-dim shadow-none",
        accent:
          "border-[#d4880c] bg-[image:var(--grad-gold)] text-[#3a2603]",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
