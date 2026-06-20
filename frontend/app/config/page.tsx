"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { Plus, Trash2, Tag, Inbox, ListChecks, Save } from "lucide-react";
import { Reveal } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { config as configApi, type ConfigItem, type ConfigResponse } from "@/lib/api";

/* ============================================================================
   CONFIGURAÇÕES — vocabulários customizáveis da org.

   O dono não se via nos status fixos (novo/em_analise/…) nem nos tipos/origens
   padrão. Aqui ele CRIA os seus, sem deixar de ver os de fábrica.

   Três seções (Status · Tipos · Origens), cada uma um card:
     - DEFAULTS aparecem read-only, com o selo "padrão" (não dá para apagar — são
       a base do produto e sustentam telas como o Board e o inbox).
     - CUSTOM são editáveis: adicionar (key + label [+ cor, só status]) e remover.
   "Salvar" envia ao backend SÓ os customizados de cada lista (PUT /api/config):
   campo ausente = não mexe; [] = limpa os custom daquela lista. Colisão de key
   com um default volta 422 — mostramos a mensagem do backend.

   Layout limpo/espaçado no padrão da Monitorar (card/section-title/field/flash).
   Sem styled-jsx: classes do globals.css + Tailwind inline. Ícones lucide
   (currentColor), sem emoji literal (bundler do Next no Windows).
   ========================================================================== */

/** Chaves dos DEFAULTS do produto (espelham o conjunto que o backend mescla no
    GET). Tudo no GET cuja key NÃO está aqui é tratado como CUSTOM da org —
    editável/removível. Manter em sincronia com os defaults do backend. */
const DEFAULT_KEYS: Record<SectionId, Set<string>> = {
  action_statuses: new Set([
    "a_abordar",
    "aguardando_retorno",
    "em_acompanhamento",
    "resolvido",
    "sem_retorno",
    "descartado",
  ]),
  feedback_types: new Set([
    "nps",
    "churn",
    "elogio",
    "sugestao",
    "bug",
    "nota",
    "abordagem",
    "outro",
  ]),
  feedback_origins: new Set([
    "manual",
    "whatsapp",
    "bizzu_app",
    "bizzu_billing",
    "bizzu_support",
    "bizzu_platform",
    "in_app",
    "forms",
  ]),
};

type SectionId = "action_statuses" | "feedback_types" | "feedback_origins";

const SECTIONS: {
  id: SectionId;
  title: string;
  sub: string;
  icon: typeof Tag;
  /** Status carrega cor; tipos/origens não. */
  hasColor: boolean;
  /** Texto-exemplo para o placeholder do label. */
  egLabel: string;
  egKey: string;
}[] = [
  {
    id: "action_statuses",
    title: "Status",
    sub: "as etapas pelas quais um feedback passa (aparecem nas abas e no Board)",
    icon: ListChecks,
    hasColor: true,
    egLabel: "Aguardando cliente",
    egKey: "aguardando_cliente",
  },
  {
    id: "feedback_types",
    title: "Tipos",
    sub: "a natureza do feedback (NPS, cancelamento, bug…)",
    icon: Tag,
    hasColor: false,
    egLabel: "Reclamação",
    egKey: "reclamacao",
  },
  {
    id: "feedback_origins",
    title: "Origens",
    sub: "de onde o feedback veio (WhatsApp, app, manual…)",
    icon: Inbox,
    hasColor: false,
    egLabel: "Instagram",
    egKey: "instagram",
  },
];

/** Cor default das pílulas de status quando o operador não escolhe uma. */
const DEFAULT_COR = "#6366f1";

/** "Aguardando Cliente!" -> "aguardando_cliente". Slug seguro p/ a key.
    (acentos viram base ASCII; espaços/símbolos viram "_"; colapsa repetidos). */
// Faixa de "combining diacritical marks" (U+0300–U+036F) via escapes ASCII —
// evita colar marcas combinantes literais no .tsx (o bundler do Next no Windows
// corrompe caracteres não-ASCII no fonte).
const DIACRITICS = new RegExp("[\\u0300-\\u036f]", "g");

