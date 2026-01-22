# Gaps e Decisões - OpenAPI from Registry (Etapa 6.5)

**Data:** 2026-01-21
**Status:** IMPLEMENTADO ✅
**Etapa:** 6.5

---

## 1. Gaps Identificados

### Gap 1: operationId com Prefixo "idl_"

**Problema:**
O `add_api_route()` em 6.4 usa `name=f"idl_{op.operation_id}"`, resultando em:
- OpenAPI mostra `operationId: idl_expense_create`
- Spec requer apenas `expense_create`

**Proposta de Resolução:**
- Modificar `idl_router.py` para usar `name=op.operation_id` diretamente
- Ou aplicar overlay para remover prefixo no OpenAPI final

**Impacto:** Baixo

---

### Gap 2: Responses do Registry Não Mapeadas

**Problema:**
O `Operation.errors` lista códigos de erro (ex: `[400, 401, 403, 404, 409, 422]`), mas:
- FastAPI não sabe desses erros
- `/openapi.json` não os inclui nas responses

**Proposta de Resolução:**
- Opção A: Passar `responses={code: {...} for code in op.errors}` ao `add_api_route()`
- Opção B: Aplicar overlay pós-geração

**Impacto:** Médio

---

### Gap 3: Header Idempotency-Key Não Documentado

**Problema:**
Quando `operation.idempotency == "required"`, o header `Idempotency-Key` deve aparecer no OpenAPI como obrigatório.

**Proposta de Resolução:**
- Adicionar parâmetro header na definição da operação se idempotency=required
- Overlay que adiciona parameter ao path/method

**Impacto:** Baixo

---

### Gap 4: Security Schemes Não Definidos por Modo

**Problema:**
O OpenAPI não declara os security schemes baseados em `ENGINE_AUTH_MODE`:
- `dev`: `X-Actor-Id` (header)
- `strict`: `X-Actor-Token` (header)

E headers adicionais:
- `X-Institution-Id` (quando multi-tenant)

**Proposta de Resolução:**
- Adicionar `securitySchemes` ao components
- Adicionar `security` requirement às operações

```yaml
components:
  securitySchemes:
    ActorIdHeader:
      type: apiKey
      in: header
      name: X-Actor-Id
    ActorTokenHeader:
      type: apiKey
      in: header
      name: X-Actor-Token
    InstitutionHeader:
      type: apiKey
      in: header
      name: X-Institution-Id
```

**Impacto:** Médio

---

### Gap 5: Endpoint `/d/{dept_id}/openapi.json` Não Existe

**Problema:**
Em bundle multi-dept, cada dept tem suas próprias operações.
Não há endpoint para obter OpenAPI filtrado por dept.

**Proposta de Resolução:**
- Criar rota `/d/{dept_id}/openapi.json`
- Filtrar paths que começam com `/d/{dept_id}/` ou são do dept específico
- Ou gerar OpenAPI do zero a partir do registry do dept

**Impacto:** Médio

---

### Gap 6: Tags Genéricas ("idl", "idl-dept")

**Problema:**
Tags atuais são genéricas:
- `["idl"]` para rotas base
- `["idl-dept"]` para rotas com `/d/{dept_id}/`

Spec requer tags por domínio (ex: "finance", "support", "approvals").

**Proposta de Resolução:**
- Derivar tag de `operation.path` (ex: `/finance/...` → tag "finance")
- Ou adicionar campo `tags` ao OperationSpec

**Impacto:** Baixo

---

### Gap 7: Request/Response Schemas Ausentes

**Problema:**
O OpenAPI não documenta schemas de request body e response body.
FastAPI gera schemas vazios ou genéricos.

**Proposta de Resolução (MVP):**
- Usar schema genérico `additionalProperties: true`
- Ou derivar de `bind.entity` se disponível

**Proposta de Resolução (futuro):**
- Definir schemas no bundle (openapi.yaml ou schema.json)
- Ou estender OperationSpec com campo `schema`

**Impacto:** Médio (MVP pode usar genérico)

---

### Gap 8: Validação de Idempotency-Key Não Implementada

**Problema:**
O campo `operation.idempotency` existe mas não é validado em runtime.
O engine aceita requests sem `Idempotency-Key` mesmo quando required.

**Proposta de Resolução (fora desta etapa):**
- Implementar middleware/handler que valida presença do header
- Retornar 400 se ausente e idempotency=required

**Impacto:** Fora do escopo 6.5 (apenas documentação OpenAPI)

---

## 2. Decisões Propostas

