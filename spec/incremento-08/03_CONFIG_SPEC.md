# Configuração

## CLI
Adicionar modo release na CLI:
- flag `--release` (ou equivalente) para disparar o fluxo “texto → rodando”.

## Premissas
- Em modo release, o engine executa docker compose + smoke tests.
- Em falha, deve executar teardown (`docker compose down`) e rollback.
