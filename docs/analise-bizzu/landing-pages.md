# Análise: bizzu-repos/landing-pages

**Repositório:** `C:\Users\jboni\Documents\Projetos\bizzu-repos\landing-pages`
**Analisado em:** 2026-06-08
**Arquivos lidos:** `index.html`, `lista-de-espera/index.html`, `relatorios/auditor-fiscal-sefaz-sp-2026.html`, `relatorios/auditor-fiscal-sefaz-rn-2026.html`, `relatorios/analista-legislativo-camara-dos-deputados-2026.html`, `sitemap.xml`, `tag.txt`

---

## Resumo Executivo

- **Stack:** HTML/CSS/JS puro, sem framework. Hospedado em `lp.bizzu.ai`. Serve como entry point de toda a aquisição orgânica/paga.
- **Produto em pré-lançamento:** plataforma ainda não no ar ("fase final de desenvolvimento"). Captação é 100% lista de espera — sem venda, sem preço, sem garantia, sem urgência declarada.
- **Captação de leads: somente email**, via Google Forms (entry `entry.19628127`, form ID `1FAIpQLSePfBW-Xh1VF3D0pqLkK7jcSSU5SfFUHUd75SC0N8evTMwnkA`). Nenhum campo de telefone ou WhatsApp em nenhuma das páginas.
- **Prova social zero** (sem depoimentos, sem contagem de usuários, sem logos de clientes). Os números exibidos são claims de banco de dados ("500k questões", "5 bancas"), não usuários reais.
- **Tracking:** só Google Analytics GA4 (`G-6WFC2DE7VE`). Nenhum Meta Pixel, nenhum PostHog, nenhum pixel de retargeting.
- **Oportunidade Escuta:** lead entra com email apenas; capturar WhatsApp (ou enriquecer via link wa.me) seria upgrade direto com zero fricção adicional — e o produto ainda não existe para competir.

---

## 1. O Que É & Stack

### Produto
A Bizzu é uma plataforma de estudos para concursos públicos baseada em IA. Posicionamento: "não é curso, não vende aulas/apostilas". Proposta de valor central: ranquear tópicos por probabilidade real de cair, usando análise de 500 mil questões históricas das 5 maiores bancas (CEBRASPE, FGV, FCC, CESGRANRIO, VUNESP). Features prometidas:

1. **Raio X da Prova** — ranking de prioridade de tópicos por edital/banca/cargo
2. **Plano de Estudos automático** — cronograma gerado a partir do Raio X
3. **Banco de Questões por tópico** — questões selecionadas + explicação de erros por IA
4. **Revisão Espaçada automática** — revisões em 24h, 7, 15 e 30 dias

### Stack
- HTML/CSS/JS puro (zero frameworks, zero bundler)
- Fontes: Google Fonts (Inter, Space Grotesk, JetBrains Mono)
- Animações: IntersectionObserver + count-up JS nativo
- Sem Next.js, sem React, sem build step
- Servido em `lp.bizzu.ai` (domínio próprio, CDN não identificada pelo código)

### Estrutura de arquivos
```
landing-pages/
  index.html                          # Redirect meta-refresh 5s → lista-de-espera/
  lista-de-espera/index.html          # Landing principal (3082 linhas)
  relatorios/
    auditor-fiscal-sefaz-sp-2026.html # Raio X completo SEFAZ-SP (~5600 linhas)
    auditor-fiscal-sefaz-rn-2026.html # Raio X completo SEFAZ-RN (~3800 linhas)
    analista-legislativo-camara-dos-deputados-2026.html  # Raio X Câmara (~2200 linhas)
  sitemap.xml
  tag.txt                             # Snippet Google Analytics reutilizável
  image/favico.svg, favico.ico
```

---

## 2. Conteúdo / Copy de Conversão

### Headline principal (`lista-de-espera/index.html`, linha 2109)
> "Plano de estudos para concursos com **inteligência artificial**"

### Sub-headline (linha 2110)
> "A Bizzu analisa mais de 500 mil questões reais das maiores bancas do Brasil para mostrar quais tópicos mais caem na sua prova. Planejamento automático, questões selecionadas por tópico e revisões com repetição espaçada. Tudo baseado em dados reais, por banca, área e cargo."