| # | Decisão | Proposta | Impacto |
|---|---------|----------|---------|
| D1 | Abordagem de implementação | **Opção A: Overlay** no FastAPI OpenAPI | Menor mudança |
| D2 | operationId | Usar `op.operation_id` sem prefixo | Simples |
| D3 | Errors mapping | Overlay adiciona responses do registry | Médio |
| D4 | Idempotency-Key | Adicionar como parameter se required | Baixo |
| D5 | Security schemes | Definir ambos (dev/strict) no schema | Médio |
| D6 | Endpoint por dept | Criar `/d/{dept_id}/openapi.json` | Médio |
| D7 | Tags | Derivar de path prefix | Baixo |
| D8 | Schemas request/response | Genérico para MVP (`additionalProperties`) | Baixo |

---

## 3. Proposta de Implementação (Opção A: Overlay)

### 3.1 Função `custom_openapi()`

```python
def create_custom_openapi(app: FastAPI, dept_id: Optional[str] = None) -> Dict:
    """Generate OpenAPI with registry enrichment."""

    # Start with FastAPI's generated schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Add security schemes
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "ActorIdHeader": {"type": "apiKey", "in": "header", "name": "X-Actor-Id"},
        "ActorTokenHeader": {"type": "apiKey", "in": "header", "name": "X-Actor-Token"},
        "InstitutionHeader": {"type": "apiKey", "in": "header", "name": "X-Institution-Id"},
    }

    # Enrich paths from registry
    ops_def = get_operations(dept_id)
    if ops_def:
        for op in ops_def.operations:
            _enrich_path_operation(openapi_schema, op)

    # Filter by dept if specified
    if dept_id:
        openapi_schema["paths"] = _filter_paths_by_dept(openapi_schema["paths"], dept_id)

    return openapi_schema
```

### 3.2 Função `_enrich_path_operation()`

```python
def _enrich_path_operation(schema: Dict, op: Operation) -> None:
    """Enrich OpenAPI path with registry data."""
    path_key = op.path
    method_key = op.method.lower()

    if path_key not in schema["paths"]:
        return
    if method_key not in schema["paths"][path_key]:
        return

    path_op = schema["paths"][path_key][method_key]

    # Fix operationId (remove idl_ prefix if present)
    if path_op.get("operationId", "").startswith("idl_"):
        path_op["operationId"] = op.operation_id

    # Add responses from errors
    path_op.setdefault("responses", {})
    for error_code in op.errors:
        code_str = str(error_code)
        if code_str not in path_op["responses"]:
            path_op["responses"][code_str] = {
                "description": _get_error_description(error_code)
            }

    # Add Idempotency-Key header if required
    if op.idempotency == "required":
        path_op.setdefault("parameters", [])
        if not any(p.get("name") == "Idempotency-Key" for p in path_op["parameters"]):
            path_op["parameters"].append({
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "Unique request identifier for idempotency",
            })

    # Add security
    auth_mode = get_auth_mode()
    if auth_mode == AuthMode.STRICT:
        path_op["security"] = [{"ActorTokenHeader": []}, {"InstitutionHeader": []}]
    else:
        path_op["security"] = [{"ActorIdHeader": []}]

    # Fix tags
    path_op["tags"] = [_derive_tag_from_path(op.path)]
```

### 3.3 Endpoint `/d/{dept_id}/openapi.json`

```python
@app.get("/d/{dept_id}/openapi.json", include_in_schema=False)
async def get_dept_openapi(dept_id: str):
    """Get OpenAPI schema filtered for a specific department."""
    schema = create_custom_openapi(app, dept_id=dept_id)
    return JSONResponse(content=schema)
```

---

## 4. Arquivos a Modificar

| Arquivo | Modificação | Linhas Est. |
|---------|-------------|-------------|
| `src/engine/api/server.py` | Customizar `app.openapi()` + novo endpoint | ~50 |
| `src/engine/core/idl_router.py` | Mudar `name` para usar `operation_id` direto | ~4 |
| `tests/test_openapi.py` | **NOVO** - Testes de OpenAPI | ~200 |

---

## 5. Critérios de Aceite Mapeados

| Critério (da spec) | Gap Relacionado | Solução |
|--------------------|-----------------|---------|
| operationId correto | Gap 1 | Remover prefixo "idl_" |
| responses com errors | Gap 2 | Overlay adiciona errors do registry |
| Idempotency-Key header | Gap 3 | Adiciona se idempotency=required |
| Security por modo | Gap 4 | securitySchemes + security por operação |
| `/d/{dept_id}/openapi.json` | Gap 5 | Novo endpoint |
| path param dept_id | Gap 5 | FastAPI já extrai |

---

## 6. Riscos Identificados

### Risco 1: Path Matching no Overlay

