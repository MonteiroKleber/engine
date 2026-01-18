# Etapa 07 — Prompts (Claude Code)

PROMPT 07.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-1/07-ege-proof/spec.md`.
2) Mapeie no código:
   - drift enforcement
   - pin após deploy (ou equivalente)
   - rollback automático
   - SAFE_MODE triggers
3) Escreva:
   - `docs/specs/fase-1/07-ege-proof/proof-offline.md` com passos para auditor validar sem runtime.
   - `docs/specs/fase-1/07-ege-proof/mvp-checklist.md` preenchendo ✅/⚠️/❌ com evidências.
[[CLAUDE_CODE_END]]

PROMPT 07.2
[[CLAUDE_CODE_START]]
Se o checklist apontar gaps para o MVP:
1) Implemente o mínimo necessário para fechar os gaps mais críticos primeiro (governança e prova).
2) Adicione testes para drift/pin/rollback/safe_mode.
3) Atualize `mvp-checklist.md` marcando o que mudou e por quê.
[[CLAUDE_CODE_END]]

