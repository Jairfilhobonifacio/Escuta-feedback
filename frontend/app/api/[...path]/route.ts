/**
 * Proxy BFF (Backend-for-Frontend) — server-side.
 *
 * Route handler catch-all que recebe TODA chamada que o painel faz para
 * `/api/...` (same-origin, no servidor do Next) e a repassa para o backend
 * FastAPI do Escuta. Existe por dois motivos:
 *
 *   1) A chave da API (`PANEL_API_KEY`) NUNCA chega ao browser. Ela é injetada
 *      aqui, no servidor, no header `X-Panel-Key`. Por isso é env SERVER-SIDE
 *      (sem prefixo NEXT_PUBLIC) — o browser jamais a vê.
 *   2) Elimina CORS: o browser fala só com a própria origem (o painel); quem
 *      cruza para o backend é este handler (server→server).
 *
 * O front (`lib/api.ts`) chama caminhos relativos (`/api/central/overview`, …),
 * que caem aqui como `path = ["central", "overview"]`. Reconstruímos a URL do
 * backend, repassamos método/query/corpo e devolvemos status + corpo crus —
 * inclusive erros (não "derrubamos" a resposta: o status real volta ao front,
 * que já sabe tratar 4xx/5xx em `request()`).
 */

import { NextRequest } from "next/server";

// Sempre dinâmico: é um proxy, nada de cache/estático no build.
export const dynamic = "force-dynamic";
// Precisa do runtime Node (não Edge): fetch server→server + headers livres.
export const runtime = "nodejs";

/** Base do backend FastAPI. Env SERVER-SIDE (sem NEXT_PUBLIC). Em dev cai no
    localhost:8000 padrão. Tiramos barras finais para não duplicar com o path. */
const API_BASE = (process.env.ESCUTA_API_URL || "http://localhost:8000").replace(/\/+$/, "");

/** Headers da resposta do backend que NÃO devem ser repassados ao browser
    (são gerenciados pelo runtime do Next / não fazem sentido cross-hop). */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
]);

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  // path = segmentos depois de /api → reconstrói /api/<...> + querystring.
  const suffix = (path ?? []).map(encodeURIComponent).join("/");
  const search = req.nextUrl.search; // já inclui o "?" (ou "")
  const target = `${API_BASE}/api/${suffix}${search}`;

  // Repassa só o essencial. Content-Type preserva o corpo; X-Panel-Key é a
  // credencial injetada AQUI (server-side) quando a env existir.
  const headers: Record<string, string> = {};
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  const accept = req.headers.get("accept");
  if (accept) headers["accept"] = accept;
  if (process.env.PANEL_API_KEY) headers["x-panel-key"] = process.env.PANEL_API_KEY;

  // Corpo: só para métodos que carregam payload. Lê cru (preserva JSON exato).
  const method = req.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD" && method !== "DELETE";
  const body = hasBody ? await req.text() : undefined;

  try {
    const res = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });

    // Repassa status + corpo crus; filtra headers hop-by-hop.
    const outHeaders = new Headers();
    res.headers.forEach((value, key) => {
      if (!HOP_BY_HOP.has(key.toLowerCase())) outHeaders.set(key, value);
    });

    const buf = await res.arrayBuffer();
    return new Response(buf, {
      status: res.status,
      statusText: res.statusText,
      headers: outHeaders,
    });
  } catch (err) {
    // Backend fora do ar / inalcançável: devolve 502 com detalhe (não derruba
    // o handler). O front trata como ApiError(502, …).
    const detail = err instanceof Error ? err.message : "upstream unreachable";
    return new Response(JSON.stringify({ detail: `proxy: ${detail}` }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
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
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
