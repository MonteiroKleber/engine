# Change Requests

Change Requests (CRs) enable traceable modifications to existing episodes. Each CR creates a new episode linked to the previous one.

## Command

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id <id> \
  --cr <path_to_cr.json> \
  [--input-mode idl|draft] \
  [--dry-run]
```

## Change Request Structure

Create a CR JSON file:

```json
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-001",
  "previous_episode_id": "exec-abc123",
  "requester": {
    "name": "João Silva",
    "role": "Product Owner"
  },
  "reason": "Add new customer field for tax ID",
  "target": "backend",
  "summary": "Add taxId field to Customer entity with validation",
  "risk_level": "low",
  "scope": {
    "entities_affected": ["Customer"],
    "usecases_affected": ["CreateCustomer", "UpdateCustomer"],
    "invariants": [
      {
        "name": "taxId_format_valid",
        "description": "Tax ID must follow valid CPF/CNPJ format",
        "severity": "must"
      }
    ]
  },
  "acceptance_criteria": [
    "Customer entity has taxId field",
    "Validation rejects invalid tax IDs",
    "Existing customers without taxId are not affected"
  ]
}
```

## CR Fields

| Field | Required | Description |
|-------|----------|-------------|
| `schema_version` | Yes | Must be `change_request.v1` |
| `change_request_id` | Yes | Unique CR identifier |
| `previous_episode_id` | Yes | Episode being modified |
| `requester.name` | Yes | Person requesting change |
| `requester.role` | Yes | Role of requester |
| `reason` | Yes | Why the change is needed |
| `target` | Yes | What is being changed |
| `summary` | Yes | Brief description |
| `risk_level` | Yes | `low`, `medium`, or `high` |
| `scope.entities_affected` | No | Affected entities |
| `scope.usecases_affected` | No | Affected use cases |
| `scope.invariants` | No | New or modified invariants |
| `acceptance_criteria` | Yes | Criteria for completion |

## Executing a Change Request

### Step 1: Create CR File

Save CR as `change_request.json`:

```json
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-add-taxid",
  "previous_episode_id": "exec-abc123",
  "requester": {
    "name": "Maria Santos",
    "role": "Tech Lead"
  },
  "reason": "Compliance requirement for tax reporting",
  "target": "backend",
  "summary": "Add taxId field to Customer entity",
  "risk_level": "low",
  "scope": {
    "entities_affected": ["Customer"]
  },
  "acceptance_criteria": [
    "Customer has taxId field",
    "API accepts taxId in create/update"
  ]
}
```

### Step 2: Validate with Dry Run

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id exec-abc123 \
  --cr change_request.json \
  --dry-run
```

Output:
```
Dry run: validation passed
  Change Request ID: cr-add-taxid
  Previous Episode ID: exec-abc123
  CR Hash: sha256:abc123...
  Would Create Episode: change-12345678
  Previous Episode Status: approved
```

### Step 3: Execute Change

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id exec-abc123 \
  --cr change_request.json
```

Output:
```
SUCCESS: Change episode created: change-12345678
  Change Request ID: cr-add-taxid
  Previous Episode ID: exec-abc123
  CR Hash: sha256:abc123...
  Episode Directory: .engine/episodes/change-12345678
```

## Episode Chain

The new episode links to the previous one:

```json
{
  "episode_id": "change-12345678",
  "links": {
    "previous_episode_id": "exec-abc123",
    "change_request_id": "cr-add-taxid",
    "cr_hash_sha256": "sha256:abc123..."
  }
}
```

This creates a traceable chain:

```
exec-abc123 ──▶ change-12345678 ──▶ change-87654321
     │                │                   │
     └─ CR: none     └─ CR: cr-add-taxid └─ CR: cr-fix-bug
```

## Validation Rules

The change command validates:

1. **CR Schema**: CR must match `change_request.v1` schema
2. **Previous Episode Match**: `CR.previous_episode_id` must match `--previous-episode-id`
3. **Episode Exists**: Previous episode must exist
4. **Episode Approved** (warning): Previous episode should be approved

### CR Previous Mismatch Error

If CR.previous_episode_id doesn't match argument:

```
ERROR: CR.previous_episode_id mismatch
  INTEGRITY: CR.previous_episode_id 'exec-wrong' does not match argument 'exec-abc123'
