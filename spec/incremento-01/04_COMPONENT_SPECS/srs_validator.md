# validators/srs_validator.py — Especificação

## Objetivo
Validar um SRS contra `schemas/srs.schema.json` usando `jsonschema`.

## API esperada
- `validate_srs(srs_dict) -> report`

## Report estruturado
- `ok: bool`
- `errors: []` (mensagens legíveis)
- `missing_fields: []` (lista de campos esperados ausentes, quando detectável)

## Question Generator (gate)
Se `ok == false`:
- gerar até `intake.max_questions_per_round` perguntas curtas
- exemplos:
  - "Quais perfis de usuário existem?"
  - "Precisa login?"
  - "Quais entidades principais o sistema gerencia?"

## Gate
- inválido: bloquear persistência/versionamento.
- válido: permitir `save_artifact`.
