# 04-1 Console Browser Auth - API Mapping

**Status:** DIAGNÓSTICO
**Data:** 2026-01-19

## Novas Rotas de Autenticação

### `GET /console/login`

**Descrição:** Página de login para colar admin token.

**Parâmetros:**
- `next` (query, optional): URL para redirect após login bem-sucedido
- Sem autenticação requerida (página pública)

**Comportamento:**
1. Se já autenticado (cookie válido) → redirect para `next` ou `/console/`
2. Se não autenticado → renderiza `login.html`

**Template context:**
```python
{
    "error": None,  # ou "Token inválido"
    "next": "/console/",  # URL para redirect
}
```

**Response:** HTML (200)

---

### `POST /console/login`

**Descrição:** Processa login e cria sessão.

**Parâmetros:**
- `token` (form, required): Admin token
- `next` (form, optional): URL para redirect

**Comportamento:**
1. Validar token com `verify_admin_token(token)`
2. Se inválido:
   - Renderiza `login.html` com error="Token inválido"
   - Status: 401
3. Se válido:
   - Criar cookie de sessão assinado
   - Gerar CSRF token
   - Set-Cookie: `console_session={signed_data}; HttpOnly; SameSite=Strict; Path=/console/`
   - Redirect 303 para `next` ou `/console/`

**Response (success):**
```http
HTTP/1.1 303 See Other
Location: /console/
Set-Cookie: console_session=...; HttpOnly; SameSite=Strict; Path=/console/; Max-Age=28800
```

**Response (failure):**
```http
HTTP/1.1 401 Unauthorized
Content-Type: text/html

<!-- login.html with error message -->
```

---

### `GET /console/logout`

**Descrição:** Limpa sessão e redireciona para login.

**Parâmetros:**
- Requer autenticação (cookie ou header)

**Comportamento:**
1. Limpar cookie de sessão
2. Redirect para `/console/login`

**Response:**
```http
HTTP/1.1 303 See Other
Location: /console/login
Set-Cookie: console_session=; HttpOnly; SameSite=Strict; Path=/console/; Max-Age=0
```

---

## Modificações em Rotas Existentes

### `_require_admin_token()` → `_require_console_auth()`

**Mudança:** Função passa a aceitar autenticação via cookie OU header.

**Comportamento:**
```
1. Verificar X-Admin-Token header
   - Se presente e válido → autenticado
2. Verificar console_session cookie
   - Se presente e válido → autenticado
3. Se nenhum válido:
   - Se Accept: text/html → redirect 303 /console/login
   - Se Accept: application/json → 401 JSON
```

**Compatibilidade:**
- `curl -H "X-Admin-Token: ..."` continua funcionando
- Browser com cookie funciona sem header
- API clients recebem JSON error

---

### POST Routes - CSRF Required

Todas as rotas POST do console passam a exigir CSRF token:

| Rota | CSRF Field |
|------|------------|
| `POST /console/login` | NÃO (cria sessão) |
| `POST /console/legacy/{asset_id}/verify` | `_csrf_token` |
| `POST /console/intake` | `_csrf_token` |
| `POST /console/intake/answer` | `_csrf_token` |
| `POST /console/intake/finalize` | `_csrf_token` |
| `POST /console/mandates/proposals` | `_csrf_token` |
| `POST /console/mandates/proposals/{id}/decide` | `_csrf_token` |
| `POST /console/ege/rollback` | `_csrf_token` |

**CSRF Validation:**
```python
def _require_csrf_token(request: Request, csrf_token: str = Form(alias="_csrf_token")):
    """Validate CSRF token matches session."""
    session = get_session_from_cookie(request)
    if not session or not secrets.compare_digest(session.csrf_token, csrf_token):
        raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID", "message": "Invalid CSRF token"})
```

**Template Integration:**

Todos os forms POST precisam incluir:
```html
<input type="hidden" name="_csrf_token" value="{{ csrf_token }}">
```

O `csrf_token` é passado no context de todos os templates.

---

## Session Cookie Format

### Cookie Name
`console_session`

### Cookie Attributes
```
HttpOnly      ; Prevent JS access
SameSite=Strict ; Prevent CSRF from other sites
Path=/console/  ; Only sent to /console/* paths
Secure        ; Only if ENGINE_CONSOLE_SECURE_COOKIE=true or HTTPS detected
Max-Age=28800 ; 8 hours default (configurable)
```

### Cookie Value (signed)
```
itsdangerous.URLSafeTimedSerializer signed payload:
{
  "th": "token_hash_16chars",  // sha256(admin_token)[:16]
  "csrf": "csrf_token_32chars", // random hex
  "n": "nonce_16chars"          // random hex
}
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENGINE_CONSOLE_SESSION_SECRET` | Yes* | None | Secret for cookie signing (32+ chars) |
| `ENGINE_CONSOLE_SESSION_TTL_HOURS` | No | 8 | Session TTL in hours |
| `ENGINE_CONSOLE_SECURE_COOKIE` | No | auto | Force Secure flag (true/false/auto) |

*Se não definido, derivar de `ENGINE_ISE_ADMIN_TOKEN` (menos seguro mas funcional).

---

## Error Responses

### Not Authenticated (HTML)

```http
HTTP/1.1 303 See Other
Location: /console/login?next=/console/mandates
```

