# Incremento-07 — Semana 9 (Blueprint Genérico: FORCED_GENERIC)

Este diretório contém a especificação organizada e prompts em fases para implementar a Semana 9 usando o Claude Code.

## Como usar
1) Leia `00_CONTEXT.md` (objetivo, escopo e anti-invenção).
2) Verifique paths e integração em `01_REPO_LAYOUT.md`.
3) Confirme pré‑requisitos em `02_DEPENDENCIES.md`.
4) Implemente componente a componente usando `04_COMPONENT_SPECS/`.
5) Use os prompts prontos em `prompts/` (um por dia/fase).
6) Valide com os critérios em `05_TEST_PLAN.md`.

## Princípios (fixados)
- Blueprint é atalho controlado, nunca criatividade.
- O motor deve funcionar sem blueprint específico.
- Blueprint só consome SRS/IR/OAS/RBAC/PLAN; não produz nem altera contratos.
- Fallback seguro e determinístico: FORCED_GENERIC.
