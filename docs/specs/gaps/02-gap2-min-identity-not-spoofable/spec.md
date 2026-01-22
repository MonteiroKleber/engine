# GAP 2 — Identidade mínima não-spoofável (produção single-instance)

## A) Resumo de correção (rastreabilidade)

- **Intenção original (spec anterior):** introduzir `ENGINE_AUTH_MODE` e um “token registry” simples para evitar spoof.
- **Intenção corrigida (produção no cliente):** identidade deve ser validada **antes de qualquer gate** com um mecanismo mínimo operável em single-instance, incluindo **provisionamento** (como o cliente cria atores/tokens) e **controles de compatibilidade** explícitos (dev vs prod).
- **Impacto:** o runtime deixa de aceitar “roles por header” em produção; `X-Actor-Id` passa a ser derivado do token, não fornecido pelo cliente.

### O que foi mantido
- Não assumir OAuth/JWT enterprise, nem DB.
- Resolver `actor_id`/`roles` localmente, de forma determinística, com persistência no namespace da instituição.

### O que foi alterado
- Exigir um caminho de **provisionamento** (admin cria tokens de ator por instituição) como parte da instalação real.
- Em produção, bloquear qualquer request mutável sem identidade verificada.

### O que foi descartado por viés de “piloto”
- “Warnings apenas” sem enforcement real em produção.

## B) Spec técnica corrigida (contrato)

### Objetivo
Eliminar confiança em headers livres (`X-Actor-Id`, `X-Actor-Roles`) como identidade e introduzir autenticação mínima aceitável para produção single-instance:

- engine valida identidade **antes** de qualquer gate institucional
- roles não podem ser fornecidos pelo cliente sem prova
- provisionamento de atores existe (admin cria tokens)

### Estado atual (com arquivos/linhas reais)
- `ActorContext` é derivado de headers e aceita roles livres:
  - `src/engine/core/actor_context.py:39-85`
- `get_actor_context()` usa `parse_actor_context()`:
  - `src/engine/api/dependencies.py:12-46`
- O middleware do server lê `X-Actor-Id` e `X-Actor-Roles` para audit em eventos (sem prova de autenticidade):
  - `src/engine/api/server.py:521-536` (exemplo em freeze/emergency)

### Mudanças necessárias (mínimas)
1) **Modo de auth**
   - Introduzir `ENGINE_AUTH_MODE` com valores:
     - `dev`: compatibilidade (headers existentes)
     - `strict`: produção (token obrigatório)

2) **Credencial do ator**
   - Introduzir `X-Actor-Token` (ou `Authorization: Bearer`) como credencial.
   - Em `strict`, o engine resolve `actor_id` e `roles` **somente** via token.

3) **Registry por instituição (sem DB, append-only)**
   - Criar storage em:
     - `institutions/<institution_id>/actors/actors_registry.jsonl` (append-only)
     - `institutions/<institution_id>/actors/actors_state.json` (lookup)
   - Um registro mínimo contém:
     - `token_sha256` (hash do token, não o token em claro)
     - `actor_id`
     - `roles` (list)
     - `status` (active/revoked)
     - `created_at`, `created_by`

4) **Provisionamento (admin)**
   - Criar endpoints admin mínimos para gerenciar tokens de ator:
     - `POST /admin/institutions/{id}/actors` (gera token e registra)
     - `POST /admin/institutions/{id}/actors/{actor_id}/revoke`
     - `GET /admin/institutions/{id}/actors` (list)
   - Auth desses endpoints usa o mecanismo já existente (`X-Admin-Token` / admin keys), sem inventar outro.

5) **Enforcement antes dos gates**
   - Atualizar `get_actor_context()` para:
     - `strict`: exigir token, resolver actor/roles do registry, ignorar `X-Actor-Roles`
     - `dev`: manter comportamento atual
   - Atualizar middlewares que hoje usam headers para audit (ex.: freeze/emergency) para usar o `ActorContext` resolvido quando disponível (ou registrar explicitamente “unverified” em dev).

### Restrições explícitas (o que NÃO mudar)
- Não implementar OAuth/JWT enterprise.
- Não introduzir banco de dados.
- Não quebrar console/admin auth (isso é separado).
- Não mudar a semântica dos gates; apenas a fonte de `actor_id/roles`.

### Eventos de ledger afetados
- Em `strict`:
  - eventos devem registrar `actor_id` e `actor_roles` provenientes do registry
- Em `dev`:
  - emitir um evento explícito `UNVERIFIED_IDENTITY_USED` (ou equivalente) quando headers forem usados como fonte

### Riscos técnicos
- Introduzir token registry exige cuidado com:
  - não armazenar token em claro
  - cache/invalidação simples
  - compatibilidade com testes existentes

## C) Critérios de aceite (produção)

- Em `ENGINE_AUTH_MODE=strict`:
  - request sem token → 401 determinístico
  - spoof de `X-Actor-Roles` não altera roles efetivas
  - actor_id/roles são resolvidos via registry por instituição
- Provisionamento:
  - admin consegue criar token de ator e revogar, com eventos no ledger
- Testes:
  - token válido permite request e registra actor_id correto
  - token revogado/ausente bloqueia
  - dev mantém compat, mas registra evento “unverified”

## D) Prompt para Claude Code (ver `prompts.md`)
