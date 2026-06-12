"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, type Contact360, type Timeline360Item } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  nps: "NPS",
  csat: "CSAT",
  churn: "Cancelamento",
  exit: "Exit survey",
  ticket: "Atendimento",
  report: "Report de questão",
  edital_request: "Pedido de edital",
};

const SOURCE_LABEL: Record<string, string> = {
  bizzu_app: "app Bizzu",
  bizzu_billing: "cobrança",
  bizzu_support: "suporte",
  whatsapp: "WhatsApp",
};

const SENT_META: Record<string, { cls: string; label: string }> = {
  positivo: { cls: "s-pos", label: "positivo" },
  neutro: { cls: "s-neu", label: "neutro" },
  negativo: { cls: "s-neg", label: "negativo" },
};

function typeBadge(type: string) {
  const label = TYPE_LABEL[type] ?? type;
  const cls = type === "churn" || type === "exit" ? "t-exit" : type === "nps" || type === "csat" ? "t-nps" : "";
  return <span className={`badge type ${cls}`}>{label}</span>;
}

function sentimentBadge(s?: string | null) {
  if (!s) return null;
  const m = SENT_META[s];
  if (!m) return null;
  return <span className={`badge sent ${m.cls}`}>{m.label}</span>;
}

function themeChips(themes?: string[] | null) {
  if (!themes || themes.length === 0) return null;
  return (
    <div className="theme-chips">
      {themes.map((t, i) => (
        <span key={`${t}-${i}`} className="chip">{t}</span>
      ))}
    </div>
  );
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function field(label: string, value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div key={label}>
      <span className="lbl">{label}</span>
      <span className="val">{String(value)}</span>
    </div>
  );
}

function ProfileCard({ partner }: { partner: Record<string, unknown> }) {
  const sub = (partner.subscription as Record<string, unknown> | undefined) ?? {};
  const nps = (partner.nps as Record<string, unknown> | undefined) ?? {};
  return (
    <div className="card c360-profile">
      <div className="card-head">
        <div className="section-title">Perfil &amp; assinatura</div>
        <div className="card-head-sub">snapshot da API de Clientes</div>
      </div>
      <div className="c360-grid">
        {field("Perfil", partner.profile)}
        {field("Estado", sub.state)}
        {field("Plano", sub.planType)}
        {field("Dias de casa", sub.daysAsSubscriber)}
        {field("NPS (nota)", nps.score)}
        {field("Motivo de churn", sub.cancellationReason)}
      </div>
    </div>
  );
}

function TimelineRow({ t }: { t: Timeline360Item }) {
  return (
    <li className="tl-item">
      <div className="tl-top">
        {typeBadge(t.type)}
        {t.score !== null && t.score !== undefined && (
          <span className={`score-pill ${t.bucket ?? "none"}`}>{t.score}</span>
        )}
        {sentimentBadge(t.sentiment)}
        {t.status === "ingested" && <span className="badge neutral">do app</span>}
        <span className="tl-when">{fmtDate(t.at)}</span>
      </div>
      {t.text && <div className="tl-text">“{t.text}”</div>}
      {themeChips(t.themes)}
      <div className="tl-src">
        via {SOURCE_LABEL[t.source] ?? t.source}
        {t.survey_name ? ` · ${t.survey_name}` : ""}
      </div>
    </li>
  );
}

export default function Contact360Page() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [data, setData] = useState<Contact360 | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setData(await api.get<Contact360>(`/api/contacts/${id}/360`));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="page-head">
        <div>
          <Link href="/contatos" className="back-link">← Contatos</Link>
          <h1 className="page-title">{data?.contact.name || data?.contact.phone || "Cliente"}</h1>
          {data && (
            <div className="page-sub">
              <span className="mono">{data.contact.phone}</span>
              {" · "}
              {data.contact.opt_in ? "opt-in ✓" : "sem opt-in"}
            </div>
          )}
        </div>
        {data && <span className="refresh-note">{data.summary.total} interações</span>}
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar a ficha ({err}). A API está rodando em <span className="mono">localhost:8000</span>?
        </div>
      )}

      {!err && !data && <div className="empty">Carregando…</div>}

      {data && (
        <>
          {data.partner && <ProfileCard partner={data.partner} />}

          <div className="card">
            <div className="card-head">
              <div>
                <div className="section-title">Linha do tempo do cliente</div>
                <div className="card-head-sub">todas as fontes de feedback, unificadas</div>
              </div>
              <span className="exit-counter">
                {data.summary.feedback_items} sinais · {data.summary.survey_responses} pesquisas
              </span>
            </div>
            {data.timeline.length === 0 ? (
              <div className="empty">
                <div className="big">🗂️</div>
                Nenhum feedback registrado ainda para este cliente.
              </div>
            ) : (
              <ul className="tl">
                {data.timeline.map((t, i) => (
                  <TimelineRow key={i} t={t} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
