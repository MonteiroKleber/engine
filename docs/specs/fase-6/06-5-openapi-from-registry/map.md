# Mapeamento - OpenAPI from Registry (Etapa 6.5)

**Data:** 2026-01-21
**Status:** IMPLEMENTADO ✅
**Etapa:** 6.5

---

## 1. Objetivo da Etapa

Garantir que o engine exponha documentação OpenAPI **derivada do contrato ativo** (`OperationRegistry`), incluindo:
- Operações do registry com `operationId`, `method`, `path`, `errors`
- Headers obrigatórios por modo de autenticação
- Rotas multi-dept com path param `{dept_id}`

---

## 2. Geração Atual do OpenAPI pelo FastAPI

### 2.1 Mecanismo Nativo

FastAPI gera automaticamente `/openapi.json` baseado em:
- Rotas registradas via `@router.get()`, `@router.post()`, etc.
- Rotas adicionadas via `app.add_api_route()`
- Dependências (Header, Query, Body) usadas nas funções

**Arquivo principal:** `src/engine/api/server.py`

```python
app = FastAPI(title="Libervia Engine", version="8.1.1", lifespan=lifespan)
```

### 2.2 Rotas Incluídas no OpenAPI Atual

| Tipo | Quantidade | operationId |
|------|------------|-------------|
| Rotas legacy (finance, support, approvals) | ~30 | Gerados automaticamente por FastAPI |
| Rotas IDL (após 6.4) | Variável | `idl_{operation_id}` ou `idl_dept_{operation_id}` |
| Rotas admin | ~40 | Gerados automaticamente |
| Console | ~15 | Gerados automaticamente |

### 2.3 Parâmetros nas Rotas IDL (6.4)

**Arquivo:** `src/engine/core/idl_router.py:373-427`

```python
app.add_api_route(
    path=op.path,
    endpoint=handler,
    methods=[op.method],
    name=f"idl_{op.operation_id}",  # <-- operationId = name
    tags=["idl"],
)

# Multi-dept variant
app.add_api_route(
    path=dept_path,
    endpoint=handler,
    methods=[op.method],
    name=f"idl_dept_{op.operation_id}",
    tags=["idl-dept"],
)
```

### 2.4 O Que Aparece no OpenAPI Gerado

| Campo | Valor Atual | Problema |
|-------|-------------|----------|
| `operationId` | `idl_expense_create` | OK (mas com prefixo "idl_") |
| `tags` | `["idl"]` ou `["idl-dept"]` | Genérico, não por domínio |
| `parameters` | Path params extraídos | OK |
| `requestBody` | Não especificado | Falta schema |
| `responses` | Não especificado | Falta errors do registry |
| `security` | Não especificado | Falta auth headers |

---

## 3. Campos Disponíveis no OperationSpec

### 3.1 Dataclass Operation

**Arquivo:** `src/engine/core/operations.py:37-48`

```python
@dataclass
class Operation:
    operation_id: str      # e.g., "expense_create"
    method: str            # GET, POST, PUT, PATCH, DELETE
    path: str              # e.g., "/finance/expenses"
    endpoint_sig: str      # e.g., "POST /finance/expenses"
    permission: str        # e.g., "expense.create"
    scope: str             # "tenant" or "global"
    idempotency: str       # "required", "optional", "none"
    errors: List[int]      # [400, 401, 403, 404, 409, 422]
    bind: Optional[Dict]   # {"kind": "create", "entity": "Expense"}
```

### 3.2 Mapeamento para OpenAPI

| Campo Operation | Campo OpenAPI | Como Usar |
|-----------------|---------------|-----------|
| `operation_id` | `operationId` | Direto |
| `method` | HTTP method | Direto |
| `path` | Path template | Direto |
| `errors` | `responses.{code}` | Iterar lista |
| `idempotency` | `parameters` (Idempotency-Key) | Se "required" |
| `bind.entity` | Tags, schema ref | Se disponível |
| `scope` | Security requirements | "tenant" → requer headers |

