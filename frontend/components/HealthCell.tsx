/* Célula de Health Score (0-100): barra + número, cor por banda — Fase 1 CS.
   Extraída de app/clientes/page.tsx para ser reusada também na fila de Tarefas.
   `healthCell(...)` é a forma usada nas tabelas; `<HealthCell />` é o wrapper JSX. */

export type HealthBand = "healthy" | "watch" | "at_risk";

export const HEALTH_META: Record<string, { cls: string; label: string }> = {
  healthy: { cls: "h-ok", label: "saudável" },
  watch: { cls: "h-watch", label: "atenção" },
  at_risk: { cls: "h-risk", label: "em risco" },
};

/** Barra de Health Score (0-100) com cor por banda; tooltip explica os fatores. */
export function healthCell(
  score: number,
  band: string,
  factors?: { delta: number; label: string }[],
) {
  const m = HEALTH_META[band] ?? HEALTH_META.watch;
  const tip = (factors ?? [])
    .map((f) => `${f.delta > 0 ? "+" : ""}${f.delta} ${f.label}`)
    .join(" · ");
  return (
    <div className={`health ${m.cls}`} title={tip || m.label}>
      <div className="health-bar"><span style={{ width: `${score}%` }} /></div>
      <span className="health-num">{score}</span>
    </div>
  );
}

export default function HealthCell({
  score,
  band,
  factors,
}: {
  score: number;
  band: string;
  factors?: { delta: number; label: string }[];
}) {
  return healthCell(score, band, factors);
}
