# Bizzu — Frontend (app web do concurseiro)

Análise profunda do repositório `bizzu-repos/frontend`. Leitura apenas; nada foi modificado.
SPA React + Vite, dark-mode, em `https://plataforma.bizzu.ai`. ~442 arquivos `.js/.jsx` em `src/`, 82 arquivos de teste.

---

## 0. Resumo executivo (o que importa pro Escuta)

- **Já existe NPS in-app nativo** (`NpsModal` + `useNpsCheck`) que dispara dentro do **Plano de Estudo** em marcos de progresso (primeira sessão, 50% da meta, meta concluída). Grava score 0–10 + comentário no backend via `POST /nps`. É o concorrente/aliado direto do produto Escuta — vale espelhar a mesma lógica de gatilho para o canal WhatsApp.
- **A equipe da Bizzu já tem painel de NPS** (`/gestao/nps`, `GestaoNpsPage`) com gauge, distribuição, NPS por gatilho, evolução semanal e lista de comentários paginada. E **já tem central de atendimento/tickets** (`/gestao/atendimentos`) com thread por email, status, prioridade e anexos. Ou seja: a "Voz do Cliente" interna existe, mas presa ao app web; o Escuta entra como camada WhatsApp.
- **Captura de telefone existe e é OPCIONAL** no signup (`telefone` → backend). O número é validado por `libphonenumber-js` (`isValidPhoneNumber`). É o gancho natural de opt-in.
- **Opt-in de WhatsApp JÁ FOI PLUGADO localmente por nós** em dois lugares: checkbox `whatsappOptIn` no `Signup.jsx` (aparece só quando há telefone válido) e toggle na aba "Dados cadastrais" da `MinhaContaPage.jsx`. Ambos mandam `whatsappOptIn` no corpo (`POST /auth/signup` e `PATCH /user/me`). **Depende de o backend persistir o campo** (o front já lê `data.whatsappOptIn`).
- **NÃO há exit survey no cancelamento.** `MinhaAssinaturaPage` cancela com um `window.confirm` seco (`POST /user/subscription/cancel`) e dispara só o evento `subscription_cancelled` (refund). Zero captura de motivo. É a **maior lacuna/oportunidade** para o Escuta: gatilho de churn com pesquisa de saída via WhatsApp.
- **Telemetria é PostHog + GA**, com `trackEvent()` instrumentado de ponta a ponta (funil de signup campo-a-campo, checkout passo-a-passo, NPS, churn). Eventos como `subscription_cancelled`, `nps_submitted`, `user_signed_up` são candidatos a webhooks/gatilhos para o Escuta.
- **Auth é JWT em `localStorage`** (`token`), enviado como `Bearer` em todo request; sem cookies de sessão de API. Backend REST puro (`VITE_API_URL`), chamado direto via `fetch` (sem axios/react-query).
- **Identidade visual:** indigo `#6C5CE7` (primária), gold `#F5A623` (accent), fundo quase-preto `#0c0b10`; fontes Space Grotesk (títulos) + DM Sans (corpo). Slogan "Estude o que importa." Tokens centralizados em `theme/brand-tokens.css`.

---

## 1. Stack & build

`package.json` (`name: bizzu-frontend`, `type: module`, Node ≥22):

