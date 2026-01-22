# 03-7 Intake Assistido - Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Resumo

Análise de gaps entre a spec.md e a implementação atual para o fluxo de intake assistido.

## Estado Atual - Backend (engine.nl)

O módulo `engine.nl` já implementa o pipeline completo NL → SIR → Draft → Gaps → Answers → Finalize:

| Componente | Status | Localização |
|------------|--------|-------------|
| SIR Extraction | ✅ Existe | `nl/extractors/` com deterministic e LLM |
| SIR Schema | ✅ Existe | `nl/schemas/sir_v1.py` |
| Draft Generator | ✅ Existe | `nl/draft_generator.py` |
| Gap Detector | ✅ Existe | `nl/gap_detector.py` |
| Answer Apply | ✅ Existe | `nl/answer_apply.py` |
| Finalizer | ✅ Existe | `nl/finalizer.py` |
| Answers Schema | ✅ Existe | `nl/schemas/answers_v1.py` |

## Estado Atual - API (engine.api.nl)

O router `/nl` já expõe endpoints REST:

| Endpoint | Status | Descrição |
|----------|--------|-----------|
| `POST /nl/compile/sir` | ✅ Existe | NL text → SIR |
| `POST /nl/compile/draft` | ✅ Existe | SIR → Draft IDL |
| `POST /nl/gaps` | ✅ Existe | SIR + Draft → Gaps |
| `POST /nl/answers/apply` | ✅ Existe | Draft + Gaps + Answers → Updated Draft |
| `POST /nl/finalize` | ✅ Existe | Draft → Final IDL |

## Estado Atual - DSL→IR Fallback

O módulo `engine.idl_dsl` implementa parsing de DSL textual para IRCS:

| Componente | Status | Localização |
|------------|--------|-------------|
| `parse_dsl()` | ✅ Existe | `idl_dsl/__init__.py` |
| Lexer | ✅ Existe | `idl_dsl/lexer.py` |
| Parser | ✅ Existe | `idl_dsl/parser.py` |
| IRCS Emitter | ✅ Existe | `idl_dsl/ircs_emit.py` |

## Estado Atual - Persistência

| Componente | Status | Localização |
|------------|--------|-------------|
| DevRunsRegistry | ✅ Existe | `pipeline/registry.py` |
| Export ZIP | ✅ Existe | `pipeline/exporter.py` |

## Estado Atual - Console

| Componente | Status | Descrição |
|------------|--------|-----------|
| `GET /console/intake` | ✅ Implementado | Formulário inicial com toggle NL/DSL |
| `POST /console/intake` | ✅ Implementado | Processa input → Draft + Gaps |
| `POST /console/intake/answer` | ✅ Implementado | Coleta respostas e atualiza draft |
| `POST /console/intake/finalize` | ✅ Implementado | Gera IDL final |
| `GET /console/intake/export` | ✅ Implementado | Download IR JSON |
| Template intake.html | ✅ Implementado | Formulário inicial |
| Template intake_draft.html | ✅ Implementado | Draft + gaps + questions |
| Template intake_result.html | ✅ Implementado | Resultado final + export |

## Gaps Resolvidos

### GAP-1: Falta página de intake no console ✅ RESOLVIDO

**Requisito spec.md:**
- `GET /console/intake` - formulário de texto
- `POST /console/intake` - gera draft + gaps
- `POST /console/intake/finalize` - aplica respostas e gera final
- `GET /console/intake/export?format=ir|dsl`

**Solução implementada:**
1. Rotas adicionadas em `console/routes.py` (linhas 844-1231)
2. Templates criados: `intake.html`, `intake_draft.html`, `intake_result.html`
3. Link de navegação adicionado em `base.html`

---

### GAP-2: Falta session/state management para draft ✅ RESOLVIDO

**Problema:** O fluxo intake requer manter estado (SIR, Draft, Gaps) entre requests.

**Solução implementada:** Hidden form fields (stateless, sem JS complexo).

Campos passados via hidden inputs:
- `sir_json`: SIR serializado
- `draft_json`: Draft serializado
- `gaps_json`: Gaps serializados
- `remaining_gaps_json`: Gaps restantes após respostas

