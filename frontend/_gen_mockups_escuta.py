# -*- coding: utf-8 -*-
"""
Gerador dos mockups visuais do web app Escuta (Voz do Cliente · Bizzu).
3 telas em alta fidelidade ao design system REAL (frontend/app/globals.css +
layout.tsx): tema light, marca indigo #6c5ce7, fontes Space Grotesk (titulos),
Inter (UI/corpo), JetBrains Mono (dados) carregadas via webfont do Google.

Rodar:
    PYTHONUTF8=1 py _gen_mockups_escuta.py
Renderiza com:
    py C:\\Users\\jboni\\.claude\\skills\\design-studio\\scripts\\svg_to_png.py <svg> <png> --scale 2
(este script ja chama o renderer no final)

Saidas:
    C:\\Users\\jboni\\AppData\\Local\\Temp\\mockup_mapeamento.png
    C:\\Users\\jboni\\AppData\\Local\\Temp\\mockup_melhorias.png
    C:\\Users\\jboni\\AppData\\Local\\Temp\\mockup_loop.png
"""
import os, sys, subprocess, html

OUT = r"C:\Users\jboni\AppData\Local\Temp"
RENDERER = r"C:\Users\jboni\.claude\skills\design-studio\scripts\svg_to_png.py"
W = 1440  # largura canonica do app

# ---- tokens (copiados 1:1 do globals.css) ---------------------------------
VOID = "#f6f6fb"        # fundo principal
INK = "#eef0f7"         # superficie base / trilhos
CARD = "#ffffff"        # cards
INK700 = "#eceef6"      # hover / superficie elevada
CHARCOAL = "#e4e5f0"    # bordas/divisores
CHARCOAL2 = "#cfd0e0"   # bordas fortes
SIDEBAR_TOP = "#ffffff"

INDIGO = "#6c5ce7"
INDIGO_DEEP = "#5b4bcf"
INDIGO_LIGHT = "#5a49c9"  # texto de marca sobre claro (AA)
INDIGO_GLOW = "rgba(108,92,231,0.16)"
PROMOTER_SOFT = "rgba(108,92,231,0.10)"
PROMOTER_LINE = "rgba(108,92,231,0.28)"

GOLD = "#b3760a"          # texto sobre claro (AA)
GOLD_SOFT = "#946105"
GOLD_FILL = "#f5a623"     # preenchimentos
GOLD_GLOW = "rgba(245,166,35,0.16)"
PASSIVE_SOFT = "rgba(245,166,35,0.13)"
PASSIVE_LINE = "rgba(245,166,35,0.34)"

TEXT = "#1a1830"
TEXT_DIM = "#56546b"
TEXT_FAINT = "#82809a"
TEXT_GHOST = "#a9a7bd"

DETRACTOR = "#cf4d4d"
DETRACTOR_SOFT = "rgba(207,77,77,0.10)"
DETRACTOR_LINE = "rgba(207,77,77,0.30)"

WA_GREEN = "#25d366"
WA_GREEN_DEEP = "#1da851"

RADIUS = 16
RADIUS_SM = 11
RADIUS_XS = 8

FONT_DISPLAY = "'Space Grotesk', 'Segoe UI', sans-serif"
FONT = "'Inter', 'Segoe UI', sans-serif"
MONO = "'JetBrains Mono', ui-monospace, monospace"

# Carrega as fontes reais do produto via Google Fonts (Edge headless baixa).
FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@500;600;700&amp;"
    "family=Inter:wght@400;500;600;700&amp;"
    "family=JetBrains+Mono:wght@500;600;700&amp;display=swap');"
)


# ---- helpers SVG -----------------------------------------------------------
def esc(s):
    return html.escape(str(s), quote=True)


def rrect(x, y, w, h, r, fill, stroke=None, sw=1, extra=""):
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{sw}"'
    if extra:
        s += " " + extra
    return s + "/>"