- **Build:** Vite **6** (`vite.config.js`) + `@vitejs/plugin-react`. Scripts: `dev`, `build` / `build:staging` / `build:production` (por `--mode`), `preview`. Sem TypeScript (JSX puro).
- **UI:** React **18.3** + React DOM. **Tailwind CSS v4** via `@tailwindcss/vite` (config CSS-first em `index.css` com `@theme`, sem `tailwind.config.js`). Ícones `lucide-react`. Animações `framer-motion`. Tooltips `@radix-ui/react-tooltip`. Editor rich text `react-quill` (comentários). `react-helmet-async` (head). Toasts `react-hot-toast`.
- **Roteamento:** `react-router-dom` **7** (modo declarativo `<Routes>`; README diz "v6" mas o pinned é 7).
- **Estado:** **sem Redux/Zustand**. Context API (`AuthContext`, `CurrentEditalContext`, `StudyRoutineContext`, `ThemeContext`) + `useState`/`useReducer` locais. Sem react-query — fetch manual em cada página/hook.
- **Forms:** sem lib de form. Estado controlado manual + validação custom (`utils/passwordValidation.js`, regex de email). Telefone com `react-phone-number-input` + `libphonenumber-js`.
- **Pagamento:** **Stripe.js** — `@stripe/stripe-js` + `@stripe/react-stripe-js` (re-exportados em `src/external-libraries/stripe.js`). `CardElement` + `confirmCardPayment`. **Pix** como método alternativo (QR code via API própria, não Stripe).
- **Analytics/telemetria:** **PostHog** (`posthog-js` + `@posthog/react`, init em `main.jsx` com session recording e `PostHogErrorBoundary` global) **e Google Analytics** (`analytics/gtag.js`, `initGtag`/`sendPageView` no `App.jsx`).
- **Segurança/util:** `dompurify` (sanitização de HTML, `external-libraries/sanitizeHtml.js`).
- **Testes:** **Vitest 4** + Testing Library + jsdom (`vitest.config.js`, `vitest.setup.js`). 82 arquivos `*.test.*` (co-locados, focados em view-models/lógica pura — ver §8).
- **Como roda (dev):** `npm run dev` → Vite na 5173, **proxy `/api` → `http://localhost:3000`** (rewrite tira o `/api`). `host: 0.0.0.0`, allowedHost ngrok hardcoded. Build é dockerizado (`Dockerfile` multi-stage + `nginx.conf`); landing-page estática em `public/landing-page.html` servida fora do SPA.

Build injeta commit/data git via `define` (`__FRONTEND_COMMIT__`, `__FRONTEND_DATE__`) — exibidos em `/version` (`VersionPage`).

---

## 2. Mapa de páginas (`src/pages/`)

Rotas definidas em `src/App.jsx` (entry: `main.jsx` → providers PostHog/Theme/Auth/Router → `App`). Layout global: `Header` + `Footer` + `PastDueBanner` + `ServiceSessionBanner` + `ActivationNoticeOverlay`.

### Públicas / auth
| Página (arquivo) | Rota | O que faz |
|---|---|---|
| `Login.jsx` | `/login` | Login email+senha e Google OAuth (`/auth/google`). |
| `Signup.jsx` | `/signup` | Cadastro (nome, email, **telefone opcional + checkbox whatsappOptIn**, senha c/ regras). Aceita `?plano=mensal\|anual`. Auto-login → `/checkout`. |
| `ForgotPasswordPage` / `ResetPasswordPage` | `/auth/forgot-password`, `/auth/reset-password` | Fluxo de recuperação de senha. |
| `AuthCallbackPage` | `/auth/callback` | Recebe token do OAuth Google e seta sessão. |
| `DescadastroPage` | `/descadastro` | Opt-out de comunicações (unsubscribe). |
| `ContatoPage` / `ReportarErroPage` / `PerguntasFrequentesPage` | `/contato`, `/reportar-problema`, `/perguntas-frequentes` | Contato (cria atendimento via `POST /contact`); reportar-erro é stub "em construção"; FAQ. |
| `VersionPage` | `/version` | Mostra commit/data do build. |

### Pagamento
| Página | Rota | O que faz |
|---|---|---|
| `CheckoutPage.jsx` | `/checkout` | **Núcleo de conversão.** Seleção de plano (mensal/anual) + Stripe `CardElement` ou Pix (com captura de CPF p/ Pix). Telemetria densa. |
| `PagamentoSucessoPage` / `PagamentoFalhaPage` / `PagamentoPendentePage` | `/pagamento/{sucesso,falha,pendente}` | Retorno pós-pagamento. |
| `PagamentoPixPage` / `RenovarPixPage` | `/pagamento/pix`, `/renovar-pix` | Exibe QR Pix e faz polling de confirmação; renovação Pix. |
| `BemVindoPage` | `/bem-vindo` | Boas-vindas pós-assinatura. |
| `EscolhaSeuPlanoPage` | `/escolha-seu-plano` | **Redirect** → `/minha-conta/assinatura`. |

