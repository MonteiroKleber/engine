# Legacy Bridge MVP - Data Model

**Data:** 2026-01-18
**Tipo:** Modelo de dados para PROMPT 2.7.1
**Status:** DIAGNÓSTICO (aguardando implementação)

---

## Resumo Executivo

Este documento define o modelo canônico de Legacy Asset e os eventos de ledger necessários para o Legacy Bridge MVP read-only.

---

## 1. LegacyAsset Model

### 1.1 Definição

Um `LegacyAsset` representa um artefato de sistema legado que está sob governança do engine, sem modificá-lo.

```python
@dataclass
class LegacyAsset:
    """Legacy asset under governance."""

    # Identification
    asset_id: str                    # UUID único do asset
    name: str                        # Nome human-readable (ex: "expense_report_2024")
    description: Optional[str]       # Descrição opcional

    # Source Information
    source_type: str                 # "file" | "http" | "dump"
    source_location: str             # Path, URL, ou identificador da fonte
    source_format: str               # "csv" | "json" | "xml" | "raw"

    # Schema/Metadata (extraído)
    schema_version: str              # Versão do schema extraído
    schema_metadata: Dict[str, Any]  # Metadados extraídos (colunas, tipos, etc.)

    # Integrity
    content_sha256: str              # "SHA256:<hex>" do conteúdo atual
    content_size_bytes: int          # Tamanho em bytes
    content_line_count: Optional[int]# Número de linhas (se aplicável)

    # Timestamps
    registered_at: str               # ISO8601 UTC - quando foi registrado
    last_verified_at: Optional[str]  # ISO8601 UTC - última verificação
    last_snapshot_at: Optional[str]  # ISO8601 UTC - último snapshot

    # Governance
    institution_id: str              # Institution owner
    registered_by: str               # Actor ID que registrou
    status: str                      # "active" | "archived" | "drift_detected"
```

### 1.2 Source Types

| Tipo | Descrição | Exemplo de `source_location` |
|------|-----------|------------------------------|
| `file` | Arquivo local (CSV, JSON, etc.) | `/data/exports/expense_report.csv` |
| `http` | Endpoint HTTP read-only | `https://legacy.system/api/v1/expenses` |
| `dump` | Export de tabela/banco | `exports/db_dump_20260118.sql` |

### 1.3 Source Formats

| Formato | Descrição | Schema Extraction |
|---------|-----------|-------------------|
| `csv` | Comma-separated values | Headers → column names |
| `json` | JSON array ou object | Keys → schema |
| `xml` | XML document | Elements → schema |
| `raw` | Binário ou texto sem estrutura | Apenas hash/size |

---

## 2. LegacyAssetSnapshot

Representa um snapshot point-in-time de um asset.

```python
@dataclass
class LegacyAssetSnapshot:
    """Point-in-time snapshot of legacy asset."""

    snapshot_id: str            # UUID do snapshot
    asset_id: str               # FK para LegacyAsset
    snapshot_at: str            # ISO8601 UTC

    # Content integrity at snapshot time
    content_sha256: str         # Hash do conteúdo
    content_size_bytes: int     # Tamanho
    content_line_count: Optional[int]

    # Previous snapshot for diff
    prev_snapshot_id: Optional[str]
    prev_content_sha256: Optional[str]

    # Drift detection
    drift_detected: bool        # True se hash diferente do anterior
    drift_type: Optional[str]   # "content_changed" | "size_changed" | "missing"

    # Actor/context
    verified_by: str            # Actor ID ou "system" para CLI
```

---

## 3. Ledger Events

### 3.1 LEGACY_ASSET_REGISTERED

Emitido quando um asset legado é registrado pela primeira vez.

```json
{
  "event_type": "LEGACY_ASSET_REGISTERED",
  "tenant_id": "<institution_id>",
  "actor": {
    "id": "<actor_id>",
    "roles": ["admin"]
  },
  "case_id": "<asset_id>",
  "step": "LEGACY_BRIDGE:asset.register",
  "payload": {
    "asset_id": "<uuid>",
    "name": "expense_report_2024",
    "source_type": "file",
    "source_location": "/data/exports/expense_report.csv",
    "source_format": "csv",
    "content_sha256": "SHA256:abcd1234...",
    "content_size_bytes": 102400,
    "schema_metadata": {
      "columns": ["id", "amount", "date", "description"],
      "row_count": 1234
    }
  }
}
```

