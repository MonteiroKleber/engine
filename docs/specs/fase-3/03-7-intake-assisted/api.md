# 03-7 Intake Assistido - API Mapping

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Backend APIs Disponíveis

### NL Pipeline (engine.nl)

#### `compile_sir` (extractor)

```python
from engine.nl.extractors import get_extractor

extractor = get_extractor()  # Uses ENGINE_NL_EXTRACTOR env
sir: SIRv1 = extractor.extract(text: str, language: Optional[str]) -> SIRv1
```

Extractors disponíveis:
- `deterministic`: Pattern matching (default, no LLM)
- `llm`: LLM-based extraction (requires API key)

#### `generate_draft`

```python
from engine.nl.draft_generator import generate_draft

draft: Dict[str, Any] = generate_draft(sir: SIRv1) -> Dict[str, Any]
```

Gera Draft IDL a partir de SIR. Inclui:
- RBAC (roles + permissions)
- Approvals (rules)
- SoD (rules)
- Invariants
- Workflows
- Runtime policies

#### `detect_gaps`

```python
from engine.nl.gap_detector import detect_gaps, gaps_to_dict

gaps: List[Gap] = detect_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]
gaps_dict = gaps_to_dict(gaps)  # {"version": "1.0", "gaps": [...]}
```

Gap types:
- `approval`: Approval requirements missing
- `sod`: Segregation of duties missing
- `identity`: Roles missing from RBAC
- `auth`: Authentication method missing
- `invariant`: Invariants missing
- `runtime_policy`: Policy validation errors
- `mandate`: Mandate missing (IDL v1.1)
- `autonomy`: Autonomy rule missing (IDL v1.1)

#### `apply_answers`

```python
from engine.nl.answer_apply import apply_answers
from engine.nl.schemas.answers_v1 import AnswersV1, Answer

answers = AnswersV1(answers=[
    Answer(question_id="q1", value=True),
    Answer(question_id="q2", value="manager"),
])

updated_draft, remaining_gaps = apply_answers(
    draft: Dict[str, Any],
    gaps: List[Gap],
    answers: AnswersV1,
) -> Tuple[Dict[str, Any], List[Gap]]
```

#### `finalize`

```python
from engine.nl.finalizer import finalize, validate_final

final_idl = finalize(
    draft: Dict[str, Any],
    remaining_gaps: List[Gap],
    allow_gaps: bool = False,
) -> Dict[str, Any]

is_valid, errors = validate_final(final_idl)
```

Raises `ValueError` if required gaps remain and `allow_gaps=False`.

### DSL Parser (engine.idl_dsl)

```python
from engine.idl_dsl import parse_dsl, IDLSyntaxError, IDLSemanticError

try:
    ircs_json: dict = parse_dsl(dsl_text: str) -> dict
except IDLSyntaxError as e:
    # Line/column info in e.location.line, e.location.column, e.message
except IDLSemanticError as e:
    # Semantic validation error
```

Output format (IRCS v1):
```json
{
  "ir_version": "ircs.v1",
  "source_idl_version": "idl.v1.2.2",
  "source_idl_sha256": "...",
  "system": {...},
  "department": {...},
  "policy_context": {...},
  "actors": [...],
  "entities": [...],
  "invariants": [...],
  "separation_of_duties": [...],
  "workflows": [...],
  "operations": {...},
  "runtime": {...}
}
```

