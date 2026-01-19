# Finance Bundle Specification

**Data:** 2026-01-18
**Versao:** 1.0
**Etapa:** 05 — Finance Template "Golden"

---

## 1. Visao Geral

Este documento descreve a composicao do bundle `finance-pilot`, o bundle default e referencia ("golden") do MVP do Libervia Engine.

**Localizacao:** `bundles/finance-pilot/`

---

## 2. Arquivos do Bundle

### 2.1 Manifest

| Arquivo | Descricao |
|---------|-----------|
| `bundle.manifest.json` | Manifesto com lista de contratos e hashes SHA256 |

### 2.2 Contratos Institucionais (required=true)

| Arquivo | Versao | Descricao |
|---------|--------|-----------|
| `policies.json` | 1.1 | Politicas dinamicas (vazio no piloto) |
| `mandates.json` | 1.0 | Autorizacoes explicitas por endpoint |
| `autonomy.json` | 1.0 | Niveis de autonomia por endpoint |

### 2.3 Contratos de Controle (required=true)

| Arquivo | Versao | Descricao |
|---------|--------|-----------|
| `rbac.json` | 1.0.0 | Roles e permissoes |
| `approvals.json` | 1.0.0 | Regras de aprovacao |
| `sod.json` | 1.0.0 | Regras de segregacao de funcoes |
| `invariants.json` | 1.0.0 | Regras de negocio/validacao |

### 2.4 Contratos Auxiliares

| Arquivo | Versao | Required | Descricao |
|---------|--------|----------|-----------|
| `contract_ledger.json` | 1.0.0 | true | Ledger de contratos |
| `workflows.json` | 1.0.0 | true | Definicoes de workflow |
| `openapi.yaml` | - | false | Especificacao OpenAPI |

---

## 3. Hashes SHA256

| Arquivo | SHA256 |
|---------|--------|
| `approvals.json` | `49699db08dcd1c427be630fe9090c73e6c923793bb4f2783171a338107333f51` |
| `autonomy.json` | `0151ac1f38390bd100cb6dac40ac42cff341ae19ecff5bec7ba29157106b9336` |
| `contract_ledger.json` | `71fbeddb02e9a3155f2483d237dcb5ec6f9b52b0204c01c01fcab042fecdeed3` |
| `invariants.json` | `3e17572bd74f31c558b5690c2e696b84352ff078ffda81b5e72019f6a5104c7f` |
| `mandates.json` | `1a3ce1b59ff21a9033d4e5dcfa22a9168cc114e801b856348d583197dccd493d` |
| `openapi.yaml` | `c96f851f30cf93204efe2bbce5c820737d0a1a65c0deb4b50de65e1610042fc5` |
| `policies.json` | `f2df6d753b154e6aa3abe70cdc277e914aeed775b63f91745075c200e1ebe09d` |
| `rbac.json` | `64907fac9729f9fc371b2a523048a2cd690216a3e0b9e08967f72de884ac8e05` |
| `sod.json` | `eaea64d77e9c5b0ba2d5318696c1a390da3a8d177249eb3e53e40d33659c7400` |
| `workflows.json` | `c473056482e60e9b11a254a4445ebb1c7e18c1a69c94ae8339d408234e66ae71` |

---

## 4. Conteudo dos Contratos

### 4.1 rbac.json

```json
{
  "version": "1.0.0",
  "name": "rbac",
  "roles": [
    {
      "name": "admin",
      "permissions": ["expense.create", "expense.read", "expense.delete",
                      "expense.approve", "approval.decide"]
    },
    {
      "name": "manager",
      "permissions": ["expense.read", "expense.approve", "approval.decide"]
    },
    {
      "name": "analyst",
      "permissions": ["expense.create", "expense.read"]
    },
    {
      "name": "viewer",
      "permissions": ["expense.read"]
    }
  ]
}
```

### 4.2 mandates.json

```json
{
  "mandate_schema_version": "1.0",
  "mandates": [
    {
      "mandate_id": "expense-create-pre",
      "endpoint_sig": "POST /finance/expenses",
      "phase": "pre",
      "allowed_roles": ["analyst", "admin"],
      "limits": [
        {
          "rule_type": "numeric_max",
          "field_path": "amount",
          "value": 100000,
          "message": "Amount exceeds pilot limit of 100000"
        }
      ]
    },
    {
      "mandate_id": "approval-decide-post",
      "endpoint_sig": "POST /approvals/{approval_id}/decide",
      "phase": "post",
      "allowed_roles": ["manager", "admin"]
    }
  ]
}
```

### 4.3 autonomy.json

```json
{
  "autonomy_schema_version": "1.0",
  "current_level": 0,
  "rules": [
    {
      "rule_id": "expense-create-pre",
      "endpoint_sig": "POST /finance/expenses",
      "phase": "pre",
      "required_level": 0
    },
    {
      "rule_id": "approval-decide-post",
      "endpoint_sig": "POST /approvals/{approval_id}/decide",
      "phase": "post",
      "required_level": 0
    }
  ]
}
```

### 4.4 policies.json

```json
{
  "policy_schema_version": "1.1",
  "policies": []
}
```

