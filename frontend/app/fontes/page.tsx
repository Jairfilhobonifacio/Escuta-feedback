"use client";

import { useCallback, useEffect, useId, useMemo, useState, type ComponentType } from "react";
import {
  Database,
  MessageCircle,
  CreditCard,
  Smartphone,
  ClipboardList,
  Users,
  Lock,
} from "lucide-react";
import { Reveal } from "@/components/Motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { sources, type Source, type SourceSync } from "@/lib/api";

/* ============================================================================
   CENTRAL DE FONTES — Fase 1. O dono LIGA/DESLIGA cada FONTE de dados e dispara
   um "Sincronizar agora" ASSÍNCRONO, vendo o PROGRESSO em tempo real (polling).

   Cada fonte vem do backend com `available` (a chave foi configurada no servidor?
   se não, o painel não pode ligar/sincronizar — controles travados + selo
   "Indisponível"), `enabled` (o liga/desliga do dono) e `sync` (estado/progresso).

   Comportamento OTIMISTA no toggle (reflete já, corrige pela resposta, reverte no
   erro), igual à Central do Agente. O "Sincronizar agora" marca a fonte como
   'running' na hora e o POLLING (a cada ~3500ms, pausado com a aba oculta) assume
   a atualização enquanto ALGUMA fonte estiver rodando — parando sozinho quando
   ninguém está mais 'running' (padrão do Chat/Conexão).

   Mesma linguagem visual do /agente (card/card-head/section-title/flash/Switch).
   Ícones lucide (currentColor), sem emoji literal. As únicas peças animadas
   (barra de progresso + spinner) ficam num <style jsx> local, como em /conexao.
   ========================================================================== */

type IconType = ComponentType<{ size?: number; "aria-hidden"?: boolean }>;

/** Ícone por fonte conhecida (graceful: chave fora da lista cai no Database). */
const SOURCE_ICONS: Record<string, IconType> = {
  whatsapp: MessageCircle,
  billing: CreditCard,
  cobranca: CreditCard,
  app: Smartphone,
  forms: ClipboardList,
  formularios: ClipboardList,
  clientes: Users,
  partner: Users,
};

function iconFor(key: string): IconType {
  return SOURCE_ICONS[key] ?? Database;
}

/** Data em pt-BR (mesmo formato curto usado nas demais telas). */
function fmtData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ===== Toggle acessível (idêntico ao da Central do Agente) ==================

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

// ===== Área de status da sincronização ======================================

function SyncStatus({ sync }: { sync: SourceSync }) {
  if (sync.status === "running") {
    const temTotal = sync.total > 0;
    const pct = temTotal
      ? Math.min(100, Math.max(0, Math.round((sync.processed / sync.total) * 100)))
      : 0;
    return (
      <div className="src-status">
        {temTotal && (
          <div
            className="src-progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={sync.total}
            aria-valuenow={sync.processed}
          >
            <span style={{ width: `${pct}%` }} />
          </div>
        )}
        <div className="src-sync-line">
          <span className="src-spinner" aria-hidden />
          {temTotal
            ? `Sincronizando… ${sync.processed}/${sync.total} (${pct}%)`
            : `Sincronizando… ${sync.processed} processados`}
        </div>
      </div>
    );
  }

  if (sync.status === "done") {
    return (
      <div className="src-done">
        Última sincronização: <b>{fmtData(sync.finished_at)}</b> {"—"} {sync.created}{" "}
        {sync.created === 1 ? "novo" : "novos"}, {sync.updated}{" "}
        {sync.updated === 1 ? "atualizado" : "atualizados"}
        {sync.errors > 0 && (
          <>
            {" "}
            {"·"} <span className="src-done-err">{sync.errors} com erro</span>
          </>
        )}
      </div>
    );
  }

  if (sync.status === "error") {
    return (
      <div className="flash err" style={{ margin: 0 }}>
        {sync.error_msg ?? "A sincronização falhou. Tente de novo."}
      </div>
    );
  }

  // idle — nunca sincronizada (ou parada).
  return <div className="src-idle">Ainda não sincronizada.</div>;
}

// ===== Card de uma fonte ====================================================

