# Procedimento de Prova Offline: DSL/IR → Bundle

**Etapa 2.3 — PROMPT 2.3.2 Implementação**
**Data**: 2026-01-18
**Status**: ✅ IMPLEMENTADO

---

## 1. Visão Geral

Este documento define o **procedimento canônico** para verificação offline da integridade de um bundle Libervia e seu vínculo com a decisão institucional (DSL v1.2.2).

### 1.1 Objetivo

Provar, **sem executar o runtime**, que:

1. O bundle em produção é íntegro (hashes verificáveis)
2. O bundle corresponde a uma decisão institucional específica (`source_idl_sha256`)
3. Todos os contratos listados no manifest existem e são válidos

### 1.2 Cadeia de Hashes

```
DSL v1.2.2 (texto UTF-8)
    │
    ├── SHA256 ─────────────────────────────────────────────────────────┐
    │                                                                   │
    ▼                                                                   │
IRCS v1 (ir.json)                                                       │
    │   ├── source_idl_sha256: "<hash>"  ◄──────────────────────────────┘
    │   └── ir_version: "ircs.v1"
    │
    ▼
ISE Compiler (compile_from_ircs)
    │
    ▼
Bundle/
    ├── bundle.manifest.json
    │   ├── contracts[]: [{file, sha256, required}]
    │   └── _metadata.bundle_hash
    │
    ├── contract_ledger.json
    │   ├── source_idl_sha256: "<hash>"  ◄─── Âncora da decisão
    │   ├── manifest_hash: "<hash>"
    │   └── contracts[]: [{contract_name, content_hash, status}]
    │
    ├── rbac.json
    ├── approvals.json
    ├── workflows.json
    ├── sod.json
    ├── invariants.json
    ├── policies.json
    ├── mandates.json
    ├── autonomy.json
    └── openapi.yaml (opcional)
```

---

## 2. Artefatos e Schemas

### 2.1 bundle.manifest.json

Schema do loader (ABI estável):

```json
{
  "name": "string",
  "version": "string",
  "description": "string",
  "contracts": [
    {
      "file": "string",
      "sha256": "SHA256:<hex64>",
      "required": true|false
    }
  ],
  "_metadata": {
    "manifest_version": "1.0",
    "bundle_hash": "<hex64>",
    "system_name": "string",
    "mode": "single|multi",
    "created_at": "ISO8601"
  }
}
```

### 2.2 contract_ledger.json

Schema canônico emitido pelo ISE (após Etapa 2.2):

```json
{
  "ledger_version": "1.0",
  "ledger_id": "<hex16>",
  "bundle_name": "string",
  "bundle_version": "string",
  "manifest_hash": "<hex64>",
  "idl_hash": "<hex64>",
  "source_idl_sha256": "<hex64>",
  "created_at": "ISO8601",
  "contracts": [
    {
      "contract_name": "string",
      "content_hash": "<hex64>",
      "status": "active"
    }
  ],
  "audit_trail": [
    {
      "event": "bundle_compiled",
      "timestamp": "ISO8601",
      "details": {}
    }
  ]
}
```

**Campo crítico**: `source_idl_sha256` é a âncora canônica da decisão institucional.

---

## 3. Procedimento Canônico de Verificação

### 3.1 Entrada

```
bundle_path/
├── bundle.manifest.json
├── contract_ledger.json
└── [contracts...]
```

### 3.2 Algoritmo

