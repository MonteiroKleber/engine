# Artefatos Canônicos — Especificação

**Data:** 2026-01-18
**Versão:** 1.1
**Etapa:** 02 — IDL Canônica e Artefatos

---

## 1. Visão Geral

Este documento define as regras de canonicalização e geração de artefatos verificáveis do Libervia Engine. Artefatos canônicos garantem:

1. **Determinismo:** Mesma entrada → mesma saída (builds reproduzíveis)
2. **Verificabilidade:** Hashes permitem prova offline de integridade
3. **Auditabilidade:** Registro imutável de quem gerou o quê e quando

---

## 2. Regras de Canonicalização

### 2.1 JSON Canônico

Todos os arquivos JSON gerados pelo ISE compiler seguem estas regras:

| Regra | Implementação | Evidência |
|-------|---------------|-----------|
| **Chaves ordenadas** | `sort_keys=True` | [manifest.py:101](../../../../src/engine/ise/manifest.py) |
| **Encoding UTF-8** | `.encode("utf-8")` | [manifest.py:30](../../../../src/engine/ise/manifest.py) |
| **Indentação 2 espaços** | `indent=2` | [compiler.py:148](../../../../src/engine/ise/compiler.py) |
| **Sem trailing whitespace** | `json.dumps()` padrão | — |

**Exemplo de serialização canônica:**

```python
json.dumps(data, indent=2, sort_keys=True)
```

### 2.2 Timestamps

| Regra | Implementação |
|-------|---------------|
| **Timezone:** UTC obrigatório | `datetime.now(timezone.utc)` |
| **Formato:** ISO 8601 | `.isoformat()` |
| **Exemplo:** | `2026-01-17T14:30:00+00:00` |

**Evidência:** [manifest.py:71](../../../../src/engine/ise/manifest.py)

### 2.3 Hashing

| Regra | Implementação |
|-------|---------------|
| **Algoritmo:** SHA-256 | `hashlib.sha256()` |
| **Input (string):** UTF-8 encoded bytes | `.encode("utf-8")` |
| **Input (arquivo):** raw bytes | `open(path, "rb")` |
| **Output:** Hex lowercase | `.hexdigest()` |

**Funções canônicas no ISE compiler:**

```python
# src/engine/ise/manifest.py
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_str(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))
```

**Funções canônicas no loader:**

```python
# src/engine/loader/verify_hashes.py
def compute_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()
```

**Evidência:** [verify_hashes.py:7](../../../../src/engine/loader/verify_hashes.py)

---

## 3. Artefatos de Bundle

### 3.1 bundle.manifest.json (Real v8.1.1)

O loader consome o manifest no seguinte formato:

```json
{
  "name": "finance-pilot",
  "version": "1.0.0",
  "description": "Finance pilot bundle for Libervia Engine",
  "contracts": [
    {
      "file": "rbac.json",
      "sha256": "SHA256:5a75d6bdef3e08d8dce63dac535aa9fd5ff489f1efbfcaf7bd5f2d52806d2439",
      "required": true
    },
    {
      "file": "openapi.yaml",
      "sha256": "SHA256:c96f851f30cf93204efe2bbce5c820737d0a1a65c0deb4b50de65e1610042fc5",
      "required": false
    }
  ]
}
```

**Campos:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do bundle |
| `version` | string | Versão semver |
| `description` | string | Descrição do bundle |
| `contracts` | array | Lista de contratos |
| `contracts[].file` | string | Nome do arquivo |
| `contracts[].sha256` | string | Hash no formato `SHA256:<hex>` ou `<hex>` |
| `contracts[].required` | boolean | Se `true` e arquivo ausente → SAFE_MODE |

**Evidência:** [load_bundle.py:351](../../../../src/engine/loader/load_bundle.py)

**Hash Format:** O loader normaliza hashes removendo o prefixo `SHA256:` se presente.

**Evidência:** [verify_hashes.py:23](../../../../src/engine/loader/verify_hashes.py)

### 3.2 contract_ledger.json (Real v8.1.1)

**Estado atual:** placeholder sem funcionalidade de prova offline.

```json
{
  "version": "1.0.0",
  "name": "contract_ledger",
  "description": "Ledger contract for finance-pilot bundle",
  "entries": []
}
```