**Descrição:** FastAPI pode gerar paths diferentes do registry (ex: normalização).
**Mitigação:** Normalizar paths antes de comparar.

### Risco 2: Performance de Overlay

**Descrição:** Overlay executado a cada request de `/openapi.json`.
**Mitigação:** Cachear schema gerado (FastAPI já faz isso).

### Risco 3: Divergência Legacy vs IDL

**Descrição:** Rotas legacy não estão no registry, podem ter metadados diferentes.
**Mitigação:** Overlay só enriquece paths do registry, legacy mantém comportamento atual.

---

## 7. Perguntas Abertas

1. **Schemas detalhados:** Devemos incluir schemas completos de request/response ou manter genérico?
2. **Preflight warning:** Se ENGINE_AUTH_MODE=dev, incluir warning no OpenAPI info?
3. **Legacy routes:** Enriquecer rotas legacy também ou apenas IDL?

---

## 8. Implementação Realizada

### 8.1 Arquivos Criados/Modificados

| Arquivo | Descrição | Linhas |
|---------|-----------|--------|
| `src/engine/core/openapi_overlay.py` | **NOVO** - Módulo de overlay OpenAPI | ~334 |
| `src/engine/api/server.py` | Integração do overlay + endpoint dept | ~50 |
| `tests/test_openapi.py` | **NOVO** - 20 testes de OpenAPI | ~700 |

### 8.2 Gaps Resolvidos

| Gap | Status | Solução Implementada |
|-----|--------|---------------------|
| Gap 1: operationId prefixado | ✅ RESOLVIDO | Overlay substitui por `op.operation_id` exato |
| Gap 2: Responses não mapeadas | ✅ RESOLVIDO | Overlay adiciona errors do registry |
| Gap 3: Idempotency-Key | ✅ RESOLVIDO | Adicionado como header se idempotency=required |
| Gap 4: Security schemes | ✅ RESOLVIDO | 4 schemes definidos (ActorId, ActorToken, ActorRoles, Institution) |
| Gap 5: Endpoint por dept | ✅ RESOLVIDO | `/d/{dept_id}/openapi.json` criado |
| Gap 6: Tags genéricas | ✅ RESOLVIDO | Tags derivadas de path prefix (ex: `/finance/...` → "finance") |
| Gap 7: Schemas | ⏭️ ADIADO | FastAPI gera schemas genéricos (aceitável para MVP) |
| Gap 8: Validação runtime | ⏭️ FORA ESCOPO | Documentado mas não implementado (escopo 6.5 é apenas OpenAPI) |

### 8.3 Testes Implementados (20 testes)

```
tests/test_openapi.py::TestDeriveTagFromPath::test_simple_path
tests/test_openapi.py::TestDeriveTagFromPath::test_nested_path
tests/test_openapi.py::TestDeriveTagFromPath::test_path_with_param
tests/test_openapi.py::TestDeriveTagFromPath::test_dept_prefixed_path
tests/test_openapi.py::TestDeriveTagFromPath::test_root_path
tests/test_openapi.py::TestNormalizePathForMatching::test_single_param
tests/test_openapi.py::TestNormalizePathForMatching::test_multiple_params
tests/test_openapi.py::TestNormalizePathForMatching::test_no_params
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_has_security_schemes
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_has_correct_operation_id
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_has_error_responses
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_has_idempotency_header_when_required
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_no_idempotency_when_not_required
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_has_tags_from_path
tests/test_openapi.py::TestOpenAPISchemaGeneration::test_schema_has_security_on_operations
tests/test_openapi.py::TestOpenAPIEndpoint::test_openapi_endpoint_returns_schema
tests/test_openapi.py::TestDeptOpenAPIEndpoint::test_dept_openapi_returns_filtered_schema
tests/test_openapi.py::TestDeptOpenAPIEndpoint::test_dept_openapi_invalid_dept_returns_400
tests/test_openapi.py::TestMultiDeptOpenAPI::test_dept_variant_has_correct_operation_id
tests/test_openapi.py::TestMultiDeptOpenAPI::test_dept_variant_has_dept_id_parameter
```

### 8.4 Decisões Confirmadas

Todas as decisões D1-D8 foram implementadas conforme proposto:
- **D1**: Overlay no FastAPI OpenAPI ✅
- **D2**: operationId sem prefixo ✅
- **D3**: Errors do registry ✅
- **D4**: Idempotency-Key header ✅
- **D5**: Security schemes (dev/strict) ✅
- **D6**: Endpoint `/d/{dept_id}/openapi.json` ✅
- **D7**: Tags derivadas de path ✅
- **D8**: Schemas genéricos (FastAPI default) ✅
