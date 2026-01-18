# Libervia Engine

## Pilot-Ready

This engine is pilot-ready. Before deploying, review the pilot documentation:

| Document | Description |
|----------|-------------|
| [Definition of Done](docs/pilot/DEFINITION_OF_DONE.md) | Acceptance criteria checklist |
| [Runbook](docs/pilot/RUNBOOK.md) | Operational procedures |
| [Examples](docs/pilot/EXAMPLES.md) | API usage examples |
| [Release Checklist](docs/pilot/RELEASE_CHECKLIST.md) | Deploy checklist |

### Quick Start (Pilot)

```bash
# 1. Run preflight check
./ops/checks/preflight.sh

# 2. Start engine
uvicorn engine.api.server:app --host 0.0.0.0 --port 8000

# 3. Verify health
curl http://localhost:8000/health
```

---

## NL to IDL Pipeline (Fase 5.6)

The engine includes a Natural Language to IDL pipeline for converting policy descriptions into structured IDL.

### Pipeline Steps

1. **Compile SIR** - Extract Structured Intermediate Representation from natural language
2. **Generate Draft** - Generate draft IDL from SIR
3. **Detect Gaps** - Identify missing policy information
4. **Apply Answers** - Resolve gaps with user answers
5. **Finalize** - Produce final validated IDL

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /nl/compile/sir` | Extract SIR from text |
| `POST /nl/compile/draft` | Generate draft IDL from SIR |
| `POST /nl/gaps` | Detect gaps in draft |
| `POST /nl/answers/apply` | Apply answers to resolve gaps |
| `POST /nl/finalize` | Finalize draft to production IDL |

### Example Usage

```bash
# 1. Compile text to SIR
curl -X POST http://localhost:8000/nl/compile/sir \
  -H "Content-Type: application/json" \
  -d '{"text": "Managers must approve expenses created by analysts."}'

# 2. Generate draft from SIR
curl -X POST http://localhost:8000/nl/compile/draft \
  -H "Content-Type: application/json" \
  -d '{"sir": <sir-from-step-1>}'

# 3. Detect gaps
curl -X POST http://localhost:8000/nl/gaps \
  -H "Content-Type: application/json" \
  -d '{"sir": <sir>, "draft": <draft>}'

# 4. Apply answers (if any gaps)
curl -X POST http://localhost:8000/nl/answers/apply \
  -H "Content-Type: application/json" \
  -d '{"draft": <draft>, "gaps": <gaps>, "answers": []}'

# 5. Finalize
curl -X POST http://localhost:8000/nl/finalize \
  -H "Content-Type: application/json" \
  -d '{"draft": <draft>, "remaining_gaps": [], "allow_gaps": false}'
```

### Supported Languages

- English (en)
- Portuguese (pt)

Language is auto-detected or can be specified via the `language` parameter.

### LLM Extractor (Fase 5.7)

The NL pipeline supports an optional LLM-based extractor with automatic fallback to deterministic extraction.

**Configuration:**

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_NL_EXTRACTOR` | Extractor type: `deterministic` or `llm` | `deterministic` |
| `ENGINE_NL_LLM_PROVIDER` | LLM provider: `mock` or `openai` | `mock` |
| `ENGINE_NL_LLM_TIMEOUT_MS` | LLM request timeout in milliseconds | `8000` |
| `ENGINE_NL_LLM_MODEL` | Model identifier (provider-specific) | provider default |

**Behavior:**

- When `ENGINE_NL_EXTRACTOR=llm`:
  - Uses LLM for extraction
  - On success: `sir.meta.extractor_used="llm"`
  - On failure (invalid JSON, schema error, timeout): falls back to deterministic
  - On fallback: `sir.meta.extractor_used="deterministic_fallback"` and `sir.meta.llm_error_code` set

**Example:**

```bash
# Use LLM extractor with mock provider
ENGINE_NL_EXTRACTOR=llm ENGINE_NL_LLM_PROVIDER=mock \
  curl -X POST http://localhost:8000/nl/compile/sir \
    -H "Content-Type: application/json" \
    -d '{"text": "Managers must approve expenses."}'
```

---

## ISE Compiler (Fase 6.1)

The ISE (IDL to Structured Executable) compiler converts final IDL into an executable bundle containing all contracts needed for runtime.

### Endpoint

| Endpoint | Description |
|----------|-------------|
| `POST /ise/compile/bundle` | Compile IDL to bundle |
| `POST /ise/compile/bundle/full` | Compile IDL and return full contract contents |

### Bundle Contents

The compiled bundle includes:

