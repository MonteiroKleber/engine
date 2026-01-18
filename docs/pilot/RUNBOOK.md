# Runbook — Libervia Engine Pilot

## PT-BR

### 1. Startup

```bash
# Verificar preflight
./ops/checks/preflight.sh

# Iniciar engine
uvicorn engine.api.server:app --host 0.0.0.0 --port 8000

# Verificar health
curl http://localhost:8000/health
```

### 2. Verificar Modo de Operação

```bash
# ACTIVE mode (normal)
curl -s http://localhost:8000/health | jq '.mode'
# Esperado: "ACTIVE"

# SAFE_MODE (degradado)
curl -s http://localhost:8000/health | jq '.'
# Esperado: {"status": "degraded", "mode": "SAFE_MODE", "reason_code": "...", "details": [...]}
```

### 3. Diagnóstico de SAFE_MODE

| reason_code | Causa | Ação |
|-------------|-------|------|
| `BUNDLE_MANIFEST_MISSING` | bundle.manifest.json não encontrado | Verificar ENGINE_BUNDLE_PATH |
| `BUNDLE_MANIFEST_INVALID_JSON` | JSON inválido no manifest | Corrigir manifest |
| `BUNDLE_CONTRACT_MISSING` | Contrato obrigatório ausente | Adicionar arquivo faltante |
| `BUNDLE_CONTRACT_HASH_MISMATCH` | Hash do contrato não confere | Regenerar hashes no manifest |
| `LEDGER_TAMPER_DETECTED` | Ledger corrompido ou adulterado | **CRÍTICO**: Investigar, não modificar ledger |
| `LEDGER_VERIFY_UNAVAILABLE` | Erro de I/O ao ler ledger | Verificar permissões e disco |

### 4. Recuperação de SAFE_MODE

```bash
# 1. Identificar causa
curl -s http://localhost:8000/health | jq '.reason_code, .details'

# 2. Corrigir problema (ex: bundle path)
export ENGINE_BUNDLE_PATH=/path/to/valid/bundle

# 3. Reiniciar engine
systemctl restart engine

# 4. Verificar recuperação
curl -s http://localhost:8000/health | jq '.mode'
```

### 5. Verificar Integridade do Ledger

```bash
# Contar eventos
wc -l var/audit_ledger.jsonl

# Verificar último evento
tail -1 var/audit_ledger.jsonl | jq '.'

# Verificar hash chain (manual)
python -c "
from engine.core.ledger import verify_ledger_file
from pathlib import Path
result = verify_ledger_file(Path('var/audit_ledger.jsonl'))
print(f'OK: {result.ok}, Code: {result.code}, Message: {result.message}')
"
```

### 6. Logs

```bash
# Logs estruturados em JSON
journalctl -u engine -f --output=cat | jq '.'

# Filtrar por request_id
journalctl -u engine --output=cat | jq 'select(.request_id == "UUID-HERE")'

# Filtrar por event_type
journalctl -u engine --output=cat | jq 'select(.event_type == "CASE_COMMITTED")'
```

### 7. Métricas Básicas

```bash
# Eventos por tipo
cat var/audit_ledger.jsonl | jq -r '.event_type' | sort | uniq -c

# Eventos por tenant
cat var/audit_ledger.jsonl | jq -r '.tenant_id' | sort | uniq -c

# Eventos nas últimas 24h
cat var/audit_ledger.jsonl | jq -r 'select(.timestamp > "2024-01-01T00:00:00") | .event_type' | sort | uniq -c
```

---

## EN

### 1. Startup

```bash
# Run preflight check
./ops/checks/preflight.sh

# Start engine
uvicorn engine.api.server:app --host 0.0.0.0 --port 8000

# Check health
curl http://localhost:8000/health
```

### 2. Check Operation Mode

```bash
# ACTIVE mode (normal)
curl -s http://localhost:8000/health | jq '.mode'
# Expected: "ACTIVE"

# SAFE_MODE (degraded)
curl -s http://localhost:8000/health | jq '.'
# Expected: {"status": "degraded", "mode": "SAFE_MODE", "reason_code": "...", "details": [...]}
```

### 3. SAFE_MODE Diagnosis

| reason_code | Cause | Action |
|-------------|-------|--------|
| `BUNDLE_MANIFEST_MISSING` | bundle.manifest.json not found | Check ENGINE_BUNDLE_PATH |
| `BUNDLE_MANIFEST_INVALID_JSON` | Invalid JSON in manifest | Fix manifest |
| `BUNDLE_CONTRACT_MISSING` | Required contract missing | Add missing file |
| `BUNDLE_CONTRACT_HASH_MISMATCH` | Contract hash mismatch | Regenerate hashes in manifest |
| `LEDGER_TAMPER_DETECTED` | Ledger corrupted or tampered | **CRITICAL**: Investigate, do not modify ledger |
| `LEDGER_VERIFY_UNAVAILABLE` | I/O error reading ledger | Check permissions and disk |

### 4. SAFE_MODE Recovery

```bash
# 1. Identify cause
curl -s http://localhost:8000/health | jq '.reason_code, .details'

# 2. Fix problem (e.g., bundle path)
export ENGINE_BUNDLE_PATH=/path/to/valid/bundle

# 3. Restart engine
systemctl restart engine

# 4. Verify recovery
curl -s http://localhost:8000/health | jq '.mode'
```

### 5. Verify Ledger Integrity

```bash
# Count events
wc -l var/audit_ledger.jsonl

# Check last event
tail -1 var/audit_ledger.jsonl | jq '.'

# Verify hash chain (manual)
python -c "
from engine.core.ledger import verify_ledger_file
from pathlib import Path
result = verify_ledger_file(Path('var/audit_ledger.jsonl'))
print(f'OK: {result.ok}, Code: {result.code}, Message: {result.message}')
"
```

### 6. Logs

```bash
# Structured JSON logs
journalctl -u engine -f --output=cat | jq '.'

# Filter by request_id
journalctl -u engine --output=cat | jq 'select(.request_id == "UUID-HERE")'

# Filter by event_type
journalctl -u engine --output=cat | jq 'select(.event_type == "CASE_COMMITTED")'
```

### 7. Basic Metrics

```bash
# Events by type
cat var/audit_ledger.jsonl | jq -r '.event_type' | sort | uniq -c

# Events by tenant
cat var/audit_ledger.jsonl | jq -r '.tenant_id' | sort | uniq -c

# Events in last 24h
cat var/audit_ledger.jsonl | jq -r 'select(.timestamp > "2024-01-01T00:00:00") | .event_type' | sort | uniq -c
```
