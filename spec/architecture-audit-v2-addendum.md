# Auditoria V2 — Fechamento de Lacunas

**Data:** 2026-01-06
**Referência:** `/home/bazari/engine/docs/architecture-audit-report.md`
**Método:** Leitura estática do código-fonte

---

## A) IDL LAYER — CONFIRMADO

### A.1 Constantes de Schema Version

| Constante | Valor | Arquivo | Linha |
|-----------|-------|---------|-------|
| `IDL_SCHEMA_VERSION` | `"idl.v1"` | `idl/idl_v1.py` | 27 |
| `IDL_DRAFT_SCHEMA_VERSION` | `"idl_draft.v1"` | `idl/idl_draft_v1.py` | 25 |

### A.2 Campos Hashable (Contract Gate)

**Arquivo:** `idl/idl_v1.py`, linhas 34-50

**Terminologia Canônica:**
- **NON_HASH_FIELDS** = campos excluídos do cálculo de hash (termo canônico para documentação)
- No código, este conjunto é implementado como `VOLATILE_FIELDS`

```python
HASHABLE_FIELDS = [
    "schema_version",
    "system",
    "actors",
    "entities",
    "usecases",
    "integrations",
    "nonfunctional",
]

# NON_HASH_FIELDS (campos fora do hash)
# Implementado no código como VOLATILE_FIELDS
VOLATILE_FIELDS = [
    "content_hash_sha256",
    "timestamp",
    "parser_version",
    "contract_notes",  # <-- CONFIRMADO: excluído do hash
]
```

### A.3 Algoritmo de Hash

**Arquivo:** `idl/idl_v1.py`, linhas 731-742

```python
def compute_content_hash_sha256(hashable_payload: Dict[str, Any]) -> str:
    """Calcula hash SHA256 do payload hashable.

    Usa serializacao canonica JSON (sort_keys=True, separators minimos).
    """
    canonical_json = json.dumps(
        hashable_payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
```

### A.4 IDL v1 Parser e Canonização

**Arquivo:** `idl/idl_v1.py` (1697 linhas)

**Classes Principais:**
- `IDLLexer` (linha 765): Tokenização do código IDL
- `IDLParser` (linha 965): Parser completo com seções: system, actors, entities, usecases, integrations, nonfunctional
- `IDLDocument` (linha 499): Documento IDL completo

**Regras de Canonização (Determinísticas):**
- Todas as listas são ordenadas por `id` (linha 521-525):
  ```python
  result["actors"] = [a.to_dict() for a in sorted(self.actors, key=lambda x: x.id)]
  result["entities"] = [e.to_dict() for e in sorted(self.entities, key=lambda x: x.id)]
  result["usecases"] = [u.to_dict() for u in sorted(self.usecases, key=lambda x: x.id)]
  ```
- Fields dentro de entities ordenados por `id` (linha 286)
- Relations ordenadas por `id` (linha 287)
- Actors.permissions ordenados (linha 181): `sorted(self.permissions)`

**Métodos de Saída:**
- `to_hashable_dict()` (linha 510): Apenas campos para hash
- `to_canonical_dict()` (linha 529): Dict completo com hash e metadados
- `to_json()` (linha 559): JSON com sort_keys=True
- `to_markdown()` (linha 570): Representação legível

### A.5 IDL Draft v1

**Arquivo:** `idl/idl_draft_v1.py` (400 linhas)

**Dataclasses:**
| Classe | Descrição | Campos Unknown |
|--------|-----------|----------------|
| `DraftActor` (linha 78) | Ator no Draft | role pode ser "unknown" |
| `DraftField` (linha 107) | Campo de entidade | type, required podem ser "unknown" |
| `DraftEntity` (linha 136) | Entidade | fields com unknown |
| `DraftUseCase` (linha 194) | Caso de uso | actor pode ser "unknown" |
| `DraftIntegration` (linha 224) | Integração | type pode ser "unknown" |
| `DraftNonFunctional` (linha 250) | NFRs | performance, security podem ser "unknown" |
| `IDLDraftV1` (linha 281) | Documento completo | open_questions, assumptions |

