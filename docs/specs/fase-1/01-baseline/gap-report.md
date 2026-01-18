# Gap Report — Libervia Engine MVP

**Data:** 2026-01-17
**Versão:** 8.1.1
**Comparação:** Código atual vs Definition of Done (MVP Pilot)

---

## Riscos Críticos

| # | Risco | Severidade | Impacto | Recomendação |
|---|-------|------------|---------|--------------|
| 1 | **ALLOW-ALL por ausência de contratos institucionais** | **CRÍTICO** | Policies, Mandates e Autonomy viram **allow-all** quando arquivos não existem no bundle. Bundle `finance-pilot` atual **não possui** `policies.json`, `mandates.json` ou `autonomy.json`. Todo request passa sem qualquer gate de governança. | **Implementar default-deny** ou exigir presença obrigatória desses contratos no bundle. Ver evidências abaixo. |
| 2 | **3 testes pulados (skipped)** | Médio | Cobertura incompleta em `test_nl_finalize.py`. | Investigar e remover skip markers ou documentar exceção. |
| 3 | **LLM extractor em modo mock** | Baixo | Default `ENGINE_NL_EXTRACTOR=deterministic`. Mock adequado para pilot. | Documentar que produção com LLM real requer configuração explícita. |
| 4 | **`ENGINE_ISE_ADMIN_TOKEN` sem validação no preflight** | Médio | Variável obrigatória para deploy não é verificada antes do startup. | Adicionar check no preflight.sh. |

---

## Decision Points

| # | Decisão Pendente | Contexto | Recomendação |
|---|------------------|----------|--------------|
| 1 | **Default para contratos de governança ausentes** | Hoje: **allow-all** quando `policies.json`, `mandates.json`, `autonomy.json` não existem. Isso viola o princípio de "nenhuma execução fora de mandato". | **Mudar para default-deny** ou exigir presença obrigatória no manifest. BLOQUEANTE para produção institucional. |
| 2 | **RBAC: default-deny implementado** | 403 sem role. Validado por `test_rbac.py`. | OK, manter. |
| 3 | **Cleanup de dev-runs** | Default: desabilitado. TTL=24h, MAX=200. | Adequado para pilot, revisar para produção. |
| 4 | **EGE drift enforcement** | Default: `ege_enforce_drift=true` bloqueia writes com drift ativo. | OK para governança de bundles. |

---

## Evidência Detalhada: Risco Crítico #1 (ALLOW-ALL)

### 1.1 Bundle `finance-pilot` — Arquivos Ausentes

**Localização:** `bundles/finance-pilot/`

```
$ ls -la bundles/finance-pilot/
approvals.json        ← PRESENTE
bundle.manifest.json  ← PRESENTE
contract_ledger.json  ← PRESENTE
invariants.json       ← PRESENTE
openapi.yaml          ← PRESENTE
rbac.json             ← PRESENTE
sod.json              ← PRESENTE
workflows.json        ← PRESENTE

policies.json         ← AUSENTE
mandates.json         ← AUSENTE
autonomy.json         ← AUSENTE
```

**Impacto:** Nenhum gate de policy, mandate ou autonomy é aplicado em runtime.

### 1.2 `load_bundle.py` — Tratamento allow-all por ausência

**Arquivo:** `src/engine/loader/load_bundle.py`

| Linhas | Contrato | Comportamento quando ausente |
|--------|----------|------------------------------|
| 471-472 | `policies.json` | `set_policies(None, None)  # No policies = allow all` |
| 499-500 | `policies.json` (multi-dept) | `set_policies(dept_id, None)  # No policies.json for this dept - allow all` |
| 524-525 | `mandates.json` | `set_mandates(None, None)  # No mandates = allow all (mandates are optional)` |
| 556-558 | `mandates.json` (multi-dept) | `set_mandates(dept_id, None)  # No mandates.json for this dept - allow all` |
| 583-584 | `autonomy.json` | `set_autonomy_for_dept(None, None)  # No autonomy = allow all (autonomy is optional)` |
| 615-617 | `autonomy.json` (multi-dept) | `set_autonomy_for_dept(dept_id, None)  # No autonomy.json for this dept - allow all` |

### 1.3 `policy.py` — Avaliação allow quando não há policies

**Arquivo:** `src/engine/core/policy.py`

**Linhas 393-397:**
```python
def evaluate_policies(...) -> PolicyEvalResult:
    policy_def = get_policies(dept_id)

    if policy_def is None:
        # No policies defined - allow by default
        return PolicyEvalResult(allow=True)
```

