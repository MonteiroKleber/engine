# Prompt — Dia 5: SRS Validator Gate + Question Generator

Implemente `validators/srs_validator.py`:
- validar contra `schemas/srs.schema.json` com `jsonschema`
- retornar relatório estruturado: ok: bool, errors[], missing_fields[]

Question Generator:
- se inválido: gerar até `intake.max_questions_per_round` perguntas curtas

Gate:
- inválido → bloqueia pipeline e retorna perguntas
- válido → permite versionar SRS

Aceite:
- inválido bloqueia e gera perguntas
- válido segue.
