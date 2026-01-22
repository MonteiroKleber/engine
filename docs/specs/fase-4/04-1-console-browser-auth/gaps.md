# 04-1 Console Browser Auth - Gaps Analysis

**Status:** IMPLEMENTADO ✅
**Data:** 2026-01-19

## Resumo

Análise de gaps entre a spec.md e a implementação atual para autenticação de browser no console.

**Implementação concluída** com todos os requisitos atendidos.

## Implementação Realizada

### Arquivos Criados/Modificados

| Arquivo | Status | Descrição |
|---------|--------|-----------|
| `console/session.py` | NOVO | Módulo de sessão com cookies assinados |
| `console/routes.py` | MODIFICADO | Login/logout, dual-auth, CSRF |
| `console/templates/login.html` | NOVO | Página de login |
| `console/templates/base.html` | MODIFICADO | Link de logout no nav |
| `core/preflight.py` | MODIFICADO | Check para session secret |
| `core/errors.py` | MODIFICADO | Códigos de erro |
| `api/server.py` | MODIFICADO | Exception handler para redirect |
| `tests/test_console.py` | MODIFICADO | 14 novos testes |

### Funcionalidades Implementadas

#### 1. Sessão via Cookie Assinado ✅

**Módulo:** `console/session.py`

- Cookie assinado com `itsdangerous.URLSafeTimedSerializer`
- TTL configurável via `ENGINE_CONSOLE_SESSION_TTL_HOURS` (default: 8h)
- Estrutura do cookie: `{th: token_hash[:16], csrf: csrf_token, n: nonce}`
- Cookie name: `console_session`
- Atributos: `HttpOnly`, `SameSite=Strict`, `Secure` (auto em HTTPS)

#### 2. Rotas de Login/Logout ✅

| Rota | Método | Descrição |
|------|--------|-----------|
| `/console/login` | GET | Página de login (sem auth) |
| `/console/login` | POST | Valida token, seta cookie, redireciona |
| `/console/logout` | GET | Limpa cookie, redireciona para login |

#### 3. Dual-Auth (Cookie OR Header) ✅

**Função:** `_require_console_auth()`

- Verifica `X-Admin-Token` header primeiro (para curl/automação)
- Se header ausente, verifica cookie `console_session`
- Se nenhum válido:
  - `Accept: text/html` → redirect 303 para `/console/login`
  - Outros → 401 JSON

#### 4. CSRF Protection ✅

**Função:** `_require_csrf_token()`

- Token CSRF gerado com a sessão e embutido no cookie
- Validado em POSTs quando autenticado via cookie
- Header auth (X-Admin-Token) isenta de CSRF (automação/curl)
- Token passado via hidden field `_csrf_token`

**Rotas protegidas:**
- `POST /console/legacy/{asset_id}/verify`
- `POST /console/intake`
- `POST /console/intake/answer`
- `POST /console/intake/finalize`
- `POST /console/mandates/proposals`
- `POST /console/mandates/proposals/{id}/decide`
- `POST /console/ege/rollback`

#### 5. Preflight Check ✅

**Requisito:** `ENGINE_CONSOLE_SESSION_SECRET` deve estar configurado.

- Se ausente → startup falha com `CONSOLE_SESSION_SECRET_MISSING`
- Não gera secret automaticamente (decisão de segurança)

#### 6. Templates Atualizados ✅

- `login.html`: formulário de login
- `base.html`: link de logout no nav
- Todos os templates com forms: hidden field `_csrf_token`

## Configuração

### Environment Variables

| Variável | Obrigatório | Default | Descrição |
|----------|-------------|---------|-----------|
| `ENGINE_CONSOLE_SESSION_SECRET` | ✅ Sim | - | Secret para assinar cookies (min 32 chars) |
| `ENGINE_CONSOLE_SESSION_TTL_HOURS` | Não | 8 | TTL da sessão em horas |
| `ENGINE_ISE_ADMIN_TOKEN` | ✅ Sim | - | Token de admin (existente) |

## Testes

14 novos testes adicionados em `tests/test_console.py`:

```
TestConsoleBrowserAuthLogin
  - test_login_page_accessible_without_auth
  - test_login_page_shows_form
  - test_login_post_invalid_token_shows_error
  - test_login_post_valid_token_sets_cookie
  - test_login_post_redirects_to_next

TestConsoleBrowserAuthLogout
  - test_logout_clears_cookie
  - test_logout_redirects_to_login

TestConsoleBrowserAuthCookieAuth
  - test_console_accepts_cookie_auth
  - test_console_header_auth_still_works

TestConsoleBrowserAuthHtmlRedirect
  - test_html_request_without_auth_redirects_to_login
  - test_json_request_without_auth_returns_401

TestConsoleBrowserAuthCSRF
  - test_post_with_cookie_without_csrf_fails
  - test_post_with_header_auth_no_csrf_required

TestConsoleBrowserAuthNavLogout
  - test_base_template_has_logout_link
```

## Definition of Done (da spec.md)

- [x] Usuário acessa `/console/` no browser, faz login com token, navega sem header
- [x] POSTs do console exigem CSRF e continuam exigindo auth
- [x] `X-Admin-Token` continua funcionando para automação/curl

## Gaps Fechados

| GAP | Status | Resolução |
|-----|--------|-----------|
| GAP-1: Falta rotas de login/logout | ✅ | Implementado em routes.py |
| GAP-2: Falta sessão via cookie | ✅ | session.py com itsdangerous |
| GAP-3: Falta CSRF protection | ✅ | _require_csrf_token() |
| GAP-4: Falta dual-auth | ✅ | _require_console_auth() |
| GAP-5: CORS para cookies | N/A | Console é same-origin |
| GAP-6: Falta template login | ✅ | login.html criado |
| GAP-7: Timing-safe compare | ✅ | secrets.compare_digest() usado |
