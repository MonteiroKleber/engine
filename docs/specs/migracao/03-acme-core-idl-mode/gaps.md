# Gaps — Migração 03 (ACME Core → IDL mode)

## Resolvido (para IDL bootável + STRICT)

### GAP-03.1 — `operations.json` ausente
- **Antes:** bundle não tinha registry de operações.
- **Depois:** `bundles/acme_core/operations.json` criado (escopo mínimo suportado).

### GAP-03.2 — Manifest/Ledger sem referência/sha corretos
- **Antes:** integridade podia ser incoerente se `operations.json` fosse adicionado sem atualizar hashes.
- **Depois:** `bundles/acme_core/bundle.manifest.json` e `bundles/acme_core/contract_ledger.json` incluem `operations.json` com `sha256`/`content_hash` e `manifest_hash` coerentes.

### GAP-03.3 — Mandates/Autonomy “deny-all” por listas vazias
- **Antes:** contratos existiam com listas vazias → comportamento efetivo de DENY.
- **Depois:** `bundles/acme_core/mandates.json` e `bundles/acme_core/autonomy.json` possuem regras mínimas aplicáveis para os endpoint_sig migrados.

### GAP-03.4 — E2E STRICT ausente
- **Depois:** `tests/test_acme_core_idl_mode_e2e.py` prova fluxo via HTTP em `ENGINE_API_MODE=idl` + `ENGINE_AUTH_MODE=strict`.

## Ainda aberto (decisão de escopo)

### GAP-03.A — Cobertura parcial do OpenAPI do ACME Core
- Endpoints descritos no `bundles/acme_core/openapi.yaml` que não estão em `operations.json` permanecem fora do IDL (por limitações atuais do dispatcher).
- Estratégias:
  1) migrar gradualmente (expandir dispatcher por fases),
  2) manter legacy em `ENGINE_API_MODE=both` até o cutover (Migração 07).

