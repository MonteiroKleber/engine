# 04-5 DSL/IR Expansion - Proposed Changes

**Status:** IMPLEMENTADO
**Data:** 2026-01-20
**Revisado:** 5 mudanças implementadas e testadas

---

## Resumo

Pacote mínimo de **5 mudanças** para expansão controlada do IDL DSL v1.2.2 subset e IRCS v1, focadas em:
- Melhorar mensagens de erro
- Garantir consistência do IRCS
- Adicionar validação semântica básica

---

## Mudanças Propostas

### CHANGE-1: Validação Semântica de Referências

**Prioridade:** ALTA
**Impacto:** Erro mais claro, previne bugs em runtime

**Descrição:**
Implementar segunda passagem de validação semântica no parser para verificar referências:
- Entidades em `applies_to`, `on`, `bind.entity`
- Campos em `Entity.field` expressions
- Workflows em `bind.workflow`
- Transitions em `bind.transition`
- Actors em `roles: [...]`

**Arquivos afetados:**
- `parser.py` - Adicionar método `_validate_semantic()`
- `errors.py` - Ativar códigos S001-S007

**Exemplo antes (aceita silenciosamente):**
```idl
invariant Test {
  applies_to: NonExistentEntity  // Não verificado
  when: always
  assert: NonExistentEntity.field > 0  // Não verificado
  severity: high
  message: "Error"
}
```

**Exemplo depois (erro claro):**
```
[IDL_S001_UNDEFINED_ENTITY] at 3:15: Undefined entity 'NonExistentEntity'
  | applies_to: NonExistentEntity
  |             ^~~~~~~~~~~~~~~~~
  | Hint: Defined entities are: Expense, Account
```

**Testes:**
- `test_semantic_undefined_entity`
- `test_semantic_undefined_field`
- `test_semantic_undefined_workflow`

---

### CHANGE-2: Guard Null → Always Explícito no IRCS

**Prioridade:** ALTA
**Impacto:** Consistência semântica, facilita consumo do IRCS

**Descrição:**
Quando uma transição omite `guard:`, emitir `{"kind": "always"}` em vez de `null`.

**Arquivos afetados:**
- `ircs_emit.py` - Método `_emit_transition()`

**IRCS antes:**
```json
{
  "name": "Submit",
  "from": "Draft",
  "to": "PendingApproval",
  "guard": null,
  "approvals": null,
  "effects": [...]
}
```

**IRCS depois:**
```json
{
  "name": "Submit",
  "from": "Draft",
  "to": "PendingApproval",
  "guard": {"kind": "always"},
  "approvals": null,
  "effects": [...]
}
```

**Testes:**
- `test_transition_guard_default_always`

---

### CHANGE-3: Required False Explícito no IRCS

**Prioridade:** ALTA
**Impacto:** Clareza semântica, facilita geração de código/docs

**Descrição:**
Emitir `required: false` explicitamente para campos sem modificador `required`.

**Arquivos afetados:**
- `ircs_emit.py` - Método `_emit_field()`, `_emit_context_field()`

**DSL:**
```idl
entity Example {
  field id: uuid required
  field notes: text  // Sem required
}
```

**IRCS antes:**
```json
{
  "fields": [
    {"name": "id", "type": "uuid", "required": true},
    {"name": "notes", "type": "text"}  // required omitido
  ]
}
```

**IRCS depois:**
```json
{
  "fields": [
    {"name": "id", "type": "uuid", "required": true},
    {"name": "notes", "type": "text", "required": false}  // explícito
  ]
}
```

**Testes:**
- `test_field_required_explicit`

---

### CHANGE-4: Mensagens de Erro com Hints

**Prioridade:** MÉDIA
**Impacto:** Melhor developer experience

**Descrição:**
Adicionar hints/suggestions às 10 mensagens de erro mais comuns:
1. `IDL_P016_EXPECTED_FIELD_TYPE` - lista tipos válidos
2. `IDL_P017_INVALID_ACTOR_TYPE` - lista human/system/external
3. `IDL_P018_INVALID_AUTH_METHOD` - lista métodos válidos
4. `IDL_P019_INVALID_SEVERITY` - lista low/medium/high/critical
5. `IDL_P020_INVALID_HTTP_METHOD` - lista GET/POST/PUT/PATCH/DELETE
6. `IDL_P021_INVALID_SCOPE` - lista own/tenant/department/all
7. `IDL_P022_INVALID_BIND_KIND` - lista create/read/update/delete/transition/approval
8. `IDL_P023_INVALID_HISTORY_ATTR` - lista actors/count/last_actor/last_at
9. `IDL_P025_INVALID_TENANCY` - lista single/multi
10. `IDL_P026_INVALID_IDEMPOTENCY` - lista required/optional/none

**Arquivos afetados:**
- `parser.py` - Métodos de parse que geram esses erros
- `errors.py` - Opcional: adicionar `hint` field à exception

**Exemplo antes:**
```
[IDL_P019_INVALID_SEVERITY] at 8:15: Invalid severity 'warning'
```

**Exemplo depois:**
```
[IDL_P019_INVALID_SEVERITY] at 8:15: Invalid severity 'warning'
  | severity: warning
  |           ^~~~~~~
  | Hint: Valid values are: low, medium, high, critical
```

