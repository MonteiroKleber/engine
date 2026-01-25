# Map — Migração 04 (multi-pilot → IDL multi-dept)

## Estado final (após Migração 04)

- Bundle: `bundles/multi-pilot`
- Modo: multi dept
  - `departments/finance`
  - `departments/support`
- IDL-ready:
  - `departments/<dept>/operations.json` presente (ambos depts)
  - `departments/<dept>/source.idl` presente (âncora dentro do bundle)
  - `contract_ledger.json` schema moderno (`contracts[]`) + `manifest_hash` coerente
  - Proof offline PASS

## Operações por dept (escopo mínimo suportado)

Finance:
- `POST /finance/expenses` → `bind.kind=create` (`entity=Expense`)
- `POST /approvals/{approval_id}/decide` → `bind.kind=approval_decide`

Support:
- `POST /support/tickets` → `bind.kind=create` (`entity=Ticket`)
- `POST /approvals/{approval_id}/decide` → `bind.kind=approval_decide`

## Roteamento multi-dept (IDL)

Quando bundle é multi-dept, o IDL router registra as rotas prefixadas por dept:
- `/d/finance/...`
- `/d/support/...`

Exemplos:
- `POST /d/finance/finance/expenses`
- `POST /d/support/support/tickets`

## Governança por dept

Cada dept tem seus próprios contratos:
- `departments/<dept>/rbac.json`
- `departments/<dept>/mandates.json`
- `departments/<dept>/autonomy.json`

Regra canônica: se o contrato existe e não há regra aplicável para o `endpoint_sig`/phase, o gate nega.

## Hard gates (evidência)

Proof offline:
- `PYTHONPATH=src python3 -m engine.proof verify bundles/multi-pilot`

E2E STRICT (HTTP via TestClient, cobrindo finance + support):
- `python -m pytest tests/test_multi_pilot_idl_mode_e2e.py -v`