### App do aluno (gated: `RequireAuth` → `RequirePlan` → `OnboardingGate` → `RequireCurrentEdital` + `RequireStudyRoutine`, dentro de `SidebarLayout`)
| Página | Rota | O que faz |
|---|---|---|
| `OnboardingPage.jsx` | `/onboarding` | Escolha do **contexto de estudo** (edital + cargo). Libera dashboard/Raio X/plano. Permite reusar contexto existente ou pedir edital faltante. |
| `onboarding-rotina/OnboardingRotina.jsx` | `/onboarding/rotina` | Define **rotina** (horas/dia por dia da semana). Recalcula prazos sem regerar plano. |
| `Dashboard.jsx` | `/dashboard` | Painel do aluno: progresso, cards de resumo, desempenho por matéria, tile do caderno. |
| `RaioXDaProvaPage.jsx` | `/raio-x-da-prova` | **Diferencial do produto.** "Raio X da prova": matérias/tópicos priorizados quantitativamente por incidência em questões reais; critérios e legenda de prioridade. (`GET /user-editais/:id/raio-x`) |
| `PlanoDeEstudoPage.jsx` | `/plano-de-estudo` | **Hub central de estudo.** Metas/tópicos, cronômetro de estudo, registrar estudo, abrir questões/anotações. **Onde o NpsModal é montado.** |
| `QuestoesPage.jsx` | `/questoes` | Lista/filtro de questões do edital. |
| `QuestoesFavoritasPage` / `QuestoesListaDetailPage` / `QuestaoDetailPage` | `/questoes/favoritas`, `/questoes/listas/:id`, `/questoes/questao/:id` | Favoritas, listas salvas, detalhe da questão (comentário IA, reportar erro). |
| `QuestaoSessaoPage.jsx` | `/questoes/sessao` | Sessão de resolução **fullscreen** (Header some). Modos IA/manual (`useSessaoIA`/`useSessaoManual`). |
| `CadernoHomePage` / `CadernoTopicoPage` | `/caderno`, `/caderno/topicos/:topicoId` | "Caderno" de erros/favoritas/notas por tópico, com autosave de anotações. |

### Conta / assinatura
| Página | Rota | O que faz |
|---|---|---|
| `MinhaContaPage.jsx` (`MinhaContaLayout` + seções) | `/minha-conta/*` | Dados cadastrais (**+ toggle whatsappOptIn + CPF**), rotina de estudo, trocar/definir senha. |
| `MinhaAssinaturaPage.jsx` | `/minha-conta/assinatura` | Ver assinatura, **cancelar** (window.confirm, sem survey), trocar de plano, retomar Pix pendente. |
| `MeusEditais.jsx` | `/meus-editais` | Editais/cargos do usuário. |

### Gestão/admin — ver §6.

---

## 3. Jornada do usuário (concurseiro)

Fluxo gated em cascata (cada gate redireciona se a etapa anterior falta):

1. **Descoberta → Signup.** Landing estática (`public/landing-page.html`, fora do SPA) com CTAs `…/signup?plano=mensal|anual`. `Signup.jsx` salva o plano (`utils/planoCheckout.js`) e cria conta (`POST /auth/signup`). Telefone é opcional; nosso checkbox de opt-in WhatsApp aparece quando o telefone é válido. Auto-login → `/checkout`.
2. **Pagamento.** `CheckoutPage` (gate `RequireAuth`): escolhe plano (mensal/anual, anual com "Economia 50%") e paga por **Stripe** (cartão) ou **Pix** (gera QR, exige CPF). Sucesso → `refetchUser()` (atualiza `planId` no JWT) → `/bem-vindo`.
3. **Onboarding de contexto.** `RequirePlan` libera `/onboarding`: escolher **edital + cargo** (contexto de estudo, salvo em storage + `CurrentEditalContext`). `OnboardingGate` garante que há contexto.
4. **Onboarding de rotina.** `/onboarding/rotina`: horas por dia. `RequireStudyRoutine` exige rotina antes de Raio X/plano/questões.
5. **Estudo (núcleo).** `RequireCurrentEdital` + `RequireStudyRoutine` liberam:
   - **Raio X** (`/raio-x-da-prova`): o que priorizar.
   - **Plano de Estudo** (`/plano-de-estudo`): metas/tópicos, cronômetro, registrar sessões, revisões, abrir questões/anotações. **É aqui que o NPS dispara** nos marcos.
   - **Questões** / sessões (IA/manual) e **Caderno** (erros, favoritas, notas).