### 3.2 LEGACY_ASSET_VERIFIED

Emitido quando um asset é verificado (hash recalculado, comparado).

```json
{
  "event_type": "LEGACY_ASSET_VERIFIED",
  "tenant_id": "<institution_id>",
  "actor": {
    "id": "system",
    "roles": ["system"]
  },
  "case_id": "<asset_id>",
  "step": "LEGACY_BRIDGE:asset.verify",
  "payload": {
    "asset_id": "<uuid>",
    "snapshot_id": "<uuid>",
    "expected_sha256": "SHA256:abcd1234...",
    "observed_sha256": "SHA256:abcd1234...",
    "drift_detected": false,
    "verification_result": "MATCH"
  }
}
```

### 3.3 LEGACY_DRIFT_DETECTED

Emitido quando drift é detectado (hash mudou).

```json
{
  "event_type": "LEGACY_DRIFT_DETECTED",
  "tenant_id": "<institution_id>",
  "actor": {
    "id": "system",
    "roles": ["system"]
  },
  "case_id": "<asset_id>",
  "step": "LEGACY_BRIDGE:drift.detected",
  "payload": {
    "asset_id": "<uuid>",
    "snapshot_id": "<uuid>",
    "expected_sha256": "SHA256:abcd1234...",
    "observed_sha256": "SHA256:efgh5678...",
    "drift_type": "content_changed",
    "expected_size_bytes": 102400,
    "observed_size_bytes": 105000,
    "detection_method": "periodic_verify"
  }
}
```

### 3.4 LEGACY_ASSET_MISSING

Emitido quando o asset fonte não é mais acessível.

```json
{
  "event_type": "LEGACY_ASSET_MISSING",
  "tenant_id": "<institution_id>",
  "actor": {
    "id": "system",
    "roles": ["system"]
  },
  "case_id": "<asset_id>",
  "step": "LEGACY_BRIDGE:asset.missing",
  "payload": {
    "asset_id": "<uuid>",
    "source_type": "file",
    "source_location": "/data/exports/expense_report.csv",
    "last_known_sha256": "SHA256:abcd1234...",
    "error": "FileNotFoundError: [Errno 2] No such file or directory"
  }
}
```

### 3.5 LEGACY_ASSET_ARCHIVED

Emitido quando um asset é arquivado (não mais monitorado).

```json
{
  "event_type": "LEGACY_ASSET_ARCHIVED",
  "tenant_id": "<institution_id>",
  "actor": {
    "id": "<actor_id>",
    "roles": ["admin"]
  },
  "case_id": "<asset_id>",
  "step": "LEGACY_BRIDGE:asset.archive",
  "payload": {
    "asset_id": "<uuid>",
    "reason": "System decommissioned",
    "final_sha256": "SHA256:abcd1234..."
  }
}
```

---

## 4. Storage Model

### 4.1 Registry File

Arquivo JSONL append-only com registro de assets.

```
<institution_root>/legacy_bridge/assets_registry.jsonl
```

Cada linha é um `LegacyAsset` serializado.

### 4.2 Snapshots File

Arquivo JSONL append-only com snapshots.

```
<institution_root>/legacy_bridge/snapshots.jsonl
```

### 4.3 State File

Estado atual de cada asset (para lookup rápido).

```
<institution_root>/legacy_bridge/state.json
```

```json
{
  "schema_version": "1.0",
  "assets": {
    "<asset_id>": {
      "name": "expense_report_2024",
      "status": "active",
      "last_sha256": "SHA256:abcd1234...",
      "last_verified_at": "2026-01-18T12:00:00Z",
      "drift_count": 0
    }
  }
}
```

---

## 5. Connectors

### 5.1 FileConnector (MVP)

Conector mínimo para arquivos locais.

```python
class FileConnector:
    """Read-only connector for local files."""

    def read_content(self, path: str) -> bytes:
        """Read file content."""
        with open(path, "rb") as f:
            return f.read()

    def compute_hash(self, path: str) -> str:
        """Compute SHA256 of file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"SHA256:{h.hexdigest()}"

    def extract_schema(self, path: str, format: str) -> Dict[str, Any]:
        """Extract schema metadata from file."""
        if format == "csv":
            return self._extract_csv_schema(path)
        elif format == "json":
            return self._extract_json_schema(path)
        return {"format": "raw"}

    def get_stats(self, path: str) -> Dict[str, Any]:
        """Get file stats (size, mtime, etc.)."""
        stat = os.stat(path)
        return {
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
```