| File | Description |
|------|-------------|
| `bundle.manifest.json` | Bundle metadata with SHA256 hashes |
| `contract_ledger.json` | Audit trail for contracts |
| `rbac.json` | Role-based access control rules |
| `workflows.json` | Workflow definitions |
| `approvals.json` | Approval rules (if applicable) |
| `sod.json` | Segregation of duties rules (if applicable) |
| `invariants.json` | Data validation constraints |
| `openapi.yaml` | API specification |

### Example Usage

```bash
# Compile IDL to bundle
curl -X POST http://localhost:8000/ise/compile/bundle \
  -H "Content-Type: application/json" \
  -d '{
    "idl": "{\"system\": \"finance-pilot\", \"version\": \"1.0.0\", \"entities\": [{\"type\": \"expense\", \"name\": \"Expense\", \"fields\": [{\"name\": \"amount\", \"type\": \"number\", \"required\": true}]}], \"actors\": [{\"role\": \"employee\", \"permissions\": [{\"resource\": \"expense\", \"actions\": [\"create\"]}]}], \"usecases\": []}",
    "bundle_name": "finance-pilot"
  }'
```

### Response

```json
{
  "success": true,
  "bundle_name": "finance-pilot",
  "version": "1.0.0",
  "bundle_hash": "abc123...",
  "contracts": [
    "approvals.json",
    "bundle.manifest.json",
    "contract_ledger.json",
    "invariants.json",
    "openapi.yaml",
    "rbac.json",
    "sod.json",
    "workflows.json"
  ],
  "sha256s": {
    "rbac.json": "...",
    "workflows.json": "..."
  }
}
```

### Validation

- **Finance-pilot MVP**: By default, the compiler validates that the IDL contains an `expense` entity. This can be disabled with `validate_finance_pilot: false`.
- **Approval keywords**: Approval rules are only generated if explicit approval keywords are found (e.g., "must be approved", "requires approval", "deve ser aprovado").
- **SoD keywords**: Segregation of duties rules are only generated if explicit SoD keywords are found (e.g., "cannot approve their own", "segregation of duties", "não pode aprovar sua própria").

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `ISE_IDL_INVALID_JSON` | 400 | IDL is not valid JSON |
| `ISE_IDL_PARSE_FAILED` | 400 | IDL parsing failed |
| `ISE_IDL_INSUFFICIENT` | 409 | IDL missing required entities for finance-pilot |
| `ISE_EMIT_FAILED` | 500 | Contract emission failed |
| `ISE_MANIFEST_FAILED` | 500 | Manifest generation failed |

### Determinism

The compiler produces **deterministic output**: the same IDL will always produce the same contracts and hashes (excluding timestamps in manifest/ledger).

---

## ISE Release (Fase 6.2)

The `/ise/compile/release` endpoint compiles IDL and deploys via lifecycle scripts (STAGING -> releases -> CURRENT).

### Endpoint

| Endpoint | Description |
|----------|-------------|
| `POST /ise/compile/release` | Compile IDL and deploy to production |

### Authentication

Requires `X-Admin-Token` header matching `ENGINE_ISE_ADMIN_TOKEN` environment variable.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_ISE_ADMIN_TOKEN` | Admin token for release endpoint | (required) |
| `ENGINE_PROD_BUNDLES_ROOT` | Production bundles directory | `/var/lib/engine/bundles` |
| `ENGINE_VERIFY_SCRIPT` | Bundle verification script | `/home/bazari/engine/ops/checks/verify_bundle.sh` |
| `ENGINE_DEPLOY_SCRIPT` | Production deploy script | `/home/bazari/engine/ops/scripts/deploy_engine_prod.sh` |

### Release Process

1. **Compile** - Bundle is compiled to temporary directory
2. **Stage** - Bundle is copied to `${ENGINE_PROD_BUNDLES_ROOT}/STAGING/<bundle_name>`
3. **Verify** - `verify_bundle.sh <staging_path>` is executed
4. **Deploy** - `deploy_engine_prod.sh` is executed (if verify passes)

### Example Usage

```bash
# Compile and deploy
curl -X POST http://localhost:8000/ise/compile/release \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-token" \
  -d '{
    "idl": "{\"system\": \"finance-pilot\", \"version\": \"1.0.0\", ...}",
    "bundle_name": "finance-pilot"
  }'
```

### Response

**Success (deployed):**
```json
{
  "status": "deployed",
  "release_id": "20250115-143022",
  "bundle_name": "finance-pilot",
  "bundle_hash": "abc123..."
}
```

**Deploy failed (rolled back):**
```json
{
  "status": "rolled_back",
  "release_id": "20250115-143022",
  "bundle_name": "finance-pilot",
  "bundle_hash": "abc123...",
  "error": {
    "code": "ISE_DEPLOY_FAILED",
    "message": "Deploy failed, rolled back",
    "exit_code": 1,
    "output": "Error details..."
  }
}
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `ISE_ADMIN_UNAUTHORIZED` | 401 | Invalid or missing admin token |
| `ISE_SCRIPT_UNAVAILABLE` | 500 | Verify or deploy script not found |
| `ISE_RELEASE_WRITE_FAILED` | 500 | Failed to copy bundle to staging |
| `ISE_VERIFY_FAILED` | 409 | Bundle verification failed |
| `ISE_DEPLOY_FAILED` | 200 | Deploy failed (status: rolled_back) |