function slugifyKey(raw: string): string {
  return raw
    .normalize("NFD")
    .replace(DIACRITICS, "") // remove acentos
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/** Divide a lista efetiva (vinda do GET) em defaults (read-only) e custom (editáveis). */
function split(items: ConfigItem[] | undefined, sectionId: SectionId) {
  const defaultKeys = DEFAULT_KEYS[sectionId];
  const defaults: ConfigItem[] = [];
  const custom: ConfigItem[] = [];
  for (const it of items ?? []) {
    (defaultKeys.has(it.key) ? defaults : custom).push(it);
  }
  return { defaults, custom };
}

// ===== Linha de um item (default read-only OU custom editável) ==============

function ItemRow({
  item,
  isDefault,
  hasColor,
}: {
  item: ConfigItem;
  isDefault: boolean;
  hasColor: boolean;
}) {
  return (
    <div
      className="card"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "11px 14px",
        opacity: isDefault ? 0.85 : 1,
      }}
    >
      {hasColor && (
        <span
          aria-hidden
          style={{
            width: 14,
            height: 14,
            borderRadius: "50%",
            flexShrink: 0,
            background: item.cor || DEFAULT_COR,
            boxShadow: "var(--edge)",
          }}
        />
      )}
      <span style={{ fontWeight: 600, color: "var(--text)" }}>{item.label}</span>
      <span className="mono" style={{ fontSize: 12, color: "var(--text-faint)" }}>
        {item.key}
      </span>
      {isDefault && (
        <span
          style={{
            marginLeft: "auto",
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: 0.6,
            textTransform: "uppercase",
            color: "var(--text-faint)",
            background: "var(--passive-soft)",
            border: "1px solid var(--passive-line)",
            borderRadius: 999,
            padding: "3px 9px",
          }}
        >
          padrão
        </span>
      )}
    </div>
  );
}

// ===== Linha editável de um item custom (com remover) =======================

function CustomRow({
  item,
  hasColor,
  onChange,
  onRemove,
}: {
  item: ConfigItem;
  hasColor: boolean;
  onChange: (next: ConfigItem) => void;
  onRemove: () => void;
}) {
  return (
    <div
      className="card"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 12px",
        flexWrap: "wrap",
      }}
    >
      {hasColor && (
        <input
          type="color"
          aria-label={`Cor de ${item.label || item.key}`}
          value={item.cor || DEFAULT_COR}
          onChange={(e) => onChange({ ...item, cor: e.target.value })}
          style={{
            width: 34,
            height: 34,
            flexShrink: 0,
            padding: 2,
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border-strong)",
            background: "var(--surface-base)",
            cursor: "pointer",
          }}
        />
      )}
      <div className="field" style={{ margin: 0, flex: "1 1 180px", minWidth: 0 }}>
        <input
          value={item.label}
          onChange={(e) => onChange({ ...item, label: e.target.value })}
          placeholder="Rótulo (ex.: Aguardando cliente)"
          aria-label="Rótulo"
        />
      </div>
      <div className="field" style={{ margin: 0, flex: "1 1 150px", minWidth: 0 }}>
        <input
          className="mono"
          value={item.key}
          onChange={(e) => onChange({ ...item, key: slugifyKey(e.target.value) })}
          placeholder="chave (ex.: aguardando_cliente)"
          aria-label="Chave"
        />
      </div>
      <button
        type="button"
        className="icon-btn danger"
        onClick={onRemove}
        title="Remover"
        aria-label={`Remover ${item.label || item.key}`}
      >
        <Trash2 size={15} aria-hidden />
      </button>
    </div>
  );
}

// ===== Uma seção (Status / Tipos / Origens) =================================

