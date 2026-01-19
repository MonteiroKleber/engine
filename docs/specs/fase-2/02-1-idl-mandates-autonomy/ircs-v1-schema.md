# IRCS v1 Schema (Intermediate Representation Canonical Schema)

**Data:** 2026-01-18
**Status:** DRAFT
**Origem:** spec.md (Etapa 2.1)

## Visão Geral

O IRCS v1 é o formato canônico de representação intermediária entre a DSL textual (IDL v1.2.2) e os contracts/bundle gerados pelo ISE. É um JSON determinístico e validável offline.

## Propriedades Obrigatórias (Root)

```json
{
  "ir_version": "ircs.v1",
  "source_idl_version": "idl.v1.2.2",
  "source_idl_sha256": "<hex-64-chars>",
  "system": { ... },
  "department": { ... },
  "policy_context": { ... },
  "actors": [ ... ],
  "entities": [ ... ],
  "invariants": [ ... ],
  "separation_of_duties": [ ... ],
  "workflows": [ ... ],
  "operations": { ... },
  "runtime": { ... }
}
```

## Seções Detalhadas

### 1. Metadados de Versão

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `ir_version` | string | Sim | Sempre `"ircs.v1"` |
| `source_idl_version` | string | Sim | Versão da IDL fonte (`"idl.v1.2.2"`) |
| `source_idl_sha256` | string | Sim | SHA256 (hex, 64 chars) do **texto DSL fonte em UTF-8** |

**IMPORTANTE:** O `source_idl_sha256` é o hash do arquivo `.idl` textual (DSL v1.2.2) codificado em UTF-8, **não** do JSON intermediário. Isso garante prova offline vinculada à especificação institucional original, não a uma representação derivada.

### 2. System

```json
{
  "system": {
    "id": "FinancePilot",
    "name": "Finance Pilot",
    "description": "...",
    "domain": "finance",
    "owner": "Libervia",
    "contact": "ops@libervia.xyz"
  }
}
```

| Campo | Tipo | Obrigatório |
|-------|------|-------------|
| `id` | string | Sim |
| `name` | string | Sim |
| `description` | string | Não |
| `domain` | string | Não |
| `owner` | string | Não |
| `contact` | string | Não |

### 3. Department

```json
{
  "department": {
    "dept_id": "finance",
    "name": "Finance",
    "namespace": "finance",
    "tenancy": "multi",
    "entrypoints": {
      "api_prefix": "/finance",
      "permission_prefix": "finance.",
      "event_prefix": "finance."
    }
  }
}
```

### 4. Policy Context

Define variáveis de contexto disponíveis em expressões.

```json
{
  "policy_context": {
    "schema": [
      { "name": "jurisdiction", "type": "string", "required": true },
      { "name": "risk_level", "type": "string", "required": false, "default": "low" },
      { "name": "sanctions_hit", "type": "bool", "required": false, "default": false }
    ]
  }
}
```

### 5. Actors

```json
{
  "actors": [
    {
      "kind": "human",
      "id": "operator",
      "name": "Operator",
      "description": "...",
      "auth": "oauth2",
      "permissions": ["finance.expense.create", "finance.expense.read"]
    }
  ]
}
```

| Campo | Tipo | Valores permitidos |
|-------|------|-------------------|
| `kind` | string | `"human"`, `"system"`, `"external"` |
| `auth` | string | `"none"`, `"basic"`, `"token"`, `"oauth2"`, `"certificate"` |

### 6. Entities

```json
{
  "entities": [
    {
      "name": "Expense",
      "storage": {
        "tenant_field": "tenant_id",
        "version_field": "version"
      },
      "fields": [
        { "name": "id", "type": "uuid", "required": true, "unique": true },
        { "name": "amount", "type": "decimal", "required": true, "min": 0 },
        { "name": "state", "type": "string", "required": true, "indexed": true }
      ]
    }
  ]
}
```

**Tipos de campo permitidos:**
- Primitivos: `uuid`, `string`, `text`, `int`, `float`, `decimal`, `bool`, `datetime`
- Coleções: `list<T>`, `set<T>`, `map<K,V>` (fora do escopo v1)

### 7. Invariants (AST tipado)

```json
{
  "invariants": [
    {
      "name": "NoNegativeBalance",
      "applies_to": "Account",
      "when": { "kind": "always" },
      "assert": {
        "kind": "compare",
        "op": ">=",
        "lhs": { "ref": "entity.balance", "type": "decimal" },
        "rhs": { "lit": 0, "type": "decimal" }
      },
      "severity": "critical",
      "message": "Account balance cannot be negative."
    }
  ]
}
```

### 8. Separation of Duties (com history() v1.2.2)

```json
{
  "separation_of_duties": [
    {
      "name": "NoSelfApproval",
      "on_entity": "Expense",
      "forbid": {
        "action": "Approve",
        "when": {
          "kind": "compare",
          "op": "==",
          "lhs": { "ref": "actor.id", "type": "uuid" },
          "rhs": { "ref": "entity.created_by", "type": "uuid" }
        }
      },
      "severity": "critical",
      "message": "Creator cannot approve their own expense."
    },
    {
      "name": "NoSubmitterApproval",
      "on_entity": "Expense",
      "forbid": {
        "action": "Approve",
        "when": {
          "kind": "compare",
          "op": "in",
          "lhs": { "ref": "actor.id", "type": "uuid" },
          "rhs": { "history": "Submit", "attr": "actors", "type": "set<uuid>" }
        }
      },
      "severity": "critical",
      "message": "Submitter cannot approve."
    }
  ]
}
```