### REST API Existente (engine.api.nl)

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/nl/compile/sir` | POST | `{text, language?}` | `{sir}` |
| `/nl/compile/draft` | POST | `{sir}` | `{draft}` |
| `/nl/gaps` | POST | `{sir, draft}` | `{gaps}` |
| `/nl/answers/apply` | POST | `{draft, gaps, answers}` | `{draft, remaining_gaps}` |
| `/nl/finalize` | POST | `{draft, remaining_gaps?, allow_gaps?}` | `{idl, valid, errors}` |

## Console Routes (Implementadas)

### `GET /console/intake` ✅

**Descrição:** Página inicial de intake assistido.

**Parâmetros:**
- `institution_id` (query, required)
- `dept_id` (query, optional)
- `mode` (query, optional): `nl` (default) ou `dsl`
- `X-Admin-Token` (header, required)

**Template context:**
```python
{
    "mode": "nl",  # or "dsl"
    "institution_id": str,
    "dept_id": Optional[str],
    "errors": None,
}
```

**Localização:** `console/routes.py` linha 844

### `POST /console/intake` ✅

**Descrição:** Processa input (NL ou DSL) e gera draft.

**Parâmetros:**
- `institution_id` (form, required)
- `dept_id` (form, optional)
- `mode` (form): `nl` ou `dsl`
- `input_text` (form): NL text ou DSL source
- `X-Admin-Token` (header, required)

**Comportamento:**
1. Se mode=`nl`:
   - `extract(input_text)` → SIR
   - `generate_draft(sir)` → Draft
   - `detect_gaps(sir, draft)` → Gaps
   - Renderiza `intake_draft.html`
2. Se mode=`dsl`:
   - `parse_dsl(input_text)` → IRCS
   - Renderiza `intake_result.html` diretamente

**Localização:** `console/routes.py` linha 880

### `POST /console/intake/answer` ✅

**Descrição:** Submete respostas para gaps.

**Parâmetros:**
- `institution_id` (form, required)
- `dept_id` (form, optional)
- `sir_json` (form, hidden): SIR serializado
- `draft_json` (form, hidden): Draft serializado
- `gaps_json` (form, hidden): Gaps serializados
- `answer_*` (form): Respostas (question_id → value)
- `X-Admin-Token` (header, required)

**Comportamento:**
1. Deserializa state
2. Coleta answers do form
3. `apply_answers(draft, gaps, answers)` → Updated draft, remaining
4. Se remaining: renderiza `intake_draft.html` novamente
5. Se empty: renderiza `intake_draft.html` com can_finalize=True

**Localização:** `console/routes.py` linha 975

### `POST /console/intake/finalize` ✅

**Descrição:** Finaliza draft e produz IDL.

**Parâmetros:**
- `institution_id` (form, required)
- `dept_id` (form, optional)
- `draft_json` (form, hidden): Draft serializado
- `remaining_gaps_json` (form, hidden): Remaining gaps
- `allow_gaps` (form, optional): Checkbox
- `X-Admin-Token` (header, required)

**Comportamento:**
1. `finalize(draft, remaining_gaps, allow_gaps)`
2. `validate_final(final_idl)`
3. Renderiza `intake_result.html` com final IDL

**Localização:** `console/routes.py` linha 1075

### `GET /console/intake/export` ✅

**Descrição:** Exporta resultado como download.

**Parâmetros:**
- `institution_id` (query, required)
- `dept_id` (query, optional)
- `format` (query): `ir` (default) ou `dsl`
- `idl_json` (query, URL-encoded): IDL a exportar
- `X-Admin-Token` (header, required)

**Comportamento:**
1. Se format=`ir`:
   - Return JSON com Content-Disposition: attachment
   - Filename: `idl-{institution_id}-{dept_id}.json`
2. Se format=`dsl`:
   - Return 400 error (IR→DSL não implementado)

**Localização:** `console/routes.py` linha 1142

## Data Models

### Gap (from answers_v1.py)

```python
@dataclass
class Gap:
    gap_key: str           # e.g., "gap-approval-expense"
    gap_type: str          # approval | sod | identity | auth | invariant | runtime_policy
    severity: str          # required | recommended | optional
    description: str       # Human-readable description
    policy_ref: str        # Policy reference
    questions: List[Question]

    def to_dict(self) -> Dict[str, Any]
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Gap"
```

### Question (from answers_v1.py)

```python
@dataclass
class Question:
    question_id: str       # Unique ID (hash-based)
    gap_key: str           # Parent gap
    policy_key: str        # Policy reference
    step: str              # Step name within gap
    question_text: str     # Human-readable question
    question_type: str     # boolean | number | text | choice
    options: Optional[List[str]] = None    # For choice type
    default_value: Optional[Any] = None    # Default answer

    def to_dict(self) -> Dict[str, Any]
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question"
```

### Answer (from answers_v1.py)

```python
@dataclass
class Answer:
    question_id: str
    value: Any

