# Legacy Bridge MVP - Gaps Analysis

**Data:** 2026-01-18
**Tipo:** Análise de gaps para PROMPT 2.7.1
**Status:** ✅ IMPLEMENTADO (PROMPT 2.7.2)

---

## Resumo Executivo

Todos os gaps críticos foram resolvidos. O engine agora possui um Legacy Bridge funcional para governança read-only de assets legados.

1. ✅ **GAP-1: Módulo legacy_bridge** - Implementado com todas as funcionalidades
2. ✅ **GAP-2: LegacyAsset Model** - Dataclass completa com todos os campos
3. ✅ **GAP-3: FileConnector** - Conector read-only para arquivos locais
4. ✅ **GAP-4: Ledger Event Types** - Eventos emitidos para registro/verify/drift/missing
5. ✅ **GAP-5: CLI Commands** - register, verify, list, verify-all funcionais
6. ✅ **GAP-6: Storage Files** - assets_registry.jsonl, snapshots.jsonl, state.json
7. ✅ **GAP-7: Error Codes** - Adicionados em `core/errors.py`

---

## GAP-1: Módulo `engine.legacy_bridge` ✅ RESOLVIDO

### Solução Implementada

Estrutura final do módulo:

```
src/engine/legacy_bridge/
├── __init__.py           # Exports públicos
├── __main__.py           # CLI entry point (argparse)
├── models.py             # LegacyAsset, LegacyAssetSnapshot
├── registry.py           # LegacyBridgeRegistry (JSONL append-only)
├── verify.py             # verify_asset, verify_all_assets
└── connectors/
    ├── __init__.py
    └── file_connector.py # FileConnector read-only
```

---

## GAP-2: LegacyAsset Model ✅ RESOLVIDO

### Solução Implementada

```python
# src/engine/legacy_bridge/models.py
@dataclass
class LegacyAsset:
    asset_id: str                    # Stable string (user-provided)
    name: str                        # Human-readable
    description: Optional[str]
    source_type: str                 # "file" | "http" | "dump"
    source_location: str             # Relative path only (no absolute, no ..)
    source_format: str               # "csv" | "json" | "xml" | "raw"
    schema_version: str
    schema_metadata: Dict[str, Any]  # CSV headers, JSON keys
    content_sha256: str              # "SHA256:<hex>"
    content_size_bytes: int
    content_line_count: Optional[int]
    registered_at: str               # ISO8601
    last_verified_at: Optional[str]
    last_snapshot_at: Optional[str]
    institution_id: str
    dept_id: Optional[str]           # Multi-dept support
    registered_by: str
    status: str                      # "active" | "archived" | "drift_detected"

@dataclass
class LegacyAssetSnapshot:
    snapshot_id: str
    asset_id: str
    snapshot_at: str
    content_sha256: str
    content_size_bytes: int
    content_line_count: Optional[int]
    prev_snapshot_id: Optional[str]
    prev_content_sha256: Optional[str]
    drift_detected: bool
    drift_type: Optional[str]        # "content_changed" | "missing"
    verified_by: str
```

---

## GAP-3: FileConnector ✅ RESOLVIDO

### Solução Implementada

```python
# src/engine/legacy_bridge/connectors/file_connector.py
class FileConnector:
    def __init__(self, base_path: Optional[Path] = None)
    def read_content(self, path: str) -> bytes
    def compute_hash(self, path: str) -> str           # "SHA256:<hex>"
    def extract_schema(self, path: str, format: str) -> Dict
    def get_stats(self, path: str) -> Dict
    def exists(self, path: str) -> bool
```

### Características de Segurança
- ❌ Rejeita paths absolutos
- ❌ Rejeita path traversal (`..`)
- ✅ Base path configurável para institution/dept namespacing

---

## GAP-4: Ledger Event Types ✅ RESOLVIDO

### Solução Implementada

