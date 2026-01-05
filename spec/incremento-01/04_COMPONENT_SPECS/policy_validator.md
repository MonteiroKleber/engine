# validators/policy_validator.py — Especificação (Semana 3)

## Objetivo
Reservar o ponto de extensão para validações de política (ex.: restrições organizacionais) sem impactar o pipeline da Semana 3.

## Semana 3 (mínimo)
- Pode ser um no-op determinístico (sempre `ok: true`).
- Não deve bloquear a geração/versionamento do SRS nesta semana.

## Output sugerido
- `validate_policies(context, srs_dict) -> {ok: bool, warnings: [], errors: []}`
