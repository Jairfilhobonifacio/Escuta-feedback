"use client";

import type { ReactNode } from "react";
import { Reveal, Stagger, StaggerItem } from "@/components/Motion";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// emoji em .ts/.tsx só via \u{...} (o bundler do Next no Windows corrompe literais).
const EMOJI_KEY = "\u{1F511}"; // 🔑 — autenticação por chave
const EMOJI_PLUG = "\u{1F50C}"; // 🔌 — integração / encaixe
const EMOJI_LOCK = "\u{1F512}"; // 🔒 — segredo no servidor

// Host da API — espelha o usado pelo lib/api.ts (NEXT_PUBLIC_API_URL ou localhost:8000).
const API_HOST =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

/** Bloco de código legível (curl/JSON) no padrão claro do painel. */
function Code({ children }: { children: ReactNode }) {
  return (
    <pre className="code-block">
      <code>{children}</code>
    </pre>
  );
}

/** Linha de parâmetro de query (nome · tipo · descrição). */
function Param({
  name,
  type,
  children,
}: {
  name: string;
  type: string;
  children: ReactNode;
}) {
  return (
    <div className="api-param">
      <code className="mono api-param-name">{name}</code>
      <Badge variant="outline" className="api-param-type">{type}</Badge>
      <span className="api-param-desc">{children}</span>
    </div>
  );
}

/** Cartão de um endpoint da API pública. */
function Endpoint({
  method,
  path,
  title,
  sub,
  params,
  curl,
  sample,
}: {
  method: string;
  path: string;
  title: string;
  sub: string;
  params: ReactNode;
  curl: string;
  sample: string;
}) {
  return (
    <Card className="api-endpoint">
      <div className="api-route">
        <Badge variant="positive" className="api-method">{method}</Badge>
        <code className="mono api-path">{path}</code>
        <Badge variant="outline" className="api-ro">somente leitura</Badge>
      </div>
      <h2 className="section-title">{title}</h2>
      <p className="section-sub">{sub}</p>

      <div className="api-block-label">Parâmetros (query)</div>
      <div className="api-params">{params}</div>

      <div className="api-block-label">Exemplo · curl</div>
      <Code>{curl}</Code>

      <div className="api-block-label">Resposta (exemplo)</div>
      <Code>{sample}</Code>
    </Card>
  );
}