6. **Conta & assinatura.** Header → dropdown → "Minha conta" / "Sair". `MinhaContaPage` (dados/rotina/senha) e `MinhaAssinaturaPage` (cancelar/trocar plano). `PastDueBanner` global avisa inadimplência; `RenovarPixPage` para renovar Pix.

Cada etapa está instrumentada com `trackEvent` (PostHog/GA).

---

## 4. Integração com o backend

- **Cliente HTTP:** `fetch` nativo direto, **sem axios nem react-query**. Cada arquivo em `src/api/*` (32 módulos) ou página monta a chamada na mão.
- **Base URL:** `import.meta.env.VITE_API_URL` (centralizado em `config/app.config.js` → `appConfig.api.baseUrl`, lido por `utils/planoEstudoApi.js::getPlanoEstudoApiUrl()`). Em dev, `vite.config.js` proxia `/api`.
- **Auth/JWT:** token em `localStorage['token']`. `getAuthHeaders()` (`utils/planoEstudoApi.js`) injeta `Authorization: Bearer <token>` + header fixo `ngrok-skip-browser-warning: true` (`getDefaultApiHeaders`). **Sem refresh-token rotativo via cookie**: `AuthContext.fetchUser()` chama `GET /user/me` no boot e dispara `POST /auth/refresh` em background para manter `planId` em sincronia. Logout → `POST /auth/logout` + limpa storage. Suporta **impersonação** ("service session": `sessionStorage['manager_token']`/`service_session_user`, banner em `ServiceSessionBanner`).
- **Identidade do usuário:** após `/user/me`, faz `posthog.identify(id, {email, name})`.
- **Onde ficam serviços/hooks de dados:**
  - `src/api/*` — wrappers REST por domínio: `npsApi`, `npsGestaoApi`, `atendimentosApi`, `dashboardApi`, `questoesApi`, `planoEstudoIaApi`, `studyRoutineApi`, `desempenhoApi`, `cadernoApi`, `editalExtractorApi`, `userEditaisApi`, `siteContentApi`, etc.
  - `src/hooks/*` — `useNpsCheck`, `useUserEditais`, `useSessaoBase/IA/Manual/Persistence`, `useFeatureFlag`.
  - Contexts em `src/context/*`.
- **Padrão de chamada:** `const res = await fetch(url, {headers: getAuthHeaders()}); if (!res.ok) throw/return null; return res.json()`. Erros geralmente engolidos com toast (`react-hot-toast`).
- **Endpoints-chave observados:** `/auth/{signup,login,logout,refresh,google}`, `/user/me` (+ `/cpf`, `/set-password`, `/change-password`, `PATCH` perfil), `/user/subscription` (+ `/cancel`, `/change-plan`), `/planos`, `/payments/create-checkout`, `/platform-config`, `/nps` (+ `/nps/check`), `/contact`, `/gestao/nps/{summary,comments}`, `/gestao/atendimentos/*`, `/user-editais/:id/raio-x`.

---

## 5. Feedback no front (CRÍTICO p/ Escuta)

