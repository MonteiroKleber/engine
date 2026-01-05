# Plano de testes (Semana 9)

## Unitários
- `tests/test_generic_blueprint.py`
  - blueprint não altera entidades/endpoints/tasks
  - blueprint é determinístico
  - funciona com inputs genéricos

## Sistema (integração)
- `tests/test_pipeline_forced_generic.py`
  - input genérico: "Quero um sistema simples de cadastro"
  - pipeline completo roda
  - `blueprint == GENERIC`
  - nenhum artefato extra criado
  - CRUD mínimo funcional

## Demo
- `python main.py --project demo --input "Quero um sistema simples de cadastro"`
  - blueprint registrado como GENERIC
  - sistema gerado corretamente
  - nenhum elemento inventado
  - build passa
