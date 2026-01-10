# AuditPack and Audits

AuditPack generates verifiable, reproducible ZIP archives from episodes for offline audit and compliance.

## Command

```bash
python -m episodes.episodes_cli auditpack \
  --episode-id <id> \
  --out <path.zip> \
  [--include-artifacts]
```

## Generating an AuditPack

### Basic Usage

```bash
python -m episodes.episodes_cli auditpack \
  --episode-id exec-abc123 \
  --out audit-exec-abc123.zip
```

Output:
```
SUCCESS: AuditPack created: audit-exec-abc123.zip
  Episode: exec-abc123
  Root Hash: sha256:789xyz...
  Total Files: 8
```

### Including Artifacts

```bash
python -m episodes.episodes_cli auditpack \
  --episode-id exec-abc123 \
  --out audit-exec-abc123.zip \
  --include-artifacts
```

This includes the `artifacts/` directory in the ZIP.

## AuditPack Contents

The generated ZIP contains:

```
auditpack/
├── index.json              # Canonical index with all hashes
├── README_AUDIT.md         # Verification instructions
├── episode/
│   ├── manifest.json       # Episode manifest
│   ├── runlog.json         # Execution runlog
│   ├── approvals/          # Approval files (if any)
│   │   └── approval.json
│   ├── change_request/     # Change request (if any)
│   │   └── change_request.json
│   ├── contracts/          # Generated contracts
│   │   ├── contracts.json
│   │   └── contracts.md
│   ├── input/              # Input files
│   └── artifacts/          # Build artifacts (if --include-artifacts)
└── hashes/
    └── sha256sums.txt      # SHA256 checksums
```

## Index Structure

The `index.json` contains:

```json
{
  "schema_version": "auditpack_index.v1",
  "episode_id": "exec-abc123",
  "execution_id": "exec-abc123",
  "created_at_volatile": "2024-01-15T14:30:00Z",
  "source_episode_root_hash": "sha256:original...",
  "files": [
    {
      "path": "auditpack/episode/manifest.json",
      "sha256": "sha256:abc123...",
      "size_bytes": 1234
    },
    {
      "path": "auditpack/episode/runlog.json",
      "sha256": "sha256:def456...",
      "size_bytes": 567
    }
  ],
  "root_hash_sha256": "sha256:789xyz...",
  "algorithm": "sha256",
  "include_artifacts": false,
  "stats": {
    "total_files": 8,
    "total_size_bytes": 15234,
    "has_approval": true,
    "has_change_request": false,
    "has_legacy_verify": false
  }
}
```

## Offline Verification

The AuditPack can be verified without any external dependencies.

### Step 1: Extract the ZIP

```bash
unzip audit-exec-abc123.zip -d audit-verify
cd audit-verify/auditpack
```

### Step 2: Verify Individual Files

```bash
sha256sum -c hashes/sha256sums.txt
```

Expected output:
```
auditpack/episode/manifest.json: OK
auditpack/episode/runlog.json: OK
auditpack/episode/contracts/contracts.json: OK
...
```

### Step 3: Verify Root Hash

Using Python:

```python
import json
import hashlib

with open('index.json') as f:
    index = json.load(f)

# Sort files by path
files = sorted(index['files'], key=lambda x: x['path'])

# Build blob
blob = ''.join(f"{f['path']}\n{f['sha256']}\n" for f in files)

# Compute hash
computed = 'sha256:' + hashlib.sha256(blob.encode()).hexdigest()

# Verify
if computed == index['root_hash_sha256']:
    print(f'Root hash verified: {computed}')
else:
    print(f'Root hash MISMATCH!')
    print(f'  Expected: {index["root_hash_sha256"]}')
    print(f'  Computed: {computed}')
```

### Step 4: Verify File Contents

```python
import json
import hashlib
from pathlib import Path

with open('index.json') as f:
    index = json.load(f)

errors = []
for entry in index['files']:
    path = Path(entry['path'])
    if not path.exists():
        errors.append(f'Missing: {path}')
        continue

    with open(path, 'rb') as f:
        actual = 'sha256:' + hashlib.sha256(f.read()).hexdigest()

    if actual != entry['sha256']:
        errors.append(f'Hash mismatch: {path}')

if errors:
    print('ERRORS:')
    for e in errors:
        print(f'  - {e}')
else:
    print('All files verified successfully!')
```

