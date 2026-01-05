# validators/blueprint_policy_validator.py — Gate anti-invenção

## Objetivo
Bloquear qualquer tentativa de blueprint “produzir” ou alterar contratos.

## Regras obrigatórias
Falhar se blueprint tentar:
- criar entidade fora do IR
- criar endpoint fora do OAS
- criar task fora do PLAN
- alterar contratos

## Interpretação operacional
Comparar before/after (inputs vs outputs):
- `IR`: entidades não podem aumentar
- `OAS`: endpoints/operations não podem aumentar
- `PLAN`: tasks não podem aumentar
- contratos não podem ser modificados

## Critério de aceite (Dia 4)
- Qualquer expansão/alteração indevida → FAIL.