### 3.3 Campos Ausentes no OperationSpec

| Campo OpenAPI | Status | Resolução Proposta |
|---------------|--------|-------------------|
| `summary` | Não existe | Derivar de `operation_id` |
| `description` | Não existe | Opcional |
| `requestBody.schema` | Não existe | Schema genérico ou por `bind.entity` |
| `security` | Não existe | Derivar de `ENGINE_AUTH_MODE` |

---

## 4. Headers Obrigatórios por Modo

### 4.1 ENGINE_AUTH_MODE

**Arquivo:** `src/engine/core/actor_context.py:28-36`

```python
def get_auth_mode() -> AuthMode:
    mode = os.environ.get("ENGINE_AUTH_MODE", "dev").lower()
    if mode == "strict":
        return AuthMode.STRICT
    return AuthMode.DEV
```

### 4.2 Headers por Modo

| Modo | Headers Obrigatórios | Arquivo |
|------|---------------------|---------|
| `dev` | `X-Actor-Id`, `X-Actor-Roles` (opcional) | dependencies.py:70-72 |
| `strict` | `X-Actor-Token` | dependencies.py:73 |
| Ambos | `X-Institution-Id` (quando multi-tenant) | dependencies.py:74 |

### 4.3 Header Idempotency-Key

**Quando:** `operation.idempotency == "required"`

Não está implementado atualmente no engine. O campo existe no OperationSpec mas não é validado.

### 4.4 Documentação Existente nos Headers

**Arquivo:** `src/engine/api/server.py:318`

```python
allow_headers=[
    "Content-Type",
    "X-Actor-Id",
    "X-Actor-Roles",
    "X-Tenant-Id",
    "X-Institution-Id",
    "X-Request-Id",
    "X-Actor-Token"
],
```

---

## 5. Geração OpenAPI Existente (ISE Emit)

### 5.1 Módulo ISE

**Arquivo:** `src/engine/ise/emit/openapi_emit.py`

Já existe código para gerar OpenAPI a partir do IDL:

```python
def emit_openapi(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit OpenAPI spec from parsed IDL."""
    # Gera paths, schemas, securitySchemes
```

### 5.2 Estrutura Gerada

```python
return {
    "openapi": "3.0.3",
    "info": {"title": f"{parsed.system_name} API", "version": parsed.version},
    "paths": dict(sorted(paths.items())),
    "components": {
        "schemas": {...},
        "securitySchemes": {
            "ActorHeader": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Actor-Id"
            }
        }
    }
}
```

### 5.3 Limitação

ISE emit é usado no **build time** (pipeline), não em **runtime**.
O engine não usa esse OpenAPI gerado.

---

## 6. Superfícies OpenAPI Necessárias

### 6.1 Endpoints Requeridos

| Endpoint | Escopo | Status |
|----------|--------|--------|
| `/openapi.json` | Global (todas operações) | ✅ Existe (FastAPI nativo) |
| `/d/{dept_id}/openapi.json` | Por dept (operações do dept) | ❌ Não existe |

### 6.2 Comportamento por ENGINE_API_MODE

| Modo | `/openapi.json` contém |
|------|------------------------|
| `legacy` | Rotas legacy apenas |
| `idl` | Rotas IDL apenas |
| `both` | Rotas legacy + IDL |

---

## 7. Opções de Implementação

### 7.1 Opção A: Overlay no FastAPI OpenAPI

**Abordagem:** Customizar o OpenAPI gerado pelo FastAPI adicionando metadados.

```python
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Enrich with registry data
    for dept_id in depts:
        ops_def = get_operations(dept_id)
        for op in ops_def.operations:
            path_key = op.path
            if path_key in openapi_schema["paths"]:
                # Add errors from registry
                # Add idempotency header
                # Add security requirements
                pass

    app.openapi_schema = openapi_schema
    return app.openapi_schema
```

