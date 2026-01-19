# Etapa 2.4: Rollback Automatizado e Governado — Fluxo

**Data:** 2026-01-18
**Status:** ✅ IMPLEMENTADO

---

## 1. Fluxo Atual: Deploy → Pin → Rollback

### 1.1 Diagrama de Deploy (Atual)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              PIPELINE DE DEPLOY                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐   ┌────────────────────┐  │
│  │ NL → IDL    │──▶│ compile_     │──▶│  verify_    │──▶│   deploy_script    │  │
│  │ (pipeline)  │   │ bundle()     │   │  bundle.sh  │   │ (deploy_engine_    │  │
│  └─────────────┘   └──────────────┘   └─────────────┘   │  prod.sh)          │  │
│                           │                  │          └──────────┬─────────┘  │
│                           ▼                  ▼                     │            │
│                    ┌────────────┐     ┌────────────┐               │            │
│                    │   TEMP     │     │  STAGING/  │               │            │
│                    │   DIR      │     │  bundle    │               ▼            │
│                    └────────────┘     └────────────┘        ┌────────────┐      │
│                                                             │ releases/  │      │
│                                                             │ YYYYMMDD-  │      │
│                                                             │ HHMMSS/    │      │
│                                                             └──────┬─────┘      │
│                                                                    │            │
│                                                                    ▼            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    SYMLINK UPDATE (deploy_engine_prod.sh)                │   │
│  │  ┌──────────┐         ┌────────────────┐         ┌────────────┐         │   │
│  │  │ PREVIOUS │◀────────│ CURRENT        │────────▶│ NEW RELEASE│         │   │
│  │  │ (backup) │  save   │ symlink update │  point  │ YYYYMMDD-  │         │   │
│  │  └──────────┘         └────────────────┘         │ HHMMSS     │         │   │
│  │                              │                   └────────────┘         │   │
│  └──────────────────────────────┼──────────────────────────────────────────┘   │
│                                 │                                               │
│                                 ▼                                               │
│                    ┌───────────────────────┐                                    │
│                    │   systemctl restart   │                                    │
│                    │   engine.service      │                                    │
│                    └───────────────────────┘                                    │
│                                 │                                               │
│                                 ▼                                               │
│                    ┌───────────────────────┐                                    │
│                    │     smoke_test.sh     │                                    │
│                    └───────────────────────┘                                    │
│                          │           │                                          │
│                       PASS          FAIL                                        │
│                          │           │                                          │
│                          ▼           ▼                                          │
│                   ┌──────────┐  ┌──────────────┐                                │
│                   │ DEPLOYED │  │   ROLLBACK   │                                │
│                   └──────────┘  │ CURRENT ←    │                                │
│                                 │ PREVIOUS     │                                │
│                                 └──────────────┘                                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Arquivos e Responsabilidades

| Módulo | Arquivo | Responsabilidade |
|--------|---------|------------------|
| Pipeline | `src/engine/pipeline/orchestrator.py` | Orquestra NL→IDL→compile→deploy |
| Release | `src/engine/ise/release.py` | `compile_release()` - coordena scripts |
| Deploy Script | `ops/scripts/deploy_engine_prod.sh` | STAGING→releases→CURRENT→restart |
| Verify Script | `ops/checks/verify_bundle.sh` | Verifica bundle antes de deploy |
| Smoke Test | `ops/checks/smoke_test.sh` | Health check pós-deploy |

---

## 2. Fluxo Atual: EGE Pins e Drift

