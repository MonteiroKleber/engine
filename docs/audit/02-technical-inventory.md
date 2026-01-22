# Inventário Técnico (para auditor/arquiteto)

Este documento descreve “o que existe” no engine e onde, com foco em rastreabilidade e verificação.

## 1) Modos de operação (produção vs dev)

- **Install mode**: `ENGINE_INSTALL_MODE=dev|prod` (baseline de segurança e preflight)
  - Implementação: `src/engine/core/install_mode.py`, `src/engine/core/preflight.py`
- **Auth mode**: `ENGINE_AUTH_MODE=dev|strict` (identidade verificada por token em `strict`)
  - Implementação: `src/engine/api/dependencies.py`, `src/engine/core/actor_context.py`, `src/engine/core/actor_tokens.py`
- **API mode**: `ENGINE_API_MODE=legacy|idl|both` (migração controlada para runtime IDL-driven)
  - Implementação: `src/engine/core/idl_router.py`, `src/engine/core/migration_check.py`, `src/engine/api/server.py`

## 2) Contratos canônicos (bundle)

O engine carrega contratos de um bundle e valida integridade por manifest + hashes.

- Loader/manifest/hashes: `src/engine/loader/load_bundle.py`, `src/engine/loader/verify_hashes.py`
- Prova offline: `src/engine/proof/verify.py` (`verify_bundle_offline`)
- Artefatos típicos do bundle:
  - `rbac.json`, `approvals.json`, `sod.json`, `workflows.json`, `invariants.json`
  - `policies.json`, `mandates.json`, `autonomy.json`
  - `contract_ledger.json`, `bundle.manifest.json`
  - `operations.json` (IDL-driven runtime)

## 3) Motores de governança (runtime gates)

Gates determinísticos chamados pelo runtime/dispatcher:

- RBAC: `src/engine/core/rbac.py`
- Policies (pre/post): `src/engine/core/policy.py`
- Mandates: `src/engine/core/mandates.py`
- Autonomy: `src/engine/core/autonomy.py`
- Approvals (request/decide): `src/engine/core/approvals.py`, API: `src/engine/api/approvals.py`
- SoD: `src/engine/core/sod.py`
- Invariants: `src/engine/core/invariants.py`

## 4) Ledger (audit trail) + integridade

- Ledger append-only com hash-chain: `src/engine/core/ledger.py`
- SAFE_MODE e triggers: `src/engine/core/safe_mode.py`
- Evento de reload governado: `src/engine/core/runtime_reload.py` (`RUNTIME_RELOADED`)

## 5) Runtime IDL-driven (contrato → operações → execução)

Este é o “core” para permitir Targets de produção consumirem uma API derivada do contrato.

- `operations.json` + registry:
  - `src/engine/core/operations.py`
  - emit: `src/engine/ise/emit/operations_emit.py`
- Dispatcher (execução determinística):
  - `src/engine/core/dispatcher.py` (create/read/approvals)
- Dynamic router (rotas FastAPI a partir do registry):
  - `src/engine/core/idl_router.py`
- OpenAPI overlay (OpenAPI alinhado ao registry):
  - `src/engine/core/openapi_overlay.py`

## 6) Multi-tenant / multi-dept

- Namespacing por instituição/dept (paths e state store): `src/engine/core/data_root.py`, `src/engine/core/state_store.py`
- Hardening contra misconfig de paths em multi-tenant: `src/engine/core/preflight.py`
- Modelo de depts ativos (ativação/desativação): `src/engine/core/active_depts.py`

## 7) EGE (evolução governada)

- Pins/proposals/drift/rollback: `src/engine/core/ege.py`, `src/engine/core/ege_pins.py`, `src/engine/core/ege_rollback.py`
- Hot-swap governado pós pin/rollback: `src/engine/core/runtime_reload.py`

## 8) Legacy Bridge (read-only + write outbox governado)

- Read-only assets/registry/drift: `src/engine/legacy_bridge/`
- Write-mode outbox (governado, sem “self-approved”): `src/engine/legacy_bridge/write_registry.py`, `src/engine/legacy_bridge/outbox_connector.py`

## 9) Console operacional do Engine

Console embutido (admin/ops), não é Target institucional:

- Rotas: `src/engine/console/routes.py`
- Templates: `src/engine/console/templates/`

