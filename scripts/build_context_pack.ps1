# build_context_pack.ps1
# Consolida os docs canonicos do projeto (Claude Code) num UNICO arquivo .md,
# sanitiza segredos e gera um "Context Pack" pronto para subir no Project Knowledge
# do Claude.ai (funcao Projetos). Rode com: powershell -File scripts\build_context_pack.ps1
$ErrorActionPreference = 'Stop'

$root   = "C:\Users\jboni\Documents\Projetos\escuta"
$docs   = Join-Path $root "docs"
$outDir = Join-Path $docs "_context-pack"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out = Join-Path $outDir "BIZZU_ESCUTA_CONTEXT_PACK.md"

# Ordem logica: visao -> integracao -> analises -> corpus (RAG) -> handoff
$files = @(
  "docs\MISSAO_JAIR.md",
  "docs\BIZZU_ESCUTA_MASTER.md",
  "docs\CONTEXTO_BIZZU.md",
  "docs\INTEGRACAO_BIZZU.md",
  "docs\INTEGRACAO_FEEDBACK.md",
  "docs\analise-bizzu\feedback-nativo.md",
  "docs\analise-bizzu\api-clientes-partner.md",
  "docs\analise-bizzu\bizzu-midia.md",
  "docs\analise-bizzu\backend.md",
  "docs\analise-bizzu\frontend.md",
  "docs\analise-bizzu\site.md",
  "docs\analise-bizzu\landing-pages.md",
  "docs\analise-bizzu\radar-editais.md",
  "docs\analise-bizzu\infra.md",
  "docs\corpus_bizzu\o-que-e-bizzu.md",
  "docs\corpus_bizzu\funcionalidades.md",
  "docs\corpus_bizzu\planos-e-precos.md",
  "docs\corpus_bizzu\cancelamento-e-garantia.md",
  "docs\corpus_bizzu\conta-e-suporte.md"
)
# + handoff mais recente (data mais alta)
$hand = Get-ChildItem (Join-Path $docs "SESSAO_HANDOFF_*.md") -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
if ($hand) { $files += "docs\$($hand.Name)" }

$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm')
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# BIZZU x ESCUTA - CONTEXT PACK (para a funcao Projetos do Claude.ai)")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("> Pacote unico de contexto, gerado automaticamente a partir do projeto Claude Code.")
[void]$sb.AppendLine("> Gerado em $stamp. Suba ESTE arquivo no Project Knowledge do Claude.ai e cole as")
[void]$sb.AppendLine("> Custom Instructions de PROJECT_CUSTOM_INSTRUCTIONS.md. Regenere quando os docs mudarem.")
[void]$sb.AppendLine("> Segredos/PII foram redigidos automaticamente (procure por <REDACTED...>).")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## Fontes incluidas neste pacote")
foreach ($f in $files) { [void]$sb.AppendLine("- $f") }

foreach ($f in $files) {
  $p = Join-Path $root $f
  if (Test-Path $p) {
    $content = Get-Content $p -Raw -Encoding UTF8
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("================================================================")
    [void]$sb.AppendLine("FONTE: $f")
    [void]$sb.AppendLine("================================================================")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine($content)
  } else {
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("(!! fonte ausente: $f)")
  }
}

$text = $sb.ToString()

# --- Sanitizacao de segredos / PII (defesa em profundidade) ---
$text = [regex]::Replace($text, '\b[0-9a-fA-F]{32,}\b', '<REDACTED-KEY>')   # chaves hex (ex: WAHA key)
$text = [regex]::Replace($text, '\b55\d{11}\b', '<REDACTED-PHONE>')          # telefone BR (DDI 55 + 11)
$text = $text -replace 'bizzu_dev_2026', '<REDACTED-PWD>'
$text = $text -replace 'SenhaForte!2026', '<REDACTED-PWD>'

Set-Content -Path $out -Value $text -Encoding utf8

$kb = [math]::Round((Get-Item $out).Length/1KB,1)
$approxTokens = [math]::Round($text.Length/4)
"Context Pack gerado:"
"  Arquivo : $out"
"  Tamanho : $kb KB  (~$approxTokens tokens estimados)"
"  Fontes  : $($files.Count) docs"
"Proximo passo: suba esse .md no Project Knowledge do Claude.ai (veja COMO_SUBIR_NO_CLAUDE_PROJECTS.md)."