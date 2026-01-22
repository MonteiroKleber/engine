# Etapa 6.4 — Dynamic Router (IDL-driven HTTP)

**Status:** ✅ IMPLEMENTADO (2026-01-21)
**Pré-requisitos:** 6.1 ✅ (OperationRegistry) + 6.2 ✅ (CRUD) + 6.3 ✅ (Approvals)

## 1) Objetivo

Publicar, no FastAPI, rotas HTTP reais baseadas no `OperationRegistry`, de forma que:

- o engine exponha endpoints definidos no contrato (`operations.json`)
- cada request seja roteada para o **dispatcher** (não para handlers hardcoded)
- rotas legacy continuem funcionando (compatibilidade)

## 2) Estado atual (realidade do código)

- O engine registra rotas fixas (`finance.py`, `support.py`, `approvals.py`, etc.).
- Já existe `OperationRegistry` em runtime e dispatcher que executa create/read/approvals via `OperationSpec`.
- Ainda não existe um componente que:
  - gere rotas FastAPI a partir do registry
  - ou faça dispatch genérico via um único endpoint

## 3) Decisões canônicas desta etapa

### 3.1 Opção escolhida: rotas reais no FastAPI

Usar `app.add_api_route(path, handler, methods=[...])` para cada operação (melhor UX e mercado).

### 3.2 Modo de operação (compatibilidade)

Introduzir `ENGINE_API_MODE` com valores:

- `legacy` (default inicial): apenas rotas atuais
- `idl`: apenas rotas geradas do registry (para teste/migração)
- `both`: rotas legacy + rotas idl (para transição)

### 3.3 Segurança e governança

- AuthN continua sendo responsabilidade do engine (strict/dev já existe).
- AuthZ é feita pelos gates existentes via dispatcher.
- Não permitir "overlap silencioso":
  - se uma rota idl colidir com uma rota legacy no mesmo método/path, registrar em log e bloquear startup em `ENGINE_API_MODE=idl` (ou marcar como incompatível).

### 3.4 Multi-dept routing (decisão desta etapa)

Para bundles multi-dept, o router dinâmico registra **dois formatos** por operação:

- **base**: usa o `path` do `OperationSpec` como está (ex.: `/finance/expenses`)
- **dept variant**: registra também `/d/{dept_id}` + path (ex.: `/d/{dept_id}/finance/expenses`)

No handler, o `dept_id` vindo do path param é usado para resolver o `OperationSpec` correto no registry.
Não há rotas com dept fixo (ex.: `/d/finance/...` hardcoded). Sempre usa `{dept_id}`.

## 4) Design mínimo

### 4.1 Registro das rotas

No startup (após `load_bundle()` e `OperationRegistry` estar disponível):

- iterar operações por dept (`dept_id` pode ser `None`)
- registrar cada rota:
  - `path` (ex.: `/finance/expenses`)
  - `method`
  - handler wrapper único (`idl_route_handler`)

### 4.2 Handler wrapper

O handler wrapper deve:

1) extrair `institution_id` do header (obrigatório conforme config)
2) inferir `dept_id` (se path começar com `/d/{dept_id}/...` ou se a operação for dept-scoped no registry)
3) resolver `OperationSpec` via `(method, path_template)` e/ou `endpoint_sig`
4) chamar dispatcher correto:
   - `bind.kind=create` → `dispatch_create` ou `dispatch_approval_request`
   - `bind.kind=read` → `dispatch_read`
   - `bind.kind=approval_decide` → `dispatch_approval_decide`
5) retornar JSON com status code determinístico

## 5) O que não pode mudar

- Não remover rotas legacy nesta etapa.
- Não mexer na semântica dos gates.
- Não reescrever o dispatcher; apenas chamá-lo.

## 6) Critérios de aceite (Etapa 6.4)

- ✅ Com `ENGINE_API_MODE=idl`, o engine sobe e responde endpoints definidos no registry:
  - ✅ `POST /finance/expenses` (create via dispatcher)
  - ✅ `POST /approvals/{approval_id}/decide` (decide via dispatcher)