```
FUNCTION verify_bundle_offline(bundle_path: Path) -> Result:

  # Passo 1: Ler e validar manifest
  manifest_path = bundle_path / "bundle.manifest.json"
  IF NOT exists(manifest_path):
    RETURN FAIL("MANIFEST_MISSING", "bundle.manifest.json not found")

  TRY:
    manifest = json.load(manifest_path)
  CATCH JSONDecodeError:
    RETURN FAIL("MANIFEST_INVALID_JSON", "Invalid JSON in manifest")

  # Passo 2: Verificar hash de cada contrato no manifest
  FOR contract IN manifest.contracts:
    contract_path = bundle_path / contract.file

    IF NOT exists(contract_path):
      IF contract.required:
        RETURN FAIL("CONTRACT_MISSING", f"Required contract missing: {contract.file}")
      CONTINUE

    actual_hash = SHA256(read_bytes(contract_path))
    expected_hash = normalize_hash(contract.sha256)  # Remove "SHA256:" prefix

    IF actual_hash != expected_hash:
      RETURN FAIL("CONTRACT_HASH_MISMATCH", f"Hash mismatch: {contract.file}")

  # Passo 3: Ler e validar ledger
  ledger_path = bundle_path / "contract_ledger.json"
  IF NOT exists(ledger_path):
    RETURN FAIL("LEDGER_MISSING", "contract_ledger.json not found")

  TRY:
    ledger = json.load(ledger_path)
  CATCH JSONDecodeError:
    RETURN FAIL("LEDGER_INVALID_JSON", "Invalid JSON in ledger")

  # Passo 4: Verificar manifest_hash no ledger
  manifest_bytes = read_bytes(manifest_path)
  computed_manifest_hash = SHA256(manifest_bytes)

  IF ledger.manifest_hash != computed_manifest_hash:
    RETURN FAIL("MANIFEST_HASH_MISMATCH",
                f"Ledger manifest_hash mismatch: expected {computed_manifest_hash}, got {ledger.manifest_hash}")

  # Passo 5: Verificar consistência contracts[] entre manifest e ledger
  manifest_contracts = {c.file: normalize_hash(c.sha256) for c IN manifest.contracts}
  ledger_contracts = {c.contract_name: c.content_hash for c IN ledger.contracts}

  FOR file, hash IN manifest_contracts:
    IF file NOT IN ledger_contracts:
      RETURN FAIL("LEDGER_CONTRACT_MISSING", f"Contract {file} in manifest but not in ledger")
    IF hash != ledger_contracts[file]:
      RETURN FAIL("LEDGER_CONTRACT_HASH_MISMATCH", f"Hash mismatch for {file} between manifest and ledger")

  # Passo 6: Verificar source_idl_sha256
  source_idl_sha256 = ledger.get("source_idl_sha256")

  IF source_idl_sha256 IS NULL:
    RETURN FAIL("SOURCE_IDL_MISSING", "source_idl_sha256 not found in ledger")

  IF NOT is_valid_sha256_hex(source_idl_sha256):
    RETURN FAIL("SOURCE_IDL_INVALID", f"Invalid SHA256 format: {source_idl_sha256}")

  # Passo 7: Sucesso
  RETURN PASS({
    "bundle_name": manifest.name,
    "version": manifest.version,
    "source_idl_sha256": source_idl_sha256,
    "contracts_verified": len(manifest.contracts),
    "manifest_hash": computed_manifest_hash
  })
```

### 3.3 Funções Auxiliares

```python
def normalize_hash(hash_value: str) -> str:
    """Remove SHA256: prefix if present, lowercase."""
    if hash_value.upper().startswith("SHA256:"):
        return hash_value[7:].lower()
    return hash_value.lower()

def is_valid_sha256_hex(value: str) -> bool:
    """Check if value is valid 64-char hex string."""
    if len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False
```

---

## 4. Códigos de Erro

| Código | Descrição | Severidade |
|--------|-----------|------------|
| `MANIFEST_MISSING` | bundle.manifest.json não encontrado | FATAL |
| `MANIFEST_INVALID_JSON` | JSON inválido no manifest | FATAL |
| `CONTRACT_MISSING` | Contrato required não existe | FATAL |
| `CONTRACT_HASH_MISMATCH` | Hash do contrato não bate | FATAL |
| `LEDGER_MISSING` | contract_ledger.json não encontrado | FATAL |
| `LEDGER_INVALID_JSON` | JSON inválido no ledger | FATAL |
| `MANIFEST_HASH_MISMATCH` | manifest_hash do ledger diverge | FATAL |
| `LEDGER_CONTRACT_MISSING` | Contrato do manifest ausente no ledger | FATAL |
| `LEDGER_CONTRACT_HASH_MISMATCH` | Hash diverge entre manifest e ledger | FATAL |
| `SOURCE_IDL_MISSING` | source_idl_sha256 ausente no ledger | FATAL |
| `SOURCE_IDL_INVALID` | source_idl_sha256 formato inválido | FATAL |

---

## 5. Exemplos de Uso

### 5.1 CLI Implementado

```bash
# Verificar bundle (output human-readable)
python -m engine.proof verify /path/to/bundle

# Output de sucesso
PASS: Bundle integrity verified
  Bundle: finance-pilot
  Version: 1.0.0
  Source IDL SHA256: 0cd2dd153f383f36c4727cbb6e884d631edcb99ef924181b07339c2b83f138f9
  Contracts verified: 9
  Manifest hash: 26947100c421569e...

# Output de falha
FAIL: PROOF_CONTRACT_HASH_MISMATCH
  Hash mismatch for rbac.json
  file: rbac.json
  expected: 014f5140c804f01d...
  actual: deadbeef12345678...

# JSON output para CI/automação
python -m engine.proof verify /path/to/bundle --json

# Exit codes:
#   0 = PASS (verificação OK)
#   1 = FAIL (verificação falhou)
```

### 5.2 Verificação Programática

```python
from engine.proof import verify_bundle_offline

result = verify_bundle_offline(Path("/path/to/bundle"))

if result.passed:
    print(f"Bundle integrity verified")
    print(f"Source IDL: {result.source_idl_sha256}")
else:
    print(f"Verification failed: {result.error_code}")
    print(f"Details: {result.error_message}")
```

### 5.3 Verificação com DSL Original

