# Mapeamento de Integração - OperationRegistry

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Objetivo:** Mapear pontos de integração para introduzir `operations.json` e `OperationRegistry`

---

## 1. Como o Bundle é Carregado

### Arquivo Principal
- **`src/engine/loader/load_bundle.py`**

### Detecção de Modo (single vs multi)

```python
# Linha 130-139
def _is_multi_dept_bundle(bundle_path: Path) -> bool:
    """Check if bundle is multi-department mode."""
    return (bundle_path / "departments").is_dir()
```

### Fluxo de Carregamento

1. `load_bundle()` (linha 781) - Entry point
2. Detecta modo: `_is_multi_dept_bundle(bundle_path)`
3. **Single mode**: `_load_single_dept_bundle()` (linha 338)
   - Carrega contratos do root do bundle
4. **Multi mode**: `_load_multi_dept_bundle()` (linha 221)
   - Carrega `contracts.json` do root
   - Itera sobre `departments/<dept_id>/` e carrega artefatos por dept

### Estrutura Global
```python
# Linha 91-97
_bundle_context: Optional[BundleContext] = None

@dataclass
class BundleContext:
    mode: str  # "single" or "multi"
    path: Path
    manifest: Dict[str, Any]
    departments: Dict[str, DeptContracts] = field(default_factory=dict)
    contracts_catalog: Optional[Dict[str, Any]] = None
```

---

## 2. Contratos Existentes por Dept

### Single Mode (root do bundle)
| Contrato | Obrigatório | Carregado em |
|----------|-------------|--------------|
| `rbac.json` | Sim | `_load_policies_single_mode()` linha 400 |
| `approvals.json` | Sim | `_load_policies_single_mode()` linha 419 |
| `sod.json` | Sim | `_load_policies_single_mode()` linha 432 |
| `invariants.json` | Sim | `_load_policies_single_mode()` linha 445 |
| `workflows.json` | Sim | `DeptContracts` dataclass |
| `mandates.json` | Sim | `_load_mandates_single_mode()` linha 503 |
| `autonomy.json` | Sim | `_load_autonomy_single_mode()` linha 562 |
| `policies.json` | Opcional | `_load_policies_single_mode()` linha 460 |
| `openapi.yaml` | Não | Apenas validação, não carregado em runtime |

### Multi Mode (por dept)
```
departments/<dept_id>/
├── rbac.json         (required)
├── approvals.json    (required)
├── sod.json          (required)
├── invariants.json   (required)
├── workflows.json    (required)
├── openapi.yaml      (required)
├── mandates.json     (opcional)
├── autonomy.json     (opcional)
└── policies.json     (opcional)
```

Definido em `DEPT_REQUIRED_ARTIFACTS` (linha 56-63):
```python
DEPT_REQUIRED_ARTIFACTS = [
    "rbac.json",
    "approvals.json",
    "workflows.json",
    "sod.json",
    "invariants.json",
    "openapi.yaml",
]
```

---

## 3. Onde `endpoint_sig` é Normalizado

### Definição Canônica (Allowlists)

Os `endpoint_sig` válidos são definidos em frozensets em cada módulo de governança:

| Módulo | Arquivo | Linha | Valores |
|--------|---------|-------|---------|
| Mandates | `src/engine/core/mandates.py` | 27-31 | `POST /finance/expenses`, `POST /approvals/{approval_id}/decide`, `POST /support/tickets` |
| Autonomy | `src/engine/core/autonomy.py` | 30-34 | Mesmos valores |
| Policy | `src/engine/core/policy.py` | 15-18 | `POST /finance/expenses`, `POST /approvals/{approval_id}/decide` |

### Validação no Parser IDL

- **`src/engine/ise/idl_parser.py`** (linhas 31-41)
  - Importa os ALLOWED_ENDPOINT_SIGS de mandates e autonomy
  - Valida durante parsing do IDL

### Uso em Runtime (API Handlers)

- **`src/engine/api/finance.py`** (linha 111, 133)
  ```python
  api_trigger = "POST /finance/expenses"
  endpoint_sig = api_trigger
  ```
- **`src/engine/api/approvals.py`**
  ```python
  endpoint_sig = "POST /approvals/{approval_id}/decide"
  ```
- **`src/engine/api/support.py`**
  ```python
  endpoint_sig = "POST /support/tickets"
  ```

### ISE Emitters

- **`src/engine/ise/emit/mandates_emit.py`**: Emite endpoint_sig direto do IDLMandate
- **`src/engine/ise/emit/autonomy_emit.py`**: Emite endpoint_sig direto do IDLAutonomyRule
- **`src/engine/ise/emit/policies_emit.py`**: Emite endpoint_sig direto do IDLPolicy

---

## 4. Local Correto para OperationRegistry em Runtime

### Opção Recomendada: `src/engine/core/operations.py`

Criar novo módulo seguindo o padrão existente:

