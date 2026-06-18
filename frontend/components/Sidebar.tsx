"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/* Ícones de traço (família Lucide), stroke 1.75 + currentColor — herdam a cor do
   item da nav (dim → text no hover, gold no item de destaque). Substituem os emojis
   anteriores, que quebravam a coesão visual editorial. */
function Ico({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
    >
      {children}
    </svg>
  );
}

const items: { href: string; label: string; ico: ReactNode; feature?: boolean }[] = [
  {
    href: "/",
    label: "Dashboard",
    ico: (
      <Ico>
        <rect x="3" y="3" width="7" height="9" rx="1.5" />
        <rect x="14" y="3" width="7" height="5" rx="1.5" />
        <rect x="14" y="12" width="7" height="9" rx="1.5" />
        <rect x="3" y="16" width="7" height="5" rx="1.5" />
      </Ico>
    ),
  },
  {
    href: "/feedbacks",
    label: "Feedbacks",
    feature: true,
    ico: (
      <Ico>
        <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
      </Ico>
    ),
  },
  {
    href: "/chat",
    label: "Chat",
    feature: true,
    ico: (
      <Ico>
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8z" />
      </Ico>
    ),
  },
  {
    href: "/board",
    label: "Board",
    ico: (
      <Ico>
        <rect x="3" y="3" width="5" height="18" rx="1.5" />
        <rect x="9.5" y="3" width="5" height="12" rx="1.5" />
        <rect x="16" y="3" width="5" height="15" rx="1.5" />
      </Ico>
    ),
  },
  {
    href: "/temas",
    label: "Temas",
    ico: (
      <Ico>
        <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
        <circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" stroke="none" />
      </Ico>
    ),
  },
  {
    href: "/melhorias",
    label: "Melhorias",
    ico: (
      <Ico>
        <path d="M15 14c.2-1 .7-1.7 1.5-2.5C17.7 10.2 18 9 18 7.5a6 6 0 0 0-12 0c0 1.5.4 2.7 1.5 4 .8.8 1.3 1.5 1.5 2.5" />
        <path d="M9 18h6" />
        <path d="M10 22h4" />
      </Ico>
    ),
  },
  {
    href: "/campanha",
    label: "Campanha",
    ico: (
      <Ico>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="5" />
        <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      </Ico>
    ),
  },
  {
    href: "/clientes",
    label: "Clientes",
    ico: (
      <Ico>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </Ico>
    ),
  },
  {
    href: "/pesquisas",
    label: "Pesquisas",
    ico: (
      <Ico>
        <rect x="8" y="2" width="8" height="4" rx="1" />
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
        <path d="M9 12l1.5 1.5L13 11" />
        <path d="M9 17h6" />
      </Ico>
    ),
  },
  {
    href: "/contatos",
    label: "Contatos",
    ico: (
      <Ico>
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
      </Ico>
    ),
  },
  {
    href: "/tarefas",
    label: "Tarefas",
    ico: (
      <Ico>
        <path d="M11 3 8 6 6.5 4.5" />
        <path d="M11 9 8 12l-1.5-1.5" />
        <path d="M11 15l-3 3-1.5-1.5" />
        <path d="M14 4h7" />
        <path d="M14 10h7" />
        <path d="M14 16h7" />
      </Ico>
    ),
  },
  {
    href: "/playbooks",
    label: "Playbooks",
    ico: (
      <Ico>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M8 13l2 2 3.5-3.5" />
        <path d="M8 18h4" />
      </Ico>
    ),
  },
  {
    href: "/integracao",
    label: "Integração",
    ico: (
      <Ico>
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
      </Ico>
    ),
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
          <div className="brand-sub">Voz do Cliente · WhatsApp</div>
        </div>
      </div>
      <nav className="nav">
        {items.map((it) => {
          const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
          const cls = [active ? "active" : "", it.feature ? "feature" : ""]
            .filter(Boolean)
            .join(" ");
          return (
            <Link key={it.href} href={it.href} className={cls} aria-current={active ? "page" : undefined}>
              <span className="ico">{it.ico}</span>
              {it.label}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <span className="brand-by">
          by Bizzu<span className="brand-by-dot">.</span>
        </span>
        <span className="sidebar-foot-meta">Piloto · WAHA local · Supabase</span>
      </div>
    </aside>
  );
}
