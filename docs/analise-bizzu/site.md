# Análise Profunda — Bizzu Site Institucional

> Gerado em 08/06/2026. Leitura-only: nenhum arquivo foi modificado.

---

## Resumo Executivo

- **Site institucional / landing page** para assinatura da plataforma Bizzu — edtech de concursos públicos com IA. Não é o app; o app está em `plataforma.bizzu.ai`.
- **Proposta de valor central**: "Estude o que importa" — planejamento de estudos baseado em dados reais de 600 mil+ questões de bancas examinadoras, com Raio X da Prova (ranking de tópicos por prioridade real, cruzando banca + cargo + órgão + área).
- **Preços declarados**: R$ 10/mês ou R$ 60/ano (lançamento válido até 20/05). Preço cheio declarado internamente: R$ 60/mês ou R$ 650/ano. Garantia de 7 dias, sem fidelidade.
- **Captação de leads**: **ZERO captura de dados do visitante antes da assinatura.** Todos os CTAs levam diretamente a `plataforma.bizzu.ai/signup`. Não há campo de e-mail, telefone, WhatsApp ou lista de espera na landing page.
- **Analytics**: GA4 (`G-6WFC2DE7VE`) + PostHog (token injetado em runtime). Rastreamento UTM completo, scroll depth (25/50/75/100%), cliques em CTA por posição e variante.
- **Oportunidade clara para o Escuta**: adicionar captura de WhatsApp/e-mail antes da assinatura (hero ou exit-intent) permitiria nutrição de leads e funil NPS — atualmente não existe nenhum ponto de opt-in.

---

## 1. Stack & Propósito

| Item | Detalhe |
|---|---|
| Framework | Next.js 16 / React 19 / TypeScript 5 |
| CSS | Tailwind CSS 4 (v4, `@import "tailwindcss"`) |
| Deploy | Vercel (domínio `bizzu.ai`; redireciona `www.` → apex) |
| Papel | Site institucional — captação para assinatura. O produto real fica em `plataforma.bizzu.ai` |

**Padrão arquitetural incomum:** a home (rota `/`) é servida por um `GET` handler em `app/route.ts` que lê `public/landing-page.html` do disco, substitui o placeholder `__POSTHOG_TOKEN__` e retorna HTML bruto com `Cache-Control: public, max-age=3600`. Todo o conteúdo da landing page está em um único arquivo HTML estático de ~5.268 linhas, sem componentes React. As demais rotas (`/bancas`, `/editais`, `/editais/[slug]`, `/exemplo`) são páginas Next.js com componentes React/Tailwind.

---

## 2. Páginas & Conteúdo

| Rota | Tipo | Conteúdo |
|---|---|---|
| `/` | HTML estático servido via route handler | Landing page completa (hero, proof bar, depoimentos, problema, features, comparativo, preços, FAQ, CTA final, footer) |
| `/bancas` | Next.js page | Lista de bancas examinadoras disponíveis na plataforma (renderização client-side via `fetch /api/bancas`) |
| `/bancas/[slug]` | Next.js page | Perfil de cada banca com editais e concursos associados |
| `/editais` | Next.js page (SSR + ISR) | Lista de editais abertos com filtros de busca; hero com contadores de editais, vagas e bancas disponíveis |
| `/editais/[slug]` | Next.js page (SSR + ISR) | Detalhe do edital: cargos, cronograma, etapas da prova, salários, FAQ gerado dinamicamente, CTA "Montar meu plano para este edital" |
| `/exemplo` | Next.js page | Tour interativo da plataforma: Dashboard, Raio X do Tópico, Plano de Estudos, Questão Comentada, Caderno do Tópico |
| `/termos/termos-de-uso.html` | HTML estático | Termos de uso (arquivo em `public/termos/`) |
| `/termos/politica-de-privacidade.html` | HTML estático | Política de privacidade (arquivo em `public/termos/`) |

Não existe rota `/sobre`, `/blog`, nem `/parceiros` — o site é exclusivamente focado em conversão.

---

## 3. Proposta de Valor & Copy (frases declaradas)

### Tagline principal
- **"Bizzu · Estude o que importa."** (nav e footer)
- **Título H1 da home:** "Planejamento de estudos para concursos públicos com **inteligência**"

