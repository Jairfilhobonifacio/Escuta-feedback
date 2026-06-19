"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  whatsapp as wa,
  type WhatsappStatus,
  type WhatsappSessionStatus,
} from "@/lib/api";

/* Conexão do WhatsApp (WAHA) — gerencia o pareamento dentro do Escuta:
   ver status, conectar escaneando o QR, desconectar e reiniciar. Espelha o que
   antes só dava para fazer via curl/dashboard externo. Modernizado para a UI
   premium (light Bizzu): grid de 2 colunas — card de status + QR à esquerda,
   guia passo-a-passo persistente à direita — para preencher e guiar.
   Emoji em .tsx só via \u{...} (o bundler do Next no Windows corrompe literais). */

const EMOJI_OK = "\u{2705}"; // ✅ conectado
const EMOJI_PHONE = "\u{1F4F1}"; // 📱 aparelho

// Cadência dos polls (ms). Status sempre; QR só enquanto aguardando o scan.
const STATUS_EVERY = 4_000;
const QR_EVERY = 3_500;

/** Mapa de cada estado da sessão para rótulo + variant de badge do design system. */
function statusBadge(
  status: WhatsappSessionStatus,
  conectado: boolean,
): { label: string; variant: "positive" | "neutral" | "negative" } {
  if (conectado || status === "WORKING")
    return { label: "Conectado", variant: "positive" };
  switch (status) {
    case "SCAN_QR_CODE":
      return { label: "Escaneie o QR", variant: "neutral" };
    case "STARTING":
      return { label: "Iniciando\u{2026}", variant: "neutral" };
    case "STOPPED":
      return { label: "Parado", variant: "neutral" };
    case "FAILED":
      return { label: "Falhou", variant: "negative" };
    case null:
    case undefined:
      return { label: "Desligado", variant: "neutral" };
    default:
      return { label: String(status), variant: "neutral" };
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
        setFlash({ kind: "ok", msg: "Sessão reiniciada. Aguardando o QR\u{2026}" });
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
        <Badge variant={badge.variant} className="px-2.5 py-1 text-[11.5px]">
          {conectado ? `${EMOJI_OK} ${badge.label}` : badge.label}
        </Badge>
      </div>

      {statusErr && !loadedOnce && (
        <div className="flash err">
          Não consegui falar com a API ({statusErr}). Ela está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {flash && <div className={`flash ${flash.kind}`}>{flash.msg}</div>}

      <div className="conn-grid">
        {/* ====== COLUNA ESQUERDA: card de status + QR ====== */}
        <Reveal className="conn-col">
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
              <Badge variant={badge.variant}>{badge.label}</Badge>
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
                  <div className="conn-state-title">Iniciando a sessão{"\u{2026}"}</div>
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
                        <span>Gerando QR code{"\u{2026}"}</span>
                      </div>
                    )}
                  </div>
                  <span className="conn-live">
                    <span className="conn-live-dot" aria-hidden />
                    atualiza sozinho
                  </span>
                  <p className="conn-qr-note">
                    O código atualiza sozinho a cada poucos segundos. Assim que o
                    WhatsApp parear, esta tela mostra <b>Conectado</b>{" "}
                    automaticamente. Siga o passo-a-passo ao lado.
                  </p>
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
                <Button
                  variant="accent"
                  onClick={conectar}
                  disabled={busy !== null}
                >
                  {busy === "start"
                    ? "Conectando\u{2026}"
                    : aguardandoScan
                      ? "Gerar novo QR"
                      : "Conectar"}
                </Button>
              )}
              {conectado && (
                <Button
                  variant="outline"
                  onClick={() => setConfirm("stop")}
                  disabled={busy !== null}
                >
                  {busy === "stop" ? "Desconectando\u{2026}" : "Desconectar"}
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={() => setConfirm("restart")}
                disabled={busy !== null}
              >
                {busy === "restart" ? "Reiniciando\u{2026}" : "Reiniciar"}
              </Button>
              {!conectado && aguardandoScan && (
                <Button
                  variant="ghost"
                  onClick={() => setConfirm("stop")}
                  disabled={busy !== null}
                >
                  Cancelar
                </Button>
              )}
            </div>
          </div>
        </Reveal>

        {/* ====== COLUNA DIREITA: guia passo-a-passo + dicas (persistente) ====== */}
        <Reveal delay={0.08} className="conn-col">
          <div className="card conn-help-card">
            <div className="conn-help-head">
              <span className="conn-help-ico" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="5" y="2" width="14" height="20" rx="3" />
                  <path d="M11 18h2" />
                </svg>
              </span>
              <div>
                <div className="conn-help-title">
                  {EMOJI_PHONE} Como conectar
                </div>
                <div className="conn-help-sub">
                  Quatro passos no seu celular — leva menos de um minuto.
                </div>
              </div>
            </div>

            <ol className="conn-steps">
              <li>
                <span className="conn-step-n" aria-hidden>1</span>
                <span className="conn-step-tx">
                  Abra o <b>WhatsApp</b> no seu celular.
                </span>
              </li>
              <li>
                <span className="conn-step-n" aria-hidden>2</span>
                <span className="conn-step-tx">
                  Toque em <b>Aparelhos conectados</b> (Configurações, ou no menu
                  de 3 pontos no Android).
                </span>
              </li>
              <li>
                <span className="conn-step-n" aria-hidden>3</span>
                <span className="conn-step-tx">
                  Toque em <b>Conectar aparelho</b>.
                </span>
              </li>
              <li>
                <span className="conn-step-n" aria-hidden>4</span>
                <span className="conn-step-tx">
                  Aponte a câmera para o <b>QR code</b>{" "}
                  {aguardandoScan ? "ao lado" : "que aparece ao clicar em Conectar"}.
                </span>
              </li>
            </ol>

            <div className="conn-tips">
              <div className="conn-tips-title">Dicas</div>
              <ul className="conn-tips-list">
                <li>
                  <span className="conn-tip-dot" aria-hidden />
                  O QR <b>expira rápido</b> — se passar do tempo, é só clicar em
                  <b> Gerar novo QR</b>.
                </li>
                <li>
                  <span className="conn-tip-dot" aria-hidden />
                  Deixe o celular <b>conectado à internet</b> para a sessão se
                  manter ativa.
                </li>
                <li>
                  <span className="conn-tip-dot" aria-hidden />
                  Travou? <b>Reiniciar</b> sobe a sessão de novo (pode pedir o QR
                  outra vez).
                </li>
              </ul>
            </div>

            <div className={`conn-help-foot ${conectado ? "ok" : ""}`}>
              {conectado ? (
                <>
                  <span className="conn-foot-ico" aria-hidden>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                  </span>
                  Conectado — pode usar o Chat e as Pesquisas normalmente.
                </>
              ) : (
                <>
                  <span className="conn-foot-ico" aria-hidden>
                    <span className="conn-live-dot" />
                  </span>
                  Esta tela detecta o pareamento sozinha — não feche a aba durante
                  o processo.
                </>
              )}
            </div>
          </div>
        </Reveal>
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
              <Button variant="ghost" onClick={() => setConfirm(null)}>
                Cancelar
              </Button>
              <Button
                variant={confirm === "stop" ? "destructive" : "default"}
                onClick={confirm === "stop" ? desconectar : reiniciar}
              >
                {confirm === "stop" ? "Desconectar" : "Reiniciar"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ---- estilos locais (padrão claro do painel) ---- */}
      <style jsx>{`
        /* grid de 2 colunas: status/QR + ajuda (preenche o espaço) */
        .conn-grid {
          display: grid;
          grid-template-columns: 1.15fr 0.85fr;
          gap: 20px;
          align-items: stretch;
        }
        .conn-col {
          display: flex;
          min-width: 0;
        }
        .conn-card,
        .conn-help-card {
          overflow: hidden;
          width: 100%;
          display: flex;
          flex-direction: column;
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
          padding: 30px 22px;
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
        }
        /* estado simples (conectado / desligado) */
        .conn-state {
          text-align: center;
          padding: 14px 12px 4px;
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
          width: 72px;
          height: 72px;
          margin: 0 auto 20px;
          display: grid;
          place-items: center;
          border-radius: 50%;
          border: 1px solid var(--charcoal-2);
          box-shadow: var(--edge);
        }
        .conn-orb svg {
          width: 30px;
          height: 30px;
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
        /* QR — agora centralizado na coluna (a ajuda fica no card ao lado) */
        .conn-qr-wrap {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 16px;
        }
        .conn-qr-box {
          width: 244px;
          height: 244px;
          display: grid;
          place-items: center;
          padding: 12px;
          background: #ffffff;
          border-radius: var(--radius);
          border: 1px solid var(--charcoal-2);
          box-shadow: var(--shadow-pop), 0 0 0 6px rgba(108, 92, 231, 0.08);
          overflow: hidden;
        }
        .conn-qr-img {
          width: 100%;
          height: 100%;
          object-fit: contain;
          display: block;
          outline: none;
          border-radius: var(--radius-xs);
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
        .conn-qr-note {
          font-size: 12.5px;
          color: var(--text-faint);
          line-height: 1.55;
          margin: 0;
          max-width: 40ch;
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

        /* ===== card de ajuda (coluna direita) ===== */
        .conn-help-card {
          background:
            linear-gradient(180deg, rgba(108, 92, 231, 0.04), transparent 30%),
            var(--ink-800);
        }
        .conn-help-head {
          display: flex;
          align-items: flex-start;
          gap: 13px;
          padding: 20px 22px 16px;
          border-bottom: 1px solid var(--charcoal);
        }
        .conn-help-ico {
          flex-shrink: 0;
          width: 40px;
          height: 40px;
          display: grid;
          place-items: center;
          border-radius: var(--radius-sm);
          color: var(--indigo-light);
          background: var(--promoter-soft);
          border: 1px solid var(--promoter-line);
        }
        .conn-help-ico svg { width: 20px; height: 20px; }
        .conn-help-title {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 600;
          letter-spacing: -0.3px;
          color: var(--text);
        }
        .conn-help-sub {
          font-size: 12.5px;
          color: var(--text-faint);
          margin-top: 3px;
          line-height: 1.5;
        }
        .conn-steps {
          list-style: none;
          margin: 0;
          padding: 18px 22px 6px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .conn-steps li {
          display: flex;
          align-items: flex-start;
          gap: 13px;
          padding: 11px 0;
          font-size: 13.5px;
          color: var(--text-dim);
          line-height: 1.5;
          border-bottom: 1px solid var(--charcoal);
        }
        .conn-steps li:last-child { border-bottom: none; }
        .conn-steps b {
          color: var(--text);
          font-weight: 600;
        }
        .conn-step-n {
          flex-shrink: 0;
          width: 24px;
          height: 24px;
          display: grid;
          place-items: center;
          border-radius: 50%;
          font-family: var(--mono);
          font-size: 12px;
          font-weight: 600;
          color: var(--indigo-light);
          background: var(--promoter-soft);
          border: 1px solid var(--promoter-line);
        }
        .conn-step-tx { padding-top: 2px; text-wrap: pretty; }
        /* dicas */
        .conn-tips {
          margin: 8px 22px 0;
          padding: 14px 16px;
          background: var(--ink);
          border: 1px solid var(--charcoal);
          border-radius: var(--radius-sm);
        }
        .conn-tips-title {
          font-size: 10.5px;
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: var(--text-faint);
          margin-bottom: 10px;
        }
        .conn-tips-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 9px;
        }
        .conn-tips-list li {
          display: flex;
          align-items: flex-start;
          gap: 9px;
          font-size: 12.5px;
          color: var(--text-dim);
          line-height: 1.5;
          text-wrap: pretty;
        }
        .conn-tips-list b { color: var(--text); font-weight: 600; }
        .conn-tip-dot {
          flex-shrink: 0;
          width: 5px;
          height: 5px;
          margin-top: 7px;
          border-radius: 50%;
          background: var(--gold-fill);
        }
        .conn-help-foot {
          margin-top: auto;
          display: flex;
          align-items: center;
          gap: 9px;
          padding: 14px 22px 18px;
          font-size: 12.5px;
          color: var(--text-faint);
          line-height: 1.45;
          text-wrap: pretty;
        }
        .conn-help-foot.ok { color: var(--indigo-light); }
        .conn-foot-ico {
          flex-shrink: 0;
          display: grid;
          place-items: center;
          width: 16px;
          height: 16px;
          color: var(--indigo-light);
        }
        .conn-foot-ico svg { width: 16px; height: 16px; }

        @media (max-width: 900px) {
          .conn-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
