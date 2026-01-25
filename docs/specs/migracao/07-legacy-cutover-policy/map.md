# Map — Migração 07 (Legacy Cutover Policy)

## Onde os routers legacy entram (FastAPI app)

Arquivo:
- `src/engine/api/server.py`

Comportamento:
- Em `ENGINE_API_MODE=idl`: legacy routers **não** são incluídos.
- Em `ENGINE_API_MODE=legacy` ou `both`: legacy routers são incluídos.

Routers legacy principais:
- Finance legacy (`/finance/*`)
- Support legacy (`/support/*`)
- Dept finance legacy (`/d/{dept}/finance/*`)
- Dept support legacy (`/d/{dept}/support/*`)
- Approvals legacy (`/approvals/*`)

## Telemetria determinística de legacy (both mode)

Arquivo:
- `src/engine/core/legacy_telemetry.py`

Hooks (chamados nos handlers legacy):
- `src/engine/api/finance.py`
- `src/engine/api/dept_finance.py`
- `src/engine/api/support.py`
- `src/engine/api/dept_support.py`
- `src/engine/api/approvals.py`

Regra: a telemetria só grava quando `ENGINE_API_MODE=both` (não grava em `idl` nem em `legacy`).

Persistência (por instituição):
- `<institution_root>/legacy_telemetry.jsonl`

## Console (read-only)

O console expõe a seção “Legacy Cutover Telemetry/Status” (somente leitura) para visualizar contagem por endpoint_sig e último uso.

Arquivos:
- `src/engine/console/routes.py`
- `src/engine/console/templates/status.html`

## Hard gate

- `python -m pytest tests/test_legacy_cutover.py -v`