### 9. Workflows (com approvals)

```json
{
  "workflows": [
    {
      "name": "ExpenseFlow",
      "on_entity": "Expense",
      "state_field": "state",
      "states": [
        { "name": "Draft", "initial": true, "terminal": false },
        { "name": "PendingApproval", "initial": false, "terminal": false },
        { "name": "Approved", "initial": false, "terminal": true }
      ],
      "transitions": [
        {
          "name": "Submit",
          "from": "Draft",
          "to": "PendingApproval",
          "guard": { ... },
          "approvals": null,
          "effects": [
            { "kind": "set_state", "value": "PendingApproval" },
            { "kind": "bump_version", "field": "version", "by": 1 }
          ]
        },
        {
          "name": "Approve",
          "from": "PendingApproval",
          "to": "Approved",
          "guard": { ... },
          "approvals": {
            "quorum": 2,
            "roles": ["manager", "controller"],
            "distinct_actors": true,
            "expires_in": "48h"
          },
          "effects": [ ... ]
        }
      ]
    }
  ]
}
```

### 10. Operations (API bindings)

```json
{
  "operations": {
    "api": [
      {
        "id": "expense_create",
        "method": "POST",
        "path": "/finance/expenses",
        "request_type": "Expense",
        "response_type": "Expense",
        "permission": "finance.expense.create",
        "scope": "tenant",
        "idempotency": "required",
        "errors": [400, 401, 403],
        "bind": { "entity": "Expense", "kind": "create" }
      },
      {
        "id": "expense_approve_transition",
        "method": "POST",
        "path": "/finance/expenses/{id}/transitions/approve",
        "bind": {
          "entity": "Expense",
          "kind": "transition",
          "workflow": "ExpenseFlow",
          "transition": "Approve"
        }
      }
    ]
  }
}
```

### 11. Runtime

```json
{
  "runtime": {
    "safe_mode": {
      "enabled": true,
      "on_invariant_violation": "enter",
      "on_contract_tamper": "enter"
    },
    "proof": {
      "snapshot_enabled": true
    },
    "gate_order": [
      "safe_mode",
      "rbac",
      "policy_pre",
      "sod",
      "workflow",
      "invariants",
      "commit",
      "policy_post",
      "ledger_finalize"
    ]
  }
}
```

## AST de Expressões (predicate_expr)

### Nós válidos

| kind | Campos | Exemplo |
|------|--------|---------|
| `always` | — | `{ "kind": "always" }` |
| `compare` | `op`, `lhs`, `rhs` | `{ "kind": "compare", "op": ">=", "lhs": {...}, "rhs": {...} }` |
| `and` | `exprs[]` | `{ "kind": "and", "exprs": [...] }` |
| `or` | `exprs[]` | `{ "kind": "or", "exprs": [...] }` |
| `not` | `expr` | `{ "kind": "not", "expr": {...} }` |

### Operadores de comparação

`==`, `!=`, `>`, `>=`, `<`, `<=`, `in`

### Referências (value nodes)

| Tipo | Formato | Exemplo |
|------|---------|---------|
| Literal | `{ "lit": <valor>, "type": "<tipo>" }` | `{ "lit": 0, "type": "decimal" }` |
| Ref path | `{ "ref": "<path>", "type": "<tipo>" }` | `{ "ref": "entity.amount", "type": "decimal" }` |
| History (v1.2.2) | `{ "history": "<step>", "attr": "<attr>", "type": "<tipo>" }` | `{ "history": "Submit", "attr": "actors", "type": "set<uuid>" }` |

### Roots permitidos em ref_path

- `entity.*` — campos da entidade aplicável
- `actor.*` — campos do ator corrente (`actor.id`, `actor.roles`)
- `context.*` — campos do policy_context
- `request.*` — campos do request (somente onde permitido)

### Atributos de history() (v1.2.2)

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `actors` | `set<uuid>` | Conjunto de atores que executaram o step |
| `count` | `int` | Quantidade de vezes que o step foi executado |
| `last_actor` | `uuid \| null` | Último ator que executou |
| `last_at` | `datetime \| null` | Timestamp da última execução |

## Validações Determinísticas

O IRCS v1 deve ser validado com erros determinísticos:

| Código | Descrição |
|--------|-----------|
| `IRCS_INVALID_VERSION` | `ir_version` não é `"ircs.v1"` |
| `IRCS_MISSING_FIELD` | Campo obrigatório ausente |
| `IRCS_INVALID_REF` | Referência a entidade/actor/field inexistente |
| `IRCS_INVALID_TYPE` | Tipo incompatível em expressão |
| `IRCS_HISTORY_UNKNOWN_ATTR` | Atributo de history() inválido |
| `IRCS_WORKFLOW_INVALID_STATE` | Estado referenciado não existe |
| `IRCS_SoD_INVALID_ACTION` | Ação em SoD não corresponde a transition |

## Diferenças: JSON Legado vs IRCS v1

| Aspecto | JSON Legado (idl_parser.py) | IRCS v1 |
|---------|----------------------------|---------|
| Fonte | NL/heurística/manual | DSL textual v1.2.2 |
| Expressões | Strings livres ou ausentes | AST tipado obrigatório |
| history() | Não suportado | Suportado (v1.2.2) |
| Versionamento | `idl_version: "1.0"` ou `"1.1"` | `ir_version: "ircs.v1"` |
| Hash | Não preservado | `source_idl_sha256` obrigatório (hash do DSL UTF-8, não do JSON) |
| Validação | Parcial/heurística | Determinística/completa |
