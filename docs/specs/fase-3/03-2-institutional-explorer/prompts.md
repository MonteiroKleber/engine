# Fase 3 — Etapa 3.2: Prompts (Claude Code)

PROMPT 3.2.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-2-institutional-explorer/spec.md` e siga como contrato.
2) Mapear no código:
   - como obter o bundle ativo/pinned por `institution_id`/`dept_id`
   - como o console atual obtém status e dados (rotas e dependências)
   - como chamar `engine.proof.verify_bundle_offline()` sem iniciar runtime
3) Produzir:
   - `docs/specs/fase-3/03-2-institutional-explorer/api.md` (read model pro console)
   - `docs/specs/fase-3/03-2-institutional-explorer/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.2.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Manter console estritamente read-only.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-2-institutional-explorer/spec.md` e siga como contrato.
2) Implementar rotas e templates do explorer:
   - listagem de contracts (manifest)
   - visualização de `bundle.manifest.json` e `contract_ledger.json`
   - visualização de um contract específico (somente dentro do bundle)
   - página de proof: rodar verify offline e mostrar resultado (e JSON opcional)
3) Adicionar testes para:
   - auth
   - path traversal
   - hash match vs manifest
   - proof PASS para bundle válido

Documentação:
- Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