```python
# src/engine/legacy_bridge/registry.py
LEGACY_ASSET_REGISTERED = "LEGACY_ASSET_REGISTERED"
LEGACY_ASSET_VERIFIED = "LEGACY_ASSET_VERIFIED"
LEGACY_DRIFT_DETECTED = "LEGACY_DRIFT_DETECTED"
LEGACY_ASSET_MISSING = "LEGACY_ASSET_MISSING"
LEGACY_ASSET_ARCHIVED = "LEGACY_ASSET_ARCHIVED"
```

### Exemplos de Payloads

**LEGACY_ASSET_REGISTERED:**
```json
{
  "asset_id": "expense-report-2024",
  "name": "Expense Report 2024",
  "source_type": "file",
  "source_location": "exports/expense_report.csv",
  "content_sha256": "SHA256:...",
  "schema_metadata": {"columns": ["id", "amount"], "row_count": 100}
}
```

**LEGACY_DRIFT_DETECTED:**
```json
{
  "asset_id": "expense-report-2024",
  "expected_sha256": "SHA256:abc...",
  "observed_sha256": "SHA256:def...",
  "drift_type": "content_changed"
}
```

---

## GAP-5: CLI Commands ✅ RESOLVIDO

### Solução Implementada

```bash
# Register
python -m engine.legacy_bridge register \
    --institution <uuid> \
    --asset-id expense-report-2024 \
    --name "Expense Report 2024" \
    --path exports/expense_report.csv \
    --format csv

# Verify single
python -m engine.legacy_bridge verify \
    --institution <uuid> \
    --asset-id expense-report-2024

# List all
python -m engine.legacy_bridge list \
    --institution <uuid>

# Verify all
python -m engine.legacy_bridge verify-all \
    --institution <uuid>
```

### Exit Codes
- `0`: Sucesso (MATCH para verify)
- `1`: Erro ou drift detectado

---

## GAP-6: Storage Files ✅ RESOLVIDO

### Solução Implementada

```
<institution_root>/legacy_bridge/
├── assets_registry.jsonl   # Append-only registro de assets
├── snapshots.jsonl         # Append-only snapshots point-in-time
└── state.json              # Estado atual para lookup rápido
```

Para multi-dept:
```
<institution_root>/depts/<dept_id>/legacy_bridge/
├── assets_registry.jsonl
├── snapshots.jsonl
└── state.json
```

---

## GAP-7: Error Codes ✅ RESOLVIDO

### Solução Implementada

```python
# src/engine/core/errors.py
LEGACY_ASSET_NOT_FOUND = "LEGACY_ASSET_NOT_FOUND"
LEGACY_ASSET_ALREADY_EXISTS = "LEGACY_ASSET_ALREADY_EXISTS"
LEGACY_SOURCE_UNAVAILABLE = "LEGACY_SOURCE_UNAVAILABLE"
LEGACY_DRIFT_DETECTED = "LEGACY_DRIFT_DETECTED"
LEGACY_CONNECTOR_ERROR = "LEGACY_CONNECTOR_ERROR"
LEGACY_PATH_INVALID = "LEGACY_PATH_INVALID"
```

---

## Matriz de Gaps (Final)

| Gap | Descrição | Status | Arquivos |
|-----|-----------|--------|----------|
| GAP-1 | Módulo legacy_bridge | ✅ | `src/engine/legacy_bridge/` |
| GAP-2 | LegacyAsset model | ✅ | `models.py` |
| GAP-3 | FileConnector | ✅ | `connectors/file_connector.py` |
| GAP-4 | Ledger event types | ✅ | `registry.py` |
| GAP-5 | CLI commands | ✅ | `__main__.py` |
| GAP-6 | Storage files | ✅ | `registry.py` |
| GAP-7 | Error codes | ✅ | `core/errors.py` |

---

## Decisões Tomadas

