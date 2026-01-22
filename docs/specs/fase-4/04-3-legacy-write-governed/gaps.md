# 04-3 Legacy Bridge Write-Mode (Governado) - Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Resumo

Legacy Bridge evoluído de read-only para write-mode governado com Outbox File Connector.

## Estado Final

### 1. Legacy Bridge Write-Mode

**Módulo:** `engine.legacy_bridge`

**Estrutura atualizada:**
```
src/engine/legacy_bridge/
├── __init__.py              # Exports (read + write)
├── __main__.py              # CLI entry point
├── models.py                # LegacyAsset, LegacyAssetSnapshot, enums
├── write_models.py          # LegacyWriteAction, ActionStatus, ACTION_SCHEMAS
├── registry.py              # LegacyBridgeRegistry (read CRUD + ledger)
├── write_registry.py        # LegacyWriteRegistry (write governado)
├── verify.py                # Verificação de drift
└── connectors/
    ├── file_connector.py    # Read-only file connector
    └── outbox_connector.py  # Write outbox connector
```

**Endpoints Console:**
| Rota | Método | Descrição | Status |
|------|--------|-----------|--------|
| `/console/legacy` | GET | Lista assets de instituição | ✅ Existe |
| `/console/legacy/{asset_id}` | GET | Detalhes do asset | ✅ Existe |
| `/console/legacy/{asset_id}/verify` | POST | Verifica drift (read-only) | ✅ Existe |
| `/console/bridge/write/{action}` | POST | Write governado | ✅ Implementado |
| `/console/bridge/write/actions` | GET | Lista write actions | ✅ Implementado |
| `/console/bridge/write/actions/{id}` | GET | Detalhes da action | ✅ Implementado |
| `/console/bridge/write/schemas` | GET | Action schemas disponíveis | ✅ Implementado |

**Eventos de Ledger:**
- `LEGACY_ASSET_REGISTERED` (read)
- `LEGACY_ASSET_VERIFIED` (read)
- `LEGACY_DRIFT_DETECTED` (read)
- `LEGACY_ASSET_MISSING` (read)
- `LEGACY_ASSET_ARCHIVED` (read)
- `LEGACY_WRITE_INTENT_CREATED` ✅ Novo
- `LEGACY_WRITE_ALLOWED` ✅ Novo
- `LEGACY_WRITE_DENIED` ✅ Novo
- `LEGACY_WRITE_ENQUEUED` ✅ Novo
- `LEGACY_WRITE_ACKED` (opcional, definido)

**Storage por Instituição:**
```
var/institutions/{uuid}/legacy_bridge/
├── assets_registry.jsonl    # Registro de assets (read)
├── snapshots.jsonl          # Histórico de verificações (read)
├── state.json               # Cache de estado (read)
├── actions_registry.jsonl   # Registro de write actions
├── write_state.json         # Cache de estado (write)
└── outbox/
    └── {action_id}.json     # Arquivos de comando (outbox)

var/institutions/{uuid}/depts/{dept_id}/legacy_bridge/
└── (mesma estrutura)        # Isolamento por departamento
```

---

## Gaps Fechados

### GAP-1: Endpoint governado para write ✅

**Implementado em:** `console/routes.py` (linhas 1120-1303)

```python
@router.post("/bridge/write/{action}")
async def console_bridge_write(
    request: Request,
    action: str,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    params: str = Form(...),  # JSON string
    ...
) -> JSONResponse:
```

---

### GAP-2: Outbox File Connector ✅

**Implementado em:** `legacy_bridge/connectors/outbox_connector.py`

```python
class OutboxConnector:
    def write_action(self, action: LegacyWriteAction) -> OutboxWriteResult
    def action_exists(self, action_id: str) -> bool
    def read_action(self, action_id: str) -> Optional[LegacyWriteAction]
    def list_actions(self) -> list
```

**Formato determinístico do outbox:**
```json
{"action_id":"uuid","action_type":"increase_limit","approved_by":null,"case_id":"uuid","created_at":"2026-01-19T10:30:00Z","intent_sha256":"abc...","mandate_id":"mandate-uuid","params":{"customer_id":"CUST-123","new_limit":50000},"requested_by":"user-123","schema_version":"1.0"}
```

---

### GAP-3: Modelo LegacyWriteAction ✅

**Implementado em:** `legacy_bridge/write_models.py`

```python
@dataclass
class LegacyWriteAction:
    action_id: str
    action_type: str
    params: Dict[str, Any]
    intent_sha256: str
    requested_by: str
    approved_by: Optional[str]
    mandate_id: Optional[str]
    created_at: str
    enqueued_at: Optional[str]
    acked_at: Optional[str]
    case_id: str
    institution_id: str
    dept_id: Optional[str]
    status: str
    denied_by: Optional[str]
    denied_reason: Optional[str]
```

---

### GAP-4: Eventos de ledger específicos ✅