### 5.2 HTTPConnector (Futuro)

```python
class HTTPConnector:
    """Read-only connector for HTTP endpoints."""

    def read_content(self, url: str) -> bytes:
        """Fetch content from HTTP endpoint."""
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content

    def compute_hash(self, url: str) -> str:
        """Compute SHA256 of HTTP response content."""
        content = self.read_content(url)
        return f"SHA256:{hashlib.sha256(content).hexdigest()}"
```

---

## 6. CLI Interface

### 6.1 Register Asset

```bash
python -m engine.legacy_bridge register \
    --name "expense_report_2024" \
    --source-type file \
    --source-location /data/exports/expense_report.csv \
    --source-format csv \
    --institution-id <uuid>
```

Output:
```
Asset registered: asset_id=<uuid>
SHA256: SHA256:abcd1234...
Schema: {"columns": ["id", "amount", "date"], "row_count": 1234}
Ledger event: LEGACY_ASSET_REGISTERED (seq=123)
```

### 6.2 Verify Asset

```bash
python -m engine.legacy_bridge verify \
    --asset-id <uuid> \
    --institution-id <uuid>
```

Output (no drift):
```
Asset verified: expense_report_2024
Status: MATCH
Expected: SHA256:abcd1234...
Observed: SHA256:abcd1234...
Ledger event: LEGACY_ASSET_VERIFIED (seq=124)
```

Output (drift detected):
```
Asset verified: expense_report_2024
Status: DRIFT_DETECTED
Expected: SHA256:abcd1234...
Observed: SHA256:efgh5678...
Drift type: content_changed
Ledger event: LEGACY_DRIFT_DETECTED (seq=125)
```

### 6.3 List Assets

```bash
python -m engine.legacy_bridge list \
    --institution-id <uuid>
```

Output:
```
Assets for institution <uuid>:
  1. expense_report_2024 (active)
     Source: file:/data/exports/expense_report.csv
     SHA256: SHA256:abcd1234...
     Last verified: 2026-01-18T12:00:00Z

  2. customer_data_export (drift_detected)
     Source: file:/data/exports/customers.json
     SHA256: SHA256:efgh5678... (drift from SHA256:abcd1234...)
     Last verified: 2026-01-18T11:30:00Z
```

### 6.4 Verify All

```bash
python -m engine.legacy_bridge verify-all \
    --institution-id <uuid>
```

Output:
```
Verifying 5 assets...
  expense_report_2024: MATCH
  customer_data_export: DRIFT_DETECTED
  inventory_dump: MATCH
  orders_2024: MATCH
  payments_log: MISSING

Summary:
  3 assets OK
  1 drift detected
  1 missing

Ledger events emitted: 5
```

---

## 7. Integração com Engine Existente

### 7.1 Reutilização de Código

| Componente | Uso no Legacy Bridge |
|------------|---------------------|
| `loader/verify_hashes.py` | `compute_sha256()`, `normalize_hash()` |
| `core/ledger.py` | Append de eventos ao ledger |
| `core/data_root.py` | `get_institution_root()` para paths |
| `core/ege.py` | Padrão de `DriftState` e detecção |

### 7.2 Padrões a Seguir

- Hash format: `SHA256:<hex>` (mesmo padrão de EGE)
- Ledger events: mesmo formato de `LedgerEvent`
- Storage: JSONL append-only para registry/snapshots
- CLI: `python -m engine.legacy_bridge <command>`

---

## 8. Considerações de Segurança

### 8.1 Read-Only Enforcement

- Nenhum conector deve ter capacidade de escrita
- Métodos de leitura retornam `bytes` imutáveis
- Sem side-effects no sistema legado

### 8.2 Path Validation

- Validar paths para evitar traversal (`../`)
- Whitelist de diretórios permitidos por institution
- Logging de todas as operações de leitura

### 8.3 Audit Trail

- Todo acesso a assets é registrado no ledger
- Drift/missing são imediatamente auditáveis
- CLI pode operar offline mas deve sincronizar ledger
