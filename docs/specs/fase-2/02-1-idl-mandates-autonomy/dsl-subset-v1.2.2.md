# IDL DSL v1.2.2 Subset (Finance Canônico)

**Data:** 2026-01-18
**Status:** DRAFT
**Origem:** spec.md (Etapa 2.1)

## Objetivo

Definir o subset mínimo da gramática IDL v1.2.2 necessário para expressar o Finance Pilot canônico, permitindo a implementação de um parser/conversor para IRCS v1.

## Fontes Normativas

- IDL v1.1 (EBNF core): `incremento-038.pdf`
- IDL v1.2.1 (extensions): `incremento-050.pdf`
- IDL v1.2.2 (history()): `incremento-061.pdf`
- IDL v1.2.2 congelada: `incremento-063.pdf`

## Gramática EBNF (Subset Finance v1.2.2)

```ebnf
(* ============================================ *)
(* IDL v1.2.2 Subset — Finance Canônico        *)
(* ============================================ *)

document = { section } ;

section =
    system_section
  | actors_section
  | entities_section
  | policy_context_section
  | invariants_section
  | separation_of_duties_section
  | workflows_section
  | operations_section
  ;

(* ---------- SYSTEM ---------- *)

system_section = "system" identifier "{" { system_property } "}" ;

system_property =
    "name" ":" string_literal
  | "description" ":" string_literal
  | "version" ":" version_string
  | "domain" ":" string_literal
  | "owner" ":" string_literal
  | "contact" ":" string_literal
  | "tenancy" ":" tenancy_mode
  ;

tenancy_mode = "single" | "multi" ;

(* ---------- ACTORS ---------- *)

actors_section = "actors" "{" { actor_definition } "}" ;

actor_definition = actor_type identifier "{" { actor_property } "}" ;

actor_type = "human" | "system" | "external" ;

actor_property =
    "name" ":" string_literal
  | "description" ":" string_literal
  | "authentication" ":" auth_method
  | "permissions" ":" identifier_list
  ;

auth_method = "none" | "basic" | "token" | "oauth2" | "certificate" ;

(* ---------- ENTITIES ---------- *)

entities_section = "entities" "{" { entity_definition } "}" ;

entity_definition = "entity" identifier "{" { entity_member } "}" ;

entity_member =
    field_definition
  | storage_definition
  ;

field_definition = "field" identifier ":" field_type { field_modifier } ;

field_type = primitive_type | identifier ;

primitive_type = "string" | "text" | "int" | "float" | "decimal" | "bool" | "datetime" | "uuid" ;

field_modifier =
    "required"
  | "unique"
  | "indexed"
  | "default" "(" literal ")"
  | "min" "(" number ")"
  | "max" "(" number ")"
  ;

storage_definition = "storage" "{" { storage_property } "}" ;

storage_property =
    "tenant_field" ":" identifier
  | "version_field" ":" identifier
  ;

(* ---------- POLICY CONTEXT ---------- *)

policy_context_section = "policy_context" "{" { context_field } "}" ;

context_field = "field" identifier ":" field_type [ "required" ] [ "default" "(" literal ")" ] ;

(* ---------- INVARIANTS ---------- *)

invariants_section = "invariants" "{" { invariant_definition } "}" ;

invariant_definition = "invariant" identifier "{" { invariant_property } "}" ;

invariant_property =
    "applies_to" ":" identifier
  | "when" ":" predicate_expr
  | "assert" ":" predicate_expr
  | "severity" ":" severity_level
  | "message" ":" string_literal
  ;

severity_level = "low" | "medium" | "high" | "critical" ;

(* ---------- SEPARATION OF DUTIES ---------- *)

separation_of_duties_section = "separation_of_duties" "{" { sod_rule } "}" ;

sod_rule = "rule" identifier "{" { sod_property } "}" ;

sod_property =
    "on" ":" identifier
  | "forbid" ":" forbid_expr
  | "severity" ":" severity_level
  | "message" ":" string_literal
  ;

forbid_expr = identifier "when" predicate_expr ;

(* ---------- WORKFLOWS ---------- *)

workflows_section = "workflows" "{" { workflow_definition } "}" ;

workflow_definition = "workflow" identifier "on" identifier "{" { workflow_member } "}" ;

workflow_member =
    workflow_state
  | workflow_transition
  ;

workflow_state = "state" identifier [ "{" { state_property } "}" ] ;

state_property =
    "initial" ":" boolean_literal
  | "terminal" ":" boolean_literal
  ;

workflow_transition = "transition" identifier ":" identifier "->" identifier [ "{" { transition_property } "}" ] ;

transition_property =
    "guard" ":" predicate_expr
  | "approvals" ":" approvals_block
  | "effects" ":" effects_block
  ;

approvals_block = "{" { approvals_property } "}" ;

approvals_property =
    "quorum" ":" number
  | "roles" ":" identifier_list
  | "distinct_actors" ":" boolean_literal
  | "expires_in" ":" duration_literal
  ;

effects_block = "[" { effect_step } "]" ;

effect_step = identifier "(" [ effect_args ] ")" ;

effect_args = literal | identifier ;

(* ---------- OPERATIONS ---------- *)

operations_section = "operations" "{" { operations_member } "}" ;

operations_member = api_section ;

api_section = "api" "{" { endpoint_definition } "}" ;

endpoint_definition = "endpoint" identifier "{" { endpoint_property } "}" ;

endpoint_property =
    "method" ":" http_method
  | "path" ":" string_literal
  | "request" ":" type_ref
  | "response" ":" type_ref
  | "permission" ":" identifier
  | "scope" ":" scope_type
  | "idempotency" ":" idempotency_mode
  | "errors" ":" error_list
  | "bind" ":" bind_spec
  ;

http_method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" ;

type_ref = identifier | "void" | "any" ;

scope_type = "own" | "tenant" | "department" | "all" ;

idempotency_mode = "required" | "optional" | "none" ;

error_list = "[" [ number { "," number } ] "]" ;

bind_spec = "{" { bind_property } "}" ;

bind_property =
    "entity" ":" identifier
  | "kind" ":" bind_kind
  | "workflow" ":" identifier
  | "transition" ":" identifier
  | "decision" ":" string_literal
  ;

bind_kind = "create" | "read" | "update" | "delete" | "transition" | "approval" ;

(* ---------- PREDICATE EXPRESSIONS (v1.2.2) ---------- *)

predicate_expr =
    "always"
  | or_expr
  ;

or_expr = and_expr { "or" and_expr } ;

and_expr = not_expr { "and" not_expr } ;

not_expr = [ "not" ] atom_expr ;

atom_expr =
    comparison
  | "(" predicate_expr ")"
  ;

comparison = value_ref comparator value_ref ;

comparator = "==" | "!=" | ">" | ">=" | "<" | "<=" | "in" ;

value_ref =
    number
  | boolean_literal
  | string_literal
  | ref_path
  | history_ref
  ;

ref_path = identifier { "." identifier } ;

(* history() — v1.2.2 extension *)
history_ref = "history" "(" string_literal ")" "." history_attr ;

history_attr = "actors" | "count" | "last_actor" | "last_at" ;

(* ---------- TERMINALS ---------- *)

identifier = letter { letter | digit | "_" } ;

identifier_list = "[" [ identifier { "," identifier } ] "]" ;

string_literal = '"' { character } '"' ;

number = [ "-" ] digit { digit } [ "." digit { digit } ] ;

boolean_literal = "true" | "false" ;

duration_literal = number ( "s" | "m" | "h" | "d" ) ;

version_string = number "." number "." number ;

literal = string_literal | number | boolean_literal ;

letter = "a" | ... | "z" | "A" | ... | "Z" ;
digit = "0" | ... | "9" ;
```

