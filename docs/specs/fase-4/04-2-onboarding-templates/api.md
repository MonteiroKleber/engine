# 04-2 Onboarding + Templates - API Design

**Status:** DRAFT
**Data:** 2026-01-19

## Rotas Console

### GET /console/onboarding

**Descrição:** Página principal do wizard de onboarding.

**Auth:** Cookie session OU X-Admin-Token header (Etapa 4.1)

**Query Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `step` | int | Não | Step atual (1-4), default 1 |
| `institution_id` | string | Não | UUID da instituição (steps 2+) |

**Response:** HTML (template `onboarding.html`)

**Template Context:**
```python
{
    "step": 1,                          # Step atual
    "institutions": [...],              # Lista de instituições existentes
    "templates": [...],                 # Lista de templates disponíveis
    "institution_id": None,             # UUID se selecionado
    "institution_name": None,           # Nome se selecionado
    "selected_template": None,          # Template selecionado
    "proof_result": None,               # Resultado do proof (step 4)
    "error": None,                      # Mensagem de erro
    "csrf_token": "...",                # CSRF token
}
```

**Steps:**
1. Create/Select Institution
2. Choose Template
3. Review & Generate
4. Proof Result

---

### POST /console/onboarding/create-institution

**Descrição:** Cria nova instituição para onboarding.

**Auth:** Cookie session OU X-Admin-Token header

**CSRF:** Obrigatório para cookie auth

**Form Data:**
| Field | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `slug` | string | Sim | Slug único (3-63 chars, lowercase) |
| `display_name` | string | Não | Nome amigável |
| `_csrf_token` | string | Cookie auth | CSRF token |

**Response:** Redirect 303

**Success:** `Location: /console/onboarding?step=2&institution_id={uuid}`

**Error:** Renderiza `onboarding.html` com `error` preenchido

**Erros Possíveis:**
| Código | HTTP | Descrição |
|--------|------|-----------|
| `INSTITUTION_SLUG_INVALID` | - | Slug formato inválido |
| `INSTITUTION_SLUG_TAKEN` | - | Slug já existe |
| `CONSOLE_CSRF_INVALID` | - | CSRF token inválido |

---

### POST /console/onboarding/generate-bundle

**Descrição:** Gera bundle a partir de template para instituição.

**Auth:** Cookie session OU X-Admin-Token header

**CSRF:** Obrigatório para cookie auth

**Form Data:**
| Field | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `template_id` | string | Sim | ID do template |
| `_csrf_token` | string | Cookie auth | CSRF token |

**Response:** Redirect 303

**Success:** `Location: /console/onboarding?step=4&institution_id={uuid}`

**Error:** Renderiza `onboarding.html` com `error` preenchido

**Processo Interno:**
1. Valida `institution_id` existe
2. Valida `template_id` existe no registry
3. Cria diretório `var/institutions/{uuid}/bundles/`
4. Copia template para `bundles/{template_id}/`
5. Atualiza `contract_ledger.json` com novos timestamps
6. Recalcula hashes do manifest
7. Roda `verify_bundle_offline()`
8. Se PASS: cria symlink `CURRENT -> {template_id}`
9. Emite evento de ledger `BUNDLE_GENERATED`

**Erros Possíveis:**
| Código | HTTP | Descrição |
|--------|------|-----------|
| `INSTITUTION_NOT_FOUND` | - | Instituição não existe |
| `TEMPLATE_NOT_FOUND` | - | Template não existe |
| `BUNDLE_GENERATION_FAILED` | - | Falha ao copiar/gerar |
| `PROOF_FAILED` | - | Proof não passou |

---

### GET /console/onboarding/proof

**Descrição:** Mostra resultado do proof do bundle gerado.

**Auth:** Cookie session OU X-Admin-Token header

**Query Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |

**Response:** HTML (template `onboarding.html` step 4)

**Reutiliza:** Lógica de `_get_bundle_path_for_institution()` e `verify_bundle_offline()`

---

## Modelos

### Template

```python
@dataclass
class BundleTemplate:
    """Template bundle for onboarding."""

    id: str                      # e.g., "finance-pilot"
    name: str                    # e.g., "Finance Pilot"
    description: str             # Human-readable description
    departments: List[str]       # e.g., ["finance"] or ["finance", "support"]
    path: str                    # Relative path from repo root
```

### Template Registry