**Testes:**
- `test_error_hint_severity`
- `test_error_hint_auth_method`

---

### CHANGE-5: Validação de Path Templates

**Prioridade:** MÉDIA
**Impacto:** Detecta erros comuns em endpoints

**Descrição:**
Validar sintaxe de path templates e extrair parâmetros:
1. Verificar que `{param}` segue padrão `[a-z_]+`
2. Emitir lista de `path_params` no IRCS
3. Warning se param não mapeia para campo da entidade (opcional)

**Arquivos afetados:**
- `parser.py` - Método `_parse_endpoint()`
- `ircs_emit.py` - Método `_emit_endpoint()`

**DSL:**
```idl
endpoint expense_get {
  method: GET
  path: "/finance/expenses/{id}"
  ...
}
```

**IRCS antes:**
```json
{
  "id": "expense_get",
  "method": "GET",
  "path": "/finance/expenses/{id}",
  ...
}
```

**IRCS depois:**
```json
{
  "id": "expense_get",
  "method": "GET",
  "path": "/finance/expenses/{id}",
  "path_params": ["id"],
  ...
}
```

**Erro para path inválido:**
```
[IDL_P029_INVALID_PATH_TEMPLATE] at 3:9: Invalid path template
  | path: "/finance/{Invalid-Param}/data"
  |                  ^~~~~~~~~~~~~
  | Hint: Path parameters must match pattern {param_name} where param_name is lowercase with underscores
```

**Arquivos:**
- Adicionar `IDL_P029_INVALID_PATH_TEMPLATE` em `errors.py`

**Testes:**
- `test_path_template_valid`
- `test_path_template_invalid`
- `test_path_params_extraction`

---

## Mudanças NÃO Incluídas (Fora do Escopo)

| Proposta | Razão para exclusão |
|----------|---------------------|
| Tipos `list<T>`, `set<T>` | Requer mudança significativa no lexer/parser |
| Operadores aritméticos (`+`, `-`) | Muda precedência de expressões, risco alto |
| Enum inline | Novo constructo, escopo maior |
| Doc comments (`///`) | Nice-to-have, não crítico |
| Source mapping | Complexidade alta, valor marginal |

---

## Plano de Implementação

### Fase 1: IRCS Consistency (Baixo risco)
1. CHANGE-2: Guard null → always
2. CHANGE-3: Required false explícito

**Estimativa:** ~20 linhas de código

### Fase 2: Error Hints (Médio risco)
3. CHANGE-4: Mensagens com hints

**Estimativa:** ~100 linhas de código

### Fase 3: Validação Semântica (Médio risco)
4. CHANGE-1: Validação de referências
5. CHANGE-5: Validação de path templates

**Estimativa:** ~200 linhas de código

---

## Compatibilidade

### Backward Compatibility (IRCS)
| Mudança | Breaking? | Mitigação |
|---------|-----------|-----------|
| CHANGE-2 | Não | `null` → `{kind: "always"}` é semanticamente equivalente |
| CHANGE-3 | Não | Campo já existia, agora sempre presente |
| CHANGE-5 | Não | Campo `path_params` é aditivo |

### Backward Compatibility (DSL)
| Mudança | Breaking? | Mitigação |
|---------|-----------|-----------|
| CHANGE-1 | Sim* | Erros novos para DSL inválido (comportamento correto) |
| CHANGE-4 | Não | Apenas melhora mensagens |
| CHANGE-5 | Sim* | Erros para paths inválidos (comportamento correto) |

*Breaking = rejeita DSL anteriormente aceito, mas que estava semanticamente incorreto.

---

## Testes Requeridos

| Mudança | Testes Novos | Arquivo |
|---------|--------------|---------|
| CHANGE-1 | 5+ | `test_idl_dsl.py` |
| CHANGE-2 | 1 | `test_idl_dsl.py` |
| CHANGE-3 | 1 | `test_idl_dsl.py` |
| CHANGE-4 | 3+ | `test_idl_dsl.py` |
| CHANGE-5 | 3+ | `test_idl_dsl.py` |

**Total:** ~15 novos testes

---

## Validação

### Critério de Sucesso
1. `examples/finance.idl` parseia sem erro
2. Output IRCS de `finance.idl` é determinístico (hash match)
3. Todos os testes novos passam
4. Todos os testes existentes continuam passando

### Comando de Verificação
```bash
cd /home/bazari/engine
python -m pytest tests/test_idl_dsl.py -v
python -m engine.idl_dsl examples/finance.idl --validate
python -m engine.idl_dsl examples/finance.idl -o /tmp/finance_ir.json
sha256sum /tmp/finance_ir.json  # Deve ser determinístico
```

---

## Definition of Done

- [x] CHANGE-1: Validação semântica implementada e testada
- [x] CHANGE-2: Guard null → always no IRCS
- [x] CHANGE-3: Required false explícito no IRCS (já estava implementado)
- [x] CHANGE-4: Hints em 10 mensagens de erro
- [x] CHANGE-5: Validação e extração de path params
- [x] `examples/finance.idl` continua funcionando
- [x] Testes existentes passando (61 testes)
- [x] 24 novos testes adicionados
- [x] Documentação atualizada (gaps.md)
