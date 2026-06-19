"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  whatsapp as wa,
  type WhatsappStatus,
  type WhatsappSessionStatus,
} from "@/lib/api";

/* Conexão do WhatsApp (WAHA) — gerencia o pareamento dentro do Escuta:
   ver status, conectar escaneando o QR, desconectar e reiniciar. Espelha o que
   antes só dava para fazer via curl/dashboard externo. Reusa o design system
   (card, badge, btn, page-head, modal) — identidade dark editorial Bizzu.
   Emoji em .tsx só via \u{...} (o bundler do Next no Windows corrompe literais). */

const EMOJI_OK = "\u{2705}"; // ✅ conectado
const EMOJI_PHONE = "\u{1F4F1}"; // 📱 aparelho

// Cadência dos polls (ms). Status sempre; QR só enquanto aguardando o scan.
const STATUS_EVERY = 4_000;
const QR_EVERY = 3_500;

/** Mapa de cada estado da sessão para rótulo + classe de badge do design system. */
function statusBadge(status: WhatsappSessionStatus, conectado: boolean) {
  if (conectado || status === "WORKING")
    return { label: "Conectado", cls: "promoter" };
  switch (status) {
    case "SCAN_QR_CODE":
      return { label: "Escaneie o QR", cls: "passive" };
    case "STARTING":
      return { label: "Iniciando…", cls: "passive" };
    case "STOPPED":
      return { label: "Parado", cls: "neutral" };
    case "FAILED":
      return { label: "Falhou", cls: "detractor" };
    case null:
    case undefined:
      return { label: "Desligado", cls: "neutral" };
    default:
      return { label: String(status), cls: "neutral" };
  }
}