function Section({
  section,
  defaults,
  custom,
  onCustomChange,
  delay,
}: {
  section: (typeof SECTIONS)[number];
  defaults: ConfigItem[];
  custom: ConfigItem[];
  onCustomChange: (next: ConfigItem[]) => void;
  delay: number;
}) {
  const Icon = section.icon;

  function updateAt(i: number, next: ConfigItem) {
    onCustomChange(custom.map((it, idx) => (idx === i ? next : it)));
  }
  function removeAt(i: number) {
    onCustomChange(custom.filter((_, idx) => idx !== i));
  }
  function add() {
    const novo: ConfigItem = section.hasColor
      ? { key: "", label: "", cor: DEFAULT_COR }
      : { key: "", label: "" };
    onCustomChange([...custom, novo]);
  }

  return (
    <Reveal delay={delay} className="card" style={{ padding: 0, marginBottom: 18 }}>
      <div className="card-head">
        <div>
          <div className="section-title inline-flex items-center gap-2">
            <Icon size={17} aria-hidden /> {section.title}
          </div>
          <div className="card-head-sub">{section.sub}</div>
        </div>
        <span className="exit-counter">
          {custom.length} {custom.length === 1 ? "personalizado" : "personalizados"}
        </span>
      </div>

      <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 18 }}>
        {/* DEFAULTS (read-only) */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: 1,
              textTransform: "uppercase",
              color: "var(--text-faint)",
            }}
          >
            De fábrica
          </div>
          {defaults.length === 0 ? (
            <p className="count-line" style={{ margin: 0 }}>Nenhum padrão.</p>
          ) : (
            defaults.map((it) => (
              <ItemRow key={it.key} item={it} isDefault hasColor={section.hasColor} />
            ))
          )}
        </div>

        {/* CUSTOM (editáveis) */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: 1,
              textTransform: "uppercase",
              color: "var(--text-faint)",
            }}
          >
            Personalizados
          </div>
          {custom.length === 0 ? (
            <p className="count-line" style={{ margin: 0 }}>
              Nenhum ainda — clique em “Adicionar” para criar o seu.
            </p>
          ) : (
            custom.map((it, i) => (
              <CustomRow
                key={i}
                item={it}
                hasColor={section.hasColor}
                onChange={(next) => updateAt(i, next)}
                onRemove={() => removeAt(i)}
              />
            ))
          )}
          <div>
            <Button type="button" variant="secondary" size="sm" onClick={add}>
              <Plus size={14} strokeWidth={2.2} aria-hidden /> Adicionar{" "}
              {section.title.toLowerCase().replace(/s$/, "")}
            </Button>
          </div>
        </div>
      </div>
    </Reveal>
  );
}

// ===== Skeleton enquanto o GET não volta ====================================