### Not Authenticated (JSON)

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "code": "CONSOLE_UNAUTHORIZED",
  "message": "Invalid or missing authentication. Pass X-Admin-Token header or login via browser."
}
```

### Invalid CSRF Token

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "CSRF_INVALID",
  "message": "Invalid or missing CSRF token"
}
```

### Session Expired (HTML)

```http
HTTP/1.1 303 See Other
Location: /console/login?next=/console/&expired=1
```

---

## Templates Necessários

### login.html (novo)

```html
{% extends "base.html" %}

{% block title %}AXIOM Console - Login{% endblock %}

{% block content %}
<div class="card" style="max-width: 400px; margin: 2rem auto;">
    <h2>Console Login</h2>

    {% if error %}
    <div style="color: var(--error-color); margin-bottom: 1rem;">
        {{ error }}
    </div>
    {% endif %}

    {% if expired %}
    <div style="color: var(--warning-color); margin-bottom: 1rem;">
        Session expired. Please login again.
    </div>
    {% endif %}

    <form method="POST" action="/console/login">
        <input type="hidden" name="next" value="{{ next }}">

        <div style="margin-bottom: 1rem;">
            <label for="token">Admin Token:</label>
            <input
                type="password"
                id="token"
                name="token"
                required
                placeholder="Paste your admin token"
                style="width: 100%; padding: 0.5rem; margin-top: 0.25rem;"
            >
        </div>

        <button type="submit" class="btn-primary" style="width: 100%;">
            Login
        </button>
    </form>

    <p style="margin-top: 1rem; font-size: 0.875rem; color: var(--text-secondary);">
        Token is validated against ENGINE_ISE_ADMIN_TOKEN environment variable.
    </p>
</div>
{% endblock %}
```

### Modificação em templates existentes

Todos os templates com forms POST devem incluir CSRF token:

```html
<!-- Em todos os forms POST -->
<form method="POST" action="...">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token }}">
    <!-- ... rest of form ... -->
</form>
```

Templates afetados:
- `intake.html`
- `intake_draft.html`
- `legacy_bridge.html`
- `mandates_proposals.html`
- `mandates_proposal_detail.html`
- `ege_status.html` (rollback form)

---

## Fluxo de Autenticação

### Browser User (novo)

```
1. User acessa /console/
2. Middleware detecta sem cookie válido
3. Accept: text/html → redirect /console/login
4. User cola token no form
5. POST /console/login com token
6. Server valida token
7. Server cria cookie assinado com token_hash + csrf_token
8. Redirect /console/ com Set-Cookie
9. Requests subsequentes enviam cookie automaticamente
10. Server valida cookie em cada request
```

### API Client (mantido)

```
1. Client envia request com X-Admin-Token header
2. Server valida token
3. Se válido → processa request
4. Se inválido → 401 JSON
```

### Logout

```
1. User clica "Logout"
2. GET /console/logout
3. Server limpa cookie (Max-Age=0)
4. Redirect /console/login
```

---

## Testes Necessários

| Test | Description |
|------|-------------|
| `test_login_page_renders` | GET /console/login returns HTML |
| `test_login_requires_token` | POST /console/login without token fails |
| `test_login_invalid_token_shows_error` | POST with invalid token shows error |
| `test_login_valid_token_sets_cookie` | POST with valid token sets session cookie |
| `test_login_redirects_to_next` | POST with valid token redirects to next param |
| `test_logout_clears_cookie` | GET /console/logout clears cookie |
| `test_console_accepts_cookie_auth` | Request with valid cookie succeeds |
| `test_console_accepts_header_auth` | Request with X-Admin-Token still works |
| `test_console_html_redirects_to_login` | HTML request without auth redirects |
| `test_console_json_returns_401` | JSON request without auth returns 401 |
| `test_csrf_required_for_post` | POST without CSRF token fails |
| `test_csrf_invalid_fails` | POST with wrong CSRF token fails |
| `test_csrf_valid_succeeds` | POST with valid CSRF token succeeds |
| `test_session_expires` | Expired cookie is rejected |
| `test_session_invalid_signature` | Tampered cookie is rejected |

---

## Diagrama de Sequência

### Login Flow

```
Browser                     Server
   |                           |
   |  GET /console/            |
   |-------------------------->|
   |                           | (no cookie, Accept: text/html)
   |  303 /console/login       |
   |<--------------------------|
   |                           |
   |  GET /console/login       |
   |-------------------------->|
   |                           |
   |  200 login.html           |
   |<--------------------------|
   |                           |
   |  POST /console/login      |
   |  token=xxx                |
   |-------------------------->|
   |                           | verify_admin_token(xxx)
   |                           | create_session_cookie()
   |  303 /console/            |
   |  Set-Cookie: console_session=...
   |<--------------------------|
   |                           |
   |  GET /console/            |
   |  Cookie: console_session=...|
   |-------------------------->|
   |                           | verify_session_cookie()
   |  200 index.html           |
   |<--------------------------|
```

### POST with CSRF

```
Browser                     Server
   |                           |
   |  GET /console/intake      |
   |  Cookie: console_session=...|
   |-------------------------->|
   |                           | extract csrf_token from session
   |  200 intake.html          |
   |  (includes csrf_token hidden field)
   |<--------------------------|
   |                           |
   |  POST /console/intake     |
   |  Cookie: console_session=...|
   |  _csrf_token=xxx&input_text=...|
   |-------------------------->|
   |                           | verify csrf_token matches session
   |  200 intake_draft.html    |
   |<--------------------------|
```
