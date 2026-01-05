# Plano de testes (obrigatório)

## tests/test_srs_schema.py
- Carregar `schemas/srs.schema.json`.
- Gerar um SRS via `req_analyst` (ou via engine) e validar com `jsonschema`.
- Esperado: válido.

## tests/test_intake_flow.py
- Rodar engine (ou CLI) com input simples.
- Confirmar que:
  - gerou SRS
  - versionou em `store_data/<project>/SRS/v1.json`
  - criou run log

## Critério final
- `pytest` verde.
- Execução manual do CLI conforme `00_CONTEXT.md`.