Error Code: CR_PREVIOUS_MISMATCH
```

### Previous Episode Not Found

```
ERROR: Previous episode not found: exec-invalid
  GOVERNANCE: Previous episode not found: exec-invalid
Error Code: PREVIOUS_EPISODE_NOT_FOUND
```

## Impact Gate

The Impact Gate validates CR scope:

| Blocked Reason | Cause |
|----------------|-------|
| `IMPACT_OUT_OF_SCOPE` | Change affects entities not in CR scope |
| `IMPACT_TOO_BROAD` | Change affects too many components |
| `IMPACT_FORBIDDEN_PATH` | Change affects protected paths |
| `IMPACT_GATE_BLOCKED` | General impact validation failure |

## Runlog for Change Execution

The change runlog includes CR reference:

```json
{
  "schema_version": "runlog.v1",
  "execution_id": "change-12345678",
  "final_status": "success",
  "blocked_reason": null,
  "duration_ms": 1250,
  "change_request": {
    "change_request_id": "cr-add-taxid",
    "previous_episode_id": "exec-abc123",
    "cr_hash_sha256": "sha256:abc123..."
  },
  "metrics": {
    "input_mode": "idl",
    "artifacts_generated": 0,
    "patches_applied": 0
  }
}
```

## CR Hash

The `cr_hash_sha256` is computed from the canonical (sorted keys) JSON of the CR. This ensures:

- Deterministic hashing
- Tamper detection
- Traceability

```python
from change_requests.cr_v1 import cr_hash_sha256, load_cr

cr = load_cr("change_request.json")
hash_value = cr_hash_sha256(cr)
print(f"CR Hash: {hash_value}")
```

## Complete Workflow Example

### Step 1: Initial Release

```bash
# Run initial engine
python main.py --project myapp --input spec.idl --input-mode idl --release
```

### Step 2: Approve Initial Episode

```bash
python -m episodes.episodes_cli approve \
  --episode-id exec-abc123 \
  --decision approve \
  --reason "Initial release approved" \
  --approver-name "CTO" \
  --role "CTO"
```

### Step 3: Create Change Request

Create `cr-v2.json`:

```json
{
  "schema_version": "change_request.v1",
  "change_request_id": "cr-v2-features",
  "previous_episode_id": "exec-abc123",
  "requester": {
    "name": "Product Team",
    "role": "Product Owner"
  },
  "reason": "Add v2 features per roadmap",
  "target": "backend",
  "summary": "Add reporting and export features",
  "risk_level": "medium",
  "scope": {
    "entities_affected": ["Report", "Export"],
    "usecases_affected": ["GenerateReport", "ExportData"]
  },
  "acceptance_criteria": [
    "Reports can be generated",
    "Data export to CSV works"
  ]
}
```

### Step 4: Execute Change

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id exec-abc123 \
  --cr cr-v2.json
```

### Step 5: Approve New Episode

```bash
python -m episodes.episodes_cli approve \
  --episode-id change-87654321 \
  --decision approve \
  --reason "V2 features verified" \
  --approver-name "Tech Lead" \
  --role "Tech Lead"
```

## Viewing CR in Episode

The CR is stored in the episode:

```bash
cat .engine/episodes/change-87654321/change_request/change_request.json
```

## JSON Output

```bash
python -m episodes.episodes_cli change \
  --previous-episode-id exec-abc123 \
  --cr change_request.json \
  --json
```

Output:
```json
{
  "success": true,
  "message": "Change episode created: change-12345678",
  "episode_id": "change-12345678",
  "data": {
    "change_request_id": "cr-add-taxid",
    "previous_episode_id": "exec-abc123",
    "cr_hash_sha256": "sha256:abc123...",
    "episode_dir": ".engine/episodes/change-12345678",
    "duration_ms": 1250.5
  }
}
```

## Next Steps

After creating change episodes:
1. [Approve the new episode](05_approvals_and_episodes.md)
2. [Generate audit pack](07_auditpack_and_audits.md) for compliance