### 1.4 `mandates.py` — Avaliação allow quando não há mandates

**Arquivo:** `src/engine/core/mandates.py`

**Linhas 596-600:**
```python
def evaluate_mandates(...) -> MandateEvalResult:
    mandate_def = get_mandates(dept_id)

    if mandate_def is None:
        # No mandates defined - allow by default (mandates are optional grants)
        return MandateEvalResult(allow=True)
```

**Linhas 687-688:**
```python
    # No matching mandate found - allow by default (mandates are optional grants)
    return MandateEvalResult(allow=True)
```

### 1.5 `autonomy.py` — Avaliação allow-all quando não há autonomy

**Arquivo:** `src/engine/core/autonomy.py`

**Linhas 42-44 (defaults):**
```python
# Default values when autonomy.json is missing (allow-all behavior)
DEFAULT_CURRENT_LEVEL = 4      # L4 = Full autonomy
DEFAULT_REQUIRED_LEVEL = 0     # L0 = No requirement
```

**Linhas 313-323:**
```python
def evaluate_autonomy(...) -> AutonomyEvalResult:
    autonomy_def = get_autonomy_for_dept(dept_id)

    if autonomy_def is None:
        # No autonomy.json - use allow-all defaults
        return AutonomyEvalResult(
            decision="allow",
            current_level=DEFAULT_CURRENT_LEVEL,  # 4
            required_level=DEFAULT_REQUIRED_LEVEL,  # 0
            rule_id=None,
            reason="No autonomy rules defined (allow-all)",
        )
```

---

## Checklist Definition of Done

### 1. Funcionalidade Core

| Critério | Status | Evidência |
|----------|--------|-----------|
| POST /finance/expenses cria despesa e retorna 202 | ✅ | `tests/test_commit_invariants.py::test_create_expense_returns_202_with_expense_id` |
| POST /approvals/{id}/decide `approve` valida invariantes e comita | ✅ | `tests/test_commit_invariants.py::test_approve_valid_expense_commits` |
| POST /approvals/{id}/decide `reject` rejeita e atualiza status | ✅ | `tests/test_commit_invariants.py::test_reject_expense_returns_rejected` |
| GET /health retorna 200 em modo ACTIVE | ✅ | `tests/test_loader_safe_mode.py`, `src/engine/api/server.py:health()` |
| GET /health retorna 503 em SAFE_MODE com `reason_code` | ✅ | `tests/test_loader_safe_mode.py::test_*_enters_safe_mode` |

### 2. Segurança e Controle de Acesso

| Critério | Status | Evidência |
|----------|--------|-----------|
| RBAC bloqueia acesso sem permissão (403) | ✅ | `tests/test_rbac.py` (5+ testes) |
| RBAC bloqueia acesso sem actor (401) | ✅ | `tests/test_rbac.py`, `src/engine/core/rbac.py` |
| SoD bloqueia self-approval (409) | ✅ | `tests/test_sod.py::test_self_approval_returns_409_sod_violation` |
| Invariantes bloqueiam valores inválidos (422) | ✅ | `tests/test_commit_invariants.py::test_approve_zero_amount_returns_422` |
| Rate limiting ativo (429) | ✅ | `tests/test_security_hardening.py::test_rate_limit_exceeded_returns_429` |
| Body size limit ativo (413) | ✅ | `tests/test_security_hardening.py::test_large_body_returns_413` |
| Security headers presentes | ✅ | `tests/test_security_hardening.py::test_security_headers_present_on_health` |

### 3. Auditoria e Integridade

| Critério | Status | Evidência |
|----------|--------|-----------|
| Eventos gravados no ledger | ✅ | `tests/test_ledger.py` (25+ testes) |
| Hash SHA-256 por evento | ✅ | `tests/test_ledger.py::test_event_hash_is_sha256` |
| Chain verificada no boot | ✅ | `tests/test_ledger_verify_boot.py` (8+ testes) |
| Ledger corrompido → SAFE_MODE | ✅ | `tests/test_ledger_verify_boot.py::test_*_tampered_*` |
| Request ID propagado | ✅ | `tests/test_request_id.py` (5+ testes) |

### 4. Operações

| Critério | Status | Evidência |
|----------|--------|-----------|
| Bundle validado no startup | ✅ | `tests/test_loader_safe_mode.py`, `load_bundle.py` |
| Bundle inválido → SAFE_MODE | ✅ | `tests/test_loader_safe_mode.py::test_*_missing_*` |
| State store persiste | ✅ | `tests/test_state_store_dept_isolation.py` |
| Logs estruturados JSON | ✅ | `src/engine/core/logging.py` |
| Preflight script funciona | ✅ | `ops/checks/preflight.sh` (236 linhas) |

