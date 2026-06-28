"use client";

import { useCallback, useEffect, useId, useMemo, useState, type ComponentType } from "react";
import { Bot, Lock, MessageCircle, Sparkles, SlidersHorizontal } from "lucide-react";
import { Reveal } from "@/components/Motion";
import { Badge } from "@/components/ui/badge";
import { agentConfig, type AgentFeature } from "@/lib/api";

/* ============================================================================
   CENTRAL DO AGENTE — Fase 1. O dono LIGA/DESLIGA o que a IA faz por ele.

   Cada feature vem do backend com seu `grupo` (vira seção), `descricao`
   (microcópia) e um `locked`: quando o env-piso da feature está OFF, o painel
   NÃO pode ligá-la — o switch fica desabilitado e ganha o selo "bloqueado pelo
   administrador".

   Comportamento OTIMISTA: ao alternar, a UI já reflete o novo estado e dispara o
   PUT; se a chamada falhar (ou o backend devolver um estado diferente — env-piso
   barrou o "ligar"), o estado é corrigido pela resposta e um flash explica.

   Mesma linguagem visual da tela Configurações (card/section-title/card-head/
   flash/skeleton). Sem styled-jsx: classes do globals.css + Tailwind/estilo
   inline com os tokens de marca. Ícones lucide (currentColor), sem emoji literal
   (o bundler do Next no Windows corrompe não-ASCII no fonte).
   ========================================================================== */

type IconType = ComponentType<{ size?: number; "aria-hidden"?: boolean }>;

/** Ordem e identidade visual das seções conhecidas. Grupos que o backend mande
    fora desta lista caem numa seção genérica no fim (fallback gracioso). */
const KNOWN_GROUPS = ["Atendimento automático", "Inteligência", "Organização"] as const;

const GROUP_META: Record<string, { sub: string; icon: IconType }> = {
  "Atendimento automático": {
    sub: "o que o agente responde e triagem sozinho no WhatsApp",
    icon: MessageCircle,
  },
  Inteligência: {
    sub: "análises que a IA gera a partir dos feedbacks",
    icon: Sparkles,
  },
  Organização: {
    sub: "como o agente arruma e encaminha o que chega",
    icon: SlidersHorizontal,
  },
};

const DEFAULT_META: { sub: string; icon: IconType } = {
  sub: "ajustes do agente",
  icon: Bot,
};

// ===== Toggle acessível (button role=switch) ================================

function Switch({
  checked,
  disabled,
  onClick,
  label,
}: {
  checked: boolean;
  disabled: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      style={{
        position: "relative",
        flexShrink: 0,
        width: 46,
        height: 27,
        padding: 0,
        borderRadius: 999,
        border: "1px solid",
        borderColor: checked ? "var(--indigo-deep)" : "var(--border-strong)",
        background: checked ? "var(--indigo)" : "var(--surface-base)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        transition: "background-color .15s var(--ease), border-color .15s var(--ease)",
      }}
    >
      <span
        aria-hidden
        style={{
          position: "absolute",
          top: 2,
          left: checked ? 21 : 2,
          width: 21,
          height: 21,
          borderRadius: "50%",
          background: "#fff",
          boxShadow: "var(--shadow-soft)",
          transition: "left .15s var(--ease)",
        }}
      />
    </button>
  );
}

// ===== Linha de uma feature =================================================

function FeatureRow({
  feature,
  busy,
  onToggle,
}: {
  feature: AgentFeature;
  busy: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className="card"
      style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 16px" }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, color: "var(--text)" }}>{feature.label}</span>
          {feature.locked && (
            <Badge
              variant="neutral"
              title="Desligado no servidor (variável de ambiente). O painel não pode ligar — peça ao administrador."
            >
              <Lock size={11} aria-hidden /> bloqueado pelo administrador
            </Badge>
          )}
        </div>
        <div className="card-head-sub" style={{ marginTop: 4 }}>
          {feature.descricao}
        </div>
      </div>
      <Switch
        checked={feature.enabled}
        disabled={feature.locked || busy}
        onClick={onToggle}
        label={`${feature.enabled ? "Desligar" : "Ligar"}: ${feature.label}`}
      />
    </div>
  );
}

// ===== Uma seção (um grupo) =================================================

function Section({
  grupo,
  items,
  busyKey,
  onToggle,
  delay,
}: {
  grupo: string;
  items: AgentFeature[];
  busyKey: string | null;
  onToggle: (f: AgentFeature) => void;
  delay: number;
}) {
  const meta = GROUP_META[grupo] ?? DEFAULT_META;
  const Icon = meta.icon;
  const ligadas = items.filter((f) => f.enabled).length;
  return (
    <Reveal delay={delay} className="card" style={{ padding: 0, marginBottom: 18 }}>
      <div className="card-head">
        <div>
          <div className="section-title inline-flex items-center gap-2">
            <Icon size={17} aria-hidden /> {grupo}
          </div>
          <div className="card-head-sub">{meta.sub}</div>
        </div>
        <span className="exit-counter">
          {ligadas}/{items.length} ligadas
        </span>
      </div>
      <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((f) => (
          <FeatureRow
            key={f.key}
            feature={f}
            busy={busyKey === f.key}
            onToggle={() => onToggle(f)}
          />
        ))}
      </div>
    </Reveal>
  );
}

