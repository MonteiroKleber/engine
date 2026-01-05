# Estrutura do repositório e convenções (Semana 4)

## Delta de estrutura (em relação à Semana 3)
Adicionar/atualizar no repo `/home/bazari/engine`:
- Adicionar pasta `agents/` com `agents/domain_modeler.py`.
- Adicionar `schemas/ir.schema.json`.
- Adicionar `validators/ir_validator.py`.
- Adicionar `tests/test_ir_schema.py`.
- Atualizar `validators/policy_validator.py` para policy do IR.
- Atualizar `store/artifacts_store.py` para suportar `kind=IR`.
- Atualizar `orchestrator/engine.py` para conectar geração/validação/persistência do IR.

## Artifact Store (layout fixo)
Raiz: `store_root` (default `./store_data`).

Layout:
- `store_data/`
  - `{project_name}/`
    - `SRS/`
      - `v1.json`
    - `IR/`
      - `v1.json`
    - `logs/`
    - `runs/`
      - `{execution_id}.json`

## Run log (contrato recomendado)
Arquivo: `{store_root}/{project}/runs/{execution_id}.json`

Campos mínimos recomendados:
- `execution_id` (string)
- `project` (string)
- `input_hash` (sha256 hex do input normalizado)
- `srs_hash` (sha256 hex do JSON canonicalizado do SRS)
- `ir_hash` (sha256 hex do JSON canonicalizado do IR)
- `artifacts.srs.path` e `artifacts.srs.version`
- `artifacts.ir.path` e `artifacts.ir.version` (quando válido)
- `validation.srs.ok`, `validation.ir.ok`, `policy.ok`

## Canonicalização para hash (para reprodutibilidade)
- Serializar JSON com `sort_keys=True`, `ensure_ascii=False`, sem espaços supérfluos.
- Hash: `sha256(serialized_bytes_utf8)`.