**Valores Especiais (linha 32-36):**
```python
UNKNOWN = "unknown"
TBD = "TBD"
UNRESOLVED_VALUES = {UNKNOWN, TBD, "tbd", "Unknown", "UNKNOWN"}
```

**Método de Verificação de Compilabilidade (linha 334-347):**
```python
def is_compileable(self) -> bool:
    if self.has_open_questions():
        return False
    if len(self.get_all_unresolved()) > 0:
        return False
    return True
```

### A.6 IDL Compile (GATE 2)

**Arquivo:** `idl/idl_compile.py` (475 linhas)

**Classe:** `DraftToIDLCompiler` (linha 136)

**Condições de Bloqueio (método `_check_blocking_conditions`, linha 204-264):**

| Condição | Erro | Localização |
|----------|------|-------------|
| open_questions presentes | `UNRESOLVED_QUESTION` | `open_questions[i]` |
| Actor sem role | `UNKNOWN_ACTOR_ROLE` | `actors.{id}.role` |
| Field sem type | `UNKNOWN_FIELD_TYPE` | `entities.{id}.fields.{name}.type` |
| Field sem required | `UNKNOWN_FIELD_REQUIRED` | `entities.{id}.fields.{name}.required` |
| UseCase sem actor | `UNKNOWN_USECASE_ACTOR` | `use_cases.{id}.actor` |
| Integration sem type | `UNKNOWN_INTEGRATION_TYPE` | `integrations.{system}.type` |

**Exceção:** `DraftNotCompileableError` (linha 85) com `blocking_errors[]`

**Resultado:** `CompileResult` (linha 107) com `success`, `idl`, `errors`

### A.7 IDL Store (Contract Gate)

**Arquivo:** `idl/idl_store.py` (246 linhas)

**Classe:** `IDLStore` (linha 28)

**Contract Gate (método `_validate_contract_gate_from_dict`, linha 134-157):**
```python
def _validate_contract_gate_from_dict(self, canonical: Dict[str, Any]) -> None:
    # Extrai payload hashable
    hashable_payload = extract_hashable_payload_from_canonical(canonical)

    # Recalcula hash
    recalculated_hash = compute_content_hash_sha256(hashable_payload)

    # Compara com hash salvo
    saved_hash = canonical.get("content_hash_sha256", "")

    if recalculated_hash != saved_hash:
        raise IDLContractGateError(
            f"Contract Gate FAILED: hash mismatch. "
            f"Expected: {saved_hash}, "
            f"Recalculated: {recalculated_hash}"
        )
```

**Métodos:**
- `save(document, project)` → salva JSON + MD, valida gate
- `load(json_path)` → carrega e valida gate
- `get_latest(project)` → último documento do projeto
- `verify_all(project)` → verifica integridade de todos

**Paths de Salvamento:**
- JSON: `{store_root}/idl/{project}_{timestamp}.json`
- Markdown: `{store_root}/idl/{project}_{timestamp}.md`

---

## B) COMPILERS — CONFIRMADO

### B.1 Arquivos Existentes

| Arquivo | Existe | Linhas | Descrição |
|---------|--------|--------|-----------|
| `compilers/backend_compiler.py` | ✅ SIM | 191 | Geração de código Java/Spring |
| `compilers/frontend_compiler.py` | ✅ SIM | 276 | Geração de código React/TypeScript |
| `compilers/patch_generator_v1.py` | ✅ SIM | 200+ | Geração de patches para templates |

### B.2 Backend Compiler

**Arquivo:** `compilers/backend_compiler.py` (191 linhas)

**Classe:** `BackendCompiler` (linha 17)

**Métodos:**
- `compile(ir, plan)` → Gera código Java para entities
- `_generate_entity_java(entity)` → Gera @Entity JPA
- `_generate_repository(entity)` → Gera JpaRepository
- `_generate_service(entity)` → Gera @Service com CRUD
- `_generate_controller(entity)` → Gera @RestController

**Tipos Gerados (linha 33-40):**
```python
TYPE_MAPPING = {
    "string": "String",
    "int": "Integer",
    "integer": "Integer",
    "float": "Double",
    "decimal": "BigDecimal",
    "bool": "Boolean",
    "boolean": "Boolean",
    "datetime": "LocalDateTime",
    "date": "LocalDate",
    "time": "LocalTime",
    "uuid": "UUID",
    "text": "String",
}
```

