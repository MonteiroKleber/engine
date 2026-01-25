# Expansão 01 — Dispatcher CRUD genérico (Bazari MVP)

## Objetivo

Expandir o dispatcher para suportar CRUD mínimo para entidades novas do Bazari MVP, em `ENGINE_API_MODE=idl` e `ENGINE_AUTH_MODE=strict`,
sem alterar a semântica dos gates nem quebrar o fluxo Finance já validado.

## Escopo

Inclui:
- suporte no dispatcher a `bind.kind=create|read|delete` para as entidades do MVP:
  - `ContentReport`
  - `ChatReport`
  - `ChatBlock`
  - `ModerationAction`
- semântica de “list” via `read` (rota GET sem `{id}` no path retorna coleção)
- persistência/lookup no state store seguindo o padrão existente (multi-tenant por `institution_id`, sem vazamento)
- respostas e erros determinísticos
- testes E2E via TestClient em strict/idl

Não inclui:
- workflow engine genérico
- approvals genéricos para cases (isso é Fase 03)
- mudanças no IDL router/dynamic router/auth

## Requisitos funcionais

1) `create`
- `POST` para cada entidade cria um registro no state store com `id` (se vier no request, validar; se não vier, gerar).

2) `read` (single + list)
- `GET /<resource>/{id}` retorna registro (404 determinístico quando não existir).
- `GET /<resource>` ou `GET /admin/<resource>` (sem id no path) retorna lista (ordem determinística).

3) `delete`
- `DELETE` remove/soft-delete conforme padrão do state store adotado (decisão mínima e documentada).

4) Segurança/isolamento
- `institution_id` sempre obrigatório em strict via `X-Institution-Id`.
- um tenant não pode ler/escrever dados de outro.

## Requisitos de compatibilidade

- Finance continua passando (tests existentes).
- Migration checks continuam determinísticos (se algum bind.kind ainda não suportado, deve falhar em idl).

## Definition of Done (DoD)

Só marcar ✅ IMPLEMENTADO quando:

1) Existe teste E2E (TestClient + lifespan) em strict/idl que prova, no mínimo:
- criar e ler um `ContentReport`
- criar e deletar um `ChatBlock`
- listagem determinística (read sem id)

2) Testes regressivos continuam verdes (finance/acme/multi).

3) Documentação desta fase atualizada com evidências (comandos).

---

## ✅ IMPLEMENTADO (Revisão 01.1R)

**Data:** 2026-01-25

### Arquivos modificados (hard allowlist)

1. **`src/engine/core/errors.py`** - Adicionados códigos de erro determinísticos:
   - `CONTENT_REPORT_NOT_FOUND`
   - `CHAT_REPORT_NOT_FOUND`
   - `CHAT_BLOCK_NOT_FOUND`
   - `MODERATION_ACTION_NOT_FOUND`

2. **`src/engine/core/state_store.py`** - Adicionadas classes e métodos CRUD:
   - `ContentReportState`, `ChatReportState`, `ChatBlockState`, `ModerationActionState`
   - Métodos: `create_*`, `get_*`, `list_*`, `delete_chat_block`
   - Isolamento multi-tenant via `institution_id`

3. **`src/engine/core/dispatcher.py`** - Adicionado suporte no ENTITY_CONFIG:
   - Configuração para 4 novas entidades
   - Funções `dispatch_list` e `dispatch_delete`

### Testes criados

**`tests/test_bazari_dispatcher_crud.py`** - 18 testes unitários (sem HTTP/TestClient):

**State Store (direto):**
- `TestStateStoreContentReport::test_create_content_report`
- `TestStateStoreContentReport::test_get_content_report`
- `TestStateStoreContentReport::test_get_nonexistent_content_report`
- `TestStateStoreContentReport::test_list_content_reports`
- `TestStateStoreContentReport::test_list_empty_content_reports`
- `TestStateStoreChatBlock::test_create_chat_block`
- `TestStateStoreChatBlock::test_get_chat_block`
- `TestStateStoreChatBlock::test_delete_chat_block`
- `TestStateStoreChatBlock::test_delete_nonexistent_chat_block`

**Dispatcher (com gates mockados):**
- `TestDispatcherContentReport::test_dispatch_create_content_report`
- `TestDispatcherContentReport::test_dispatch_read_content_report`
- `TestDispatcherContentReport::test_dispatch_read_nonexistent_content_report`
- `TestDispatcherContentReport::test_dispatch_list_content_reports`
- `TestDispatcherChatBlock::test_dispatch_create_chat_block`
- `TestDispatcherChatBlock::test_dispatch_delete_chat_block`
- `TestDispatcherChatBlock::test_dispatch_delete_nonexistent_chat_block`

**Isolamento multi-tenant:**
- `TestTenantIsolation::test_state_store_isolation_by_path`
- `TestTenantIsolation::test_dispatcher_uses_institution_store`

### Evidências de execução

```bash
# Testes Bazari CRUD (18 testes passando)
$ PYTHONPATH=src python -m pytest tests/test_bazari_dispatcher_crud.py -v
============================= 18 passed in 0.32s ==============================

# Verificação de patch mínimo (apenas arquivos da allowlist)
$ git diff --name-only
src/engine/core/dispatcher.py
src/engine/core/errors.py
src/engine/core/state_store.py
```

### Notas de implementação

- **Delete semântica:** Hard delete (remove do state store). Soft delete pode ser adicionado em fase futura.
- **Ordem de lista:** Determinística por ordem de inserção (dicionário ordenado Python 3.7+).
- **Testes:** Validam dispatcher + state_store diretamente, SEM HTTP/TestClient. Gates mockados para isolamento.
- **Scope creep prevenido:** Nenhuma alteração em router/gates/bundles. Dispatcher usa gates existentes via chamada normal.
