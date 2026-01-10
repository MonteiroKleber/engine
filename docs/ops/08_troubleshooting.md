# Troubleshooting

This guide covers the 10 most common issues and their solutions.

## Quick Reference: Blocked Reasons

| Blocked Reason | Component | Meaning |
|----------------|-----------|---------|
| `GATE1_FAILED` | Pipeline | Draft structural validation failed |
| `GATE2_BLOCKED` | Pipeline | Draft to IDL compilation blocked |
| `SRS_BLOCKED_QUESTIONS` | Pipeline | SRS has blocking questions |
| `IR_EMPTY` | Pipeline | Intermediate representation is empty |
| `IR_VALIDATION_FAILED` | Pipeline | IR schema validation failed |
| `POLICY_FAILED` | Pipeline | General policy violation |
| `CONTRACTS_POLICY_FAILED` | Pipeline | Contract generation policy failed |
| `CONTRACT_GATE_FAILED` | Pipeline | Contract ledger integrity failure |
| `PLAN_POLICY_FAILED` | Pipeline | Plan generation policy failed |
| `PATCH_SECURITY` | Pipeline | Security violation in patch |
| `PATCH_FAILED` | Pipeline | Patch application failed |
| `BUILD_FAILED` | Build | Compilation failed |
| `FIX_LOOP_EXHAUSTED` | Build | Fix attempts exceeded limit |
| `DOCKER_UP_FAILED` | Release | Docker compose up failed |
| `SMOKE_FAILED` | Release | Smoke tests failed |
| `READINESS_FAILED` | Release | Container readiness timeout |
| `OPEN_QUESTIONS_BLOCKING` | Wizard | Session has blocking questions |
| `SCHEMA_INVALID` | Wizard | Session/CR schema invalid |
| `INCOMPLETE_STEPS` | Wizard | Required steps incomplete |
| `APPROVAL_REQUIRED` | Episode | Episode needs approval |
| `APPROVAL_INVALID` | Episode | Invalid approval data |
| `IMPACT_OUT_OF_SCOPE` | CR | Change outside declared scope |
| `IMPACT_TOO_BROAD` | CR | Change affects too many components |
| `IMPACT_FORBIDDEN_PATH` | CR | Change affects protected path |
| `CR_PREVIOUS_MISMATCH` | CR | CR.previous_episode_id mismatch |

## Quick Reference: Error Codes

| Error Code | Description |
|------------|-------------|
| `EPISODE_NOT_FOUND` | Episode does not exist |
| `EPISODE_IMMUTABLE` | Cannot modify finalized episode |
| `EPISODE_STORE_ERROR` | General episode store error |
| `CR_NOT_FOUND` | Change request file not found |
| `CR_SCHEMA_INVALID` | Change request schema invalid |
| `CR_PREVIOUS_MISMATCH` | CR previous_episode_id mismatch |
| `PREVIOUS_EPISODE_NOT_FOUND` | Previous episode not found |
| `WIZARD_SESSION_NOT_FOUND` | Wizard session not found |
| `WIZARD_SCHEMA_INVALID` | Wizard session schema invalid |
| `WIZARD_BLUEPRINT_NOT_FOUND` | Blueprint not in registry |
| `WIZARD_REGISTRY_INTEGRITY_ERROR` | Registry integrity check failed |
| `AUDITPACK_SECURITY_BLOCKED` | Forbidden file in episode |
| `AUDITPACK_VALIDATION_ERROR` | AuditPack validation failed |
| `AUDITPACK_ERROR` | General auditpack error |

---

## Issue 1: Pipeline Blocked with GATE1_FAILED

**Symptoms:**
```
Pipeline falhou!
Erros:
  - GATE1_FAILED: Draft structural validation failed
```

**Cause:** IDL Draft JSON does not match schema.

**Solution:**

