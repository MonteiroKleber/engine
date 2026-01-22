# 04-5 DSL/IR Expansion - Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-20
**Revisado:** Implementação das 5 mudanças aprovadas completa

---

## Resumo

Análise das limitações atuais do `engine.idl_dsl` (IDL DSL v1.2.2 subset) e IRCS v1 emitter para identificar oportunidades de expansão controlada.

---

## Estado Atual

### 1. Visão Geral do Parser

| Componente | Arquivo | LOC | Status |
|------------|---------|-----|--------|
| Lexer | `lexer.py` | ~310 | ✅ Completo |
| Tokens | `tokens.py` | ~345 | ✅ Completo |
| AST | `ast_nodes.py` | ~290 | ✅ Completo |
| Parser | `parser.py` | ~1450 | ✅ Completo |
| Emitter | `ircs_emit.py` | ~465 | ✅ Completo |
| Errors | `errors.py` | ~165 | ✅ Completo |
| CLI | `__main__.py` | ~90 | ✅ Completo |

**Total:** ~3100 LOC (Python puro, sem dependências externas)

---

### 2. Seções Suportadas (8/8)

| Seção | Status | Observações |
|-------|--------|-------------|
| `system` | ✅ | Metadados completos |
| `actors` | ✅ | 3 tipos, 5 auth methods |
| `entities` | ✅ | Storage config, 10 tipos primitivos |
| `policy_context` | ✅ | Schema com defaults |
| `invariants` | ✅ | When/assert expressions |
| `separation_of_duties` | ✅ | Forbid com history() |
| `workflows` | ✅ | States, transitions, approvals |
| `operations` | ✅ | API endpoints com bind spec |

---

### 3. Tipos Primitivos Suportados

| Tipo | Token | Uso no finance.idl |
|------|-------|---------------------|
| `string` | TYPE_STRING | ✅ |
| `text` | TYPE_TEXT | ✅ |
| `int` | TYPE_INT | ✅ |
| `float` | TYPE_FLOAT | - |
| `decimal` | TYPE_DECIMAL | ✅ |
| `bool` | TYPE_BOOL | ✅ |
| `datetime` | TYPE_DATETIME | ✅ |
| `uuid` | TYPE_UUID | ✅ |
| `void` | TYPE_VOID | ✅ |
| `any` | TYPE_ANY | ✅ |

---

### 4. Expression Language (Predicados)

**Operadores implementados:**
```
Precedência (menor → maior):
1. OR  (left-associative)
2. AND (left-associative)
3. NOT (prefix)
4. ==, !=, >, >=, <, <=, in
```

**Valores suportados:**
- Literais: `42`, `3.14`, `"string"`, `true`, `false`
- Referências: `Entity.field`, `actor.id`, `context.var`
- Função: `history("StepName").attr`

**Atributos de history() (4):**
| Atributo | Tipo Inferido | Descrição |
|----------|---------------|-----------|
| `actors` | `set<uuid>` | Set de atores que executaram |
| `count` | `int` | Contagem de execuções |
| `last_actor` | `uuid` | Último ator |
| `last_at` | `datetime` | Timestamp da última execução |

---

### 5. Workflow Effects (Limitados)

**Implementados:**
| Effect | Sintaxe | IRCS Output |
|--------|---------|-------------|
| `set_state` | `set_state("NewState")` | `{kind: "set_state", value: "..."}` |
| `bump_version` | `bump_version(1)` | `{kind: "bump_version", field: "version", by: 1}` |

**Não implementados (potenciais):**
- `emit_event(...)` - Emitir evento customizado
- `set_field(...)` - Definir valor de campo
- `call_hook(...)` - Invocar hook externo

---

### 6. Bind Kinds (Operations)

| Kind | Suportado | Uso |
|------|-----------|-----|
| `create` | ✅ | CRUD create |
| `read` | ✅ | CRUD read |
| `update` | ✅ | CRUD update |
| `delete` | ✅ | CRUD delete |
| `transition` | ✅ | Workflow transition |
| `approval` | ✅ | Approval decision |

---

## Gaps Identificados

### GAP-1: Falta de Tipos de Lista/Set

**Impacto:** Médio
**Área:** `entities`, `policy_context`