- ✅ Com `ENGINE_API_MODE=legacy`, comportamento permanece igual ao atual.
- ✅ Com `ENGINE_API_MODE=both`, ambos funcionam sem conflito fatal (se houver conflito, deve ser tratado conforme decisão 3.3).
- ✅ Testes provam:
  - ✅ rotas idl aparecem no `app.routes`
  - ✅ request via TestClient executa e retorna payload esperado (sem precisar de server real)

## 7) Implementação (2026-01-21)

### 7.1 Arquivos Criados

| Arquivo | Descrição |
|---------|-----------|
| `src/engine/core/idl_router.py` | Módulo principal do dynamic router |
| `tests/test_idl_router.py` | 21 testes cobrindo todos critérios |

### 7.2 Arquivos Modificados

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/api/server.py` | Adicionado import e chamada `register_idl_routes()` no lifespan |

### 7.3 Novas Funções

```python
# src/engine/core/idl_router.py

def get_api_mode() -> str:
    """Get API mode from ENGINE_API_MODE env var.
    Returns: "legacy" (default), "idl", or "both".
    """

def register_idl_routes(app: FastAPI, departments: Optional[List[str]] = None) -> int:
    """Register IDL routes from OperationRegistry.
    Called during app startup (lifespan) after load_bundle().
    Returns: Number of routes registered.
    Raises: RuntimeError in 'idl' mode if collision detected.
    """
```

### 7.4 Lógica de Registro

```python
# No lifespan (server.py)
api_mode = get_api_mode()
if api_mode != API_MODE_LEGACY:
    bundle_ctx = get_bundle_context()
    departments = None
    if bundle_ctx and bundle_ctx.mode == "multi":
        departments = list(bundle_ctx.departments.keys())
    routes_count = register_idl_routes(app, departments=departments)
```

### 7.5 Handler Wrapper

O handler genérico `_create_idl_handler()` cria closures para cada operação:

```python
async def idl_handler(request: Request) -> JSONResponse:
    # 1. Build actor context from headers
    actor = _build_actor_context_from_request(request)

    # 2. Get institution_id
    institution_id = get_request_institution_id(request) or headers

    # 3. Resolve dept_id (from path param or request context)
    dept_id = path_params.get("dept_id") if dept_from_path else get_request_dept()

    # 4. Route to dispatcher based on bind.kind
    if bind_kind == "create":
        # Check if approval required
        if rule exists:
            result = await dispatch_approval_request(...)
        else:
            result = await dispatch_create(...)
    elif bind_kind == "read":
        result = await dispatch_read(...)
    elif bind_kind == "approval_decide":
        result = await dispatch_approval_decide(...)

    return JSONResponse(status_code=result.status_code, content=result.response_body)
```

### 7.6 Detecção de Colisões

```python
def _normalize_path_for_collision(path: str) -> str:
    """Normalize path params: {expense_id} → {param}"""
    return re.sub(r"\{[^}]+\}", "{param}", path)

def _has_collision(app: FastAPI, method: str, path: str) -> bool:
    """Check if route already exists after normalization."""
```

Comportamento por modo:
- `idl`: colisão → `RuntimeError` (startup falha)
- `both`: colisão → skip + warning log

### 7.7 Testes Implementados

| Classe | Testes | Cobertura |
|--------|--------|-----------|
| `TestPathNormalization` | 3 | Normalização de path params |
| `TestCollisionDetection` | 4 | Detecção de rotas existentes |
| `TestApiModeEnvVar` | 4 | ENGINE_API_MODE handling |
| `TestIdlRouteRegistration` | 5 | Registro de rotas por modo |
| `TestIdlRouteExecution` | 4 | Full approval flow via IDL |
| `TestIdlMultiDeptRoutes` | 1 | Multi-dept /d/{dept_id}/ prefix |

**Total: 21 testes, todos passando**

## 8) Riscos Mitigados

| Risco | Mitigação |
|-------|-----------|
| Colisão com rotas legacy | Detecção e tratamento por modo |
| Path params com nomes diferentes | Normalização antes de comparar |
| Middlewares não executando | Middlewares são no app global, funcionam |
| Hot reload em dev mode | Lifespan re-executa registro |
