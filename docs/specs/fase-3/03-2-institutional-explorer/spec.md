# Fase 3 — Etapa 3.2: Institutional Explorer (Contratos)

**Data:** 2026-01-18
**Status:** IMPLEMENTADO (PROMPT 3.2.2)
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.2)

## Objetivo

Expandir o console read-only para permitir navegar a **camada institucional** de forma executiva e técnica, usando apenas os artefatos canônicos:

- `bundle.manifest.json`
- `contract_ledger.json`
- contracts (rbac/policies/mandates/autonomy/workflows/invariants/sod/approvals)
- provas (`engine.proof`)

## Escopo

Inclui
- Páginas read-only no `/console` para:
  - visualizar manifest e contract_ledger
  - listar contracts e abrir o conteúdo (com syntax highlight simples)
  - exibir âncoras: `source_idl_sha256`, `manifest_hash`, hashes de cada contract
- Navegação por `institution_id` + `dept_id` (multi-dept)

Não inclui
- editar contracts
- criar proposals

## Regras não negociáveis

- Read-only total.
- Mostrar sempre o hash ao lado do conteúdo (prova por inspeção).
- Não ler arquivos fora do bundle root (anti path traversal).

## Entregas mínimas

1) Novas rotas console
- `GET /console/contracts?institution_id=...&dept_id=...`
- `GET /console/contracts/{file}?institution_id=...&dept_id=...`
- `GET /console/proof?institution_id=...&dept_id=...` (executa verify offline em memória e mostra resultado)

2) API/read model
- Reusar o que já existe para descobrir bundle atual/pinned.
- Se não existir, criar endpoint read-only que retorna o caminho do bundle ativo por institution/dept.

3) Testes
- Testar que:
  - rotas exigem `X-Admin-Token`
  - não existe rota mutável
  - leitura é limitada ao bundle
  - hash exibido bate com manifest

## Definition of Done

- Um CTO consegue selecionar institution/dept e:
  - ver manifest + contract_ledger
  - abrir qualquer contract e ver conteúdo + hash
  - rodar `proof verify` e ver PASS/FAIL