### Claims extraídos literalmente do HTML

- "600 mil questões reais analisadas" (proof bar, countup animado)
- "Maiores bancas examinadoras do Brasil"
- "12+ áreas de concursos"
- "IA — inteligência artificial aplicada"
- "Não é previsão nem achismo: são dados reais e verificáveis."
- "Modelo multifatorial: banca + cargo + órgão + área de atuação"
- "Classificação ALTA, MÉDIA e BAIXA por relevância comprovada"
- "Cada edital esconde um padrão. A Bizzu revela qual tópico pesa mais." (hero da página /editais)
- "O edital vira estratégia em minutos." (CTA em /editais)
- "A Bizzu não é um curso online e não vende aulas ou apostilas." (FAQ — diferenciação explícita)
- "Sim, a Bizzu complementa qualquer método ou curso preparatório." (FAQ)
- "Cancele quando quiser, sem fidelidade." (preços)
- "Garantia incondicional de 7 dias — Cancele nos primeiros 7 dias e receba reembolso integral, sem burocracia."

### Framing do problema (seção "O problema")
- "300+ Tópicos no edital — todos com o mesmo peso."
- "∞ Formas de organizar os estudos errado."
- "Zero Ferramentas que personalizam de verdade."
- "A maioria dos concurseiros perde tempo por falta de dados. Eles estudam no escuro."

### Depoimentos (nomes e perfis exibidos — verificabilidade não avaliada)
- Lucas R. / SEFAZ GO: "O Raio X mostrou que eu gastava 40% do tempo em tópicos que quase não caem."
- Camila S. / TJCE: "Trabalho o dia inteiro e só tenho 2 horas à noite para estudar. O plano automático me diz exatamente o que fazer."
- Rafael M. / PMAL 2026: "O edital tinha mais de 200 tópicos. A Bizzu ranqueou por prioridade e eu soube por onde começar no primeiro dia."
- Ana P. / UNEAL 2026, Juliana F. / TJSC 2026, Pedro H. / IFCE 2026, Fernanda L. / SES/MG 2026.

### Funcionalidades declaradas
1. **Raio X da Prova** — ranking de tópicos por prioridade (Muito Alta / Alta / Média / Baixa), modelo multifatorial.
2. **Bizzu do Tópico** — resumo inteligente gerado por IA a partir de questões reais; "o que mais cai, armadilhas comuns e checklist de revisão".
3. **Plano de Estudos automático** — cronograma com metas semanais progressivas, cobre 100% do edital.
4. **Questões Selecionadas** — banco de 600 mil+ questões filtradas por tópico dentro do plano.
5. **Questões Comentadas** — explicação IA com "por que cada alternativa está certa ou errada", detecta gabarito equivocado.
6. **Caderno do Tópico** — organiza Bizzus salvos, favoritas, erros e anotações por tópico.
7. **Revisões Inteligentes** — desbloqueadas automaticamente após completar cada tópico.

### Público-alvo declarado
- **Iniciante** ("Primeiro concurso? O edital saiu e são centenas de tópicos.")
- **Experiente** ("Já investiu meses de estudo. A Bizzu mostra onde concentrar esforço.")
- **Profissional** ("Com poucas horas por dia, cada minuto conta.")

---

## 4. Preços Declarados

Arquivo canônico de preços: `app/(site)/lib/pricing.ts` (fallback com valores hardcoded).

| Plano | Preço Lançamento | Preço Cheio (fallback) | Período Promo |
|---|---|---|---|
| Mensal | **R$ 10,00/mês** | R$ 60,00/mês | até 20/05 |
| Anual | **R$ 60,00/ano** | R$ 650,00/ano | até 20/05 |

- Ambos os planos incluem acesso completo a todas as funcionalidades (não há plano gratuito ou freemium declarado).
- Garantia: 7 dias com reembolso integral.
- Sem fidelidade (cancel any time).
- O plano anual é apresentado como "Economize 50% comparado ao valor mensal total".
- CTAs de assinatura apontam para `https://plataforma.bizzu.ai/signup?plano=mensal` e `https://plataforma.bizzu.ai/signup?plano=anual`.

