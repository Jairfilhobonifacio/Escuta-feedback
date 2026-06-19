"use client";

import type { ReactNode } from "react";

// emoji em .ts/.tsx só via \u{...} (o bundler do Next no Windows corrompe literais).
const EMOJI_KEY = "\u{1F511}"; // 🔑 — autenticação por chave
const EMOJI_PLUG = "\u{1F50C}"; // 🔌 — integração / encaixe
const EMOJI_LOCK = "\u{1F512}"; // 🔒 — segredo no servidor

// Host da API — espelha o usado pelo lib/api.ts (NEXT_PUBLIC_API_URL ou localhost:8000).
const API_HOST =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

/** Bloco de código legível (curl/JSON) no padrão dark do painel. */
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
      <span className="badge type api-param-type">{type}</span>
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
    <div className="card api-endpoint reveal">
      <div className="api-route">
        <span className="badge api-method">{method}</span>
        <code className="mono api-path">{path}</code>
      </div>
      <h2 className="section-title">{title}</h2>
      <p className="section-sub">{sub}</p>

      <div className="api-block-label">Parâmetros (query)</div>
      <div className="api-params">{params}</div>

      <div className="api-block-label">Exemplo · curl</div>
      <Code>{curl}</Code>

      <div className="api-block-label">Resposta (exemplo)</div>
      <Code>{sample}</Code>
    </div>
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

      <div className="reveal-stagger">
      {/* ---- Autenticação ---- */}
      <div className="card api-auth reveal">
        <h2 className="section-title">
          {EMOJI_KEY} Autenticação
        </h2>
        <p className="section-sub">
          Toda requisição precisa do header <code className="mono">X-API-Key</code>. A chave vive{" "}
          <b>apenas no servidor</b>, na variável de ambiente <code className="mono">INTEGRATION_API_KEY</code>;
          o painel nunca a exibe nem a solicita. Quem configura é o administrador, no ambiente da API.
        </p>

        <div className="api-block-label">Base URL</div>
        <Code>{API_HOST}</Code>

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
      </div>

      {/* ---- Endpoints ---- */}
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
      </div>

      {/* ---- estilos locais dos blocos de código (padrão dark do painel) ---- */}
      <style jsx>{`
        .api-auth {
          padding: 18px 20px;
          margin-bottom: 16px;
        }
        .api-endpoint {
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
        .api-method {
          background: var(--promoter-soft);
          color: var(--indigo-light);
          border-color: var(--promoter-line);
          letter-spacing: 0.6px;
          font-weight: 700;
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
          background: var(--void);
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
        .api-param-type {
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