---

## Pipeline Deploy (Fase 6.3)

The `/pipeline/deploy` endpoint executes the full Natural Language to Deploy pipeline in a single operation.

### Endpoint

| Endpoint | Description |
|----------|-------------|
| `POST /pipeline/deploy` | Full NL to Deploy pipeline |

### Authentication

Requires `X-Admin-Token` header matching `ENGINE_ISE_ADMIN_TOKEN` environment variable.

### Pipeline Steps

1. **compile_sir** - Extract SIR from natural language text
2. **compile_draft** - Generate draft IDL from SIR
3. **detect_gaps** - Find missing policy information
4. **apply_answers** - Fill gaps with user answers (if provided)
5. **finalize** - Produce final validated IDL
6. **compile_release** - Compile bundle and deploy

### Request

```json
{
  "text": "Employees can create expenses. Managers approve expenses.",
  "bundle_name": "finance-pilot",
  "target": "production",
  "answers": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Natural language policy description |
| `bundle_name` | string | Name for the bundle |
| `target` | string | Deployment target (default: `production`) |
| `answers` | list/null | Answers to gap questions (null on first run) |

### Response States

**NEEDS_ANSWERS** - Gaps found, user must provide answers:
```json
{
  "status": "NEEDS_ANSWERS",
  "bundle_name": "finance-pilot",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "gaps": [
    {
      "gap_key": "gap-approval-expense",
      "gap_type": "approval",
      "severity": "required",
      "questions": [
        {
          "question_id": "q-123",
          "question_text": "Does expense creation require approval?"
        }
      ]
    }
  ],
  "sir": {...},
  "draft_idl": {...}
}
```

**DEPLOYED** - Successfully deployed:
```json
{
  "status": "DEPLOYED",
  "bundle_name": "finance-pilot",
  "release_id": "20250115-143022",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "hash_idl_final": "ghi789...",
  "bundle_hash": "jkl012..."
}
```

**ROLLED_BACK** - Deploy failed, changes rolled back:
```json
{
  "status": "ROLLED_BACK",
  "bundle_name": "finance-pilot",
  "release_id": "20250115-143022",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "hash_idl_final": "ghi789...",
  "bundle_hash": "jkl012...",
  "error": {
    "code": "ISE_DEPLOY_FAILED",
    "message": "Deploy failed, rolled back",
    "exit_code": 1
  }
}
```

### Example Usage

```bash
# First run - may return NEEDS_ANSWERS
curl -X POST http://localhost:8000/pipeline/deploy \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-token" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "answers": null
  }'

# Second run - with answers
curl -X POST http://localhost:8000/pipeline/deploy \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-token" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "answers": [
      {"question_id": "q-123", "value": true},
      {"question_id": "q-456", "value": "manager"}
    ]
  }'