**GAP:** O `contract_ledger.json` atual **não** contém:
- Hashes dos contratos
- IDL hash
- Manifest hash
- Audit trail com eventos
- Prova offline de integridade

O schema atual não permite verificação offline de que o bundle não foi alterado após compilação.

### 3.3 contract_ledger.json (Proposto — pós-mudança)

Schema desejado para prova offline:

```json
{
  "ledger_version": "1.0",
  "ledger_id": "a1b2c3d4e5f6g7h8",
  "bundle_name": "finance-pilot",
  "bundle_version": "1.0.0",
  "manifest_hash": "sha256...",
  "idl_hash": "sha256...",
  "created_at": "2026-01-17T14:30:00+00:00",
  "contracts": [
    {"contract_name": "rbac.json", "content_hash": "sha256...", "status": "active"}
  ],
  "audit_trail": [
    {"event": "bundle_compiled", "timestamp": "2026-01-17T14:30:00+00:00", "details": {}}
  ]
}
```

**Status:** PROPOSTO — não implementado no código atual.

---

## 4. Verificação de Integridade no Boot

### 4.1 Fluxo do Loader (v8.1.1)

```
1. Ler bundle.manifest.json
   - Se ausente → SAFE_MODE (BUNDLE_MANIFEST_MISSING)
   - Se JSON inválido → SAFE_MODE (BUNDLE_MANIFEST_INVALID_JSON)

2. Para cada contrato em manifest.contracts[]:
   - Se required=true e arquivo ausente → SAFE_MODE (BUNDLE_CONTRACT_MISSING)
   - Se sha256 presente e não bate → SAFE_MODE (BUNDLE_CONTRACT_HASH_MISMATCH)
   - Se .json e JSON inválido → SAFE_MODE (BUNDLE_CONTRACT_INVALID_JSON)

3. Carregar políticas operacionais (rbac, sod, approvals, invariants)

4. Carregar contratos institucionais (policies, mandates, autonomy)
   - Comportamento atual: se ausente → allow-all
   - Comportamento canônico MVP: se ausente → SAFE_MODE
```

**Evidência:** [load_bundle.py:636](../../../../src/engine/loader/load_bundle.py)

### 4.2 Função de Verificação de Hash

```python
def verify_contract_hash(file_path: Path, expected_hash: str) -> bool:
    actual_hash = compute_sha256(file_path)
    expected_normalized = normalize_hash(expected_hash)
    return actual_hash.lower() == expected_normalized

def normalize_hash(hash_value: str) -> str:
    if hash_value.upper().startswith("SHA256:"):
        return hash_value[7:].lower()
    return hash_value.lower()
```

**Evidência:** [verify_hashes.py:37](../../../../src/engine/loader/verify_hashes.py)

---

## 5. Prova Offline

### 5.1 Estado Atual (v8.1.1)

**GAP:** Não é possível fazer prova offline completa porque:

1. `contract_ledger.json` é placeholder vazio (`entries: []`)
2. Não há IDL hash para verificar origem
3. Não há manifest hash para verificar integridade do manifest

**O que É possível verificar offline:**

```bash
# Verificar hash de contrato individual contra manifest
sha256sum bundles/finance-pilot/rbac.json
# Comparar manualmente com contracts[].sha256 no manifest
```

### 5.2 Verificação Offline Completa (Proposto)

Quando `contract_ledger.json` implementar o schema completo:

```bash
# 1. Verificar que manifest não foi alterado
sha256sum bundles/finance-pilot/bundle.manifest.json
# Comparar com manifest_hash no contract_ledger.json

# 2. Verificar cada contrato contra hashes no manifest
for file in $(jq -r '.contracts[].file' bundle.manifest.json); do
  sha256sum "bundles/finance-pilot/$file"
done

# 3. Verificar IDL fonte (se disponível)
sha256sum source.idl.json
# Comparar com idl_hash no contract_ledger.json
```

---

## 6. Artefatos de Auditoria Runtime

### 6.1 Ledger de Eventos (audit_ledger.jsonl)