### Badge / Contexto acima do H1 (linha 2107)
> "Plataforma de estudos para concursos públicos"

### Tagline / footer (linha 2847)
> "Estude o que importa."

### Seção-problema (linhas 2256–2280)
Três cards de números:
- **300+** tópicos no edital (Auditor Fiscal)
- **22** matérias para cobrir
- **0** ferramentas que resolvem isso ("Cursos vendem conteúdo. Planilhas organizam horas. Ninguém diz o que importa mais. Até agora.")

### Proof bar (linhas 2228–2248)
- 500k+ questões reais
- 5 bancas cobertas
- 12 áreas de concursos
- "estatística + ciência de dados + IA"

Estes números são **claims do produto** (banco de dados), não métricas de usuários. Nenhum depoimento, nenhuma avaliação, nenhuma contagem de "usuários cadastrados".

### Para quem é
Três perfis: Iniciante / Experiente / Profissional (trabalha e estuda).

### Posicionamento vs. concorrentes (linha 2768)
> "A Bizzu complementa qualquer método ou curso preparatório (Estratégia, Gran Cursos, Direção, entre outros). A Bizzu diz o que estudar e em que ordem priorizar. Seu curso ensina o conteúdo em si."

---

## 3. Preços / Oferta

**Nenhum preço declarado.** A única menção é vaga e de caráter especulativo, no FAQ (linha 2812):

> "A plataforma terá **planos acessíveis por assinatura mensal**. Entre na lista de espera para ser avisado no lançamento e garantir condições exclusivas de acesso antecipado."

Não há:
- Valores de lançamento
- Desconto de early access
- Garantia de devolução
- Conta regressiva / urgência real
- Quantidade de vagas limitadas

Os salários exibidos no slide panel (R$ 21.177 / R$ 13.283 / R$ 30.853,99) são dos **cargos dos concursos** analisados nos relatórios — não preços do produto (`lista-de-espera/index.html`, linhas 2883–2902).

---

## 4. Captura de Lead (CRÍTICO para Escuta)

### Mecanismo principal
**Somente email.** Dois formulários na landing principal:

| ID do form | Localização | CTA |
|---|---|---|
| `heroForm` | Hero section | "Quero acesso" |
| `ctaForm` | Seção final | "Garantir meu lugar" |

Ambos capturam apenas `input[type="email"]`. Nenhum campo de nome, telefone ou WhatsApp.

Mensagem pós-submissão (linha 2120): "Você está na lista. Avisaremos no lançamento."
Nota abaixo do botão (linha 2122): "Sem spam. Acesso antecipado para quem entrar agora."

### Destino dos leads — Google Forms
Todos os formulários (landing + 3 relatórios) submetem para o mesmo endpoint via `fetch` com `mode: 'no-cors'`:

```javascript
// lista-de-espera/index.html, linha 2935–2936
var GFORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSePfBW-Xh1VF3D0pqLkK7jcSSU5SfFUHUd75SC0N8evTMwnkA/formResponse';
var GFORM_ENTRY = 'entry.19628127';
```

O mesmo form ID e entry ID aparecem nos três arquivos de relatório (linhas 2212–2213, 3737–3738, 5552–5553). Não há webhook próprio, não há envio para CRM, não há API Bizzu sendo chamada — tudo vai direto para uma planilha Google Forms.

### Slide Panel (segundo ponto de captura)
Um painel lateral deslizante abre automaticamente 2,5 segundos após o carregamento (se não houver email salvo em `localStorage`), ou via FAB (botão flutuante). Permite selecionar um dos 3 concursos disponíveis e inserir email para acessar o "Raio X gratuito":

```javascript
// lista-de-espera/index.html, linhas 2944–2949
var REPORTS = [
  { cargo: 'Analista Legislativo – Câmara dos Deputados', banca: 'CESPE', salario: 'R$ 31.403',
    file: '/relatorios/analista-legislativo-camara-dos-deputados-2026.html' },
  { cargo: 'Auditor Fiscal da Receita Estadual – SEFAZ-RN', banca: 'CEBRASPE (CESPE)', salario: 'R$ 13.283',
    file: '/relatorios/auditor-fiscal-sefaz-rn-2026.html' },
  { cargo: 'Analista Legislativo – Câmara dos Deputados', banca: 'CEBRASPE (CESPE)', salario: 'R$ 30.853,99',
    file: '/relatorios/analista-legislativo-camara-dos-deputados-2026.html' },
];
```

