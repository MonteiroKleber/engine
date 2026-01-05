# Prompt — Dia 4: Gates anti-invenção do Blueprint

Implemente o Dia 4 da Semana 9.

Criar:
- `/home/bazari/engine/validators/blueprint_policy_validator.py`

Regras obrigatórias:
- Blueprint falha se tentar:
  - criar entidade fora do IR
  - criar endpoint fora do OAS
  - criar task fora do PLAN
  - alterar contratos

Regra:
- Blueprint só pode consumir, nunca produzir.
