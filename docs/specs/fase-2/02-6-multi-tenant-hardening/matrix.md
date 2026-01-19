# Multi-Tenant Hardening - ENV/Config Matrix

**Data:** 2026-01-18
**Tipo:** Matriz de configurações para PROMPT 2.6.1
**Status:** ✅ IMPLEMENTADO (PROMPT 2.6.2)

---

## Resumo Executivo

Este documento lista todas as variáveis de ambiente e configurações que influenciam paths e isolamento multi-tenant. Identifica quais combinações podem quebrar isolamento por acidente.

---

## 1. Variáveis de Path Críticas

### 1.1 ENGINE_DATA_ROOT

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/core/data_root.py:17` |
| **Default** | `"var"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Raiz para todos os dados institution-specific |

**Comportamento:**
```python
def get_data_root() -> Path:
    env_value = os.environ.get("ENGINE_DATA_ROOT")
    if env_value:
        return Path(env_value)
    return Path(DEFAULT_DATA_ROOT)

def get_institution_root(institution_id: str) -> Path:
    data_root = get_data_root()
    return data_root / "institutions" / institution_id
```

**Risco:** BAIXO - Sempre usado como base para namespace.

---

### 1.2 ENGINE_LEDGER_PATH

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/core/ledger.py:37-38` |
| **Default** | `"var/audit_ledger.jsonl"` (legacy) / `"audit_ledger.jsonl"` (per-inst) |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Caminho do ledger de auditoria |

**Comportamento (resolve_namespaced_path):**
```python
def resolve_namespaced_path(institution_id, env_value, default_rel) -> Path:
    institution_root = get_institution_root(institution_id)

    if env_value is None:
        return institution_root / default_rel    # SAFE: per-institution

    env_path = Path(env_value)
    if env_path.is_absolute():
        return env_path                          # DANGER: bypasses namespace!

    return institution_root / env_value          # SAFE: per-institution
```

**Risco:** ALTO
- Se `ENGINE_LEDGER_PATH=/var/log/audit.jsonl` (absoluto), TODAS as instituições compartilham o mesmo ledger.
- Quebra isolamento multi-tenant completamente.

---

### 1.3 ENGINE_STATE_STORE_DIR

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/core/state_store.py:25-28, 70-111` |
| **Default** | `"var"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Diretório do state store (expenses, tickets, etc.) |

**Comportamento:**
```python
def get_state_store_path_for_institution(institution_id, dept_id=None) -> Path:
    env_value = os.environ.get("ENGINE_STATE_STORE_DIR")

    if env_value is None:
        base_path = resolve_namespaced_path(institution_id, None, "")
    elif Path(env_value).is_absolute():
        base_path = Path(env_value)  # DANGER: shared across all institutions!
    else:
        base_path = resolve_namespaced_path(institution_id, None, env_value)
```

**Risco:** ALTO
- Se `ENGINE_STATE_STORE_DIR=/data/state` (absoluto), instituições compartilham state store.
- Pode causar vazamento de dados entre tenants.

---

### 1.4 ENGINE_PROD_BUNDLES_ROOT

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/ise/release.py:39,56` |
| **Default** | `"/var/lib/engine/bundles"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Diretório raiz para bundles de produção |

**Comportamento:**
```python
def get_bundles_root_for_institution(institution_id: str) -> Path:
    env_value = os.environ.get(ENV_PROD_BUNDLES_ROOT)
    return resolve_namespaced_path(institution_id, env_value, DEFAULT_BUNDLES_REL_PATH)
```

**Risco:** ALTO
- Default é absoluto (`/var/lib/engine/bundles`), mas usa `resolve_namespaced_path`.
- Se mantido absoluto, todas instituições usam mesmos bundles.
- Pode ser intencional (bundles compartilhados) ou misconfig.

---

### 1.5 ENGINE_DEV_RUNS_REGISTRY_PATH

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/pipeline/registry.py:27,45` |
| **Default** | `"var/dev_runs_registry.jsonl"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Registry de dev runs |

**Comportamento:** Usa `resolve_namespaced_path` - mesma lógica.

**Risco:** MÉDIO
- Se absoluto, dev runs de todas instituições vão para mesmo arquivo.
- Impacto menor (dev-only), mas ainda quebra isolamento de dados.

---

### 1.6 ENGINE_BUNDLE_PATH (Dev-time)

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/loader/load_bundle.py:112` |
| **Default** | `"bundles/finance-pilot"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Bundle path para loading inicial |

**Risco:** BAIXO
- Usado apenas em dev/test.
- Não é per-institution (bundle é compartilhado por design).

---

### 1.7 ENGINE_INSTITUTIONS_REGISTRY_PATH

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/core/institutions.py:94` |
| **Default** | `"var/institutions_registry.jsonl"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Registry global de todas as instituições |

**Risco:** BAIXO (por design)
- É intencionalmente global - lista todas as instituições.
- Não contém dados sensíveis per-tenant.

---

### 1.8 ENGINE_INSTITUTIONS_DIR

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/core/institutions.py:102` |
| **Default** | `"var/institutions"` |
| **Tipo** | Path (relativo ou absoluto) |
| **Função** | Diretório base para metadados de instituições |

**Risco:** BAIXO
- Usado para armazenar metadata de cada instituição.
- Estrutura interna já é namespaced por institution_id.

---

## 2. Flags de Configuração Relevantes

