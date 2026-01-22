# Fase 5 — Plano Linear (1 IDL por dept + multi-dept como composição)

**Data:** 2026-01-20  
**Base:** Fases 1–4 concluídas (DSL→IRCS→ISE→bundle, prova offline, multi-tenant, multi-dept runtime, governança UI, onboarding, legacy bridge RO+write governado, packaging)

## Objetivo da Fase 5

Alinhar o produto com a definição normativa: **1 IDL (DSL v1.2.2) por departamento**, e **multi-dept como composição no runtime**, sem perder:

- determinismo
- governança (proposal/decide/apply)
- prova offline
- isolamento `(institution_id, dept_id)`

## Decisão canônica (Fase 5)

- **Fonte de verdade:** DSL v1.2.2 (por dept) → IRCS v1 → contracts/bundle.
- **Execução multi-dept:** composição de **múltiplos departamentos** em uma mesma instituição, com **contratos e estado por dept**.
- **Instalar ≠ ativar:** criar/instalar um dept package não implica torná-lo ativo.

## Não objetivos (nesta fase)

- “Um arquivo DSL com múltiplos departamentos” como formato canônico.
- IA autônoma aplicando mudanças sem governança.
- Refatorar tudo para um ERP completo.

## 0.1) Mapa de etapas → pastas

| Etapa | Tema | Pasta |
|------:|------|-------|
| 5.1 | Modelo de ativação multi-dept (canônico) | `docs/specs/fase-5/05-1-multi-dept-activation-model/` |
| 5.2 | Workspace de dept no console (IDL/IR por dept) | `docs/specs/fase-5/05-2-intake-dept-workspace/` |
| 5.3 | Compilação “dept package” (IRCS→bundle por dept) | `docs/specs/fase-5/05-3-ise-compile-dept-package/` |
| 5.4 | Runtime: múltiplos bundles ativos por dept | `docs/specs/fase-5/05-4-runtime-multi-active-bundles/` |
| 5.5 | UX: contexto claro (instituição vs dept) | `docs/specs/fase-5/05-5-console-context-ux/` |
| 5.6 | EGE por dept (pin/drift/rollback) | `docs/specs/fase-5/05-6-ege-per-dept-evolution/` |
| 5.7 | Templates com âncoras (source_idl_sha256 real) | `docs/specs/fase-5/05-7-template-to-dept-idl-anchors/` |

## 0.2) Status atual (Fase 5)

| Etapa | Status |
|------:|:------:|
| 5.1 | ⏳ |
| 5.2 | ⏳ |
| 5.3 | ⏳ |
| 5.4 | ⏳ |
| 5.5 | ⏳ |
| 5.6 | ⏳ |
| 5.7 | ⏳ |

## Cronograma linear (prioridade)

### Etapa 5.1 — Modelo canônico: ativação multi-dept

**Meta:** definir (em spec) o modelo canônico de “quais depts estão ativos” por instituição, e como o runtime resolve isso (sem ambiguidades).

### Etapa 5.2 — Console: workspace por dept (IDL/IR por dept)

**Meta:** permitir que o usuário mantenha **várias definições por dept** (DSL/IR) dentro da instituição, com export, diff e rastreabilidade.

### Etapa 5.3 — ISE: IRCS→bundle por dept (dept package)

**Meta:** compilar um dept (IRCS) em bundle compatível com loader e gerar prova offline, com `source_idl_sha256` real.

### Etapa 5.4 — Runtime: múltiplos bundles ativos

**Meta:** permitir que uma instituição rode com **N bundles ativos**, um por dept, e roteie requests para o bundle correto.

### Etapa 5.5 — Console: contexto e escopo

**Meta:** deixar explícito em todas as telas se você está vendo:

- estado da instituição (global)
- estado do dept (escopado)

Sem “confusão de escopo”.

### Etapa 5.6 — EGE por dept

**Meta:** drift/pin/rollback por dept, com prova offline e eventos no ledger, sem afetar outros depts.

### Etapa 5.7 — Templates com âncoras reais

**Meta:** templates viram **seed institucional**, não “bundle solto”:

- `source_idl_sha256` real (mesmo que derivado de DSL gerado/seed)
- link para a definição (DSL/IR) armazenada na instituição

## Saída esperada da Fase 5

- Uma empresa consegue operar **multi-dept real** mantendo “1 IDL por dept” como verdade versionável, e o runtime rodando múltiplos depts com governança e prova.