## Exemplo Canônico: Finance v1.2.2

```idl
system FinancePilot {
  name: "Finance Pilot"
  description: "Governed finance department with approvals, SoD and hard invariants."
  version: 1.0.0
  domain: "finance"
  owner: "Libervia"
  contact: "ops@libervia.xyz"
  tenancy: multi
}

actors {
  human operator {
    name: "Operator"
    description: "Creates and submits expenses."
    authentication: oauth2
    permissions: [finance.expense.create, finance.expense.read, finance.expense.submit]
  }

  human manager {
    name: "Manager"
    description: "Approves expenses under policy constraints."
    authentication: oauth2
    permissions: [finance.expense.read, finance.expense.approve, finance.expense.transition]
  }

  human controller {
    name: "Controller"
    description: "Second approver / financial control."
    authentication: oauth2
    permissions: [finance.expense.read, finance.expense.approve, finance.expense.transition]
  }

  system runtime {
    name: "Runtime"
    description: "Institutional runtime actor."
    authentication: token
    permissions: [runtime.bundle.load, runtime.proof.snapshot, runtime.safe_mode.enter]
  }
}

entities {
  entity Expense {
    storage {
      tenant_field: tenant_id
      version_field: version
    }

    field id: uuid required unique
    field tenant_id: uuid required indexed
    field amount: decimal required min(0)
    field currency: string required
    field description: text required
    field created_by: uuid required indexed
    field created_at: datetime required
    field state: string required indexed
    field version: int required default(1)
  }

  entity Account {
    storage {
      tenant_field: tenant_id
      version_field: version
    }

    field id: uuid required unique
    field tenant_id: uuid required indexed
    field balance: decimal required
    field currency: string required
    field version: int required default(1)
  }
}

policy_context {
  field jurisdiction: string required
  field risk_level: string default("low")
  field sanctions_hit: bool default(false)
}

invariants {
  invariant NoNegativeAccountBalance {
    applies_to: Account
    when: always
    assert: Account.balance >= 0
    severity: critical
    message: "Account balance cannot be negative."
  }

  invariant ExpenseMustHaveCurrency {
    applies_to: Expense
    when: always
    assert: Expense.currency != ""
    severity: high
    message: "Expense currency must be defined."
  }
}

separation_of_duties {
  rule NoSelfApproval {
    on: Expense
    forbid: Approve when actor.id == Expense.created_by
    severity: critical
    message: "Creator cannot approve their own expense."
  }

  rule NoSubmitterApproval {
    on: Expense
    forbid: Approve when actor.id in history("Submit").actors
    severity: critical
    message: "Submitter cannot approve."
  }
}

workflows {
  workflow ExpenseFlow on Expense {
    state Draft { initial: true }
    state PendingApproval
    state Approved { terminal: true }
    state Rejected { terminal: true }

    transition Submit: Draft -> PendingApproval {
      guard: context.sanctions_hit == false
      effects: [set_state("PendingApproval"), bump_version(1)]
    }

    transition Approve: PendingApproval -> Approved {
      guard: context.risk_level != "high"
      approvals: {
        quorum: 2
        roles: [manager, controller]
        distinct_actors: true
        expires_in: 48h
      }
      effects: [set_state("Approved"), bump_version(1)]
    }

    transition Reject: PendingApproval -> Rejected {
      approvals: {
        quorum: 1
        roles: [controller]
        distinct_actors: true
        expires_in: 48h
      }
      effects: [set_state("Rejected"), bump_version(1)]
    }
  }
}

operations {
  api {
    endpoint expense_create {
      method: POST
      path: "/finance/expenses"
      request: Expense
      response: Expense
      permission: finance.expense.create
      scope: tenant
      idempotency: required
      errors: [400, 401, 403]
      bind: { entity: Expense, kind: create }
    }

    endpoint expense_get {
      method: GET
      path: "/finance/expenses/{id}"
      request: void
      response: Expense
      permission: finance.expense.read
      scope: tenant
      idempotency: none
      errors: [401, 403, 404]
      bind: { entity: Expense, kind: read }
    }

    endpoint expense_submit {
      method: POST
      path: "/finance/expenses/{id}/transitions/submit"
      request: void
      response: any
      permission: finance.expense.submit
      scope: tenant
      idempotency: required
      errors: [401, 403, 409]
      bind: { entity: Expense, kind: transition, workflow: ExpenseFlow, transition: Submit }
    }

    endpoint expense_approve {
      method: POST
      path: "/finance/expenses/{id}/approvals/approve"
      request: void
      response: any
      permission: finance.expense.approve
      scope: tenant
      idempotency: required
      errors: [401, 403, 409]
      bind: { entity: Expense, kind: approval, workflow: ExpenseFlow, transition: Approve, decision: "approve" }
    }
  }
}
```

