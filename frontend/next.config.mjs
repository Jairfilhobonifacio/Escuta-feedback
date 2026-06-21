/** @type {import('next').NextConfig} */

/* Headers de segurança (M1). Aplicados a TODAS as rotas.
   - HSTS: força https por 2 anos (só tem efeito sobre https; inócuo em dev http).
   - X-Frame-Options DENY + frame-ancestors 'none': sem clickjacking/embed.
   - nosniff: navegador respeita o Content-Type declarado.
   - Referrer-Policy no-referrer: não vaza URL do painel para terceiros.
   - CSP: 'self' por padrão. O painel Next precisa de:
       * style-src 'unsafe-inline'  → estilos inline do Next + styled-jsx;
       * script-src 'unsafe-inline' → bootstrap/hidratação inline do Next;
       * img-src data:              → avatares/QR em data-uri (ex.: WhatsApp QR);
       * font-src gstatic           → next/font (Space Grotesk/Inter/JetBrains);
       * connect-src 'self'         → o front só fala com a própria origem (BFF).
     'unsafe-eval' fica de FORA (não é necessário em prod). Refinar com nonces
     depois. Validar com `next build` + smoke antes de prod. */
const csp = [
  "default-src 'self'",
  "img-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  "font-src 'self' https://fonts.gstatic.com",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Content-Security-Policy", value: csp },
];

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
