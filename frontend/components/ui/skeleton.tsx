import * as React from "react";
import { cn } from "@/lib/utils";

/* Skeleton — placeholder de carregamento. Usa a base clara (--sk-base) e o pulse
   do tailwindcss-animate. Para o shimmer deslizante mais elaborado, as classes
   legadas .sk-line/.sk-card/.sk-circle do globals.css continuam disponíveis. */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-[var(--sk-base)]", className)}
      {...props}
    />
  );
}

export { Skeleton };
