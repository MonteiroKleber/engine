# Incremento-06 — Semana 8 (Compilers reais + Fix Loop Agent)

Este diretório contém a especificação organizada e prompts em fases para implementar a Semana 8 usando o Claude Code.

## Como usar
1) Leia `00_CONTEXT.md` (objetivo, escopo e regras fixadas).
2) Verifique paths e convenções em `01_REPO_LAYOUT.md`.
3) Confirme pré‑requisitos em `02_DEPENDENCIES.md`.
4) Implemente componente a componente usando `04_COMPONENT_SPECS/`.
5) Use os prompts prontos em `prompts/` (um por dia/fase).
6) Valide com os critérios em `05_TEST_PLAN.md`.

## Princípios (fixados)
- Autonomia controlada: correções limitadas, governadas, e reproduzíveis.
- Fix Loop: no máximo 3 tentativas; 1 patch por tentativa; 1 causa por iteração.
- Nunca violar contratos, policies ou paths.
- Nunca escrever fora de `/home/bazari/generated/<project>/`.