### 2.1 require_institution_header_for_runtime

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `src/engine/core/institution_config.py:54` |
| **Default** | `False` |
| **Tipo** | Boolean |
| **Função** | Força uso de X-Institution-Id header |

**Comportamento:**
- Se `True`: requests sem X-Institution-Id são rejeitados (400).
- Se `False`: fallback para X-Tenant-Id ou DEFAULT_INSTITUTION_ID.

**Risco em combinação:**
- Se `require_institution_header_for_runtime=True` E paths absolutos estão configurados:
  - Header enforcement funciona, MAS dados ainda vão para path compartilhado.
  - **Falsa sensação de segurança.**

---

## 3. Matriz de Risco: Path Absoluto × Multi-Tenant

| ENV Variable | Absoluto | Multi-Tenant Ativo | Resultado |
|--------------|----------|-------------------|-----------|
| ENGINE_LEDGER_PATH | `/var/audit.jsonl` | `require_institution_header=true` | **QUEBRA ISOLAMENTO**: Todas inst. escrevem no mesmo ledger |
| ENGINE_STATE_STORE_DIR | `/data/state` | `require_institution_header=true` | **QUEBRA ISOLAMENTO**: Expenses/tickets compartilhados |
| ENGINE_PROD_BUNDLES_ROOT | `/var/lib/bundles` | `require_institution_header=true` | **POSSÍVEL**: Bundles podem ser intencionalmente compartilhados |
| ENGINE_DEV_RUNS_REGISTRY_PATH | `/var/dev.jsonl` | `require_institution_header=true` | **MENOR**: Apenas dev runs afetados |
| ENGINE_DATA_ROOT | `/data` | `require_institution_header=true` | **OK**: Namespace ainda funciona via `institutions/` subdir |

---

## 4. Combinações Perigosas Identificadas

### DANGER-1: Ledger Absoluto em Multi-Tenant
```bash
ENGINE_LEDGER_PATH=/var/log/engine/audit.jsonl
# + institution com require_institution_header_for_runtime=true
```
**Resultado:** Todos os eventos de TODAS as instituições vão para mesmo arquivo.
- Quebra audit isolation
- Compliance violation (LGPD, SOX, etc.)

### DANGER-2: State Store Absoluto em Multi-Tenant
```bash
ENGINE_STATE_STORE_DIR=/data/engine/state
# + institution com require_institution_header_for_runtime=true
```
**Resultado:** Expenses, tickets, e outros estados compartilhados.
- Vazamento de dados entre tenants
- Potencial acesso cross-tenant

### DANGER-3: Default Produção do BUNDLES_ROOT
```bash
# Default: ENGINE_PROD_BUNDLES_ROOT=/var/lib/engine/bundles
```
**Resultado:** Pode ser intencional (bundles são os mesmos para todos), mas se instituições precisam de bundles diferentes, há conflito.

---

## 5. Detecção e Guardrails (IMPLEMENTADO)

### Implementação (PROMPT 2.6.2):

**Preflight Check:** `src/engine/core/preflight.py`
```python
def check_path_isolation(require_multi_tenant: bool = False) -> PreflightResult:
    """Check that critical path ENVs don't break multi-tenant isolation."""
    if not require_multi_tenant:
        return PreflightResult(ok=True)  # Single-tenant allows any path

    for env_name, error_code in CRITICAL_PATH_ENVS.items():
        env_value = os.environ.get(env_name)
        if env_value is not None and Path(env_value).is_absolute():
            return PreflightResult(
                ok=False,
                code=error_code,
                message=f"{env_name} cannot be absolute in multi-tenant mode",
            )
    return PreflightResult(ok=True)
```

**Server Startup:** `src/engine/api/server.py` (lifespan)
```python
# Run preflight checks for multi-tenant path isolation
preflight_result = run_preflight_checks()
if not preflight_result.ok:
    raise RuntimeError(
        f"Preflight check failed: [{preflight_result.code}] {preflight_result.message}"
    )
```

### Comportamento:
- **Multi-tenant ativo** (`require_institution_header_for_runtime=true` em qualquer instituição):
  - `ENGINE_LEDGER_PATH` absoluto → **HARD FAIL** com `PATH_MISCONFIG_ABSOLUTE_LEDGER`
  - `ENGINE_STATE_STORE_DIR` absoluto → **HARD FAIL** com `PATH_MISCONFIG_ABSOLUTE_STATE_STORE`
- **Single-tenant/dev**: Qualquer configuração de path é permitida (backward compatible).

---

## 6. Resumo de Variáveis

| Variable | Default | Usa resolve_namespaced | Risco se Absoluto |
|----------|---------|----------------------|-------------------|
| ENGINE_DATA_ROOT | `var` | Base | BAIXO |
| ENGINE_LEDGER_PATH | `var/audit_ledger.jsonl` | SIM | **ALTO** |
| ENGINE_STATE_STORE_DIR | `var` | SIM | **ALTO** |
| ENGINE_PROD_BUNDLES_ROOT | `/var/lib/engine/bundles` | SIM | MÉDIO |
| ENGINE_DEV_RUNS_REGISTRY_PATH | `var/dev_runs_registry.jsonl` | SIM | BAIXO |
| ENGINE_BUNDLE_PATH | `bundles/finance-pilot` | NÃO (dev-only) | BAIXO |
| ENGINE_INSTITUTIONS_REGISTRY_PATH | `var/institutions_registry.jsonl` | NÃO (global) | N/A |
| ENGINE_INSTITUTIONS_DIR | `var/institutions` | NÃO (global) | N/A |