```

### Trace Hashes

All responses include SHA256 hashes for traceability:

| Hash | Description |
|------|-------------|
| `hash_sir` | Hash of Structured Intermediate Representation |
| `hash_draft` | Hash of draft IDL |
| `hash_idl_final` | Hash of final IDL |
| `bundle_hash` | Hash of compiled bundle |

---

## Pipeline Build (Fase 6.4)

The `/pipeline/build` endpoint executes NL to Bundle compilation in a sandbox, without deploying.

### Endpoint

| Endpoint | Description |
|----------|-------------|
| `POST /pipeline/build` | NL to Bundle build (sandbox, no deploy) |

### Authentication

**No authentication required.** This is a public endpoint.

### Pipeline Steps

1. **compile_sir** - Extract SIR from natural language text
2. **compile_draft** - Generate draft IDL from SIR
3. **detect_gaps** - Find missing policy information
4. **apply_answers** - Fill gaps with user answers (if provided)
5. **finalize** - Produce final validated IDL
6. **compile_bundle** - Compile bundle to dev-runs sandbox

**Important:** This endpoint does NOT call `compile_release`, deploy scripts, or `subprocess`. Bundles are written to a sandbox directory.

### Request

```json
{
  "text": "Employees can create expenses. Managers approve expenses.",
  "bundle_name": "finance-pilot",
  "answers": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Natural language policy description |
| `bundle_name` | string | Name for the bundle |
| `answers` | list/null | Answers to gap questions (null on first run) |

### Response States

**NEEDS_ANSWERS** - Gaps found, user must provide answers:
```json
{
  "status": "NEEDS_ANSWERS",
  "bundle_name": "finance-pilot",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "gaps": [...],
  "sir": {...},
  "draft_idl": {...}
}
```

**BUILT** - Successfully built in sandbox:
```json
{
  "status": "BUILT",
  "bundle_name": "finance-pilot",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_path": "bundles/dev-runs/550e8400-e29b-41d4-a716-446655440000/finance-pilot",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "hash_idl_final": "ghi789...",
  "bundle_hash": "jkl012..."
}
```

### Sandbox Location

Bundles are written to: `bundles/dev-runs/<run_id>/<bundle_name>/`

Each call generates a new UUID v4 `run_id`, ensuring isolation between builds.

### Example Usage

```bash
# First run - may return NEEDS_ANSWERS
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "answers": null
  }'

# Second run - with answers
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "answers": [
      {"question_id": "q-123", "value": true},
      {"question_id": "q-456", "value": "manager"}
    ]
  }'
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `PIPELINE_TEXT_REQUIRED` | 400 | Text is required |
| `PIPELINE_BUNDLE_NAME_REQUIRED` | 400 | Bundle name is required |
| `PIPELINE_BUILD_WRITE_FAILED` | 500 | Failed to write bundle to sandbox |
| `PIPELINE_STAGE_FAILED` | 500 | Pipeline stage failed (includes stage name) |

---

## Pipeline Export & Download (Fase 6.5)

Export sandbox bundles to deterministic ZIP and download.

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /pipeline/build/export` | Export bundle to deterministic ZIP |
| `GET /pipeline/build/download` | Download exported ZIP file |

### Authentication

**No authentication required.** Both endpoints are public.

### Export Request

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_name": "finance-pilot"
}
```

### Export Response

```json
{
  "status": "EXPORTED",
  "zip_path": "bundles/dev-runs/550e8400-.../exports/finance-pilot.zip",
  "zip_sha256": "abc123...",
  "download_url": "/pipeline/build/download?run_id=550e8400-...&bundle_name=finance-pilot"
}
```

### Download

```bash
curl -O "http://localhost:8000/pipeline/build/download?run_id=550e8400-...&bundle_name=finance-pilot"
```

Response:
- Content-Type: `application/zip`
- Content-Disposition: `attachment; filename="finance-pilot.zip"`

### Deterministic ZIP Properties

The exported ZIP is deterministic (same input = same SHA256):

- **Sorted paths**: Files are sorted alphabetically
- **Fixed timestamp**: All files use 1980-01-01 00:00:00
- **Fixed permissions**: All files use 0644
- **DEFLATED compression**: Consistent compression algorithm

### ZIP Structure

```
finance-pilot/
├── approvals.json
├── bundle.manifest.json
├── contract_ledger.json
├── invariants.json
├── openapi.yaml
├── rbac.json
├── sod.json
└── workflows.json
```

### Export Path

ZIPs are created at: `bundles/dev-runs/<run_id>/exports/<bundle_name>.zip`

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `PIPELINE_RUN_NOT_FOUND` | 404 | Run ID does not exist |
| `PIPELINE_BUNDLE_NOT_FOUND` | 404 | Bundle not found in run |
| `PIPELINE_EXPORT_FAILED` | 500 | Failed to create ZIP |
| `PIPELINE_DOWNLOAD_NOT_FOUND` | 404 | ZIP not found (export first) |

### Example Flow

```bash
# 1. Build bundle
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "bundle_name": "my-bundle", "answers": [...]}'
# Response: {"status": "BUILT", "run_id": "abc123...", ...}

# 2. Export to ZIP
curl -X POST http://localhost:8000/pipeline/build/export \
  -H "Content-Type: application/json" \
  -d '{"run_id": "abc123...", "bundle_name": "my-bundle"}'
# Response: {"status": "EXPORTED", "download_url": "...", ...}

# 3. Download ZIP
curl -O "http://localhost:8000/pipeline/build/download?run_id=abc123...&bundle_name=my-bundle"
```

---

## Dev Runs Registry & Cleanup (Fase 6.6)

Manage sandbox dev-runs with append-only registry and TTL-based cleanup.

### Registry

The registry tracks all dev-run lifecycle events in an append-only JSONL file.

**Default path:** `var/dev_runs_registry.jsonl`

**Override:** `ENGINE_DEV_RUNS_REGISTRY_PATH`

**Event Types:**
- `DEV_RUN_CREATED` - Emitted when `POST /pipeline/build` succeeds with `BUILT` status
- `DEV_RUN_EXPORTED` - Emitted when `POST /pipeline/build/export` succeeds
- `DEV_RUN_DELETED` - Emitted when cleanup deletes a run

### Admin Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /pipeline/build/runs` | List active (non-deleted) dev runs |
| `POST /pipeline/build/cleanup` | Execute cleanup (TTL + MAX_RUNS) |

