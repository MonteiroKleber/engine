# Plano de testes (Semana 7)

## Unitários
- `tests/test_patch_rules.py`
  - valida bloqueios: engine/templates, traversal, rewrite >80%

- `tests/test_patch_apply_rollback.py`
  - aplica patches válidos
  - patch inválido → rollback imediato

## Integração
- `tests/test_pipeline_to_repo_build.py`
  - cria repo em `/home/bazari/generated/<project>`
  - gera patches
  - aplica patches
  - roda build validator
  - falha → rollback, sucesso → build_ok=true

## Critério final
- `pytest` verde.
- Demo CLI gera `/home/bazari/generated/demo` com backend/frontend compilando.