function SourceCard({
  source,
  busy,
  syncing,
  onToggle,
  onSync,
  delay,
}: {
  source: Source;
  busy: boolean;
  syncing: boolean;
  onToggle: () => void;
  onSync: () => void;
  delay: number;
}) {
  const Icon = iconFor(source.key);
  const running = source.sync.status === "running";
  const syncDisabled = !source.available || !source.enabled || running || syncing;

  const syncTitle = !source.available
    ? "Fonte indisponível — configure a chave no servidor (deploy)."
    : !source.enabled
      ? "Ligue a fonte para poder sincronizar."
      : running
        ? "Sincronização em andamento…"
        : "Buscar agora os dados novos desta fonte.";

  return (
    <Reveal delay={delay} className="card" style={{ padding: 0, marginBottom: 18 }}>
      <div className="card-head">
        <div style={{ minWidth: 0 }}>
          <div className="section-title inline-flex items-center gap-2">
            <Icon size={17} aria-hidden /> {source.label}
            {!source.available && (
              <Badge
                variant="neutral"
                title="A chave desta fonte não está configurada no servidor. Só o administrador libera (deploy)."
              >
                <Lock size={11} aria-hidden /> Indisponível
              </Badge>
            )}
          </div>
          <div className="card-head-sub">{source.descricao}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <span
            style={{
              fontSize: 12.5,
              fontWeight: 600,
              color: source.enabled ? "var(--indigo-light)" : "var(--text-faint)",
            }}
          >
            {source.enabled ? "Ligada" : "Desligada"}
          </span>
          <Switch
            checked={source.enabled}
            disabled={!source.available || busy}
            onClick={onToggle}
            label={`${source.enabled ? "Desligar" : "Ligar"}: ${source.label}`}
          />
        </div>
      </div>

      <div
        style={{
          padding: "14px 20px 18px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          {!source.available ? (
            <div className="src-idle">
              Configure a chave no servidor (deploy) para liberar esta fonte.
            </div>
          ) : (
            <SyncStatus sync={source.sync} />
          )}
        </div>
        <Button variant="outline" onClick={onSync} disabled={syncDisabled} title={syncTitle}>
          {running || syncing ? "Sincronizando…" : "Sincronizar agora"}
        </Button>
      </div>
    </Reveal>
  );
}

// ===== Skeleton enquanto o GET não volta ====================================

