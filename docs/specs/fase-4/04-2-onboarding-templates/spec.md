# Fase 4 — Etapa 4.2: Onboarding + Templates

**Data:** 2026-01-19  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.2)

## Objetivo

Reduzir drasticamente o custo de iniciar um piloto:

- criar instituição
- escolher dept(s) e templates
- gerar bundle(s) + rodar proof
- deixar pronto para operar sem “setup manual”

## Escopo

Inclui
- Um fluxo guiado no console (wizard) para:
  - criar/listar instituições
  - escolher templates: `finance`, `support` (mínimo)
  - gerar bundles em um local por instituição
  - rodar proof e mostrar resultado

Não inclui
- deploy automático em produção
- conectores de legado

## Regras não negociáveis

- Sem pular prova: todo bundle gerado deve passar `engine.proof verify` antes de ser “oferecido” como pronto.
- Mudanças são explícitas e auditáveis.

## Entregas mínimas

1) Console
- `GET /console/onboarding`
- `POST /console/onboarding/create-institution`
- `POST /console/onboarding/generate-bundle` (seleção template)
- `GET /console/onboarding/proof` (mostra report)

2) Templates
- Reusar bundles existentes:
  - `bundles/finance-pilot`
  - `bundles/multi-pilot` (se útil)
- Criar um mecanismo de “template registry” simples (lista fixa inicial).

3) Testes
- fluxo happy-path: create institution → generate bundle → proof PASS

## Definition of Done

- Um usuário consegue, via browser, criar uma instituição e gerar um bundle piloto com proof PASS.
