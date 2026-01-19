# Etapa 07 — Prompts (Claude Code)

PROMPT 07.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-1/07-ege-proof/spec.md` e siga como contrato.
2) Mapeie no código:
   - drift enforcement
   - pin após deploy (ou equivalente)
   - rollback automático
   - SAFE_MODE triggers
   - onde `trace.json` é gerado e se ele persiste para deploy/run (não só em memória)
   - estado atual de `contract_ledger.json` no bundle default `bundles/finance-pilot` e se ele atende prova offline
3) Escreva:
   - `docs/specs/fase-1/07-ege-proof/proof-offline.md` com passos para auditor validar sem runtime.
   - `docs/specs/fase-1/07-ege-proof/mvp-checklist.md` preenchendo ✅/⚠️/❌ com evidências.

Regras:
- Se `contract_ledger.json` ainda for placeholder (sem hashes/idl_hash), marcar como GAP bloqueador para “prova offline”.
- Se `trace.json` não persistir para deploy/run, marcar como GAP (pode ser bloqueador dependendo do DoD acordado).
[[CLAUDE_CODE_END]]

PROMPT 07.2
[[CLAUDE_CODE_START]]
Se o checklist apontar gaps para o MVP:
1) Implemente o mínimo necessário para fechar os gaps mais críticos primeiro (governança e prova).
2) Adicione testes para drift/pin/rollback/safe_mode.
3) Atualize `mvp-checklist.md` marcando o que mudou e por quê.

Notas (direção do MVP):
- Se `contract_ledger.json` do `bundles/finance-pilot` for placeholder, atualize-o para um schema de prova offline (coerente com o que o ISE já gera em `src/engine/ise/contract_ledger.py`) e atualize o SHA256 no manifest.
- Se `trace.json` não for persistido para deploy/run, implemente persistência mínima e referencie em `proof-offline.md`.
[[CLAUDE_CODE_END]]