### NpsModal + useNpsCheck (NPS in-app nativo)
- **Hook** `src/hooks/useNpsCheck.js`: expõe `{ npsTrigger, triggerCheck, clearTrigger }`. `triggerCheck()` chama **`GET /nps/check`** (`api/npsApi.js::checkNps`) que retorna `{ trigger }` (string do marco) ou null. Guard de **uma vez por sessão de navegação** (flag módulo-global `checkedThisSession`) + ref anti-concorrência. Falhas são silenciosas ("NPS não pode quebrar o fluxo principal").
- **Onde dispara:** apenas em `PlanoDeEstudoPage.jsx`. `triggerCheck()` é chamado: (a) após carregar o plano IA (`fetchAiPlan`, fim do load); (b) após qualquer `onTaskUpdate` (concluir/atualizar meta). O backend decide o gatilho; o front só pergunta. Gatilhos conhecidos (de `GestaoNpsPage`): **`FIRST_SESSION`** (primeira sessão), **`GOAL_HALF`** (50% da meta), **`GOAL_COMPLETE`** (meta concluída).
- **Modal** `src/components/NpsModal.jsx`: card flutuante bottom-center. Pergunta "De 1 a 10, qual a chance de você recomendar a Bizzu para um amigo?", grid 1–10, textarea opcional (≤500 chars). Categoriza PROMOTER(9-10)/PASSIVE(7-8)/DETRACTOR(≤6).
  - **Envia** `POST /nps` (`submitNps`) com `{ trigger, score, comment }`. Dismiss manda `score:null, comment:null` (registra "dismissal"). Auto-fecha 1.8s após envio.
  - Telemetria PostHog: `nps_shown`, `nps_score_selected`, `nps_submitted`, `nps_dismissed`.
- **Relevância p/ Escuta:** a lógica de gatilho por marco de jornada é exatamente o que o Escuta quer reproduzir no WhatsApp. O endpoint `/nps/check` já funciona como "motor de elegibilidade". Espelhar isso (ou consumir o mesmo sinal) evita duplicar regra de negócio.

### Exit survey no cancelamento — **NÃO EXISTE**
- `MinhaAssinaturaPage.jsx::handleCancel`: só um `window.confirm("Tem certeza que deseja cancelar…")`, depois `POST /user/subscription/cancel`. Dispara `trackEvent('subscription_cancelled', { refund_amount_cents })`. **Nenhum campo de motivo, nenhuma pesquisa de saída.** Esta é a oportunidade #1 do Escuta: pesquisa de churn (motivo de cancelamento) — seja inline aqui, seja via WhatsApp pós-cancelamento disparada pelo evento `subscription_cancelled`.

### Captura de telefone no signup
- `Signup.jsx`: campo "Celular (opcional)" via `PhoneInputField` (`react-phone-number-input` + `libphonenumber-js`). Validado por `isValidPhoneNumber`. Vai como `telefone` no `POST /auth/signup` (apenas se preenchido). Telefone também aparece em `ContatoPage` (pré-preenchido do user) e nos tickets de atendimento.

### Onde plugar opt-in de WhatsApp (e o que já fizemos localmente)
- **Signup (`Signup.jsx`):** estado `whatsappOptIn` no form; **checkbox condicional** que só renderiza quando há telefone válido ("Topo receber pesquisas e avisos do Bizzu no WhatsApp. Sem spam — dá pra sair quando quiser."). Enviado no body como `whatsappOptIn: form.phoneNumber ? form.whatsappOptIn : undefined`.
- **Minha Conta → Dados cadastrais (`MinhaContaPage.jsx`, `DadosCadastraisSection`):** carrega `whatsappOptIn` de `GET /user/me`; **toggle (checkbox)** "Receber pesquisas e avisos do Bizzu no WhatsApp", desabilitado sem telefone válido ("Adicione um celular para ativar"). Salvo via `PATCH /user/me` com `whatsappOptIn: form.phoneNumber ? form.whatsappOptIn : false`. Limpar o telefone zera o opt-in.
- Ambos comentados como "(Escuta)". **Pendência:** o backend precisa persistir/retornar `whatsappOptIn` no usuário (o front já lê `data.whatsappOptIn`). Confirmar no repo do backend.
- **Outros pontos plugáveis:** `DescadastroPage` (`/descadastro`) é o lugar natural para opt-out de WhatsApp; e os eventos `user_signed_up` / `subscription_cancelled` no PostHog podem acionar fluxos do Escuta.

---

## 6. Área de gestão/admin (`/gestao`, role `MANAGER`)

Gated por `RequireManager` (checa `user.role === 'MANAGER'`), dentro de `GestaoLayout` (sidebar com seções: Visão geral, Email, Cadastros, Comercial, Publicação, Infra, Knowledge Graph, Analytics). ~40 páginas em `src/pages/gestao/`. Destaques para o Escuta:

