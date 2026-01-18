# Hello Institution

Documentação executável do fluxo end-to-end do Libervia Engine.

---

## PT-BR

### Visão Geral

O Libervia Engine transforma políticas em linguagem natural em bundles executáveis. O fluxo completo é:

```
Texto (NL) → SIR → Draft IDL → Gaps/Answers → Final IDL → Bundle → Deploy
```

### Fluxo Principal

#### 1. Build (Sandbox)

O endpoint `/pipeline/build` compila texto em bundle, sem deploy.

**Primeira chamada (pode retornar NEEDS_ANSWERS):**

```bash
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Funcionários podem criar despesas. Gerentes aprovam despesas.",
    "bundle_name": "finance-pilot",
    "answers": null
  }'
```

**Resposta NEEDS_ANSWERS:**

```json
{
  "status": "NEEDS_ANSWERS",
  "bundle_name": "finance-pilot",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
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
          "question_text": "A criação de despesa requer aprovação?"
        }
      ]
    }
  ],
  "sir": {...},
  "draft_idl": {...}
}
```

**Segunda chamada (com answers):**

```bash
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Funcionários podem criar despesas. Gerentes aprovam despesas.",
    "bundle_name": "finance-pilot",
    "answers": [
      {"question_id": "q-123", "value": true}
    ]
  }'
```

**Resposta BUILT:**

```json
{
  "status": "BUILT",
  "bundle_name": "finance-pilot",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_path": "bundles/dev-runs/550e8400-.../finance-pilot",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "hash_idl_final": "ghi789...",
  "bundle_hash": "jkl012..."
}
```

#### 2. Export (ZIP Determinístico)

Após BUILT, exporte o bundle para ZIP:

```bash
curl -X POST http://localhost:8000/pipeline/build/export \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "bundle_name": "finance-pilot"
  }'
```

**Resposta:**

```json
{
  "status": "EXPORTED",
  "zip_path": "bundles/dev-runs/550e8400-.../exports/finance-pilot.zip",
  "zip_sha256": "abc123def456...",
  "download_url": "/pipeline/build/download?run_id=550e8400-...&bundle_name=finance-pilot"
}
```

**ZIP Determinístico:**
- Mesma entrada = mesmo SHA256
- Arquivos ordenados alfabeticamente
- Timestamp fixo: 1980-01-01 00:00:00
- Permissões fixas: 0644
- Compressão DEFLATED

#### 3. Download

```bash
curl -O "http://localhost:8000/pipeline/build/download?run_id=550e8400-e29b-41d4-a716-446655440000&bundle_name=finance-pilot"
```

Retorna `application/zip` com header `Content-Disposition: attachment; filename="finance-pilot.zip"`.

#### 4. Deploy (Admin)

Para deploy em produção, use `/pipeline/deploy` com token admin:

```bash
curl -X POST http://localhost:8000/pipeline/deploy \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: seu-token-secreto" \
  -d '{
    "text": "Funcionários podem criar despesas. Gerentes aprovam despesas.",
    "bundle_name": "finance-pilot",
    "target": "production",
    "answers": [
      {"question_id": "q-123", "value": true}
    ]
  }'
```

**Resposta DEPLOYED:**

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

### Endpoints Admin

Requerem header `X-Admin-Token` com valor de `ENGINE_ISE_ADMIN_TOKEN`.

#### Run Detail

```bash
curl -X GET "http://localhost:8000/pipeline/build/runs/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Admin-Token: seu-token-secreto"
```

**Resposta:**

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

#### Diff entre Runs

Compara `idl_final.idl` de dois runs (unified diff):

```bash
curl -X GET "http://localhost:8000/pipeline/build/diff?run_a=run-001&run_b=run-002" \
  -H "X-Admin-Token: seu-token-secreto"
```

**Resposta:**

```json
{
  "success": true,
  "run_a": "run-001",
  "run_b": "run-002",
  "diff": "--- run-a/run-001/idl_final.idl\n+++ run-b/run-002/idl_final.idl\n@@ -1,3 +1,3 @@\n...",
  "is_identical": false,
  "size_a": 1024,
  "size_b": 1152
}
```

Limite: 256KB por arquivo IDL (retorna 413 se exceder).

#### Cleanup Manual

```bash
# Dry run (simula)
curl -X POST http://localhost:8000/pipeline/build/cleanup \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: seu-token-secreto" \
  -d '{"dry_run": true}'

# Cleanup real
curl -X POST http://localhost:8000/pipeline/build/cleanup \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: seu-token-secreto" \
  -d '{"dry_run": false}'
```

**Resposta:**

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

### Cleanup Automático no Boot

Configure via variáveis de ambiente:

| Variável | Descrição | Default |
|----------|-----------|---------|
| `ENGINE_DEV_RUNS_CLEANUP_ON_BOOT` | Habilita cleanup no boot ("0" ou "1") | `0` |
| `ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT` | Modo dry run no boot ("0" ou "1") | `0` |
| `ENGINE_DEV_RUNS_TTL_HOURS` | TTL em horas | `24` |
| `ENGINE_DEV_RUNS_MAX_RUNS` | Máximo de runs ativos | `200` |

**Comportamento:**
- Roda após load do bundle e verificação do ledger
- Não bloqueia startup em caso de falha
- Não entra em SAFE_MODE em caso de falha
- Loga eventos JSON: `DEV_RUNS_CLEANUP_ON_BOOT_START`, `DEV_RUNS_CLEANUP_ON_BOOT_OK`, `DEV_RUNS_CLEANUP_ON_BOOT_FAILED`

### Checklist "O que é Pronto"

