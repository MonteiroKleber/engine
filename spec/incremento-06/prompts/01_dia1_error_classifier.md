# Prompt — Dia 1: Classificador de Erros de Build (Build Error Taxonomy)

Implemente o Dia 1 da Semana 8.

Criar:
- `/home/bazari/engine/fix_loop/error_classifier.py`

Implementar `BuildErrorClassifier` que recebe:
- `stderr`, `stdout`, `exit_code`, `step` (backend/frontend)

E classifica em tipos fechados (enum):
- JAVA_MISSING_IMPORT
- JAVA_METHOD_NOT_IMPLEMENTED
- JAVA_TYPE_MISMATCH
- JAVA_SECURITY_CONFIG_ERROR
- SQL_MIGRATION_ERROR
- TS_TYPE_ERROR
- TS_MISSING_EXPORT
- API_CLIENT_MISMATCH
- UNKNOWN_BUT_PATCHABLE
- FATAL_UNCLASSIFIED

Regras:
- Nada de texto livre. Classificação fechada.

Critério de aceite:
- Strings conhecidas → classe correta.
- Desconhecido → UNKNOWN_BUT_PATCHABLE ou FATAL_UNCLASSIFIED.