## Security Checks

AuditPack includes security checks that block forbidden files:

| Pattern | Reason |
|---------|--------|
| `.env` | Environment secrets |
| `secrets/` | Secret directory |
| `private_key` | Private keys |
| `.pem`, `.key` | Key files |
| `credentials/` | Credentials |
| `api_key`, `token` | API credentials |

### Security Error

If forbidden files are detected:

```
ERROR: SECURITY: Forbidden path pattern '.env' found in: input/.env
Error Code: AUDITPACK_SECURITY_BLOCKED
```

## Determinism

AuditPack generation is deterministic:

1. Files are sorted by path
2. Index JSON uses `sort_keys=True`
3. Root hash is computed from sorted `<path>\n<sha256>\n` blob

This ensures:
- Same episode always produces same root hash
- Reproducible verification

### Verify Determinism

```bash
# Generate twice
python -m episodes.episodes_cli auditpack --episode-id exec-abc123 --out audit1.zip
python -m episodes.episodes_cli auditpack --episode-id exec-abc123 --out audit2.zip

# Compare root hashes
unzip -p audit1.zip auditpack/index.json | jq .root_hash_sha256
unzip -p audit2.zip auditpack/index.json | jq .root_hash_sha256
# Should be identical
```

## JSON Output

```bash
python -m episodes.episodes_cli auditpack \
  --episode-id exec-abc123 \
  --out audit.zip \
  --json
```

Output:
```json
{
  "success": true,
  "message": "AuditPack created: audit.zip",
  "out_zip": "audit.zip",
  "data": {
    "episode_id": "exec-abc123",
    "root_hash": "sha256:789xyz...",
    "source_root_hash": "sha256:original...",
    "total_files": 8,
    "include_artifacts": false,
    "stats": {
      "total_files": 8,
      "total_size_bytes": 15234,
      "has_approval": true,
      "has_change_request": false
    }
  }
}
```

## Complete Audit Workflow

### Step 1: Run Engine and Create Episode

```bash
python main.py --project myapp --input spec.idl --input-mode idl --release
```

### Step 2: Approve Episode

```bash
python -m episodes.episodes_cli approve \
  --episode-id exec-abc123 \
  --decision approve \
  --reason "Approved for production" \
  --approver-name "CTO" \
  --role "CTO"
```

### Step 3: Generate AuditPack

```bash
python -m episodes.episodes_cli auditpack \
  --episode-id exec-abc123 \
  --out releases/audit-myapp-v1.0.0.zip \
  --include-artifacts
```

### Step 4: Store AuditPack

Store the ZIP in:
- Version control (for traceability)
- Secure archive (for compliance)
- Audit system (for review)

### Step 5: Verify Before Archive

```bash
cd releases
unzip audit-myapp-v1.0.0.zip -d verify
cd verify/auditpack
sha256sum -c hashes/sha256sums.txt
```

## Error Handling

### Episode Not Found

```
ERROR: Episode not found: exec-invalid
Error Code: EPISODE_NOT_FOUND
```

### Security Violation

```
ERROR: SECURITY: Forbidden path pattern '.env' found in: ...
Error Code: AUDITPACK_SECURITY_BLOCKED
```

### Validation Error

```
ERROR: Episode manifest not found
Error Code: AUDITPACK_VALIDATION_ERROR
```

## Audit Report Template

The `README_AUDIT.md` in the ZIP contains:

- Episode ID and hashes
- File counts and sizes
- Verification instructions with code
- Approval status
- File structure documentation

## Integration with Compliance

For SOC2/ISO27001 compliance:

1. Generate AuditPack for each release
2. Store ZIP in immutable archive
3. Record root hash in compliance system
4. Maintain chain of custody

## Next Steps

- [Troubleshooting](08_troubleshooting.md) for common issues
