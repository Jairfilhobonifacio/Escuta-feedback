# Como levar o contexto do Claude Code → função Projetos do Claude.ai

## O que é possível (e o que não é)

| | Claude Code (PC) | Claude.ai → Projetos |
|---|---|---|
| Ler/entender todo o contexto | ✅ | ✅ (via Project Knowledge) |
| Custom instructions persistentes | ✅ (skills/CLAUDE.md) | ✅ (campo Instruções) |
| Rodar a stack, editar código, ler a máquina | ✅ | ❌ (não acessa seu PC) |
| Ler `~/.secrets`, `.env`, rodar testes | ✅ | ❌ |
| Acessar de qualquer lugar (celular/web) | ❌ | ✅ |
| Sync automático com os arquivos | (é a fonte) | ❌ por upload · ✅ via conector |

**Resumo honesto:** dá para transferir **100% do conhecimento** (o "saber"); **não** dá para transferir as **capacidades de execução** (o "fazer" na sua máquina). Então o Project vira um ótimo **estrategista de bolso**; o Claude Code continua sendo o **operador**. É uma divisão de papéis, não uma limitação a contornar.

## Caminho recomendado (upload do Context Pack) — 5 min

1. **Gere o pacote** (no Claude Code, a partir de `Documents/Projetos`):
   - skill: **`/bizzu-context-pack`**  — ou — `powershell -File escuta\scripts\build_context_pack.ps1`
   - Saída: `escuta/docs/_context-pack/BIZZU_ESCUTA_CONTEXT_PACK.md` (um único arquivo, segredos redigidos).
2. No **claude.ai** → **Projects** → **Create project** → nome: **"Bizzu × Escuta"**.
3. Em **Project knowledge / Add content**, suba o `BIZZU_ESCUTA_CONTEXT_PACK.md`.
   - (Opcional) suba também os docs individuais de `escuta/docs/` se quiser granularidade no retrieval.
4. Em **Instruções personalizadas**, cole o conteúdo de `PROJECT_CUSTOM_INSTRUCTIONS.md`.
5. Pronto. Toda conversa nesse Project já nasce com o contexto. Teste: *"onde paramos no Escuta?"*.

> **Ao atualizar os docs** no Claude Code: rode `/bizzu-context-pack` de novo e **re-suba** o arquivo
> (substituindo o anterior no Project Knowledge). É o "deploy" do conhecimento.

## Alternativas (quando quiser sync automático ou o código junto)

- **Conector GitHub** (Claude.ai Pro/Max/Team): suba os repos (inclusive o `escuta`, que hoje não tem
  remote) para o GitHub e conecte no Project. O chat passa a **ler o código-fonte** direto, sempre
  atualizado — sem re-upload manual. Ideal se quiser o chat "lendo código", não só os docs.
- **Conector Google Drive**: jogue a pasta `escuta/docs/` no Drive e conecte. Editou o doc → o Project
  reflete. Bom para os docs sem mexer com Git.
- **Híbrido (recomendado a longo prazo):** docs destilados via Context Pack (rápido, sem segredo) +
  conector GitHub para o código quando precisar de profundidade.

## Limites a saber

- **Tamanho:** o Project Knowledge tem capacidade limitada; por isso o pacote usa os **docs destilados**
  (não o código cru de 11 MB). Se precisar do código, use o conector GitHub.
- **Segredos:** o gerador redige chaves/telefone/senhas conhecidas, mas **revise** o pacote antes de subir.
  Nunca suba `.env` nem `~/.secrets`.
- **Não é tempo-real:** por upload, o conhecimento é um "snapshot" — regenere quando algo importante mudar.
- **Sem execução:** o Project não roda a stack, não testa, não acessa seu PC. Para isso, Claude Code.