def text(x, y, s, size, fill, *, font=FONT, weight=400, anchor="start",
         spacing=None, opacity=None):
    attrs = (f'x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
             f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"')
    if spacing is not None:
        attrs += f' letter-spacing="{spacing}"'
    if opacity is not None:
        attrs += f' opacity="{opacity}"'
    return f'<text {attrs}>{esc(s)}</text>'


def tspan_line(x, y, parts, size, font=FONT):
    """parts = [(txt, fill, weight), ...] numa unica linha."""
    out = [f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}">']
    for t, fill, wt in parts:
        out.append(f'<tspan fill="{fill}" font-weight="{wt}">{esc(t)}</tspan>')
    out.append("</text>")
    return "".join(out)


# Sombra suave de card (luz de cima, tingida de indigo) — replica --shadow.
SHADOW_DEF = f'''
  <filter id="cardShadow" x="-20%" y="-20%" width="140%" height="160%">
    <feDropShadow dx="0" dy="10" stdDeviation="9" flood-color="#1a1830" flood-opacity="0.10"/>
  </filter>
  <filter id="softShadow" x="-20%" y="-20%" width="140%" height="150%">
    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#1a1830" flood-opacity="0.06"/>
  </filter>
  <filter id="popShadow" x="-40%" y="-40%" width="180%" height="200%">
    <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#1a1830" flood-opacity="0.22"/>
  </filter>
'''


def card(x, y, w, h, *, r=RADIUS, fill=CARD, stroke=CHARCOAL, sw=1, shadow=True,
         accent=None):
    """Card branco com borda + sombra suave; accent = cor da faixa lateral esq."""
    g = []
    filt = ' filter="url(#cardShadow)"' if shadow else ""
    g.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
             f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{filt}/>')
    # hairline de topo (luz)
    g.append(f'<rect x="{x+1}" y="{y+1}" width="{w-2}" height="{r}" rx="{r-1}" '
             f'fill="rgba(255,255,255,0.6)" opacity="0.5"/>')
    if accent:
        g.append(f'<rect x="{x}" y="{y+1}" width="3" height="{h-2}" rx="1.5" fill="{accent}"/>')
    return "".join(g)


def pill(x, y, w, h, fill, stroke, *, r=999):
    return rrect(x, y, w, h, r, fill, stroke, 1)


# ---- icones (Lucide, traco currentColor, 24x24 viewBox) --------------------
# subconjunto usado nas telas; desenhados como <g> com transform/scale
LUCIDE = {
    # map (Mapeamento)
    "map": '<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>',
    "radar": '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "message-circle": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "kanban": '<path d="M6 5v11"/><path d="M12 5v6"/><path d="M18 5v14"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "clipboard": '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    "smartphone": '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "bar-chart": '<line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/>',
    "credit-card": '<rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
    "pencil": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "lightbulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    "loader": '<path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/>',
    "party": '<path d="M5.8 11.3 2 22l10.7-3.79"/><path d="M4 3h.01"/><path d="M22 8h.01"/><path d="M15 2h.01"/><path d="M22 20h.01"/><path d="m22 2-2.24.75a2.9 2.9 0 0 0-1.96 3.12c.1.86-.57 1.63-1.45 1.63h-.38c-.86 0-1.6.6-1.76 1.44L12 10"/><path d="m22 13-.82-.33c-.86-.34-1.82.2-1.98 1.11c-.11.7-.72 1.22-1.43 1.22H17"/><path d="m11 2 .33.82c.34.86-.2 1.82-1.11 1.98C9.52 4.9 9 5.52 9 6.23V7"/><path d="M11 13c1.93 1.93 2.83 4.17 2 5-.83.83-3.07-.07-5-2-1.93-1.93-2.83-4.17-2-5 .83-.83 3.07.07 5 2Z"/>',
}


def icon(name, x, y, size, color, sw=1.75):
    """Renderiza um icone Lucide num bbox size x size na posicao (x,y)."""
    body = LUCIDE[name]
    sc = size / 24.0
    return (f'<g transform="translate({x},{y}) scale({sc})" '
            f'fill="none" stroke="{color}" stroke-width="{sw/sc:.3f}" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</g>')


def avatar(x, y, d, initials, fg, bg, line):
    """Avatar quadrado arredondado com iniciais (estilo .avatar do app)."""
    g = [rrect(x, y, d, d, 9, bg, line, 1)]
    g.append(text(x + d / 2, y + d / 2 + d * 0.135, initials, d * 0.4, fg,
                  font=FONT_DISPLAY, weight=700, anchor="middle"))
    return "".join(g)


# ---- SIDEBAR (replica components/Sidebar.tsx) ------------------------------
SIDEBAR_W = 256
NAV_GROUPS = [
    ("Operação", [
        ("radar", "Monitorar", "feature", False),
        ("message-square", "Feedbacks", "feature", False),
        ("message-circle", "Chat", "feature", False),
        ("kanban", "Board", "", False),
        ("map", "Mapeamento", "", False),
    ]),
    ("Clientes", [
        ("users", "Clientes", "", False),
        ("clipboard", "Pesquisas", "", False),
    ]),
    ("Config", [
        ("smartphone", "Conexão", "", False),
        ("settings", "Configurações", "", False),
    ]),
]


def sidebar(height, active_label):
    g = []
    # fundo com leve gradiente branco->ink
    g.append(f'''<defs><linearGradient id="sbg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="{SIDEBAR_TOP}"/>
        <stop offset="0.7" stop-color="{INK}"/></linearGradient></defs>''')
    g.append(f'<rect x="0" y="0" width="{SIDEBAR_W}" height="{height}" fill="url(#sbg)"/>')
    g.append(f'<line x1="{SIDEBAR_W}" y1="0" x2="{SIDEBAR_W}" y2="{height}" stroke="{CHARCOAL}" stroke-width="1"/>')

    pad = 16
    # --- brand ---
    bx, by = pad + 8, 30
    g.append(f'''<defs><linearGradient id="bmark" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="{INDIGO}"/><stop offset="1" stop-color="{INDIGO_DEEP}"/>
        </linearGradient></defs>''')
    g.append(rrect(bx, by, 38, 38, 11, "url(#bmark)"))
    g.append(text(bx + 19, by + 26, "E", 19, "#ffffff", font=FONT_DISPLAY, weight=700, anchor="middle"))
    g.append(f'<circle cx="{bx+38-2}" cy="{by+38-2}" r="4.5" fill="{GOLD_FILL}" stroke="{VOID}" stroke-width="2"/>')
    g.append(text(bx + 50, by + 16, "Escuta", 18, TEXT, font=FONT_DISPLAY, weight=700, spacing="-0.4"))
    g.append(text(bx + 50, by + 32, "Voz do Cliente · WhatsApp", 11, TEXT_FAINT))
    # divisor sob a marca
    g.append(f'<line x1="{pad+8}" y1="{by+58}" x2="{SIDEBAR_W-pad-8}" y2="{by+58}" stroke="{CHARCOAL}" stroke-width="1"/>')

    # --- nav groups ---
    y = by + 58 + 22
    for glabel, items in NAV_GROUPS:
        g.append(text(pad + 12, y, glabel.upper(), 10.5, TEXT_GHOST, weight=600, spacing="0.8"))
        y += 16
        for ic, label, feat, _ in items:
            is_active = (label == active_label)
            row_h = 38
            ix = pad + 12
            tcol = TEXT_DIM
            icol = TEXT_FAINT
            if feat == "feature":
                tcol = TEXT
            if is_active:
                # fundo ativo + faixa indigo a esquerda
                g.append(rrect(pad, y - 14, SIDEBAR_W - pad * 2, row_h - 6, RADIUS_SM,
                               PROMOTER_SOFT))
                g.append(f'<rect x="0" y="{y-12}" width="3" height="{row_h-10}" rx="1.5" fill="{INDIGO}"/>')
                tcol = TEXT
                icol = INDIGO_LIGHT if feat != "feature" else GOLD
            elif feat == "feature":
                icol = GOLD
            g.append(icon(ic, ix, y - 13, 18, icol, sw=1.75))
            g.append(text(ix + 30, y + 1, label, 14, tcol, weight=600 if (feat or is_active) else 500))
            y += row_h - 4
        y += 14

    # --- footer ---
    fy = height - 56
    g.append(f'<line x1="{pad+8}" y1="{fy-16}" x2="{SIDEBAR_W-pad-8}" y2="{fy-16}" stroke="{CHARCOAL}" stroke-width="1"/>')
    g.append(tspan_line(pad + 12, fy + 4,
                        [("by ", TEXT_DIM, 700), ("Bizzu", TEXT, 700), (".", GOLD_FILL, 700)],
                        15, font=FONT_DISPLAY))
    g.append(text(pad + 12, fy + 22, "Voz do Cliente · WhatsApp", 11, TEXT_GHOST))
    return "".join(g)


def page_head(cx, title, sub, *, right=None, top=64):
    """Cabecalho de pagina: titulo grande + regua de marca + subtitulo."""
    g = []
    g.append(text(cx, top, title, 34, TEXT, font=FONT_DISPLAY, weight=700, spacing="-1.2"))
    # regua indigo
    g.append(f'''<defs><linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#7c6cf0"/><stop offset="1" stop-color="{INDIGO_DEEP}"/>
        </linearGradient></defs>''')
    g.append(rrect(cx, top + 16, 54, 2, 1, "url(#rule)"))
    if sub:
        g.append(text(cx, top + 40, sub, 14.5, TEXT_DIM))
    return "".join(g)


def svg_open(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">'
            f'<defs><style>{FONT_IMPORT}</style>{SHADOW_DEF}</defs>'
            # fundo void com glows de marca nas quinas (replica body bg)
            f'<rect width="{w}" height="{h}" fill="{VOID}"/>'
            f'<defs>'
            f'<radialGradient id="glowI" cx="0.82" cy="-0.1" r="0.6">'
            f'<stop offset="0" stop-color="rgba(108,92,231,0.07)"/>'
            f'<stop offset="1" stop-color="rgba(108,92,231,0)"/></radialGradient>'
            f'<radialGradient id="glowG" cx="-0.06" cy="0.04" r="0.5">'
            f'<stop offset="0" stop-color="rgba(245,166,35,0.06)"/>'
            f'<stop offset="1" stop-color="rgba(245,166,35,0)"/></radialGradient>'
            f'</defs>'
            f'<rect width="{w}" height="{h}" fill="url(#glowI)"/>'
            f'<rect width="{w}" height="{h}" fill="url(#glowG)"/>')


def render(name, svg, png):
    svg_path = os.path.join(OUT, name + ".svg")
    open(svg_path, "w", encoding="utf-8").write(svg)
    r = subprocess.run([sys.executable.replace("python.exe", "py.exe") if False else "py",
                        RENDERER, svg_path, png, "--scale", "2"],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("ERRO render:", r.stderr.strip())
    return r.returncode == 0


# ===========================================================================
# TELA 1 — MAPEAMENTO
# ===========================================================================
def tela_mapeamento():
    H = 1024
    cx = SIDEBAR_W + 40           # margem de conteudo
    cw = W - cx - 40              # largura util
    g = [svg_open(W, H)]
    g.append(sidebar(H, "Mapeamento"))
    g.append(page_head(cx, "Mapeamento",
                       "As dores dos clientes, agrupadas por significado e priorizadas."))

    # linha de contexto (contagem + controle de ordenacao)
    cy = 120
    g.append(tspan_line(cx, cy, [("11 dores", TEXT, 600),
                                 ("  ·  agrupadas de 27 feedbacks  ·  ordenadas por prioridade",
                                  TEXT_FAINT, 500)], 12.5))
    # controle "ordenar" a direita
    ob_w = 168
    g.append(pill(cx + cw - ob_w, cy - 16, ob_w, 34, CARD, CHARCOAL2))
    g.append(text(cx + cw - ob_w + 14, cy + 1, "Ordenar: prioridade", 12.5, TEXT_DIM, weight=500))
    g.append(icon("chevron-down", cx + cw - 26, cy - 9, 16, TEXT_FAINT))

    # --- cards de dor (ordenados por prioridade) ---
    # (nome, clientes, pagantes, sentimento, prioridade, indice 0..100)
    dores = [
        ("Erro no pagamento", 8, 5, "negativo", "Alta", 92),
        ("Dificuldade de navegação no app", 5, 3, "negativo", "Alta", 74),
        ("Cancelamento de assinatura", 3, 3, "negativo", "Média", 58),
        ("Falta de conteúdo de Direito Constitucional", 3, 1, "negativo", "Média", 46),
        ("Lentidão para carregar videoaulas", 2, 1, "neutro", "Baixa", 28),
    ]
    PR = {
        "Alta": (DETRACTOR, DETRACTOR_SOFT, DETRACTOR_LINE),
        "Média": (GOLD_SOFT, PASSIVE_SOFT, PASSIVE_LINE),
        "Baixa": (TEXT_DIM, "rgba(86,84,107,0.08)", CHARCOAL2),
    }
    SENT = {"negativo": (DETRACTOR, "negativo"), "neutro": (GOLD_SOFT, "neutro"),
            "positivo": (INDIGO_LIGHT, "positivo")}

    card_y = cy + 26
    card_h = 150
    gap = 16
    for i, (nome, cli, pag, sent, prio, idx) in enumerate(dores):
        y = card_y + i * (card_h + gap)
        pr_col, pr_bg, pr_line = PR[prio]
        accent = pr_col if prio == "Alta" else None
        g.append(card(cx, y, cw, card_h, accent=accent))
        px = cx + 26
        # rank
        g.append(rrect(px, y + 22, 28, 28, 8, INK, CHARCOAL, 1))
        g.append(text(px + 14, y + 41, str(i + 1), 13, TEXT_FAINT, font=MONO, weight=600, anchor="middle"))
        # nome da dor (nivel 1)
        nx = px + 42
        g.append(text(nx, y + 36, nome, 19, TEXT, font=FONT_DISPLAY, weight=600, spacing="-0.3"))
        # selo de prioridade (canto sup direito)
        seal_w = 116
        seal_x = cx + cw - seal_w - 24
        g.append(pill(seal_x, y + 20, seal_w, 30, pr_bg, pr_line))
        g.append(f'<circle cx="{seal_x+16}" cy="{y+35}" r="4" fill="{pr_col}"/>')
        g.append(text(seal_x + 28, y + 39, f"Prioridade {prio}", 12, pr_col, weight=600))

        # linha de metricas com icones (nivel 2)
        my = y + 64
        mx = nx
        sent_col, sent_lbl = SENT[sent]
        g.append(icon("bar-chart", mx, my - 12, 15, TEXT_FAINT, sw=2))
        g.append(text(mx + 20, my, f"{cli} clientes", 13, TEXT_DIM, font=FONT, weight=500))
        seg = mx + 20 + len(f"{cli} clientes") * 7.0 + 22
        g.append(text(seg - 14, my, "·", 13, TEXT_GHOST))
        g.append(icon("credit-card", seg, my - 12, 15, TEXT_FAINT, sw=2))
        g.append(text(seg + 20, my, f"{pag} pagantes", 13, TEXT_DIM, font=FONT, weight=500))
        seg2 = seg + 20 + len(f"{pag} pagantes") * 7.0 + 22
        g.append(text(seg2 - 14, my, "·", 13, TEXT_GHOST))
        g.append(f'<circle cx="{seg2+6}" cy="{my-4}" r="4" fill="{sent_col}"/>')
        g.append(text(seg2 + 18, my, sent_lbl, 13, sent_col, weight=600))

        # barra de indice de dor (nivel 3) — rotulo + valor inline, barra curta
        # (deixa a coluna da direita livre para as acoes, sem colisao)
        by = y + 86
        g.append(text(nx, by + 8, "ÍNDICE DE DOR", 10, TEXT_FAINT, weight=600, spacing="0.8"))
        val_x = nx + 108
        g.append(text(val_x, by + 9, str(idx), 14, TEXT, font=MONO, weight=600))
        bx = nx
        bw = cw * 0.42  # barra curta: nao alcanca a zona de acoes
        g.append(rrect(bx, by + 18, bw, 8, 4, INK, CHARCOAL, 1))
        gid = f"barfill{i}"
        c2 = "#eb9090" if prio == "Alta" else (GOLD_FILL if prio == "Média" else CHARCOAL2)
        c1 = pr_col if prio != "Baixa" else CHARCOAL2
        g.append(f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
                 f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>')
        g.append(rrect(bx, by + 18, max(10, bw * idx / 100), 8, 4, f"url(#{gid})"))

        # acoes discretas no rodape (linha propria, separadas por divisor sutil)
        fy = y + card_h - 38
        g.append(f'<line x1="{nx}" y1="{fy}" x2="{cx+cw-24}" y2="{fy}" stroke="{CHARCOAL}" stroke-width="1"/>')
        btn_w = 132
        bx2 = cx + cw - btn_w - 24
        g.append(pill(bx2, fy + 8, btn_w, 30, CARD, CHARCOAL2))
        g.append(icon("arrow-right", bx2 + 14, fy + 15, 14, INDIGO_LIGHT, sw=2))
        g.append(text(bx2 + 34, fy + 28, "Virar melhoria", 12.5, INDIGO_LIGHT, weight=600))
        g.append(text(bx2 - 18, fy + 28, "Ver feedbacks", 12.5, TEXT_DIM, weight=600, anchor="end"))

    g.append("</svg>")
    return "".join(g)


# ===========================================================================
# TELA 2 — MELHORIAS (roadmap / board)
# ===========================================================================
def tela_melhorias():
    H = 624
    cx = SIDEBAR_W + 40
    cw = W - cx - 40
    g = [svg_open(W, H)]
    g.append(sidebar(H, "Mapeamento"))  # Melhorias mora fora do menu; Mapeamento ativo
    # cabecalho com botao primario "+ Nova melhoria" a direita
    g.append(page_head(cx, "Melhorias", "Você pediu, a gente fez."))
    nb_w, nb_h = 168, 40
    nbx = cx + cw - nb_w
    g.append(f'<defs><linearGradient id="primg" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="#7c6cf0"/><stop offset="1" stop-color="{INDIGO_DEEP}"/></linearGradient></defs>')
    g.append(rrect(nbx, 40, nb_w, nb_h, RADIUS_SM, "url(#primg)", INDIGO_DEEP, 1,
                   extra='filter="url(#softShadow)"'))
    g.append(icon("plus", nbx + 20, 50, 16, "#ffffff", sw=2.2))
    g.append(text(nbx + 44, 65, "Nova melhoria", 13.5, "#ffffff", weight=600))

    # --- 3 colunas: Ideias / Fazendo / Entregue ---
    cols = [
        ("Ideias", 3, [
            ("Filtro de questões por banca", 6, None),
            ("Modo escuro no app", 4, None),
            ("Baixar apostila em PDF", 3, None),
        ]),
        ("Fazendo", 2, [
            ("Melhorar navegação do app", 5, None),
            ("Reduzir tempo de carregamento das videoaulas", 2, None),
        ]),
        ("Entregue", 2, [
            ("Corrigir erro no pagamento", 8, "notify"),
            ("Reativar conteúdo de Constitucional", 3, None),
        ]),
    ]
    col_top = 116
    gutter = 20
    col_w = (cw - gutter * 2) / 3
    col_h = H - col_top - 40
    dot_cols = [TEXT_GHOST, GOLD_FILL, INDIGO]  # marcador por estagio

    for ci, (cname, count, cards_) in enumerate(cols):
        colx = cx + ci * (col_w + gutter)
        # coluna como trilho (ink)
        g.append(rrect(colx, col_top, col_w, col_h, RADIUS, INK, CHARCOAL, 1,
                       extra='filter="url(#softShadow)"'))
        # cabecalho da coluna
        g.append(f'<circle cx="{colx+18}" cy="{col_top+24}" r="4.5" fill="{dot_cols[ci]}"/>')
        g.append(text(colx + 30, col_top + 28, cname.upper(), 11, TEXT_FAINT, weight=600, spacing="0.8"))
        # contador
        g.append(pill(colx + col_w - 44, col_top + 13, 28, 22, CARD, CHARCOAL))
        g.append(text(colx + col_w - 30, col_top + 28, str(count), 12, TEXT_DIM, font=MONO, weight=600, anchor="middle"))
        g.append(f'<line x1="{colx+14}" y1="{col_top+44}" x2="{colx+col_w-14}" y2="{col_top+44}" stroke="{CHARCOAL}" stroke-width="1"/>')

        # cards de melhoria
        cyc = col_top + 58
        for title, pedidos, special in cards_:
            # altura dinamica: titulo (1-2 linhas) + chip (+ faixa notify)
            two_lines = len(title) > 26
            ch = 86 if not two_lines else 104
            if special == "notify":
                ch += 56
            inx = colx + 12
            inw = col_w - 24
            g.append(card(inx, cyc, inw, ch, r=RADIUS_SM, fill=CARD, shadow=True))
            tx = inx + 15
            # titulo (quebra em 2 linhas se preciso)
            if not two_lines:
                g.append(text(tx, cyc + 28, title, 14, TEXT, font=FONT_DISPLAY, weight=600, spacing="-0.2"))
                chip_y = cyc + 46
                if special == "notify":
                    g.append(icon("check", inx + inw - 30, cyc + 16, 15, INDIGO_LIGHT, sw=2.5))
            else:
                w1, w2 = _wrap2(title, 24)
                g.append(text(tx, cyc + 26, w1, 14, TEXT, font=FONT_DISPLAY, weight=600, spacing="-0.2"))
                g.append(text(tx, cyc + 44, w2, 14, TEXT, font=FONT_DISPLAY, weight=600, spacing="-0.2"))
                chip_y = cyc + 64
                if special == "notify":
                    g.append(icon("check", inx + inw - 30, cyc + 14, 15, INDIGO_LIGHT, sw=2.5))
            # chip "X clientes pediram"
            chw = 132
            g.append(pill(tx, chip_y, chw, 24, INK, CHARCOAL))
            g.append(icon("bar-chart", tx + 9, chip_y + 5, 13, INDIGO_LIGHT, sw=2))
            g.append(tspan_line(tx + 28, chip_y + 16,
                                [(str(pedidos), INDIGO_LIGHT, 700),
                                 (" clientes pediram", TEXT_DIM, 500)], 11.5))

            # faixa de destaque verde "X esperando retorno -> Avisar"
            if special == "notify":
                fy = chip_y + 36
                fw = inw - 30
                g.append(rrect(tx, fy, fw, 44, RADIUS_XS,
                               "rgba(37,211,102,0.10)", "rgba(37,211,102,0.40)", 1))
                g.append(icon("check", tx + 11, fy + 9, 14, "#128c41", sw=2.5))
                g.append(tspan_line(tx + 32, fy + 19,
                                    [("8 clientes esperando", "#128c41", 600)], 11.5))
                g.append(text(tx + 32, fy + 34, "retorno", 11.5, "#128c41", weight=600))
                # botao Avisar (verde)
                avw = 76
                g.append(f'<defs><linearGradient id="wag" x1="0" y1="0" x2="0" y2="1">'
                         f'<stop offset="0" stop-color="#2ee072"/><stop offset="1" stop-color="{WA_GREEN_DEEP}"/></linearGradient></defs>')
                g.append(rrect(tx + fw - avw, fy + 8, avw, 28, RADIUS_XS, "url(#wag)", WA_GREEN_DEEP, 1))
                g.append(text(tx + fw - avw / 2, fy + 26, "Avisar", 12.5, "#07210f", weight=700, anchor="middle"))

            cyc += ch + 12

    g.append("</svg>")
    return "".join(g)


def _wrap2(s, n):
    """Quebra grosseira em 2 linhas perto de n chars."""
    if len(s) <= n:
        return s, ""
    words = s.split()
    l1 = ""
    for w in words:
        if len(l1) + len(w) + 1 <= n:
            l1 = (l1 + " " + w).strip()
        else:
            break
    l2 = s[len(l1):].strip()
    return l1, l2


# ===========================================================================
# TELA 3 — LOOP (modal "Avisar quem pediu" sobre a tela de Melhorias esmaecida)
# ===========================================================================
def tela_loop():
    H = 720
    cx = SIDEBAR_W + 40
    cw = W - cx - 40
    g = [svg_open(W, H)]
    # fundo: reaproveita a tela de melhorias como contexto, esmaecido
    g.append(sidebar(H, "Mapeamento"))
    g.append(page_head(cx, "Melhorias", "Você pediu, a gente fez."))
    # colunas fantasma so pra dar contexto atras do scrim
    for ci in range(3):
        col_w = (cw - 40) / 3
        colx = cx + ci * (col_w + 20)
        g.append(rrect(colx, 116, col_w, H - 156, RADIUS, INK, CHARCOAL, 1))
        g.append(text(colx + 30, 144, ["IDEIAS", "FAZENDO", "ENTREGUE"][ci], 11, TEXT_GHOST, weight=600, spacing="0.8"))
        for k in range(3):
            g.append(rrect(colx + 12, 160 + k * 92, col_w - 24, 78, RADIUS_SM, CARD, CHARCOAL, 1))

    # scrim (backdrop blur do app: rgba(26,24,48,0.42))
    g.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="rgba(26,24,48,0.46)"/>')

    # --- painel modal ---
    mw, mh = 564, 632
    mx = (W + SIDEBAR_W) / 2 - mw / 2  # centraliza na area de conteudo
    my = (H - mh) / 2
    g.append(rrect(mx, my, mw, mh, RADIUS, CARD, CHARCOAL2, 1, extra='filter="url(#popShadow)"'))
    g.append(rrect(mx + 1, my + 1, mw - 2, RADIUS, RADIUS - 1, "rgba(255,255,255,0.6)", extra='opacity="0.6"'))

    pad = 28
    inx = mx + pad
    inw = mw - pad * 2
    right = mx + mw - pad

    # head
    g.append(text(inx, my + 40, "Avisar quem pediu", 19, TEXT, font=FONT_DISPLAY, weight=700, spacing="-0.4"))
    g.append(icon("x", right - 16, my + 26, 18, TEXT_FAINT, sw=2))
    g.append(f'<line x1="{inx}" y1="{my+60}" x2="{right}" y2="{my+60}" stroke="{CHARCOAL}" stroke-width="1"/>')

    # TOPO: a melhoria entregue (faixa de destaque)
    by = my + 80
    g.append(rrect(inx, by, inw, 56, RADIUS_SM, PROMOTER_SOFT, PROMOTER_LINE, 1))
    g.append(f'<circle cx="{inx+28}" cy="{by+28}" r="13" fill="{INDIGO}"/>')
    g.append(icon("check", inx + 20, by + 20, 16, "#ffffff", sw=3))
    g.append(text(inx + 52, by + 24, "MELHORIA ENTREGUE", 9.5, INDIGO_LIGHT, weight=700, spacing="0.8"))
    g.append(text(inx + 52, by + 43, "Corrigir erro no pagamento", 15.5, TEXT, font=FONT_DISPLAY, weight=600, spacing="-0.3"))

    # MEIO: lista de quem pediu
    ly = by + 56 + 38
    g.append(text(inx, ly, "QUEM PEDIU", 10.5, TEXT_FAINT, weight=600, spacing="0.8"))
    g.append(text(right, ly, "8 clientes", 10.5, TEXT_FAINT, weight=600, anchor="end"))
    ly += 18
    pessoas = [
        ("João Marques", "+55 24 9••••-1820", "JM", "pagante"),
        ("Beatriz Lima", "+55 11 9••••-4471", "BL", "pagante"),
        ("Carlos Tavares", "+55 31 9••••-0093", "CT", "pagante"),
    ]
    row_h = 44
    for i, (nome, fone, ini, tag) in enumerate(pessoas):
        ry = ly + i * row_h
        g.append(f'<line x1="{inx}" y1="{ry+row_h-2}" x2="{right}" y2="{ry+row_h-2}" stroke="{CHARCOAL}" stroke-width="1"/>')
        g.append(avatar(inx, ry + 5, 32, ini, INDIGO_LIGHT, PROMOTER_SOFT, PROMOTER_LINE))
        g.append(text(inx + 44, ry + 21, nome, 13.5, TEXT, weight=600))
        g.append(text(inx + 44, ry + 37, fone, 12, TEXT_FAINT, font=MONO))
        cw_ = 70
        g.append(pill(right - cw_, ry + 11, cw_, 22, PASSIVE_SOFT, PASSIVE_LINE))
        g.append(text(right - cw_ / 2, ry + 26, "pagante", 11, GOLD_SOFT, weight=600, anchor="middle"))
    # linha "+ 5 outros"
    last_y = ly + len(pessoas) * row_h
    g.append(text(inx, last_y + 18, "+ 5 outros clientes", 12, TEXT_DIM, weight=500))
    g.append(text(right, last_y + 18, "todos receberão a mensagem", 11.5, TEXT_FAINT, anchor="end"))

    # PREVIA da mensagem (balao estilo WhatsApp)
    py = last_y + 46
    g.append(text(inx, py, "PRÉVIA DA MENSAGEM", 10.5, TEXT_FAINT, weight=600, spacing="0.8"))
    py += 12
    chat_h = 100
    g.append(rrect(inx, py, inw, chat_h, RADIUS_SM, "rgba(37,211,102,0.05)", "rgba(37,211,102,0.22)", 1))
    bub_w = inw - 86
    bub_x = inx + 18
    bub_y = py + 16
    bub_h = chat_h - 32
    g.append(rrect(bub_x, bub_y, bub_w, bub_h, 12, "rgba(37,211,102,0.16)", "rgba(37,211,102,0.30)", 1))
    g.append(f'<path d="M{bub_x+13},{bub_y+2} L{bub_x-5},{bub_y} L{bub_x+13},{bub_y+14} Z" fill="rgba(37,211,102,0.16)"/>')
    msg1 = "Oi João! \U0001F44B  Você comentou sobre o erro no"
    msg2 = "pagamento — a gente corrigiu. Obrigado por"
    msg3 = "avisar! \U0001F64C"
    g.append(text(bub_x + 16, bub_y + 24, msg1, 13, "#0a3d1c", font=FONT, weight=500))
    g.append(text(bub_x + 16, bub_y + 43, msg2, 13, "#0a3d1c", font=FONT, weight=500))
    g.append(text(bub_x + 16, bub_y + 62, msg3, 13, "#0a3d1c", font=FONT, weight=500))
    g.append(text(bub_x + bub_w - 14, bub_y + bub_h - 9, "14:32", 10, "#3b7a52", font=MONO, anchor="end"))

    # FOOT: botoes (ancorados ao rodape do painel)
    fy = my + mh - 72
    g.append(f'<line x1="{inx}" y1="{fy}" x2="{right}" y2="{fy}" stroke="{CHARCOAL}" stroke-width="1"/>')
    sb_w = 158
    g.append(rrect(inx, fy + 14, sb_w, 44, RADIUS_SM, CARD, CHARCOAL2, 1))
    g.append(icon("pencil", inx + 22, fy + 28, 15, TEXT, sw=2))
    g.append(text(inx + 46, fy + 42, "Editar mensagem", 13.5, TEXT, weight=600))
    pb_w = 200
    pbx = right - pb_w
    g.append(f'<defs><linearGradient id="sendg" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="#7c6cf0"/><stop offset="1" stop-color="{INDIGO_DEEP}"/></linearGradient></defs>')
    g.append(rrect(pbx, fy + 14, pb_w, 44, RADIUS_SM, "url(#sendg)", INDIGO_DEEP, 1,
                   extra='filter="url(#softShadow)"'))
    g.append(icon("send", pbx + 28, fy + 28, 16, "#ffffff", sw=2))
    g.append(text(pbx + 54, fy + 42, "Enviar para os 8", 14, "#ffffff", weight=700))

    g.append("</svg>")
    return "".join(g)


if __name__ == "__main__":
    jobs = [
        ("mockup_mapeamento", tela_mapeamento),
        ("mockup_melhorias", tela_melhorias),
        ("mockup_loop", tela_loop),
    ]
    for name, fn in jobs:
        svg = fn()
        png = os.path.join(OUT, name + ".png")
        ok = render(name, svg, png)
        print(("OK " if ok else "FALHOU ") + png)
