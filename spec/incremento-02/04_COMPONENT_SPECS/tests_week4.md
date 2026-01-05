# Tests — Semana 4

## tests/test_ir_schema.py
- Carrega `schemas/ir.schema.json`.
- Valida um IR manual mínimo (válido).
- Valida IR gerado por `DomainModeler.generate_ir` a partir de um SRS gerado.

## Integração
- Atualizar `tests/test_intake_flow.py` ou criar `tests/test_pipeline_to_ir.py`.
- Verificar que a pipeline:
  - salva SRS
  - gera IR
  - valida IR (schema + policy)
  - salva IR
  - registra run log com hashes e referências