// ===== Skeleton enquanto o GET não volta ====================================

function AgentSkeleton() {
  return (
    <div aria-busy="true">
      {KNOWN_GROUPS.map((g) => (
        <div key={g} className="card" style={{ padding: 0, marginBottom: 18 }}>
          <div className="card-head">
            <div style={{ flex: 1 }}>
              <div className="sk-line w-30" style={{ margin: "2px 0" }} />
              <div className="sk-line sk-sm w-60" style={{ margin: "6px 0 2px" }} />
            </div>
          </div>
          <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="sk-card" style={{ height: 56, borderRadius: "var(--radius-sm)" }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ===== Página ===============================================================

export default function AgentePage() {
  const liveId = useId();
  const [features, setFeatures] = useState<AgentFeature[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await agentConfig.get();
      setFeatures(res.features);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Agrupa por `grupo`, na ordem conhecida; grupos desconhecidos vão ao fim.
  const ordered = useMemo(() => {
    const byGroup = new Map<string, AgentFeature[]>();
    for (const f of features ?? []) {
      const arr = byGroup.get(f.grupo) ?? [];
      arr.push(f);
      byGroup.set(f.grupo, arr);
    }
    const keys: string[] = [];
    for (const g of KNOWN_GROUPS) if (byGroup.has(g)) keys.push(g);
    for (const g of byGroup.keys()) if (!keys.includes(g)) keys.push(g);
    return keys.map((g) => ({ grupo: g, items: byGroup.get(g) ?? [] }));
  }, [features]);

  async function toggle(feature: AgentFeature) {
    if (feature.locked || busyKey) return;
    const next = !feature.enabled;
    // Otimista: reflete já; corrige pela resposta (ou reverte no erro).
    setFeatures((prev) =>
      prev ? prev.map((f) => (f.key === feature.key ? { ...f, enabled: next } : f)) : prev,
    );
    setBusyKey(feature.key);
    setFlash(null);
    try {
      const res = await agentConfig.set(feature.key, next);
      setFeatures((prev) =>
        prev
          ? prev.map((f) =>
              f.key === feature.key ? { ...f, enabled: res.enabled, locked: res.locked } : f,
            )
          : prev,
      );
      if (res.enabled !== next) {
        // Backend recusou o "ligar" (env-piso OFF) — a feature aparece bloqueada.
        setFlash({
          kind: "err",
          msg: `Nao foi possivel ligar "${feature.label}" — bloqueada pelo administrador.`,
        });
      } else {
        setFlash({
          kind: "ok",
          msg: `"${feature.label}" ${res.enabled ? "ligada" : "desligada"}.`,
        });
      }
    } catch (e) {
      // Reverte ao estado anterior e explica.
      setFeatures((prev) =>
        prev
          ? prev.map((f) => (f.key === feature.key ? { ...f, enabled: feature.enabled } : f))
          : prev,
      );
      const msg = e instanceof Error ? e.message : String(e);
      setFlash({ kind: "err", msg: `Nao deu para alterar "${feature.label}": ${msg}.` });
    } finally {
      setBusyKey(null);
    }
  }

  const total = features?.length ?? 0;
  const ligadas = features?.filter((f) => f.enabled).length ?? 0;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Central do Agente</h1>
          <div className="page-sub">
            Ligue e desligue o que o agente de IA faz por voce. As mudancas valem na
            hora. Itens bloqueados pelo administrador so podem ser liberados no servidor.
          </div>
        </div>
        {features && (
          <div className="page-head-actions">
            <span className="refresh-note">
              {ligadas} de {total} ligadas
            </span>
          </div>
        )}
      </div>

      {err && (
        <div className="flash err">
          Nao consegui carregar as features do agente ({err}). A API esta rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {flash && (
        <div className={`flash ${flash.kind}`} role="status" id={liveId}>
          {flash.msg}
        </div>
      )}

      {!err && !features ? (
        <AgentSkeleton />
      ) : features && features.length === 0 ? (
        <div
          className="card"
          style={{ padding: 28, textAlign: "center", color: "var(--text-faint)" }}
        >
          Nenhuma feature do agente disponivel ainda.
        </div>
      ) : features ? (
        <>
          {ordered.map((g, i) => (
            <Section
              key={g.grupo}
              grupo={g.grupo}
              items={g.items}
              busyKey={busyKey}
              onToggle={toggle}
              delay={0.04 + i * 0.05}
            />
          ))}
          <p className="count-line">
            Cada chave controla uma capacidade do agente isoladamente — ligue só o
            que fizer sentido para a sua operação.
          </p>
        </>
      ) : null}
    </div>
  );
}
