# API — Etapa 3.2: Institutional Explorer

**Data:** 2026-01-18
**Status:** IMPLEMENTADO (PROMPT 3.2.2)
**Prompt inicial:** 3.2.1 (Diagnóstico)

## 1. Como obter bundle ativo/pinned por institution_id/dept_id

### 1.1 Bundle Path Global

```python
# engine/loader/load_bundle.py:106-116
def get_bundle_path() -> Path:
    """Get the bundle path from ENV or default."""
    env_path = os.environ.get("ENGINE_BUNDLE_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_BUNDLE_PATH)  # "bundles/finance-pilot"
```

**Nota:** O `ENGINE_BUNDLE_PATH` define o bundle carregado pelo runtime. Não é por institution.

### 1.2 Bundle Context (runtime carregado)

```python
# engine/loader/load_bundle.py:95-97
_bundle_context: Optional[BundleContext] = None

def get_bundle_context() -> Optional[BundleContext]:
    """Get the current bundle context."""
    return _bundle_context
```

**BundleContext fields:**
- `mode`: "single" ou "multi"
- `path`: Path do bundle
- `manifest`: Dict com bundle.manifest.json parsed
- `departments`: Dict[str, DeptContracts] (multi-dept)
- `contracts_catalog`: contracts.json (multi-dept)

### 1.3 Pinned Hashes por Institution

```python
# engine/core/institution_config.py
def get_effective_config(institution_id: str) -> InstitutionConfig

# InstitutionConfig fields relevantes:
# - pinned_release_id: str
# - pinned_bundle_manifest_sha256: str
# - pinned_contract_ledger_sha256: str
```

### 1.4 Observed Hashes (CURRENT bundle deployed)

```python
# engine/core/ege_pins.py:101-143
def get_observed_hashes(institution_id: str) -> Tuple[str, Optional[str]]:
    """
    Reads CURRENT symlink -> resolved bundle path
    Returns (manifest_sha256, ledger_sha256)
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    current_path = bundles_root / "CURRENT"  # symlink
    resolved = current_path.resolve()
    manifest_path = resolved / "bundle.manifest.json"
    ledger_path = resolved / "contract_ledger.json"
```

### 1.5 Pin Status (drift detection)

```python
# engine/core/ege_pins.py:146-185
def get_pin_status(institution_id: str) -> Tuple[Optional[PinStatus], error_code, error_msg]

# PinStatus fields:
# - pinned_manifest, pinned_ledger (from config)
# - observed_manifest, observed_ledger (from CURRENT)
# - drift_status: "CLEAR" | "ACTIVE" | "UNPINNED"
```

### 1.6 Multi-Dept Discovery

```python
# engine/loader/load_bundle.py:81-87
@dataclass
class BundleContext:
    departments: Dict[str, DeptContracts]  # dept_id -> DeptContracts

# DeptContracts:
# - name: str
# - path: Path (departments/<dept_id>/)
# - rbac, approvals, workflows, sod, invariants: Dict
# - openapi: str (yaml content)
```

---

## 2. Rotas Console Existentes (Etapa 3.1)

| Rota | Descrição | Dados |
|------|-----------|-------|
| `GET /console/` | Home - seleção institution/dept | institutions list, departments list |
| `GET /console/status` | Status runtime | health, drift_status, config (pinned hashes) |
| `GET /console/bundles` | Bundles/releases | pinned vs observed, dev runs, proposals |
| `GET /console/legacy` | Legacy assets | bridge status (placeholder) |
| `GET /console/static/{path}` | Static files | CSS/JS |
| `GET /console/partials/status` | HTMX partial | health update |

### Helper Functions (routes.py)

```python
def _get_institutions_list() -> List[Dict]:
    registry = get_institutions_registry()
    return registry.list_institutions(limit=100)

def _get_departments_list() -> List[str]:
    ctx = get_bundle_context()
    return list(ctx.departments.keys())

def _get_health_info() -> Dict:
    return {"mode": runtime_state.mode.value, ...}

def _get_pin_status_info(institution_id) -> Dict:
    pin_status, _, _ = get_pin_status(institution_id)
    return {"pinned": ..., "observed": ..., "drift_status": ...}

def _get_institution_config_info(institution_id) -> Dict:
    config = get_effective_config(institution_id)
    return {
        "pinned_release_id": config.pinned_release_id,
        "pinned_bundle_manifest_sha256": config.pinned_bundle_manifest_sha256,
        ...
    }
```

---

## 3. verify_bundle_offline (Proof Verification)

### 3.1 Localização

```python
# engine/proof/verify.py:148-384
def verify_bundle_offline(bundle_path: Path) -> ProofResult
```

### 3.2 O que verifica

1. **Manifest exists** - `bundle.manifest.json`
2. **Contracts hash** - SHA256 de cada arquivo em `contracts[]`
3. **Ledger exists** - `contract_ledger.json`
4. **Ledger manifest_hash** - deve bater com hash real do manifest
5. **Ledger contracts[]** - 1:1 com manifest (mesmos arquivos, mesmos hashes)
6. **source_idl_sha256** - presente e formato válido

