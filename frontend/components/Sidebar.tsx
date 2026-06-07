"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "Dashboard", ico: "▦" },
  { href: "/pesquisas", label: "Pesquisas", ico: "✦" },
  { href: "/contatos", label: "Contatos", ico: "☎" },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">E</div>
        <div>
          <div className="brand-name">Escuta</div>
          <div className="brand-sub">Voz do Cliente · WhatsApp</div>
        </div>
      </div>
      <nav className="nav">
        {items.map((it) => (
          <Link key={it.href} href={it.href} className={path === it.href ? "active" : ""}>
            <span className="ico">{it.ico}</span>
            {it.label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-foot">
        Piloto · Bizzu
        <br />
        WAHA local · Supabase
      </div>
    </aside>
  );
}
