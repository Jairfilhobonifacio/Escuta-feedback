"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";
import {
  LayoutDashboard,
  MessageSquare,
  MessageCircle,
  Tag,
  Kanban,
  Lightbulb,
  Users,
  ClipboardList,
  Phone,
  Megaphone,
  ListChecks,
  BookOpen,
  Smartphone,
  Plug,
  Radar,
} from "lucide-react";

/* Ícones da família Lucide (traço, currentColor): herdam a cor do item da nav
   (dim -> text no hover; gold no item de destaque). Coesos com o tema claro.
   stroke 1.75 acompanha a linguagem editorial do painel. */
type IconType = ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;
type NavItem = { href: string; label: string; icon: IconType; feature?: boolean };

/* Navegação agrupada por intenção do usuário (mantém TODOS os itens e rotas):
     MONITORAR - onde se observa a voz do cliente (telas de leitura/insight)
     GERIR     - onde se organiza e prioriza (triagem, roadmap, base)
     OPERAR    - onde se age e se conecta (execucao + infra do WhatsApp) */
const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Monitorar",
    items: [
      { href: "/central", label: "Central", icon: Radar, feature: true },
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/feedbacks", label: "Feedbacks", icon: MessageSquare, feature: true },
      { href: "/chat", label: "Chat", icon: MessageCircle, feature: true },
      { href: "/temas", label: "Temas", icon: Tag },
    ],
  },
  {
    label: "Gerir",
    items: [
      { href: "/board", label: "Board", icon: Kanban },
      { href: "/melhorias", label: "Melhorias", icon: Lightbulb },
      { href: "/clientes", label: "Clientes", icon: Users },
      { href: "/pesquisas", label: "Pesquisas", icon: ClipboardList },
      { href: "/contatos", label: "Contatos", icon: Phone },
    ],
  },
  {
    label: "Operar",
    items: [
      { href: "/campanha", label: "Campanha", icon: Megaphone },
      { href: "/tarefas", label: "Tarefas", icon: ListChecks },
      { href: "/playbooks", label: "Playbooks", icon: BookOpen },
      { href: "/conexao", label: "Conexao", icon: Smartphone },
      { href: "/integracao", label: "Integracao", icon: Plug },
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
              const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
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
        <span className="sidebar-foot-meta">Piloto {"·"} WAHA local {"·"} Supabase</span>
      </div>
    </aside>
  );
}
