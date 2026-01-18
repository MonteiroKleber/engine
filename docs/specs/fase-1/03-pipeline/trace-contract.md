# Trace Contract — Especificação

**Data:** 2026-01-18
**Versão:** 1.0
**Etapa:** 03 — Pipeline NL → Canonical IDL → Bundle

---

## 1. Visão Geral

Este documento define o contrato mínimo para `trace.json` — o artefato de rastreabilidade que conecta a IDL fonte ao bundle compilado.

---

## 2. Propósito do trace.json

O `trace.json` permite:

1. **Rastreabilidade:** Conectar bundle → IDL final → draft → SIR → texto NL original
2. **Verificação offline:** Provar que um bundle foi gerado a partir de uma IDL específica
3. **Auditoria:** Registrar hashes em cada estágio do pipeline

---

## 3. Schema do trace.json (v8.1.1)

```json
{
  "run_id": "UUID v4",
  "bundle_name": "string",
  "mode": "single|multi",
  "sir_sha256": "SHA256 hex",
  "draft_sha256": "SHA256 hex",
  "final_idl_sha256": "SHA256 hex",
  "bundle_manifest_sha256": "SHA256 hex",
  "contract_ledger_sha256": "SHA256 hex",
  "policy_count": 0,
  "policy_gap_count": 0,
  "has_policy_gaps": false,
  "departments": ["dept_id", ...]  // apenas em mode=multi
}
```

**Evidência:** [orchestrator.py:727-743](../../../../src/engine/pipeline/orchestrator.py)

---

## 4. Campos Obrigatórios

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `run_id` | string (UUID v4) | Identificador único do build |
| `bundle_name` | string | Nome do bundle |
| `mode` | string | `"single"` ou `"multi"` |
| `sir_sha256` | string (64 hex) | Hash do SIR extraído |
| `draft_sha256` | string (64 hex) | Hash do Draft IDL |
| `final_idl_sha256` | string (64 hex) | Hash da IDL final canonizada |
| `bundle_manifest_sha256` | string (64 hex) | Hash do bundle.manifest.json |
| `contract_ledger_sha256` | string (64 hex) | Hash do contract_ledger.json |

---

## 5. Campos Opcionais

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `policy_count` | int | Número de policies na IDL |
| `policy_gap_count` | int | Número de policy gaps detectados |
| `has_policy_gaps` | bool | Se tem policy gaps |
| `departments` | array[string] | Lista de dept_ids (apenas mode=multi) |

---

## 6. Cálculo de Hashes

### 6.1 Função de Hash

```python
def compute_hash(data: Any) -> str:
    if isinstance(data, (dict, list)):
        # Canonical JSON serialization
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        content = json_str.encode("utf-8")
    elif isinstance(data, str):
        content = data.encode("utf-8")
    elif isinstance(data, bytes):
        content = data
    else:
        content = str(data).encode("utf-8")
    return hashlib.sha256(content).hexdigest()
```

**Evidência:** [hashes.py:8-28](../../../../src/engine/pipeline/hashes.py)

### 6.2 Canonicalização JSON

Para dicts e lists, a serialização usa:
- `sort_keys=True` — chaves ordenadas alfabeticamente
- `separators=(",", ":")` — sem espaços extras

Isso garante que o mesmo conteúdo sempre produz o mesmo hash.

---

## 7. Localização dos Artefatos

### 7.1 Estrutura de Diretórios

```
dev-runs/
└── <run_id>/
    ├── trace.json              ← Rastreabilidade
    ├── idl_final.idl           ← IDL canonizada
    ├── <bundle_name>/          ← Bundle compilado
    │   ├── bundle.manifest.json
    │   ├── contract_ledger.json
    │   ├── rbac.json
    │   ├── workflows.json
    │   ├── approvals.json
    │   ├── sod.json
    │   ├── invariants.json
    │   ├── openapi.yaml
    │   ├── policies.json       ← Se presente na IDL
    │   ├── mandates.json       ← GAP: não emitido
    │   └── autonomy.json       ← GAP: não emitido
    └── exports/
        └── <bundle_name>.zip   ← Após export
```

**Evidência:** [run_detail.py:108-111](../../../../src/engine/pipeline/run_detail.py)

### 7.2 Namespacing por Institution

Quando `institution_id` é fornecido:

```
data/institutions/<institution_id>/
└── dev-runs/
    └── <run_id>/
        └── ...
```

**Evidência:** [registry.py:49-59](../../../../src/engine/pipeline/registry.py)

---

## 8. Verificação de Integridade

### 8.1 Verificação Manual

```bash
# 1. Verificar hash do idl_final.idl
cat dev-runs/<run_id>/idl_final.idl | \
  python3 -c "import sys,json,hashlib; d=json.load(sys.stdin); print(hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest())"

# Comparar com final_idl_sha256 no trace.json

# 2. Verificar hash do manifest
cat dev-runs/<run_id>/<bundle_name>/bundle.manifest.json | \
  python3 -c "import sys,hashlib; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())"

# Comparar com bundle_manifest_sha256 no trace.json
```

### 8.2 Chain de Verificação

