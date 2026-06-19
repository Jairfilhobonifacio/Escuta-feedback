"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import { api, type Contact } from "@/lib/api";

/** Linha-fantasma (avatar + nome/telefone + opt-in + data) durante o load. */
function SkeletonRow() {
  return (
    <tr aria-hidden>
      <td>
        <div className="cell-person">
          <div className="sk-circle" />
          <div className="cell-person-txt" style={{ flex: 1 }}>
            <div className="sk-line sk-sm w-70" style={{ margin: "2px 0" }} />
            <div className="sk-line sk-sm w-50" style={{ margin: "2px 0" }} />
          </div>
        </div>
      </td>
      <td><div className="sk-line" style={{ width: 40, margin: 0 }} /></td>
      <td><div className="sk-line w-60" style={{ margin: 0 }} /></td>
    </tr>
  );
}

/** SVG discreto p/ o vazio: aparelho/balão de contato (stroke=currentColor). */
const EMPTY_CONTACT = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </svg>
);

export default function ContatosPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setContacts(await api.get<Contact[]>("/api/contacts"));
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function addContact(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFlash(null);
    try {
      const c = await api.post<Contact>("/api/contacts", { phone, name: name || null });
      setFlash({ kind: "ok", msg: `Contato ${c.name || c.phone} adicionado (opt-in registrado).` });
      setPhone("");
      setName("");
      await load();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Contatos</h1>
          <div className="page-sub">Quem pode receber pesquisas — sempre com opt-in</div>
        </div>
      </div>

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="two-col">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Contato</th>
                  <th>Opt-in</th>
                  <th>Desde</th>
                </tr>
              </thead>
              <tbody aria-busy={loading || undefined}>
                {loading && contacts.length === 0 &&
                  Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}
                {!loading && contacts.length === 0 && (
                  <tr>
                    <td colSpan={3}>
                      <div className="empty">
                        <div className="empty-illu">{EMPTY_CONTACT}</div>
                        <div className="empty-title">Nenhum contato ainda</div>
                        <p className="empty-sub">
                          Adicione o primeiro ao lado — o opt-in fica registrado.
                        </p>
                      </div>
                    </td>
                  </tr>
                )}
                {contacts.map((c, i) => (
                  <tr
                    key={c.id}
                    className="reveal"
                    style={{ ["--i" as string]: Math.min(i, 12) } as React.CSSProperties}
                  >
                    <td>
                      <div className="cell-person">
                        <Avatar name={c.name} seed={c.id} />
                        <div className="cell-person-txt">
                          <Link href={`/contatos/${c.id}`} className="row-link">
                            {c.name || "sem nome"}
                          </Link>
                          <span className="mono cell-person-sub">{c.phone}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      {c.opt_in ? (
                        <span className="badge promoter">sim</span>
                      ) : (
                        <span className="badge detractor">não</span>
                      )}
                    </td>
                    <td className="dim">
                      {c.created_at
                        ? new Date(c.created_at).toLocaleDateString("pt-BR")
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card" style={{ padding: "18px 20px" }}>
          <h2 className="section-title">Adicionar contato</h2>
          <p className="section-sub">
            Telefone com DDI, só dígitos (ex.: 5524998365809). O opt-in fica registrado.
          </p>
          <form onSubmit={addContact}>
            <div className="field">
              <label>WhatsApp (DDI+DDD+número)</label>
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="5524998365809"
                required
              />
            </div>
            <div className="field">
              <label>Nome (opcional)</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Maria Silva" />
            </div>
            <button className="btn" disabled={saving}>
              {saving ? "Salvando…" : "Adicionar"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