### Authentication

Both endpoints require `X-Admin-Token` header matching `ENGINE_ISE_ADMIN_TOKEN`.

### List Runs

```bash
curl -X GET "http://localhost:8000/pipeline/build/runs?limit=50" \
  -H "X-Admin-Token: your-secret-token"
```

Response:
```json
{
  "runs": [
    {
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "bundle_name": "finance-pilot",
      "created_at": "2024-01-15T10:00:00+00:00",
      "bundle_path": "bundles/dev-runs/550e8400-.../finance-pilot",
      "has_zip": true,
      "zip_path": "bundles/dev-runs/550e8400-.../exports/finance-pilot.zip",
      "zip_sha256": "abc123...",
      "deleted": false
    }
  ],
  "total": 1
}
```

| Parameter | Type | Description | Default | Max |
|-----------|------|-------------|---------|-----|
| `limit` | int | Maximum runs to return | 50 | 200 |

### Cleanup

```bash
# Dry run (simulate)
curl -X POST http://localhost:8000/pipeline/build/cleanup \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-token" \
  -d '{"dry_run": true}'

# Real cleanup
curl -X POST http://localhost:8000/pipeline/build/cleanup \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-token" \
  -d '{"dry_run": false}'
```

Response:
```json
{
  "success": true,
  "dry_run": false,
  "deleted_run_ids": ["run-001", "run-002"],
  "deleted_paths": [
    "bundles/dev-runs/run-001",
    "bundles/dev-runs/run-002"
  ],
  "ttl_expired_count": 1,
  "max_runs_exceeded_count": 1
}
```

### Cleanup Policy

Cleanup is deterministic and applies two rules in order:

1. **TTL expiration**: Delete runs older than `ENGINE_DEV_RUNS_TTL_HOURS` (oldest first)
2. **Max runs**: Delete oldest runs to stay under `ENGINE_DEV_RUNS_MAX_RUNS`

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_DEV_RUNS_REGISTRY_PATH` | Path to registry JSONL file | `var/dev_runs_registry.jsonl` |
| `ENGINE_DEV_RUNS_TTL_HOURS` | Run TTL in hours | `24` |
| `ENGINE_DEV_RUNS_MAX_RUNS` | Maximum active runs | `200` |

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `ISE_ADMIN_UNAUTHORIZED` | 401 | Invalid or missing admin token |
| `DEV_RUNS_REGISTRY_UNAVAILABLE` | 500 | Failed to read registry |
| `DEV_RUNS_CLEANUP_FAILED` | 500 | Cleanup operation failed |

---

## Run Detail & Diff (Fase 6.7)

Get detailed trace information for a run and compare IDL files between runs.

### Persistent Artifacts

When a build completes with `BUILT` status, the following files are persisted in `bundles/dev-runs/<run_id>/`:

| File | Description |
|------|-------------|
| `idl_final.idl` | Final IDL JSON (pretty-printed) |
| `trace.json` | Trace hashes for traceability |

**trace.json structure:**
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_name": "finance-pilot",
  "sir_sha256": "abc123...",
  "draft_sha256": "def456...",
  "final_idl_sha256": "ghi789...",
  "bundle_manifest_sha256": "jkl012...",
  "contract_ledger_sha256": "mno345..."
}
```

### Admin Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /pipeline/build/runs/{run_id}` | Get detailed run info with trace |
| `GET /pipeline/build/diff` | Generate unified diff between two runs |

### Authentication

Both endpoints require `X-Admin-Token` header matching `ENGINE_ISE_ADMIN_TOKEN`.

### Run Detail

```bash
curl -X GET "http://localhost:8000/pipeline/build/runs/550e8400-..." \
  -H "X-Admin-Token: your-secret-token"
```

Response:
```json
{
  "success": true,
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_name": "finance-pilot",
  "created_at": "2024-01-15T10:00:00+00:00",
  "bundle_path": "bundles/dev-runs/550e8400-.../finance-pilot",
  "has_zip": true,
  "zip_path": "bundles/dev-runs/550e8400-.../exports/finance-pilot.zip",
  "zip_sha256": "abc123...",
  "deleted": false,
  "trace": {
    "run_id": "550e8400-...",
    "bundle_name": "finance-pilot",
    "sir_sha256": "abc123...",
    "draft_sha256": "def456...",
    "final_idl_sha256": "ghi789...",
    "bundle_manifest_sha256": "jkl012...",
    "contract_ledger_sha256": "mno345..."
  }
}
```

### Run Diff

Compare IDL files between two runs using unified diff format.