```python
# src/engine/core/operations.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

@dataclass
class Operation:
    """A single operation definition."""
    operation_id: str
    method: str  # GET, POST, PUT, DELETE
    path: str  # e.g., "/finance/expenses"
    endpoint_sig: str  # e.g., "POST /finance/expenses"
    permission: str  # e.g., "expense.create"
    scope: str  # "tenant" or "global"
    idempotency: str  # "required", "optional", "none"
    errors: List[int] = field(default_factory=list)
    bind: Optional[Dict[str, Any]] = None  # {"kind": "create", "entity": "Expense"}

@dataclass
class OperationsDef:
    """Operations definition for a department."""
    dept_id: Optional[str]
    operations: List[Operation] = field(default_factory=list)

# Global registry per department
_operations: Dict[str, OperationsDef] = {}
SINGLE_MODE_KEY = "_single"

def set_operations(dept_id: Optional[str], ops_def: Optional[OperationsDef]) -> None:
    """Set operations for a department."""
    key = dept_id or SINGLE_MODE_KEY
    if ops_def is None:
        _operations.pop(key, None)
    else:
        _operations[key] = ops_def

def get_operations(dept_id: Optional[str]) -> Optional[OperationsDef]:
    """Get operations for a department."""
    key = dept_id or SINGLE_MODE_KEY
    return _operations.get(key)

def lookup_by_endpoint_sig(dept_id: Optional[str], endpoint_sig: str) -> Optional[Operation]:
    """Lookup operation by endpoint_sig."""
    ops_def = get_operations(dept_id)
    if ops_def is None:
        return None
    for op in ops_def.operations:
        if op.endpoint_sig == endpoint_sig:
            return op
    return None

def lookup_by_method_path(dept_id: Optional[str], method: str, path: str) -> Optional[Operation]:
    """Lookup operation by method + path."""
    ops_def = get_operations(dept_id)
    if ops_def is None:
        return None
    for op in ops_def.operations:
        if op.method == method and op.path == path:
            return op
    return None

def reset_all_operations() -> None:
    """Clear all operations (for testing)."""
    _operations.clear()
```

### Integração no Loader

Adicionar em `src/engine/loader/load_bundle.py`:

```python
# Após carregar outros contratos
def _load_operations_single_mode(bundle_path: Path) -> bool:
    operations_path = bundle_path / "operations.json"
    if operations_path.exists():
        ops_def = load_operations_from_file(operations_path)
        set_operations(None, ops_def)
    # Se não existir, não falha (compatibilidade legacy)
    return True
```

---

## 5. Implementação Final (DONE)

### ✅ Fase 6.1.1: ISE Emitter

1. ✅ Criado `src/engine/ise/emit/operations_emit.py`
2. ✅ Emite `operations.json` a partir de IRCS ou ParsedIDL
3. ✅ Adicionado ao `_emit_all_contracts()` em `compiler.py`

### ✅ Fase 6.1.2: Loader

1. ✅ Criado `src/engine/core/operations.py` com structs e registry
2. ✅ Adicionado `load_operations_from_file()`
3. ✅ Chamado no `load_bundle()` após carregar outros contratos
4. ✅ Se `operations.json` não existir, continua (legacy mode)

### ✅ Fase 6.1.3: Manifest

1. ✅ `operations.json` adicionado a `OPTIONAL_CONTRACTS` em `manifest.py`
   - `required: false` para manter compatibilidade com bundles legados

### Diagrama de Dependências

```
ISE Parser (ParsedIDL)
        │
        ▼
ISE Emitter (operations_emit.py)
        │
        ▼
Compiler (_emit_all_contracts)
        │
        ▼
Bundle (operations.json)
        │
        ▼
Loader (load_bundle.py)
        │
        ▼
Runtime Registry (operations.py)
        │
        ▼
Gates (mandates/autonomy/policy) - podem usar registry para validar endpoint_sig
```

---

## 6. Arquivos Modificados (DONE)

| Arquivo | Ação | Status |
|---------|------|--------|
| `src/engine/ise/emit/operations_emit.py` | Criado | ✅ |
| `src/engine/ise/emit/__init__.py` | Export adicionado | ✅ |
| `src/engine/ise/compiler.py` | emit_operations integrado | ✅ |
| `src/engine/ise/manifest.py` | OPTIONAL_CONTRACTS atualizado | ✅ |
| `src/engine/core/operations.py` | Criado | ✅ |
| `src/engine/loader/load_bundle.py` | Carregamento integrado | ✅ |
| `src/engine/ise/idl_parser.py` | Não modificado (conforme spec) | N/A |
| `tests/test_operations.py` | 27 testes criados | ✅ |

---

## 7. Compatibilidade com Bundles Legados

### Critério de Detecção

```python
def is_legacy_bundle(bundle_path: Path) -> bool:
    """Check if bundle is legacy (no operations.json)."""
    return not (bundle_path / "operations.json").exists()
```

### Comportamento

| Cenário | operations.json | Modo | Comportamento |
|---------|-----------------|------|---------------|
| Bundle legacy | Ausente | legacy | Rotas fixas, gates usam ALLOWED_ENDPOINT_SIGS hardcoded |
| Bundle IDL v1.2+ | Presente | idl | Registry carregado, gates validam contra registry |
| Multi-dept legacy | Ausente por dept | legacy | Cada dept opera em modo legacy |
| Multi-dept IDL | `departments/<dept>/operations.json` | idl | Registry por dept |

### Sem Breaking Changes

- Se `operations.json` não existir, o loader ignora
- Gates continuam usando ALLOWED_ENDPOINT_SIGS se registry vazio
- Runtime não requer operations.json para funcionar