**Implementado em:** `legacy_bridge/write_registry.py`

```python
LEGACY_WRITE_INTENT_CREATED = "LEGACY_WRITE_INTENT_CREATED"
LEGACY_WRITE_ALLOWED = "LEGACY_WRITE_ALLOWED"
LEGACY_WRITE_DENIED = "LEGACY_WRITE_DENIED"
LEGACY_WRITE_ENQUEUED = "LEGACY_WRITE_ENQUEUED"
LEGACY_WRITE_ACKED = "LEGACY_WRITE_ACKED"
```

---

### GAP-5: Integração com approval workflow

**Status:** Parcialmente implementado. Gates (mandate/autonomy/policy) integrados.
Approval workflow completo (com SoD) não incluído nesta etapa (fora do escopo MVP).

---

### GAP-6: Schema validation por action_type ✅

**Implementado em:** `legacy_bridge/write_models.py`

```python
ACTION_SCHEMAS = {
    "increase_limit": {
        "type": "object",
        "required": ["customer_id", "new_limit"],
        "properties": {
            "customer_id": {"type": "string"},
            "new_limit": {"type": "number", "minimum": 0},
            "reason": {"type": "string"},
        }
    }
}

def validate_action_params(action_type: str, params: Dict[str, Any]) -> List[str]
```

---

## Dependências

| Dependência | Status |
|-------------|--------|
| Legacy Bridge read-only | ✅ Existe |
| Mandate gate | ✅ Integrado |
| Autonomy gate | ✅ Integrado |
| Policy gate | ✅ Integrado |
| Approval workflow | ⚠️ Parcial (fora do MVP) |
| SoD check | ⚠️ Parcial (fora do MVP) |
| Ledger events | ✅ Implementado |
| Outbox connector | ✅ Implementado |
| Write endpoint | ✅ Implementado |
| Write action model | ✅ Implementado |
| Write ledger events | ✅ Implementado |

---

## Fluxo Implementado

```
1. POST /console/bridge/write/{action}
   ├── Body: { "params": {...}, "institution_id": "...", "dept_id": "..." }
   │
   ├── 2. Validate action_type (ACTION_SCHEMAS)
   │   └── Se inválido → return 400 LEGACY_WRITE_ACTION_TYPE_UNKNOWN
   │
   ├── 3. Validate params (validate_action_params)
   │   └── Se inválido → return 400 LEGACY_WRITE_PARAMS_INVALID
   │
   ├── 4. Create LegacyWriteAction + compute intent_sha256
   │
   ├── 5. Emit LEGACY_WRITE_INTENT_CREATED
   │
   ├── 6. PRE-GATES (ordem mandatória)
   │   ├── evaluate_mandates("pre", endpoint_sig, actor, params)
   │   │   └── Se deny → Emit LEGACY_WRITE_DENIED, return 403
   │   │
   │   ├── evaluate_autonomy("pre", endpoint_sig)
   │   │   └── Se deny → Emit LEGACY_WRITE_DENIED, return 403
   │   │
   │   └── evaluate_policies("pre", endpoint_sig, params)
   │       └── Se deny → Emit LEGACY_WRITE_DENIED, return 403
   │
   ├── 7. Emit LEGACY_WRITE_ALLOWED
   │
   ├── 8. Write outbox file (OutboxConnector.write_action)
   │   ├── Path: legacy_bridge/outbox/{action_id}.json
   │   └── Compute outbox_sha256
   │
   ├── 9. Emit LEGACY_WRITE_ENQUEUED
   │
   └── 10. Return 201 { "action_id": "...", "outbox_path": "...", "status": "enqueued" }
```

---

## Testes

**Arquivo:** `tests/test_legacy_bridge_write.py`
**Total:** 28 testes

| Classe | Testes |
|--------|--------|
| TestLegacyWriteActionModel | 4 |
| TestValidateActionParams | 5 |
| TestOutboxConnector | 4 |
| TestLegacyWriteRegistryAllowed | 3 |
| TestLegacyWriteRegistryDenied | 3 |
| TestLegacyWriteRegistryValidation | 2 |
| TestLegacyWriteRegistryIsolation | 3 |
| TestLegacyWriteRegistryListAndGet | 4 |

---

## Definition of Done (da spec.md)

- [x] Existe 1 ação write governada end-to-end até outbox
- [x] Auditor consegue provar offline o que foi pedido e por quê foi permitido

---

## Arquivos Modificados/Criados

| Arquivo | Ação |
|---------|------|
| `legacy_bridge/write_models.py` | Criado |
| `legacy_bridge/connectors/outbox_connector.py` | Criado |
| `legacy_bridge/write_registry.py` | Criado |
| `legacy_bridge/__init__.py` | Atualizado (exports write) |
| `console/routes.py` | Adicionado rotas write |
| `core/errors.py` | Adicionado códigos de erro |
| `tests/test_legacy_bridge_write.py` | Criado |