function FontesSkeleton() {
  return (
    <div aria-busy="true">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="card" style={{ padding: 0, marginBottom: 18 }}>
          <div className="card-head">
            <div style={{ flex: 1 }}>
              <div className="sk-line w-30" style={{ margin: "2px 0" }} />
              <div className="sk-line sk-sm w-60" style={{ margin: "6px 0 2px" }} />
            </div>
          </div>
          <div style={{ padding: "16px 20px 18px" }}>
            <div className="sk-card" style={{ height: 40, borderRadius: "var(--radius-sm)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ===== Página ===============================================================

export default function FontesPage() {
  const liveId = useId();
  const [items, setItems] = useState<Source[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [syncingKey, setSyncingKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await sources.list();
      setItems(res.sources);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Re-busca SILENCIOSA (polling): atualiza a lista sem piscar skeleton nem
  // derrubar a tela num blip transitório.
  const refresh = useCallback(async () => {
    try {
      const res = await sources.list();
      setItems(res.sources);
    } catch {
      /* silencioso — tenta de novo no próximo tick */
    }
  }, []);

  // Há alguma fonte sincronizando agora? Governa o polling.
  const anyRunning = useMemo(
    () => (items ?? []).some((s) => s.sync.status === "running"),
    [items],
  );

  // POLLING: só enquanto alguém está 'running'; pausa com a aba oculta; para
  // sozinho quando ninguém está mais rodando (o efeito desmonta).
  useEffect(() => {
    if (!anyRunning) return;
    const POLL_MS = 3500;
    const id = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      refresh();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [anyRunning, refresh]);

  async function toggle(source: Source) {
    if (!source.available || busyKey) return;
    const next = !source.enabled;
    // Otimista: reflete já; corrige pela resposta (ou reverte no erro).
    setItems((prev) =>
      prev ? prev.map((s) => (s.key === source.key ? { ...s, enabled: next } : s)) : prev,
    );
    setBusyKey(source.key);
    setFlash(null);
    try {
      const updated = await sources.setEnabled(source.key, next);
      setItems((prev) => (prev ? prev.map((s) => (s.key === source.key ? updated : s)) : prev));
      setFlash({
        kind: "ok",
        msg: `"${updated.label}" ${updated.enabled ? "ligada" : "desligada"}.`,
      });
    } catch (e) {
      // Reverte ao estado anterior (inclui 409: tentou ligar fonte indisponível).
      setItems((prev) => (prev ? prev.map((s) => (s.key === source.key ? source : s)) : prev));
      const msg = e instanceof Error ? e.message : String(e);
      setFlash({ kind: "err", msg: `Não deu para alterar "${source.label}": ${msg}.` });
    } finally {
      setBusyKey(null);
    }
  }

  async function sync(source: Source) {
    if (!source.available || !source.enabled || source.sync.status === "running" || syncingKey)
      return;
    setSyncingKey(source.key);
    setFlash(null);
    // Otimista: marca 'running' já — mostra barra/spinner na hora e liga o polling.
    setItems((prev) =>
      prev
        ? prev.map((s) =>
            s.key === source.key
              ? { ...s, sync: { ...s.sync, status: "running" as const } }
              : s,
          )
        : prev,
    );
    try {
      const res = await sources.sync(source.key);
      setItems((prev) =>
        prev ? prev.map((s) => (s.key === source.key ? { ...s, sync: res.sync } : s)) : prev,
      );
    } catch (e) {
      // 409 (desligada/indisponível/já em andamento) ou erro: reverte e explica.
      setItems((prev) => (prev ? prev.map((s) => (s.key === source.key ? source : s)) : prev));
      const msg = e instanceof Error ? e.message : String(e);
      setFlash({ kind: "err", msg: `Não deu para sincronizar "${source.label}": ${msg}.` });
    } finally {
      setSyncingKey(null);
    }
  }

  const total = items?.length ?? 0;
  const ligadas = items?.filter((s) => s.enabled).length ?? 0;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Fontes</h1>
          <div className="page-sub">
            Ligue e desligue cada fonte de dados e sincronize quando quiser. O
            progresso aparece aqui em tempo real. Fontes indisponíveis precisam da
            chave configurada no servidor.
          </div>
        </div>
        {items && (
          <div className="page-head-actions">
            <span className="refresh-note">
              {anyRunning ? "sincronizando… atualiza sozinho" : `${ligadas} de ${total} ligadas`}
            </span>
          </div>
        )}
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar as fontes ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {flash && (
        <div className={`flash ${flash.kind}`} role="status" id={liveId}>
          {flash.msg}
        </div>
      )}

      {!err && !items ? (
        <FontesSkeleton />
      ) : items && items.length === 0 ? (
        <div
          className="card"
          style={{ padding: 28, textAlign: "center", color: "var(--text-faint)" }}
        >
          Nenhuma fonte disponível ainda.
        </div>
      ) : items ? (
        <>
          {items.map((s, i) => (
            <SourceCard
              key={s.key}
              source={s}
              busy={busyKey === s.key}
              syncing={syncingKey === s.key}
              onToggle={() => toggle(s)}
              onSync={() => sync(s)}
              delay={0.04 + i * 0.05}
            />
          ))}
          <p className="count-line">
            Cada fonte é sincronizada por conta própria — ligue só as que fizerem
            sentido e atualize quando precisar.
          </p>
        </>
      ) : null}

      {/* estilos locais das peças animadas (barra de progresso + spinner) */}
      <style jsx>{`
        .src-status {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .src-progress {
          width: 100%;
          max-width: 320px;
          height: 7px;
          border-radius: 999px;
          overflow: hidden;
          background: var(--ink);
          border: 1px solid var(--charcoal);
        }
        .src-progress > span {
          display: block;
          height: 100%;
          border-radius: 999px;
          background: linear-gradient(90deg, var(--indigo), var(--indigo-light));
          transition: width 400ms var(--ease);
        }
        @media (prefers-reduced-motion: reduce) {
          .src-progress > span {
            transition: none;
          }
        }
        .src-sync-line {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          font-size: 13px;
          color: var(--text-dim);
          font-variant-numeric: tabular-nums;
        }
        .src-spinner {
          width: 15px;
          height: 15px;
          flex-shrink: 0;
          border-radius: 50%;
          border: 2px solid var(--charcoal);
          border-top-color: var(--indigo);
          animation: src-spin 0.8s linear infinite;
        }
        @keyframes src-spin {
          to {
            transform: rotate(360deg);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .src-spinner {
            animation: none;
          }
        }
        .src-done {
          font-size: 13px;
          color: var(--text-dim);
          line-height: 1.5;
          text-wrap: pretty;
        }
        .src-done b {
          color: var(--text);
          font-weight: 600;
        }
        .src-done-err {
          color: var(--detractor);
          font-weight: 600;
        }
        .src-idle {
          font-size: 13px;
          color: var(--text-faint);
          line-height: 1.5;
          text-wrap: pretty;
        }
      `}</style>
    </div>
  );
}
