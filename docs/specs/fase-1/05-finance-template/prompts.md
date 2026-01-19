# Etapa 05 — Prompts (Claude Code)

PROMPT 05.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-1/05-finance-template/spec.md` e siga como contrato.
2) Localize o bundle/template Finance existente (atualmente `bundles/finance-pilot`) e os endpoints.
3) Escreva:
   - `docs/specs/fase-1/05-finance-template/finance-contract.md`
   - `docs/specs/fase-1/05-finance-template/finance-bundle.md`

Regras:
- Trate `bundles/finance-pilot` como a referência atual do MVP e documente:
  - contratos presentes e seus schemas
  - regras mínimas de mandates/autonomy necessárias para o fluxo funcionar sob a semântica canônica
  - consistência entre `approvals.json` e roles em `rbac.json`
- Não implemente mudança de código neste prompt (apenas documentação + gaps).
[[CLAUDE_CODE_END]]

PROMPT 05.2
[[CLAUDE_CODE_START]]
Se houver gaps no bundle Finance:
1) Atualize o bundle Finance “golden” para cumprir o contrato (mínimo).
2) Adicione/ajuste testes E2E para garantir o fluxo end-to-end.
3) Garanta eventos no ledger para cada decisão relevante.

Saída:
- Patch mínimo + testes + docs atualizadas.
[[CLAUDE_CODE_END]]