**Nota:** a data "até 20/05" está defasada (data atual: 08/06/2026). O preço pode ter sido ajustado na plataforma via `api.bizzu.ai/platform-config`, mas o fallback hardcoded ainda exibe "R$ 10/mês" e "R$ 60/ano".

---

## 5. Captação de Leads (CRÍTICO para o Escuta)

### O que existe atualmente

**Não há nenhum formulário de captura de leads no site.** Levantamento completo:

- Nenhum `<form>`, `<input type="email">`, `<input type="tel">` ou campo de WhatsApp no HTML gerado.
- Os CSS classes `.hero-form` e `.cta-form` existem no arquivo de estilos, mas **não são usadas em nenhum elemento HTML** do body — evidência de que houve um formulário em versão anterior que foi removido.
- Todos os CTAs são links diretos para `plataforma.bizzu.ai` ou `#pricing`:
  - Nav: "Entrar" → `https://plataforma.bizzu.ai`
  - Nav: "Assinar agora" → `#pricing`
  - Hero: "Assinar agora" → `#pricing` | "Ver amostra grátis →" → `/exemplo`
  - Pricing: "Assinar Mensal" → `https://plataforma.bizzu.ai/signup?plano=mensal`
  - Pricing: "Assinar Anual" → `https://plataforma.bizzu.ai/signup?plano=anual`
  - CTA Final: "Assinar agora" → `#pricing`

- **Não há** lista de espera, newsletter, captura de e-mail pré-assinatura, nem integração com WhatsApp, Telegram ou qualquer canal de mensagens.

### Oportunidade para o Escuta

O funil hoje é: **visita → preço → signup na plataforma**. Quem não converte na primeira visita é perdido permanentemente.

Pontos de inserção naturais para captura de WhatsApp/e-mail:

1. **Hero** — após o H1, antes ou depois do CTA "Assinar agora": um campo "Receba novidades e análise do seu edital pelo WhatsApp" capturaria visitantes ainda na fase de consideração.
2. **Exit-intent** — pop-up ao tentar sair da página, com oferta de "análise gratuita do seu edital por WhatsApp".
3. **Página `/exemplo`** — ao final do tour interativo, o visitante já viu o produto; é o momento ideal para opt-in antes de pedir o pagamento.
4. **Páginas de edital (`/editais/[slug]`)** — cada página já segmenta o visitante por concurso específico; uma captura contextualizada ("Quero receber atualizações deste edital no WhatsApp") converteria muito melhor que a landing genérica.

**Ausência de telefone/WhatsApp é confirmada**: nenhuma menção nos ~5.268 linhas de `landing-page.html` nem nas páginas React.

---

## 6. SEO / Analytics / Tracking

### Google Analytics 4
- Propriedade: `G-6WFC2DE7VE`
- Injetado em dois lugares: `app/layout.tsx` (via `<Script>`) e `public/landing-page.html` (script inline direto).
- Eventos GA4 personalizados: `click_subscribe` (com `event_label` por posição: `hero`, `pricing_mensal`, `pricing_anual`, `cta_final`).

### PostHog
- Token injetado em runtime via variável de ambiente `NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN` (substituído no HTML via `replace()` no route handler).
- Configuração: `autocapture: true`, `capture_pageview: true`, `capture_pageleave: true`, session recording com `maskAllInputs: false`.
- Proxy via Next.js rewrites: `/ingest/*` → `https://us.i.posthog.com/*` (contorna bloqueadores de ads).
- Eventos customizados implementados:
  - `landing_cta_clicked` (com `cta_label`, `cta_position`, `cta_variant`, `href`)
  - `landing_amostra_cta_clicked` (variante `amostra_tour_v1`)
  - `landing_sample_pdf_clicked` (para amostras PDF)
  - `landing_scroll_depth` (25%, 50%, 75%, 100%)
- Classificação de canal UTM automatizada: `paid_search`, `paid_social`, `email`, `organic_search`, `organic_social`, `referral`, `direct`.

