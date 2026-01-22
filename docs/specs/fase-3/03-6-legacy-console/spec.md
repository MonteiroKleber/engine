# Fase 3 — Etapa 3.6: Legacy Bridge no Console (Read-Only)

**Data:** 2026-01-19
**Status:** IMPLEMENTADO
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.6)

## Objetivo

Adicionar ao console uma visão operacional do **Legacy Bridge (read-only)**:

- listar assets registrados
- visualizar último snapshot/hash
- executar verify sob demanda e mostrar drift/tamper

## Escopo

Inclui
- Páginas console:
  - lista de legacy assets por instituição/dept
  - detalhe do asset (metadados + hash + status)
  - botão “Verify” (ação mutável permitida, mas read-only no legado)

Não inclui
- conectores write-mode
- edição de asset fora de register (se existir)

## Regras não negociáveis

- Ações exigem `X-Admin-Token`.
- Verify não pode modificar o arquivo legado (read-only).
- Anti path traversal e isolamento por instituição/dept.

## Entregas mínimas

1) Rotas console
- `GET /console/legacy?institution_id=...&dept_id=...` (já existe placeholder; substituir por real)
- `GET /console/legacy/{asset_id}?institution_id=...&dept_id=...`
- `POST /console/legacy/{asset_id}/verify` (executa verify e redireciona)

2) Templates
- lista com badges (active/drift/missing)
- detalhe com histórico mínimo (últimos eventos, se disponível)

3) Testes
- auth
- list/detail
- verify detecta drift

## Definition of Done

- Operador consegue ver assets e rodar verify via console.