O runtime mantém um ledger de eventos append-only:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `event_type` | string | Tipo do evento |
| `timestamp` | ISO8601 | Momento do evento |
| `tenant_id` | string | Identificador do tenant |
| `actor_id` | string | Ator que executou |
| `case_id` | string | ID do caso |
| `hash` | SHA256 | Hash do evento |
| `prev_hash` | SHA256 | Hash do evento anterior |

**Verificação de chain:**
- Cada evento contém `hash = SHA256(payload + prev_hash)`
- Chain é verificada no boot
- Chain corrompida → SAFE_MODE

**Evidência:** [ledger.py](../../../../src/engine/core/ledger.py)

### 6.2 Eventos de Governança

| Evento | Emitido por | Conteúdo |
|--------|-------------|----------|
| `POLICY_EVALUATED` | policy.py | decision, rule_id, field_path |
| `MANDATE_EVALUATED` | mandates.py | decision, mandate_id, actor |
| `AUTONOMY_EVALUATED` | autonomy.py | decision, current_level, required_level |
| `RBAC_EVALUATED` | rbac.py | decision, role, resource |
| `SOD_EVALUATED` | sod.py | decision, rule_id |

---

## 7. Builds Determinísticos

### 7.1 Garantias do ISE Compiler

| Propriedade | Garantia |
|-------------|----------|
| **Mesma IDL → Mesmos contratos** | Sim (sort_keys=True, UTF-8) |
| **Mesma IDL → Mesmo bundle_hash** | Não (timestamp varia) |
| **Chaves ordenadas** | Garantido |
| **Encoding consistente** | Garantido (UTF-8) |

### 7.2 Variáveis Não-Determinísticas

| Variável | Localização | Impacto |
|----------|-------------|---------|
| `created_at` | manifest (ISE) | Varia por compilação |
| `timestamp` | audit_trail (ISE) | Varia por compilação |

**Nota:** O bundle `finance-pilot` atual foi criado manualmente, não pelo ISE compiler.

---

## 8. Fluxo de Compilação (ISE)

O ISE compiler gera bundles a partir de IDL:

```
IDL (JSON) → parse_idl() → emit_*() → contratos → manifest → bundle/
```

**Diferença importante:**

- **ISE compiler** (`src/engine/ise/`) gera manifest no formato com `bundle_hash`, `contracts{}` como dict
- **Loader** (`src/engine/loader/`) consome manifest no formato com `name`, `contracts[]` como array

**GAP potencial:** Formato de manifest gerado pelo ISE pode diferir do consumido pelo loader.

---

## 9. Resumo de GAPs

| Item | Estado Atual | Impacto | Prioridade |
|------|--------------|---------|------------|
| contract_ledger.json | placeholder vazio | Sem prova offline | Média |
| Formato manifest ISE vs loader | potencialmente divergentes | Bundles gerados podem não carregar | Alta (verificar) |
| policies/mandates/autonomy ausentes | allow-all | Viola princípio de governança | **CRÍTICA** |

---

## 10. Checklist de Verificação

### 10.1 Para Bundle (v8.1.1)

- [x] `bundle.manifest.json` presente
- [x] `bundle.manifest.json` tem formato `{name, version, contracts[]}`
- [x] Cada `contracts[].file` existe se `required=true`
- [x] Cada `contracts[].sha256` bate com conteúdo se presente
- [ ] `policies.json` presente (**GAP**)
- [ ] `mandates.json` presente (**GAP**)
- [ ] `autonomy.json` presente (**GAP**)

### 10.2 Para Prova Offline

- [ ] `contract_ledger.json` contém hashes de contratos (**GAP**)
- [ ] `contract_ledger.json` contém `idl_hash` (**GAP**)
- [ ] `contract_ledger.json` contém `manifest_hash` (**GAP**)

---

## 11. Referências

- [IDL v1.x Specification](idl-v1.md) — Estrutura da IDL e schemas
- [Gap Report v8.1.1](../01-baseline/gap-report.md) — Risco crítico #1
- [load_bundle.py](../../../../src/engine/loader/load_bundle.py) — Loader de bundles
- [verify_hashes.py](../../../../src/engine/loader/verify_hashes.py) — Verificação de hashes
- [manifest.py](../../../../src/engine/ise/manifest.py) — Geração de manifest (ISE)

---

**Status:** ESPECIFICAÇÃO ATIVA
**Data:** 2026-01-18