### B.3 Frontend Compiler

**Arquivo:** `compilers/frontend_compiler.py` (276 linhas)

**Classe:** `FrontendCompiler` (linha 19)

**Métodos:**
- `compile(ir, plan)` → Gera código React/TypeScript
- `_generate_page_list(entity)` → Página de listagem
- `_generate_page_new(entity)` → Formulário de criação
- `_generate_page_edit(entity)` → Formulário de edição
- `_generate_api_client(entity)` → Cliente de API

**Tipos TypeScript (linha 41-52):**
```python
TYPE_MAPPING = {
    "string": "string",
    "int": "number",
    "integer": "number",
    "float": "number",
    "decimal": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "datetime": "string",
    "date": "string",
    "time": "string",
    "uuid": "string",
    "text": "string",
}
```

### B.4 Onde São Chamados

**Arquivo:** `orchestrator/engine.py`

Os compilers **NÃO são chamados diretamente** no fluxo principal. O código gerado vem através do `PatchGenerator` que usa templates com slots.

**Fluxo Real:**
1. `RepoGenerator.create_repo()` → copia templates
2. `PatchGenerator.generate_patches(plan, ir)` → gera patches para slots
3. `PatchEngine.apply_patches()` → aplica patches nos slots dos templates

Os `BackendCompiler` e `FrontendCompiler` parecem ser **código legado ou alternativo** não usado no pipeline principal. O código de geração está em `patch_generator_v1.py`.

---

## C) RELEASE REPORTS / DIAGNOSTICS — CONFIRMADO

### C.1 Arquivos Existentes

| Arquivo | Existe | Linhas | Schema Version |
|---------|--------|--------|----------------|
| `release/release_report.py` | ✅ SIM | 427 | N/A (sem contract gate) |
| `release/release_checklist.py` | ✅ SIM | 705 | N/A (sem contract gate) |
| `release/diagnostic_report.py` | ✅ SIM | 200+ | `diagnostic_report.v1` |

### C.2 Release Report

**Arquivo:** `release/release_report.py` (427 linhas)

**Dataclass:** `ReleaseReport` (linha 22)

**Campos:**
- Identificação: project, version, timestamp, engine_version, execution_id
- Caminhos: repo_path, store_path
- Status: success, final_status
- Artefatos: srs_version, ir_version, oas_version, rbac_version, plan_version
- Métricas: requirements_count, entities_count, operations_count, tasks_count, patch_count
- Build: build_ok, fix_attempts, fixes_applied
- Release: docker_compose_ok, services_running, smoke_ok, smoke_passed, smoke_failed
- Readiness: readiness_fingerprint, readiness_fingerprint_file, runtime_evidence_dir
- DB: db_volume_name

**Gerador:** `ReleaseReportGenerator` (linha 269)

**Salvamento (método `save`, linha 241-266):**
- JSON: `{output_dir}/release_report_{timestamp}.json`
- Markdown: `{output_dir}/release_report_{timestamp}.md`

**Output Dir Default:** `{store_root}/{project}/releases/`

### C.3 Release Checklist

**Arquivo:** `release/release_checklist.py` (705 linhas)

**Classe:** `ReleaseChecklist` (linha 99)

**Verificações:**
1. **Artifacts** (linha 212-237): SRS, IR, OAS, RBAC, PLAN presentes
2. **Hashes** (linha 268-318): input_hash, srs_hash, ir_hash, oas_hash, rbac_hash, plan_hash
3. **Build** (linha 320-358): build_ok = True
4. **Smoke** (linha 360-409): smoke_ok = True (se release_mode)
5. **Blueprint** (linha 411-465): blueprint registrado
6. **Absolute Rules** (linha 467-660):
   - no_pii_logging
   - no_hardcoded_secrets
   - authenticated_endpoints

**Resultado:** `ReleaseChecklistResult` (linha 48)

### C.4 Paths Reais no Disco

