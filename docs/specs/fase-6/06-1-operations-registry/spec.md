# Etapa 6.1 — ABI de Operações + OperationRegistry

**Status:** ✅ IMPLEMENTADO (2026-01-21)
**Objetivo:** habilitar o runtime a resolver operações definidas no contrato, por `(institution_id, dept_id)`, sem depender de handlers fixos.

## 1) Objetivo

Introduzir um contrato canônico de operações no bundle e um registry em runtime:

- contrato: `operations.json` (single-dept) ou `departments/<dept_id>/operations.json` (multi-dept)
- runtime: `OperationRegistry` com lookup determinístico:
  - key primária: `(method, path_template)`
  - key derivada: `endpoint_sig` (ex.: `POST /finance/expenses`)

## 2) Estado atual (realidade do código)

O runtime expõe rotas fixas e usa contratos para governança (rbac/sod/workflows/approvals/mandates/autonomy/policies/invariants), mas:

- não existe contrato institucional canônico para `operations` no bundle (apenas `openapi.yaml` opcional, e não executável)
- o loader não constrói um registry de operações em runtime

## 3) Decisões canônicas desta etapa

### 3.1 Contrato novo: `operations.json`

- `operations.json` é **derivado do IRCS/IDL**, emitido pelo ISE durante a compilação do bundle.
- `operations.json` deve ser determinístico (ordem estável, hashes coerentes com manifest/ledger).
- `operations.json` não executa nada sozinho; ele habilita o runtime a “saber quais operações existem”.

### 3.2 Compatibilidade

- Não quebrar bundles legados:
  - se `operations.json` não existir, o engine continua operando no modo atual (`legacy`)
- O modo `idl` (router/dispatcher) só será habilitado quando `operations.json` existir (etapas 6.4+).

## 4) Schema mínimo do `operations.json` (v1)

```json
{
  "operations_schema_version": "1.0",
  "dept_id": "finance",
  "operations": [
    {
      "operation_id": "expense_create",
      "method": "POST",
      "path": "/finance/expenses",
      "endpoint_sig": "POST /finance/expenses",
      "permission": "expense.create",
      "scope": "tenant",
      "idempotency": "required",
      "errors": [400, 401, 403],
      "bind": { "kind": "create", "entity": "Expense" }
    }
  ]
}
```

Notas:
- `endpoint_sig` é canônico (já usado em mandates/autonomy/policy).
- `permission` segue o modelo atual do runtime (ex.: `expense.create`) para compatibilidade com RBAC existente.

## 5) O que precisa mudar (mínimo)

- ISE: emitir `operations.json` por dept a partir do input canônico (IRCS→ParsedIDL adapter já existe).
- Bundle manifest: incluir `operations.json` como contract (required=true para bundles `idl`, required=false para legacy).
- Loader: carregar `operations.json` e construir `OperationRegistry` por dept.
- Runtime state: manter o registry acessível em memória para resolver operações.

## 6) O que não pode mudar

- Não remover rotas fixas existentes nesta etapa.
- Não introduzir dispatcher/execução genérica nesta etapa (isso é 6.2+).
- Não alterar a semântica dos gates existentes.

## 7) Eventos de ledger afetados

Nenhum evento novo obrigatório nesta etapa (somente carga e integridade de bundle já existente).  
Se houver evento de “bundle loaded”, ele pode incluir contagem de operações carregadas (opcional, sem quebrar ABI).

## 8) Critérios de aceite (Etapa 6.1)

- ✅ O ISE gera `operations.json` determinístico para:
  - ✅ single-dept (`finance-pilot`)
  - ✅ multi-dept (`multi-pilot`)
- ✅ O loader carrega `operations.json` e constrói um registry em memória:
  - ✅ lookup por `endpoint_sig`
  - ✅ lookup por `(method, path_template)`
- ✅ Testes provam:
  - ✅ schema válido (27 testes em `tests/test_operations.py`)
  - ✅ ordem determinística (sorted by method, path, operation_id)
  - ✅ compatibilidade com bundles sem `operations.json` (legacy)

## 9) Implementação Final

### Arquivos Criados/Modificados

| Arquivo | Descrição |
|---------|-----------|
| `src/engine/core/operations.py` | OperationRegistry, schema validation, lookup functions |
| `src/engine/ise/emit/operations_emit.py` | Emitter para operations.json |
| `src/engine/ise/emit/__init__.py` | Export do emit_operations |
| `src/engine/ise/compiler.py` | Integração do emit no _emit_all_contracts |
| `src/engine/ise/manifest.py` | operations.json como contrato opcional |
| `src/engine/loader/load_bundle.py` | Carregamento do operations.json |
| `tests/test_operations.py` | 27 testes unitários |

### API Pública

```python
from engine.core.operations import (
    get_operation_by_endpoint_sig,
    get_operation_by_method_path,
    get_operations,
)

# Lookup por endpoint_sig
op = get_operation_by_endpoint_sig(dept_id, "POST /finance/expenses")
if op:
    print(f"Permission: {op.permission}")

# Lookup por method + path
op = get_operation_by_method_path(dept_id, "POST", "/finance/expenses")
```

### Decisões Finais

1. **operations.json é opcional** (`required: false` no manifest) para compatibilidade com bundles legados
2. **Sem SAFE_MODE** para bundles sem operations.json - simplesmente opera em modo legacy
3. **Ordem determinística**: operations são sorted por `(method, path, operation_id)` antes de serializar
4. **Validação de segurança**: path deve ser absoluto (começar com `/`) e não pode conter `..`
5. **endpoint_sig deve corresponder** a `{method} {path}` - validação no parse

