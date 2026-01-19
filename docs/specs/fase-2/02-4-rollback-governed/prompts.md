# Fase 2 — Etapa 2.4: Prompts (Claude Code)

PROMPT 2.4.1 (Diagnóstico + design mínimo)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-4-rollback-governed/spec.md` e siga como contrato.
2) Mapeie no código:
   - como o deploy é feito hoje (orchestrator/release)
   - onde o “CURRENT” é definido/atualizado
   - como o pin funciona hoje (EGE pins)
   - quais estados representam “drift ACTIVE” e como isso bloqueia execução
3) Identifique precisamente:
   - quais pontos são atômicos vs não atômicos
   - onde rollback é manual hoje
4) Produza:
   - `docs/specs/fase-2/02-4-rollback-governed/flow.md` (diagrama + passos)
   - `docs/specs/fase-2/02-4-rollback-governed/gaps.md` (gaps + decisão recomendada)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.4.2 (Implementação mínima: rollback automático)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-4-rollback-governed/spec.md` e siga como contrato.
2) Implementar rollback automático governado:
   - se deploy falhar em qualquer etapa pós-build, reverter CURRENT para a última pinned release
   - se não existir pinned release, entrar SAFE_MODE (ou falhar explicitamente, conforme decisão)
   - emitir eventos determinísticos no ledger
3) Garantir que freeze/emergency bloqueiam o procedimento (se isso já é regra do runtime).

Testes obrigatórios:
- Cenário: existe release pinada A
  - tentar deploy de release B que falha → rollback para A
  - runtime retorna ACTIVE apontando para A
- Cenário: sem pinned release
  - falha de deploy → SAFE_MODE (ou erro explícito) + eventos

Documentação:
- Atualizar `flow.md` e `gaps.md` com status final.

Restrições:
- Mudanças mínimas e com testes.
[[CLAUDE_CODE_END]]
