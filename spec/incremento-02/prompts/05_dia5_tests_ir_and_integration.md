# Prompt — Dia 5: Testes obrigatórios (unit + integração)

Implemente as Tarefas 4.5 e 4.6 (Dia 5) da Semana 4.

1) Criar `tests/test_ir_schema.py`
Testes obrigatórios:
- carrega `schemas/ir.schema.json`
- valida IR manual mínimo (válido)
- valida IR gerado por DomainModeler a partir de SRS gerado

2) Integração
- Atualizar `tests/test_intake_flow.py` (ou criar `tests/test_pipeline_to_ir.py`) para testar:
  - pipeline completo até IR
  - IR versiona e incrementa versão
  - run log inclui referência ao IR gerado e inclui `ir_hash`

Critério de aceite:
- `pytest` verde
- IR versionado corretamente.
