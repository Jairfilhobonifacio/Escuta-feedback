"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Avatar from "@/components/Avatar";
import {
  whatsapp as wa,
  type WhatsappConversation,
  type WhatsappStatus,
  type WhatsappThread,
} from "@/lib/api";

function fmtTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

const ESTADO_LABEL: Record<string, string> = {
  cancelled: "cancelou",
  paid_without_access: "pagou s/ acesso",
  active_paying: "ativo",
  complimentary: "cortesia",
  past_due: "atrasado",
};

/** Skeleton de uma linha da lista de conversas (avatar + nome + prévia). */
function ConvSkeleton() {
  return (
    <div className="chat-conv chat-conv-sk" aria-hidden>
      <div className="sk-circle" style={{ ["--sk-size" as string]: "40px" }} />
      <div className="chat-conv-body">
        <div className="sk-line w-60" style={{ margin: "2px 0 8px" }} />
        <div className="sk-line sk-sm w-90" style={{ margin: 0 }} />
      </div>
    </div>
  );
}

/** Skeleton de um balão do chat (lado in/out alternado). */
function BubbleSkeleton({ side }: { side: "inbound" | "outbound" }) {
  return (
    <div className={`chat-bubble ${side} chat-bubble-sk`} aria-hidden>
      <div className="sk-line w-full" style={{ margin: "2px 0", width: 160 }} />
      <div className="sk-line sk-sm" style={{ margin: 0, width: 60 }} />
    </div>
  );
}

function estadoBadge(estado: string | null) {
  if (!estado) return null;
  const cls = estado === "active_paying" ? "promoter" : estado === "cancelled" ? "detractor" : "neutral";
  return <span className={`badge ${cls}`}>{ESTADO_LABEL[estado] ?? estado}</span>;
}

