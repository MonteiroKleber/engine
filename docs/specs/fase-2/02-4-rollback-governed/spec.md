# Fase 2 — Etapa 2.4: Rollback Automatizado e Governado (EGE + Release)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.4)

## Fonte de Verdade (normativa)

- Princípio: “nunca entrar em estado meio aplicado” (SAFE_MODE/rollback) — ver Fase 1 (DoD e proof offline)
- Runtime/EGE existentes (referência no código):
  - `src/engine/core/ege.py`
  - `src/engine/core/ege_pins.py`
  - `src/engine/core/ege_proposals.py`
  - `src/engine/pipeline/orchestrator.py`

## Objetivo

Transformar rollback de “operacional/manual” para um procedimento **automático e governado**, garantindo que:

- deploy falhou → rollback automático para a última release pinada
- drift ACTIVE / proposal rejeitada → execução bloqueada e rollback claro
- auditor consegue provar offline qual release estava ativa antes/depois

## Escopo

Inclui
- Definir o **contrato de release** por instituição:
  - o que é “CURRENT”, o que é “PINNED”, e como isso é materializado (ex.: symlink, arquivo, registry)
- Implementar rollback automático no pipeline de deploy
- Persistir evidências mínimas (trace/eventos) para auditoria
- Testes cobrindo: falha → rollback → runtime consistente

Não inclui
- Mudança de arquitetura de storage (mantém o modelo atual)
- Expansões de UI/console

## Regras não negociáveis

- **Atomicidade:** não pode existir estado “meio aplicado”.
- **Determinismo:** o procedimento de rollback deve ser determinístico.
- **Governança:** rollback deve deixar trilha (ledger/eventos) e ser bloqueável por freeze/emergency.

## Definições (propostas)

- **Release:** um bundle versionado e materializado no filesystem (ou registry), identificado por `release_id`.
- **Pinned Release:** release considerada “boa e governada” pela instituição (via EGE pin).
- **Current Release:** release efetivamente ativa no runtime.

## Deliverables (Etapa 2.4)

1) `docs/specs/fase-2/02-4-rollback-governed/flow.md`
- Diagrama do fluxo: deploy → pin → rollback.

2) Implementação mínima
- Ajustes no pipeline/orchestrator para:
  - detectar falha de deploy em ponto único
  - reverter para a última pinned release automaticamente
  - emitir eventos (ex.: `EGE_ROLLBACK_STARTED`, `EGE_ROLLBACK_COMPLETED`, `EGE_ROLLBACK_FAILED`)

3) Testes
- Simular deploy com bundle inválido/induzir erro e garantir rollback.
- Garantir que após rollback o runtime volta a ACTIVE na release anterior.

## Definition of Done

- Um deploy falho nunca deixa o runtime apontando para uma release inválida.
- Rollback é automático e deixa trilha de auditoria.
- Testes automatizados cobrem o cenário de falha e retorno ao estado consistente.