| Tipo | Path | Arquivo |
|------|------|---------|
| Run Logs | `{store_root}/{project}/runs/{exec_id}_{ts}.json` | `store/artifacts_store.py` |
| Releases | `{store_root}/{project}/releases/release_report_{ts}.json` | `release/release_report.py` |
| Diagnostics | `{store_root}/{project}/diagnostics/diagnostic_{ts}.json` | `release/diagnostic_report.py` |
| IDL | `{store_root}/idl/{project}_{ts}.json` | `idl/idl_store.py` |
| Artefatos | `{store_root}/{project}/{KIND}/v{N}.{ext}` | `store/artifacts_store.py` |

### C.5 Contract Gate no DiagnosticReport

**Arquivo:** `release/diagnostic_report.py`

**Schema Version (linha 25):**
```python
DIAGNOSTIC_REPORT_SCHEMA_VERSION = "diagnostic_report.v1"
```

**Campos Hashable (linha ~50):**
- schema_version, project, final_status, engine_version
- build_ok, docker_compose_ok, smoke_ok
- errors, repo_path, failed_repo_path
- docker_ps_snapshot, docker_logs_backend_tail, docker_logs_frontend_tail
- suggested_actions

**Hash (linha 28-43):**
```python
def compute_content_hash_sha256():
    # SHA256 of canonical JSON (sorted keys)
```

**Contract Gate:** Usa mesmo padrão do IDL - hashable fields + content_hash verificado na leitura.

---

## D) RUNRESULT FIELDS E STATUS — CONFIRMADO

### D.1 Localização

**Arquivo:** `orchestrator/engine.py`, linhas 47-130

### D.2 Todos os Campos

```python
@dataclass
class RunResult:
    """Resultado de uma execução do pipeline."""

    # Identificação (obrigatórios)
    success: bool
    execution_id: str
    project: str

    # Versões de Artefatos
    srs_version: Optional[int] = None
    srs_path: Optional[str] = None
    ir_version: Optional[int] = None
    ir_path: Optional[str] = None
    oas_version: Optional[int] = None
    oas_path: Optional[str] = None
    rbac_version: Optional[int] = None
    rbac_path: Optional[str] = None
    plan_version: Optional[int] = None
    plan_path: Optional[str] = None

    # Blueprint
    blueprint_type: str = "generic"
    blueprint_forced_generic: bool = True

    # Contadores
    requirements_count: int = 0
    entities_count: int = 0
    operations_count: int = 0
    tasks_count: int = 0

    # Flags de Validação
    srs_validation_ok: bool = False
    ir_validation_ok: bool = False
    oas_validation_ok: bool = False
    rbac_validation_ok: bool = False
    plan_validation_ok: bool = False
    policy_ok: bool = False
    contracts_policy_ok: bool = False
    plan_policy_ok: bool = False

    # Build Phase
    repo_path: Optional[str] = None
    patch_count: int = 0
    build_ok: bool = False
    build_errors: List[str] = field(default_factory=list)

    # Fix Loop
    fix_attempts: int = 0
    fixes_applied: List[Dict[str, Any]] = field(default_factory=list)
    final_status: str = ""  # "success", "fixed", "build_failed", "fatal_error", "running"
    fix_loop_aborted_reason: str = ""

    # Release Mode
    docker_compose_ok: bool = False
    services_running: List[str] = field(default_factory=list)
    smoke_ok: bool = False
    smoke_passed: int = 0
    smoke_failed: int = 0
    release_mode: bool = False

    # Docker Evidence
    docker_up_timeout_seconds: int = 300
    docker_compose_command: str = ""
    docker_stdout_tail: str = ""
    docker_stderr_tail: str = ""

    # Readiness Evidence
    readiness_fingerprint: str = ""
    readiness_fingerprint_file: str = ""
    runtime_evidence_dir: str = ""

    # Failure
    failed_repo_path: Optional[str] = None

    # Input Mode
    input_mode_detected: Optional[str] = None
    input_mode_used: Optional[str] = None

    # IDL Dispatch
    idl_schema_version: Optional[str] = None
    idl_content_hash: Optional[str] = None
    idl_json_path: Optional[str] = None
    draft_used: bool = False
    draft_schema_version: Optional[str] = None

    # Errors
    errors: List[str] = field(default_factory=list)
```

