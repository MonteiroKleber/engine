# Fase 4 — Etapa 4.4: Governança UI (Policies + Autonomy)

**Data:** 2026-01-19  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.4)

## Objetivo

Adicionar governança operacional para **policies** e **autonomy** no mesmo padrão de mandatos:

- proposal → decide → apply
- diff antes/depois
- trilha no ledger

## Escopo

Inclui
- Implementar proposals governadas para:
  - `policies.json`
  - `autonomy.json`
- UI no console para operar essas proposals.

Não inclui
- Editor completo da DSL
- Governança para workflows/invariants/sod

## Regras não negociáveis

- Não editar arquivos do bundle diretamente.
- Precedência: override governado (instituição) > bundle.
- Read-only do console continua para o que não for proposal.

## Entregas mínimas

1) Core (similar a governed_mandates)
- `governed_policies` e `governed_autonomy`:
  - JSONL append-only + state JSON efetivo
  - validação determinística de schema
  - eventos no ledger

2) Runtime lookup
- `evaluate_policies()` e `evaluate_autonomy()` devem considerar override governado por `(institution_id, dept_id)`.

3) Console UI
- páginas:
  - lista efetiva (bundle vs governado)
  - lista proposals
  - criar proposal
  - decidir
  - apply

4) Testes
- proposta não altera execução até apply
- apply muda decisão do gate
- isolamento por institution/dept

## Definition of Done

- Policies e autonomy podem ser governadas sem rebuild, com prova e isolamento.
