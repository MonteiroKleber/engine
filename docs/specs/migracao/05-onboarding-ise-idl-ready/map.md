# Map — Migração 05 (Onboarding + ISE IDL-ready)

## Objetivo operacional

Em `ENGINE_API_MODE=idl`, o engine não pode:
- instalar/botar com bundle “meio válido” (sem operations registry)
- produzir bundles sem âncora de decisão (`source_idl_sha256`)

## Pipeline 1 — Onboarding (console) → bundle a partir de template

Arquivos chave:
- `src/engine/console/bundle_generator.py`

Pontos relevantes do fluxo:
- Copia template do repo para o `ENGINE_DATA_ROOT`.
- Em `ENGINE_API_MODE=idl`, valida que o bundle gerado é “IDL-ready”:
  - single: `operations.json` no root do bundle
  - multi: `departments/<dept>/operations.json` para cada dept
- Em falha: erro determinístico (`MIGRATION_MISSING_OPERATIONS`) e cleanup do bundle parcial.

## Pipeline 2 — ISE (compiler) → bundle a partir de IRCS

Arquivos chave:
- `src/engine/ise/compiler.py`
- `src/engine/ise/ircs_adapter.py` (campo canônico: `source_idl_sha256`)

Regras aplicadas:
- Se o IRCS não tiver `source_idl_sha256`, a compilação falha determinísticamente e **não escreve** bundle incompleto.

## Testes (evidência)

- `tests/test_onboarding_idl_ready.py`
  - positivos em `ENGINE_API_MODE=idl` (finance-pilot e multi-pilot)
  - negativo: template sem `operations.json` falha com `MIGRATION_MISSING_OPERATIONS`
- `tests/test_ise_idl_ready.py`
  - negativo: IRCS sem `source_idl_sha256` falha com `ISE_SOURCE_IDL_SHA256_MISSING`
  - positivo: IRCS com `source_idl_sha256` gera ledger contendo a âncora