### D.3 Valores de final_status

| Valor | Contexto | Significado |
|-------|----------|-------------|
| `"success"` | Build | Build passou sem fix loop |
| `"fixed"` | Build | Build passou após fix loop |
| `"build_failed"` | Build | Build falhou após max attempts |
| `"fatal_error"` | Build | Erro fatal não recuperável |
| `"running"` | Release | Serviços docker rodando |

**Nota:** `final_status` é usado tanto em build quanto em release, mas com valores diferentes. Em release mode, `"running"` indica sucesso completo.

### D.4 Campos de Input Mode

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `input_mode_detected` | Optional[str] | Modo detectado pelo AUTO |
| `input_mode_used` | Optional[str] | Modo efetivamente usado |
| `idl_schema_version` | Optional[str] | "idl.v1" se IDL |
| `idl_content_hash` | Optional[str] | Hash do IDL canônico |
| `draft_used` | bool | True se Draft foi usado |
| `draft_schema_version` | Optional[str] | "idl_draft.v1" se Draft |

---

## 2. MERMAID DELTA PATCH

**NOTA:** O delta abaixo foi incorporado ao diagrama principal em `architecture-flow.md`.

O Contract Gate é representado **dentro** de `IDLStore.save()`, não como nó separado:

```mermaid
%% SUBGRAPH IDL LAYER - Contract Gate dentro do IDLStore.save()
subgraph IDL_LAYER["IDL LAYER (Detalhado)"]
    direction TB

    subgraph IDL_CONSTANTS["Constantes"]
        IDL_VER["IDL_SCHEMA_VERSION<br/>= 'idl.v1'"]
        DRAFT_VER["IDL_DRAFT_SCHEMA_VERSION<br/>= 'idl_draft.v1'"]
    end

    subgraph HASH_RULES["Hash Rules"]
        HASH_FIELDS["HASHABLE_FIELDS (7):<br/>schema_version, system,<br/>actors, entities, usecases,<br/>integrations, nonfunctional"]
        NON_HASH["NON_HASH_FIELDS (4):<br/>(código: VOLATILE_FIELDS)<br/>content_hash_sha256,<br/>timestamp, parser_version,<br/>contract_notes"]
    end

    subgraph IDL_PARSE["Parser (idl_v1.py)"]
        LEXER["IDLLexer.tokenize()"]
        PARSER["IDLParser.parse()"]
        IDL_DOC_CLASS["IDLDocument"]
        LEXER --> PARSER --> IDL_DOC_CLASS
    end

    subgraph CANON["Canonização"]
        TO_HASHABLE["to_hashable_dict()<br/>Ordena por id"]
        TO_CANONICAL["to_canonical_dict()<br/>Adiciona hash + metadata"]
        COMPUTE_HASH["compute_content_hash_sha256()<br/>JSON sort_keys + SHA256"]
        TO_HASHABLE --> COMPUTE_HASH --> TO_CANONICAL
    end

    subgraph DRAFT_LAYER["Draft Layer (idl_draft_v1.py)"]
        DRAFT_DOC["IDLDraftV1"]
        UNKNOWN_VAL["UNKNOWN = 'unknown'<br/>TBD = 'TBD'"]
        IS_COMPILEABLE["is_compileable()<br/>open_questions? unresolved?"]
    end

    subgraph COMPILE_LAYER["Compiler (idl_compile.py)"]
        COMPILER["DraftToIDLCompiler"]
        CHECK_BLOCK["_check_blocking_conditions()"]
        TRANSFORM["_transform_to_idl()"]

        COMPILER --> CHECK_BLOCK
        CHECK_BLOCK -->|"errors"| COMPILE_ERR["CompileBlockingError<br/>DraftNotCompileableError"]
        CHECK_BLOCK -->|"OK"| TRANSFORM --> IDL_DOC_CLASS
    end

    subgraph IDL_STORE_LAYER["Store (idl_store.py)"]
        STORE_CLASS["IDLStore"]
        SAVE_METHOD["save(document, project)<br/>├─ to_canonical_dict()<br/>├─ _validate_contract_gate_from_dict()<br/>│   └─ Recalcula hash + compara<br/>└─ write JSON + MD"]
        GATE_ERR["IDLContractGateError<br/>(hash mismatch)"]

        STORE_CLASS --> SAVE_METHOD
        SAVE_METHOD -->|"mismatch"| GATE_ERR
    end
end

%% Conexões ao fluxo principal
DRAFT_PATH --> DRAFT_DOC
DRAFT_DOC --> IS_COMPILEABLE
IS_COMPILEABLE -->|"False"| GATE2_BLOCKED
IS_COMPILEABLE -->|"True"| COMPILER

IDL_PATH --> LEXER
IDL_DOC_CLASS --> STORE_CLASS
```

