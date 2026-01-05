# Plano de testes (Semana 4)

## tests/test_ir_schema.py (novo)
- Carregar `schemas/ir.schema.json`.
- Validar um IR manual mínimo (válido).
- Validar um IR gerado pelo DomainModeler a partir de um SRS gerado.

## Integração (atualizar test existente ou criar novo)
Atualizar `tests/test_intake_flow.py` (ou criar `tests/test_pipeline_to_ir.py`) para:
- rodar pipeline completo até IR
- confirmar persistência/versionamento do IR (`IR/v1.json`, depois `IR/v2.json` em segunda execução)
- confirmar que o run log referencia o IR gerado (path/version) e inclui `ir_hash`

## Critério final
- `pytest` verde.
