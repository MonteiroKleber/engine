# Etapa 6.6 — Registry Versioning + EGE (hot-swap governado)

**Status:** ✅ IMPLEMENTADO
**Data implementação:** 2026-01-21
**Pré-requisitos:** 6.1 ✅ + 6.2 ✅ + 6.3 ✅ + 6.4 ✅ + 6.5 ✅

## 1) Objetivo

Amarrar **EGE (pins/rollback/drift)** ao **runtime IDL-driven** (router/dispatcher/openapi), para que:

- a API exposta reflita **a versão ativa** (release) por instituição
- o OpenAPI reflita **a versão ativa**
- atualizar/pinar/rollback seja **governado** e resulte em **hot-swap seguro**, sem depender de restart “duro”

## 2) Estado atual (realidade do código)

Hoje o engine já tem:

- releases por instituição (CURRENT symlink / bundle path)
- EGE com pins/proposals/rollback governado
- dynamic router (6.4) registra rotas no startup
- openapi overlay (6.5) é derivado do schema do FastAPI + OperationRegistry em memória

Lacuna:

- Se a versão ativa mudar via EGE (novo pin/rollback), o processo em execução pode:
  - continuar com rotas/registry antigos até restart, ou
  - ficar inconsistente entre “bundle no disco” e “registry em memória”

## 3) Decisões canônicas desta etapa

### 3.1 Fonte de verdade de “versão ativa”

- Fonte de verdade: o mecanismo de releases já existente (CURRENT/pinned_release_id) por instituição.
- O runtime deve expor (em memória) um **ActiveRuntimeSnapshot** por `(institution_id, dept_id?)` com:
  - `active_release_id` (ou equivalente)
  - `bundle_path`
  - `manifest_hash`
  - `operations_hash` (hash do `operations.json`)
  - `loaded_at`

### 3.2 Política de reload

Implementar hot-swap com a menor mudança possível e sem heurística:

- **Reload explícito e governado**: ao aplicar pin/rollback (ponto já governado), chamar uma função do runtime que:
  - recarrega bundle/registry em memória
  - revalida proof mínima (hashes via loader)
  - atualiza snapshot ativo
- Não fazer “auto-reload” por polling a cada request (custo/risco).
- Limitação explícita (aceita nesta etapa, por restrição do FastAPI):
  - rotas FastAPI são registradas no startup e não serão removidas/re-registradas no hot-swap.
  - portanto, o reload governado garante **consistência** (registry/openapi/execução) para rotas já registradas,
    mas **não garante** que novas rotas (novos paths/methods) apareçam sem restart.
  - a habilitação de “adicionar/remover rotas sem restart” fica para etapa futura (se necessário).

### 3.3 Escopo multi-dept

- Para multi-dept, o snapshot deve refletir:
  - bundle multi (um release)
  - registry por dept dentro do bundle
- Em fases futuras, se existir “release por dept”, isso será modelado separadamente (não aqui).

## 4) Mudanças necessárias (mínimo)

- Introduzir um módulo core que mantenha e atualize `ActiveRuntimeSnapshot` por instituição:
  - criar/atualizar snapshot no boot (após load_bundle)
  - atualizar snapshot quando EGE aplicar pin/rollback
- Integrar EGE:
  - no “accept pin” e no “governed rollback”, chamar `reload_active_runtime(institution_id)`
- Garantir que:
  - dynamic router continua válido após reload, ou
  - no mínimo, o handler wrapper resolve operação contra o registry atualizado (sem ficar com cache stale).
  - handlers não podem capturar `OperationSpec` em closure de registro; devem resolver em runtime por lookup.

## 5) Observabilidade / prova

- Emitir evento(s) determinísticos no ledger ao efetivar reload:
  - `RUNTIME_RELOADED` (ou equivalente), com:
    - `active_release_id`
    - `manifest_hash`
    - `operations_hash`
    - `reason`: `pin_applied|rollback|manual`

## 6) Critérios de aceite (Etapa 6.6)

- Após aplicar pin (EGE) em uma instituição:
  - `ActiveRuntimeSnapshot` muda (release_id/hash)
  - `/openapi.json` muda conforme a nova versão ativa (sem restart)
  - requests para uma rota presente apenas na nova versão funcionam (em `ENGINE_API_MODE=idl|both`)
- Após rollback governado:
  - snapshot volta para a versão anterior (pinned)
  - openapi e registry refletem a versão anterior
- Testes (sem HTTP real):
  - simular troca de bundle path (ex.: alternar entre dois bundles temporários) e provar reload
  - provar que o handler wrapper resolve pelo registry atualizado
  - provar evento no ledger (type + hashes)
