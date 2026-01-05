# Incremento-08 — Semana 10 (Release Final: congelamento v1.0)

Este diretório contém a especificação organizada e prompts em fases para implementar a Semana 10 usando o Claude Code.

## Como usar
1) Leia `00_CONTEXT.md` (objetivo, escopo e gates finais).
2) Verifique paths e integração em `01_REPO_LAYOUT.md`.
3) Confirme pré‑requisitos em `02_DEPENDENCIES.md`.
4) Implemente componente a componente usando `04_COMPONENT_SPECS/`.
5) Use os prompts prontos em `prompts/` (um por dia/fase).
6) Valide com os critérios em `05_TEST_PLAN.md`.

## Princípios (fixados)
- “Texto → sistema rodando” via `docker compose up -d`.
- QA/Release Agent executa smoke + checklist e produz bundle/relatórios.
- Gates finais: qualquer item faltando → FAIL.
- Congelamento v1.0: schemas/policies/templates governados por versão.
