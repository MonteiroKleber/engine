# Pipeline States — Especificação

**Data:** 2026-01-18
**Versão:** 1.0
**Etapa:** 03 — Pipeline NL → Canonical IDL → Bundle

---

## 1. Visão Geral

Este documento define os estados, transições e bloqueios do pipeline NL → IDL → Bundle do Libervia Engine.

---

## 2. Estados do Pipeline

| Estado | Descrição | Bloqueante |
|--------|-----------|------------|
| `NEEDS_ANSWERS` | Gaps detectados, aguardando respostas humanas | **Sim** — bloqueia build/deploy |
| `BUILT` | Bundle compilado em sandbox (dev-runs) | Não |
| `DEPLOYED` | Bundle em produção (via release scripts) | Não |
| `ROLLED_BACK` | Deploy falhou, revertido automaticamente | — |
| `FAILED` | Erro em qualquer estágio | — |

**Evidência:** [orchestrator.py:39-43](../../../../src/engine/pipeline/orchestrator.py)

---

## 3. Fluxo de Estados

### 3.1 Pipeline de Build (`build_pipeline`)

```
┌─────────┐
│  START  │
└────┬────┘
     │
     ▼
┌─────────────────┐
│ 1. compile_sir  │  NL → SIR
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. compile_draft│  SIR → Draft IDL
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. detect_gaps  │
└────────┬────────┘
         │
         ├──── required_gaps? ────┐
         │         YES            │
         │                        ▼
         │              ┌─────────────────┐
         │              │ NEEDS_ANSWERS   │  ◄── BLOQUEIO DURO
         │              └─────────────────┘
         │         NO
         ▼
┌─────────────────┐
│ 4. apply_answers│  (se answers fornecidas)
└────────┬────────┘
         │
         ├──── still_gaps? ───────┐
         │         YES            │
         │                        ▼
         │              ┌─────────────────┐
         │              │ NEEDS_ANSWERS   │  ◄── BLOQUEIO DURO
         │              └─────────────────┘
         │         NO
         ▼
┌─────────────────┐
│ 5. finalize     │  Draft → IDL Final
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. compile_bundle│  IDL → Bundle (sandbox)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 7. persist trace│  trace.json + idl_final.idl
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     BUILT       │
└─────────────────┘
```

**Evidência:** [orchestrator.py:481-771](../../../../src/engine/pipeline/orchestrator.py)

### 3.2 Pipeline de Deploy (`run_pipeline`)

```
┌─────────┐
│  START  │
└────┬────┘
     │
     ▼
┌─────────────────┐
│ 0. check SAFE_MODE │ ──── is_safe_mode? ──── YES ──► FAILED
└────────┬────────┘
         │ NO
         ▼
     (steps 1-6 igual build_pipeline)
         │
         ▼
┌─────────────────┐
│ 7. pre-compile  │  Verificação explícita
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 8. verify_bundle│  verify_bundle.sh
└────────┬────────┘
         │
         ├──── failed? ──────────┐
         │         YES           │
         │                       ▼
         │             ┌─────────────────┐
         │             │     FAILED      │
         │             └─────────────────┘
         │ NO
         ▼
┌─────────────────┐
│ 9. compile_release │ (deploy_engine_prod.sh)
└────────┬────────┘
         │
         ├──── failed? ──────────┐
         │         YES           │
         │                       ▼
         │             ┌─────────────────┐
         │             │  ROLLED_BACK    │
         │             └─────────────────┘
         │ NO
         ▼
┌─────────────────┐
│   DEPLOYED      │
└─────────────────┘
```

**Evidência:** [orchestrator.py:145-478](../../../../src/engine/pipeline/orchestrator.py)

---

## 4. Bloqueio NEEDS_ANSWERS

### 4.1 Comportamento

O estado `NEEDS_ANSWERS` é um **bloqueio duro**:
- Não chama `compile_bundle` nem `compile_release`
- Retorna imediatamente com gaps para resolução humana
- Requer que o chamador forneça `answers` para prosseguir