```bash
curl -X GET "http://localhost:8000/pipeline/build/diff?run_a=run1&run_b=run2" \
  -H "X-Admin-Token: your-secret-token"
```

Response:
```json
{
  "success": true,
  "run_a": "run1",
  "run_b": "run2",
  "diff": "--- run-a/run1/idl_final.idl\n+++ run-b/run2/idl_final.idl\n@@ -1,3 +1,3 @@\n...",
  "is_identical": false,
  "size_a": 1024,
  "size_b": 1152
}
```

**Size limit:** 256KB per IDL file. Larger files return `413 RUN_DIFF_TOO_LARGE`.

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `ISE_ADMIN_UNAUTHORIZED` | 401 | Invalid or missing admin token |
| `DEV_RUN_NOT_FOUND` | 404 | Run not found in registry |
| `DEV_RUN_TRACE_NOT_FOUND` | 404 | trace.json not found for run |
| `DEV_RUN_IDL_NOT_FOUND` | 404 | idl_final.idl not found for run |
| `RUN_DIFF_TOO_LARGE` | 413 | IDL file exceeds 256KB limit |

---

## Cleanup on Boot (Fase 6.8)

Automatically run cleanup of dev-runs during engine startup.

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_DEV_RUNS_CLEANUP_ON_BOOT` | Enable cleanup on boot ("0" or "1") | `0` |
| `ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT` | Dry run mode on boot ("0" or "1") | `0` |

### Behavior

When `ENGINE_DEV_RUNS_CLEANUP_ON_BOOT=1`:

1. After bundle load and ledger verification, cleanup runs automatically
2. Follows the same TTL + MAX_RUNS policy as `POST /pipeline/build/cleanup`
3. If `ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT=1`, runs in dry-run mode (no deletions)
4. **Does NOT block startup** - if cleanup fails, logs error and continues
5. **Does NOT enter SAFE_MODE** - cleanup failures are non-fatal

### Log Events

| Event | Level | Description |
|-------|-------|-------------|
| `DEV_RUNS_CLEANUP_ON_BOOT_START` | INFO | Cleanup starting |
| `DEV_RUNS_CLEANUP_ON_BOOT_OK` | INFO | Cleanup completed successfully |
| `DEV_RUNS_CLEANUP_ON_BOOT_FAILED` | ERROR | Cleanup returned error result |
| `DEV_RUNS_CLEANUP_ON_BOOT_EXCEPTION` | ERROR | Cleanup raised exception |

### Example Configuration

```bash
# Enable cleanup on boot
ENGINE_DEV_RUNS_CLEANUP_ON_BOOT=1

# Optional: Run in dry-run mode first to verify
ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT=1

# Configure cleanup policy
ENGINE_DEV_RUNS_TTL_HOURS=24
ENGINE_DEV_RUNS_MAX_RUNS=200
```

### Example Log Output

```json
{"event": "DEV_RUNS_CLEANUP_ON_BOOT_START", "dry_run": false}
{"event": "DEV_RUNS_CLEANUP_ON_BOOT_OK", "dry_run": false, "deleted_count": 5, "ttl_expired_count": 3, "max_runs_exceeded_count": 2}
```

---

## EGE: Engine Governance Enforcement (Fase 8.1)

EGE provides deterministic drift detection between pinned bundle hashes and the actual CURRENT bundle, with a proposal-based workflow for resolving drift.

### Concepts

- **Drift**: Mismatch between expected (pinned) and observed (current) bundle/ledger hashes
- **Drift Status**:
  - `CLEAR`: Hashes match, system is in expected state
  - `ACTIVE`: Hashes mismatch, drift detected
  - `UNPINNED`: No hashes pinned in config (no enforcement)
- **Proposal**: A record to accept or block observed changes when drift is ACTIVE

### Institution Config v1.2

EGE adds three fields to institution config:

| Field | Type | Description |
|-------|------|-------------|
| `pinned_bundle_manifest_sha256` | string/null | Expected bundle manifest hash |
| `pinned_contract_ledger_sha256` | string/null | Expected contract ledger hash |
| `ege_enforce_drift` | bool | Enable drift enforcement (default: true) |

Hash format: `SHA256:<64 hex chars>` or plain 64 hex chars.

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /admin/ege/drift/check` | Check drift status |
| `POST /admin/ege/proposals` | Create proposal (if drift ACTIVE) |
| `GET /admin/ege/proposals` | List proposals |
| `POST /admin/ege/proposals/{id}/decide` | Decide proposal (accept/block) |

### Authentication

All EGE endpoints require admin authentication:
- `X-Admin-Key` header with valid key
- `X-Admin-Token` header (for DEFAULT institution only)
- `X-Institution-Id` header (required)

### Drift Check

```bash
curl -X POST http://localhost:8000/admin/ege/drift/check \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT"
```