```
trace.json.sir_sha256          ──► SIR original
trace.json.draft_sha256        ──► Draft IDL
trace.json.final_idl_sha256    ──► idl_final.idl
trace.json.bundle_manifest_sha256 ──► bundle/bundle.manifest.json
trace.json.contract_ledger_sha256 ──► bundle/contract_ledger.json
```

---

## 9. GAPs

### 9.1 GAP: trace.json não persiste em deploy

| Severidade | Média |
|------------|-------|
| Descrição | `run_pipeline` (deploy) não persiste trace.json |
| Impacto | Sem rastreabilidade para bundles em produção |

**Comportamento atual:**
- `build_pipeline` → persiste `trace.json` e `idl_final.idl` ✓
- `run_pipeline` → **não** persiste nenhum artefato de trace ✗

**Evidência:** [orchestrator.py:145-478](../../../../src/engine/pipeline/orchestrator.py) — nenhuma escrita de trace

**Proposto:** Persistir trace.json também em deploys, em diretório dedicado (ex: `releases/<release_id>/`).

### 9.2 GAP: idl_final.idl não vinculado ao bundle em produção

Quando um deploy é feito via `run_pipeline`, a IDL final é compilada para temp dir e descartada. Não há registro persistente da IDL que gerou o bundle em produção.

---

## 10. Registry de Eventos

### 10.1 Arquivo

`dev_runs_registry.jsonl` — append-only JSONL

**Evidência:** [registry.py:22](../../../../src/engine/pipeline/registry.py)

### 10.2 Schema de Evento

```json
{
  "event_type": "DEV_RUN_CREATED|DEV_RUN_EXPORTED|DEV_RUN_DELETED",
  "run_id": "UUID",
  "bundle_name": "string",
  "timestamp": "ISO8601 UTC",
  "bundle_path": "string",       // para CREATED
  "zip_path": "string",          // para EXPORTED
  "zip_sha256": "string"         // para EXPORTED
}
```

**Evidência:** [registry.py:63-101](../../../../src/engine/pipeline/registry.py)

---

## 11. API de Consulta

### 11.1 GET /pipeline/build/detail

Retorna detalhes de um run incluindo trace:

```json
{
  "success": true,
  "run_id": "...",
  "bundle_name": "...",
  "created_at": "ISO8601",
  "bundle_path": "...",
  "has_zip": false,
  "deleted": false,
  "trace": {
    "run_id": "...",
    "bundle_name": "...",
    "sir_sha256": "...",
    "draft_sha256": "...",
    "final_idl_sha256": "...",
    "bundle_manifest_sha256": "...",
    "contract_ledger_sha256": "..."
  }
}
```

**Evidência:** [run_detail.py:74-105](../../../../src/engine/pipeline/run_detail.py)

---

## 12. Determinismo

### 12.1 Garantias

| Propriedade | Garantia |
|-------------|----------|
| Mesma IDL → mesmo `final_idl_sha256` | **Sim** |
| Mesma IDL → mesmo `bundle_manifest_sha256` | **Não** (timestamp varia) |
| Mesmos inputs → mesmo `sir_sha256` | **Sim** (extractor determinístico) |

### 12.2 Nota sobre Timestamps

O `bundle.manifest.json` contém `created_at` que varia por compilação. Para builds 100% reproduzíveis, seria necessário fixar timestamp via variável de ambiente.

---

## 13. Exemplo Completo

### 13.1 trace.json (single mode)

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "bundle_name": "finance-pilot",
  "mode": "single",
  "sir_sha256": "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd",
  "draft_sha256": "b2c3d4e5f6789012345678901234567890123456789012345678901234abcdef",
  "final_idl_sha256": "c3d4e5f6789012345678901234567890123456789012345678901234abcdef01",
  "bundle_manifest_sha256": "d4e5f6789012345678901234567890123456789012345678901234abcdef0123",
  "contract_ledger_sha256": "e5f6789012345678901234567890123456789012345678901234abcdef012345",
  "policy_count": 3,
  "policy_gap_count": 0,
  "has_policy_gaps": false
}
```

### 13.2 trace.json (multi mode)

```json
{
  "run_id": "660e8400-e29b-41d4-a716-446655440001",
  "bundle_name": "enterprise-bundle",
  "mode": "multi",
  "sir_sha256": "...",
  "draft_sha256": "...",
  "final_idl_sha256": "...",
  "bundle_manifest_sha256": "...",
  "contract_ledger_sha256": "...",
  "policy_count": 5,
  "policy_gap_count": 0,
  "has_policy_gaps": false,
  "departments": ["finance", "hr", "procurement"]
}
```

---

## 14. Referências

- [States Specification](states.md)
- [IDL v1.x Specification](../02-idl-artifacts/idl-v1.md)
- [Canonical Artifacts](../02-idl-artifacts/canonical-artifacts.md)
- [orchestrator.py](../../../../src/engine/pipeline/orchestrator.py)
- [hashes.py](../../../../src/engine/pipeline/hashes.py)
- [run_detail.py](../../../../src/engine/pipeline/run_detail.py)
- [registry.py](../../../../src/engine/pipeline/registry.py)

---

**Status:** ESPECIFICAÇÃO ATIVA
**Data:** 2026-01-18
