# Incremento-05 — Semana 7 (Templates + Patch Engine + Rollback + Build)

Este diretório contém a especificação organizada e prompts em fases para implementar a Semana 7 usando o Claude Code.

## Como usar
1) Leia `00_CONTEXT.md` (objetivo, escopo e regras fixadas).
2) Verifique paths e convenções em `01_REPO_LAYOUT.md`.
3) Confirme pré‑requisitos e validação em `02_DEPENDENCIES.md`.
4) Implemente componente a componente usando `04_COMPONENT_SPECS/`.
5) Use os prompts prontos em `prompts/` (um por dia/fase).
6) Valide com os critérios em `05_TEST_PLAN.md`.

## Princípios (fixados)
- O motor nunca se auto‑modifica (`/home/bazari/engine/**` é read‑only para o Patch Engine).
- Templates nunca são alterados (`/home/bazari/templates/**` é read‑only para o Patch Engine).
- Tudo gerado vai para `/home/bazari/generated/<project>/**`.
- Patches são aplicados com rollback e regras de segurança (path traversal, limites de rewrite).
