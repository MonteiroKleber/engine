# Fase 2 — Etapa 2.7: Legacy Bridge MVP (Read-Only)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.7)

## Objetivo

Iniciar o Legacy Bridge com valor imediato e baixo risco:

- **provar o legado** (metadados + integridade + drift)
- **sem reescrever** e **sem mutar** sistemas existentes
- focar em **read-only** com trilha auditável

## Escopo

Inclui
- Modelo canônico de "Legacy Asset" (o que é um artefato legada governável):
  - fonte (tipo + localização)
  - schema/metadados extraídos
  - hashing SHA256 dos bytes ou export determinístico
  - registro append-only no ledger (drift/tamper)
- Um conector read-only mínimo (escolher 1):
  - arquivo (CSV/JSON) exportado
  - endpoint HTTP read-only
  - dump de tabela (arquivo)
- Detecção de drift:
  - recalcular hash e comparar
  - emitir evento `LEGACY_DRIFT_DETECTED`

Não inclui
- Conectores COBOL/DB nativos (isso pode ser etapa seguinte)
- Escrita/ação no legado
- Migração de código

## Regras não negociáveis

- Bridge read-only: nenhum side-effect no legado.
- Fonte de verdade do bridge é o ledger (append-only).
- Drift/tamper devem ser detectáveis offline (pelo menos no nível de hashes + timestamps + origem).

## Deliverables

1) `docs/specs/fase-2/02-7-legacy-bridge-readonly/model.md`
- Definição do modelo de Legacy Asset + eventos.

2) Implementação mínima
- Um módulo `engine.legacy_bridge` com:
  - registro de assets
  - snapshot/hash
  - verificação periódica ou sob demanda

3) CLI mínima
- `python -m engine.legacy_bridge register ...`
- `python -m engine.legacy_bridge verify ...`

4) Testes
- Registrar asset → ledger registra
- Alterar conteúdo → drift detectado

## Definition of Done

- Existe pelo menos 1 conector read-only funcional.
- Drift é detectado e auditável.
- O mecanismo não depende de runtime rodando (pode ser offline CLI).