### 4.5 approvals.json

```json
{
  "version": "1.0.0",
  "name": "approvals",
  "rules": [
    {
      "rule_name": "expense.create",
      "trigger": {
        "api": "POST /finance/expenses"
      },
      "approver_roles": ["manager"],
      "quorum": 1
    }
  ]
}
```

### 4.6 sod.json

```json
{
  "version": "1.0.0",
  "name": "sod",
  "rules": [
    {
      "rule_name": "expense.create.requester_not_approver",
      "case_step": "APPROVAL:expense.create",
      "constraint": "REQUESTER_NEQ_DECIDER"
    }
  ]
}
```

### 4.7 invariants.json

```json
{
  "version": "1.0.0",
  "name": "invariants",
  "expense": {
    "amount": { "min": 0.01, "max": 1000000000 },
    "description": { "max_len": 280, "required": false }
  }
}
```

---

## 5. Fluxo Permitido no Piloto

### 5.1 Criar Despesa

```
Actor: analyst ou admin
Endpoint: POST /finance/expenses
Limite: amount <= 100.000
Resultado: 202 + approval criado
```

### 5.2 Decidir Aprovacao

```
Actor: manager ou admin (diferente do requester)
Endpoint: POST /approvals/{approval_id}/decide
Decisao: approve ou reject
Resultado: 200 (COMMITTED ou REJECTED)
```

### 5.3 Diagrama de Fluxo

```
         analyst/admin
              |
              v
    POST /finance/expenses
              |
              +-- RBAC: expense.create
              +-- Mandate PRE: expense-create-pre (amount <= 100k)
              +-- Autonomy PRE: expense-create-pre (L0)
              +-- Approval: expense.create -> requires manager
              |
              v
         [202 Accepted]
         Expense: PENDING
         Approval: PENDING
              |
              v
        manager/admin
              |
              v
   POST /approvals/{id}/decide
              |
              +-- Can-decide: manager role
              +-- SoD: requester != decider
              |
      +-------+-------+
      |               |
   reject          approve
      |               |
      v               v
  REJECTED     +-- Mandate POST
      |        +-- Autonomy POST
      |        +-- Invariants
      |               |
      v               v
   [200]         COMMITTED
                    [200]
```

---

## 6. Carregamento do Bundle

### 6.1 Variavel de Ambiente

```bash
ENGINE_BUNDLE_PATH=/path/to/bundles/finance-pilot
```

### 6.2 Verificacao de Integridade

O loader verifica:
1. Existencia de todos os arquivos `required=true`
2. Hash SHA256 de cada contrato vs manifest
3. Schema version compativel

### 6.3 Modos de Operacao

| Condicao | Resultado |
|----------|-----------|
| Todos contratos validos | ACTIVE |
| Contrato required ausente | SAFE_MODE (BUNDLE_CONTRACT_MISSING) |
| Hash invalido | SAFE_MODE (BUNDLE_HASH_MISMATCH) |

---

## 7. Extensao do Bundle

### 7.1 Adicionar Nova Policy

1. Editar `policies.json` adicionando policy
2. Recalcular hash SHA256
3. Atualizar `bundle.manifest.json` com novo hash
4. Testar carregamento do bundle

### 7.2 Aumentar Limite de Mandate

1. Editar `mandates.json` alterando `limits[].value`
2. Recalcular hash SHA256
3. Atualizar `bundle.manifest.json` com novo hash

### 7.3 Adicionar Novo Endpoint

1. Adicionar mandate em `mandates.json`
2. Adicionar rule em `autonomy.json`
3. Adicionar approval rule em `approvals.json` (se aplicavel)
4. Atualizar RBAC se nova permissao necessaria
5. Recalcular hashes e atualizar manifest

---

## 8. Testes

### 8.1 Testes de Bundle

| Teste | Arquivo |
|-------|---------|
| Bundle existe | test_default_bundle_finance_pilot.py |
| Manifest valido | test_default_bundle_finance_pilot.py |
| Hashes corretos | test_default_bundle_finance_pilot.py |
| Carrega ACTIVE | test_default_bundle_finance_pilot.py |
| Missing contract -> SAFE_MODE | test_default_bundle_finance_pilot.py |

### 8.2 Testes E2E

| Teste | Arquivo |
|-------|---------|
| analyst cria expense | test_etapa04_runtime_gates.py |
| admin cria expense | test_etapa04_runtime_gates.py |
| viewer nao cria (RBAC) | test_etapa04_runtime_gates.py |
| amount > 100k (mandate) | test_etapa04_runtime_gates.py |
| manager aprova | test_etapa04_runtime_gates.py |
| manager rejeita | test_etapa04_runtime_gates.py |

---

## 9. Referencias

- [finance-contract.md](finance-contract.md) - Especificacao de contrato
- [gates-matrix.md](../04-runtime-gates/gates-matrix.md) - Matriz de Gates
- [load_bundle.py](../../../../src/engine/loader/load_bundle.py) - Loader de bundle

---

**Status:** ESPECIFICACAO ATIVA
**Data:** 2026-01-18
