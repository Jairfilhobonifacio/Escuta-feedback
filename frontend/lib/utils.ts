import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/* cn() — junta classes condicionais (clsx) e resolve conflitos do Tailwind
   (tailwind-merge), ex.: cn("px-2", cond && "px-4") => "px-4". Padrão shadcn/ui;
   usado por todos os componentes em components/ui. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