@dataclass
class AnswersV1:
    answers: List[Answer]
```

### SIRv1 (from sir_v1.py)

```python
@dataclass
class SIRv1:
    version: str = "1.0"
    extraction: Extraction  # Contains policies, actors, entities, workflows

    def to_dict(self) -> Dict[str, Any]
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SIRv1"
```

## Templates Implementados

### intake.html ✅

Formulário inicial:
- Toggle: NL mode / DSL mode (radio buttons)
- Textarea para input
- Submit button
- Error display area

**Localização:** `console/templates/intake.html`

### intake_draft.html ✅

Resultado de processamento:
- Draft preview (JSON collapsible)
- Lista de gaps com questions
- Form para submeter answers (inputs por tipo)
- Hidden fields: sir_json, draft_json, gaps_json
- Botão "Finalizar" quando can_finalize=True

**Localização:** `console/templates/intake_draft.html`

### intake_result.html ✅

Resultado final:
- Final IDL preview (JSON)
- Validation status (valid/errors)
- Warnings display
- Summary metrics (roles, rules, actors, entities)
- Export buttons (IR JSON, Copy to clipboard)
- Back to intake link

**Localização:** `console/templates/intake_result.html`

## State Management

### Approach: Hidden Form Fields ✅

Estado é passado entre requests via hidden fields JSON-encoded:

```html
<input type="hidden" name="sir_json" value="{{ sir_json | e }}">
<input type="hidden" name="draft_json" value="{{ draft_json | e }}">
<input type="hidden" name="gaps_json" value="{{ gaps_json | e }}">
```

**Pros:**
- Stateless server
- No session storage needed
- Works without JavaScript

**Cons:**
- Large payloads in forms
- URL size limits for GET redirects

**Mitigação:** Usar POST para todas as transições, evitar redirects com state.

## Testes Implementados

| Test | Class | Description |
|------|-------|-------------|
| `test_intake_get_requires_admin_token` | TestConsoleIntakeAuth | Auth GET |
| `test_intake_post_requires_admin_token` | TestConsoleIntakeAuth | Auth POST |
| `test_intake_finalize_requires_admin_token` | TestConsoleIntakeAuth | Auth finalize |
| `test_intake_page_returns_html` | TestConsoleIntakePage | GET /console/intake |
| `test_intake_page_shows_nl_mode_by_default` | TestConsoleIntakePage | Default mode |
| `test_intake_page_shows_dsl_mode_when_requested` | TestConsoleIntakePage | DSL mode |
| `test_intake_nl_generates_draft` | TestConsoleIntakeNLMode | POST with NL text |
| `test_intake_nl_empty_text_shows_error` | TestConsoleIntakeNLMode | Empty input |
| `test_intake_dsl_generates_ir` | TestConsoleIntakeDSLMode | POST with DSL text |
| `test_intake_dsl_invalid_shows_error` | TestConsoleIntakeDSLMode | DSL syntax error |
| `test_intake_finalize_produces_idl` | TestConsoleIntakeFinalize | Finalize flow |
| `test_intake_finalize_with_required_gaps_fails` | TestConsoleIntakeFinalize | Required gaps block |
| `test_intake_finalize_allow_gaps` | TestConsoleIntakeFinalize | allow_gaps=true |
| `test_intake_export_ir_json` | TestConsoleIntakeExport | Export JSON download |
| `test_intake_export_dsl_not_supported` | TestConsoleIntakeExport | DSL export error |
| `test_intake_nav_link_present` | TestConsoleIntakeNavLink | Nav link in base |

**Total:** 16 testes implementados
