"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";
import {
  MessageSquare,
  MessageCircle,
  Kanban,
  Map,
  Users,
  ClipboardList,
  Smartphone,
  Settings,
  Radar,
} from "lucide-react";

/* Ícones da família Lucide (traço, currentColor): herdam a cor do item da nav
   (dim -> text no hover; gold no item de destaque). Coesos com o tema claro.
   stroke 1.75 acompanha a linguagem editorial do painel. */
type IconType = ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;
type NavItem = { href: string; label: string; icon: IconType; feature?: boolean };

/* Navegação ENXUTA, organizada pelo FLUXO real da operação manual (decisão do dono:
   simplicidade — "bato o olho e entendo"):
     OPERAÇÃO - o dia a dia: ver, registrar, conversar, organizar
     CLIENTES - a base e a coleta
     CONFIG   - infra do WhatsApp
   As telas que o dono considerou ruído saíram do MENU mas continuam EXISTINDO e
   acessíveis por URL (nada foi apagado). Reverter = devolver o item a um grupo:
     /dashboard  -> substituído pela Monitorar
     /temas      -> "Mapeamento": mapa de dores (clustering por significado)
     /melhorias  -> roadmap ("pra que serve?")
     /campanha   -> win-back ("inútil, dados errôneos")
     /tarefas    -> "deveria estar no board, não separado"
     /playbooks  -> automação ("não faz sentido")
     /contatos   -> coberto pela visão de Clientes
     /integracao -> documentação técnica de API */
const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Operação",
    items: [
      { href: "/", label: "Monitorar", icon: Radar, feature: true },
      { href: "/feedbacks", label: "Feedbacks", icon: MessageSquare, feature: true },
      { href: "/chat", label: "Chat", icon: MessageCircle, feature: true },
      { href: "/board", label: "Board", icon: Kanban },
      { href: "/temas", label: "Mapeamento", icon: Map },
    ],
  },
  {
    label: "Clientes",
    items: [
      { href: "/clientes", label: "Clientes", icon: Users },
      { href: "/pesquisas", label: "Pesquisas", icon: ClipboardList },
    ],
  },
  {
    label: "Config",
    items: [
      { href: "/conexao", label: "Conexão", icon: Smartphone },
      { href: "/config", label: "Configurações", icon: Settings },
    ],
  },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          E<span className="brand-mark-dot" aria-hidden />
        </div>
        <div>
          <div className="brand-name">Escuta</div>
          <div className="brand-sub">Voz do Cliente {"·"} WhatsApp</div>
        </div>
      </div>
      <nav className="nav">
        {groups.map((g) => (
          <div className="nav-group" key={g.label} role="group" aria-label={g.label}>
            <div className="nav-group-label" aria-hidden>{g.label}</div>
            {g.items.map((it) => {
              // "Monitorar" (href "/") é a Central: a home redireciona para
              // /central, então o item fica ativo nas duas rotas.
              const active =
                it.href === "/"
                  ? path === "/" || path === "/central" || path.startsWith("/central")
                  : path.startsWith(it.href);
              const cls = [active ? "active" : "", it.feature ? "feature" : ""]
                .filter(Boolean)
                .join(" ");
              const Icon = it.icon;
              return (
                <Link
                  key={it.href}
                  href={it.href}
                  className={cls}
                  aria-current={active ? "page" : undefined}
                >
                  <span className="ico">
                    <Icon size={18} strokeWidth={1.75} aria-hidden />
                  </span>
                  {it.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <span className="brand-by">
          by <b>Bizzu</b>
          <span className="brand-by-dot">.</span>
        </span>
        <span className="sidebar-foot-meta">Voz do Cliente {"·"} WhatsApp</span>
      </div>
    </aside>
  );
}