- **`GestaoNpsPage.jsx`** (`/gestao/nps`, seção "Analytics"): dashboard NPS completo (Recharts) — gauge -100/+100, score médio, total/dismissals, **taxa de resposta**, % promotores/passivos/detratores, distribuição de scores, donut, **NPS por gatilho** (primeira sessão / 50% / meta concluída), **evolução semanal**, e **lista de comentários** paginada com nome/email/score/gatilho/data. Consome `GET /gestao/nps/summary` e `/gestao/nps/comments` (`api/npsGestaoApi.js`).
- **`GestaoAtendimentosPage.jsx`** (`/gestao/atendimentos`): **central de tickets** estilo helpdesk. Lista filtrável (status: aberto/em_atendimento/resolvido/fechado; busca por nome/email/assunto; paginação). Painel de detalhe com **thread de mensagens** (admin × usuário), badges de status/prioridade/tipo (dúvida/erro/reclamação/sugestão), controles de status e prioridade, e **resposta por email com anexos** (`POST /gestao/atendimentos/:id/reply`, multipart, até 5 arquivos/10MB). API em `api/atendimentosApi.js`. Tickets nascem de `POST /contact` (ContatoPage).
- **`GestaoDashboardPage.jsx`** (`/gestao/dashboard`): visão geral com cards (faturamento, assinantes, NPS resumido via `npsColor`, atendimentos via `fetchAtendimentosStats`), solicitações de editais e cargos pendentes, filtro por período.
- Demais (fora do escopo Escuta): operação editorial, importar/extrair editais (com IA, `EditalExtractor`), importar questões, fila de processamento, knowledge graph, LLM observabilidade, radar de editais/matches, cadastros (editais/cargos/matérias/órgãos/bancas/áreas), comercial (assinantes/pagamentos/planos/reajuste/plataforma), email (boas-vindas/marketing), publicação de editais/conteúdo de site.

**Leitura p/ Escuta:** a Bizzu já internaliza NPS + atendimento. O Escuta não substitui isso — complementa com o **canal WhatsApp** (coleta proativa, churn survey, alcance de quem não abre o app). Idealmente o Escuta alimenta os mesmos dashboards (ou um equivalente) com o feedback vindo do WhatsApp.

---

## 7. Identidade visual

Tokens em `src/theme/brand-tokens.css` (fonte: `guideline/brand-guidelines-bizzu.html`), expostos ao Tailwind v4 em `src/index.css` (`@theme`):

- **Cores:** primária **indigo `#6C5CE7`** (`--indigo`; deep `#5B4BCF`, light `#A78BFA`, wash `#F0EBFF`). Accent **gold `#F5A623`** (`--gold`; usado no ponto da logo "Bizzu·" e em planos anuais). Estados: success `#10B981`, alert/erro `#EF4444`. Neutros escuros levemente tintados para indigo: void `#0c0b10` (fundo), ink `#14131a`, card `#1a1920`, charcoal `#28272e`, muted `#6e6d78`, silver `#a09fac`, canvas `#f9f8fc` (texto claro).
- **Tema claro:** suportado via `[data-theme="light"]` (`ThemeContext` + `ThemeToggle`), com overrides de tokens e classes utilitárias (`.sidebar-bg`, `.dashboard-card-*`, etc.) e correções de contraste.
- **Fontes:** títulos **Space Grotesk** (`--font-heading`), corpo **DM Sans** (`--font-body`); `font-variant-numeric: tabular-nums`. (Quill/dados usam família "data".)
- **Raios/espaços/easing:** escala de radius (6→100px), espaçamento (4→96px), `--ease-out: cubic-bezier(0.16,1,0.3,1)`. Respeita `prefers-reduced-motion`; foco visível com outline indigo.
- **Design system / componentes base:** `src/components/ui/` — `Button`, `Input`, `Card`, `Badge`, `SplitButton` (pequeno, não é shadcn). Muitos componentes de domínio em `src/components/**` (Dashboard, RaioX, Caderno, EditalExtractor, Checkout, ActivationNotice, gestao). Branding da marca: logo textual "Bizzu" + ponto gold + slogan "Estude o que importa." (Header).

---

