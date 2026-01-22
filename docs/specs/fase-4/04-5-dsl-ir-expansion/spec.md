# Fase 4 — Etapa 4.5: Expansão DSL/IR (Controlada)

**Data:** 2026-01-19  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.5)

## Objetivo

Expandir o subset da **IDL DSL v1.2.2** e do **IRCS v1** de forma controlada, sem inflar escopo e sem quebrar provas.

Foco: dar cobertura para o que já virou produto no console e no runtime.

## Escopo

Inclui
- Definir uma lista pequena de incrementos (patch-level) na DSL subset.
- Atualizar `engine.idl_dsl` para suportar esses incrementos.
- Atualizar IRCS emitter/schema conforme necessário.
- Adicionar testes determinísticos.

Não inclui
- Reescrever a gramática completa v1.2.2
- Novos constructos institucionais grandes (councils/norms)

## Regras não negociáveis

- Compatibilidade: não quebrar `examples/finance.idl`.
- Determinismo: mesmo input → mesmo IR.
- Erros determinísticos.

## Entregas mínimas

- `docs/specs/fase-4/04-5-dsl-ir-expansion/changes.md` (lista de mudanças, pequenas e enumeradas)
- Implementação no parser/emitter + testes.

## Definition of Done

- Subset expandido com mudanças pequenas e testadas.
- Sem regressão em proof/pipeline.
