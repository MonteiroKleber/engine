# Fase 4 — Etapa 4.4: Prompts (Claude Code)

PROMPT 4.4.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-4-policies-autonomy-ui/spec.md` e siga como contrato.
2) Mapear:
   - schema/validação de `policies.json` e `autonomy.json`
   - como policies/autonomy são carregados hoje (bundle/dept)
   - como governed_mandates foi implementado (padrão)
3) Propor a abordagem mínima:
   - módulos core (governed_policies/governed_autonomy)
   - integrações no runtime
   - UI no console
4) Produzir:
   - `docs/specs/fase-4/04-4-policies-autonomy-ui/gaps.md`
   - `docs/specs/fase-4/04-4-policies-autonomy-ui/api.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.4.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Policies/autonomy governadas seguem o mesmo padrão de mandatos (proposal/decide/apply), com override > bundle.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-4-policies-autonomy-ui/spec.md` e siga como contrato.
2) Implementar core + runtime lookup + UI console para policies e autonomy governadas.
3) Adicionar testes end-to-end e de isolamento.
4) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