## 8. Qualidade / dívida técnica

**Pontos fortes**
- **Telemetria de produto excelente:** `trackEvent` (PostHog + GA) cobre funil de signup campo-a-campo (`signup_field_focused/errored`), checkout passo-a-passo (`checkout_*`, incl. erros Stripe com decline_code), NPS e churn. Ótimo manancial de gatilhos para o Escuta.
- **Error boundary global** (`PostHogErrorBoundary` em `main.jsx`) com fallback amigável e captura de exceções.
- **Gating de rotas robusto** e em cascata; impersonação/service-session prevista.
- **Sanitização** com DOMPurify; CPF descrito como AES-256; Stripe não toca o servidor.
- **82 arquivos de teste** (Vitest), majoritariamente sobre **view-models e lógica pura** co-locada (`*.viewModel.test.js`, `cadernoTopicoPresentation.test.js`, `concursoDraftState.test.js`, etc.) e alguns components/guards (`RequirePlan.test.jsx`, `PastDueBanner.test.jsx`, `OnboardingGate.test.jsx`).

**Dívidas / pontos frágeis**
- **JWT em `localStorage`** (exposto a XSS). Sem refresh-token httpOnly; refresh é fetch manual em background.
- **Sem camada HTTP unificada:** `fetch` repetido em dezenas de arquivos; tratamento de erro inconsistente (ora toast, ora silêncio, ora `alert()` nativo em `GestaoAtendimentosPage`). Sem retry/cache (react-query ausente) → re-fetch manual e flicker.
- **`ReportarErroPage` é stub** ("em construção") embora linkada — caminho de feedback morto.
- **Cancelamento sem captura de motivo** (`window.confirm` cru) — perda de sinal de churn (lacuna p/ Escuta).
- **`whatsappOptIn` depende do backend** persistir/retornar o campo; se o backend ignorar, o toggle "funciona" no UI mas não tem efeito.
- **Inconsistências menores:** README diz "React Router v6"/rotas `/plano-de-estudos`,`/raio-x` que não batem com as rotas reais (`/plano-de-estudo`, `/raio-x-da-prova`); allowedHost ngrok e proxy `localhost:3000` hardcoded no `vite.config.js`; alguns textos com encoding/typo ("Topo receber" no checkbox de opt-in — provável "Topo/Topa"; "Voce"/"nao" sem acento em strings do CheckoutPage).
- **Sem TypeScript:** validação de shapes de API só em runtime; risco de drift com o backend.
- Página de Plano de Estudo é muito grande/stateful (cronômetro, modais, NPS) — candidata a refactor.

---

### Apêndice — arquivos-âncora (caminhos absolutos)

- Roteamento/entry: `C:\Users\jboni\Documents\Projetos\bizzu-repos\frontend\src\App.jsx`, `…\src\main.jsx`
- HTTP/Auth: `…\src\utils\planoEstudoApi.js`, `…\src\context\AuthContext.jsx`, `…\src\config\app.config.js`
- **NPS in-app:** `…\src\hooks\useNpsCheck.js`, `…\src\components\NpsModal.jsx`, `…\src\api\npsApi.js`, montado em `…\src\pages\PlanoDeEstudoPage.jsx`
- **Opt-in WhatsApp (nosso):** `…\src\pages\Signup.jsx` (checkbox), `…\src\pages\MinhaContaPage.jsx` (toggle em `DadosCadastraisSection`)
- **Churn (sem survey):** `…\src\pages\MinhaAssinaturaPage.jsx`
- Checkout/Stripe+Pix: `…\src\pages\CheckoutPage.jsx`, `…\src\external-libraries\stripe.js`
- Gestão feedback: `…\src\pages\gestao\GestaoNpsPage.jsx`, `…\src\pages\gestao\GestaoAtendimentosPage.jsx`, `…\src\api\npsGestaoApi.js`, `…\src\api\atendimentosApi.js`
- Telemetria: `…\src\utils\analytics.js`, `…\src\analytics\gtag.js`
- Tokens/visual: `…\src\theme\brand-tokens.css`, `…\src\index.css`, `…\src\components\Header.jsx`, `…\src\components\ui\`
