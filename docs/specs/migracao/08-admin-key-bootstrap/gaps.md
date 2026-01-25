# Gaps — Migração 08 (Admin Key Bootstrap)

## Resolvido

### GAP-08.1 — Sem bootstrap por instituição via HTTP
- **Antes:** recém-criado não conseguia gerar `X-Admin-Key`, bloqueando o provisioning de tokens e a operação em STRICT.
- **Depois:** bootstrap one-time via `X-Admin-Token` no endpoint de admin keys quando não há keys ainda.

### GAP-08.2 — Risco de regressão do DEFAULT institution
- **Mitigação:** comportamento do DEFAULT foi preservado; testes cobrem que o token legacy continua funcionando conforme compat.

## Ainda aberto (melhorias)

- Adicionar mecanismos opcionais de “bootstrap window” (tempo) ou “bootstrap disabled” por config (decisão de produto).