### 2.1 Diagrama de Pin Update

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           FLUXO DE PIN UPDATE                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  DEPLOY SUCCESS                                                                  │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────┐                                  │
│  │  orchestrator.py: auto_propose_and_accept_ │                                  │
│  │                   pin()                    │                                  │
│  └────────────────────────────────────────────┘                                  │
│       │                                                                          │
│       │  (if auto_propose_pin_on_deploy=true)                                    │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────┐                                  │
│  │  create_pin_update_proposal()              │                                  │
│  │  - reads CURRENT hashes (observed)         │                                  │
│  │  - reads config hashes (expected/pinned)   │                                  │
│  │  - creates OPEN proposal                   │                                  │
│  │  - emits EGE_PIN_PROPOSAL_CREATED          │                                  │
│  └────────────────────────────────────────────┘                                  │
│       │                                                                          │
│       │  (if auto_accept_pin_on_deploy=true)                                     │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────┐                                  │
│  │  accept_pin_update_proposal()              │                                  │
│  │  - updates config with observed hashes     │                                  │
│  │  - emits EGE_PIN_PROPOSAL_ACCEPTED         │                                  │
│  │  - emits EGE_PIN_AUTO_ACCEPTED             │                                  │
│  └────────────────────────────────────────────┘                                  │
│                                                                                  │
│  RESULT: pinned hashes = observed hashes (CURRENT bundle)                        │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Diagrama de Drift Detection

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DRIFT DETECTION FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────┐                                                         │
│  │  check_drift()      │                                                         │
│  │  (ege.py)           │                                                         │
│  └──────────┬──────────┘                                                         │
│             │                                                                    │
│             ▼                                                                    │
│  ┌──────────────────────────────────────────────────────┐                        │
│  │  1. Load expected hashes from institution config     │                        │
│  │     - pinned_bundle_manifest_sha256                  │                        │
│  │     - pinned_contract_ledger_sha256                  │                        │
│  └──────────────────────────────────────────────────────┘                        │
│             │                                                                    │
│             ▼                                                                    │
│  ┌──────────────────────────────────────────────────────┐                        │
│  │  2. Resolve CURRENT symlink                          │                        │
│  │     - bundles_root/CURRENT → releases/YYYYMMDD-HH..  │                        │
│  └──────────────────────────────────────────────────────┘                        │
│             │                                                                    │
│             ▼                                                                    │
│  ┌──────────────────────────────────────────────────────┐                        │
│  │  3. Compute observed hashes from CURRENT bundle      │                        │
│  │     - SHA256(bundle.manifest.json)                   │                        │
│  │     - SHA256(contract_ledger.json)                   │                        │
│  └──────────────────────────────────────────────────────┘                        │
│             │                                                                    │
│             ▼                                                                    │
│  ┌──────────────────────────────────────────────────────┐                        │
│  │  4. Compare expected vs observed                     │                        │
│  └──────────────────────────────────────────────────────┘                        │
│             │                                                                    │
│      ┌──────┴───────┬─────────────┐                                              │
│      │              │             │                                              │
│      ▼              ▼             ▼                                              │
│ ┌─────────┐   ┌──────────┐  ┌───────────┐                                        │
│ │ UNPINNED│   │  CLEAR   │  │  ACTIVE   │                                        │
│ │ (no pin)│   │ (match)  │  │ (mismatch)│                                        │
│ └─────────┘   └──────────┘  └───────────┘                                        │
│                                   │                                              │
│                                   ▼                                              │
│                        ┌────────────────────┐                                    │
│                        │ Blocks execution   │                                    │
│                        │ Requires proposal  │                                    │
│                        │ decision           │                                    │
│                        └────────────────────┘                                    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mecanismo CURRENT/PREVIOUS

### 3.1 Estrutura de Diretórios (por instituição)

```
<institution_root>/bundles/
├── STAGING/                    # Temp antes de verify
│   └── finance-pilot/
├── releases/                   # Versões imutáveis
│   ├── 20260115-143052/
│   │   └── finance-pilot/
│   │       ├── bundle.manifest.json
│   │       ├── contract_ledger.json
│   │       └── contracts/
│   └── 20260118-091500/        # Nova release
│       └── finance-pilot/
├── CURRENT -> releases/20260118-091500/finance-pilot
└── PREVIOUS -> releases/20260115-143052/finance-pilot
```

### 3.2 Operações Atômicas vs Não-Atômicas

| Operação | Atomicidade | Implementação |
|----------|-------------|---------------|
| `ln -sfn` (symlink update) | **ATÔMICA** | POSIX rename() - single syscall |
| `shutil.copytree()` | NÃO atômica | Múltiplas operações de I/O |
| `rsync` (staging) | NÃO atômica | Múltiplas operações de I/O |
| `mv` (staging→releases) | **ATÔMICA** | rename() se mesmo filesystem |
| `systemctl restart` | NÃO atômica | Service lifecycle |
| Config file write | **ATÔMICA** | Via tempfile + os.replace() |

### 3.3 Pontos de Falha Atuais

| Ponto | Tipo | O que acontece se falhar |
|-------|------|-------------------------|
| 1. compile_bundle() | Não atômico | Bundle temp inválido → FAILED |
| 2. copy to STAGING | Não atômico | Bundle parcial no STAGING |
| 3. verify_bundle.sh | Externa | STAGING cleanup + FAILED |
| 4. mv STAGING→releases | Atômico* | release parcial se cross-device |
| 5. PREVIOUS = CURRENT | Atômico | Sem rollback possível se falhar |
| 6. CURRENT = new | Atômico | Runtime aponta para antigo |
| 7. systemctl restart | Não atômico | **CRÍTICO**: service pode morrer |
| 8. smoke_test.sh | Externa | Rollback automático |

