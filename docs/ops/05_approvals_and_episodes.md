# Approvals and Episodes

Episodes are immutable records of pipeline executions. The approval gate ensures human sign-off before release.

## Episode Management Commands

```bash
# Show episode details
python -m episodes.episodes_cli show --episode-id <id>

# List episodes
python -m episodes.episodes_cli list
python -m episodes.episodes_cli list --status pending
python -m episodes.episodes_cli list --status approved

# Approve episode
python -m episodes.episodes_cli approve --episode-id <id> --decision approve --reason "..." --approver-name "..." --role "..."
```

## Episode Structure

Each episode is stored in `.engine/episodes/<episode_id>/`:

```
.engine/episodes/exec-abc123/
├── manifest.json       # Episode manifest with integrity hashes
├── runlog.json         # Execution runlog
├── contracts/          # Generated contracts
│   ├── contracts.json
│   └── contracts.md
├── input/              # Input files used
├── artifacts/          # Build artifacts
├── approvals/          # Approval records
│   └── approval.json
└── change_request/     # CR reference (if applicable)
    └── change_request.json
```

## Episode Manifest

The manifest contains metadata and integrity hashes:

```json
{
  "schema_version": "episode_manifest.v1",
  "episode_id": "exec-abc123",
  "execution_id": "exec-abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "created_by": null,
  "inputs": {
    "input_mode": "draft",
    "input_hash_sha256": "sha256:abc123..."
  },
  "outputs": {
    "repo_hash_sha256": "sha256:def456...",
    "release_artifact_hash_sha256": "sha256:..."
  },
  "links": {
    "previous_episode_id": null,
    "change_request_id": null,
    "cr_hash_sha256": null
  },
  "integrity": {
    "episode_root_hash_sha256": "sha256:789xyz...",
    "algorithm": "sha256",
    "file_hashes": {
      "manifest.json": "sha256:...",
      "runlog.json": "sha256:...",
      "contracts/contracts.json": "sha256:..."
    }
  },
  "status": "pending",
  "approval_status": null
}
```

## Viewing Episodes

### Show Episode Details

```bash
python -m episodes.episodes_cli show --episode-id exec-abc123
```

Output:
```
Episode: exec-abc123
Status: pending
Approval Status: awaiting_approval
Created: 2024-01-15T10:30:00Z

Inputs:
  Mode: draft
  Hash: sha256:abc123...

Integrity:
  Root Hash: sha256:789xyz...
  Algorithm: sha256

Links:
  Previous Episode: none
  Change Request: none
```

### List All Episodes

```bash
python -m episodes.episodes_cli list
```

Output:
```
Episodes:
  exec-abc123  pending   2024-01-15T10:30:00Z
  exec-def456  approved  2024-01-14T15:45:00Z
  exec-ghi789  rejected  2024-01-13T09:00:00Z
```

### List by Status

```bash
python -m episodes.episodes_cli list --status pending
```

## Approval Gate

The approval gate blocks release until explicit approval is registered.

### Gate Status

| Status | Description |
|--------|-------------|
| `awaiting_approval` | No approval registered |
| `approved` | Episode approved for release |
| `rejected` | Episode rejected |

### Checking Gate Status

```bash
python -m episodes.episodes_cli show --episode-id exec-abc123 --json
```

Check the `approval_status` and `gate_result` fields.

## Registering an Approval

### Approve an Episode

```bash
python -m episodes.episodes_cli approve \
  --episode-id exec-abc123 \
  --decision approve \
  --reason "Código revisado e testes passaram" \
  --approver-name "João Silva" \
  --role "Tech Lead"
```

Output:
```
SUCCESS: Approval added: appr-12345678
Episode: exec-abc123
Decision: approve
Gate Status: PASSED (approved)
```

### Reject an Episode

```bash
python -m episodes.episodes_cli approve \
  --episode-id exec-abc123 \
  --decision reject \
  --reason "Faltam testes de integração" \
  --approver-name "Maria Santos" \
  --role "QA Lead"
```

### Approval with Organization

```bash
python -m episodes.episodes_cli approve \
  --episode-id exec-abc123 \
  --decision approve \
  --reason "Aprovado conforme processo" \
  --approver-name "Carlos Oliveira" \
  --role "CTO" \
  --org "Acme Corp"
```

## Approval Record

Approvals are stored in `approvals/approval.json`:

```json
{
  "schema_version": "approval.v1",
  "approval_id": "appr-12345678",
  "episode_id": "exec-abc123",
  "approver": {
    "name": "João Silva",
    "role": "Tech Lead",
    "org": null
  },
  "decision": "approve",
  "reason": "Código revisado e testes passaram",
  "scope": {
    "what": "release"
  },
  "signatures": [
    {"scheme": "manual"}
  ],
  "volatile": {
    "timestamp": "2024-01-15T14:30:00Z"
  }
}
```

## Episode Status Flow

```
┌─────────────┐
│   pending   │
└──────┬──────┘
       │ approve/reject
       ▼
┌─────────────────────┐
│  approved/rejected  │
└─────────────────────┘
```

Once approved or rejected:
- Episode status is updated
- Manifest is finalized
- Integrity hashes are computed
- Episode becomes immutable

## Episode Integrity

### Verifying Integrity

```python
from episodes.episode_store import EpisodeStore

store = EpisodeStore()
valid, message = store.verify_integrity("exec-abc123")

if valid:
    print("Integrity OK")
else:
    print(f"INTEGRITY ERROR: {message}")
```

### Integrity Fields

| Field | Purpose |
|-------|---------|
| `episode_root_hash_sha256` | Hash of entire episode content |
| `file_hashes` | Individual file hashes |
| `algorithm` | Hash algorithm (sha256) |

## Immutability

After finalization, episodes are immutable:
- Cannot modify manifest
- Cannot modify runlog
- Cannot add/remove files
- Cannot change approval

Attempts to modify raise `EpisodeImmutableError`.

## Episode Chaining

Episodes can be linked via `previous_episode_id`:

```json
{
  "links": {
    "previous_episode_id": "exec-previous",
    "change_request_id": "cr-001",
    "cr_hash_sha256": "sha256:..."
  }
}
```

This enables traceability of changes over time.

## Common Operations

### Check if Episode Exists

```python
from episodes.episode_store import EpisodeStore

store = EpisodeStore()
if store.exists("exec-abc123"):
    print("Episode exists")
```

### Get Episode Manifest

```python
manifest = store.get_manifest("exec-abc123")
print(f"Status: {manifest['status']}")
```

### Check if Finalized

```python
if store.is_finalized("exec-abc123"):
    print("Episode is finalized and immutable")
```

## JSON Output

Add `--json` for machine-readable output:

```bash
python -m episodes.episodes_cli show --episode-id exec-abc123 --json
```

```bash
python -m episodes.episodes_cli approve ... --json
```

## Error Handling

### Episode Not Found

```
ERROR: Episode not found: exec-invalid
Error Code: EPISODE_NOT_FOUND
```

### Episode Already Finalized

```
ERROR: Cannot modify finalized episode: exec-abc123
Error Code: EPISODE_IMMUTABLE
```

### Invalid Approval Decision

```
ERROR: Invalid decision: maybe
Valid decisions: approve, reject
```

## Next Steps

After approving an episode:
1. [Create change requests](06_change_requests.md) for modifications
2. [Generate audit pack](07_auditpack_and_audits.md) for compliance
