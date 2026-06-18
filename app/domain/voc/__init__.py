"""Agente de Voz do Cliente (VoC) — Fase 2, function-calling sobre as tools de CS.

Infraestrutura DORMENTE: tudo aqui só roda quando `settings.voc_agent_enabled` é
True (default OFF). Com a flag OFF o fluxo de survey segue BYTE-A-BYTE como hoje —
o resolver nem importa este pacote. Componentes:

- `registry.VoCToolRegistry`: registra tools (nome/descrição/JSON Schema/executor),
  expõe a lista no formato `tools` do Groq e despacha um `tool_call` para o executor.
- `tools`: as 7 tools que operam sobre os models existentes (FeedbackItem, CsTask,
  Improvement, Contact) via a AsyncSession — sem schema novo, sem migration. A tool
  de WhatsApp fica atrás de `voc_whatsapp_tool_enabled` + 3 gates (opt-in, cooldown,
  alcançável) e é NO-OP com a flag OFF.
- `orchestrator.VoCAgentOrchestrator`: o loop (LLM pede tool → registry executa →
  resultado volta ao LLM → repete) com teto de iterações e saída segura.
"""