Response:
```json
{
  "status": "ACTIVE",
  "state": {
    "schema_version": "1.0",
    "status": "ACTIVE",
    "checked_at": "2024-01-15T10:00:00Z",
    "expected_bundle_manifest_sha256": "SHA256:aaa...",
    "expected_contract_ledger_sha256": "SHA256:bbb...",
    "observed_bundle_manifest_sha256": "SHA256:ccc...",
    "observed_contract_ledger_sha256": "SHA256:ddd...",
    "bundle_manifest_mismatch": true,
    "contract_ledger_mismatch": true
  }
}
```

### Create Proposal

When drift is ACTIVE, create a proposal to resolve it:

```bash
curl -X POST http://localhost:8000/admin/ege/proposals \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT"
```

Response (201):
```json
{
  "proposal_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "OPEN",
  "created_at": "2024-01-15T10:00:00Z",
  "expected_bundle_manifest_sha256": "SHA256:aaa...",
  "observed_bundle_manifest_sha256": "SHA256:ccc...",
  "decision": null
}
```

### Decide Proposal

Accept or block the proposal:

```bash
# Accept - updates config with observed hashes, clears drift
curl -X POST http://localhost:8000/admin/ege/proposals/{id}/decide \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT" \
  -H "X-Actor-Id: admin-user" \
  -H "Content-Type: application/json" \
  -d '{"decision": "accept", "reason": "Approved deployment"}'

# Block - leaves drift ACTIVE
curl -X POST http://localhost:8000/admin/ege/proposals/{id}/decide \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT" \
  -H "X-Actor-Id: admin-user" \
  -H "Content-Type: application/json" \
  -d '{"decision": "block", "reason": "Unauthorized changes detected"}'
```

### Drift Enforcement Middleware

When `ege_enforce_drift=true` and drift status is `ACTIVE`:
- **POST, PUT, PATCH, DELETE** requests return `409 EGE_DRIFT_BLOCKED`
- **GET** requests are allowed
- **Admin endpoints** (`/admin/*`) bypass drift check
- **Health endpoint** (`/health`) bypasses drift check

### Workflow Example

```bash
# 1. Pin hashes after successful deploy
curl -X PUT http://localhost:8000/admin/institutions/DEFAULT/config \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT" \
  -H "Content-Type: application/json" \
  -d '{
    "pinned_bundle_manifest_sha256": "SHA256:abc123...",
    "pinned_contract_ledger_sha256": "SHA256:def456...",
    "ege_enforce_drift": true
  }'

# 2. Later, a new bundle is deployed externally...
# 3. Check drift
curl -X POST http://localhost:8000/admin/ege/drift/check \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT"
# Returns: {"status": "ACTIVE", ...}

# 4. Create proposal to review changes
curl -X POST http://localhost:8000/admin/ege/proposals \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT"
# Returns: {"proposal_id": "...", "status": "OPEN", ...}

# 5. Review and decide
curl -X POST http://localhost:8000/admin/ege/proposals/{id}/decide \
  -H "X-Admin-Token: your-secret-token" \
  -H "X-Institution-Id: DEFAULT" \
  -H "Content-Type: application/json" \
  -d '{"decision": "accept", "reason": "Verified new deployment"}'
# Config updated, drift cleared

# 6. Normal operations resume
```

### Ledger Events

| Event Type | Step | Description |
|------------|------|-------------|
| `EGE_DRIFT_CHECKED` | `EGE:drift.check` | Drift check performed |
| `EGE_DRIFT_BLOCKED` | `EGE:drift.block` | Request blocked by drift |
| `EGE_PROPOSAL_CREATED` | `EGE:proposal.create` | Proposal created |
| `EGE_PROPOSAL_DECIDED` | `EGE:proposal.decide` | Proposal accepted/blocked |

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `EGE_STATE_UNAVAILABLE` | 500 | Failed to check drift state |
| `EGE_REGISTRY_UNAVAILABLE` | 500 | Failed to access proposals registry |
| `EGE_DRIFT_BLOCKED` | 409 | Write blocked due to active drift |
| `EGE_NO_DRIFT_ACTIVE` | 409 | Cannot create proposal (no active drift) |
| `EGE_PROPOSAL_NOT_FOUND` | 404 | Proposal not found |
| `EGE_PROPOSAL_ALREADY_DECIDED` | 409 | Proposal already decided |
| `EGE_DECISION_INVALID` | 400 | Invalid decision (must be accept/block) |

### Storage

Per-institution files:
- `data/institutions/{id}/ege_drift_state.json` - Current drift state
- `data/institutions/{id}/ege_proposals.jsonl` - Append-only proposals registry

---

## Development

### Installation

```bash
pip install -e ".[dev]"
```

### Run API (development)

