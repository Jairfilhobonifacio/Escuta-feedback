/**
 * Proxy BFF (Backend-for-Frontend) — server-side.
 *
 * Route handler catch-all que recebe TODA chamada que o painel faz para
 * `/api/...` (same-origin, no servidor do Next) e a repassa para o backend
 * FastAPI do Escuta. Existe por três motivos:
 *
 *   1) A chave da API (`PANEL_API_KEY`) NUNCA chega ao browser. Ela é injetada
 *      aqui, no servidor, no header `X-Panel-Key`. Por isso é env SERVER-SIDE
 *      (sem prefixo NEXT_PUBLIC) — o browser jamais a vê.
 *   2) Elimina CORS: o browser fala só com a própria origem (o painel); quem
 *      cruza para o backend é este handler (server→server).
 *   3) SESSÃO DO OPERADOR. O JWT do operador vive num cookie httpOnly
 *      (`escuta_session`) que o JS do browser NÃO consegue ler (defesa anti-XSS).
 *      Em `/api/auth/login` este handler recebe o JWT do FastAPI e o grava no
 *      cookie (sem devolver o token ao browser). Nas demais chamadas, lê o
 *      cookie e injeta `Authorization: Bearer <jwt>` (identidade do operador)
 *      ALÉM do `X-Panel-Key` (trust server→server). Sem cookie em rota
 *      protegida → responde 401 SEM nem chamar o backend.
 *
 * O front (`lib/api.ts`) chama caminhos relativos (`/api/central/overview`, …),
 * que caem aqui como `path = ["central", "overview"]`. Reconstruímos a URL do
 * backend, repassamos método/query/corpo e devolvemos status + corpo crus —
 * inclusive erros (não "derrubamos" a resposta: o status real volta ao front,
 * que já sabe tratar 4xx/5xx em `request()`).
 */

import { NextRequest, NextResponse } from "next/server";

// Sempre dinâmico: é um proxy, nada de cache/estático no build.
export const dynamic = "force-dynamic";
// Precisa do runtime Node (não Edge): fetch server→server + headers livres.
export const runtime = "nodejs";

/** Base do backend FastAPI. Env SERVER-SIDE (sem NEXT_PUBLIC). Em dev cai no
    localhost:8000 padrão. Tiramos barras finais para não duplicar com o path. */
const API_BASE = (process.env.ESCUTA_API_URL || "http://localhost:8000").replace(/\/+$/, "");

/** Nome do cookie de sessão do operador (httpOnly; só o BFF lê/escreve). */
const SESSION_COOKIE = "escuta_session";
/** TTL do cookie = TTL do JWT (12h, em segundos). Espelha JWT_TTL_SECONDS do backend. */
const SESSION_MAX_AGE = 12 * 3600;

/** Headers da resposta do backend que NÃO devem ser repassados ao browser
    (são gerenciados pelo runtime do Next / não fazem sentido cross-hop). */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
]);

/** Flags do cookie de sessão (A.3 do blueprint). `secure` só em produção:
    sobre http://localhost o browser DESCARTA cookies Secure (o login "não
    funciona"). Decisão por NODE_ENV (não pelo APP_ENV do backend). */
function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: SESSION_MAX_AGE,
  };
}

/** Repasse cru de status + corpo + headers (filtra hop-by-hop). Devolve um
    NextResponse para permitir setar cookies por cima quando necessário. */
function passthrough(res: Response, buf: ArrayBuffer | null): NextResponse {
  const outHeaders = new Headers();
  res.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) outHeaders.set(key, value);
  });
  return new NextResponse(buf, {
    status: res.status,
    statusText: res.statusText,
    headers: outHeaders,
  });
}