**Problema:**
Não há sintaxe para declarar campos do tipo lista ou set:
```idl
// Desejado (não suportado)
field tags: list<string>
field approvers: set<uuid>
```

**Workaround atual:**
Usar `text` com serialização JSON ou `any`.

**Proposta:**
Adicionar `list<T>` e `set<T>` ao lexer/parser com emissão em IRCS.

---

### GAP-2: Validação Semântica Incompleta

**Impacto:** Alto
**Área:** Parser, semantic validation

**Problemas identificados:**

1. **Referências não validadas:** `Entity.field` no parser não verifica se a entidade/campo existe.
2. **Workflow refs não validados:** `bind.workflow` e `bind.transition` não verificam existência.
3. **Role refs não validados:** `roles: [manager]` não verifica se actor existe.

**Erros definidos mas não utilizados:**
- `IDL_S001_UNDEFINED_ENTITY`
- `IDL_S002_UNDEFINED_ACTOR`
- `IDL_S003_UNDEFINED_WORKFLOW`
- `IDL_S004_UNDEFINED_TRANSITION`
- `IDL_S005_UNDEFINED_STATE`
- `IDL_S006_UNDEFINED_FIELD`
- `IDL_S007_TYPE_MISMATCH`

**Proposta:**
Implementar segunda passagem de validação semântica no parser.

---

### GAP-3: Mensagens de Erro Sem Contexto Rico

**Impacto:** Médio
**Área:** Error reporting

**Problema:**
Algumas mensagens de erro não incluem contexto suficiente para debugging:
```
[IDL_P016_EXPECTED_FIELD_TYPE] at 52:12: Expected field type
```

**Desejado:**
```
[IDL_P016_EXPECTED_FIELD_TYPE] at 52:12: Expected field type
  | field amount: xxx
  |              ^
  | Hint: Valid types are: string, text, int, float, decimal, bool, datetime, uuid, or entity name
```

**Proposta:**
Adicionar hints/suggestions às mensagens de erro comuns.

---

### GAP-4: Falta de Operador Aritmético em Expressões

**Impacto:** Baixo
**Área:** Expression language

**Problema:**
Não é possível fazer comparações com aritmética:
```idl
// Desejado (não suportado)
assert: Account.balance - Expense.amount >= 0
guard: context.threshold + 100 < Expense.amount
```

**Workaround atual:**
Usar campos pré-computados ou lógica no runtime.

**Proposta:**
Adicionar `+`, `-`, `*`, `/` com precedência correta (menor que comparações).

---

### GAP-5: Endpoint Path Templates Não Validados

**Impacto:** Médio
**Área:** Operations

**Problema:**
Path templates como `/finance/expenses/{id}` não são validados:
- Sintaxe de template não verificada
- Parâmetros não mapeados para campos da entidade

**Proposta:**
Validar sintaxe de path template e emitir lista de path params no IRCS.

---

### GAP-6: Falta de Default para Campos Opcionais

**Impacto:** Baixo
**Área:** Entities

**Problema:**
Campo sem `required` não tem semântica clara:
```idl
field notes: text  // É opcional? Qual o default?
```

**Proposta:**
Emitir `required: false` explicitamente no IRCS para campos sem `required`.

---

### GAP-7: Workflow State Transition Guards Inconsistentes

**Impacto:** Médio
**Área:** Workflows

**Problema:**
Transição com `approvals` mas sem `guard` implica guard=always, mas isso não é explícito no IRCS:
```json
{
  "guard": null,  // Significa always?
  "approvals": {...}
}
```

**Proposta:**
Emitir `guard: {"kind": "always"}` quando omitido, garantindo semântica explícita.

---

### GAP-8: Falta de Suporte a Comentários de Documentação

**Impacto:** Baixo
**Área:** Lexer, emitter

**Problema:**
Comentários `//` e `/* */` são ignorados pelo lexer, não preservados no IRCS.

**Proposta:**
Adicionar `///` como doc-comment e emitir em campo `doc` no IRCS para elementos.

---

### GAP-9: IRCS Não Inclui Source Mapping

**Impacto:** Médio
**Área:** IRCS emitter

**Problema:**
Não há mapeamento de volta para linhas/colunas do source DSL.

**Proposta:**
Adicionar `source_map` opcional com ranges para cada elemento emitido.

---

### GAP-10: Falta de Suporte a Enum Inline

**Impacto:** Médio
**Área:** Entities, expressions

**Problema:**
Não há sintaxe para definir enum inline:
```idl
// Desejado (não suportado)
field status: enum(draft, pending, approved, rejected)
```

**Workaround atual:**
Usar `string` + invariant para validação.

**Proposta:**
Adicionar `enum(...)` como tipo de campo com valores possíveis.

---

## Priorização

### Alta Prioridade (valor imediato)
1. **GAP-2:** Validação semântica (erros mais claros) ✅ **IMPLEMENTADO (CHANGE-1)**
2. **GAP-7:** Guard null → always explícito (IRCS consistency) ✅ **IMPLEMENTADO (CHANGE-2)**
3. **GAP-6:** Required false explícito (IRCS clarity) ✅ **JÁ ESTAVA IMPLEMENTADO (CHANGE-3)**

### Média Prioridade (melhoria de DX)
4. **GAP-3:** Mensagens de erro com hints ✅ **IMPLEMENTADO (CHANGE-4)**
5. **GAP-5:** Validação de path templates ✅ **IMPLEMENTADO (CHANGE-5)**

### Baixa Prioridade (expansão futura)
6. **GAP-1:** Tipos list/set ⏳ Pendente
7. **GAP-10:** Enum inline ⏳ Pendente
8. **GAP-4:** Operadores aritméticos ⏳ Pendente
9. **GAP-8:** Doc comments ⏳ Pendente
10. **GAP-9:** Source mapping ⏳ Pendente

---

## Compatibilidade

Qualquer mudança deve garantir:
- `examples/finance.idl` continua parseando sem erro
- Output IRCS é backward-compatible (novas chaves opcionais)
- Determinismo mantido (same input → same output)

---

## Arquivos de Referência

| Arquivo | Descrição |
|---------|-----------|
| [src/engine/idl_dsl/tokens.py](src/engine/idl_dsl/tokens.py) | 140+ token types |
| [src/engine/idl_dsl/errors.py](src/engine/idl_dsl/errors.py) | 50+ error codes (+ IDL_P029_INVALID_PATH_TEMPLATE) |
| [src/engine/idl_dsl/parser.py](src/engine/idl_dsl/parser.py) | Recursive descent parser (+ semantic validation) |
| [src/engine/idl_dsl/ircs_emit.py](src/engine/idl_dsl/ircs_emit.py) | IRCS v1 emitter (+ guard always, path_params) |
| [src/engine/idl_dsl/ast_nodes.py](src/engine/idl_dsl/ast_nodes.py) | AST nodes (+ path_params field) |
| [examples/finance.idl](examples/finance.idl) | Canonical example (202 lines) |
| [tests/test_idl_dsl.py](tests/test_idl_dsl.py) | Test suite (61 tests, ~1000 lines) |

---

## Implementação Realizada (2026-01-20)

### Mudanças Implementadas

| ID | Mudança | Arquivos | LOC |
|----|---------|----------|-----|
| CHANGE-1 | Validação semântica de referências | parser.py | ~100 |
| CHANGE-2 | Guard null → always explícito | ircs_emit.py | ~3 |
| CHANGE-3 | Required false explícito | (já implementado) | 0 |
| CHANGE-4 | Mensagens de erro com hints | parser.py | ~30 |
| CHANGE-5 | Validação de path templates | parser.py, ircs_emit.py, ast_nodes.py, errors.py | ~30 |

**Total:** ~163 linhas de código, 24 novos testes

### Verificação

```bash
# Todos os testes passam (61 total)
python -m pytest tests/test_idl_dsl.py -v

# finance.idl continua funcionando com output determinístico
python -m engine.idl_dsl examples/finance.idl --validate
```

### Notas de Compatibilidade

- IRCS output é backward-compatible (novas chaves adicionais, semântica mantida)
- DSL anteriormente aceito que referenciava entidades/campos inexistentes agora gera erro semântico (comportamento correto)
- Path templates com parâmetros inválidos agora geram erro (comportamento correto)
