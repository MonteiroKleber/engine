# Map — Migração 03 (ACME Core → IDL mode)

## Estado final (após Migração 03)

- Bundle: `bundles/acme_core`
- Modo: single dept (`_single`)
- IDL-ready:
  - `operations.json` presente
  - `bundle.manifest.json` referencia `operations.json`
  - `contract_ledger.json` usa schema moderno (`contracts[]`) e tem `manifest_hash` coerente
  - Proof offline PASS

## Contratos do bundle (paths)

- `bundles/acme_core/operations.json`
- `bundles/acme_core/bundle.manifest.json`
- `bundles/acme_core/contract_ledger.json`
- `bundles/acme_core/rbac.json`
- `bundles/acme_core/mandates.json`
- `bundles/acme_core/autonomy.json`
- `bundles/acme_core/approvals.json`
- `bundles/acme_core/workflows.json`
- `bundles/acme_core/policies.json`
- `bundles/acme_core/sod.json`
- `bundles/acme_core/invariants.json`
- `bundles/acme_core/openapi.yaml`

## Operações migradas (IDL)

Escopo mínimo suportado pelo dispatcher atual (create + approval_decide):
- `POST /finance/expenses` → `bind.kind=create` (`entity=Expense`)
- `POST /approvals/{approval_id}/decide` → `bind.kind=approval_decide`

Nota: endpoints descritos no OpenAPI e não suportados pelo dispatcher não entram no `operations.json` nesta fase (evita migration check FAIL).

## Governança (RBAC / Mandates / Autonomy)

Semântica canônica do engine:
- `mandates.json` existe → precisa ter mandate aplicável, senão **DENY**
- `autonomy.json` existe → precisa ter rule aplicável, senão **DENY**

Portanto, a migração correta do ACME Core manteve esses contratos e adicionou regras mínimas coerentes com os endpoints IDL migrados (não “remove para fazer passar”).

## Hard gates (evidência)

Proof offline:
- `PYTHONPATH=src python3 -m engine.proof verify bundles/acme_core`

E2E STRICT (HTTP via TestClient):
- `python -m pytest tests/test_acme_core_idl_mode_e2e.py -v`