## Construtos Fora do Subset (v1.2.2 completa)

Os seguintes construtos existem na IDL v1.2.2 completa mas estão **fora** do subset Finance:

| Construto | Motivo de exclusão |
|-----------|-------------------|
| `governance` section | Não necessário para Finance MVP |
| `policies` section (v1.1) | Substituído por invariants/SoD |
| `integrations` section | Fora do escopo (Etapa futura) |
| `nonfunctional` section | Fora do escopo |
| `runtime` section (DSL) | Gerado automaticamente |
| `usecases` section | Legado v1.0 |
| `events` / `jobs` | Fora do escopo |
| Collection types (`list<T>`) | Simplificação |
| `relation_definition` | Simplificação |

## Mapeamento DSL → IRCS v1

| DSL Section | IRCS v1 Section |
|-------------|-----------------|
| `system { }` | `system` |
| `actors { }` | `actors[]` |
| `entities { }` | `entities[]` |
| `policy_context { }` | `policy_context.schema[]` |
| `invariants { }` | `invariants[]` |
| `separation_of_duties { }` | `separation_of_duties[]` |
| `workflows { }` | `workflows[]` |
| `operations { api { } }` | `operations.api[]` |
| (implícito) | `department` (derivado de system) |
| (implícito) | `runtime` (defaults) |

## Conversão de Expressões

### DSL → IRCS v1 AST

| DSL | IRCS v1 AST |
|-----|-------------|
| `always` | `{ "kind": "always" }` |
| `A == B` | `{ "kind": "compare", "op": "==", "lhs": {...}, "rhs": {...} }` |
| `A and B` | `{ "kind": "and", "exprs": [...] }` |
| `A or B` | `{ "kind": "or", "exprs": [...] }` |
| `not A` | `{ "kind": "not", "expr": {...} }` |
| `entity.field` | `{ "ref": "entity.field", "type": "<inferred>" }` |
| `123` | `{ "lit": 123, "type": "int" }` |
| `"str"` | `{ "lit": "str", "type": "string" }` |
| `history("X").actors` | `{ "history": "X", "attr": "actors", "type": "set<uuid>" }` |

## Validações do Parser

O parser deve validar:

1. **Referências de entidade** — `applies_to`, `on` devem referenciar entidades definidas
2. **Referências de workflow** — `workflow` em bind deve existir
3. **Referências de transition** — `transition` em bind deve existir no workflow
4. **Tipos em expressões** — inferência de tipos com validação
5. **history() apenas em SoD/guards** — não permitido em invariants.assert
6. **Roles em approvals** — devem corresponder a actors definidos
