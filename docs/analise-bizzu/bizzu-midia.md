# bizzu_midia — a fábrica de conteúdo (frente de AQUISIÇÃO)

> O repo de marketing/conteúdo do Jair (GitHub `felipelemes/bizzu_midia`, clonado em
> `Documents/Projetos/bizzu_midia`; package name interno `bizzu_insta`). É a **frente de aquisição**
> que complementa o Escuta (retenção). Gera artes/posts de Instagram a partir de dados reais da Bizzu.
> Analisado e validado 2026-06-09.

## O que é + stack
Node (servidor `server.js`, HTTP nativo, porta **3000**) + **Playwright** (HTML→PNG 1080×1350) +
**Gemini** (texto + imagem "nano banana 2" `gemini-3-pro-image-preview`) + **Miniflux** (Docker, RSS de
notícias). Sem framework web. Opera **localmente** na máquina do Jair.

## Os 5 subsistemas
| Subsistema | Gera | Fonte | Como rodar |
|---|---|---|---|
| **Carrossel de Cargo** (10 agentes) | carrossel premium do Raio-X, capa com arte IA | API Bizzu (Raio-X) | `node agents/run-pipeline.js --cargo <id>` |
| **Carrossel de Edital** (6 agentes) | visão geral do concurso (cargos/vagas/salários) | API Bizzu pública | `node agents/run-edital-pipeline.js <slug>` |
| **Daily Editais / Radar** (5 agentes) | post "edital novo na praça" do dia | Radar (`radar-editais.bizzu.ai`) | `node agents/daily-editais/run-daily-editais.js --date ...` |
| **Notícias** (4 agentes) | post single-image de notícia curada | Miniflux (RSS) | `/noticias.html` ou CLI |
| **Email Generator + Relatórios PDF** | e-mail transacional + **PDF de prospecção** | API Bizzu | `npm start` → localhost:3000 |

**Pipeline de arte (não alucina texto):** `07-render` (Playwright renderiza o slide com o texto exato)
→ `08-artist` (Gemini gera a arte ao redor preservando o texto, 5 variações, escolhe a 1ª). Só a capa
tem arte IA; os demais slides são HTML/CSS puro.

## Integrações (env vars em `.env`, nunca commitar)
- **API Bizzu** (`BIZZU_API_KEY`): Raio-X, editais públicos, dados de cargo → `lib/bizzu-api.js`.
- **Radar** (`RADAR_API_URL` + `RADAR_SERVICE_API_KEY`): editais novos do dia → `lib/radar-client.js`.
- **Gemini** (`GEMINI_API_KEY`): copy + caption + imagem. (Trocar pela chave própria do Jair.)
- **Miniflux** (`MINIFLUX_*`, docker-compose): agrega RSS de sites de concurso (Trilha 2).
- **Instagram/Meta:** ⚠️ **publicação 100% MANUAL hoje** — não há integração com a Graph API. A
  construir após homologação do app Meta (4-7 dias).

## Marca (brand-guidelines-bizzu.html — mesma identidade do Escuta)
Indigo `#6C5CE7` · Gold `#F5A623` (ponto do logo "Bizzu.") · dark `#09090B`. Fontes: Space Grotesk
(títulos) + Inter (corpo) + JetBrains Mono (números). Voice "mentor estratégico": Problema + Insight com
dado real + Ação. Proibido: travessão (—), "aprovação garantida", "grátis/gratuito", números por extenso.
Preços: **R$20/mês · R$120/ano**.

## Estado do código
- ✅ Os 4 pipelines + Email/PDF prontos e testados; deps instaladas (09/06).
- ⚠️ Publicação manual (sem Meta API). Cron desligado (roda sob demanda). `radar_gui.py` tem bug no
  Windows (abrir pasta usa comando macOS). Sem mascote. Scripts `.sh/.command` são macOS — ignorar.

## Benchmark de concorrentes (do analise-mercado-instagram-concursos.md, 2026-03-27)
- **@victorconcursos** (222k) — notícia quente, "SAIU EDITAL", card único, velocidade.
- **@grancursosonline** (3,2M) — conversão em massa, meme, motivacional, CTA "comenta a palavra".
- **@gurujaconcursos** (94k) — nicho fiscal/policial, tom de consultoria/jornada.
- **Padrões do nicho:** gancho de urgência + números (vagas/salário/data) + texto grande; feed mistura
  notícia/meme/venda; legível em <1s no grid de busca.
- **Espaço da Bizzu:** *"saiu o concurso → o que importa → como começar"* (notícia + diagnóstico +
  plano). Vender **clareza/priorização/ação**, não hype. Fórmula sugerida de carrossel:
  slide 1 gancho de busca · slide 2 Raio-X do que pesa · slide 3 leitura estratégica · slide 4 como a
  Bizzu ajuda. ⚠️ Esse benchmark é de março — atualizar (ver card no TRELLO_BOARD.md).

## Próximos passos
Ler o brand-guidelines → atualizar o benchmark → criar os 3 templates base → rodar o Daily como baseline
→ avatar/mascote → publicação via Meta (pós-homologação) → melhorar o PDF de prospecção.
