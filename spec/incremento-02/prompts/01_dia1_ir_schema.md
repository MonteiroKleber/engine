# Prompt — Dia 1: Schemas do IR (lei do domínio)

Implemente a Tarefa 4.1 (Dia 1) da Semana 4.

1) Adicionar `schemas/ir.schema.json`
- Usar **exatamente** o schema definido na Semana 2 (IR com `meta`, `domain`, `api_intent`, `ui`, `nfr`).
- Não alterar nomes de campos nem requisitos.

2) Criar teste `tests/test_ir_schema.py`
- Deve carregar `schemas/ir.schema.json` sem erro.

Regras:
- Não adicionar dependências.
- Não alterar o schema do SRS.

Critério de aceite:
- `pytest -q` passa pelo menos esse teste e o schema é carregado sem erro.
