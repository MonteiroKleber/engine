# ISE Compilation Architecture Map

**Etapa 2.2 — PROMPT 2.2.2 Implementação**
**Data**: 2026-01-18
**Status**: ✅ IMPLEMENTADO

---

## Status de Implementação

| Item | Status | Notas |
|------|--------|-------|
| Adapter IRCS v1 → ParsedIDL | ✅ | `src/engine/ise/ircs_adapter.py` |
| Entry point `compile_from_ircs()` | ✅ | `src/engine/ise/compiler.py:688` |
| CLI `compile-ircs` | ✅ | `src/engine/ise/__main__.py` |
| Tests | ✅ | `tests/test_ircs_to_bundle.py` (15 tests) |
| Bundle loads as ACTIVE | ✅ | Verified via loader test |
| source_idl_sha256 preserved | ✅ | In contract_ledger.json |

---

**Contexto**: Mapeamento do fluxo de compilação ISE para integração com IRCS v1

---

## 1. Fluxo Atual de Compilação

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ISE COMPILATION FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   JSON Input (ad-hoc)                                                        │
│         │                                                                    │
│         ▼                                                                    │
│   ┌─────────────────┐                                                        │
│   │  parse_idl()    │  src/engine/ise/idl_parser.py:1260                    │
│   │  JSON → ParsedIDL                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │  compile_bundle │  src/engine/ise/compiler.py:580                       │
│   │  Orchestrator   │                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ _emit_all_      │  src/engine/ise/compiler.py:450                       │
│   │  contracts()    │                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ├──────────────────────────────────────────────────────┐         │
│            │                                                       │         │
│            ▼                                                       ▼         │
│   ┌─────────────────┐                                    ┌──────────────────┐│
│   │   10 Emitters   │                                    │  Manifest/Ledger ││
│   │   (see §2)      │                                    │  Generation      ││
│   └────────┬────────┘                                    └────────┬─────────┘│
│            │                                                      │          │
│            ▼                                                      ▼          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        BUNDLE OUTPUT                                 │   │
│   │  bundle.manifest.json + contract_ledger.json + contracts/*.json     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mapeamento de Emitters → Contratos

| Emitter Function | Source File | Contract Output | ParsedIDL Fields Used |
|------------------|-------------|-----------------|----------------------|
| `emit_rbac()` | `emit/rbac_emit.py` | `rbac.json` | `actors`, `entities`, `usecases` |
| `emit_workflows()` | `emit/workflows_emit.py` | `workflows.json` | `entities`, `usecases` (workflow defs) |
| `emit_approvals()` | `emit/approvals_emit.py` | `approvals.json` | `usecases` (approval requirements) |
| `emit_sod()` | `emit/sod_emit.py` | `sod.json` | `usecases` (SoD rules) |
| `emit_invariants()` | `emit/invariants_emit.py` | `invariants.json` | `entities` (invariant defs) |
| `emit_openapi_yaml()` | `emit/openapi_emit.py` | `openapi.yaml` | `entities`, `usecases` |
| `emit_policies_json()` | `emit/policies_emit.py` | `policies.json` | `policies` |
| `emit_mandates_json()` | `emit/mandates_emit.py` | `mandates.json` | `mandates` |
| `emit_autonomy_json()` | `emit/autonomy_emit.py` | `autonomy.json` | `autonomy` |
| `emit_contracts()` | `emit/contracts_emit.py` | `contracts.json` | `contracts` |

---

## 3. Modelo Interno: ParsedIDL

```python
# src/engine/ise/idl_parser.py

@dataclass
class ParsedIDL:
    system_name: str
    version: str
    idl_version: str = "1.0"  # "1.0" legacy, "1.1" mandates/autonomy first-class

    # Core collections
    actors: List[IDLActor]           # → rbac.json
    entities: List[IDLEntity]        # → workflows.json, invariants.json
    usecases: List[IDLUseCase]       # → approvals.json, sod.json, workflows.json
    departments: List[IDLDepartment] # Multi-tenant routing
    contracts: List[IDLContract]     # → contracts.json

    # IDL v1.1+ extensions
    policies: List[IDLPolicy]        # → policies.json
    mandates: List[IDLMandate]       # → mandates.json
    autonomy: Optional[IDLAutonomy]  # → autonomy.json
```

### Sub-modelos Relevantes

```python
@dataclass
class IDLActor:
    id: str
    name: str
    kind: str  # "human" | "system" | "external"
    permissions: List[str]
    auth: str  # "oauth2" | "token" | "basic" | "none"

@dataclass
class IDLEntity:
    name: str
    fields: List[IDLField]
    invariants: List[IDLInvariant]
    storage: Optional[IDLStorage]

@dataclass
class IDLUseCase:
    id: str
    name: str
    actor: str
    entity: str
    operation: str  # "create" | "read" | "update" | "delete" | "transition"
    workflow: Optional[IDLWorkflow]
    approval: Optional[IDLApproval]
    sod_rules: List[IDLSoDRule]
```

---

## 4. IRCS v1 Schema (Output de Etapa 2.1)

```python
# Output de parse_dsl() em src/engine/idl_dsl/

{
    "ir_version": "ircs.v1",
    "source_idl_version": "idl.v1.2.2",
    "source_idl_sha256": "...",

    "system": {...},
    "department": {...},
    "policy_context": {...},

    "actors": [...],           # ← Mapeia para IDLActor
    "entities": [...],         # ← Mapeia para IDLEntity
    "invariants": [...],       # ← Mapeia para IDLEntity.invariants
    "separation_of_duties": [...], # ← Mapeia para IDLUseCase.sod_rules
    "workflows": [...],        # ← Mapeia para IDLUseCase.workflow
    "operations": {...},       # ← Mapeia para IDLUseCase

    "runtime": {...}
}
```

---

## 5. Ponto de Integração Recomendado

### Opção A: Adapter IRCS v1 → ParsedIDL (RECOMENDADA)

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐
│  IRCS v1     │ ──► │ ircs_to_parsed_idl()│ ──► │  ParsedIDL   │
│  (JSON)      │     │ (novo adapter)      │     │  (existente) │
└──────────────┘     └─────────────────────┘     └──────┬───────┘
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │  Emitters        │
                                              │  (sem alteração) │
                                              └──────────────────┘
```

**Vantagens**:
- Reutiliza 100% dos emitters existentes
- Zero duplicação de lógica de emissão
- Fácil de testar (adapter isolado)
- Mantém compatibilidade com JSON legacy

### Opção B: Bypass ParsedIDL (NÃO RECOMENDADA)

Criar emitters específicos para IRCS v1 duplicaria toda a lógica de emissão.

---

## 6. Arquivos Afetados

### Novos Arquivos (✅ CRIADOS)

| Arquivo | Propósito |
|---------|-----------|
| `src/engine/ise/ircs_adapter.py` | ✅ Adapter IRCS v1 → ParsedIDL |
| `src/engine/ise/__main__.py` | ✅ CLI entry point |
| `tests/test_ircs_to_bundle.py` | ✅ Testes E2E (15 tests) |

### Arquivos Modificados (✅ IMPLEMENTADO)

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/ise/compiler.py` | ✅ `compile_from_ircs()` e `compile_from_ircs_file()` |
| `src/engine/ise/__init__.py` | ✅ Exportar novas funções |

### Arquivos Não Modificados

Todos os emitters em `src/engine/ise/emit/` permanecem inalterados (conforme design).

---

## 7. Fluxo Proposto Pós-Integração

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NOVO FLUXO COM IRCS v1                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   DSL v1.2.2 (finance.idl)                                                  │
│         │                                                                    │
│         ▼                                                                    │
│   ┌─────────────────┐                                                        │
│   │  parse_dsl()    │  src/engine/idl_dsl/ (Etapa 2.1)                      │
│   │  DSL → IRCS v1  │                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ ircs_to_parsed_ │  src/engine/ise/ircs_adapter.py (NOVO)                │
│   │     idl()       │                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │   ParsedIDL     │  (modelo interno existente)                           │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │  compile_bundle │  (existente, sem alteração)                           │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        BUNDLE OUTPUT                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Referência Rápida de Arquivos

```
src/engine/
├── idl_dsl/                    # Etapa 2.1 (DSL → IRCS v1)
│   ├── lexer.py
│   ├── parser.py
│   ├── ast_nodes.py
│   ├── ircs_emit.py
│   └── __main__.py
│
├── ise/                        # ISE (Compilation Engine)
│   ├── idl_parser.py          # ParsedIDL dataclass + parse_idl()
│   ├── compiler.py            # compile_bundle() orchestrator
│   ├── ircs_adapter.py        # (NOVO) IRCS v1 → ParsedIDL
│   │
│   └── emit/                   # Contract Emitters
│       ├── rbac_emit.py
│       ├── workflows_emit.py
│       ├── approvals_emit.py
│       ├── sod_emit.py
│       ├── invariants_emit.py
│       ├── openapi_emit.py
│       ├── policies_emit.py
│       ├── mandates_emit.py
│       ├── autonomy_emit.py
│       └── contracts_emit.py
│
examples/
└── finance.idl                 # Canonical DSL example
```
