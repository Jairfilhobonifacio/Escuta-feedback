"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { auth, ApiError } from "@/lib/api";

/**
 * Tela de login do operador.
 *
 * Manda `{user,password}` para `POST /api/auth/login` (via BFF). Em 200 o
 * cookie httpOnly `escuta_session` já foi gravado pelo BFF — o token NUNCA
 * chega aqui. Redireciona para `?next=` (ou `/`). Mensagens por status:
 *   401 → "usuário ou senha inválidos" (não vaza qual falhou);
 *   503 → "login não configurado (contate o admin)";
 *   outro → mensagem genérica.
 *
 * Fica FORA do shell com Sidebar (ver components/Shell.tsx) e usa o estilo
 * `.login-*` (em globals.css), na marca Escuta.
 */
/* `useSearchParams` exige um limite de Suspense para o prerender do Next 15.
   A casca é trivial; o formulário inteiro vive em <LoginForm/>. */
export default function LoginPage() {
  return (
    <Suspense fallback={<div className="login-wrap" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      await auth.login({ user: user.trim(), password });
      // Cookie já setado pelo BFF; o destino padrão é a home.
      const next = search.get("next");
      const dest = next && next.startsWith("/") ? next : "/";
      // `replace` para o login não ficar no histórico (voltar não relogga).
      router.replace(dest);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) setError("Usuário ou senha inválidos.");
        else if (err.status === 503)
          setError("Login não configurado. Contate o administrador.");
        else setError("Não foi possível entrar. Tente novamente.");
      } else {
        setError("Não foi possível entrar. Tente novamente.");
      }
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit} noValidate>
        <div className="login-brand">
          <div className="brand-mark">
            E<span className="brand-mark-dot" aria-hidden />
          </div>
          <div>
            <div className="brand-name">Escuta</div>
            <div className="login-sub">Voz do Cliente {"·"} WhatsApp</div>
          </div>
        </div>

        <h1 className="login-title">Entrar no painel</h1>
        <p className="login-hint">Acesso restrito à operação.</p>

        <label className="login-field">
          <span className="login-label">Usuário</span>
          <input
            type="text"
            name="user"
            autoComplete="username"
            autoFocus
            value={user}
            onChange={(e) => setUser(e.target.value)}
            disabled={loading}
            required
          />
        </label>

        <label className="login-field">
          <span className="login-label">Senha</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            required
          />
        </label>

        {error && (
          <div className="login-error" role="alert">
            {error}
          </div>
        )}

        <button
          type="submit"
          className="login-btn"
          disabled={loading || !user.trim() || !password}
        >
          {loading ? "Entrando…" : "Entrar"}
        </button>

        <div className="login-foot">
          by <b>Bizzu</b>
          <span className="login-foot-dot">.</span>
        </div>
      </form>
    </div>
  );
}
