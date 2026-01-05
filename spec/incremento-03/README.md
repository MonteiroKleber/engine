# Incremento-03 — Semana 5 (Contracts: OpenAPI + RBAC + Gates)

Este diretório contém a especificação organizada e prompts em fases para implementar a Semana 5 usando o Claude Code.

## Como usar
1) Leia `00_CONTEXT.md` (objetivo, escopo e critérios de aceite).
2) Verifique deltas e convenções em `01_REPO_LAYOUT.md`.
3) Confirme dependências/config em `02_DEPENDENCIES.md` e `03_CONFIG_SPEC.md`.
4) Implemente componente a componente usando `04_COMPONENT_SPECS/`.
5) Use os prompts prontos em `prompts/` (um por dia/fase).
6) Valide com os critérios em `05_TEST_PLAN.md`.

## Princípios
- Determinístico (sem SDK de LLM nesta semana).
- Gerar apenas CRUD (sem inventar endpoints fora de CRUD).
- Gates e policies devem bloquear contrato inconsistente ou endpoint “sem auth”.
- Versionamento e hashes no run log são obrigatórios.
