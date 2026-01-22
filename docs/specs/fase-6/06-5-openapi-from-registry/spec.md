# Etapa 6.5 — OpenAPI a partir do OperationRegistry (por instituição/dept)

**Status:** IMPLEMENTADO ✅
**Pré-requisitos:** 6.1 ✅ + 6.2 ✅ + 6.3 ✅ + 6.4 ✅
**Data de conclusão:** 2026-01-21

## 1) Objetivo

Garantir que o engine exponha documentação OpenAPI **derivada do contrato ativo**, compatível com:

- runtime IDL-driven (`ENGINE_API_MODE=idl|both`)
- single-dept e multi-dept (`/d/{dept_id}/...`)

Isso é requisito para Target de produção (SDKs, integrações, QA, observabilidade).

## 2) Estado atual (realidade do código)

- Bundles incluem `openapi.yaml` (required=false em single, required=true por dept em multi), mas:
  - pode ficar desatualizado em relação ao registry
  - não é garantido como “OpenAPI do sistema ativo”
- FastAPI já expõe `/openapi.json`, porém ele descreve:
  - rotas legacy
  - e, após 6.4, também rotas dinâmicas
- Ainda falta alinhar o OpenAPI com os **schemas** e **metadados institucionais** necessários (headers, auth, erros).

## 3) Decisões canônicas desta etapa

### 3.1 Fonte de verdade do OpenAPI

- Fonte de verdade para **paths/operations**: `OperationRegistry` (contrato `operations.json`).
- Fonte de verdade para **auth scheme**: modo de auth do engine (`ENGINE_AUTH_MODE`) e headers exigidos.
- Schemas:
  - mínimo: schemas genéricos para payloads aceitos hoje (Expense, Ticket) **ou** schema “opaque” (`additionalProperties`) quando não houver modelagem suficiente.
  - Não inventar tipagem completa da DSL nesta etapa.

### 3.2 Superfícies OpenAPI

Expor pelo menos:

- `/openapi.json` (global do engine, como FastAPI já faz)
- `/d/{dept_id}/openapi.json` (multi-dept) para refletir operações do dept selecionado

Observação: o mecanismo pode ser implementado como:
- geração programática a partir do registry (preferido), ou
- overlay/patch do OpenAPI do FastAPI para inserir headers/schemas (mínimo aceitável).

## 4) Requisitos mínimos do OpenAPI (DoD)

- Cada operação do `OperationRegistry` aparece no OpenAPI com:
  - method + path
  - operationId (de `operation_id`)
  - responses mínimas (200/201/202 e erros listados em `OperationSpec.errors`)
- Auth e headers aparecem explicitamente:
  - `X-Institution-Id` (quando requerido)
  - `X-Actor-Token` (strict)
  - `Idempotency-Key` quando `idempotency=required`
- Para multi-dept:
  - as rotas `"/d/{dept_id}"+path` aparecem e `dept_id` é um path param.

## 5) O que não pode mudar

- Não remover/alterar rotas legacy.
- Não alterar semântica dos gates/dispatcher.
- Não transformar `openapi.yaml` do bundle em requisito de execução.

## 6) Critérios de aceite (Etapa 6.5)

- Em `ENGINE_API_MODE=idl`, `/openapi.json` contém as rotas IDL (registry-driven), com `operationId` correto.
- Em bundle multi, `/openapi.json` contém também as rotas `/d/{dept_id}/...`.
- OpenAPI declara os headers obrigatórios (institution/actor token/idempotency quando aplicável).
- Testes validam:
  - `operationId` por operação
  - presença de headers
  - presença de path param `dept_id` nas rotas multi

