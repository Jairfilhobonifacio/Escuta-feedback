"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import { api, type Contact } from "@/lib/api";

export default function ContatosPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setContacts(await api.get<Contact[]>("/api/contacts"));
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
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
              <tbody>
                {contacts.length === 0 && (
                  <tr>
                    <td colSpan={3}>
                      <div className="empty">
                        <div className="big">☎</div>
                        Nenhum contato ainda — adicione o primeiro ao lado.
                      </div>
                    </td>
                  </tr>
                )}
                {contacts.map((c) => (
                  <tr key={c.id}>
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