function ConfigSkeleton() {
  return (
    <div aria-busy="true">
      {SECTIONS.map((s) => (
        <div key={s.id} className="card" style={{ padding: 0, marginBottom: 18 }}>
          <div className="card-head">
            <div style={{ flex: 1 }}>
              <div className="sk-line w-30" style={{ margin: "2px 0" }} />
              <div className="sk-line sk-sm w-60" style={{ margin: "6px 0 2px" }} />
            </div>
          </div>
          <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="sk-card" style={{ height: 44, borderRadius: "var(--radius-sm)" }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ===== Página ===============================================================

export default function ConfigPage() {
  const liveId = useId();
  const [data, setData] = useState<ConfigResponse | null>(null);
  // Os itens CUSTOM editáveis de cada lista (estado de edição da tela).
  const [custom, setCustom] = useState<Record<SectionId, ConfigItem[]>>({
    action_statuses: [],
    feedback_types: [],
    feedback_origins: [],
  });
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const cfg = await configApi.get();
      setData(cfg);
      setCustom({
        action_statuses: split(cfg.action_statuses, "action_statuses").custom,
        feedback_types: split(cfg.feedback_types, "feedback_types").custom,
        feedback_origins: split(cfg.feedback_origins, "feedback_origins").custom,
      });
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Os defaults read-only de cada lista (derivados da resposta efetiva do GET).
  const defaults = useMemo(() => {
    return {
      action_statuses: split(data?.action_statuses, "action_statuses").defaults,
      feedback_types: split(data?.feedback_types, "feedback_types").defaults,
      feedback_origins: split(data?.feedback_origins, "feedback_origins").defaults,
    };
  }, [data]);

  function setSectionCustom(id: SectionId, next: ConfigItem[]) {
    setCustom((prev) => ({ ...prev, [id]: next }));
    setFlash(null);
  }

  /** Valida e normaliza os custom de UMA lista para o corpo do PUT.
      Devolve string de erro (1ª pendência) ou os itens limpos. */
  function prepare(id: SectionId): { error?: string; items?: ConfigItem[] } {
    const out: ConfigItem[] = [];
    const seen = new Set<string>();
    const defaultKeys = DEFAULT_KEYS[id];
    const hasColor = id === "action_statuses";
    for (const raw of custom[id]) {
      const key = slugifyKey(raw.key || raw.label);
      const label = raw.label.trim();
      if (!key && !label) continue; // linha em branco: ignora
      if (!label) return { error: "Todo item personalizado precisa de um rótulo." };
      if (!key) return { error: `Defina uma chave para “${label}”.` };
      if (defaultKeys.has(key)) {
        return { error: `A chave “${key}” já é um padrão — escolha outra.` };
      }
      if (seen.has(key)) return { error: `A chave “${key}” está repetida.` };
      seen.add(key);
      out.push(hasColor ? { key, label, cor: raw.cor || DEFAULT_COR } : { key, label });
    }
    return { items: out };
  }

  async function salvar() {
    // Monta o corpo: SÓ as três listas de custom (sempre enviadas; [] limpa).
    const body: Record<SectionId, ConfigItem[]> = {
      action_statuses: [],
      feedback_types: [],
      feedback_origins: [],
    };
    for (const s of SECTIONS) {
      const r = prepare(s.id);
      if (r.error) {
        setFlash({ kind: "err", msg: `${s.title}: ${r.error}` });
        return;
      }
      body[s.id] = r.items ?? [];
    }

    setSaving(true);
    setFlash(null);
    try {
      const cfg = await configApi.update(body);
      setData(cfg);
      setCustom({
        action_statuses: split(cfg.action_statuses, "action_statuses").custom,
        feedback_types: split(cfg.feedback_types, "feedback_types").custom,
        feedback_origins: split(cfg.feedback_origins, "feedback_origins").custom,
      });
      setFlash({ kind: "ok", msg: "Configurações salvas." });
    } catch (e) {
      // 422 = colisão de key com default (detalhe vem do backend). Mensagem clara.
      const msg = e instanceof Error ? e.message : String(e);
      const is422 = typeof (e as { status?: number }).status === "number" && (e as { status?: number }).status === 422;
      setFlash({
        kind: "err",
        msg: is422
          ? `Não deu para salvar: ${msg}. Provável colisão de chave com um padrão — troque a chave.`
          : `Não deu para salvar: ${msg}.`,
      });
    } finally {
      setSaving(false);
    }
  }

  const totalCustom =
    custom.action_statuses.length + custom.feedback_types.length + custom.feedback_origins.length;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Configurações</h1>
          <div className="page-sub">
            Crie seus próprios status, tipos e origens de feedback. Os de fábrica
            ficam disponíveis; os personalizados aparecem nas telas de Feedbacks e
            na ficha do cliente.
          </div>
        </div>
        <div className="page-head-actions">
          {data && <span className="refresh-note">{totalCustom} personalizados</span>}
          <Button onClick={salvar} disabled={saving || !data}>
            <Save size={15} aria-hidden /> {saving ? "Salvando…" : "Salvar alterações"}
          </Button>
        </div>
      </div>

      {err && (
        <div className="flash err">
          Não consegui carregar as configurações ({err}). A API está rodando em{" "}
          <span className="mono">localhost:8000</span>?
        </div>
      )}

      {flash && (
        <div className={`flash ${flash.kind}`} role="status" id={liveId}>
          {flash.msg}
        </div>
      )}

      {!err && !data ? (
        <ConfigSkeleton />
      ) : data ? (
        <>
          {SECTIONS.map((s, i) => (
            <Section
              key={s.id}
              section={s}
              defaults={defaults[s.id]}
              custom={custom[s.id]}
              onCustomChange={(next) => setSectionCustom(s.id, next)}
              delay={0.04 + i * 0.05}
            />
          ))}

          <p className="count-line">
            Os padrões do produto não podem ser removidos — eles sustentam o Board e o
            inbox. Mudanças nos personalizados só valem depois de “Salvar alterações”.
          </p>

          <div>
            <Button onClick={salvar} disabled={saving}>
              <Save size={15} aria-hidden /> {saving ? "Salvando…" : "Salvar alterações"}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
