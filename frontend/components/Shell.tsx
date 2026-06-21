"use client";

import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";

/**
 * Casca do app: decide se mostra o shell com Sidebar ou a página "nua".
 *
 * O /login fica FORA do shell (sem Sidebar, full-bleed) — é uma porta de
 * entrada, não uma tela do painel. Escolhemos esconder a Sidebar via
 * `usePathname()` (client wrapper) em vez de reorganizar todas as páginas num
 * route group `(app)/` — mesmo resultado visual, mudança mínima e sem mover
 * arquivos. O layout raiz (server component) continua dono de <html>/<body>.
 */
export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const bare = path === "/login";

  if (bare) {
    return <main className="bare-main">{children}</main>;
  }

  return (
    <div className="shell">
      <Sidebar />
      <main className="main">{children}</main>
    </div>
  );
}