```bash
cd /home/bazari/engine
PYTHONPATH=src uvicorn engine.api.server:app --reload
```

### Run Tests

```bash
pytest -v
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_BUNDLE_PATH` | Path to bundle directory | `bundles/finance-pilot` |
| `ENGINE_LEDGER_PATH` | Path to audit ledger file | `audit_ledger.jsonl` |
| `ENGINE_STATE_PATH` | Path to state store file | `var/state_store.json` |
| `ENGINE_ENV` | Environment (development/production) | `development` |
| `ENGINE_LOG_FORMAT` | Log format (text/json) | `text` |

---

## Production (systemd)

### Prerequisites

- Python 3.11+
- User `bazari` exists
- sudo access for installation

### 1. Install Service

```bash
cd /home/bazari/engine
sudo ./ops/scripts/install_engine_service.sh
```

This will:
- Create `/etc/engine/` config directory
- Copy `engine.env.example` to `/etc/engine/engine.env`
- Create `/var/lib/engine/` data directory
- Install systemd service file
- Enable `engine.service`

### 2. Deploy Bundle

```bash
sudo ./ops/scripts/deploy_engine_prod.sh
```

This will:
1. Generate release ID (YYYYMMDD-HHMMSS UTC)
2. Copy bundle to staging
3. Verify bundle integrity (hashes, JSON/YAML syntax)
4. Move to releases directory
5. Update CURRENT symlink (save PREVIOUS)
6. Restart service
7. Run smoke test
8. **Auto-rollback** if smoke test fails

### 3. Bundle Lifecycle

The bundle system uses versioned releases with atomic activation:

```
/var/lib/engine/bundles/
├── releases/
│   ├── 20250115-143022/
│   │   └── finance-pilot/
│   └── 20250115-150000/
│       └── finance-pilot/
├── CURRENT -> releases/20250115-150000/finance-pilot
├── PREVIOUS -> releases/20250115-143022/finance-pilot
└── STAGING/  (temporary during deploy)
```

- **CURRENT**: Symlink to active release (used by engine)
- **PREVIOUS**: Symlink to previous release (for rollback)
- **releases/**: All deployed releases (timestamped)
- **STAGING/**: Temporary staging during deploy

### 4. List Releases

```bash
ls -1 /var/lib/engine/bundles/releases/
```

Show active release:

```bash
readlink -f /var/lib/engine/bundles/CURRENT
```

### 5. Manual Rollback

```bash
sudo ./ops/scripts/rollback_engine_bundle.sh
```

This will:
1. Set CURRENT to PREVIOUS
2. Restart service
3. Run smoke test
4. Report success/failure

### 6. Verify Bundle

Verify a bundle before or after deploy:

```bash
./ops/checks/verify_bundle.sh /path/to/bundle
```

Checks:
- `bundle.manifest.json` exists and is valid JSON
- All required contracts exist
- SHA256 hashes match
- JSON/YAML files are syntactically valid
- `contract_ledger.json` exists
- `openapi.yaml` exists (optional)

### 7. Manage Service

```bash
# Start
sudo systemctl start engine.service

# Stop
sudo systemctl stop engine.service

# Restart
sudo systemctl restart engine.service

# Status
sudo systemctl status engine.service

# View logs
sudo journalctl -u engine.service -f
```

### 8. Smoke Test

```bash
./ops/checks/smoke_test.sh
```

Tests:
1. Health check (GET /health → 200)
2. Create expense (POST /finance/expenses → 202)
3. Approve expense (POST /approvals/{id}/decide → 200, COMMITTED)
4. Verify ledger file exists
5. Verify state store file exists

### Production Paths

| Path | Purpose |
|------|---------|
| `/home/bazari/engine` | Application code |
| `/etc/engine/engine.env` | Configuration |
| `/var/lib/engine/bundles/CURRENT` | Active bundle (symlink) |
| `/var/lib/engine/bundles/PREVIOUS` | Previous bundle (symlink) |
| `/var/lib/engine/bundles/releases/` | All releases |
| `/var/lib/engine/audit_ledger.jsonl` | Audit ledger |
| `/var/lib/engine/state_store.json` | State store |

### Logs

Logs go to journald. View with:

```bash
# Follow logs
sudo journalctl -u engine.service -f

# Last 100 lines
sudo journalctl -u engine.service -n 100

# Since last hour
sudo journalctl -u engine.service --since "1 hour ago"
```

When `ENGINE_LOG_FORMAT=json`, logs are structured JSON with fields:
- `timestamp`: ISO8601 UTC
- `level`: INFO/ERROR/etc
- `event`: Log message
- `method`: HTTP method (for requests)
- `path`: Request path
- `tenant_id`: Tenant ID (if present)
- `actor_id`: Actor ID (if present)
- `status_code`: HTTP status code