---

## 4. Fluxo de Rollback Atual (deploy_engine_prod.sh)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ROLLBACK FLOW (CURRENT)                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  smoke_test.sh FAILS                                                             │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────┐                                              │
│  │  Check if PREVIOUS symlink    │                                               │
│  │  exists                        │                                              │
│  └────────────────────────────────┘                                              │
│       │                                                                          │
│   ┌───┴───┐                                                                      │
│   │       │                                                                      │
│  YES      NO                                                                     │
│   │       │                                                                      │
│   │       ▼                                                                      │
│   │   ┌───────────────────────┐                                                  │
│   │   │ ERROR: Manual         │                                                  │
│   │   │ intervention required │                                                  │
│   │   │ exit 1                │                                                  │
│   │   └───────────────────────┘                                                  │
│   │                                                                              │
│   ▼                                                                              │
│  ┌────────────────────────────────┐                                              │
│  │  CURRENT = PREVIOUS            │  ◀─── ATÔMICO (ln -sfn)                      │
│  │  (ln -sfn)                     │                                              │
│  └────────────────────────────────┘                                              │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────┐                                              │
│  │  systemctl restart             │  ◀─── NÃO ATÔMICO                            │
│  │  engine.service                │                                              │
│  └────────────────────────────────┘                                              │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────┐                                              │
│  │  smoke_test.sh                 │                                              │
│  └────────────────────────────────┘                                              │
│       │                                                                          │
│   ┌───┴───┐                                                                      │
│   │       │                                                                      │
│  PASS     FAIL                                                                   │
│   │       │                                                                      │
│   ▼       ▼                                                                      │
│  ┌───────┐ ┌─────────────────────┐                                               │
│  │ROLLED │ │ CRITICAL: Rollback  │                                               │
│  │ BACK  │ │ also failed         │                                               │
│  │exit 1 │ │ exit 1              │                                               │
│  └───────┘ └─────────────────────┘                                               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. SAFE_MODE e Bloqueio de Deploy

### 5.1 Fluxo de Bloqueio

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SAFE_MODE BLOCK                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  run_pipeline() / build_pipeline()                                               │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────┐                                      │
│  │  if runtime_state.is_safe_mode():      │                                      │
│  │      return FAILED                     │                                      │
│  │      error_code: PIPELINE_ENGINE_      │                                      │
│  │                  SAFE_MODE             │                                      │
│  └────────────────────────────────────────┘                                      │
│                                                                                  │
│  runtime_state é singleton global em memory                                      │
│  - NÃO persiste entre restarts                                                   │
│  - Setado por código, não por arquivo                                            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Estados do Runtime

| Estado | Descrição | Deploy Permitido |
|--------|-----------|------------------|
| `ACTIVE` | Normal operation | SIM |
| `SAFE_MODE` | Triggered by drift or error | NÃO |

---

## 6. Eventos de Auditoria Existentes

### 6.1 Eventos no Ledger

| Evento | Emitido Por | Quando |
|--------|-------------|--------|
| `EGE_DRIFT_CHECKED` | `ege.py:emit_ege_drift_checked()` | Após check_drift() |
| `EGE_PIN_PROPOSAL_CREATED` | `ege_pins.py` | Proposta de pin criada |
| `EGE_PIN_PROPOSAL_ACCEPTED` | `ege_pins.py` | Proposta aceita |
| `EGE_PIN_PROPOSAL_BLOCKED` | `ege_pins.py` | Proposta bloqueada |
| `EGE_PIN_AUTO_ACCEPTED` | `ege_pins.py` | Auto-accept após deploy |
| `EGE_PROPOSAL_CREATED` | `ege_proposals.py` | Drift resolution proposal |
| `EGE_PROPOSAL_DECIDED` | `ege_proposals.py` | Proposta decidida |

### 6.2 Trace Files

| Arquivo | Local | Quando |
|---------|-------|--------|
| `trace.json` | `dev-runs/<run_id>/` | build_pipeline() |
| `trace.json` | `deploy-traces/<release_id>/` | run_pipeline() DEPLOYED |

---

## 7. Fluxo Implementado: Governed Rollback (Etapa 2.4)

