# Fase 3 — Etapa 3.5: Console de Evolução (EGE)

**Data:** 2026-01-19
**Status:** IMPLEMENTADO (PROMPT 3.5.2)
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.5)

## Objetivo

Adicionar ao console uma UI mínima para governança de evolução:

- visualizar proposals/pins
- visualizar releases e deploy traces
- executar rollback governado (quando permitido)

## Escopo

Inclui
- Páginas read-mostly (com ações governadas específicas):
  - listar proposals EGE
  - detalhes de proposal (diff/resumo + status)
  - listar pins e pinned_release_id
  - listar releases e deploy traces
- Ação mutável permitida nesta etapa:
  - rollback governado (botão), com confirmação explícita e trilha

Não inclui
- editor de IDL/IR
- automação de rollout

## Regras não negociáveis

- Ações mutáveis exigem `X-Admin-Token`.
- Rollback só pode executar o mecanismo governado já implementado (Etapa 2.4), sem atalhos.
- Console não pode escrever arquivos diretamente.

## Entregas mínimas

1) Rotas console
- `GET /console/ege` (overview: drift, pinned_release_id, proposals count)
- `GET /console/ege/proposals` (lista)
- `GET /console/ege/proposals/{id}` (detalhe)
- `GET /console/ege/releases` (lista)
- `GET /console/ege/traces/{release_id}` (trace view)
- `POST /console/ege/rollback` (executa rollback governado para pinned)

2) Templates
- listas e detalhes com badges
- confirmação de rollback

3) Testes
- auth
- render das páginas
- rollback: só com token + comportamento esperado

## Definition of Done

- Operador consegue ver status EGE e executar rollback governado via console com segurança.