### SEO
- Meta description da home menciona preço ("Preço de lançamento R$ 10/mês até 20/05") — desatualizado.
- Canonical URL: `https://bizzu.ai/`
- Open Graph completo (imagem 1200×630, locale `pt_BR`).
- Twitter card `summary_large_image`.
- Structured data (JSON-LD): `Organization`, `SoftwareApplication` (com `offers.price: "10.00"`), `FAQPage` com 12 Q&As.
- Sitemap gerado em `app/sitemap.ts`.
- Páginas de edital geram metadata dinâmico com informações do concurso (vagas, salários, data da prova) para SEO long-tail.
- `robots`: `index, follow`.

---

## 7. Identidade Visual

### Cores (variáveis CSS declaradas)
| Token | Valor | Uso |
|---|---|---|
| `--void` | `#09090B` | Background principal (quase-preto) |
| `--indigo` | `#6C5CE7` | Cor primária de ação e destaque |
| `--indigo-deep` | `#5B4BCF` | Hover do indigo |
| `--indigo-light` | `#A78BFA` | Labels, badges, texto secundário |
| `--gold` | `#F5A623` | Cor de destaque/contraste, atenção |
| `--gold-soft` | `#FBBF24` | Variante suave do gold |
| `--success` | `#10B981` | Confirmações, checks |
| `--alert` | `#EF4444` | Prioridade alta, alertas |
| `--canvas` | `#FAFAFA` | Texto principal claro |
| `--silver` | `#A1A1AA` | Texto secundário |
| `--muted` | `#71717A` | Texto terciário |

Tema escuro consistente com fundo `#09090B` e glow ambiental via gradientes radiais em indigo/gold.

### Tipografia
| Variável | Fonte | Uso |
|---|---|---|
| `--font-heading` | Space Grotesk (400–700) | Títulos H1–H3, nomes de planos |
| `--font-body` | Inter (300–900) | Corpo de texto, botões, labels |
| `--font-data` | JetBrains Mono (400–700) | Números, percentuais, rankings, badges de dados |

Fontes carregadas via Google Fonts no `<head>`. No layout Next.js, `Geist` e `Geist_Mono` são declaradas mas afetam apenas as páginas React (não o HTML estático da home).

### Tom de comunicação
- Direto, técnico mas acessível. Evita superlativos vagos; ancora cada claim em dados ("214 questões globais", "35 questões específicas de Banca+Área").
- Posicionamento anti-achismo: repetição deliberada de "dados reais", "verificável", "transparente".
- CTA principal é "Assinar agora" (conversão direta, sem free trial).

---

## 8. Outros Arquivos Relevantes

- `lib/leads-api.ts` — cliente HTTP para `/leads/bancas`, `/leads/editais`, `/leads/editais/{slug}` via API interna com `x-api-key`. Usado pelas páginas React de bancas e editais. **O nome "leads" é interno/técnico** — não indica captura de leads de marketing; é o endpoint de dados públicos de editais.
- `lib/public-api.ts` — cliente alternativo para dados públicos de editais (diferente do `leads-api`).
- `lib/json-ld.ts` — helpers para gerar JSON-LD (Organization, SoftwareApplication, FAQ).
- `lib/banca-profiles.ts` — dados de perfis de bancas.
- `instrumentation-client.ts` — inicialização do PostHog no client-side para páginas React.
- `app/sitemap.ts` — geração automática do sitemap XML.
- `posthog-setup-report.md` — relatório interno de implementação do PostHog.
- `public/amostras/` — PDFs de amostras de análise (referenciados por `data-sample-pdf` em alguns CTAs).
- `public/screenshots/` — screenshots do produto para o carrossel da landing page.

---

## Conclusão para o Projeto Escuta

O site da Bizzu é uma landing page de conversão direta sem nenhum ponto de captura de dados do visitante antes do pagamento. Isso representa uma lacuna clara: visitantes que não convertem na primeira visita são completamente perdidos. O Escuta pode preencher exatamente essa lacuna com um opt-in de WhatsApp contextualizado — especialmente nas páginas de edital (`/editais/[slug]`), onde o visitante já demonstrou intenção específica por um concurso. A integração com NPS pós-assinatura (via `plataforma.bizzu.ai`) é o gancho natural já identificado nos demais arquivos do projeto.