1. Check draft schema:
```bash
python -c "
import json
import jsonschema
with open('schemas/idl_draft.v1.json') as f:
    schema = json.load(f)
with open('your_draft.json') as f:
    draft = json.load(f)
jsonschema.validate(draft, schema)
"
```

2. Common draft issues:
   - Missing `schema_version: "idl_draft.v1"`
   - Missing required `project_name` or `domain`
   - Invalid field types

3. Regenerate draft from wizard:
```bash
python main.py wizard export <session_id>
```

---

## Issue 2: Build Failed with Fix Loop Exhausted

**Symptoms:**
```
Pipeline falhou!
  - BUILD_FAILED
  - FIX_LOOP_EXHAUSTED
Fix Loop tentou corrigir:
  - Tentativas: 3
  - Razao do abort: max_attempts_exceeded
```

**Cause:** Build errors persist after 3 fix attempts.

**Solution:**

1. Check build errors in runlog:
```bash
cat demo_store/<project>/runlog.json | jq .build_errors
```

2. Check preserved failed repo:
```bash
ls /home/bazari/generated/_failed/<project>*
cd /home/bazari/generated/_failed/<project>*

# Try manual build
cd backend && mvn compile
```

3. Common build issues:
   - Missing imports
   - Type mismatches
   - Invalid entity relationships

4. Fix input specification and re-run:
```bash
python main.py --project <project> --input "..." --release
```

---

## Issue 3: Docker Compose Up Failed

**Symptoms:**
```
Release:
  - Docker Compose: FAILED
  - DOCKER_UP_FAILED
```

**Cause:** Docker containers failed to start.

**Solution:**

1. Check Docker is running:
```bash
docker info
```

2. Check container logs:
```bash
cd /home/bazari/generated/<project>
docker compose logs
```

3. Check if ports are in use:
```bash
lsof -i :8080
lsof -i :5432
lsof -i :3000
```

4. Clean up and retry:
```bash
docker compose down -v
docker compose up -d
docker compose ps
```

5. Check Dockerfile issues:
```bash
docker compose build --no-cache backend
```

---

## Issue 4: Episode Not Found

**Symptoms:**
```
ERROR: Episode not found: exec-abc123
Error Code: EPISODE_NOT_FOUND
```

**Cause:** Episode ID does not exist or wrong base path.

**Solution:**

1. List existing episodes:
```bash
ls -la .engine/episodes/
```

2. Check episode ID spelling:
```bash
python -m episodes.episodes_cli list
```

3. Verify base path:
```bash
python -m episodes.episodes_cli list --base-path /path/to/project
```

---

## Issue 5: CR Previous Episode Mismatch

**Symptoms:**
```
ERROR: CR.previous_episode_id mismatch
  INTEGRITY: CR.previous_episode_id 'exec-wrong' does not match argument 'exec-abc123'
Error Code: CR_PREVIOUS_MISMATCH
```

**Cause:** CR file has different `previous_episode_id` than CLI argument.

**Solution:**

1. Check CR file:
```bash
cat change_request.json | jq .previous_episode_id
```

2. Update CR to match:
```json
{
  "previous_episode_id": "exec-abc123"
}
```

3. Or update CLI argument to match CR.

---

## Issue 6: Wizard Session Not Found

**Symptoms:**
```
ERROR: Session not found: wiz-abc123
Error Code: WIZARD_SESSION_NOT_FOUND
```

**Cause:** Session ID invalid or session deleted.

**Solution:**

1. List sessions:
```bash
ls -la .engine/wizard/sessions/
```

2. Check session ID format:
   - Should be `wiz-` followed by 8 hex characters
   - Example: `wiz-a1b2c3d4`

3. Create new session if needed:
```bash
python main.py wizard start --project MyProject --domain healthcare
```

---

## Issue 7: AuditPack Security Blocked

**Symptoms:**
```
ERROR: SECURITY: Forbidden path pattern '.env' found in: input/.env
Error Code: AUDITPACK_SECURITY_BLOCKED
```