export default function IntegracaoPage() {
  const curlFeedbacks = `curl -s "${API_HOST}/api/integration/feedbacks?selo=ouro&tipo=nps" \\
  -H "X-API-Key: $ESCUTA_API_KEY"`;

  const sampleFeedbacks = `{
  "items": [
    {
      "id": "f_8c1a...",
      "tipo": "nps",
      "selo": "ouro",
      "nota": 9,
      "sentimento": "positivo",
      "texto": "Atendimento excelente, recomendo.",
      "contato_id": "c_22f0...",
      "criado_em": "2026-06-15T13:42:10Z"
    }
  ],
  "count": 1
}`;

  const curlClientes = `curl -s "${API_HOST}/api/integration/clientes?estado=MG" \\
  -H "X-API-Key: $ESCUTA_API_KEY"`;

  const sampleClientes = `{
  "items": [
    {
      "id": "c_22f0...",
      "nome": "Ana Souza",
      "estado": "MG",
      "whatsapp": "+5531...",
      "perfil": "promotor",
      "ultimo_feedback_em": "2026-06-15T13:42:10Z"
    }
  ],
  "count": 1
}`;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Integração</h1>
          <div className="page-sub">
            API pública para sistemas externos lerem feedbacks e clientes do Escuta — autenticada por
            chave, somente leitura
          </div>
        </div>
        <span className="refresh-note">2 endpoints · somente leitura</span>
      </div>

      {/* ---- visão geral (preenche o topo + dá hierarquia) ---- */}
      <Reveal>
        <Card className="api-overview">
          <div className="api-ov-item">
            <span className="api-ov-ico" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.5 1.5" />
                <path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.5-1.5" />
              </svg>
            </span>
            <div className="api-ov-text">
              <div className="api-ov-label">Base URL</div>
              <code className="mono api-ov-value">{API_HOST}</code>
            </div>
          </div>
          <div className="api-ov-divider" aria-hidden />
          <div className="api-ov-item">
            <span className="api-ov-ico" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </span>
            <div className="api-ov-text">
              <div className="api-ov-label">Autenticação</div>
              <span className="api-ov-value-sm">
                Header <code className="mono">X-API-Key</code> em toda requisição
              </span>
            </div>
          </div>
          <div className="api-ov-divider" aria-hidden />
          <div className="api-ov-item">
            <span className="api-ov-ico" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <path d="M14 2v6h6" />
              </svg>
            </span>
            <div className="api-ov-text">
              <div className="api-ov-label">Recursos</div>
              <span className="api-ov-value-sm">
                <code className="mono">feedbacks</code> · <code className="mono">clientes</code>
              </span>
            </div>
          </div>
        </Card>
      </Reveal>

      <Stagger stagger={0.08}>
        {/* ---- Autenticação ---- */}
        <StaggerItem>
          <Card className="api-auth">
            <h2 className="section-title">
              {EMOJI_KEY} Autenticação
            </h2>
            <p className="section-sub">
              Toda requisição precisa do header <code className="mono">X-API-Key</code>. A chave vive{" "}
              <b>apenas no servidor</b>, na variável de ambiente <code className="mono">INTEGRATION_API_KEY</code>;
              o painel nunca a exibe nem a solicita. Quem configura é o administrador, no ambiente da API.
            </p>

            <div className="api-block-label">Header obrigatório</div>
            <Code>X-API-Key: &lt;sua-chave&gt;</Code>

            <ul className="api-notes">
              <li>
                <span className="api-note-ico" aria-hidden>
                  {EMOJI_LOCK}
                </span>
                A chave é um segredo: trate-a como senha, envie só por HTTPS e nunca a coloque em URLs,
                logs ou no front-end.
              </li>
              <li>
                <span className="api-note-ico" aria-hidden>
                  {EMOJI_PLUG}
                </span>
                Sem o header (ou com chave inválida) a API responde <code className="mono">401</code>.
              </li>
              <li>
                <span className="api-note-ico" aria-hidden>
                  {"\u{2699}"}
                </span>
                Para definir/rotacionar a chave, o admin ajusta <code className="mono">INTEGRATION_API_KEY</code>{" "}
                no ambiente e reinicia a API.
              </li>
            </ul>
          </Card>
        </StaggerItem>

        {/* ---- Endpoints ---- */}
        <StaggerItem>
          <Endpoint
            method="GET"
            path="/api/integration/feedbacks"
            title="Listar feedbacks"
            sub="Retorna os feedbacks coletados, opcionalmente filtrados por selo e por tipo."
            params={
              <>
                <Param name="selo" type="string">
                  Filtra pelo selo do cliente (ex.: <code className="mono">ouro</code>,{" "}
                  <code className="mono">prata</code>). Opcional.
                </Param>
                <Param name="tipo" type="string">
                  Filtra pelo tipo do feedback (ex.: <code className="mono">nps</code>,{" "}
                  <code className="mono">exit</code>). Opcional.
                </Param>
              </>
            }
            curl={curlFeedbacks}
            sample={sampleFeedbacks}
          />
        </StaggerItem>

        <StaggerItem>
          <Endpoint
            method="GET"
            path="/api/integration/clientes"
            title="Listar clientes"
            sub="Retorna os clientes (contatos) cadastrados, opcionalmente filtrados por estado."
            params={
              <Param name="estado" type="string">
                Filtra pela UF do cliente (ex.: <code className="mono">MG</code>,{" "}
                <code className="mono">SP</code>). Opcional.
              </Param>
            }
            curl={curlClientes}
            sample={sampleClientes}
          />
        </StaggerItem>
      </Stagger>

      {/* ---- estilos locais dos blocos de código (padrão claro do painel) ---- */}
      <style jsx>{`
        /* visão geral em faixa horizontal */
        :global(.api-overview) {
          display: flex;
          align-items: stretch;
          flex-wrap: wrap;
          gap: 4px;
          padding: 16px 8px;
          margin-bottom: 16px;
        }
        .api-ov-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 6px 16px;
          flex: 1 1 220px;
          min-width: 0;
        }
        .api-ov-ico {
          flex-shrink: 0;
          width: 38px;
          height: 38px;
          display: grid;
          place-items: center;
          border-radius: var(--radius-sm);
          color: var(--indigo-light);
          background: var(--promoter-soft);
          border: 1px solid var(--promoter-line);
        }
        .api-ov-ico svg { width: 19px; height: 19px; }
        .api-ov-text { min-width: 0; }
        .api-ov-label {
          font-size: 10.5px;
          font-weight: 700;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: var(--text-faint);
          margin-bottom: 3px;
        }
        .api-ov-value {
          font-size: 13px;
          color: var(--text);
          font-weight: 600;
          overflow-wrap: anywhere;
        }
        .api-ov-value-sm {
          font-size: 13px;
          color: var(--text-dim);
        }
        .api-ov-value-sm code { color: var(--gold-soft); }
        .api-ov-divider {
          width: 1px;
          align-self: stretch;
          background: var(--charcoal);
          margin: 4px 0;
        }
        @media (max-width: 720px) {
          .api-ov-divider { display: none; }
        }

        :global(.api-auth) {
          padding: 18px 20px;
          margin-bottom: 16px;
        }
        :global(.api-endpoint) {
          padding: 18px 20px;
          margin-bottom: 16px;
        }
        .api-route {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 12px;
          flex-wrap: wrap;
        }
        :global(.api-method) {
          letter-spacing: 0.6px;
          font-weight: 700;
          padding: 2px 9px;
        }
        :global(.api-ro) {
          font-size: 10px;
          font-weight: 600;
          letter-spacing: 0.4px;
          text-transform: uppercase;
          margin-left: auto;
        }
        .api-path {
          font-size: 13px;
          color: var(--text);
        }
        .api-block-label {
          font-size: 10.5px;
          letter-spacing: 1.1px;
          text-transform: uppercase;
          color: var(--text-faint);
          margin: 16px 0 7px;
          font-weight: 600;
        }
        .code-block {
          margin: 0;
          padding: 13px 15px;
          background: var(--ink);
          border: 1px solid var(--charcoal);
          border-radius: var(--radius-sm);
          overflow-x: auto;
          box-shadow: var(--edge);
        }
        .code-block code {
          font-family: var(--mono);
          font-size: 12.5px;
          line-height: 1.65;
          color: var(--text-dim);
          white-space: pre;
          font-variant-numeric: tabular-nums;
        }
        .api-params {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .api-param {
          display: flex;
          align-items: baseline;
          gap: 10px;
          flex-wrap: wrap;
        }
        .api-param-name {
          font-size: 12.5px;
          color: var(--gold-soft);
          font-weight: 600;
        }
        :global(.api-param-type) {
          font-size: 10.5px;
        }
        .api-param-desc {
          font-size: 13px;
          color: var(--text-dim);
          flex: 1 1 200px;
        }
        .api-notes {
          list-style: none;
          margin: 14px 0 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .api-notes li {
          display: flex;
          align-items: flex-start;
          gap: 9px;
          font-size: 13px;
          color: var(--text-dim);
          line-height: 1.55;
        }
        .api-note-ico {
          flex-shrink: 0;
          line-height: 1.5;
        }
      `}</style>
    </div>
  );
}