```python
# console/templates_registry.py

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

@dataclass
class BundleTemplate:
    id: str
    name: str
    description: str
    departments: List[str]
    path: str

# Lista fixa inicial (pode ser expandida para JSON/YAML futuramente)
AVAILABLE_TEMPLATES: List[BundleTemplate] = [
    BundleTemplate(
        id="finance-pilot",
        name="Finance Pilot",
        description="Single-department bundle for finance operations. "
                    "Includes expense approval workflows, budget controls, "
                    "and SOD rules.",
        departments=["finance"],
        path="bundles/finance-pilot",
    ),
    BundleTemplate(
        id="multi-pilot",
        name="Multi-Department Pilot",
        description="Multi-department bundle with finance and support. "
                    "Includes inter-department contracts and shared workflows.",
        departments=["finance", "support"],
        path="bundles/multi-pilot",
    ),
]

def get_template(template_id: str) -> Optional[BundleTemplate]:
    """Get template by ID."""
    for template in AVAILABLE_TEMPLATES:
        if template.id == template_id:
            return template
    return None

def list_templates() -> List[BundleTemplate]:
    """List all available templates."""
    return AVAILABLE_TEMPLATES.copy()
```

### Bundle Generation Result

```python
@dataclass
class BundleGenerationResult:
    """Result of bundle generation from template."""

    success: bool                    # Whether generation succeeded
    bundle_path: Optional[Path]      # Path to generated bundle
    proof_result: Optional[ProofResult]  # Proof verification result
    error_code: Optional[str]        # Error code if failed
    error_message: Optional[str]     # Human-readable error
```

### Onboarding State

```python
@dataclass
class OnboardingState:
    """State tracked through onboarding wizard."""

    step: int                        # Current step (1-4)
    institution_id: Optional[str]    # Institution UUID
    institution_name: Optional[str]  # Institution display name
    template_id: Optional[str]       # Selected template ID
    bundle_path: Optional[str]       # Generated bundle path
    proof_passed: Optional[bool]     # Whether proof passed
```

---

## Template HTML

### onboarding.html

```html
{% extends "base.html" %}

{% block title %}AXIOM Console - Onboarding{% endblock %}

{% block content %}
<div class="card">
    <h2>Institution Onboarding</h2>

    <!-- Progress Steps -->
    <div class="steps">
        <div class="step {% if step >= 1 %}active{% endif %}">1. Institution</div>
        <div class="step {% if step >= 2 %}active{% endif %}">2. Template</div>
        <div class="step {% if step >= 3 %}active{% endif %}">3. Generate</div>
        <div class="step {% if step >= 4 %}active{% endif %}">4. Verify</div>
    </div>

    {% if error %}
    <div class="error-banner">{{ error }}</div>
    {% endif %}

    <!-- Step 1: Create/Select Institution -->
    {% if step == 1 %}
    <div class="step-content">
        <h3>Create or Select Institution</h3>

        {% if institutions %}
        <h4>Existing Institutions</h4>
        <ul>
            {% for inst in institutions %}
            <li>
                <a href="/console/onboarding?step=2&institution_id={{ inst.id }}">
                    {{ inst.name }} ({{ inst.slug }})
                </a>
            </li>
            {% endfor %}
        </ul>
        {% endif %}

        <h4>Create New Institution</h4>
        <form method="POST" action="/console/onboarding/create-institution">
            {% if csrf_token %}
            <input type="hidden" name="_csrf_token" value="{{ csrf_token }}">
            {% endif %}

            <div class="form-group">
                <label for="slug">Slug (unique identifier):</label>
                <input type="text" id="slug" name="slug" required
                       pattern="[a-z0-9][a-z0-9-]{1,61}[a-z0-9]"
                       placeholder="my-institution">
            </div>

            <div class="form-group">
                <label for="display_name">Display Name (optional):</label>
                <input type="text" id="display_name" name="display_name"
                       placeholder="My Institution">
            </div>

            <button type="submit">Create Institution</button>
        </form>
    </div>
    {% endif %}

    <!-- Step 2: Choose Template -->
    {% if step == 2 %}
    <div class="step-content">
        <h3>Choose Template</h3>
        <p>Institution: <strong>{{ institution_name }}</strong></p>

        <form method="POST" action="/console/onboarding/generate-bundle">
            <input type="hidden" name="institution_id" value="{{ institution_id }}">
            {% if csrf_token %}
            <input type="hidden" name="_csrf_token" value="{{ csrf_token }}">
            {% endif %}

            {% for template in templates %}
            <div class="template-card">
                <label>
                    <input type="radio" name="template_id" value="{{ template.id }}"
                           {% if loop.first %}checked{% endif %}>
                    <strong>{{ template.name }}</strong>
                </label>
                <p>{{ template.description }}</p>
                <p>Departments: {{ template.departments | join(", ") }}</p>
            </div>
            {% endfor %}

            <button type="submit">Generate Bundle</button>
        </form>
    </div>
    {% endif %}

    <!-- Step 3 is implicit (processing) -->

    <!-- Step 4: Proof Result -->
    {% if step == 4 %}
    <div class="step-content">
        <h3>Bundle Verification</h3>
        <p>Institution: <strong>{{ institution_name }}</strong></p>

        {% if proof_result.passed %}
        <div class="success-banner">
            Bundle verified successfully!
        </div>
        <ul>
            <li>Bundle: {{ proof_result.bundle_name }} v{{ proof_result.bundle_version }}</li>
            <li>Contracts verified: {{ proof_result.contracts_verified }}</li>
            <li>Manifest hash: <code>{{ proof_result.manifest_hash[:16] }}...</code></li>
        </ul>

        <p>
            <a href="/console/?institution_id={{ institution_id }}">
                Go to Console
            </a>
        </p>
        {% else %}
        <div class="error-banner">
            Bundle verification failed: {{ proof_result.error_code }}
        </div>
        <p>{{ proof_result.error_message }}</p>

        <p>
            <a href="/console/onboarding?step=2&institution_id={{ institution_id }}">
                Try Again
            </a>
        </p>
        {% endif %}
    </div>
    {% endif %}
</div>
{% endblock %}
```

