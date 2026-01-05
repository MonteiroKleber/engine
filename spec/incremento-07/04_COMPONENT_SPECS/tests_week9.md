# Tests — Semana 9

## Unitário
- `tests/test_generic_blueprint.py`:
  - não altera entidades
  - não altera endpoints
  - não altera tasks
  - determinístico
  - inputs genéricos

## Sistema
- `tests/test_pipeline_forced_generic.py`:
  - pipeline completo com input genérico
  - blueprint=GENERIC
  - nenhum artefato extra
  - CRUD mínimo funcional

## Demo
- CLI com input genérico deve registrar GENERIC e passar build.