| ID | Questão | Decisão |
|----|---------|---------|
| D-1 | Conector MVP? | **A) FileConnector only** |
| D-2 | Schema extraction scope? | **B) CSV + JSON** (headers e top-level keys) |
| D-3 | CLI standalone ou API também? | **A) CLI only** (para MVP) |
| D-4 | Verificação periódica? | **A) Sob demanda only** |
| D-5 | Storage: ledger como primary? | **A) Registry + Ledger** (ambos) |
| D-6 | asset_id format? | **String estável** (não UUID) |
| D-7 | source_location validation? | **Relativo only** (sem absoluto, sem `..`) |

---

## Arquivos Criados

### Novos Arquivos
- `src/engine/legacy_bridge/__init__.py` - Exports públicos
- `src/engine/legacy_bridge/__main__.py` - CLI entry point
- `src/engine/legacy_bridge/models.py` - Dataclasses
- `src/engine/legacy_bridge/registry.py` - Asset registry
- `src/engine/legacy_bridge/verify.py` - Verificação
- `src/engine/legacy_bridge/connectors/__init__.py`
- `src/engine/legacy_bridge/connectors/file_connector.py`

### Arquivos Modificados
- `src/engine/core/errors.py` - Novos códigos de erro

### Testes Criados
- `tests/test_legacy_bridge_register.py` - 14 testes
- `tests/test_legacy_bridge_verify.py` - 13 testes
- `tests/test_legacy_bridge_cli.py` - 12 testes

---

## Verificação

### Testes
```bash
pytest tests/test_legacy_bridge_*.py -v
# 39 passed
```

### Cenários Cobertos
- ✅ Register cria record no registry e evento no ledger
- ✅ Register extrai schema de CSV (headers) e JSON (keys)
- ✅ Register rejeita paths absolutos
- ✅ Register rejeita path traversal (`..`)
- ✅ Register falha se arquivo não existe
- ✅ Register falha se asset_id já existe
- ✅ Verify retorna MATCH para arquivo não modificado
- ✅ Verify detecta drift ao modificar 1 byte
- ✅ Verify emite LEGACY_DRIFT_DETECTED no ledger
- ✅ Verify detecta arquivo missing/deleted
- ✅ Verify-all processa múltiplos assets
- ✅ CLI register funciona corretamente
- ✅ CLI verify retorna exit code apropriado
- ✅ CLI list mostra assets registrados
- ✅ Multi-dept suportado com paths isolados

---

## Comportamento Final

### Registro de Asset
```bash
$ python -m engine.legacy_bridge register \
    --institution test-001 \
    --asset-id expense-report \
    --path exports/report.csv \
    --format csv

Asset registered: asset_id=expense-report
SHA256: SHA256:a1b2c3d4...
Size: 1024 bytes
Schema: {'columns': ['id', 'amount', 'date'], 'row_count': 50}
Ledger event: LEGACY_ASSET_REGISTERED
```

### Verificação (sem drift)
```bash
$ python -m engine.legacy_bridge verify \
    --institution test-001 \
    --asset-id expense-report

Asset verified: expense-report
Status: MATCH
Expected: SHA256:a1b2c3d4...
Observed: SHA256:a1b2c3d4...
Ledger event: LEGACY_ASSET_VERIFIED
```

### Verificação (com drift)
```bash
$ python -m engine.legacy_bridge verify \
    --institution test-001 \
    --asset-id expense-report

Asset verified: expense-report
Status: DRIFT_DETECTED
Expected: SHA256:a1b2c3d4...
Observed: SHA256:e5f6g7h8...
Drift type: content_changed
Ledger event: LEGACY_DRIFT_DETECTED
```

---

## Definition of Done

- ✅ Existe pelo menos 1 conector read-only funcional (FileConnector)
- ✅ Drift é detectado e auditável (ledger events)
- ✅ O mecanismo não depende de runtime rodando (CLI offline)
- ✅ Paths validados (sem absoluto, sem traversal)
- ✅ 39 testes passando
