# Prompt — Dia 7: Integração + Demo CLI + estabilidade

Implemente as Tarefas 6.9 e 6.10 (Dia 7) da Semana 6.

1) Integração
Criar `tests/test_pipeline_to_plan.py`.

Testes obrigatórios:
- pipeline completo gera PLAN.
- versionamento incrementa.
- run log contém `plan_hash`.
- `plan_hash` bate com arquivo.

2) Demo CLI obrigatória
Rodar:
- `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`

Artefatos obrigatórios:
- `store_data/demo/PLAN/v1.json`

Critério de aceite:
- `pytest` verde.
- demo CLI gera PLAN sempre.
- plan é validado por schema + policy.