---

### GAP-3: Falta integração console→nl pipeline ✅ RESOLVIDO

**Problema:** Console precisa chamar endpoints `/nl/*` ou funções diretamente.

**Solução implementada:** Import direto das funções:
```python
from engine.nl.extractors import get_extractor
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps, gaps_to_dict
from engine.nl.answer_apply import apply_answers
from engine.nl.finalizer import finalize, validate_final
from engine.nl.schemas.answers_v1 import AnswersV1, Answer, Gap
```

---

### GAP-4: Falta modo "manual DSL" (fallback) ✅ RESOLVIDO

**Requisito spec.md:** "Se não existir NL de verdade, permitir modo 'mock/manual': usuário cola DSL e o console só valida/gera IR."

**Solução implementada:**
1. Toggle NL/DSL mode no formulário
2. Modo DSL chama `parse_dsl()` diretamente
3. Erros de parsing (IDLSyntaxError, IDLSemanticError) exibidos na UI
4. DSL bypass do fluxo de gaps, vai direto para resultado final

---

### GAP-5: Falta export IR/DSL ✅ RESOLVIDO (parcial)

**Requisito spec.md:** `GET /console/intake/export?format=ir|dsl`

**Solução implementada:**
1. Export IR: `/console/intake/export?format=ir` retorna JSON com Content-Disposition: attachment
2. Export DSL: Retorna erro 400 (IR→DSL reverso não implementado)

**Nota:** DSL export pode ser adicionado no futuro quando IR→DSL converter existir.

---

### GAP-6: Falta templates para UI de gaps/questions ✅ RESOLVIDO

**Problema:** Gap questions precisam de UI interativa para coletar respostas.

**Solução implementada:** Template `intake_draft.html` renderiza questions com inputs apropriados:
- Boolean: checkbox
- Number: input type="number"
- Text: input type="text"
- Choice: select com options

## Dependências

| Dependência | Status |
|-------------|--------|
| `engine.nl.*` | ✅ Disponível e integrado |
| `engine.idl_dsl` | ✅ Disponível e integrado |
| `engine.pipeline.exporter` | ✅ Disponível (não usado diretamente) |
| Session management | ✅ Resolvido via hidden form fields |

## Implementação Realizada (PROMPT 3.7.2)

### Fase 1: Rotas básicas ✅
1. `GET /console/intake` - Formulário inicial (NL text ou DSL manual)
2. `POST /console/intake` - Processa input → SIR → Draft → Gaps
3. Renderiza `intake_draft.html` com draft + gaps

### Fase 2: Answer collection ✅
4. `POST /console/intake/answer` - Coleta respostas via form
5. Aplica respostas com `apply_answers()`
6. Loop até gaps resolvidos ou user aceita

### Fase 3: Finalize e Export ✅
7. `POST /console/intake/finalize` - Gera IDL final
8. `GET /console/intake/export?format=ir` - Download JSON

### Fase 4: DSL Manual fallback ✅
9. Modo alternativo que aceita DSL text
10. Valida com `parse_dsl()`
11. Export IR diretamente

## Testes Implementados

| Test Class | Tests | Description |
|------------|-------|-------------|
| `TestConsoleIntakeAuth` | 3 | Auth com X-Admin-Token |
| `TestConsoleIntakePage` | 3 | GET /console/intake |
| `TestConsoleIntakeNLMode` | 2 | POST com NL text |
| `TestConsoleIntakeDSLMode` | 2 | POST com DSL text |
| `TestConsoleIntakeFinalize` | 3 | Finalize flow |
| `TestConsoleIntakeExport` | 2 | Export IR JSON |
| `TestConsoleIntakeNavLink` | 1 | Nav link presente |

**Total:** 16 novos testes, 132 testes passando

## Definition of Done (da spec.md)

- [x] Operador consegue gerar um rascunho via texto/DSL
- [x] Operador consegue ver e responder gaps
- [x] Operador consegue fechar gaps e finalizar
- [x] Operador consegue exportar IR para revisão humana
- [ ] Operador consegue exportar DSL (futuro - requer IR→DSL converter)
