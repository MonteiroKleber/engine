# Onboarding Wizard

The Wizard is an interactive tool for creating structured project specifications that can be exported as IDL Draft files.

## Commands

| Command | Description |
|---------|-------------|
| `start` | Create a new wizard session |
| `resume` | Update an existing session |
| `export` | Export session as IDL Draft v1 |

## Starting a Session

### Basic Usage

```bash
python main.py wizard start --project MyProject --domain healthcare
```

### Full Options

```bash
python main.py wizard start \
  --project "PatientManagement" \
  --domain "healthcare" \
  --objective "Sistema de gerenciamento de pacientes"
```

### Output

```
Session created: wiz-a1b2c3d4
Files:
  - Session: .engine/wizard/sessions/wiz-a1b2c3d4/session.json
  - Runlog: .engine/wizard/sessions/wiz-a1b2c3d4/wizard_runlog.json
```

## Session Structure

Each session contains:

```json
{
  "schema_version": "wizard_session.v1",
  "session_id": "wiz-a1b2c3d4",
  "project_name": "MyProject",
  "domain": "healthcare",
  "objective": "...",
  "steps": {
    "actors": { ... },
    "entities": { ... },
    "usecases": { ... },
    "rules": { ... }
  },
  "open_questions": [],
  "evidence": [],
  "blueprint_ref": null
}
```

### Session Steps

| Step | Purpose | Key Fields |
|------|---------|------------|
| `actors` | System users | `actors_list` |
| `entities` | Data entities | `entities_list` |
| `usecases` | Use cases | `usecases_list` |
| `rules` | Business rules | `rules_list` |

## Resuming a Session

Update session fields with the `resume` command.

### Update a Field

```bash
python main.py wizard resume <session_id> \
  --set 'actors.actors_list=["Admin","Medico","Paciente"]'
```

### Update Multiple Fields

```bash
python main.py wizard resume <session_id> \
  --set 'actors.actors_list=["Admin","User"]' \
  --set 'entities.entities_list=["Paciente","Consulta","Medico"]'
```

### Field Format

Format: `step_id.field_id=value`

Values are parsed as JSON. String values can be plain text:

```bash
# JSON array
--set 'actors.actors_list=["A","B"]'

# Plain string
--set 'actors.notes=Just a note'
```

## Exporting to IDL Draft

Export the session as an IDL Draft v1 file.

### Basic Export

```bash
python main.py wizard export <session_id>
```

### Export with Blueprint

Apply a blueprint during export:

```bash
python main.py wizard export <session_id> --blueprint-id petclinic-v1
```

### Export Output

```
Export successful: wiz-a1b2c3d4
Files:
  - JSON: .engine/wizard/sessions/wiz-a1b2c3d4/export/idl_draft.json
  - Markdown: .engine/wizard/sessions/wiz-a1b2c3d4/export/idl_draft.md
Blueprint: petclinic-v1 (applied)
```

## Complete Workflow Example

### Step 1: Start Session

```bash
cd /home/bazari/engine

python main.py wizard start \
  --project "Clinica" \
  --domain "healthcare"
```

Output:
```
Session created: wiz-abc12345
```

### Step 2: Define Actors

```bash
python main.py wizard resume wiz-abc12345 \
  --set 'actors.actors_list=["Administrador","Medico","Recepcionista","Paciente"]'
```

### Step 3: Define Entities

```bash
python main.py wizard resume wiz-abc12345 \
  --set 'entities.entities_list=["Paciente","Medico","Consulta","Prontuario","Agenda"]'
```

### Step 4: Define Use Cases

```bash
python main.py wizard resume wiz-abc12345 \
  --set 'usecases.usecases_list=["AgendarConsulta","CadastrarPaciente","RegistrarConsulta","ConsultarProntuario"]'
```

### Step 5: Define Business Rules

```bash
python main.py wizard resume wiz-abc12345 \
  --set 'rules.rules_list=["PacienteDeveSerMaior18Anos","ConsultaNaoPodeSerNoPassado"]'
```

### Step 6: Export

```bash
python main.py wizard export wiz-abc12345
```

### Step 7: Use with Engine

```bash
python main.py \
  --project clinica \
  --input .engine/wizard/sessions/wiz-abc12345/export/idl_draft.json \
  --input-mode draft \
  --skip-build
```

## Session Files

Sessions are stored in `.engine/wizard/sessions/<session_id>/`:

```
.engine/wizard/sessions/wiz-abc12345/
├── session.json        # Session data
├── wizard_runlog.json  # Execution runlog
├── events.jsonl        # Event log (append-only)
└── export/             # Export directory (after export)
    ├── idl_draft.json  # IDL Draft JSON
    └── idl_draft.md    # Human-readable markdown
```

## Session Runlog

The wizard runlog tracks execution:

```json
{
  "schema_version": "wizard_runlog.v1",
  "session_id": "wiz-abc12345",
  "command": "export",
  "final_status": "success",
  "blocked_reason": null,
  "duration_ms": 125.5,
  "counts": {
    "steps_total": 4,
    "steps_complete": 4,
    "open_questions_count": 0,
    "blocking_questions_count": 0
  },
  "flags": {
    "all_steps_complete": true,
    "has_blocking_questions": false,
    "export_ready": true
  }
}
```

## Blocked Status

A session can be blocked if:

| Blocked Reason | Cause |
|----------------|-------|
| `OPEN_QUESTIONS_BLOCKING` | Session has blocking questions |
| `SCHEMA_INVALID` | Session data is invalid |
| `INCOMPLETE_STEPS` | Required steps not complete |

Check session status:

```bash
python main.py wizard resume <session_id>
# Review runlog for blocked_reason
```

## Listing Sessions

Sessions are stored in `.engine/wizard/sessions/`. List them:

```bash
ls -la .engine/wizard/sessions/
```

## Deleting a Session

```bash
rm -rf .engine/wizard/sessions/<session_id>
```

## Next Steps

After exporting:
1. [Apply a blueprint](03_blueprints.md) (optional)
2. [Run the engine](04_running_engine.md)
