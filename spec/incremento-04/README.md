# Incremento-04 — Semana 6 (Planner Agent + plan.json + Gates)

Este diretório contém a especificação organizada e prompts em fases para implementar a Semana 6 usando o Claude Code.

## Como usar
1) Leia `00_CONTEXT.md` (objetivo, escopo e critérios de aceite).
2) Verifique deltas e convenções em `01_REPO_LAYOUT.md`.
3) Confirme dependências/config em `02_DEPENDENCIES.md` e `03_CONFIG_SPEC.md`.
4) Implemente componente a componente usando `04_COMPONENT_SPECS/`.
5) Use os prompts prontos em `prompts/` (um por dia/fase).
6) Valide com os critérios em `05_TEST_PLAN.md`.

## Princípios
- Determinístico (sem SDK de LLM nesta semana).
- O Planner só gera o `PLAN` (não implementa código).
- Gates (schema + rules + policy) devem bloquear plano inconsistente.
- Versionamento e `plan_hash` no run log são obrigatórios.