Para verificar vínculo completo (DSL → Bundle):

```bash
# 1. Calcular hash do DSL original
sha256sum finance.idl
# Output: 0cd2dd153f383f36c4727cbb6e884d631edcb99ef924181b07339c2b83f138f9  finance.idl

# 2. Verificar bundle
python -m engine.proof verify /path/to/bundle
# Output: source_idl_sha256: 0cd2dd153f383f36c4727cbb6e884d631edcb99ef924181b07339c2b83f138f9

# 3. Comparar (match = integridade comprovada)
```

---

## 6. Integração com Código Existente

### 6.1 Utilitários Existentes

| Módulo | Função | Reutilizável |
|--------|--------|--------------|
| `engine.loader.verify_hashes` | `compute_sha256(path)` | ✅ Sim |
| `engine.loader.verify_hashes` | `normalize_hash(hash)` | ✅ Sim |
| `engine.loader.verify_hashes` | `verify_contract_hash(path, expected)` | ✅ Sim |
| `engine.pipeline.hashes` | `compute_hash(data)` | ✅ Sim (para dicts) |

### 6.2 Módulo Implementado

```
src/engine/proof/
├── __init__.py        # Exports públicos
├── verify.py          # verify_bundle_offline(), ProofResult
├── errors.py          # Códigos PROOF_*
└── __main__.py        # CLI: python -m engine.proof verify
```

### 6.3 Segurança de Path (Anti-Traversal)

A implementação inclui proteção contra path traversal:
- Rejeita paths absolutos (`/etc/passwd`)
- Rejeita paths com `..` (`../secret.json`)
- Resolve symlinks e verifica que o path final está dentro do bundle

---

## 7. Testes

### 7.1 Casos Positivos

1. **Bundle válido**: Todos os hashes batem, source_idl_sha256 presente
2. **Bundle com optional faltando**: openapi.yaml ausente mas required=false
3. **Pipeline completo**: DSL → IRCS → Bundle → verify PASS

### 7.2 Casos Negativos

1. **Manifest ausente**: MANIFEST_MISSING
2. **Manifest JSON inválido**: MANIFEST_INVALID_JSON
3. **Contrato required ausente**: CONTRACT_MISSING
4. **Hash de contrato alterado**: CONTRACT_HASH_MISMATCH
5. **Ledger ausente**: LEDGER_MISSING
6. **manifest_hash divergente**: MANIFEST_HASH_MISMATCH
7. **source_idl_sha256 ausente**: SOURCE_IDL_MISSING
8. **source_idl_sha256 formato inválido**: SOURCE_IDL_INVALID

---

## 8. Observações de Segurança

1. **Hashes são SHA256**: Resistente a colisões, padrão da indústria.
2. **Normalização**: Aceita `SHA256:` prefix para compatibilidade, compara lowercase.
3. **Determinismo**: Mesma entrada sempre produz mesmo hash (JSON sort_keys).
4. **Offline**: Não requer runtime, banco de dados, ou rede.
5. **Path Traversal**: Proteção contra tentativas de escape do bundle directory.

---

## 9. Implementação

### 9.1 Arquivos Criados

| Arquivo | LOC | Descrição |
|---------|-----|-----------|
| `src/engine/proof/__init__.py` | ~40 | Exports públicos |
| `src/engine/proof/errors.py` | ~30 | Códigos de erro PROOF_* |
| `src/engine/proof/verify.py` | ~280 | Lógica de verificação |
| `src/engine/proof/__main__.py` | ~70 | CLI entry point |
| `tests/test_offline_proof.py` | ~350 | 32 testes |

### 9.2 Correção no ISE Compiler

O `contract_ledger.json` foi corrigido para usar `SHA256(manifest_json)` como `manifest_hash` em vez do `bundle_hash` (hash of hashes), conforme a spec:

```python
# Antes: manifest_hash=bundle_hash (hash of contract hashes)
# Depois: manifest_hash=sha256_str(manifest_json) (SHA256 do arquivo)
```

Arquivos modificados:
- `src/engine/ise/compiler.py` (4 locais)

### 9.3 Testes

```bash
# Rodar testes
cd /home/bazari/engine
PYTHONPATH=src python -m pytest tests/test_offline_proof.py -v

# Resultado: 32 passed
```

---

## 10. Definition of Done

- [x] CLI `python -m engine.proof verify <bundle_path>` funcional
- [x] Verifica hashes de todos os contracts
- [x] Verifica `manifest_hash` no ledger
- [x] Cross-check completo manifest ↔ ledger
- [x] Valida `source_idl_sha256` presente e formato correto
- [x] Proteção anti path-traversal
- [x] Exit code 0 para PASS, 1 para FAIL
- [x] Output JSON para CI (`--json`)
- [x] 32 testes cobrindo PASS e todos os FAILs
- [x] Documentação atualizada