**Prós:**
- Mantém rotas legacy no schema
- FastAPI cuida de path params automaticamente
- Menor código

**Contras:**
- Complexidade de matching path templates
- Overlay pode não capturar tudo

### 7.2 Opção B: OpenAPI do Zero a partir do Registry

**Abordagem:** Ignorar FastAPI e gerar OpenAPI programaticamente.

```python
def generate_openapi_from_registry(dept_id: Optional[str] = None) -> Dict:
    ops_def = get_operations(dept_id)
    paths = {}

    for op in ops_def.operations:
        paths[op.path] = {
            op.method.lower(): {
                "operationId": op.operation_id,
                "responses": {str(e): {"description": f"Error {e}"} for e in op.errors},
                # ... mais campos
            }
        }

    return {
        "openapi": "3.0.3",
        "info": {...},
        "paths": paths,
        "components": {...}
    }
```

**Prós:**
- Fonte de verdade única (registry)
- Controle total sobre o schema
- Fácil gerar por dept

**Contras:**
- Não inclui rotas legacy
- Duplica lógica de path params
- Mais código a manter

### 7.3 Recomendação

**Opção A (Overlay)** é preferível porque:
1. Mantém compatibilidade com rotas legacy
2. Aproveita parsing de path params do FastAPI
3. Menor superfície de mudança
4. `/d/{dept_id}/openapi.json` pode filtrar paths por prefixo

---

## 8. Arquivos Relevantes

| Arquivo | Função |
|---------|--------|
| `src/engine/api/server.py` | App FastAPI, lifespan |
| `src/engine/core/idl_router.py` | Registro de rotas IDL |
| `src/engine/core/operations.py` | OperationRegistry |
| `src/engine/api/dependencies.py` | Headers de auth |
| `src/engine/ise/emit/openapi_emit.py` | Geração OpenAPI (build time) |

---

## 9. Resumo do Mapeamento (Pós-Implementação)

| Item | Status | Localização |
|------|--------|-------------|
| OpenAPI gerado pelo FastAPI | ✅ Existe | /openapi.json |
| Rotas IDL no OpenAPI | ✅ Incluídas (6.4) | idl_router.py |
| operationId correto | ✅ **IMPLEMENTADO** | openapi_overlay.py - usa `op.operation_id` exato |
| Errors do registry | ✅ **IMPLEMENTADO** | openapi_overlay.py - `_enrich_operation_from_registry()` |
| Idempotency header | ✅ **IMPLEMENTADO** | Adicionado se `idempotency=required` |
| Auth headers (dev/strict) | ✅ **IMPLEMENTADO** | 4 security schemes definidos |
| OpenAPI por dept | ✅ **IMPLEMENTADO** | `/d/{dept_id}/openapi.json` |
| Schemas de request/response | ⏭️ Genéricos (MVP) | FastAPI gera schemas default |

---

## 10. Arquivos Criados na Implementação

| Arquivo | Descrição |
|---------|-----------|
| `src/engine/core/openapi_overlay.py` | Módulo de overlay OpenAPI com funções de enriquecimento |
| `tests/test_openapi.py` | 20 testes cobrindo todos os requisitos da spec |

## 11. Funções Principais Implementadas

```python
# src/engine/core/openapi_overlay.py

def create_openapi_schema(app, dept_id=None, filter_by_dept=False):
    """Create OpenAPI schema with registry enrichment."""

def setup_custom_openapi(app):
    """Setup custom OpenAPI generation for the app."""

def _enrich_operation_from_registry(path_item, method, op):
    """Enrich operation with operationId, errors, idempotency, security, tags."""

def _derive_tag_from_path(path):
    """Derive tag from path prefix (e.g., /finance/... → 'finance')."""

def _build_security_schemes():
    """Build security schemes (ActorIdHeader, ActorTokenHeader, etc.)."""
```