**Evidência:** [orchestrator.py:239-256](../../../../src/engine/pipeline/orchestrator.py) — retorno antes de compile

### 4.2 Estrutura do Retorno NEEDS_ANSWERS

```json
{
  "status": "NEEDS_ANSWERS",
  "bundle_name": "...",
  "hash_sir": "SHA256...",
  "hash_draft": "SHA256...",
  "gaps": [
    {
      "question_id": "...",
      "question": "...",
      "severity": "required|optional",
      "field_path": "..."
    }
  ],
  "sir": {...},
  "draft_idl": {...},
  "policy_gaps": [...],
  "answers_template": {...}
}
```

### 4.3 Fluxo com Answers

```
Cliente                                 Pipeline
   │                                       │
   │ POST /pipeline/build {text}           │
   ├──────────────────────────────────────►│
   │                                       │
   │ 200 {status: "NEEDS_ANSWERS", gaps}   │
   │◄──────────────────────────────────────┤
   │                                       │
   │ (humano preenche answers)             │
   │                                       │
   │ POST /pipeline/build {text, answers}  │
   ├──────────────────────────────────────►│
   │                                       │
   │ 200 {status: "BUILT", run_id, ...}    │
   │◄──────────────────────────────────────┤
```

---

## 5. Persistência

### 5.1 Artefatos por Run

Cada build bem-sucedido persiste em `dev-runs/<run_id>/`:

| Arquivo | Descrição |
|---------|-----------|
| `trace.json` | Hashes de rastreabilidade |
| `idl_final.idl` | IDL canonizada final |
| `<bundle_name>/` | Bundle compilado |
| `exports/<bundle_name>.zip` | ZIP determinístico (após export) |

**Evidência:** [orchestrator.py:693-748](../../../../src/engine/pipeline/orchestrator.py)

### 5.2 Registry (dev_runs_registry.jsonl)

Eventos append-only:

| Evento | Quando |
|--------|--------|
| `DEV_RUN_CREATED` | Após build bem-sucedido |
| `DEV_RUN_EXPORTED` | Após export ZIP |
| `DEV_RUN_DELETED` | Após cleanup |

**Evidência:** [registry.py:14-16](../../../../src/engine/pipeline/registry.py)

---

## 6. GAPs (Histórico)

### 6.1 ~~GAP CRÍTICO: Formato de Manifest Incompatível~~ — RESOLVIDO ✅

| Status | **RESOLVIDO** (2026-01-18) |
|--------|----------------------------|
| Resolução | [manifest.py](../../../../src/engine/ise/manifest.py) atualizado para emitir formato loader-compatible |
| Testes | `tests/test_ise_loader_compatibility.py` — 13 testes passando |

**Formato ISE (atualizado):**
```json
{
  "name": "bundle-name",
  "version": "1.0.0",
  "description": "...",
  "contracts": [
    {"file": "rbac.json", "sha256": "SHA256:...", "required": true},
    {"file": "policies.json", "sha256": "SHA256:...", "required": true},
    {"file": "mandates.json", "sha256": "SHA256:...", "required": true},
    {"file": "autonomy.json", "sha256": "SHA256:...", "required": true}
  ],
  "_metadata": {...}
}
```

### 6.2 ~~GAP CRÍTICO: Contratos Institucionais Ausentes~~ — RESOLVIDO ✅

| Status | **RESOLVIDO** (2026-01-18) |
|--------|----------------------------|
| Resolução | ISE agora emite todos os três contratos institucionais obrigatórios |
| Novos Emitters | [mandates_emit.py](../../../../src/engine/ise/emit/mandates_emit.py), [autonomy_emit.py](../../../../src/engine/ise/emit/autonomy_emit.py) |
| Testes | `tests/test_missing_institutional_contracts_safe_mode.py` — 7 testes passando |