### 7.1 Diagrama de Governed Rollback

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         GOVERNED ROLLBACK FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  DEPLOY FAILURE (via release.py)                                                 │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────┐                                          │
│  │  _handle_deploy_failure()          │                                          │
│  │  (release.py)                      │                                          │
│  └────────────────────────────────────┘                                          │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────┐                                          │
│  │  execute_governed_rollback()       │                                          │
│  │  (ege_rollback.py)                 │                                          │
│  └────────────────────────────────────┘                                          │
│       │                                                                          │
│       │  1. Emit EGE_ROLLBACK_STARTED                                            │
│       ▼                                                                          │
│  ┌────────────────────────────────────┐                                          │
│  │  Check: freeze/emergency blocked?  │                                          │
│  └────────────────────────────────────┘                                          │
│       │                                                                          │
│   ┌───┴───┐                                                                      │
│   │       │                                                                      │
│  NO      YES                                                                     │
│   │       │                                                                      │
│   │       ▼                                                                      │
│   │   ┌───────────────────────┐                                                  │
│   │   │ EGE_ROLLBACK_FAILED   │                                                  │
│   │   │ error: BLOCKED_FROZEN │                                                  │
│   │   └───────────────────────┘                                                  │
│   │                                                                              │
│   ▼                                                                              │
│  ┌────────────────────────────────────┐                                          │
│  │  get_pinned_release_path()         │                                          │
│  │  - Uses pinned_release_id from     │                                          │
│  │    config (v1.4)                   │                                          │
│  │  - Falls back to hash matching     │                                          │
│  └────────────────────────────────────┘                                          │
│       │                                                                          │
│   ┌───┴───┐                                                                      │
│   │       │                                                                      │
│  FOUND   NOT FOUND                                                               │
│   │       │                                                                      │
│   │       ▼                                                                      │
│   │   ┌───────────────────────────┐                                              │
│   │   │ ACTIVATE SAFE_MODE        │                                              │
│   │   │ EGE_ROLLBACK_FAILED       │                                              │
│   │   │ error: NO_PINNED_RELEASE  │                                              │
│   │   └───────────────────────────┘                                              │
│   │                                                                              │
│   ▼                                                                              │
│  ┌────────────────────────────────────┐                                          │
│  │  ATOMIC SYMLINK UPDATE             │                                          │
│  │  CURRENT → pinned_release_path     │                                          │
│  │  (via tempfile + os.replace)       │                                          │
│  └────────────────────────────────────┘                                          │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────┐                                          │
│  │  Emit EGE_ROLLBACK_COMPLETED       │                                          │
│  │  - rolled_back_to: release_id      │                                          │
│  │  - failed_release_id               │                                          │
│  │  - timestamp                        │                                          │
│  └────────────────────────────────────┘                                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Arquivos Implementados

| Módulo | Arquivo | Responsabilidade |
|--------|---------|------------------|
| Rollback | `src/engine/core/ege_rollback.py` | `execute_governed_rollback()` |
| Errors | `src/engine/core/errors.py` | `EGE_ROLLBACK_*` error codes |
| Config | `src/engine/core/institution_config.py` | `pinned_release_id` field (v1.4) |
| Release | `src/engine/ise/release.py` | `_handle_deploy_failure()` |
| Pins | `src/engine/core/ege_pins.py` | Stores `pinned_release_id` on accept |

### 7.3 Eventos de Auditoria (Novos)

| Evento | Emitido Por | Quando |
|--------|-------------|--------|
| `EGE_ROLLBACK_STARTED` | `ege_rollback.py` | Início do rollback |
| `EGE_ROLLBACK_COMPLETED` | `ege_rollback.py` | Rollback bem-sucedido |
| `EGE_ROLLBACK_FAILED` | `ege_rollback.py` | Rollback falhou |

### 7.4 Testes

| Teste | Arquivo | Cenário |
|-------|---------|---------|
| 18 testes | `tests/test_ege_rollback.py` | Rollback scenarios |

---

## 8. Resumo da Implementação

### 8.1 O que foi implementado

1. **`pinned_release_id`** - Campo no config v1.4 que guarda o ID da release pinada
2. **`execute_governed_rollback()`** - Função que executa rollback para pinned release
3. **Eventos de auditoria** - `EGE_ROLLBACK_STARTED/COMPLETED/FAILED`
4. **SAFE_MODE automático** - Ativado se não houver pinned release
5. **Bloqueio por freeze/emergency** - Respeitado durante rollback
6. **Testes completos** - 18 testes cobrindo todos os cenários

### 8.2 Definition of Done - ATINGIDO

- [x] Deploy falho nunca deixa runtime apontando para release inválida
- [x] Rollback é automático e deixa trilha de auditoria
- [x] Testes automatizados cobrem cenário de falha + retorno ao estado consistente