**Cause:** Episode contains files matching security-sensitive patterns.

**Solution:**

1. Identify forbidden file:
```bash
ls -la .engine/episodes/<id>/input/
```

2. Remove forbidden files from episode (before finalization):
```bash
rm .engine/episodes/<id>/input/.env
```

3. Regenerate episode without sensitive files.

4. Forbidden patterns include:
   - `.env`, `.env.local`
   - `secrets/`, `credentials/`
   - `private_key`, `.pem`, `.key`
   - `api_key`, `token`, `password`

---

## Issue 8: Blueprint Not Found in Registry

**Symptoms:**
```
ERROR: Blueprint not found in registry: custom-v1
Error Code: WIZARD_BLUEPRINT_NOT_FOUND
```

**Cause:** Blueprint ID not registered.

**Solution:**

1. List available blueprints:
```bash
cat blueprints/registry/index.json | jq '.blueprints[].blueprint_id'
```

2. Check blueprint ID spelling.

3. If blueprint exists, verify registry:
```bash
python -c "from blueprints.registry_v1 import verify_registry; verify_registry()"
```

4. Export without blueprint:
```bash
python main.py wizard export <session_id>
```

---

## Issue 9: Readiness Timeout

**Symptoms:**
```
Release:
  - READINESS_FAILED
Smoke Tests: FAILED
```

**Cause:** Containers didn't become healthy in time.

**Solution:**

1. Increase timeout (default: 240s):
```bash
# Check container health
docker compose ps
docker inspect --format='{{json .State.Health}}' <container>
```

2. Check container logs:
```bash
docker compose logs backend --tail 100
docker compose logs frontend --tail 100
```

3. Common issues:
   - Database connection failure
   - Port binding conflicts
   - Missing environment variables

4. Manual healthcheck:
```bash
curl http://localhost:8080/actuator/health
curl http://localhost:3000/
```

5. Restart with fresh state:
```bash
docker compose down -v
docker compose up -d
```

---

## Issue 10: Registry Integrity Error

**Symptoms:**
```
ERROR: Registry integrity check failed
  INTEGRITY: Blueprint hash mismatch: petclinic-v1
Error Code: WIZARD_REGISTRY_INTEGRITY_ERROR
```

**Cause:** Blueprint file was modified without updating registry.

**Solution:**

1. Verify registry:
```bash
python -c "
from blueprints.registry_v1 import verify_registry
try:
    verify_registry()
    print('Registry OK')
except Exception as e:
    print(f'ERROR: {e}')
"
```

2. Rebuild registry (if you have permission):
```bash
python -c "
from blueprints.registry_v1 import rebuild_registry
rebuild_registry()
"
```

3. Restore original blueprint from backup:
```bash
git checkout blueprints/registry/
```

---

## General Debugging Tips

### Enable Verbose Output

```bash
python main.py --project test --input "..." 2>&1 | tee output.log
```

### Check Runlog

```bash
cat demo_store/<project>/runlog.json | jq .
```

### Check Telemetry

```bash
# Telemetry events go to stdout
python main.py ... 2>&1 | grep '"event"'
```

### Validate Schemas

```bash
python -c "
import json
import jsonschema

with open('schemas/runlog.v1.json') as f:
    schema = json.load(f)
with open('demo_store/myproject/runlog.json') as f:
    data = json.load(f)
jsonschema.validate(data, schema)
print('Valid!')
"
```

### Run Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_episodes.py -v

# Run with output
python -m pytest tests/ -v -s
```

### Check Disk Space

```bash
df -h /home/bazari
du -sh /home/bazari/generated/*
```

### Docker Cleanup

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# Full cleanup
docker system prune -a
```

## Getting Help

1. Check runlog for detailed errors
2. Review telemetry output
3. Check schema documentation in `/home/bazari/engine/schemas/`
4. Run tests to verify installation
5. Check GitHub Issues for known problems