### 5. Testes

| Critério | Status | Evidência |
|----------|--------|-----------|
| Testes unitários passam | ✅ | `pytest tests/ -v` → 1154 passed |
| Testes de integração passam | ✅ | 97 arquivos com TestClient |
| Cobertura de cenários de erro | ✅ | 403, 401, 409, 422, 429, 413, 500, SAFE_MODE |
| Nenhum teste skipped | ⚠️ | **3 skipped** em `test_nl_finalize.py` |

### 6. Documentação

| Critério | Status | Evidência |
|----------|--------|-----------|
| RUNBOOK | ✅ | `docs/pilot/RUNBOOK.md` (200 linhas) |
| EXAMPLES | ✅ | `docs/pilot/EXAMPLES.md` (308 linhas) |
| RELEASE_CHECKLIST | ✅ | `docs/pilot/RELEASE_CHECKLIST.md` (180 linhas) |
| README atualizado | ✅ | `README.md` (1299 linhas) |

### 7. Governança Institucional (CRITÉRIO ADICIONAL)

| Critério | Status | Evidência |
|----------|--------|-----------|
| Gates de policy obrigatórios | ❌ | `policies.json` ausente → allow-all. Ver Risco #1. |
| Mandatos para delegação controlada | ❌ | `mandates.json` ausente → allow-all. Ver Risco #1. |
| Níveis de autonomia configurados | ❌ | `autonomy.json` ausente → L4 (full autonomy). Ver Risco #1. |

---

## Resumo de Evidências

| Categoria | Total | ✅ OK | ⚠️ Parcial | ❌ Faltando |
|-----------|-------|-------|------------|-------------|
| 1. Funcionalidade Core | 5 | 5 | 0 | 0 |
| 2. Segurança e Controle | 7 | 7 | 0 | 0 |
| 3. Auditoria e Integridade | 5 | 5 | 0 | 0 |
| 4. Operações | 5 | 5 | 0 | 0 |
| 5. Testes | 4 | 3 | 1 | 0 |
| 6. Documentação | 4 | 4 | 0 | 0 |
| **7. Governança Institucional** | **3** | **0** | **0** | **3** |
| **TOTAL** | **33** | **29** | **1** | **3** |

---

## Arquivos-Chave Verificados

| Arquivo | Propósito | Observação |
|---------|-----------|------------|
| `src/engine/loader/load_bundle.py:471-617` | Carregamento de contratos | **Allow-all por ausência** |
| `src/engine/core/policy.py:393-397` | Avaliação de policies | **Allow se None** |
| `src/engine/core/mandates.py:596-600,687-688` | Avaliação de mandatos | **Allow se None** |
| `src/engine/core/autonomy.py:42-44,313-323` | Avaliação de autonomia | **L4 (full) se None** |
| `bundles/finance-pilot/` | Bundle MVP | **Sem policies/mandates/autonomy** |

---

## Conclusão

O Libervia Engine **atende 29 de 33 critérios** do Definition of Done expandido.

### Status: NÃO APROVADO PARA PRODUÇÃO INSTITUCIONAL

O risco crítico #1 (allow-all por ausência de contratos de governança) **viola o princípio de "nenhuma execução fora de mandato"**. O sistema atualmente opera em modo **permissivo por default** quando contratos institucionais estão ausentes.

### Bloqueantes para Produção

1. **CRÍTICO:** Definir e implementar política de default para contratos ausentes:
   - **Opção A (recomendada):** Default-deny — exigir presença obrigatória de `policies.json`, `mandates.json`, `autonomy.json` no bundle, com SAFE_MODE se ausentes.
   - **Opção B:** Allow-all explícito — documentar formalmente que produção pilot aceita allow-all e criar contratos vazios explícitos.

2. Investigar e resolver 3 testes skipped em `test_nl_finalize.py`.

### Aceito para Pilot Controlado (com ressalvas)

Se a liderança aceitar explicitamente o comportamento allow-all para o pilot inicial, documentar:
- Que o pilot opera sem gates de policy/mandate/autonomy.
- Que RBAC + SoD + Invariantes são os únicos controles ativos.
- Que produção institucional requer implementação de default-deny.

---

**Status:** NÃO APROVADO
**Motivo:** Risco Crítico #1 não resolvido (allow-all por ausência de contratos)
**Data:** 2026-01-17
**Revisor:** [Pendente decisão da liderança]
