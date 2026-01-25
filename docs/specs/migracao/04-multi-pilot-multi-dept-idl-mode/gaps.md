# Gaps — Migração 04 (multi-pilot → IDL multi-dept)

## Resolvido

### GAP-04.1 — Ledger schema legado (`entries[]`)
- **Antes:** `bundles/multi-pilot/contract_ledger.json` em schema antigo quebrava Proof offline.
- **Depois:** convertido para schema atual (`contracts[]`) e `manifest_hash` coerente.

### GAP-04.2 — `operations.json` ausente por dept
- **Depois:** criados:
  - `bundles/multi-pilot/departments/finance/operations.json`
  - `bundles/multi-pilot/departments/support/operations.json`

### GAP-04.3 — Support dept não tinha governança para approval.decide
- **Depois:** support recebeu ajustes mínimos:
  - RBAC: permission `approval.decide` para role que decide
  - Mandate/autonomy: regras aplicáveis para `POST /approvals/{approval_id}/decide`

### GAP-04.4 — Âncora de IDL dentro do bundle (source)
- **Depois:** seeds dentro do bundle:
  - `departments/finance/source.idl`
  - `departments/support/source.idl`
  - `source_idl_sha256` agregado no `contract_ledger.json` (não placeholder).

## Ainda aberto (decisão de produto / expansão)

### GAP-04.A — Endpoints de leitura (support) ainda não migrados
- Exemplo típico: `GET /support/tickets/{ticket_id}` pode continuar como legacy-only dependendo do escopo do `operations.json`.
- Isso afeta cutover (Migração 07): o modo `both` serve para medir e planejar remoção do legacy com base em telemetria.

