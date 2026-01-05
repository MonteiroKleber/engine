# fix_loop/error_classifier.py — Build Error Taxonomy

## Objetivo
Classificar erros de build em uma taxonomia fechada (sem texto livre) para acionar correções governadas.

## API
- `class BuildErrorClassifier:`
  - entrada: `stderr`, `stdout`, `exit_code`, `step` (`backend` | `frontend`)
  - saída: `error_class` (enum)

## Enum (fechado)
- `JAVA_MISSING_IMPORT`
- `JAVA_METHOD_NOT_IMPLEMENTED`
- `JAVA_TYPE_MISMATCH`
- `JAVA_SECURITY_CONFIG_ERROR`
- `SQL_MIGRATION_ERROR`
- `TS_TYPE_ERROR`
- `TS_MISSING_EXPORT`
- `API_CLIENT_MISMATCH`
- `UNKNOWN_BUT_PATCHABLE`
- `FATAL_UNCLASSIFIED`

## Regras
- Nada de texto livre como categoria.
- Erros desconhecidos devem cair em `UNKNOWN_BUT_PATCHABLE` ou `FATAL_UNCLASSIFIED`.

## Critério de aceite (Dia 1)
- Strings conhecidas → classe correta.
- Desconhecido → UNKNOWN_BUT_PATCHABLE ou FATAL_UNCLASSIFIED.