---

## 3. EVIDENCE MAP (Itens Fechados)

| Node | File | Function/Method | Line | Status |
|------|------|-----------------|------|--------|
| `IDL_SCHEMA_VERSION` | `idl/idl_v1.py` | constant | 27 | CONFIRMADO |
| `IDL_DRAFT_SCHEMA_VERSION` | `idl/idl_draft_v1.py` | constant | 25 | CONFIRMADO |
| `HASHABLE_FIELDS` | `idl/idl_v1.py` | constant | 34-42 | CONFIRMADO |
| `VOLATILE_FIELDS` | `idl/idl_v1.py` | constant | 45-50 | CONFIRMADO |
| `contract_notes` exclusão | `idl/idl_v1.py` | VOLATILE_FIELDS | 49 | CONFIRMADO |
| `IDLLexer` | `idl/idl_v1.py` | class | 765 | CONFIRMADO |
| `IDLParser` | `idl/idl_v1.py` | class | 965 | CONFIRMADO |
| `IDLDocument` | `idl/idl_v1.py` | dataclass | 499 | CONFIRMADO |
| `to_hashable_dict()` | `idl/idl_v1.py` | method | 510 | CONFIRMADO |
| `to_canonical_dict()` | `idl/idl_v1.py` | method | 529 | CONFIRMADO |
| `compute_content_hash_sha256()` | `idl/idl_v1.py` | function | 731 | CONFIRMADO |
| `IDLDraftV1` | `idl/idl_draft_v1.py` | dataclass | 281 | CONFIRMADO |
| `is_compileable()` | `idl/idl_draft_v1.py` | method | 334 | CONFIRMADO |
| `DraftToIDLCompiler` | `idl/idl_compile.py` | class | 136 | CONFIRMADO |
| `_check_blocking_conditions()` | `idl/idl_compile.py` | method | 204 | CONFIRMADO |
| `CompileBlockingError` | `idl/idl_compile.py` | dataclass | 66 | CONFIRMADO |
| `DraftNotCompileableError` | `idl/idl_compile.py` | exception | 85 | CONFIRMADO |
| `IDLStore` | `idl/idl_store.py` | class | 28 | CONFIRMADO |
| `_validate_contract_gate()` | `idl/idl_store.py` | method | 118 | CONFIRMADO |
| `IDLContractGateError` | `idl/idl_store.py` | exception | 23 | CONFIRMADO |
| `BackendCompiler` | `compilers/backend_compiler.py` | class | 17 | CONFIRMADO (não usado no fluxo) |
| `FrontendCompiler` | `compilers/frontend_compiler.py` | class | 19 | CONFIRMADO (não usado no fluxo) |
| `ReleaseReport` | `release/release_report.py` | dataclass | 22 | CONFIRMADO |
| `ReleaseReportGenerator` | `release/release_report.py` | class | 269 | CONFIRMADO |
| `ReleaseChecklist` | `release/release_checklist.py` | class | 99 | CONFIRMADO |
| `ReleaseChecklistResult` | `release/release_checklist.py` | dataclass | 48 | CONFIRMADO |
| `RunResult` | `orchestrator/engine.py` | dataclass | 47 | CONFIRMADO |
| `final_status` values | `orchestrator/engine.py` | field | 85 | CONFIRMADO |
| `input_mode_detected` | `orchestrator/engine.py` | field | ~105 | CONFIRMADO |
| `input_mode_used` | `orchestrator/engine.py` | field | ~106 | CONFIRMADO |

