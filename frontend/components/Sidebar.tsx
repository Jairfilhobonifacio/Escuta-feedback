"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ComponentType } from "react";
import {
  MessageSquare,
  MessageCircle,
  Kanban,
  Map,
  Lightbulb,
  Users,
  ClipboardList,
  Smartphone,
  Settings,
  Radar,
  LogOut,
} from "lucide-react";
import { auth, whatsapp as wa } from "@/lib/api";

/* Ícones da família Lucide (traço, currentColor): herdam a cor do item da nav
   (dim -> text no hover; gold no item de destaque). Coesos com o tema claro.
   stroke 1.75 acompanha a linguagem editorial do painel. */
type IconType = ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;
type NavItem = { href: string; label: string; icon: IconType; feature?: boolean; statusDot?: boolean };

/* Navegação ENXUTA, organizada pelo FLUXO real da operação manual (decisão do dono:
   simplicidade — "bato o olho e entendo"):
     OPERAÇÃO - o dia a dia: ver, registrar, conversar, organizar
     CLIENTES - a base e a coleta
     CONFIG   - infra do WhatsApp
   As telas que o dono considerou ruído saíram do MENU mas continuam EXISTINDO e
   acessíveis por URL (nada foi apagado). Reverter = devolver o item a um grupo:
     /dashboard  -> substituído pela Monitorar
     /mapeamento -> "Mapeamento": mapa de dores (clustering por significado); /temas redireciona p/ cá
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
      { href: "/mapeamento", label: "Mapeamento", icon: Map },
      { href: "/melhorias", label: "Melhorias", icon: Lightbulb },
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
      { href: "/conexao", label: "Conexão", icon: Smartphone, statusDot: true },
      { href: "/config", label: "Configurações", icon: Settings },
    ],
  },
];

/* Indicador GLOBAL da conexão do WhatsApp: um ponto no item "Conexão", visível em todas
   as telas. Verde=conectado, vermelho=desconectado, cinza=verificando. Poll leve de 30s,
   pausa com a aba oculta — sem peso. Fonte: o MESMO `wa.status()` da tela de Conexão. */
function WaDot() {
  const [conectado, setConectado] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      wa
        .status()
        .then((s) => alive && setConectado(!!s?.conectado))
        .catch(() => alive && setConectado(null));
    tick();
    const id = setInterval(() => {
      if (typeof document === "undefined" || !document.hidden) tick();
    }, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  const cor = conectado == null ? "var(--text-ghost, #9aa0aa)" : conectado ? "#22c55e" : "#ef4444";
  const titulo =
    conectado == null
      ? "WhatsApp: verificando…"
      : conectado
        ? "WhatsApp conectado"
        : "WhatsApp desconectado — clique para reconectar";
  return (
    <span
      title={titulo}
      aria-label={titulo}
      style={{
        marginLeft: "auto",
        width: 8,
        height: 8,
        borderRadius: 999,
        background: cor,
        flex: "0 0 auto",
        boxShadow: conectado ? "0 0 0 3px rgba(34,197,94,.15)" : undefined,
      }}
    />
  );
}

export default function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const [saindo, setSaindo] = useState(false);

  async function sair() {
    if (saindo) return;
    setSaindo(true);
    try {
      await auth.logout();
    } catch {
      /* logout é best-effort; o cookie é apagado pelo BFF de toda forma */
    }
    router.replace("/login");
  }

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
                  {it.statusDot && <WaDot />}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <button
          type="button"
          className="sidebar-logout"
          onClick={sair}
          disabled={saindo}
          title="Encerrar a sessão"
        >
          <LogOut size={15} strokeWidth={1.75} aria-hidden />
          {saindo ? "Saindo…" : "Sair"}
        </button>
        <span className="brand-by">
          by <b>Bizzu</b>
          <span className="brand-by-dot">.</span>
        </span>
        <span className="sidebar-foot-meta">Voz do Cliente {"·"} WhatsApp</span>
      </div>
    </aside>
  );
}
