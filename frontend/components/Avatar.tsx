/* Avatar de iniciais com cor derivada do nome (determinística) — dá identidade
   visual a pessoas em tabelas, cards e na timeline. Tons harmônicos com a marca
   (indigo/gold/teal/coral dessaturados, no espírito editorial dark). */

const TONES = [
  { bg: "rgba(108, 92, 231, 0.16)", fg: "#a78bfa", line: "rgba(108, 92, 231, 0.38)" }, // indigo
  { bg: "rgba(245, 166, 35, 0.15)", fg: "#fbbf24", line: "rgba(245, 166, 35, 0.36)" }, // gold
  { bg: "rgba(94, 201, 178, 0.15)", fg: "#5ec9b2", line: "rgba(94, 201, 178, 0.36)" }, // teal
  { bg: "rgba(232, 121, 153, 0.15)", fg: "#e879a0", line: "rgba(232, 121, 153, 0.36)" }, // rosé
  { bg: "rgba(129, 140, 248, 0.15)", fg: "#a5b4fc", line: "rgba(129, 140, 248, 0.36)" }, // periwinkle
];

function initials(name?: string | null): string {
  const n = (name || "").trim();
  if (!n) return "?";
  const parts = n.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function toneFor(seed?: string | null): (typeof TONES)[number] {
  const s = seed || "?";
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return TONES[h % TONES.length];
}

export default function Avatar({
  name,
  seed,
  size = 34,
}: {
  name?: string | null;
  seed?: string | null;
  size?: number;
}) {
  const t = toneFor(seed ?? name);
  return (
    <span
      className="avatar"
      aria-hidden
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.4),
        background: t.bg,
        color: t.fg,
        borderColor: t.line,
      }}
    >
      {initials(name)}
    </span>
  );
}