---

## Ledger Events

### BUNDLE_GENERATED

Emitido quando bundle é gerado com sucesso.

```json
{
  "event_type": "BUNDLE_GENERATED",
  "tenant_id": "institution-uuid",
  "actor_id": "admin-user-uuid",
  "case_id": "institution-uuid",
  "step": "ONBOARDING:generate_bundle",
  "payload": {
    "institution_id": "institution-uuid",
    "template_id": "finance-pilot",
    "bundle_path": "var/institutions/.../bundles/finance-pilot",
    "proof_passed": true,
    "manifest_hash": "abc123...",
    "contracts_verified": 10
  }
}
```

---

## Erros

### Novos Códigos de Erro

```python
# core/errors.py

# Onboarding errors
TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
BUNDLE_GENERATION_FAILED = "BUNDLE_GENERATION_FAILED"
ONBOARDING_PROOF_FAILED = "ONBOARDING_PROOF_FAILED"
```

---

## Considerações de Segurança

1. **Auth:** Todas as rotas exigem autenticação (cookie ou header)
2. **CSRF:** POSTs com cookie auth exigem CSRF token
3. **Path traversal:** Template paths são validados contra lista fixa
4. **Proof obrigatório:** Bundle só é "ativado" (symlink CURRENT) se proof passar
5. **Audit trail:** Todos os eventos são logados no ledger

---

## Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────────┐
│                     Onboarding Wizard                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Institution          Step 2: Template                   │
│  ┌─────────────────┐          ┌─────────────────┐               │
│  │ Create/Select   │ ───────► │ Choose template │               │
│  │ institution     │          │ from registry   │               │
│  └─────────────────┘          └─────────────────┘               │
│         │                            │                           │
│         │ POST /create-institution   │ POST /generate-bundle     │
│         ▼                            ▼                           │
│  ┌─────────────────┐          ┌─────────────────┐               │
│  │ Registry        │          │ Bundle          │               │
│  │ .create()       │          │ Generation      │               │
│  └─────────────────┘          └─────────────────┘               │
│                                      │                           │
│                                      │ 1. Copy template          │
│                                      │ 2. Update ledger          │
│                                      │ 3. Recalc hashes          │
│                                      │ 4. Run proof              │
│                                      ▼                           │
│  Step 4: Verify               ┌─────────────────┐               │
│  ┌─────────────────┐          │ Proof           │               │
│  │ Show result     │ ◄─────── │ verify_bundle   │               │
│  │ PASS/FAIL       │          │ _offline()      │               │
│  └─────────────────┘          └─────────────────┘               │
│         │                            │                           │
│         │ If PASS                    │ If PASS                   │
│         ▼                            ▼                           │
│  ┌─────────────────┐          ┌─────────────────┐               │
│  │ Redirect to     │          │ Create symlink  │               │
│  │ Console home    │          │ CURRENT         │               │
│  └─────────────────┘          └─────────────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testes Necessários

### Test Happy Path

```python
class TestOnboardingHappyPath:
    """Test complete onboarding flow."""

    def test_create_institution_and_generate_bundle(self):
        """
        1. GET /console/onboarding (step 1)
        2. POST /console/onboarding/create-institution
        3. GET /console/onboarding?step=2 (verify redirect)
        4. POST /console/onboarding/generate-bundle
        5. GET /console/onboarding?step=4 (verify proof PASS)
        """
        pass
```

### Test Error Cases

```python
class TestOnboardingErrors:
    def test_invalid_slug_shows_error(self):
        pass

    def test_duplicate_slug_shows_error(self):
        pass

    def test_invalid_template_shows_error(self):
        pass

    def test_institution_not_found_shows_error(self):
        pass
```

### Test Auth

```python
class TestOnboardingAuth:
    def test_routes_require_auth(self):
        pass

    def test_csrf_required_for_posts(self):
        pass
```