O ISE agora emite:
- `rbac.json` ✓
- `workflows.json` ✓
- `approvals.json` ✓
- `sod.json` ✓
- `invariants.json` ✓
- `openapi.yaml` ✓
- `policies.json` ✓ **SEMPRE EMITE**
- `mandates.json` ✓ **SEMPRE EMITE**
- `autonomy.json` ✓ **SEMPRE EMITE**

**Comportamento:**
- `autonomy.json`: default `current_level: 0` (L0 = supervisão humana total)
- `mandates.json`: default `mandates: []` (sem mandatos ativos)
- `policies.json`: default `policies: []` (sem policies = deny-all via rbac)

### 6.3 GAP: trace.json não persiste para deploy

| Severidade | Média |
|------------|-------|
| Impacto | `run_pipeline` (deploy) não persiste `trace.json` |
| Evidência | [orchestrator.py:145-478](../../../../src/engine/pipeline/orchestrator.py) — nenhuma escrita de trace |

Apenas `build_pipeline` persiste `trace.json`. O deploy via `run_pipeline` compila para temp dir e não mantém artefatos de trace.

---

## 7. Verificação de Bundle (verify_bundle.sh)

### 7.1 Localização

```
/home/bazari/engine/ops/checks/verify_bundle.sh
```

**Evidência:** [release.py:26](../../../../src/engine/ise/release.py)

### 7.2 Uso no Pipeline

Chamado em dois momentos:
1. **Pré-verificação explícita** em `run_pipeline` antes de `compile_release`
2. **Dentro de `compile_release`** antes de `deploy_engine_prod.sh`

---

## 8. Determinismo

### 8.1 Garantias

| Artefato | Determinístico |
|----------|----------------|
| Hashes de contratos | **Sim** (SHA256 de conteúdo) |
| `bundle_hash` | **Sim** (hash de hashes) |
| `trace.json` hashes | **Sim** |
| ZIP export | **Sim** (timestamp fixo 1980-01-01) |
| `created_at` no manifest | **Não** (varia por compilação) |

**Evidência:** [exporter.py:16](../../../../src/engine/pipeline/exporter.py)

### 8.2 Variáveis de Ambiente para CI/CD

Para builds 100% reproduzíveis:
- `SOURCE_DATE_EPOCH` ou `ENGINE_BUILD_TIMESTAMP` (proposto, não implementado)

---

## 9. Resumo de GAPs

| # | GAP | Severidade | Status |
|---|-----|------------|--------|
| 1 | ~~Formato manifest ISE ≠ loader~~ | ~~CRÍTICO~~ | ✅ RESOLVIDO |
| 2 | ~~ISE não emite mandates.json~~ | ~~CRÍTICO~~ | ✅ RESOLVIDO |
| 3 | ~~ISE não emite autonomy.json~~ | ~~CRÍTICO~~ | ✅ RESOLVIDO |
| 4 | trace.json não persiste em deploy | Média | Aberto |

---

## 10. Referências

- [IDL v1.x Specification](../02-idl-artifacts/idl-v1.md)
- [Canonical Artifacts](../02-idl-artifacts/canonical-artifacts.md)
- [Gap Report v8.1.1](../01-baseline/gap-report.md)
- [orchestrator.py](../../../../src/engine/pipeline/orchestrator.py)
- [compiler.py](../../../../src/engine/ise/compiler.py)
- [manifest.py](../../../../src/engine/ise/manifest.py)
- [load_bundle.py](../../../../src/engine/loader/load_bundle.py)
- [mandates_emit.py](../../../../src/engine/ise/emit/mandates_emit.py)
- [autonomy_emit.py](../../../../src/engine/ise/emit/autonomy_emit.py)

---

**Status:** ESPECIFICAÇÃO ATIVA (GAPs críticos resolvidos)
**Data:** 2026-01-18
**Última atualização:** 2026-01-18 — Fechamento dos GAPs críticos ISE→Loader
