import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/* Button — ação do painel, com PERSONALIDADE Bizzu (não shadcn cru).
   A primária (default) é indigo com relevo próprio: gradiente de marca, realce
   de luz no topo por dentro (inset sheen) e sombra COLORIDA tingida pela marca
   — um botão tátil/premium, reconhecível como Bizzu. A `accent` (gold) é a ação
   de VALOR, com o mesmo relevo em âmbar. As variantes subordinadas (secondary/
   outline/ghost) têm hierarquia clara — nem todo botão é primário.

   variants: default=indigo (primária) · secondary=superfície · ghost · outline ·
   accent=gold (valor/ação) · destructive=vermelho. sizes: sm | default | lg | icon.
   API pública preservada (nomes de variants/sizes). Tudo via CSS vars do
   globals.css → acompanha o tema. Foco com anel indigo de marca (offset claro). */
const buttonVariants = cva(
  [
    // base: forma, tipografia e movimento comuns a todas as variantes
    "relative inline-flex items-center justify-center gap-2 whitespace-nowrap select-none",
    "rounded-[var(--radius-sm)] font-semibold leading-none tracking-[-0.01em]",
    "transition-[transform,box-shadow,background-color,border-color,filter] duration-150 ease-[var(--ease)]",
    // foco de marca: anel indigo com leve afastamento sobre o fundo claro
    "outline-none focus-visible:ring-2 focus-visible:ring-[var(--indigo)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--void)]",
    // desabilitado: sem relevo, sem movimento
    "disabled:pointer-events-none disabled:opacity-55 disabled:shadow-none",
    // micro-interação tátil (suprimida em reduce-motion via media query no globals)
    "active:translate-y-px",
  ].join(" "),
  {
    variants: {
      variant: {
        // PRIMÁRIA — indigo com relevo de marca: gradiente + sheen + sombra colorida
        default: [
          "text-white border border-[var(--indigo-deep)]",
          "bg-[image:var(--grad-indigo)]",
          "shadow-[var(--btn-sheen),var(--btn-indigo-shadow)]",
          "hover:-translate-y-px hover:shadow-[var(--btn-sheen),var(--btn-indigo-shadow-hover)] hover:brightness-[1.04]",
          "active:translate-y-0 active:brightness-95 active:shadow-[var(--btn-indigo-shadow)]",
        ].join(" "),
        // VALOR/AÇÃO — gold marcante, mesmo relevo tátil em âmbar
        accent: [
          "text-[#3a2603] border border-[#d4880c]",
          "bg-[image:var(--grad-gold)]",
          "shadow-[var(--btn-sheen),var(--btn-gold-shadow)]",
          "hover:-translate-y-px hover:shadow-[var(--btn-sheen),var(--btn-gold-shadow-hover)] hover:brightness-[1.03]",
          "active:translate-y-0 active:brightness-95 active:shadow-[var(--btn-gold-shadow)]",
        ].join(" "),
        // SECUNDÁRIA — superfície tingida, borda forte; subordinada à primária
        secondary: [
          "text-ink bg-surface-raised border border-border-strong",
          "shadow-[var(--edge),var(--shadow-soft)]",
          "hover:bg-surface hover:border-ink-faint hover:-translate-y-px hover:shadow-[var(--edge),var(--shadow)]",
          "active:translate-y-0 active:shadow-[var(--shadow-soft)]",
        ].join(" "),
        // OUTLINE — vazado com borda tingida de indigo; preenche de leve no hover
        outline: [
          "text-ink bg-transparent border border-border-strong",
          "hover:bg-[var(--promoter-soft)] hover:border-[var(--promoter-line)] hover:text-[var(--indigo-light)]",
          "active:bg-[color-mix(in_srgb,var(--promoter-soft)_70%,transparent)]",
        ].join(" "),
        // GHOST — mínima, só um leve banho de superfície no hover (menor hierarquia)
        ghost: [
          "text-ink-dim bg-transparent border border-transparent",
          "hover:bg-surface-raised hover:text-ink",
          "active:bg-[color-mix(in_srgb,var(--ink-700)_80%,transparent)]",
        ].join(" "),
        // PERIGO — vermelho dessaturado com sombra própria
        destructive: [
          "text-white border border-[color-mix(in_srgb,var(--detractor)_75%,black)]",
          "bg-[image:linear-gradient(180deg,#d96a6a,var(--detractor))]",
          "shadow-[var(--btn-sheen),var(--btn-danger-shadow)]",
          "hover:-translate-y-px hover:brightness-[1.05]",
          "active:translate-y-0 active:brightness-95 active:shadow-none",
        ].join(" "),
      },
      size: {
        sm: "h-[34px] px-3.5 text-[12.5px]",
        default: "h-10 px-[18px] text-[13.5px]",
        lg: "h-[46px] px-7 text-[14.5px]",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };
