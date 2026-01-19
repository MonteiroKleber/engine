# Checklist de Implementação Mínima — Etapa 2.1

**Data:** 2026-01-18
**Status:** DRAFT
**DoD:** DSL v1.2.2 → IRCS v1 JSON (determinístico)

## Diagnóstico do Estado Atual

### Input Institucional Atual

| Arquivo | Função | Observação |
|---------|--------|------------|
| `src/engine/ise/idl_parser.py` | Parseia **JSON ad-hoc** | NÃO é DSL textual |
| `ParsedIDL` dataclass | Estrutura interna | Diferente de IRCS v1 |

**Conclusão:** Não existe parser de DSL textual. O "IDL" atual é um JSON legacy.

### Estruturas Relevantes

| Componente | Arquivo | Acoplamento |
|------------|---------|-------------|
| `ParsedIDL` | `idl_parser.py:193-215` | Dataclass central — todos emitters dependem |
| `IDLEntity`, `IDLActor`, etc. | `idl_parser.py:69-209` | Sub-dataclasses |
| `parse_idl()` | `idl_parser.py:242-337` | Entry point — recebe JSON |
| `compile_bundle()` | `compiler.py:49-94` | Chama `parse_idl()` e emitters |
| Emitters | `emit/*.py` | Recebem `ParsedIDL`, emitem contracts |

### O que NÃO existe (gaps)

1. **DSL Parser textual** — nenhum parser de gramática EBNF
2. **AST tipado para expressões** — expressões são strings ou ausentes
3. **Validação de history()** — não implementado
4. **IRCS v1 schema** — não existe formato canônico intermediário
5. **source_idl_sha256** — não preservado

---

## Caminho Mínimo de Implementação

### Arquitetura Alvo

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  finance.idl    │ ───► │   DSL Parser    │ ───► │    ir.json      │
│  (DSL v1.2.2)   │      │   (novo)        │      │   (IRCS v1)     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                                          │
                                                          ▼
                                                  ┌─────────────────┐
                                                  │    ISE (atual)  │
                                                  │  (Etapa 2.2)    │
                                                  └─────────────────┘
```

**Nota:** Nesta etapa (2.1), o ISE continua consumindo `ParsedIDL`. A adaptação do ISE para IRCS v1 é a **Etapa 2.2**.

---

## Checklist de Implementação

### Fase A: Estruturas Base

- [ ] **A1. Criar módulo `src/engine/idl/`** (novo pacote)
  - `__init__.py`
  - `tokens.py` — definição de tokens
  - `lexer.py` — tokenização
  - `parser.py` — parsing recursive descent
  - `ast_nodes.py` — nós da AST
  - `ir_emitter.py` — AST → IRCS v1 JSON
  - `errors.py` — códigos de erro determinísticos

- [ ] **A2. Definir AST nodes para expressões**
  - `ExprNode` (base)
  - `AlwaysExpr`
  - `CompareExpr` (op, lhs, rhs)
  - `AndExpr`, `OrExpr`, `NotExpr`
  - `LiteralValue` (lit, type)
  - `RefPath` (path, type)
  - `HistoryRef` (step, attr, type) — v1.2.2

- [ ] **A3. Definir AST nodes para seções**
  - `SystemNode`
  - `ActorNode`
  - `EntityNode`, `FieldNode`
  - `PolicyContextNode`
  - `InvariantNode`
  - `SodRuleNode`
  - `WorkflowNode`, `StateNode`, `TransitionNode`
  - `OperationNode`, `EndpointNode`

### Fase B: Lexer

- [ ] **B1. Implementar tokenização**
  - Keywords: `system`, `actors`, `entities`, `invariants`, `separation_of_duties`, `workflows`, `operations`, etc.
  - Operadores: `==`, `!=`, `>=`, `<=`, `>`, `<`, `in`, `and`, `or`, `not`
  - Delimitadores: `{`, `}`, `[`, `]`, `(`, `)`, `:`, `,`, `->`, `.`
  - Literals: string, number, boolean, identifier
  - Comentários: `//` linha, `/* */` bloco (opcional)

- [ ] **B2. Posicionamento de erro**
  - Linha e coluna para cada token
  - Contexto de erro (trecho do source)

### Fase C: Parser

- [ ] **C1. Parser recursive descent**
  - `parse_document()` → lista de seções
  - `parse_system_section()`
  - `parse_actors_section()`
  - `parse_entities_section()`
  - `parse_policy_context_section()`
  - `parse_invariants_section()`
  - `parse_sod_section()`
  - `parse_workflows_section()`
  - `parse_operations_section()`

- [ ] **C2. Parser de expressões (predicate_expr)**
  - `parse_expr()` → `parse_or_expr()`
  - `parse_or_expr()` → `parse_and_expr()`
  - `parse_and_expr()` → `parse_not_expr()`
  - `parse_not_expr()` → `parse_atom_expr()`
  - `parse_comparison()`
  - `parse_value_ref()` — inclui `history_ref`

- [ ] **C3. Validações semânticas**
  - Referências a entidades existentes
  - Referências a actors existentes
  - Referências a workflows/transitions existentes
  - Tipos compatíveis em comparações
  - `history()` apenas em contextos permitidos

### Fase D: IR Emitter

- [ ] **D1. AST → IRCS v1 JSON**
  - `emit_ir(ast, source_text)` → JSON dict
  - Adicionar `ir_version`, `source_idl_version`
  - Calcular e incluir `source_idl_sha256`

- [ ] **D2. Serialização determinística**
  - Ordenação de chaves
  - Formato consistente de números/strings
  - Identação padronizada

### Fase E: Validação do IRCS v1

- [ ] **E1. Schema validation**
  - Validar estrutura JSON resultante
  - Verificar campos obrigatórios
  - Verificar tipos

- [ ] **E2. Erros determinísticos**
  - Catálogo de códigos de erro
  - Mensagens padronizadas
  - Mesmo input → mesmo erro (sempre)

### Fase F: Testes

- [ ] **F1. Testes de lexer**
  - Tokenização de keywords
  - Tokenização de literais
  - Tratamento de whitespace/comentários

- [ ] **F2. Testes de parser**
  - Cada seção isoladamente
  - Expressões com `history()`
  - Erros de sintaxe

- [ ] **F3. Testes de IR emitter**
  - Finance canônico completo
  - Comparação com IRCS v1 esperado
  - Determinismo (múltiplas execuções = mesmo output)

- [ ] **F4. Testes de validação**
  - Referências inválidas → erro
  - Tipos incompatíveis → erro
  - history() em contexto proibido → erro

### Fase G: CLI / Entry Point

- [ ] **G1. Comando de conversão**
  - `python -m engine.idl finance.idl -o ir.json`
  - Ou integrado no ISE existente

- [ ] **G2. Relatório de erros**
  - Formato legível
  - Linha/coluna do erro
  - Sugestão de correção (opcional)

---

## Arquivos Alvo (Criação)

| Arquivo | Propósito |
|---------|-----------|
| `src/engine/idl/__init__.py` | Package init |
| `src/engine/idl/tokens.py` | Token types enum |
| `src/engine/idl/lexer.py` | Tokenizer |
| `src/engine/idl/ast_nodes.py` | AST node classes |
| `src/engine/idl/parser.py` | Recursive descent parser |
| `src/engine/idl/type_checker.py` | Type inference/validation |
| `src/engine/idl/ir_emitter.py` | AST → IRCS v1 |
| `src/engine/idl/errors.py` | Error codes |
| `tests/test_idl_lexer.py` | Lexer tests |
| `tests/test_idl_parser.py` | Parser tests |
| `tests/test_idl_ir_emitter.py` | IR emitter tests |
| `examples/finance.idl` | Finance canônico DSL |
| `examples/finance-ir.json` | Finance IRCS v1 esperado |

---

## Arquivos Existentes (Não Modificar nesta Etapa)

| Arquivo | Motivo |
|---------|--------|
| `src/engine/ise/idl_parser.py` | Legacy JSON parser — Etapa 2.2 |
| `src/engine/ise/compiler.py` | Usa ParsedIDL — Etapa 2.2 |
| `src/engine/ise/emit/*.py` | Emitters — Etapa 2.2 |

A migração do ISE para consumir IRCS v1 é escopo da **Etapa 2.2**.

---

## Dependências Externas

| Dependência | Propósito | Recomendação |
|-------------|-----------|--------------|
| Nenhuma obrigatória | Parser é hand-written | Evitar deps externas |
| (opcional) `lark` | Parser generator | Pode simplificar, mas adiciona dep |
| (opcional) `ply` | Lex/yacc Python | Alternativa a lark |

**Recomendação:** Parser recursive descent manual (sem deps externas) para controle total sobre erros e performance.

---

## Definition of Done (Etapa 2.1)

- [ ] `finance.idl` (DSL textual) → `ir.json` (IRCS v1) funciona
- [ ] IR resultante valida (tipos + refs + history())
- [ ] Erros determinísticos (mesmo input → mesmo erro)
- [ ] `source_idl_sha256` preservado no IR
- [ ] Testes passam para Finance canônico
- [ ] Documentação atualizada

---

## Estimativa de Complexidade

| Fase | Arquivos | LOC estimado |
|------|----------|--------------|
| A (Estruturas) | 2 | ~200 |
| B (Lexer) | 1 | ~200 |
| C (Parser) | 1 | ~500 |
| D (IR Emitter) | 1 | ~300 |
| E (Validação) | 1 | ~150 |
| F (Testes) | 4 | ~400 |
| G (CLI) | 1 | ~50 |
| **Total** | **11** | **~1800** |

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Gramática ambígua | Usar EBNF fechada do subset |
| history() complexo | Implementar apenas atributos especificados |
| Inferência de tipos difícil | Limitar a tipos primitivos conhecidos |
| Erros pouco informativos | Investir em contexto de erro desde início |
