# Prompts — Migração 01 (Diagnóstico)

## PROMPT 01.1 (Diagnóstico)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Mapear com evidências no repo:
   - onde `ENGINE_API_MODE` é lido e aplicado (`legacy`/`idl`/`both`)
   - onde rodam migration checks e quais erros são “hard fail” no boot
   - como o IDL router registra rotas a partir de `operations.json`
   - quais `bind.kind` o dispatcher suporta hoje
   - quais bundles existem e se possuem `operations.json`
2) Produzir:
   - `docs/specs/migracao/01-diagnostico/map.md` (com paths e símbolos)
   - `docs/specs/migracao/01-diagnostico/gaps.md` (gaps priorizados + próximo passo)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

