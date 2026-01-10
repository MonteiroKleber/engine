# Running the Engine

The engine pipeline transforms input specifications into complete, deployable systems.

## Input Modes

| Mode | Description | Input Format |
|------|-------------|--------------|
| `natural` | Free-text description | Plain text |
| `draft` | IDL Draft JSON | `idl_draft.v1` JSON file |
| `idl` | IDL v1 specification | IDL JSON file |
| `auto` | Auto-detect format | Any of the above |

## Execution Modes

| Mode | Flag | Description |
|------|------|-------------|
| Skip Build | `--skip-build` | Generate artifacts only (no compilation) |
| Build | (default) | Generate and compile |
| Release | `--release` | Full pipeline with docker compose and smoke tests |

## Basic Commands

### Generate Artifacts Only

```bash
cd /home/bazari/engine

python main.py \
  --project myproject \
  --input "Sistema de cadastro de clientes com nome, email e telefone" \
  --skip-build
```

Output:
```
Bazari Engine v1.0.0 - Gerando projeto: myproject
Store: /home/bazari/engine/demo_store
Input Mode: auto

Modo skip-build: apenas artefatos serao gerados

Pipeline concluido com sucesso!

Artefatos gerados (sem build):
  - SRS: v1
  - IR: v1
  - OAS: v1
  - RBAC: v1
  - PLAN: v1
```

### Generate with Build

```bash
python main.py \
  --project myproject \
  --input "Sistema de cadastro de clientes"
```

### Full Release Mode

```bash
python main.py \
  --project myproject \
  --input "Sistema de cadastro de clientes" \
  --release
```

## Using IDL Draft Input

### From Wizard Export

```bash
python main.py \
  --project clinica \
  --input .engine/wizard/sessions/wiz-abc123/export/idl_draft.json \
  --input-mode draft \
  --release
```

### From File Path

```bash
python main.py \
  --project myproject \
  --input /path/to/my_spec.json \
  --input-mode draft
```

## Using IDL Input

```bash
python main.py \
  --project myproject \
  --input /path/to/spec.idl \
  --input-mode idl \
  --release
```

## IDL-Only Processing

Process IDL without running the full pipeline:

```bash
python main.py \
  --project test \
  --input spec.idl \
  --input-mode idl \
  --idl-only
```

Output:
```
IDL Processing: SUCCESS

Input Mode Resolved: idl
Detection Reason: explicit_mode

IDL Schema Version: idl.v1
IDL Content Hash: a1b2c3d4e5f6...

Files:
  - JSON: demo_store/test/idl.json
  - Markdown: demo_store/test/idl.md
```

## Output Structure

### Store Directory

```
/home/bazari/engine/demo_store/<project>/
├── srs.json           # Software Requirements Specification
├── ir.json            # Intermediate Representation
├── oas.json           # OpenAPI Specification
├── rbac.json          # Role-Based Access Control
├── plan.json          # Execution Plan
├── runlog.json        # Execution Runlog
├── contracts/         # Generated contracts
│   ├── contracts.json
│   └── contracts.md
└── idl.json           # IDL (if --idl-only)
```

### Generated Project

```
/home/bazari/generated/<project>/
├── backend/           # Spring Boot backend
│   ├── src/
│   ├── pom.xml
│   └── Dockerfile
├── frontend/          # React/Vite frontend
│   ├── src/
│   ├── package.json
│   └── Dockerfile
├── database/          # SQL migrations
│   └── init.sql
└── docker-compose.yml
```

## Release Report

In release mode, the engine generates a release report:

```bash
python main.py --project demo --input "..." --release
```

Output includes:

```
==============================================================
RELEASE REPORT
==============================================================

Status: SUCCESS
Engine: Bazari Engine v1.0.0

System Summary:
  - Requirements: 5
  - Entities: 3
  - API Operations: 12
  - Tasks: 8
  - Patches: 15

Artifacts:
  - SRS: v1
  - IR: v1
  - OpenAPI: v1
  - RBAC: v1
  - PLAN: v1

Build:
  - Status: OK
  - Fix Attempts: 1
  - Fixes Applied: 2

Release:
  - Docker Compose: OK
  - Services: postgres, backend, frontend
  - Smoke Tests: OK (5/5)

Paths:
  - Repository: /home/bazari/generated/demo
  - Store: /home/bazari/engine/demo_store/demo

Commands:
  Start:   docker compose up -d
  Stop:    docker compose down
  Logs:    docker compose logs -f
  Status:  docker compose ps

==============================================================
```

## Accessing Generated System

After successful release:

```bash
cd /home/bazari/generated/myproject

# Start services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop services
docker compose down
```

Default ports:
- Frontend: http://localhost:3000 (or 5173)
- Backend: http://localhost:8080
- Database: localhost:5432

## Episode Creation

Each successful execution creates an episode in `.engine/episodes/`:

```
.engine/episodes/<execution_id>/
├── manifest.json      # Episode manifest
├── runlog.json        # Execution runlog
├── contracts/         # Generated contracts
├── input/             # Input files
└── artifacts/         # Build artifacts
```

See [Approvals and Episodes](05_approvals_and_episodes.md) for episode management.

## Runlog Structure

The runlog captures execution details:

```json
{
  "schema_version": "runlog.v1",
  "execution_id": "exec-abc123",
  "final_status": "success",
  "blocked_reason": null,
  "duration_ms": 45230,
  "errors": [],
  "error_codes": [],
  "metrics": {
    "input_mode": "draft",
    "artifacts_generated": 5,
    "patches_applied": 15
  }
}
```

## Pipeline Stages

The engine executes these stages:

1. **Intake**: Parse and validate input
2. **SRS Generation**: Create requirements specification
3. **IR Generation**: Create intermediate representation
4. **Contract Generation**: Generate API contracts (OpenAPI, RBAC)
5. **Plan Generation**: Create execution plan
6. **Code Generation**: Generate application code
7. **Build**: Compile backend and frontend
8. **Release** (if `--release`): Docker compose and smoke tests

## Fix Loop

The engine includes an automatic fix loop for build errors:

- Maximum 3 fix attempts
- Applies targeted fixes based on error type
- Records fix history in runlog

```json
{
  "fix_attempts": 2,
  "fixes_applied": [
    {"type": "missing_import", "file": "User.java"},
    {"type": "type_mismatch", "file": "UserController.java"}
  ]
}
```

## Telemetry

Pipeline execution emits telemetry events to stdout:

```json
{"execution_id":"exec-123","project":"demo","stage":"intake","event":"start","ts_iso":"..."}
{"execution_id":"exec-123","project":"demo","stage":"intake","event":"end","duration_ms":150}
```

Disable telemetry:
```bash
export TELEMETRY_ENABLED=false
```

## Running via Docker

Using the distribution:

```bash
docker exec bazari-engine python main.py \
  --project myproject \
  --input "Sistema de cadastro" \
  --skip-build
```

## Next Steps

After running the engine:
1. [Manage episodes and approvals](05_approvals_and_episodes.md)
2. [Create change requests](06_change_requests.md)