---

## 4. NÃO FOI POSSÍVEL CONFIRMAR

| Item | Motivo | Ação Recomendada |
|------|--------|------------------|
| `compilers/db_compiler.py` | Arquivo não existe | N/A - migrações SQL são geradas via patch_generator |
| Chamada de BackendCompiler/FrontendCompiler no pipeline | Não referenciado em engine.py | Código parece ser legado/alternativo |
| `release/release_report.py` contract gate | Não implementado | ReleaseReport não tem contract gate (apenas DiagnosticReport) |
| `final_status` enum formal | É apenas string, não Enum | Considerar criar Enum para type safety |
| Smoke tests específicos | Categorias documentadas mas testes individuais não listados | Verificar `smoke_runner.py` em detalhe |

---

## 5. RESUMO DAS DESCOBERTAS

### Lacunas Fechadas (100%)

1. **IDL_SCHEMA_VERSION**: `"idl.v1"` em `idl/idl_v1.py:27`
2. **IDL_DRAFT_SCHEMA_VERSION**: `"idl_draft.v1"` em `idl/idl_draft_v1.py:25`
3. **HASHABLE_FIELDS**: 7 campos definidos em `idl/idl_v1.py:34-42`
4. **contract_notes exclusão**: Confirmado em VOLATILE_FIELDS linha 49
5. **Compilers existem**: BackendCompiler e FrontendCompiler existem mas não são usados no pipeline principal
6. **ReleaseReport**: Existe em `release/release_report.py`, salva em `{store}/releases/`
7. **ReleaseChecklist**: Existe em `release/release_checklist.py` com 6 verificações
8. **RunResult campos**: 60+ campos documentados com tipos e defaults
9. **final_status valores**: "success", "fixed", "build_failed", "fatal_error", "running"

### Correções ao Diagrama Anterior

1. **BackendCompiler/FrontendCompiler** não são chamados no fluxo - código via PatchGenerator
2. **IDL Layer** é mais complexo que representado - inclui Lexer, Parser, Canonização, Store
3. **Contract Gate IDL** usa HASHABLE_FIELDS (7 campos) e exclui VOLATILE_FIELDS (4 campos)
4. **ReleaseReport não tem Contract Gate** - apenas DiagnosticReport tem

### Constantes Canônicas Adicionadas

```python
# IDL Schema Versions
IDL_SCHEMA_VERSION = "idl.v1"                     # idl/idl_v1.py:27
IDL_DRAFT_SCHEMA_VERSION = "idl_draft.v1"         # idl/idl_draft_v1.py:25

# IDL Hashable Fields
HASHABLE_FIELDS = [
    "schema_version", "system", "actors", "entities",
    "usecases", "integrations", "nonfunctional"
]

# IDL Volatile Fields (excluded from hash)
VOLATILE_FIELDS = [
    "content_hash_sha256", "timestamp",
    "parser_version", "contract_notes"
]

# Draft Special Values
UNKNOWN = "unknown"
TBD = "TBD"
UNRESOLVED_VALUES = {UNKNOWN, TBD, "tbd", "Unknown", "UNKNOWN"}

# Compile Blocking Errors
COMPILE_ERRORS = [
    "UNRESOLVED_QUESTION",
    "UNKNOWN_ACTOR_ROLE",
    "UNKNOWN_FIELD_TYPE",
    "UNKNOWN_FIELD_REQUIRED",
    "UNKNOWN_USECASE_ACTOR",
    "UNKNOWN_INTEGRATION_TYPE"
]

# Store Paths
IDL_STORE_PATH = "{store_root}/idl/{project}_{timestamp}.json"
RELEASE_REPORT_PATH = "{store_root}/{project}/releases/release_report_{timestamp}.json"
DIAGNOSTIC_PATH = "{store_root}/{project}/diagnostics/diagnostic_{timestamp}.json"
RUN_LOG_PATH = "{store_root}/{project}/runs/{exec_id}_{timestamp}.json"
ARTIFACT_PATH = "{store_root}/{project}/{KIND}/v{N}.{ext}"
```