export default function ChatPage() {
  const [convs, setConvs] = useState<WhatsappConversation[]>([]);
  const [search, setSearch] = useState("");
  const [so1a1, setSo1a1] = useState(true); // "Só 1:1" — exclui grupos (default LIGADO)
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [thread, setThread] = useState<WhatsappThread | null>(null);
  const [status, setStatus] = useState<WhatsappStatus | null>(null);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [texto, setTexto] = useState("");
  const [sending, setSending] = useState(false);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const loadConvs = useCallback(async (q?: string, excluirGrupos?: boolean) => {
    setLoadingConvs(true);
    try {
      const r = await wa.conversations(q, excluirGrupos);
      setConvs(r.conversations);
      setListErr(null);
    } catch (e) {
      setListErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingConvs(false);
    }
  }, []);

  const loadThread = useCallback(async (id: string) => {
    setLoadingThread(true);
    try {
      setThread(await wa.thread(id));
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoadingThread(false);
    }
  }, []);

  // carga inicial + status do WAHA
  useEffect(() => {
    loadConvs(undefined, so1a1);
    wa.status().then(setStatus).catch(() => setStatus(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadConvs]);

  // busca com debounce + reage ao toggle "Só 1:1"
  useEffect(() => {
    const t = setTimeout(() => loadConvs(search.trim() || undefined, so1a1), 300);
    return () => clearTimeout(t);
  }, [search, so1a1, loadConvs]);

  // troca de conversa -> carrega a thread
  useEffect(() => {
    if (selectedId) loadThread(selectedId);
  }, [selectedId, loadThread]);

  // rola pro fim quando a thread muda
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread]);

  const conectado = !!status?.conectado;
  const isGrupo = !!thread?.contact.is_grupo;
  const alcancavel = !!thread?.contact.alcancavel;
  const podeEnviar = conectado && alcancavel && !!texto.trim() && !sending;

  async function enviar() {
    if (!selectedId || !podeEnviar) return;
    setSending(true);
    setFlash(null);
    try {
      await wa.sendConfirm(selectedId, { texto: texto.trim() });
      setTexto("");
      await loadThread(selectedId);
      await loadConvs(search.trim() || undefined, so1a1);
    } catch (e) {
      // 409 = WAHA off; 422 = sem WhatsApp; demais = erro de envio.
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSending(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Chat</h1>
          <div className="page-sub">Conversas do WhatsApp, dentro da central — sem abrir o WhatsApp Web</div>
        </div>
        <span className={`badge ${conectado ? "promoter" : "neutral"}`}>
          {conectado ? "WAHA conectado" : "WAHA desligado"}
        </span>
      </div>

      {!conectado && (
        <div className="note">
          <span className="note-ico" aria-hidden>
            {"\u{1F50C}"}
          </span>
          <span>
            O WhatsApp está desconectado — você pode ler as conversas, mas o envio
            fica bloqueado.{" "}
            <Link href="/conexao" className="row-link">
              Conectar o WhatsApp
            </Link>
            .
          </span>
        </div>
      )}

      <div className="chat-wrap">
        {/* ----- coluna esquerda: conversas ----- */}
        <aside className="chat-list card">
          <div className="chat-search">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nome ou telefone"
              aria-label="Buscar conversa"
            />
            <label className="chat-so1a1" title="Esconde grupos e comunidades — só conversas individuais">
              <input
                type="checkbox"
                checked={so1a1}
                onChange={(e) => setSo1a1(e.target.checked)}
              />
              <span>Só 1:1</span>
            </label>
          </div>

          {listErr && (
            <div className="flash err" style={{ margin: 12 }}>
              Não consegui carregar as conversas ({listErr}).
            </div>
          )}

          <div className="chat-convs" aria-busy={loadingConvs && convs.length === 0}>
            {loadingConvs && convs.length === 0 ? (
              <>
                {Array.from({ length: 7 }).map((_, i) => (
                  <ConvSkeleton key={i} />
                ))}
              </>
            ) : convs.length === 0 ? (
              <div className="empty">
                <div className="empty-illu" aria-hidden>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 0 1-.9-3.8 8.38 8.38 0 0 1 8.5-8.5 8.38 8.38 0 0 1 8.5 8.5Z" />
                  </svg>
                </div>
                <div className="empty-title">
                  {search.trim() ? "Nada encontrado" : "Nenhuma conversa ainda"}
                </div>
                <p className="empty-sub">
                  {search.trim()
                    ? "Ajuste a busca ou desligue o filtro “Só 1:1” para ver grupos."
                    : "As mensagens aparecem aqui quando um cliente escreve no WhatsApp — ou quando você envia pela ficha ou por aqui."}
                </p>
              </div>
            ) : (
              convs.map((c, i) => (
                <button
                  key={c.contact_id}
                  type="button"
                  className={`chat-conv reveal ${c.contact_id === selectedId ? "active" : ""}`}
                  style={{ ["--i" as string]: i }}
                  onClick={() => setSelectedId(c.contact_id)}
                >
                  <Avatar name={c.nome} seed={c.contact_id} size={40} />
                  <div className="chat-conv-body">
                    <div className="chat-conv-top">
                      <span className="chat-conv-name">{c.nome || c.whatsapp || "Sem nome"}</span>
                      <span className="chat-conv-time">{fmtTime(c.ultima_em)}</span>
                    </div>
                    <div className="chat-conv-prev">
                      {c.ultima_direction === "outbound" && <span className="chat-prev-you">Você: </span>}
                      {c.ultima_mensagem}
                    </div>
                    <div className="chat-conv-meta">
                      {c.is_grupo && <span className="badge neutral">{"\u{1F465}"} grupo</span>}
                      {!c.is_grupo && !c.tem_whatsapp && (
                        <span className="badge neutral">{"\u{2709}\u{FE0F}"} sem WhatsApp</span>
                      )}
                      {estadoBadge(c.estado)}
                      {c.selos.includes("respondeu") && <span className="badge promoter">respondeu</span>}
                      {c.selos.includes("contatado") && !c.selos.includes("respondeu") && (
                        <span className="badge open">contatado</span>
                      )}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </aside>

        {/* ----- coluna direita: thread + envio ----- */}
        <section className="chat-main card">
          {!selectedId || !thread ? (
            <div className="chat-empty">
              <div className="empty-illu" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z" />
                </svg>
              </div>
              <div className="empty-title">Selecione uma conversa</div>
              <p className="empty-sub">
                Escolha alguém na lista à esquerda para ver o histórico e responder por aqui.
              </p>
            </div>
          ) : (
            <>
              <header className="chat-head">
                <Avatar name={thread.contact.nome} seed={thread.contact.id} size={42} />
                <div className="chat-head-info">
                  <div className="chat-head-name">{thread.contact.nome || thread.contact.whatsapp || "Cliente"}</div>
                  <div className="chat-head-sub">
                    <span className="mono">{thread.contact.whatsapp}</span>
                    {estadoBadge(thread.contact.estado)}
                    {thread.contact.is_grupo && (
                      <span className="badge neutral">{"\u{1F465}"} grupo</span>
                    )}
                    {!thread.contact.is_grupo && !thread.contact.tem_whatsapp && (
                      <span className="badge neutral">{"\u{2709}\u{FE0F}"} sem WhatsApp</span>
                    )}
                  </div>
                </div>
                <Link href={`/contatos/${thread.contact.id}`} className="btn ghost chat-head-360">
                  Ficha 360
                </Link>
              </header>

              <div className="chat-thread" aria-busy={loadingThread && thread.mensagens.length === 0}>
                {loadingThread && thread.mensagens.length === 0 ? (
                  <>
                    <BubbleSkeleton side="inbound" />
                    <BubbleSkeleton side="outbound" />
                    <BubbleSkeleton side="inbound" />
                  </>
                ) : thread.mensagens.length === 0 ? (
                  <div className="empty">
                    <div className="empty-illu" aria-hidden>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 0 1-.9-3.8 8.38 8.38 0 0 1 8.5-8.5 8.38 8.38 0 0 1 8.5 8.5Z" />
                      </svg>
                    </div>
                    <div className="empty-title">Comece a conversa</div>
                    <p className="empty-sub">
                      Ainda não há mensagens com este contato. Escreva abaixo para iniciar.
                    </p>
                  </div>
                ) : (
                  thread.mensagens.map((m, i) => (
                    <div
                      key={m.id}
                      className={`chat-bubble reveal ${m.direction}`}
                      style={{ ["--i" as string]: Math.min(i, 6) }}
                    >
                      <div className="chat-bubble-body">{m.body}</div>
                      <div className="chat-bubble-time">{fmtTime(m.at)}</div>
                    </div>
                  ))
                )}
                <div ref={endRef} />
              </div>

              {!conectado && (
                <div className="chat-gate-note">
                  WAHA desligado — você pode ler as conversas, mas o envio fica bloqueado.
                  Ligue a sessão do WhatsApp para responder por aqui.
                </div>
              )}
              {conectado && !alcancavel && isGrupo && (
                <div className="chat-gate-note">
                  Esta é uma conversa de grupo — grupos não recebem 1:1.
                </div>
              )}
              {conectado && !alcancavel && !isGrupo && (
                <div className="chat-gate-note">
                  Este contato não está no WhatsApp — não dá para enviar.
                </div>
              )}

              {flash && (
                <div className={`flash ${flash.kind}`} style={{ margin: "0 14px" }}>
                  {flash.msg}
                </div>
              )}

              <div className="chat-compose">
                <textarea
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder={
                    conectado ? "Escreva uma mensagem… (Enter envia, Shift+Enter quebra linha)" : "WAHA desligado — envio bloqueado"
                  }
                  rows={2}
                  disabled={sending}
                />
                <button
                  type="button"
                  className="btn btn-wa"
                  onClick={enviar}
                  disabled={!podeEnviar}
                  title={
                    !conectado
                      ? "WAHA desligado — não dá para enviar"
                      : isGrupo
                        ? "Grupos não recebem 1:1"
                        : !alcancavel
                          ? "Contato não está no WhatsApp"
                          : "Enviar mensagem"
                  }
                >
                  {sending ? "Enviando…" : "Enviar"}
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
