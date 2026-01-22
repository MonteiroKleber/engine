# Gaps e Decisões - Dynamic Router (Etapa 6.4)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.4 (Concluída)

---

## 1. Gaps Identificados e Status

### ✅ Gap 1: Não Existe ENGINE_API_MODE

**Problema:**
Não há variável de ambiente para controlar modo de operação (legacy/idl/both).

**Resolução Implementada:**
- Criado `get_api_mode()` em `idl_router.py`
- Default: `"legacy"` (comportamento atual)
- Valores válidos: `"legacy"`, `"idl"`, `"both"`

---

### ✅ Gap 2: Não Existe Função register_idl_routes()

**Problema:**
Não existe código que itere o OperationRegistry e registre rotas no FastAPI.

**Resolução Implementada:**
- Criado módulo `src/engine/core/idl_router.py`
- Função `register_idl_routes(app, departments) -> int`
- Retorna número de rotas registradas
- Suporta single-dept e multi-dept

---

### ✅ Gap 3: Não Existe Handler Wrapper Genérico

**Problema:**
Rotas IDL precisam de um handler genérico que:
- Extraia institution_id e dept_id
- Construa ActorContext
- Roteia para dispatcher correto baseado em `bind.kind`

**Resolução Implementada:**
- Criado `_create_idl_handler(operation, dept_from_path)` em `idl_router.py`
- Mapeia `bind.kind` para dispatcher:
  - `create` → `dispatch_create` ou `dispatch_approval_request`
  - `read` → `dispatch_read`
  - `approval_decide` → `dispatch_approval_decide`

---

### ✅ Gap 4: Detecção de Colisões Não Implementada

**Problema:**
Não há código para detectar se uma rota IDL colide com rota legacy existente.

**Resolução Implementada:**
- Criado `_has_collision(app, method, path) -> bool`
- Itera `app.routes` e compara path + methods
- Em modo `idl`: `RuntimeError` se colisão
- Em modo `both`: log warning e skip rota IDL

---

### ✅ Gap 5: Path Parameters Não Normalizados

**Problema:**
Rotas legacy usam `{expense_id}` e `{approval_id}` como path params.
Rotas IDL podem ter path templates diferentes no `operations.json`.

**Resolução Implementada:**
- Criado `_normalize_path_for_collision(path) -> str`
- Regex: `{[^}]+}` → `{param}`
- `/finance/expenses/{expense_id}` == `/finance/expenses/{id}` para detecção

---

### ✅ Gap 6: Não Existe Mapeamento bind.kind → Dispatcher

**Problema:**
O `bind.kind` em `operations.json` precisa ser mapeado para funções do dispatcher.

**Resolução Implementada:**
- Mapeamento implementado dentro de `_create_idl_handler()`:
  - `create` → verifica approval rule → `dispatch_approval_request` ou `dispatch_create`
  - `read` → `dispatch_read`
  - `approval_decide` → `dispatch_approval_decide`
- Retorna 501 para `bind.kind` desconhecido

---

### ✅ Gap 7: Dept-Scoped Routes Não Suportadas

**Problema:**
Em modo multi-dept, operações podem ser dept-scoped com path `/d/{dept}/...`.

**Decisão e Resolução:**
- Multi-dept registra **dois formatos** por operação:
  - Base: `path` como está (ex.: `/finance/expenses`)
  - Dept variant: `/d/{dept_id}` + `path` (ex.: `/d/{dept_id}/finance/expenses`)
- `dept_from_path` flag no handler indica se deve extrair dept_id do path param

---

### ✅ Gap 8: Request Body Parsing

**Problema:**
O handler wrapper precisa ler o body do request para passar ao dispatcher.

**Resolução Implementada:**
- Criado `_read_request_body(request) -> Dict`
- Usa `await request.body()` para ler bytes
- Parse JSON com fallback para dict vazio

---

### ✅ Gap 9: Path Params Extraction

**Problema:**
Para rotas como `/approvals/{approval_id}/decide`, o handler precisa extrair `approval_id`.

**Resolução Implementada:**
- Criado `_extract_path_params(request) -> Dict`
- Usa `request.path_params` diretamente
- FastAPI extrai automaticamente

---

### Mantido: Gap 10: OpenAPI Schema Generation

**Problema:**
Rotas dinâmicas podem não aparecer corretamente no `/docs` (Swagger UI).

**Decisão:**
- Manter para Fase 6.5+
- Rotas aparecem em `/docs` mas sem descrições customizadas
- Futuro: extrair metadata de `Operation` para `add_api_route()`

---

## 2. Decisões Finais

| # | Decisão | Resultado | Status |
|---|---------|-----------|--------|
| D1 | ENGINE_API_MODE default | `"legacy"` implementado | ✅ |
| D2 | Módulo para rotas IDL | `src/engine/core/idl_router.py` criado | ✅ |
| D3 | Colisão em modo `idl` | RuntimeError no startup | ✅ |
| D4 | Colisão em modo `both` | Skip + warning log | ✅ |
| D5 | Normalização de path params | `{[^}]+}` → `{param}` | ✅ |
| D6 | Dept-scoped paths | Dois formatos: base + `/d/{dept_id}` | ✅ |
| D7 | Testes | TestClient sem server real | ✅ |

---

## 3. Patch Implementado

### Arquivos Criados

| Arquivo | Linhas |
|---------|--------|
| `src/engine/core/idl_router.py` | ~300 |
| `tests/test_idl_router.py` | ~830 |

### Arquivos Modificados

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/api/server.py` | +20 linhas: import + chamada no lifespan |

### Arquivos NÃO Modificados (como planejado)

| Arquivo | Razão |
|---------|-------|
| `src/engine/core/dispatcher.py` | Reutilizado as-is |
| `src/engine/core/operations.py` | Reutilizado as-is |
| `src/engine/api/finance.py` | Rotas legacy mantidas |
| `src/engine/api/approvals.py` | Rotas legacy mantidas |

---

## 4. Critérios de Aceite - TODOS ATENDIDOS

| Critério | Como Validado | Status |
|----------|---------------|--------|
| ENGINE_API_MODE=idl funciona | `test_idl_expense_create_returns_202` | ✅ |
| POST /finance/expenses via dispatcher | `test_idl_expense_create_returns_202` | ✅ |
| POST /approvals/{id}/decide via dispatcher | `test_idl_approval_decide_returns_committed` | ✅ |
| ENGINE_API_MODE=legacy comportamento igual | `test_legacy_mode_registers_no_routes` | ✅ |
| ENGINE_API_MODE=both ambos funcionam | `test_both_mode_skips_collision` | ✅ |
| Rotas IDL em app.routes | `test_idl_mode_registers_routes` | ✅ |
| Colisão idl bloqueia startup | `test_idl_mode_fails_on_collision` | ✅ |
| Full approval flow via IDL | `test_idl_full_approval_flow` | ✅ |
| Multi-dept /d/{dept_id}/ | `test_dept_route_resolves_dept_id` | ✅ |

---

## 5. Riscos Mitigados

| Risco | Mitigação Implementada |
|-------|------------------------|
| Colisão com rotas legacy | Detecção + comportamento por modo |
| Path params com nomes diferentes | Normalização antes de comparar |
| Middlewares não executando | Confirmado: funcionam (no app global) |
| Hot reload em dev mode | Confirmado: lifespan re-executa |

---

## 6. Próximos Passos (Fase 6.5+)

1. **6.5**: Validação automática de endpoint_sig
2. **6.6**: OpenAPI schema customization para rotas IDL
3. **7.x**: Workflow engine genérico (se necessário)
