# Relatório do agente — Frontend Bizzu (gabarita-ai/frontend)

> Exploração automática em 07/06/2026. Clone local: `~/Documents/Projetos/bizzu-repos/frontend`.

## 1. Stack técnico

- **Vite** 6.0.3 + **React** 18.3.1 + React Router DOM 7.13
- **Tailwind CSS** 4.0 + Framer Motion 12
- Radix UI (tooltip), Lucide React (ícones), React Hot Toast, **React Phone Number Input** (validação de telefone), React Quill
- **API REST** (`/auth/`, `/user/`, `/nps/`...), auth `Authorization: Bearer {token}` em localStorage
- **PostHog** (analytics + feature flags), **Stripe** 5.6
- State: Context API + hooks (`AuthContext`, `CurrentEditalContext`, `StudyRoutineContext`)

## 2. Signup/Onboarding — onde adicionar opt-in WhatsApp

### Signup
- **Arquivo:** `src/pages/Signup.jsx`
- **Telefone JÁ capturado:** campo `phoneNumber` via `<PhoneInputField />` (linhas 286-298), validação `isValidPhoneNumber()` (libphonenumber-js)
- Payload ao backend: `{primeiroNome, ultimoNome, email, telefone, password}`
- **Melhor lugar pro checkbox de opt-in:** após linha 299 (logo abaixo do telefone) — passar `whatsappOptIn: boolean` no payload

### Onboarding (escolher edital)
- `src/pages/OnboardingPage.jsx` — só seleção de edital/cargo; não é o lugar do opt-in

### Rotina de estudo (setup pós-pagamento)
- `src/pages/onboarding-rotina/OnboardingRotina.jsx` — horas/dia; secundário

## 3. Perfil/Configurações

**Arquivo principal:** `src/pages/MinhaContaPage.jsx`

```
MinhaContaLayout (sidebar)
├─ /minha-conta/dados-cadastrais → DadosCadastraisSection  (nome, email, TELEFONE, CPF)
├─ /minha-conta/rotina-de-estudo → RotinaDeEstudoSection
├─ /minha-conta/trocar-senha     → TrocarSenhaSection
└─ /minha-conta/assinatura       → MinhaAssinaturaPage
```

Adicionar seção "Preferências de Comunicação" (toggles WhatsApp NPS / marcos) na DadosCadastraisSection (linhas 117-307). Endpoint sugerido: `PATCH /user/me/communication-preferences`.

## 4. Momentos-chave da jornada (telas)

### (a) Plano de estudos gerado
- `src/pages/PlanoDeEstudoPage.jsx` — `handleGeneratePlan()` L118-137; sucesso L427-449
- Disparo sugerido após L343 (`setAiPlan(plan)`)

### (b) Conclusão de sessão/tópico
- `src/pages/QuestaoSessaoPage.jsx` — fase `resumo` (L87-93) via `onFinish()`; componente `QuestaoSessionResumoView` mostra acertos
- Hooks: `useSessaoIA()` / `useSessaoManual()`

### (c) Cancelamento de assinatura
- `src/pages/MinhaAssinaturaPage.jsx` — `handleCancel()` L101-140 com `window.confirm()`
- ✓ **Exit survey JÁ EXISTE**: NpsModal é disparado; `trackEvent('subscription_cancelled')` na L126

### (d) NPS in-app JÁ EXISTE
- `src/components/NpsModal.jsx` — modal NPS 1-10 + textarea opcional
- `src/hooks/useNpsCheck.js` — checa `GET /nps/check`
- Submit: `submitNps(trigger, score, comment)` → `POST /nps` (via `npsApi.js`)

## 5. Design system (brand tokens)

**Arquivo:** `src/theme/brand-tokens.css`

```css
--indigo: #6c5ce7 (primária/CTA)  --indigo-deep: #5b4bcf  --indigo-light: #a78bfa  --indigo-wash: #f0ebff
--gold: #f5a623 (acento)          --gold-soft: #fbbf24    --gold-wash: #fff8eb
--success: #10b981                --alert: #ef4444
/* dark-first */
--void: #0c0b10 (fundo)  --ink: #14131a  --card: #1a1920  --charcoal: #28272e (borders)
--muted: #6e6d78  --silver: #a09fac  --canvas: #f9f8fc (texto primário)
/* tipografia */
--font-heading: "Space Grotesk"   --font-body: "DM Sans"
/* espaçamento 8px base; radius 6/10/14/20/full */
```

## 6. As 3 melhores oportunidades de UI

1. **Signup** (maior taxa bruta, ~40-50%): checkbox junto do telefone — `Signup.jsx` pós-L299
2. **Pós-pagamento** (melhor contexto psicológico, ~35-45%): card CTA em `PagamentoSucessoPage.jsx` (antes da L214)
3. **Minha Conta** (melhor qualidade, ~60-70% de re-opt-in): seção de preferências em `MinhaContaPage.jsx`

## 7. Rotas relevantes

```
POST  /auth/signup                  GET  /nps/check
POST  /auth/login                   POST /nps
GET   /user/me                      POST /plano-estudo-ia/gerar
PATCH /user/me                      PATCH /user/subscription/cancel
```

**Conclusão:** a Bizzu já tem infraestrutura de feedback (NPS in-app) funcionando. A integração Escuta é viável em 3 touchpoints; telefone já é capturado e validado; design system bem definido facilita white-label.
