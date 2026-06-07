# Relatório do agente — Site + Landing Pages Bizzu (gabarita-ai/site, gabarita-ai/landing-pages)

> Exploração automática em 07/06/2026. Clones: `~/Documents/Projetos/bizzu-repos/{site,landing-pages}`.

## 1. Stack e relação entre os repos

**`/site` (institucional — bizzu.ai):**
- Next.js 16 + React 19 + TS 5 + Tailwind v4 + ESLint 9
- PostHog + GA4
- A landing é um **HTML estático** (`public/landing-page.html`) servido por `/app/route.ts` com cache 3600s
- Páginas dinâmicas: `/editais`, `/bancas`, `/exemplo`

**`/landing-pages` (waitlist — lp.bizzu.ai):**
- HTML estático puro; `index.html` → redireciona pra `lista-de-espera/index.html`
- Relatórios estáticos em `/relatorios/` (SEFAZ-RN, SEFAZ-SP, Câmara)
- GA (`G-6WFC2DE7VE`) + PostHog

Relação: landing-pages = waitlist early-stage; site = institucional + showcase. Mesmo design system e analytics.

## 2. Captação de leads

- **Hero + CTA section (site)** e **Hero + Slide Panel/FAB (waitlist)**
- Capturam **APENAS EMAIL** (required) + relatório selecionado (waitlist)
- Destino: **Google Forms** via POST no-cors (silencioso — sem tratamento de erro!)
  - Form: `1FAIpQLSePfBW-Xh1VF3D0pqLkK7jcSSU5SfFUHUd75SC0N8evTMwnkA`
  - Campo email: `entry.19628127`
- `localStorage.setItem('bizzu_email', email)` p/ persistência
- ⚠️ Sem CRM — o "banco de leads" é a planilha do Google Forms

## 3. WhatsApp

**NÃO encontrado**: nenhum `wa.me`, `whatsapp://`, número de telefone, botão/ícone de WhatsApp, nem CRM/chat (Zendesk/Intercom).

## 4. Marca (tokens em `/site/app/globals.css`)

| Token | Hex | Uso |
|---|---|---|
| `--indigo` | #6C5CE7 | CTA principal |
| `--indigo-light` | #A78BFA | hover/highlight |
| `--gold` | #F5A623 | destaques/badges |
| `--void` | #09090B | fundo (dark-first) |
| `--ink`/`--card` | #141416/#18181B | superfícies |
| `--canvas` | #FAFAFA | texto principal |
| `--success`/`--alert` | #10B981/#EF4444 | estados |

Tipografia: **Space Grotesk** (headings) · **Inter** (body) · **JetBrains Mono** (dados).
Gradiente assinatura: `#6C5CE7 → #A78BFA → #F5A623`. Logo: "Bizzu" em Space Grotesk.

## 5. Depoimentos/social proof

- 8 depoimentos **hardcoded** no carousel (`landing-page.html` L3349-3418), nomes genéricos, sem data/foto/validação
- Sem integração com sistema de reviews (Trustpilot/G2/etc.)
- → oportunidade direta do Escuta: fluxo "aprovado → depoimento real coletado via WhatsApp"

## Oportunidades de opt-in WhatsApp na captação

1. **Hero form (site)** — `site/public/landing-page.html` L442-447: adicionar telefone + checkbox
2. **Waitlist** — `landing-pages/lista-de-espera/index.html` L2111-2122 (form) e L2906-2910 (slide panel)
3. Handler JS: L2933-3079 (`submitToGoogleForms`) — adicionar `GFORM_ENTRY_PHONE`/`GFORM_ENTRY_WHATSAPP_OPT`
4. Persistência: `localStorage` L3017/3055 (`bizzu_phone`, `bizzu_whatsapp_opt`)

Estrutura sugerida pro lead: email, phone, interesse (edital/cargo), whatsapp_opt_in, timestamp, source (hero/waitlist/slide), UTMs.

**Conclusão:** captação atual é low-tech (Google Forms, só email, sem telefone). Lead chegar "conversável" no WhatsApp exige só adicionar campo+checkbox e atualizar os entries do Forms — ou apontar o form pro próprio Escuta no futuro.
