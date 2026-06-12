# Board do Trello — Bizzu Growth (Jair) · cards prontos para colar

> Estrutura para o board que o Felipe criou. Crie 6 listas e cole os cards (título + descrição).
> Marcadores sugeridos: 🎨 Aquisição · 🎧 Retenção · 🔧 Setup · 🔥 Prioridade.
> Atualizado 2026-06-09. Os cards de "✅ Feito" são o que já fizemos no Claude Code hoje.

---

## Lista: ✅ FEITO (09/06)

**bizzu_midia clonado e destravado**
Repo `felipelemes/bizzu_midia` clonado em Documents/Projetos; `.env` posicionado; `npm install` + Playwright OK. Pronto para gerar conteúdo.

**API de Clientes integrada no Escuta (13 perfis)**
Cliente HTTP + classificador de perfis + `sync_partner_customers.py` (dry-run). 233 clientes classificados; 40 testes verdes. Sem disparo (só preparação).

**Documento-mestre + pacote de contexto p/ Claude.ai**
`MISSAO_JAIR.md`, `api-clientes-partner.md`, `BIZZU_ESCUTA_CONTEXT_PACK.md` criados. Pronto para subir no Projects.

---

## Lista: 🔧 SETUP & ACESSOS (com o Felipe)

**Trocar a GEMINI_API_KEY pela minha** 🔧
A chave atual é a do Felipe (compartilhada). Criar a minha grátis em aistudio.google.com/apikey e colar no `.env` do bizzu_midia (não dividir quota).

**Acesso ao Instagram (central de contas)** 🔧🔥
Mandar meu @ no WhatsApp pro Felipe autorizar via central de contas. Sem isso não publico.

**Links dos grupos de Telegram** 🔧
Pedir ao Felipe os grupos de concurso (fiscal/policial) pra estudar a dinâmica do público e prospectar.

**Iniciar homologação do app na Meta** 🔧🔥
Criar app Meta Business + Instagram Professional e submeter caso de uso. Aprovação leva 4-7 dias — começar JÁ. (Permite publicar via API oficial depois.)

**Confirmar preço vigente** 🔧
Conteúdo novo usa R$20/mês · R$120/ano; o site pode ter resíduo de R$10/R$60 (promo vencida). Alinhar com o Felipe pra não publicar valor errado.

**Listar ferramentas/assinaturas p/ a Bizzu contratar** 🔧
Montar lista (geração de vídeo/shorts, agendador de post, transcrição etc.) com plano sugerido. Felipe testa mensal antes de anual.

---

## Lista: 🎨 AQUISIÇÃO — Instagram (bizzu_midia)

**Ler o brand-guidelines-bizzu.html** 🎨🔥
Bíblia da marca (cores Indigo #6C5CE7 / Gold #F5A623 / dark #09090B; Space Grotesk + Inter + JetBrains Mono; voice "mentor estratégico"; sem travessão; "Bizzu." com ponto gold). Obrigatório antes de gerar.

**Benchmark de concorrentes (atualizar mar→jun)** 🎨🔥
Atualizar o `analise-mercado-instagram-concursos.md`: Victor Concursos (notícia quente), Gran (conversão/meme/motivacional), Guruja (nicho/consultoria) + novos. Destilar ganchos, formatos e frequência que engajam.

**Criar os 3 templates base** 🎨🔥
Com base no benchmark: (1) "saiu edital" de busca/feed, (2) Raio-X do que pesa, (3) como começar. Fundamentar no que funciona, não no achismo.

**Rodar Daily Editais e revisar a arte (baseline)** 🎨
`node agents/daily-editais/run-daily-editais.js --date <hoje>` → revisar PNGs em output/. Ver o que a máquina já produz hoje pra comparar com o estado da arte.

**Definir avatar/mascote** 🎨
Dentro da marca (sem humanos/stock): um objeto editorial recorrente que vira "personagem" da Bizzu. Testar versões.

**Publicar via API oficial da Meta** 🎨
Após homologação: construir `lib/instagram-client.js` (criar containers de slide → carrossel → publicar). Conectar ao botão "postar" da UI. Até lá, postar manual.

**Melhorar o PDF de prospecção** 🎨
Inserir perfil do concurseiro + comparativo com concorrentes + screenshot do Raio-X real + ROI. (Já prospecta bem mesmo "feio".)

---

## Lista: 🎧 RETENÇÃO — Feedback (Escuta + API de Clientes)

**Rodar o sync de perfis e revisar a base** 🎧🔥
`py scripts/sync_partner_customers.py --dry-run` (auditar) → sem flag faz o upsert. 233 clientes em 13 perfis. Revisar a distribuição com o Felipe.

**Coletar NPS dos 100 ativos silenciosos** 🎧🔥
Maior balde (43%): ativos que nunca opinaram. Disparar o NPS revela a saúde real da base. (Só com opt-in, em teste primeiro.)

**Reter os 34 "vai expirar"** 🎧🔥
Têm acesso mas estão por expirar — janela curta. Mensagem de retenção antes de virar churn.

**Aprender com os 27 churn rápido** 🎧
Cancelaram ≤7 dias / garantia. Exit survey: o que não atendeu de cara (fricção de entrada).

**Pedir depoimento aos 33 promotores** 🎧
Clientes ativos com nota 9-10. Base real de depoimento/indicação (substitui os depoimentos fake do site).

**Criar as surveys novas no Escuta** 🎧
Retenção, Indicação, CSAT Onboarding, Escuta de Detrator — reusando o motor de survey existente.

**Teste de disparo WhatsApp (Jair ↔ Felipe)** 🎧🔥
Validar o fluxo entre nós dois antes de qualquer cliente real (evitar ban / erro).

**Coordenar double-touch de churn com o Felipe** 🎧
PAYMENT_FAILED já recebe winback por e-mail. Definir cadência pra não mandar e-mail + WhatsApp juntos.

---

## Lista: 📥 BACKLOG / IDEIAS

**Threads + Shorts (YouTube/IG)** — ampliar alcance; reaproveitar conteúdo (decisão da reunião 05/06).
**Radar → "saiu seu edital" no WhatsApp** — gancho de altíssimo valor (pipeline radar-editais).
**Espelhar NPS in-app no Escuta** — unificar feedback in-app + WhatsApp.
