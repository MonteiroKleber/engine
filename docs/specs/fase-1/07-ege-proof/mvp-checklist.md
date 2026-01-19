# MVP Checklist - Fase 1 Libervia Engine

**Data:** 2026-01-18
**Versao:** 1.1
**Etapa:** 07 — Checklist Final do MVP

---

## Legenda

- ✅ Implementado e testado
- ⚠️ Parcialmente implementado ou com ressalvas
- ❌ Nao implementado ou bloqueador

---

## 1. Bundle e Contratos

| Item | Status | Evidencia |
|------|--------|-----------|
| `bundle.manifest.json` com SHA256 de cada contrato | ✅ | [bundle.manifest.json](../../../../bundles/finance-pilot/bundle.manifest.json) |
| Contratos institucionais obrigatorios (`required: true`) | ✅ | policies.json, mandates.json, autonomy.json |
| Verificacao de hash na carga do bundle | ✅ | [load_bundle.py](../../../../src/engine/loader/load_bundle.py) `_verify_contracts()` |
| SAFE_MODE em bundle invalido | ✅ | [safe_mode.py](../../../../src/engine/loader/safe_mode.py), Testes: test_loader_safe_mode.py |

---

## 2. EGE - Engine Governance Enforcement

### 2.1 Drift Detection e Enforcement

| Item | Status | Evidencia |
|------|--------|-----------|
| Deteccao de drift (pinned vs observed) | ✅ | [ege.py:170](../../../../src/engine/core/ege.py) `check_drift()` |
| Estado de drift persistido (ege_drift_state.json) | ✅ | [ege.py:122](../../../../src/engine/core/ege.py) `save_drift_state()` |
| Bloqueio de mutacoes quando drift ACTIVE | ✅ | [server.py:541-616](../../../../src/engine/api/server.py) `ege_drift_middleware()` |
| Evento EGE_DRIFT_BLOCKED no ledger | ✅ | server.py:599-615 |
| Flag `ege_enforce_drift` na config | ✅ | [institution_config.py](../../../../src/engine/core/institution_config.py) |
| API `/admin/ege/drift/check` | ✅ | [admin_ege.py](../../../../src/engine/api/admin_ege.py) |
| Testes de middleware de drift | ✅ | test_ege_drift_middleware_block.py (77 testes) |

### 2.2 Pin apos Deploy

| Item | Status | Evidencia |
|------|--------|-----------|
| Criacao de proposta PIN_UPDATE | ✅ | [ege_pins.py:236](../../../../src/engine/core/ege_pins.py) `create_pin_update_proposal()` |
| Auto-propose apos deploy | ✅ | [orchestrator.py:426-450](../../../../src/engine/pipeline/orchestrator.py) |
| Aceitacao de proposta (atualiza config) | ✅ | [ege_pins.py:441](../../../../src/engine/core/ege_pins.py) `accept_pin_update_proposal()` |
| Bloqueio de proposta | ✅ | [ege_pins.py:554](../../../../src/engine/core/ege_pins.py) `block_pin_update_proposal()` |
| Flag `auto_propose_pin_on_deploy` | ✅ | institution_config.py |
| Flag `auto_accept_pin_on_deploy` | ✅ | institution_config.py |
| Testes de pins | ✅ | test_ege_pins.py |

### 2.3 Rollback

| Item | Status | Evidencia |
|------|--------|-----------|
| Rollback automatico em falha de deploy | ⚠️ | orchestrator.py retorna FAILED/ROLLED_BACK, mas rollback e via symlink manual |
| Funcao explícita de rollback | ⚠️ | Nao existe `rollback()` dedicado - operador reverte CURRENT symlink manualmente |
| Bloqueio via proposta de pin | ✅ | `block_pin_update_proposal()` mantem drift ACTIVE |

**Nota:** Rollback e "soft" - bloqueia mutacoes via drift mas nao reverte automaticamente o bundle.

---

## 3. SAFE_MODE

| Item | Status | Evidencia |
|------|--------|-----------|
| Trigger: Bundle invalido | ✅ | load_bundle.py entra em SAFE_MODE via `enter_safe_mode()` |
| Trigger: Ledger corrompido | ✅ | [server.py:157-165](../../../../src/engine/api/server.py) verifica ledger no boot |
| Trigger: Schema invalido | ✅ | MandateSchemaError, AutonomySchemaError entram em SAFE_MODE |
| Deploy bloqueado em SAFE_MODE | ✅ | [orchestrator.py:177-193](../../../../src/engine/pipeline/orchestrator.py) |
| Evento SAFE_MODE_ENTERED no ledger | ✅ | safe_mode.py:19-33 |
| Testes SAFE_MODE | ✅ | test_pipeline_deploy_blocked_safe_mode.py (40 testes) |

---

## 4. Prova Offline

### 4.1 Artefatos

| Artefato | Status | Evidencia |
|----------|--------|-----------|
| `bundle.manifest.json` com hashes verificaveis | ✅ | Formato implementado |
| `contract_ledger.json` com schema completo | ✅ | [contract_ledger.json](../../../../bundles/finance-pilot/contract_ledger.json) - GAP 1 RESOLVIDO |
| `audit_ledger.jsonl` append-only | ✅ | [ledger.py](../../../../src/engine/core/ledger.py) |
| `trace.json` para builds | ✅ | [orchestrator.py:726-745](../../../../src/engine/pipeline/orchestrator.py) |
| `trace.json` para deploys | ✅ | [orchestrator.py:148-220](../../../../src/engine/pipeline/orchestrator.py) `_write_deploy_trace()` - GAP 2 RESOLVIDO |

