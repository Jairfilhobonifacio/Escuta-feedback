import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

/* ============================================================================
   Tailwind — fundação da NOVA UI do painel Escuta (tema CLARO, marca Bizzu).

   CRÍTICO: `corePlugins.preflight = false`. O painel tem ~2200 linhas de CSS
   legado em globals.css com classes próprias (.card/.btn/.kpi/.sidebar/.table…)
   que consomem CSS variables (--indigo, --gold, --text, --void…). Ligar o reset
   do Tailwind (preflight) reescreveria margens/box-sizing/tipografia base e
   quebraria as 15 telas existentes. Por isso o reset fica DESLIGADO — Tailwind
   entra só como camada de utilitários + tokens para os componentes novos.

   As cores aqui mapeiam para as MESMAS CSS vars do globals.css. Assim, quando
   os valores das vars viram light no :root, os utilitários do Tailwind (ex.
   `bg-surface`, `text-primary`) acompanham automaticamente — uma única fonte
   de verdade para legado e componentes novos.
   ========================================================================== */
const config: Config = {
  // Sem dark: variant — o tema é definido pelos valores das CSS vars no :root.
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false, // NÃO resetar o CSS legado
  },
  theme: {
    extend: {
      colors: {
        // marca (mapeadas para as vars de :root — única fonte de verdade)
        primary: {
          DEFAULT: "var(--indigo)",
          deep: "var(--indigo-deep)",
          light: "var(--indigo-light)",
        },
        accent: {
          DEFAULT: "var(--gold)",
          soft: "var(--gold-soft)",
        },
        // superfícies / fundo
        canvas: "var(--void)", // fundo da página
        surface: {
          DEFAULT: "var(--ink-800)", // cards (camada 2)
          base: "var(--ink)", // superfície base (camada 1)
          raised: "var(--ink-700)", // elevada / hover (camada 3)
        },
        // bordas / divisores
        border: {
          DEFAULT: "var(--charcoal)",
          strong: "var(--charcoal-2)",
        },
        hairline: "var(--hairline)",
        // texto
        ink: {
          DEFAULT: "var(--text)",
          dim: "var(--text-dim)",
          faint: "var(--text-faint)",
          ghost: "var(--text-ghost)",
        },
        // sentimento / dados (positivo=indigo · neutro=gold · negativo=vermelho)
        positive: "var(--promoter)",
        neutral: "var(--passive)",
        negative: "var(--detractor)",
      },
      fontFamily: {
        // títulos = Space Grotesk · corpo/UI = Inter · dados/números = JetBrains Mono
        display: ["var(--font-heading)", "var(--font-body)", "sans-serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-data)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)", // 16px
        md: "var(--radius-sm)", // 11px
        sm: "var(--radius-xs)", // 8px
      },
      boxShadow: {
        soft: "var(--shadow-sm)",
        DEFAULT: "var(--shadow)",
        pop: "var(--shadow-pop)",
        edge: "var(--edge)",
      },
      ringColor: {
        primary: "var(--indigo)",
      },
      transitionTimingFunction: {
        brand: "var(--ease)",
        out: "var(--ease-out)",
      },
      keyframes: {
        // usados por componentes novos (ex.: skeleton, reveal) via Tailwind
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "rise-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "none" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms var(--ease-out, ease-out) both",
        "rise-in": "rise-in 320ms var(--ease-out, ease-out) both",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
