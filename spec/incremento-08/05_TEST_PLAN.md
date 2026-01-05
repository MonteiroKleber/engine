# Plano de testes (Semana 10)

## Unitários
- QA/Release Agent gera relatório estruturado mesmo com repo mínimo.
- Release checklist falha quando itens obrigatórios faltam.

## Integração (release mode)
- Pipeline `--release`:
  - gera repo
  - aplica patches
  - build ok
  - `docker compose up -d`
  - smoke PASS/FAIL
  - falha → `docker compose down` + rollback

## Critério final
- `pytest` verde.
- Demo `--release` sobe 3 serviços e smoke PASS.