export default function ConexaoPage() {
  const [status, setStatus] = useState<WhatsappStatus | null>(null);
  // null = nunca carregou ainda (mostra "Carregando…"); um obj = já temos resposta.
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [statusErr, setStatusErr] = useState<string | null>(null);

  const [qr, setQr] = useState<string | null>(null);
  const [polling, setPolling] = useState(false); // estamos aguardando o scan?
  const [busy, setBusy] = useState<null | "start" | "stop" | "restart">(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [confirm, setConfirm] = useState<null | "stop" | "restart">(null);

  // refs para limpar os timers no unmount sem recriar os efeitos a cada render.
  const qrTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingRef = useRef(false); // espelha `polling` p/ ler dentro do loop do QR.

  const conectado = !!status?.conectado;

  const stopQrPolling = useCallback(() => {
    pollingRef.current = false;
    setPolling(false);
    if (qrTimer.current) {
      clearTimeout(qrTimer.current);
      qrTimer.current = null;
    }
  }, []);

  // --- status: 1ª carga + auto-refresh a cada ~4s --------------------------
  const loadStatus = useCallback(async () => {
    try {
      const s = await wa.status();
      setStatus(s);
      setStatusErr(null);
      // Conectou (em qualquer caminho): some o QR e para o polling.
      if (s.conectado || s.status === "WORKING") {
        setQr(null);
        pollingRef.current = false;
        setPolling(false);
        if (qrTimer.current) {
          clearTimeout(qrTimer.current);
          qrTimer.current = null;
        }
      }
    } catch (e) {
      setStatusErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadedOnce(true);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const t = setInterval(loadStatus, STATUS_EVERY);
    return () => clearInterval(t);
  }, [loadStatus]);

  // --- QR: loop de polling enquanto aguardando o scan ----------------------
  // Auto-reagenda via setTimeout (não setInterval) para nunca empilhar chamadas.
  const pollQrOnce = useCallback(async () => {
    if (!pollingRef.current) return;
    try {
      const r = await wa.qr();
      if (!pollingRef.current) return;
      if (r.status === "WORKING") {
        // Conectou durante o polling — encerra e deixa o loadStatus refletir.
        setQr(null);
        pollingRef.current = false;
        setPolling(false);
        loadStatus();
        return;
      }
      setQr(r.qr);
    } catch (e) {
      // Não derruba a tela: mostra o erro e segue tentando no próximo tick.
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    }
    if (pollingRef.current) {
      qrTimer.current = setTimeout(pollQrOnce, QR_EVERY);
    }
  }, [loadStatus]);

  // limpa o timer do QR no unmount (sem vazar interval).
  useEffect(() => {
    return () => {
      pollingRef.current = false;
      if (qrTimer.current) clearTimeout(qrTimer.current);
    };
  }, []);

  // --- ações ---------------------------------------------------------------
  async function conectar() {
    setBusy("start");
    setFlash(null);
    try {
      const r = await wa.startSession();
      // já reflete o estado retornado pelo start
      setStatus((prev) => (prev ? { ...prev, status: r.status } : prev));
      if (r.status === "WORKING") {
        setFlash({ kind: "ok", msg: "WhatsApp conectado." });
        await loadStatus();
      } else {
        // começa a buscar o QR
        setQr(null);
        pollingRef.current = true;
        setPolling(true);
        pollQrOnce();
      }
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function desconectar() {
    setConfirm(null);
    setBusy("stop");
    setFlash(null);
    stopQrPolling();
    setQr(null);
    try {
      await wa.stopSession();
      setFlash({ kind: "ok", msg: "WhatsApp desconectado." });
      await loadStatus();
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function reiniciar() {
    setConfirm(null);
    setBusy("restart");
    setFlash(null);
    stopQrPolling();
    setQr(null);
    try {
      const r = await wa.restartSession();
      if (r.status === "WORKING") {
        setFlash({ kind: "ok", msg: "Sessão reiniciada e conectada." });
        await loadStatus();
      } else {
        // reiniciou: provavelmente pedirá QR de novo — volta ao polling.
        setFlash({ kind: "ok", msg: "Sessão reiniciada. Aguardando o QR…" });
        pollingRef.current = true;
        setPolling(true);
        pollQrOnce();
      }
    } catch (e) {
      setFlash({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  const badge = statusBadge(status?.status ?? null, conectado);
  const desligado = !status || status.status == null;
  const aguardandoScan = polling || status?.status === "SCAN_QR_CODE";
  // estados intermediários com visual próprio (fora do "desligado" genérico)
  const iniciando = !conectado && !aguardandoScan && (busy === "start" || status?.status === "STARTING");
  const falhou = !conectado && !aguardandoScan && !iniciando && status?.status === "FAILED";

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Conexão do WhatsApp</h1>
          <div className="page-sub">
            Conecte o WhatsApp da central escaneando o QR code — sem precisar de
            terminal ou dashboard externo. Daqui você liga, desliga e reinicia a
            sessão.
          </div>
        </div>
        <span className={`badge ${badge.cls}`}>
          {conectado ? `${EMOJI_OK} ${badge.label}` : badge.label}
        </span>
      </div>

      {statusErr && !loadedOnce && (
        <div className="flash err">
          Não consegui falar com a API ({statusErr}). Ela está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="card conn-card">
        {/* ---- cabeçalho de status do card ---- */}
        <div className="conn-head">
          <div className="conn-head-info">
            <div className="conn-head-title">Status da sessão</div>
            <div className="conn-head-sub">
              {!loadedOnce ? (
                <span className="sk-line w-80" style={{ display: "block", maxWidth: 280, margin: "4px 0 2px" }} />
              ) : conectado ? (
                <>
                  {EMOJI_OK} O WhatsApp está conectado e recebendo mensagens.
                </>
              ) : aguardandoScan ? (
                "Aguardando você escanear o QR code abaixo."
              ) : desligado ? (
                "A sessão está desligada. Clique em Conectar para gerar o QR code."
              ) : (
                <>
                  Estado atual:{" "}
                  <span className="mono">{status?.status ?? "—"}</span>
                </>
              )}
            </div>
            {status?.session && (
              <div className="conn-head-meta">
                <span className="mono">{status.session}</span>
                {status.base_url && (
                  <>
                    {" · "}
                    <span className="mono">{status.base_url}</span>
                  </>
                )}
              </div>
            )}
          </div>
          <span className={`badge ${badge.cls}`}>{badge.label}</span>
        </div>

        {/* ---- corpo: QR / conectado / desligado ---- */}
        <div className="conn-body" aria-busy={!loadedOnce}>
          {!loadedOnce ? (
            <div className="conn-state" aria-hidden>
              <div className="sk-circle sk-lg" style={{ ["--sk-size" as string]: "60px", margin: "0 auto 16px" }} />
              <div className="sk-line sk-lg w-50" style={{ maxWidth: 200, margin: "0 auto 12px" }} />
              <div className="sk-line w-80" style={{ maxWidth: 340, margin: "0 auto 7px" }} />
              <div className="sk-line w-60" style={{ maxWidth: 260, margin: "0 auto" }} />
            </div>
          ) : conectado ? (
            <div className="conn-state">
              <div className="conn-orb conn-orb-ok" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </div>
              <div className="conn-state-title">Conectado</div>
              <p className="conn-state-text">
                Tudo certo. As conversas e o envio 1:1 já funcionam no{" "}
                <b>Chat</b>. Você não precisa fazer mais nada aqui.
              </p>
            </div>
          ) : iniciando ? (
            <div className="conn-state">
              <div className="conn-orb conn-orb-busy" aria-hidden>
                <span className="conn-spinner conn-spinner-lg" />
              </div>
              <div className="conn-state-title">Iniciando a sessão…</div>
              <p className="conn-state-text">
                Subindo a conexão com o WhatsApp. Em instantes o <b>QR code</b> aparece
                aqui para você parear o aparelho.
              </p>
            </div>
          ) : falhou ? (
            <div className="conn-state">
              <div className="conn-orb conn-orb-fail" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 9v4" />
                  <path d="M12 17h.01" />
                  <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                </svg>
              </div>
              <div className="conn-state-title">A sessão falhou</div>
              <p className="conn-state-text">
                Algo travou a conexão. Clique em <b>Reiniciar</b> para subir a sessão de
                novo — pode ser preciso escanear o QR outra vez.
              </p>
            </div>
          ) : aguardandoScan ? (
            <div className="conn-qr-wrap">
              <div className="conn-qr-box">
                {qr ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={qr} alt="QR code para conectar o WhatsApp" className="conn-qr-img" />
                ) : (
                  <div className="conn-qr-pending">
                    <div className="conn-spinner" aria-hidden />
                    <span>Gerando QR code…</span>
                  </div>
                )}
              </div>
              <div className="conn-qr-help">
                <span className="conn-live">
                  <span className="conn-live-dot" aria-hidden />
                  atualiza sozinho
                </span>
                <div className="conn-qr-help-title">
                  {EMOJI_PHONE} Como conectar
                </div>
                <ol className="conn-steps">
                  <li>Abra o <b>WhatsApp</b> no seu celular.</li>
                  <li>
                    Toque em <b>Aparelhos conectados</b> (Configurações ou menu
                    de 3 pontos).
                  </li>
                  <li>
                    Toque em <b>Conectar aparelho</b> e aponte a câmera para o QR
                    ao lado.
                  </li>
                </ol>
                <p className="conn-qr-note">
                  O código atualiza sozinho a cada poucos segundos. Assim que o
                  WhatsApp parear, esta tela mostra <b>Conectado</b>{" "}
                  automaticamente.
                </p>
              </div>
            </div>
          ) : (
            <div className="conn-state">
              <div className="conn-orb conn-orb-idle" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="5" y="2" width="14" height="20" rx="3" />
                  <path d="M11 18h2" />
                </svg>
              </div>
              <div className="conn-state-title">WhatsApp desconectado</div>
              <p className="conn-state-text">
                {desligado
                  ? "A sessão está desligada. Clique em Conectar para gerar o QR code e parear um aparelho."
                  : "A sessão não está ativa. Clique em Conectar para iniciar e gerar o QR code."}
              </p>
            </div>
          )}
        </div>

        {/* ---- ações ---- */}
        <div className="conn-actions">
          {!conectado && (
            <button
              type="button"
              className="btn"
              onClick={conectar}
              disabled={busy !== null}
            >
              {busy === "start"
                ? "Conectando…"
                : aguardandoScan
                  ? "Gerar novo QR"
                  : "Conectar"}
            </button>
          )}
          {conectado && (
            <button
              type="button"
              className="btn danger"
              onClick={() => setConfirm("stop")}
              disabled={busy !== null}
            >
              {busy === "stop" ? "Desconectando…" : "Desconectar"}
            </button>
          )}
          <button
            type="button"
            className="btn ghost"
            onClick={() => setConfirm("restart")}
            disabled={busy !== null}
          >
            {busy === "restart" ? "Reiniciando…" : "Reiniciar"}
          </button>
          {!conectado && aguardandoScan && (
            <button
              type="button"
              className="btn ghost"
              onClick={() => setConfirm("stop")}
              disabled={busy !== null}
            >
              Cancelar
            </button>
          )}
        </div>
      </div>

      {/* ---- modal de confirmação (desconectar / reiniciar) ---- */}
      {confirm && (
        <div
          className="modal-backdrop"
          onClick={() => busy === null && setConfirm(null)}
          role="presentation"
        >
          <div
            className="modal-panel"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="conn-confirm-title"
          >
            <div className="modal-head">
              <h2 className="modal-title" id="conn-confirm-title">
                {confirm === "stop" ? "Desconectar o WhatsApp?" : "Reiniciar a sessão?"}
              </h2>
              <button
                type="button"
                className="modal-close"
                onClick={() => setConfirm(null)}
                aria-label="Fechar"
              >
                {"\u{2715}"}
              </button>
            </div>
            <div className="modal-body">
              <p className="confirm-text">
                {confirm === "stop" ? (
                  <>
                    Isso desfaz o pareamento: o envio e o recebimento de mensagens
                    param até você conectar de novo (escaneando o QR). Tem certeza?
                  </>
                ) : (
                  <>
                    Reiniciar para a sessão e sobe de novo. Pode ser necessário{" "}
                    <b>escanear o QR outra vez</b>. Use isto quando a conexão travar.
                    Continuar?
                  </>
                )}
              </p>
            </div>
            <div className="modal-foot">
              <button type="button" className="btn ghost" onClick={() => setConfirm(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className={`btn ${confirm === "stop" ? "danger" : ""}`}
                onClick={confirm === "stop" ? desconectar : reiniciar}
              >
                {confirm === "stop" ? "Desconectar" : "Reiniciar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---- estilos locais (padrão dark do painel) ---- */}
      <style jsx>{`
        .conn-card {
          overflow: hidden;
          max-width: 760px;
        }
        .conn-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 18px 22px 16px;
          border-bottom: 1px solid var(--charcoal);
        }
        .conn-head-title {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 600;
          letter-spacing: -0.3px;
          color: var(--text);
        }
        .conn-head-sub {
          font-size: 13px;
          color: var(--text-dim);
          margin-top: 4px;
          line-height: 1.5;
          text-wrap: pretty;
        }
        .conn-head-meta {
          font-size: 11.5px;
          color: var(--text-ghost);
          margin-top: 7px;
        }
        .conn-body {
          padding: 26px 22px;
        }
        /* estado simples (conectado / desligado) */
        .conn-state {
          text-align: center;
          padding: 14px 12px 4px;
        }
        .conn-big {
          font-size: 42px;
          line-height: 1;
          margin-bottom: 14px;
          opacity: 0.92;
        }
        .conn-state-title {
          font-family: var(--font-display);
          font-size: 18px;
          font-weight: 700;
          letter-spacing: -0.4px;
          color: var(--text);
        }
        .conn-state-text {
          font-size: 13.5px;
          color: var(--text-dim);
          line-height: 1.6;
          margin: 10px auto 0;
          max-width: 46ch;
          text-wrap: pretty;
        }
        /* orbe de estado — disco tingido pela marca, com glow e halo */
        .conn-orb {
          position: relative;
          width: 64px;
          height: 64px;
          margin: 0 auto 18px;
          display: grid;
          place-items: center;
          border-radius: 50%;
          border: 1px solid var(--charcoal-2);
          box-shadow: var(--edge);
        }
        .conn-orb svg {
          width: 28px;
          height: 28px;
          display: block;
          position: relative;
          z-index: 1;
        }
        /* halo pulsante sutil ao redor do orbe */
        .conn-orb::after {
          content: "";
          position: absolute;
          inset: -6px;
          border-radius: 50%;
          border: 1px solid currentColor;
          opacity: 0.18;
          animation: conn-halo 2.4s var(--ease) infinite;
        }
        @keyframes conn-halo {
          0% { transform: scale(0.9); opacity: 0.28; }
          70% { transform: scale(1.12); opacity: 0; }
          100% { transform: scale(1.12); opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          .conn-orb::after { animation: none; }
        }
        .conn-orb-ok {
          color: var(--indigo-light);
          background:
            radial-gradient(120% 120% at 50% 0%, var(--indigo-glow), transparent 70%),
            var(--ink);
          box-shadow: var(--edge), 0 10px 30px -8px var(--indigo-glow);
        }
        .conn-orb-busy {
          color: var(--gold-soft);
          background:
            radial-gradient(120% 120% at 50% 0%, var(--gold-glow), transparent 70%),
            var(--ink);
        }
        .conn-orb-busy::after { animation: none; }
        .conn-orb-fail {
          color: var(--detractor);
          background:
            radial-gradient(120% 120% at 50% 0%, var(--detractor-soft), transparent 70%),
            var(--ink);
        }
        .conn-orb-fail::after { animation: none; }
        .conn-orb-idle {
          color: var(--text-faint);
          background: var(--ink);
        }
        .conn-orb-idle::after { animation: none; }
        .conn-spinner-lg {
          width: 30px;
          height: 30px;
          border-width: 3px;
          border-top-color: var(--gold-soft);
        }
        /* QR */
        .conn-qr-wrap {
          display: grid;
          grid-template-columns: 232px 1fr;
          gap: 28px;
          align-items: center;
        }
        .conn-qr-box {
          width: 232px;
          height: 232px;
          display: grid;
          place-items: center;
          padding: 12px;
          background: #ffffff;
          border-radius: var(--radius);
          border: 1px solid var(--charcoal-2);
          box-shadow: var(--shadow-pop), 0 0 0 6px rgba(108, 92, 231, 0.08);
          overflow: hidden;
        }
        .conn-qr-img { border-radius: var(--radius-xs); }
        .conn-qr-img {
          width: 100%;
          height: 100%;
          object-fit: contain;
          display: block;
          outline: none;
        }
        .conn-qr-pending {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          color: var(--text-faint);
          font-size: 12.5px;
        }
        .conn-spinner {
          width: 30px;
          height: 30px;
          border-radius: 50%;
          border: 3px solid var(--charcoal);
          border-top-color: var(--indigo);
          animation: conn-spin 0.8s linear infinite;
        }
        @keyframes conn-spin {
          to {
            transform: rotate(360deg);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .conn-spinner {
            animation: none;
          }
        }
        .conn-live {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          font-size: 10.5px;
          font-weight: 600;
          letter-spacing: 0.6px;
          text-transform: uppercase;
          color: var(--indigo-light);
          background: var(--promoter-soft);
          border: 1px solid var(--promoter-line);
          border-radius: 999px;
          padding: 4px 10px;
          margin-bottom: 14px;
        }
        .conn-live-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--indigo);
          box-shadow: 0 0 0 0 var(--indigo-glow);
          animation: conn-live-pulse 1.8s var(--ease) infinite;
        }
        @keyframes conn-live-pulse {
          0% { box-shadow: 0 0 0 0 rgba(108, 92, 231, 0.45); }
          70% { box-shadow: 0 0 0 7px rgba(108, 92, 231, 0); }
          100% { box-shadow: 0 0 0 0 rgba(108, 92, 231, 0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .conn-live-dot { animation: none; }
        }
        .conn-qr-help-title {
          font-family: var(--font-display);
          font-size: 15px;
          font-weight: 600;
          letter-spacing: -0.3px;
          color: var(--text);
          margin-bottom: 12px;
        }
        .conn-steps {
          margin: 0;
          padding-left: 20px;
          display: flex;
          flex-direction: column;
          gap: 9px;
          font-size: 13.5px;
          color: var(--text-dim);
          line-height: 1.5;
        }
        .conn-steps b {
          color: var(--text);
          font-weight: 600;
        }
        .conn-qr-note {
          font-size: 12.5px;
          color: var(--text-faint);
          line-height: 1.55;
          margin: 14px 0 0;
          text-wrap: pretty;
        }
        .conn-qr-note b {
          color: var(--text-dim);
          font-weight: 600;
        }
        /* ações */
        .conn-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
          padding: 16px 22px 18px;
          border-top: 1px solid var(--charcoal);
        }
        @media (max-width: 620px) {
          .conn-qr-wrap {
            grid-template-columns: 1fr;
            justify-items: center;
            gap: 22px;
          }
        }
      `}</style>
    </div>
  );
}
