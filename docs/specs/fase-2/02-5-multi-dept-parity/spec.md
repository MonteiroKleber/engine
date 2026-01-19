# Fase 2 — Etapa 2.5: Multi-Department Parity End-to-End

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.5)

## Objetivo

Tornar **multi-department** um caminho de primeira classe end-to-end, com paridade real (não “apenas paths auxiliares”).

Em termos práticos:
- 2 departamentos distintos operando simultaneamente
- isolamento correto por `institution_id` **e** por `dept_id`
- contracts/gates e state-store funcionando por dept

## Escopo

Inclui
- Definir o modelo canônico de “department context”:
  - como `dept_id` entra no request (path/header)
  - como contracts são selecionados por dept
  - como state_store/ledger são namespaced por dept+institution
- Garantir paridade de contracts por dept:
  - approvals, rbac, policies, sod, invariants, mandates, autonomy
- Adicionar testes E2E para 2 depts (mínimo):
  - `finance`
  - `support` (ou `tech`) com endpoints simples

Não inclui
- UI
- Legacy Bridge
- Novo stack/runtime

## Regras não negociáveis

- Um dept não pode ler/escrever estado de outro dept.
- Um dept não pode “herdar permissividade” por ausência de contract.
- Auditoria deve identificar `dept_id` em eventos críticos.

## Entregas mínimas

1) Template de 2º dept
- Criar um segundo bundle mínimo (ex.: `bundles/support-pilot`) com:
  - contracts mínimos required=true
  - 1 endpoint mutável simples (ex.: `POST /support/tickets`)
  - approvals opcional, mas mandates/autonomy devem cobrir o endpoint

2) Routing/Loader
- Definir/confirmar como o runtime seleciona dept:
  - se via prefixo `/d/{dept_id}/...` ou rotas fixas por dept
- Garantir que `load_bundle()` cria contextos separados por dept.

3) Testes
- E2E: finance e support em paralelo, na mesma instituição:
  - criar expense em finance não aparece em support
  - criar ticket em support não aparece em finance
- E2E: dois depts em duas instituições (matriz 2x2) sem inferência.

## Definition of Done

- Dois departamentos rodando com isolamento por dept+institution.
- Gates/mandates/autonomy aplicados corretamente por dept.
- Testes E2E cobrindo cenários principais e anti-inference.
