"use client";

import { useState, useEffect, useCallback } from "react";
import {
  users as usersApi,
  type OrgUser,
  type CreateUserInput,
  type UpdateUserInput,
  type UserRole,
  ApiError,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Utils
// ---------------------------------------------------------------------------

function roleLabel(role: UserRole) {
  return role === "owner" ? "Dono" : role === "admin" ? "Admin" : "Membro";
}

function rolePilula(role: UserRole) {
  const bg =
    role === "owner"
      ? "var(--accent-gold, #f5a623)"
      : role === "admin"
        ? "var(--accent-blue, #3b82f6)"
        : "var(--surface-raised, #e5e7eb)";
  const color =
    role === "owner" || role === "admin" ? "#fff" : "var(--text-muted, #6b7280)";
  return (
    <span
      style={{
        background: bg,
        color,
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.02em",
      }}
    >
      {roleLabel(role)}
    </span>
  );
}

function initials(u: OrgUser) {
  const src = u.name || u.email;
  return src
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("");
}

// ---------------------------------------------------------------------------
// Modal de criação/edição
// ---------------------------------------------------------------------------

type ModalMode = { kind: "create" } | { kind: "edit"; user: OrgUser } | { kind: "password"; user: OrgUser };

function Modal({
  mode,
  onClose,
  onSaved,
}: {
  mode: ModalMode;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isCreate = mode.kind === "create";
  const isEdit = mode.kind === "edit";
  const isPw = mode.kind === "password";

  const editUser = isEdit || isPw ? (mode as { kind: "edit" | "password"; user: OrgUser }).user : null;

  const [email, setEmail] = useState(editUser?.email ?? "");
  const [name, setName] = useState(editUser?.name ?? "");
  const [role, setRole] = useState<UserRole>(editUser?.role ?? "member");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (isCreate) {
        const body: CreateUserInput = {
          email,
          name: name || null,
          role,
          password: password || undefined,
        };
        await usersApi.create(body);
      } else if (isEdit && editUser) {
        const body: UpdateUserInput = {
          name: name || null,
          role,
        };
        await usersApi.update(editUser.id, body);
      } else if (isPw && editUser) {
        if (!password || password.length < 6) {
          setError("Senha mínima de 6 caracteres.");
          setLoading(false);
          return;
        }
        await usersApi.setPassword(editUser.id, { password });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  }

  const title = isCreate ? "Convidar usuário" : isPw ? "Definir senha" : "Editar usuário";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        zIndex: 999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "var(--surface, #fff)",
          borderRadius: 12,
          padding: 28,
          width: 420,
          maxWidth: "95vw",
          boxShadow: "0 8px 32px rgba(0,0,0,.18)",
        }}
      >
        <h2 style={{ margin: "0 0 20px", fontSize: 17, fontWeight: 700 }}>{title}</h2>
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {isCreate && (
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted, #6b7280)" }}>
                E-mail *
              </span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="nome@empresa.com"
                style={inputStyle}
              />
            </label>
          )}
          {(isCreate || isEdit) && (
            <>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted, #6b7280)" }}>
                  Nome
                </span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Nome completo"
                  style={inputStyle}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted, #6b7280)" }}>
                  Papel
                </span>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                  style={inputStyle}
                >
                  <option value="member">Membro</option>
                  <option value="admin">Admin</option>
                  <option value="owner">Dono</option>
                </select>
              </label>
            </>
          )}
          {(isCreate || isPw) && (
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted, #6b7280)" }}>
                {isCreate ? "Senha (opcional — deixe em branco para convite)" : "Nova senha *"}
              </span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isCreate ? "••••••" : "••••••"}
                minLength={isPw ? 6 : undefined}
                required={isPw}
                style={inputStyle}
              />
            </label>
          )}
          {error && (
            <p style={{ margin: 0, color: "#ef4444", fontSize: 13 }}>{error}</p>
          )}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
            <button type="button" onClick={onClose} style={btnSecStyle} disabled={loading}>
              Cancelar
            </button>
            <button type="submit" style={btnPriStyle} disabled={loading}>
              {loading ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export default function UsuariosPage() {
  const [list, setList] = useState<OrgUser[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalMode | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setList(await usersApi.list());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erro ao carregar usuários");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(u: OrgUser) {
    if (!confirm(`Remover ${u.email}? Esta ação não pode ser desfeita.`)) return;
    setRemoving(u.id);
    try {
      await usersApi.remove(u.id);
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Erro ao remover");
    } finally {
      setRemoving(null);
    }
  }

  async function toggleActive(u: OrgUser) {
    setToggling(u.id);
    try {
      await usersApi.update(u.id, { is_active: !u.is_active });
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Erro ao atualizar");
    } finally {
      setToggling(null);
    }
  }

  return (
    <main style={{ padding: "32px 28px", maxWidth: 860, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Usuários</h1>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-muted, #6b7280)" }}>
            Membros da equipe com acesso ao painel Escuta.
          </p>
        </div>
        <button
          style={btnPriStyle}
          onClick={() => setModal({ kind: "create" })}
        >
          + Convidar usuário
        </button>
      </div>

      {loading && (
        <p style={{ color: "var(--text-muted, #6b7280)", fontSize: 14 }}>Carregando…</p>
      )}
      {error && (
        <p style={{ color: "#ef4444", fontSize: 14 }}>{error}</p>
      )}

      {list && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {list.map((u) => {
            const isEnv = !!u._env_operator;
            const busy = removing === u.id || toggling === u.id;
            return (
              <div
                key={u.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  background: "var(--surface-raised, #f9fafb)",
                  border: "1px solid var(--border, #e5e7eb)",
                  borderRadius: 10,
                  padding: "14px 18px",
                  opacity: !u.is_active ? 0.6 : 1,
                }}
              >
                {/* Avatar */}
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 999,
                    background: isEnv
                      ? "var(--accent-gold, #f5a623)"
                      : "var(--accent-blue, #3b82f6)",
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: 14,
                    flex: "0 0 auto",
                  }}
                >
                  {initials(u)}
                </div>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>
                      {u.name || u.email}
                    </span>
                    {rolePilula(u.role)}
                    {!u.is_active && (
                      <span
                        style={{
                          fontSize: 11,
                          color: "#ef4444",
                          background: "#fee2e2",
                          padding: "1px 6px",
                          borderRadius: 999,
                          fontWeight: 600,
                        }}
                      >
                        Inativo
                      </span>
                    )}
                    {!u.has_password && (
                      <span
                        style={{
                          fontSize: 11,
                          color: "#d97706",
                          background: "#fef3c7",
                          padding: "1px 6px",
                          borderRadius: 999,
                          fontWeight: 600,
                        }}
                      >
                        Convite pendente
                      </span>
                    )}
                    {isEnv && (
                      <span
                        style={{
                          fontSize: 11,
                          color: "var(--text-muted, #6b7280)",
                          fontStyle: "italic",
                        }}
                      >
                        (operador principal)
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted, #6b7280)", marginTop: 2 }}>
                    {u.name ? u.email : ""}
                    {u.last_login_at && (
                      <span style={{ marginLeft: u.name ? 10 : 0 }}>
                        Último acesso: {new Date(u.last_login_at).toLocaleDateString("pt-BR")}
                      </span>
                    )}
                    {!u.last_login_at && !isEnv && (
                      <span style={{ marginLeft: u.name ? 10 : 0 }}>Nunca acessou</span>
                    )}
                  </div>
                </div>

                {/* Ações */}
                {!isEnv && (
                  <div style={{ display: "flex", gap: 6, flex: "0 0 auto" }}>
                    {!u.has_password && (
                      <button
                        style={btnSecStyle}
                        disabled={busy}
                        onClick={() => setModal({ kind: "password", user: u })}
                        title="Definir senha para este convite"
                      >
                        Definir senha
                      </button>
                    )}
                    <button
                      style={btnSecStyle}
                      disabled={busy}
                      onClick={() => setModal({ kind: "edit", user: u })}
                    >
                      Editar
                    </button>
                    <button
                      style={{
                        ...btnSecStyle,
                        color: u.is_active ? "#d97706" : "#16a34a",
                      }}
                      disabled={busy}
                      onClick={() => toggleActive(u)}
                      title={u.is_active ? "Desativar acesso" : "Reativar acesso"}
                    >
                      {toggling === u.id
                        ? "…"
                        : u.is_active
                          ? "Desativar"
                          : "Reativar"}
                    </button>
                    <button
                      style={{ ...btnSecStyle, color: "#ef4444" }}
                      disabled={busy}
                      onClick={() => remove(u)}
                    >
                      {removing === u.id ? "…" : "Remover"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {modal && (
        <Modal
          mode={modal}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      )}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Estilos inline compartilhados
// ---------------------------------------------------------------------------

const inputStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid var(--border, #e5e7eb)",
  fontSize: 14,
  background: "var(--surface, #fff)",
  color: "inherit",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const btnPriStyle: React.CSSProperties = {
  padding: "8px 18px",
  borderRadius: 8,
  background: "var(--accent-gold, #f5a623)",
  color: "#fff",
  fontWeight: 600,
  fontSize: 13,
  border: "none",
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const btnSecStyle: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 8,
  background: "transparent",
  color: "var(--text-muted, #6b7280)",
  fontWeight: 500,
  fontSize: 12,
  border: "1px solid var(--border, #e5e7eb)",
  cursor: "pointer",
  whiteSpace: "nowrap",
};