### 3.3 ProofResult

```python
@dataclass
class ProofResult:
    passed: bool
    error_code: Optional[str]
    error_message: Optional[str]
    bundle_name: Optional[str]
    bundle_version: Optional[str]
    source_idl_sha256: Optional[str]
    manifest_hash: Optional[str]
    contracts_verified: int
    details: Dict[str, Any]
```

### 3.4 Error Codes

| Code | Descrição |
|------|-----------|
| `PROOF_MANIFEST_MISSING` | bundle.manifest.json não encontrado |
| `PROOF_MANIFEST_INVALID_JSON` | JSON inválido |
| `PROOF_CONTRACT_MISSING` | Contract required não encontrado |
| `PROOF_CONTRACT_HASH_MISMATCH` | Hash do arquivo não bate |
| `PROOF_LEDGER_MISSING` | contract_ledger.json não encontrado |
| `PROOF_LEDGER_MANIFEST_HASH_MISMATCH` | manifest_hash no ledger não bate |
| `PROOF_LEDGER_CONTRACT_MISSING` | Contract no manifest mas não no ledger |
| `PROOF_LEDGER_CONTRACT_EXTRA` | Contract no ledger mas não no manifest |
| `PROOF_SOURCE_IDL_MISSING` | source_idl_sha256 não encontrado |
| `PROOF_PATH_TRAVERSAL` | Path traversal detectado |

### 3.5 Uso sem runtime

```python
from pathlib import Path
from engine.proof.verify import verify_bundle_offline

result = verify_bundle_offline(Path("/path/to/bundle"))
if result.passed:
    print(f"OK: {result.contracts_verified} contracts verified")
else:
    print(f"FAIL: {result.error_code} - {result.error_message}")
```

**Não requer:**
- Runtime ativo
- Banco de dados
- Ledger inicializado
- Institution config

---

## 4. Estrutura Bundle por Institution

```
var/institutions/<institution_id>/bundles/
├── CURRENT -> releases/20260118-120000  (symlink)
├── releases/
│   ├── 20260118-120000/
│   │   ├── bundle.manifest.json
│   │   ├── contract_ledger.json
│   │   ├── rbac.json
│   │   ├── policies.json
│   │   ├── mandates.json
│   │   └── ...
│   └── 20260117-100000/
│       └── ...
└── pending/
    └── ...
```

### Multi-Dept

```
bundle/
├── bundle.manifest.json
├── contract_ledger.json
├── contracts.json
└── departments/
    ├── dept-a/
    │   ├── rbac.json
    │   ├── approvals.json
    │   ├── policies.json
    │   ├── mandates.json
    │   └── ...
    └── dept-b/
        └── ...
```

---

## 5. Rotas Implementadas (Etapa 3.2)

| Rota | Descrição | Status |
|------|-----------|--------|
| `GET /console/contracts` | Lista contracts do bundle | IMPLEMENTADO |
| `GET /console/contracts/{file}` | Conteúdo de um contract | IMPLEMENTADO |
| `GET /console/proof` | Executa verify offline | IMPLEMENTADO |

### Parâmetros comuns

- `institution_id`: UUID (required)
- `dept_id`: string (optional, para multi-dept)
- `X-Admin-Token`: header (required)

### Funcionalidades

**`/console/contracts`**
- Lista contracts do manifest
- Mostra bundle.manifest.json com hash SHA256
- Mostra contract_ledger.json com hash SHA256
- Exibe source_idl_sha256
- Links para visualizar cada contract

**`/console/contracts/{file}`**
- Mostra conteúdo do contract
- Computa hash SHA256 do arquivo
- Compara com hash esperado no manifest
- Exibe MATCH/MISMATCH
- Proteção anti path-traversal

**`/console/proof`**
- Executa `verify_bundle_offline()`
- Mostra PASS/FAIL com detalhes
- Exibe cryptographic anchors (manifest_hash, source_idl_sha256)
- Opção `?show_json=true` para ver resultado raw

---

## 6. Funções a Reutilizar

| Função | Módulo | Uso |
|--------|--------|-----|
| `get_bundle_context()` | loader/load_bundle | Bundle carregado atual |
| `get_effective_config()` | core/institution_config | Config da institution |
| `get_pin_status()` | core/ege_pins | Pinned vs observed |
| `get_observed_hashes()` | core/ege_pins | Hashes do CURRENT |
| `verify_bundle_offline()` | proof/verify | Verificação offline |
| `compute_sha256()` | loader/verify_hashes | Hash de arquivo |
| `get_bundles_root_for_institution()` | ise/release | Path bundles da institution |

---

## 7. Diagrama de Acesso

```
Console Request
      │
      ▼
institution_id param
      │
      ├──> get_bundles_root_for_institution(institution_id)
      │         │
      │         ▼
      │    CURRENT symlink -> resolved bundle path
      │
      ├──> get_effective_config(institution_id)
      │         │
      │         ▼
      │    pinned_bundle_manifest_sha256
      │    pinned_contract_ledger_sha256
      │
      └──> verify_bundle_offline(resolved_path)
                │
                ▼
           ProofResult (passed/failed + details)
```
