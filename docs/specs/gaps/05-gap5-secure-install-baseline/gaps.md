# GAP 5 — Diagnóstico: Secure Install Baseline

## 1. Resumo Executivo

**Objetivo:** Garantir que uma instalação single-instance em produção tenha baseline seguro com:
- Preflight que falha determinísticamente quando requisitos mínimos não são atendidos
- Instituições criadas já nasçam com defaults seguros
- Runbook/checklist verificáveis

**Estado atual:**
- `ENGINE_INSTALL_MODE` já existe (GAP 3): `src/engine/core/install_mode.py`
- Preflight valida: path isolation, `ENGINE_CONSOLE_SESSION_SECRET`
- Defaults de instituição são **permissivos** (inseguros para produção)
- Não há enforcement de `ENGINE_AUTH_MODE=strict` ou `ENGINE_ISE_ADMIN_TOKEN` no preflight

---

## 2. Mapeamento: ENV Vars Obrigatórias para Produção

### 2.1 ENVs já documentadas em `ops/env/engine.env.example`

| ENV | Propósito | Obrigatório Prod? | Validado Preflight? |
|-----|-----------|-------------------|---------------------|
| `ENGINE_CONSOLE_SESSION_SECRET` | Assinatura de cookies | ✅ SIM | ✅ SIM (linhas 116-134 preflight.py) |
| `ENGINE_ISE_ADMIN_TOKEN` | Token admin para /admin/* | ✅ SIM | ❌ NÃO |
| `ENGINE_DATA_ROOT` | Root de dados multi-tenant | ✅ SIM | ❌ NÃO (assume default) |
| `ENGINE_BUNDLE_PATH` | Caminho do bundle | ✅ SIM | ❌ NÃO (valida na carga) |

### 2.2 ENVs de segurança não validadas no preflight

| ENV | Propósito | Default Atual | Valor Seguro |
|-----|-----------|---------------|--------------|
| `ENGINE_AUTH_MODE` | Modo de autenticação | `dev` | `strict` |
| `ENGINE_INSTALL_MODE` | Modo de instalação | `dev` | `prod` |
| `ENGINE_CONSOLE_SECURE_COOKIE` | Cookie HTTPS | `auto` | `true` |

### 2.3 Onde cada ENV é lida

```
ENGINE_CONSOLE_SESSION_SECRET:
  └── src/engine/console/session.py:38 (get_session_secret)
  └── src/engine/core/preflight.py:124 (check_console_session_secret)

ENGINE_ISE_ADMIN_TOKEN:
  └── src/engine/ise/release.py:18 (ENV_ADMIN_TOKEN)
  └── src/engine/api/admin_institutions.py:90 (verify_admin_token)

ENGINE_AUTH_MODE:
  └── src/engine/core/actor_context.py:33 (get_auth_mode)
  └── src/engine/api/dependencies.py:111 (get_auth_mode)

ENGINE_INSTALL_MODE:
  └── src/engine/core/install_mode.py:27 (get_install_mode)
```

---

## 3. Análise: O que Preflight Valida Hoje

### 3.1 Estrutura atual (`src/engine/core/preflight.py`)

```python
def run_preflight_checks() -> PreflightResult:
    # Check 1: Path isolation in multi-tenant mode
    multi_tenant_active = is_multi_tenant_mode_active()
    path_check = check_path_isolation(require_multi_tenant=multi_tenant_active)
    if not path_check.ok:
        return path_check

    # Check 2: Console session secret
    session_check = check_console_session_secret()
    if not session_check.ok:
        return session_check

    return PreflightResult(ok=True)
```

### 3.2 Verificações existentes

| Check | Descrição | Resultado em falha |
|-------|-----------|-------------------|
| `check_path_isolation` | ENVs absolutas em multi-tenant | `PATH_MISCONFIG_ABSOLUTE_*` |
| `check_console_session_secret` | Secret de sessão configurado | `CONSOLE_SESSION_SECRET_MISSING` |

### 3.3 O que FALTA no preflight para produção

| Check Faltando | Quando Aplicar | Código de Erro Proposto |
|----------------|----------------|------------------------|
| `ENGINE_ISE_ADMIN_TOKEN` presente | `ENGINE_INSTALL_MODE=prod` | `ADMIN_TOKEN_MISSING` |
| `ENGINE_AUTH_MODE=strict` | `ENGINE_INSTALL_MODE=prod` | `AUTH_MODE_INSECURE` |

---

## 4. Análise: Defaults Inseguros na Criação de Instituição

### 4.1 Defaults atuais (`src/engine/core/institution_config.py:50-57`)

```python
@dataclass
class ConfigFlags:
    require_institution_header_for_runtime: bool = False  # ⚠️ INSEGURO
    allow_legacy_routes: bool = True                      # ⚠️ INSEGURO
    enable_contracts_stub: bool = True                    # ⚠️ INSEGURO
```

### 4.2 Impacto de cada default inseguro

| Flag | Default Atual | Risco em Produção |
|------|---------------|-------------------|
| `require_institution_header_for_runtime=False` | Single-tenant mode | Cross-tenant data access se múltiplas instituições |
| `allow_legacy_routes=True` | Rotas `/finance/*` abertas | Bypass de gates de segurança legados |
| `enable_contracts_stub=True` | Stubs de contrato | Contratos não verificados passam |

### 4.3 Onde instituição é criada

```
src/engine/core/institutions.py:272-332
└── InstitutionsRegistry.create()
    └── _save_institution_meta() → institution.json
    └── NÃO cria config/ACTIVE.json com defaults seguros
```

**Problema:** Ao criar instituição, NÃO é criado `config/ACTIVE.json`. O config é criado apenas quando admin explicitamente salva via PUT.

---

## 5. Análise: Smoke Test e Runbook

### 5.1 Estado atual do smoke test (`ops/checks/smoke_test.sh`)

| Teste | O que valida |
|-------|--------------|
| Test 1 | `/health` → 200 + `"status":"ok"` |
| Test 2 | `/console/` → 200 ou 302 |
| Test 3 | `/console/login` → 200 + campo `admin_token` |
| Test 4-7 | Workflow de expense (opcional) |

**Conforme spec:** Smoke test já cobre `/health` e `/console/login`. ✅

### 5.2 Estado do `engine.env.example`

O arquivo documenta as ENVs mas NÃO inclui:
- `ENGINE_INSTALL_MODE=prod`
- `ENGINE_AUTH_MODE=strict`

---

## 6. Proposta de Patch Mínimo

### 6.1 Mudanças necessárias

| Arquivo | Mudança | Linhas Est. |
|---------|---------|-------------|
| `src/engine/core/preflight.py` | Adicionar checks para prod mode | +35 |
| `src/engine/core/errors.py` | Novos códigos de erro | +6 |
| `src/engine/core/institutions.py` | Criar config com defaults seguros em prod | +25 |
| `src/engine/core/institution_config.py` | Helper para defaults seguros | +15 |
| `ops/env/engine.env.example` | Adicionar ENVs de segurança | +10 |
| `tests/test_preflight_prod.py` | Testes de preflight prod | +80 |
| `tests/test_institution_secure_defaults.py` | Testes de defaults seguros | +60 |

**Total estimado: ~230 linhas**

### 6.2 Novos códigos de erro

```python
# src/engine/core/errors.py

# GAP 5: Secure Install Baseline
PREFLIGHT_ADMIN_TOKEN_MISSING = "PREFLIGHT_ADMIN_TOKEN_MISSING"
PREFLIGHT_AUTH_MODE_INSECURE = "PREFLIGHT_AUTH_MODE_INSECURE"
```

### 6.3 Preflight checks para prod mode

```python
# src/engine/core/preflight.py

def check_prod_mode_requirements() -> PreflightResult:
    """Check production mode requirements.

    In ENGINE_INSTALL_MODE=prod:
    - ENGINE_ISE_ADMIN_TOKEN must be set
    - ENGINE_AUTH_MODE must be 'strict'
    """
    from engine.core.install_mode import is_prod_mode

    if not is_prod_mode():
        return PreflightResult(ok=True)  # Dev mode - skip checks

    # Check 1: Admin token must be set
    admin_token = os.environ.get("ENGINE_ISE_ADMIN_TOKEN")
    if not admin_token:
        return PreflightResult(
            ok=False,
            code=PREFLIGHT_ADMIN_TOKEN_MISSING,
            message=(
                "Production mode requires ENGINE_ISE_ADMIN_TOKEN. "
                "Set a secure random token for admin API authentication."
            ),
        )

    # Check 2: Auth mode must be strict
    auth_mode = os.environ.get("ENGINE_AUTH_MODE", "dev").lower()
    if auth_mode != "strict":
        return PreflightResult(
            ok=False,
            code=PREFLIGHT_AUTH_MODE_INSECURE,
            message=(
                f"Production mode requires ENGINE_AUTH_MODE=strict. "
                f"Current value: '{auth_mode}'. "
                "Strict mode ensures actor identity is verified via tokens."
            ),
        )

    return PreflightResult(ok=True)


def run_preflight_checks() -> PreflightResult:
    """Run all preflight checks."""
    # Check 1: Path isolation in multi-tenant mode
    multi_tenant_active = is_multi_tenant_mode_active()
    path_check = check_path_isolation(require_multi_tenant=multi_tenant_active)
    if not path_check.ok:
        return path_check

    # Check 2: Console session secret
    session_check = check_console_session_secret()
    if not session_check.ok:
        return session_check

    # Check 3: Production mode requirements (GAP 5)
    prod_check = check_prod_mode_requirements()
    if not prod_check.ok:
        return prod_check

    return PreflightResult(ok=True)
```

### 6.4 Defaults seguros na criação de instituição

```python
# src/engine/core/institution_config.py

def get_secure_defaults_for_prod() -> Dict[str, Any]:
    """Get secure default config for production mode.

    Returns:
        Config dict with secure defaults for production.
    """
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "flags": {
            "require_institution_header_for_runtime": True,
            "allow_legacy_routes": False,
            "enable_contracts_stub": False,
        },
        "limits": {
            "rate_limit_per_minute": _get_default_rate_limit(),
            "max_body_bytes": _get_default_max_body_bytes(),
        },
        "defaults": {
            "default_dept": "finance",
            "default_bundle_name": "finance-pilot",
        },
        "freeze_mode": False,
        "emergency_stop": {
            "enabled": False,
            "blocked_endpoints": [],
        },
    }
```

```python
# src/engine/core/institutions.py (modificar create())

def create(self, slug, display_name=None):
    # ... existing code ...

    # Save metadata file
    if not self._save_institution_meta(institution):
        return None, INSTITUTION_META_UNAVAILABLE, "..."

    # GAP 5: Create config with secure defaults in prod mode
    from engine.core.install_mode import is_prod_mode
    if is_prod_mode():
        from engine.core.institution_config import (
            get_secure_defaults_for_prod,
            save_active_config,
        )
        secure_config = get_secure_defaults_for_prod()
        save_active_config(
            institution_id=institution_id,
            config_dict=secure_config,
            updated_by="system:secure_defaults",
        )

    # Emit ledger event
    self._emit_created_event(institution)

    return institution, None, None
```

### 6.5 Atualização do engine.env.example

```bash
# ==============================================================================
# SECURITY MODES (GAP 2, GAP 3, GAP 5)
# ==============================================================================

# Installation mode: "dev" (relaxed) or "prod" (strict enforcement)
# IMPORTANT: Set to "prod" for production deployments
ENGINE_INSTALL_MODE=prod

# Authentication mode: "dev" (trust headers) or "strict" (require tokens)
# IMPORTANT: Set to "strict" for production deployments
ENGINE_AUTH_MODE=strict
```

---

## 7. Fluxo de Verificação

### 7.1 Startup em prod mode

```
Server Start
    │
    ▼
lifespan(app)
    │
    ├── verify_ledger_file()
    │
    ├── load_bundle()
    │
    └── run_preflight_checks()
            │
            ├── check_path_isolation()
            │       └── Se multi-tenant + paths absolutos → FAIL
            │
            ├── check_console_session_secret()
            │       └── Se secret ausente/curto → FAIL
            │
            └── check_prod_mode_requirements()  ◄── NOVO (GAP 5)
                    │
                    ├── Se ENGINE_INSTALL_MODE != prod → SKIP
                    │
                    ├── Se ENGINE_ISE_ADMIN_TOKEN ausente → FAIL
                    │
                    └── Se ENGINE_AUTH_MODE != strict → FAIL
```

### 7.2 Criação de instituição em prod mode

```
POST /admin/institutions
    │
    ▼
InstitutionsRegistry.create()
    │
    ├── validate_slug()
    │
    ├── append_to_registry()
    │
    ├── save_institution_meta()
    │
    ├── [GAP 5] Se ENGINE_INSTALL_MODE=prod:
    │       └── save_active_config(secure_defaults)
    │
    └── emit_created_event()
```

---

## 8. Testes Necessários

### 8.1 Testes de preflight prod mode

| # | Cenário | Resultado Esperado |
|---|---------|-------------------|
| 1 | `ENGINE_INSTALL_MODE=prod` + sem `ENGINE_ISE_ADMIN_TOKEN` | Preflight FAIL: `PREFLIGHT_ADMIN_TOKEN_MISSING` |
| 2 | `ENGINE_INSTALL_MODE=prod` + `ENGINE_AUTH_MODE=dev` | Preflight FAIL: `PREFLIGHT_AUTH_MODE_INSECURE` |
| 3 | `ENGINE_INSTALL_MODE=prod` + token + strict | Preflight PASS |
| 4 | `ENGINE_INSTALL_MODE=dev` (default) | Preflight PASS (skip checks) |

### 8.2 Testes de defaults seguros

| # | Cenário | Resultado Esperado |
|---|---------|-------------------|
| 1 | Criar instituição em `ENGINE_INSTALL_MODE=prod` | `config/ACTIVE.json` com flags seguros |
| 2 | Criar instituição em `ENGINE_INSTALL_MODE=dev` | Sem `config/ACTIVE.json` (comportamento atual) |
| 3 | Flags em prod: `require_institution_header_for_runtime=True` | ✅ |
| 4 | Flags em prod: `allow_legacy_routes=False` | ✅ |
| 5 | Flags em prod: `enable_contracts_stub=False` | ✅ |

---

## 9. Matriz de Decisão: Comportamento por Modo

| Cenário | `ENGINE_INSTALL_MODE` | `ENGINE_AUTH_MODE` | Preflight | Defaults Instituição |
|---------|----------------------|-------------------|-----------|---------------------|
| Dev local | `dev` (default) | `dev` (default) | ✅ PASS | Permissivos |
| Testes CI | `dev` | `dev` ou `strict` | ✅ PASS | Permissivos |
| Staging | `prod` | `strict` | ✅ PASS (se token) | Seguros |
| Produção | `prod` | `strict` | ✅ PASS (se token) | Seguros |
| Produção mal-configurada | `prod` | `dev` | ❌ FAIL | N/A |

---

## 10. Riscos e Mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Dev seta `ENGINE_INSTALL_MODE=prod` por engano | Preflight falha sem tokens | Default é `dev`, explícito em docs |
| Instituição existente não tem config seguro | Flags inseguros | Não retroativo, apenas novas instituições |
| Prod sem secrets configurados | Server não inicia | Preflight determinístico, fail-fast |

---

## 11. Dependências de Outros GAPs

| GAP | Dependência | Status |
|-----|-------------|--------|
| GAP 2 | `ENGINE_AUTH_MODE=strict` implementado | ✅ Completo |
| GAP 3 | `ENGINE_INSTALL_MODE` implementado | ✅ Completo |
| GAP 4 | N/A | ✅ Completo |

---

## 12. Checklist de Implementação

### Fase 1: Preflight Prod Mode
- [x] Adicionar `PREFLIGHT_ADMIN_TOKEN_MISSING` em `errors.py`
- [x] Adicionar `PREFLIGHT_AUTH_MODE_INSECURE` em `errors.py`
- [x] Implementar `check_prod_mode_requirements()` em `preflight.py`
- [x] Chamar em `run_preflight_checks()`
- [x] Testes: 15 cenários de preflight prod

### Fase 2: Defaults Seguros
- [x] Implementar `get_secure_config_flags()` em `institution_config.py`
- [x] Implementar `get_secure_defaults_for_prod()` em `institution_config.py`
- [x] Implementar `create_secure_config_for_institution()` em `institution_config.py`
- [x] Modificar `InstitutionsRegistry.create()` com `_create_secure_config_if_prod()`
- [x] Testes: 15 cenários de defaults seguros

### Fase 3: Documentação
- [x] Atualizar `ops/env/engine.env.example` com ENGINE_INSTALL_MODE e ENGINE_AUTH_MODE

---

## 13. Implementação Final (PROMPT 05.2)

### 13.1 Arquivos Modificados

| Arquivo | Mudança | Linhas |
|---------|---------|--------|
| `src/engine/core/errors.py` | +2 códigos de erro | +4 |
| `src/engine/core/preflight.py` | +`check_prod_mode_requirements()` | +52 |
| `src/engine/core/institution_config.py` | +3 funções para secure defaults | +65 |
| `src/engine/core/institutions.py` | +`_create_secure_config_if_prod()` | +42 |
| `ops/env/engine.env.example` | +seção de security modes | +16 |

### 13.2 Arquivos Criados

| Arquivo | Descrição | Testes |
|---------|-----------|--------|
| `tests/test_preflight_prod_mode.py` | Testes de preflight prod | 15 |
| `tests/test_institution_secure_defaults.py` | Testes de defaults seguros | 15 |

### 13.3 Novos Códigos de Erro

```python
# src/engine/core/errors.py

# Preflight errors (GAP 5 - Secure Install Baseline)
PREFLIGHT_ADMIN_TOKEN_MISSING = "PREFLIGHT_ADMIN_TOKEN_MISSING"
PREFLIGHT_AUTH_MODE_INSECURE = "PREFLIGHT_AUTH_MODE_INSECURE"
```

### 13.4 Nova Função de Preflight

```python
# src/engine/core/preflight.py

def check_prod_mode_requirements() -> PreflightResult:
    """Check production mode security requirements.

    GAP 5: In ENGINE_INSTALL_MODE=prod, enforce:
    - ENGINE_ISE_ADMIN_TOKEN must be set
    - ENGINE_AUTH_MODE must be 'strict'
    """
    from engine.core.install_mode import is_prod_mode

    if not is_prod_mode():
        return PreflightResult(ok=True)  # Dev mode skips

    # Check admin token
    if not os.environ.get("ENGINE_ISE_ADMIN_TOKEN"):
        return PreflightResult(
            ok=False,
            code=PREFLIGHT_ADMIN_TOKEN_MISSING,
            message="Production mode requires ENGINE_ISE_ADMIN_TOKEN"
        )

    # Check auth mode is strict
    if os.environ.get("ENGINE_AUTH_MODE", "dev").lower() != "strict":
        return PreflightResult(
            ok=False,
            code=PREFLIGHT_AUTH_MODE_INSECURE,
            message="Production mode requires ENGINE_AUTH_MODE=strict"
        )

    return PreflightResult(ok=True)
```

### 13.5 Secure Defaults para Instituições

```python
# src/engine/core/institution_config.py

def get_secure_config_flags() -> ConfigFlags:
    """Secure flags for production."""
    return ConfigFlags(
        require_institution_header_for_runtime=True,
        allow_legacy_routes=False,
        enable_contracts_stub=False,
    )

def get_secure_defaults_for_prod() -> Dict[str, Any]:
    """Complete config dict with secure defaults."""
    # ... returns full config dict

def create_secure_config_for_institution(institution_id, updated_by) -> Tuple:
    """Create secure config for new institution."""
    # ... saves ACTIVE.json with secure defaults
```

### 13.6 Hook na Criação de Instituição

```python
# src/engine/core/institutions.py

def _create_secure_config_if_prod(self, institution_id: str) -> None:
    """Create secure config if ENGINE_INSTALL_MODE=prod.

    Silent operation - doesn't fail institution creation if config fails.
    """
    from engine.core.install_mode import is_prod_mode

    if not is_prod_mode():
        return

    from engine.core.institution_config import create_secure_config_for_institution
    create_secure_config_for_institution(
        institution_id=institution_id,
        updated_by="system:secure_defaults",
    )
```

### 13.7 Resultados dos Testes

```
tests/test_preflight_prod_mode.py ................... 15 passed
tests/test_institution_secure_defaults.py ........... 15 passed

Total: 30 tests passed
```

---

## 14. GAP 5.3 - Non-Silent Prod Mode (PROMPT 05.3)

### 14.1 Problema Identificado

Na implementação inicial (PROMPT 05.2), se `ENGINE_INSTALL_MODE=prod` e a criação de `config/ACTIVE.json` falhasse, a instituição era criada mesmo assim (operação "silent"). Isso permitia que uma instituição nascesse sem baseline seguro em produção.

### 14.2 Correção Aplicada

**Decisão:** Em `ENGINE_INSTALL_MODE=prod`, se falhar criar `config/ACTIVE.json` com defaults seguros, a criação da instituição deve **falhar determinísticamente**.

### 14.3 Mudanças Implementadas

| Arquivo | Mudança |
|---------|---------|
| `src/engine/core/errors.py` | +`INSTITUTION_SECURE_CONFIG_REQUIRED` |
| `src/engine/core/institutions.py` | Modificou `_create_secure_config_if_prod()` para retornar `(ok, error_code, error_message)` e `create()` para falhar se `ok=False` em prod |
| `tests/test_institution_secure_defaults.py` | +7 testes para GAP 5.3 |

### 14.4 Novo Código de Erro

```python
# src/engine/core/errors.py
INSTITUTION_SECURE_CONFIG_REQUIRED = "INSTITUTION_SECURE_CONFIG_REQUIRED"
```

### 14.5 Comportamento Final

| Modo | Config Falha? | Resultado |
|------|---------------|-----------|
| `ENGINE_INSTALL_MODE=prod` | Sim | ❌ Instituição **NÃO** criada, retorna `INSTITUTION_SECURE_CONFIG_REQUIRED` |
| `ENGINE_INSTALL_MODE=prod` | Não | ✅ Instituição criada com secure defaults |
| `ENGINE_INSTALL_MODE=dev` | N/A | ✅ Instituição criada (config não é criado) |
| Default (não setado) | N/A | ✅ Instituição criada (dev mode) |

### 14.6 Testes GAP 5.3

| Teste | Cenário |
|-------|---------|
| `test_prod_mode_fails_if_config_creation_fails` | Mock config failure → institution fails |
| `test_prod_mode_fails_with_deterministic_error_code` | Error code always `INSTITUTION_SECURE_CONFIG_REQUIRED` |
| `test_prod_mode_fails_on_exception` | Exception → institution fails |
| `test_dev_mode_continues_on_config_failure` | Dev mode → institution succeeds |
| `test_dev_mode_backward_compatible_no_config` | Dev mode → no config created |
| `test_default_mode_backward_compatible` | No mode set → dev behavior |
| `test_institution_secure_config_required_defined` | Error code exists |

### 14.7 Resultados Atualizados

```
tests/test_preflight_prod_mode.py ................... 15 passed
tests/test_institution_secure_defaults.py ........... 22 passed (+ 7 GAP 5.3)

Total: 37 tests passed
```

---

## 15. Conclusão

O GAP 5 foi implementado como **patch incremental** aproveitando infraestrutura existente:

1. **`ENGINE_INSTALL_MODE`** já existia (GAP 3)
2. **Preflight** já tinha framework de checks (Etapa 2.6)
3. **Institution config** já tinha estrutura de flags

As mudanças foram:
- **+2 checks no preflight** para prod mode
- **+1 hook em `create()`** para defaults seguros (com falha determinística em prod)
- **~200 linhas de código** + **~400 linhas de testes**

**GAP 5.3** garantiu que a criação de instituição em prod mode seja **honesta**: se o baseline seguro não puder ser criado, a operação falha com erro determinístico (`INSTITUTION_SECURE_CONFIG_REQUIRED`).

Não houve redesign de arquitetura, apenas enforcement de segurança quando `ENGINE_INSTALL_MODE=prod`.
