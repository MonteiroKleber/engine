# Etapa 04 — Prompts (Claude Code)

PROMPT 04.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-1/04-runtime-gates/spec.md` e siga como contrato.
2) Gere `docs/specs/fase-1/04-runtime-gates/gates-matrix.md` mapeando os endpoints mutáveis do Finance e seus gates reais no código (ordem e local de enforcement).
3) Gere `docs/specs/fase-1/04-runtime-gates/errors.md` com os erros determinísticos esperados por gate.

Regras:
- Se encontrar allow por default quando **não há mandate aplicável** ou **não há autonomia rule aplicável**, marque como risco crítico (viola “nenhuma execução fora de mandato”).
- Não implemente mudança de código neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 04.2
[[CLAUDE_CODE_START]]
Implementação (MVP):
1) Aplique a semântica canônica de mandates e autonomy (ver `docs/specs/fase-1/04-runtime-gates/spec.md`):
   - `mandates.json` existe, mas não há mandate aplicável ao endpoint/phase → deny (`MANDATE_DENIED`)
   - `autonomy.json` existe, mas não há rule aplicável ao endpoint/phase → deny (`AUTONOMY_INSUFFICIENT`)
2) Garanta que o runtime continue emitindo eventos no ledger para allow/deny:
   - `POLICY_*` (pre/post)
   - `MANDATE_EVALUATED`
   - `AUTONOMY_EVALUATED`
3) Adicione/ajuste testes para provar, no mínimo:
   - `POST /finance/expenses` é negado se não existir mandate aplicável (mesmo com RBAC ok)
   - `POST /approvals/{approval_id}/decide` é negado se não existir mandate aplicável
   - operações são negadas se não existir autonomy rule aplicável
   - com mandates + autonomy regras mínimas, o fluxo Finance end-to-end funciona
   - decisões allow/deny deixam trilha no ledger

Notas:
- SAFE_MODE por “contrato ausente” já é responsabilidade do loader/manifest (Etapa 03). Aqui o foco é semântica de runtime quando os contratos existem.

Saída:
- Patch mínimo + testes + atualização de docs da Etapa 04.
[[CLAUDE_CODE_END]]