Após o email, abre o relatório em nova aba. Os relatórios são HTML estáticos públicos — qualquer pessoa com a URL pode acessar sem fornecer email. Não há gate real.

### Formulários nos relatórios
Cada relatório (`sefaz-sp`, `sefaz-rn`, `analista-legislativo`) tem um formulário de "lista de espera" embutido no topo, com o mesmo endpoint Google Forms. CTA: "Quero acesso antecipado".

### Link wa.me / WhatsApp
**Inexistente.** Não há nenhum link `wa.me`, botão WhatsApp, ou campo de telefone em nenhuma das páginas. A captura é exclusivamente por email para Google Sheets.

---

## 5. Tracking / Pixels

| Ferramenta | Status | ID |
|---|---|---|
| Google Analytics (GA4) | **Ativo** em todas as páginas | `G-6WFC2DE7VE` |
| Meta Pixel (Facebook/Instagram) | **Ausente** | — |
| PostHog | **Ausente** | — |
| Hotjar / FullStory | **Ausente** | — |
| LinkedIn Insight Tag | **Ausente** | — |
| TikTok Pixel | **Ausente** | — |

O snippet GA4 está centralizado em `tag.txt` e incluído manualmente em cada HTML. Não há tag manager (GTM), apenas o snippet direto.

---

## 6. Conteúdo dos Relatórios "Raio X"

Os três relatórios HTML são documentos de análise extensos (2.200–5.600 linhas cada), com:

- Mapa de matérias com distribuição de prioridade Alta/Média/Baixa
- Tabelas tópico a tópico com justificativas geradas por IA
- Dados de frequência histórica por banca

**Exemplo de dados reais nos relatórios:**

| Concurso | Banca | Matérias | Tópicos | Salário |
|---|---|---|---|---|
| Auditor Fiscal SEFAZ-SP | FCC | 24 | 469 | R$ 21.177,10 |
| Auditor Fiscal SEFAZ-RN | CEBRASPE | — | — | R$ 13.283,64 |
| Analista Legislativo Câmara | CEBRASPE | 10 | 106 | R$ 30.853,99 |

Os dados de frequência (ex: "Direitos e Garantias Fundamentais · 127 questões · Presente em 94% das provas CESPE") **parecem reais** — são específicos, citam quantidades e anos de provas. Não há indicação de que sejam hardcoded/fictícios na estrutura do HTML: são tabelas densas com justificativas contextualizadas por cargo.

---

## 7. Oportunidade Escuta / Análise para Integração

### Fraquezas na captação atual
1. **Somente email** — sem telefone, sem WhatsApp. Lead entra frio e fica em uma planilha Google Forms sem follow-up automatizado visível.
2. **Sem gate real nos relatórios** — os arquivos HTML são públicos. O "email para acessar" é contornável com a URL direta. Incentivo para conversão é baixo.
3. **Sem prova social** — nenhum depoimento, nenhum contador de "X concurseiros já cadastrados".
4. **Sem urgência/escassez** — nenhuma mecânica de pressão de conversão.
5. **Tracking limitado** — só GA4, sem pixel de retargeting para reimpactar visitantes.

### Ganchos para Escuta / WhatsApp
- **Lead já existe** (Google Forms → planilha) mas sem canal de ativação. WhatsApp seria o canal natural de follow-up para pré-lançamento.
- Um campo `"Receber aviso pelo WhatsApp?"` ou link `wa.me` pós-cadastro de email não conflita com nenhum mecanismo existente.
- Os relatórios "Raio X" são conteúdo de alto valor — gatilho natural para uma sequência de nutrição via WhatsApp ("você acessou o Raio X do SEFAZ-SP, quer receber dicas de estudo para esse concurso?").
- A Bizzu já tem fluxo NPS in-app básico (conforme `docs/INTEGRACAO_BIZZU.md`) — o Escuta pode se posicionar como a camada de WhatsApp que complementa esse fluxo **antes mesmo do produto entrar no ar**, na fase de lista de espera.
