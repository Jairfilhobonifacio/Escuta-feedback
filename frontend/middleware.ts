/**
 * Middleware de UX da sessão do operador.
 *
 * Checa apenas a PRESENÇA do cookie httpOnly `escuta_session` para decidir entre
 * mostrar o painel ou mandar para /login. NÃO valida a assinatura do JWT — a
 * validação REAL é no FastAPI (`require_operator`): um cookie forjado (string
 * qualquer) passa por aqui mas é rejeitado pelo backend com 401. Logo isto é só
 * conforto de navegação, não um controle de segurança.
 *
 * O `matcher` exclui:
 *   - /api/*      → o proxy BFF cuida do 401 (e do /api/auth/* público);
 *   - /_next/*    → assets/chunks do Next;
 *   - /login      → senão entraríamos em loop de redirect;
 *   - favicon e arquivos estáticos com extensão.
 */

import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "escuta_session";

export function middleware(req: NextRequest) {
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  const { pathname } = req.nextUrl;

  // Já logado tentando ver /login → manda para a home.
  if (pathname === "/login") {
    if (hasSession) {
      return NextResponse.redirect(new URL("/", req.url));
    }
    return NextResponse.next();
  }

  // Rota protegida sem sessão → /login (preserva o destino em ?next=).
  if (!hasSession) {
    const url = new URL("/login", req.url);
    if (pathname && pathname !== "/") url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Tudo MENOS: api, _next/static, _next/image, favicon, /login e arquivos
  // com extensão (ex.: .png, .svg, .ico) — esses não passam pelo gate.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|login|.*\\.[\\w]+$).*)"],
};