/** Faz o fetch ao backend e lê o corpo respeitando status sem-corpo. */
async function callBackend(
  target: string,
  method: string,
  headers: Record<string, string>,
  body: string | undefined,
): Promise<{ res: Response; buf: ArrayBuffer | null }> {
  const res = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });
  // Status "sem corpo" (204/205/304) NÃO podem carregar body — nem um
  // ArrayBuffer vazio (o construtor de Response lança).
  const noBody = res.status === 204 || res.status === 205 || res.status === 304;
  const buf = noBody ? null : await res.arrayBuffer();
  return { res, buf };
}

/** JSON helper para respostas que o BFF gera por conta própria (sem backend). */
function json(status: number, body: unknown): NextResponse {
  return NextResponse.json(body, { status });
}

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const segs = path ?? [];
  const method = req.method.toUpperCase();
  const isAuthLogin = segs[0] === "auth" && segs[1] === "login";
  const isAuthLogout = segs[0] === "auth" && segs[1] === "logout";

  // path = segmentos depois de /api → reconstrói /api/<...> + querystring.
  const suffix = segs.map(encodeURIComponent).join("/");
  const search = req.nextUrl.search; // já inclui o "?" (ou "")
  const target = `${API_BASE}/api/${suffix}${search}`;

  // Headers base repassados ao backend.
  const headers: Record<string, string> = {};
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  const accept = req.headers.get("accept");
  if (accept) headers["accept"] = accept;
  // X-Panel-Key (trust server→server) vai em TODA chamada quando a env existir,
  // inclusive no /login (o backend mantém require_panel_key no login).
  if (process.env.PANEL_API_KEY) headers["x-panel-key"] = process.env.PANEL_API_KEY;

  // Corpo: só para métodos que carregam payload. Lê cru (preserva JSON exato).
  const hasBody = method !== "GET" && method !== "HEAD" && method !== "DELETE";
  const body = hasBody ? await req.text() : undefined;

  // --- LOGOUT: limpa o cookie aqui; o backend é stateless (chamada opcional). ---
  if (isAuthLogout) {
    const out = json(200, { ok: true });
    out.cookies.set(SESSION_COOKIE, "", { ...sessionCookieOptions(), maxAge: 0 });
    return out;
  }

  // --- LOGIN: repassa {user,password} ao backend; em 200 grava o JWT no cookie. ---
  if (isAuthLogin) {
    try {
      const { res, buf } = await callBackend(target, method, headers, body);
      // Erro do backend (401 credenciais / 503 não configurado): repassa cru.
      if (!res.ok) return passthrough(res, buf);
      // Sucesso: extrai o token, NÃO o devolve ao browser; grava no cookie.
      let token = "";
      let user = "";
      try {
        const data = buf ? JSON.parse(Buffer.from(buf).toString("utf-8")) : {};
        token = typeof data.token === "string" ? data.token : "";
        user = typeof data.user === "string" ? data.user : "";
      } catch {
        /* corpo inesperado — trata como falha de login */
      }
      if (!token) {
        return json(502, { detail: "login: resposta do backend sem token" });
      }
      const out = json(200, { ok: true, user });
      out.cookies.set(SESSION_COOKIE, token, sessionCookieOptions());
      return out;
    } catch (err) {
      const detail = err instanceof Error ? err.message : "upstream unreachable";
      return json(502, { detail: `proxy: ${detail}` });
    }
  }

  // --- DEMAIS ROTAS: exigem sessão. Sem cookie → 401 sem chamar o backend. ---
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return json(401, { detail: "não autenticado" });
  }
  headers["authorization"] = `Bearer ${token}`;

  try {
    const { res, buf } = await callBackend(target, method, headers, body);
    return passthrough(res, buf);
  } catch (err) {
    // Backend fora do ar / inalcançável: devolve 502 com detalhe (não derruba
    // o handler). O front trata como ApiError(502, …).
    const detail = err instanceof Error ? err.message : "upstream unreachable";
    return json(502, { detail: `proxy: ${detail}` });
  }
}

// No Next 15 o 2º arg traz params como Promise.
type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
