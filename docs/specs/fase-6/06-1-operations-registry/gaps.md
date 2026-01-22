# Gaps e Decisões - OperationRegistry

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.1.2 (Concluída)

---

## 1. Gaps Identificados (Resolvidos)

### ✅ Gap 1: ALLOWED_ENDPOINT_SIGS Hardcoded em Múltiplos Lugares

**Problema:**
Os `endpoint_sig` válidos estão duplicados em 3 módulos.

**Decisão Final:**
- Manter ALLOWED_ENDPOINT_SIGS como fallback para bundles legacy
- Para bundles com `operations.json`, registry pode ser consultado
- Refatoração completa adiada para Fase 6.4

---

### ✅ Gap 2: ISE não Emite `operations.json`

**Resolução:**
- Criado `src/engine/ise/emit/operations_emit.py`
- Integrado ao `_emit_all_contracts()` em `compiler.py`
- Emite de IRCS (canônico) ou ParsedIDL (fallback)

---

### ✅ Gap 3: IDL Parser não tem `IDLOperation`

**Decisão Final:**
- **Não modificar idl_parser.py** conforme spec 6.1.2
- O caminho canônico é DSL → IRCS → ISE
- `operations_emit.py` usa diretamente os dados do IRCS

---

### ✅ Gap 4: Loader não Carrega `operations.json`

**Resolução:**
- Criado `_load_operations_single_mode()` e `_load_operations_multi_mode()`
- Carregado **após** autonomy (step 7 no loader)
- Não adicionado a DEPT_REQUIRED_ARTIFACTS (mantém opcional)

---

### ✅ Gap 5: Não Existe `src/engine/core/operations.py`

**Resolução:**
- Criado com structs: `Operation`, `OperationsDef`
- Registry global com funções: `set_operations`, `get_operations`
- Lookup: `get_operation_by_endpoint_sig`, `get_operation_by_method_path`
- Registry é imutável após carga (conforme recomendação)

---

### Gap 6: `endpoint_sig` Derivado Manualmente em API Handlers

**Status:** Adiado para Fase 6.4
- Validação automática será implementada com dispatcher

---

### ✅ Gap 7: Schema `operations.json` Definido

**Resolução:**
- Schema implementado em `src/engine/core/operations.py:parse_operations_data()`
- Validações:
  - `operations_schema_version: "1.0"`
  - `method` in {GET, POST, PUT, PATCH, DELETE}
  - `path` absoluto (começa com `/`)
  - `path` sem `..` (segurança)
  - `endpoint_sig` deve corresponder a `{method} {path}`
  - `scope` in {tenant, global}
  - `idempotency` in {required, optional, none}

---

## 2. Decisões Finais

| # | Decisão | Resultado |
|---|---------|-----------|
| D1 | `operations.json` required no manifest? | `false` ✅ |
| D2 | Derivar operations de entities/usecases? | Sim, via IRCS ✅ |
| D3 | Deprecar ALLOWED_ENDPOINT_SIGS? | Não (manter fallback) ✅ |
| D4 | Ordem de carga no loader | Após autonomy (step 7) ✅ |
| D5 | Registry imutável? | Sim ✅ |
| D6 | Validação automática de endpoint_sig | Adiado para 6.4 |
| D7 | Local do JSON Schema | Inline em `operations.py` ✅ |

---

## 3. Checklist de Implementação 6.1.2 (DONE)

### ISE
- ✅ Criar `src/engine/ise/emit/operations_emit.py`
- ✅ Adicionar `emit_operations()` e `emit_operations_json()`
- ✅ Registrar em `src/engine/ise/emit/__init__.py`
- ✅ Adicionar ao `_emit_all_contracts()` em `compiler.py`
- ✅ Criar testes unitários

### Loader
- ✅ Criar `src/engine/core/operations.py`
- ✅ Implementar `load_operations_from_file()`
- ✅ Adicionar `_load_operations_single_mode()` em `load_bundle.py`
- ✅ Adicionar `_load_operations_multi_mode()` em `load_bundle.py`
- ✅ Criar testes unitários

### Manifest
- ✅ Atualizar `OPTIONAL_CONTRACTS` em `manifest.py` (required=false)

### Testes E2E
- ✅ Bundle single-dept com operations.json
- ✅ Bundle single-dept sem operations.json (legacy)
- ✅ Lookup por endpoint_sig
- ✅ Lookup por (method, path)

### Documentação
- ✅ spec.md atualizado com status IMPLEMENTADO
- ✅ map.md atualizado com status IMPLEMENTADO
- ✅ gaps.md atualizado com decisões finais

---

## 4. Riscos Mitigados

| Risco | Mitigação Implementada |
|-------|------------------------|
| Bundles existentes falham | `required: false`, legacy mode funciona |
| Mismatch operations vs rotas | 27 testes unitários |
| Performance lookup | List lookup (O(n) mas n é pequeno, típico <20) |
| Complexidade manutenção | Roadmap claro para consolidar em 6.4 |

---

## 5. Próximos Passos (Fase 6.2+)

1. **6.2**: Entity Handlers genéricos
2. **6.3**: Workflow Executor
3. **6.4**: Dynamic Dispatcher + validação automática de endpoint_sig
4. **6.5**: Consolidar ALLOWED_ENDPOINT_SIGS usando registry
