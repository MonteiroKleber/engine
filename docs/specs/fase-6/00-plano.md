# Fase 6 — Plano Linear (IDL-driven Runtime: OperationRegistry → Router/Dispatcher → OpenAPI)

**Data:** 2026-01-21  
**Base:** Fases 1–5 (governança runtime, prova offline, multi-tenant, multi-dept, onboarding, console operacional, DSL→IRCS→ISE→bundle)

## Objetivo da Fase 6

Transformar o Engine de “handlers fixos por domínio” em **runtime institucional dirigido por contrato**, onde:

- **IDL/DSL → IRCS → bundle** define a superfície institucional (`operations`)
- o runtime materializa **OperationRegistry** por `(institution_id, dept_id)`
- o runtime resolve **(method, path) → OperationSpec**
- um **Dispatcher** executa a operação de forma determinística usando os motores existentes (RBAC/SoD/Policies/Mandates/Autonomy/Approvals/Workflows/Invariants/Ledger)
- o **OpenAPI exposto** reflete o contrato ativo (por instituição/dept)

## Decisão canônica (Fase 6)

- **O contrato governa a API**, não “arquivos `finance.py`, `hr.py`, etc.”.
- **Compatibilidade obrigatória:** não quebrar o runtime existente imediatamente; introduzir um modo incremental:
  - `legacy`: rotas fixas atuais continuam (baseline)
  - `idl`: rotas expostas e executadas via OperationRegistry/Dispatcher

## Não objetivos (nesta fase)

- Gerar “Target” (web/mobile/chat) automaticamente.
- Refatorar todos os domínios existentes para sumir com `finance.py` imediatamente.
- Introduzir cluster/HA/multi-instância.

## 0.1) Mapa de etapas → pastas

| Etapa | Tema | Pasta |
|------:|------|-------|
| 6.1 | ABI de operações + OperationRegistry (bundle/loader) | `docs/specs/fase-6/06-1-operations-registry/` |
| 6.2 | Dispatcher v1: create/read (state store genérico) | `docs/specs/fase-6/06-2-dispatcher-crud/` |
| 6.3 | Dispatcher v2: workflow/transition + approvals | `docs/specs/fase-6/06-3-dispatcher-workflows-approvals/` |
| 6.4 | Dynamic Router: publicar rotas reais no FastAPI | `docs/specs/fase-6/06-4-dynamic-router/` |
| 6.5 | OpenAPI a partir do registry (por instituição/dept) | `docs/specs/fase-6/06-5-openapi-from-registry/` |
| 6.6 | Versões ativas + hot-swap governado (EGE integrado) | `docs/specs/fase-6/06-6-registry-versioning-ege/` |
| 6.7 | Plano de migração: handlers fixos → idl (sem quebra) | `docs/specs/fase-6/06-7-migration-plan/` |

## 0.2) Status atual (Fase 6)

| Etapa | Status |
|------:|:------:|
| 6.1 | ✅ |
| 6.2 | ✅ |
| 6.3 | ✅ |
| 6.4 | ✅ |
| 6.5 | ✅ |
| 6.6 | ✅ |
| 6.7 | ⏳ |

## Cronograma linear (prioridade)

### Etapa 6.1 — ABI + OperationRegistry

**Meta:** existir um contrato canônico `operations.json` no bundle e o runtime conseguir carregar e resolver `OperationSpec` por dept.

### Etapa 6.2 — Dispatcher v1 (CRUD)

**Meta:** executar operações `bind.kind=create/read` via pipeline determinístico usando motores existentes (gates + ledger + state store).

### Etapa 6.3 — Dispatcher v2 (workflow + approvals)

**Meta:** executar `bind.kind=transition/approval` com workflows/approvals já existentes, sem handlers fixos.

### Etapa 6.4 — Dynamic Router

**Meta:** publicar rotas reais no FastAPI (melhor UX/mercado) baseadas no registry, com controle de modo (`legacy` vs `idl`).

### Etapa 6.5 — OpenAPI from registry

**Meta:** o OpenAPI exposto pelo engine refletir o contrato ativo (por instituição/dept), não um YAML estático no bundle.

### Etapa 6.6 — Hot-swap governado

**Meta:** ativar uma nova versão de registry/bundle sem restart “duro”, com rollback/pin governado.

### Etapa 6.7 — Migração controlada

**Meta:** plano e mecanismos para migrar domínios existentes para `idl` sem quebra e sem “big bang”.

## Saída esperada da Fase 6

- Uma instituição consegue criar (DSL/IR) → compilar → instalar e **expor** suas próprias rotas e operações sem escrever handlers em Python.
- Targets de produção podem ser desenvolvidos consumindo uma API institucional estável derivada do contrato, com versionamento e rollback governado.