- [ ] `/pipeline/build` retorna `BUILT` com `bundle_hash`
- [ ] `/pipeline/build/export` retorna `zip_sha256`
- [ ] ZIP baixado tem mesmo SHA256 do export
- [ ] `/pipeline/build/runs/{run_id}` retorna `trace` com todos os hashes
- [ ] `/pipeline/build/diff` gera unified diff correto
- [ ] `/pipeline/build/cleanup` deleta runs conforme TTL e MAX_RUNS
- [ ] Cleanup no boot executa sem bloquear startup
- [ ] `/pipeline/deploy` retorna `DEPLOYED` com `release_id`
- [ ] Health check retorna 200 com `mode: ACTIVE`

---

## EN-US

### Overview

The Libervia Engine transforms natural language policies into executable bundles. The complete flow is:

```
Text (NL) → SIR → Draft IDL → Gaps/Answers → Final IDL → Bundle → Deploy
```

### Main Flow

#### 1. Build (Sandbox)

The `/pipeline/build` endpoint compiles text into a bundle, without deploying.

**First call (may return NEEDS_ANSWERS):**

```bash
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "answers": null
  }'
```

**NEEDS_ANSWERS Response:**

```json
{
  "status": "NEEDS_ANSWERS",
  "bundle_name": "finance-pilot",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
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

**Second call (with answers):**

```bash
curl -X POST http://localhost:8000/pipeline/build \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "answers": [
      {"question_id": "q-123", "value": true}
    ]
  }'
```

**BUILT Response:**

```json
{
  "status": "BUILT",
  "bundle_name": "finance-pilot",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_path": "bundles/dev-runs/550e8400-.../finance-pilot",
  "hash_sir": "abc123...",
  "hash_draft": "def456...",
  "hash_idl_final": "ghi789...",
  "bundle_hash": "jkl012..."
}
```

#### 2. Export (Deterministic ZIP)

After BUILT, export the bundle to ZIP:

```bash
curl -X POST http://localhost:8000/pipeline/build/export \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "bundle_name": "finance-pilot"
  }'
```

**Response:**

```json
{
  "status": "EXPORTED",
  "zip_path": "bundles/dev-runs/550e8400-.../exports/finance-pilot.zip",
  "zip_sha256": "abc123def456...",
  "download_url": "/pipeline/build/download?run_id=550e8400-...&bundle_name=finance-pilot"
}
```

**Deterministic ZIP:**
- Same input = same SHA256
- Files sorted alphabetically
- Fixed timestamp: 1980-01-01 00:00:00
- Fixed permissions: 0644
- DEFLATED compression

#### 3. Download

```bash
curl -O "http://localhost:8000/pipeline/build/download?run_id=550e8400-e29b-41d4-a716-446655440000&bundle_name=finance-pilot"
```

Returns `application/zip` with header `Content-Disposition: attachment; filename="finance-pilot.zip"`.

#### 4. Deploy (Admin)

For production deployment, use `/pipeline/deploy` with admin token:

```bash
curl -X POST http://localhost:8000/pipeline/deploy \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-token" \
  -d '{
    "text": "Employees can create expenses. Managers approve expenses.",
    "bundle_name": "finance-pilot",
    "target": "production",
    "answers": [
      {"question_id": "q-123", "value": true}
    ]
  }'
```

**DEPLOYED Response:**

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

### Admin Endpoints

Require `X-Admin-Token` header with value from `ENGINE_ISE_ADMIN_TOKEN`.

#### Run Detail

```bash
curl -X GET "http://localhost:8000/pipeline/build/runs/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Admin-Token: your-secret-token"
```

**Response:**

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

#### Diff Between Runs

Compares `idl_final.idl` from two runs (unified diff):

```bash
curl -X GET "http://localhost:8000/pipeline/build/diff?run_a=run-001&run_b=run-002" \
  -H "X-Admin-Token: your-secret-token"
```

**Response:**

```json
{
  "success": true,
  "run_a": "run-001",
  "run_b": "run-002",
  "diff": "--- run-a/run-001/idl_final.idl\n+++ run-b/run-002/idl_final.idl\n@@ -1,3 +1,3 @@\n...",
  "is_identical": false,
  "size_a": 1024,
  "size_b": 1152
}
```

Limit: 256KB per IDL file (returns 413 if exceeded).

#### Manual Cleanup

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

**Response:**

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

### Automatic Cleanup on Boot

Configure via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_DEV_RUNS_CLEANUP_ON_BOOT` | Enable cleanup on boot ("0" or "1") | `0` |
| `ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT` | Dry run mode on boot ("0" or "1") | `0` |
| `ENGINE_DEV_RUNS_TTL_HOURS` | TTL in hours | `24` |
| `ENGINE_DEV_RUNS_MAX_RUNS` | Maximum active runs | `200` |

**Behavior:**
- Runs after bundle load and ledger verification
- Does not block startup on failure
- Does not enter SAFE_MODE on failure
- Logs JSON events: `DEV_RUNS_CLEANUP_ON_BOOT_START`, `DEV_RUNS_CLEANUP_ON_BOOT_OK`, `DEV_RUNS_CLEANUP_ON_BOOT_FAILED`

### "Definition of Done" Checklist

- [ ] `/pipeline/build` returns `BUILT` with `bundle_hash`
- [ ] `/pipeline/build/export` returns `zip_sha256`
- [ ] Downloaded ZIP has same SHA256 as export
- [ ] `/pipeline/build/runs/{run_id}` returns `trace` with all hashes
- [ ] `/pipeline/build/diff` generates correct unified diff
- [ ] `/pipeline/build/cleanup` deletes runs per TTL and MAX_RUNS
- [ ] Cleanup on boot executes without blocking startup
- [ ] `/pipeline/deploy` returns `DEPLOYED` with `release_id`
- [ ] Health check returns 200 with `mode: ACTIVE`