### 4.2 Verificabilidade

| Item | Status | Evidencia |
|------|--------|-----------|
| Reconstruir decisoes via ledger | ✅ | Eventos com payload, actor, timestamp |
| Identificar regras via bundle | ✅ | Hashes no manifest, contratos verificaveis |
| Identificar versao institucional | ✅ | bundle_manifest_sha256 em cada evento |
| Documentacao para auditor | ✅ | [proof-offline.md](proof-offline.md) |

---

## 5. Multi-Instituicao (Etapa 06)

| Item | Status | Evidencia |
|------|--------|-----------|
| Isolamento de dados por institution | ✅ | test_cross_tenant_isolation.py (12 testes) |
| Admin keys por institution | ✅ | test_admin_keys_registry.py |
| Ledger namespaced | ✅ | test_storage_namespacing_ledger.py |
| State store namespaced | ✅ | test_cross_tenant_isolation.py |
| Anti-inference (404, nao 403) | ✅ | test_cross_tenant_isolation.py:test_expense_not_found_returns_404_not_403 |

---

## 6. Runtime Gates (Etapa 04)

| Item | Status | Evidencia |
|------|--------|-----------|
| RBAC enforcement | ✅ | test_rbac.py |
| Mandate enforcement (deny-by-default) | ✅ | test_etapa04_runtime_gates.py |
| Autonomy enforcement (deny-by-default) | ✅ | test_etapa04_runtime_gates.py |
| Policy enforcement | ✅ | test_policy_engine.py |
| SoD enforcement | ✅ | test_sod.py |
| Approvals workflow | ✅ | test_approvals.py |

---

## 7. GAPs Resolvidos

### GAP 1: contract_ledger.json ✅ RESOLVIDO

**Arquivo:** `bundles/finance-pilot/contract_ledger.json`

**Antes (placeholder):**
```json
{
  "version": "1.0.0",
  "name": "contract_ledger",
  "description": "Ledger contract for finance-pilot bundle",
  "entries": []
}
```

**Agora (schema completo):**
```json
{
  "ledger_version": "1.0",
  "ledger_id": "fp-manual-v1.0.0",
  "bundle_name": "finance-pilot",
  "bundle_version": "1.0.0",
  "manifest_hash": "SHA256:8f6bfd93e82619bbf94a5c213a0f7cb811f78613347ba1f2f3ace5d56e1d1ae6",
  "idl_hash": "SHA256:abe451b82e81612a3de8b4bb00c15b7311676326bf6f715ccb486a58193ffecb",
  "created_at": "2025-01-18T00:00:00+00:00",
  "contracts": [
    {"contract_name": "approvals.json", "content_hash": "SHA256:...", "status": "active"},
    {"contract_name": "autonomy.json", "content_hash": "SHA256:...", "status": "active"},
    ...
  ],
  "audit_trail": [{"event": "bundle_compiled", ...}]
}
```

**SHA256 no manifest atualizado:** `SHA256:722a5886da640be9afd68d138d67ba3cbca4ad7538befa7f883701672081b8aa`

---

### GAP 2: trace.json para Deploys ✅ RESOLVIDO

**Implementacao:** `_write_deploy_trace()` em [orchestrator.py:148-220](../../../../src/engine/pipeline/orchestrator.py)

**Funcionalidade:**
- Cria diretorio `deploy-traces/<release_id>/`
- Grava `trace.json` com:
  - `trace_version`, `operation`, `release_id`
  - `bundle_name`, `bundle_hash`
  - `sir_sha256`, `draft_sha256`, `final_idl_sha256`
  - `deployed_at` (UTC ISO8601)
  - `institution_id`

**Chamado:** Apos deploy bem-sucedido em `run_pipeline()` (Step 11)

---

## 8. Resumo

| Categoria | Total | ✅ | ⚠️ | ❌ |
|-----------|-------|-----|-----|-----|
| Bundle e Contratos | 4 | 4 | 0 | 0 |
| EGE Drift | 7 | 7 | 0 | 0 |
| EGE Pin | 7 | 7 | 0 | 0 |
| Rollback | 3 | 1 | 2 | 0 |
| SAFE_MODE | 6 | 6 | 0 | 0 |
| Prova Offline | 9 | 9 | 0 | 0 |
| Multi-Instituicao | 5 | 5 | 0 | 0 |
| Runtime Gates | 6 | 6 | 0 | 0 |
| **TOTAL** | **47** | **45** | **2** | **0** |

---

## 9. Definition of Done (Etapa 07)

| Criterio | Status |
|----------|--------|
| Checklist final do MVP preenchida com evidencias | ✅ Este documento |
| Prova offline demonstravel com artefatos minimos | ✅ Todos artefatos implementados |
| GAP 1 resolvido (contract_ledger.json) | ✅ |
| GAP 2 resolvido (trace.json para deploys) | ✅ |
| Testes EGE/drift/pin/safe_mode passando | ✅ 117 testes (77 EGE + 40 safe_mode) |

---

## 10. Ressalvas Conhecidas (Nao Bloqueadores)

1. **Rollback manual:** Rollback automatico nao reverte bundle fisicamente - operador reverte CURRENT symlink manualmente. Bloqueio de mutacoes via drift ACTIVE e suficiente para MVP.

2. **idl_hash no contract_ledger:** Para bundle manual (finance-pilot), `idl_hash` e marcador (`manual-bundle-no-idl-source`) pois nao ha IDL fonte. Bundles compilados pelo ISE terao hash real.

---

**Status:** MVP COMPLETO ✅
**Data:** 2026-01-18
**Versao:** 1.1 (GAPs resolvidos)
