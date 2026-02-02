# Core genérico (Engine) — Visão

Objetivo: transformar o Engine em um **runtime genérico guiado pelo bundle** (IDL), removendo hardcode de entidades e approvals.

Princípios
- Engine é core neutro (sem regra de negócio específica).
- Bundle é a fonte canônica (sem bundle/registry ativo, não existe operação).
- Enforcement determinístico (RBAC, mandates, autonomy, policies, invariants, SoD).
- 2 conceitos de 1ª classe:
  - **Entidades**: estado institucional durável
  - **Jobs**: execução no mundo (outbox + runtime)

Regras de execução (anti-retrabalho e anti-regressão)
- Antes de implementar qualquer coisa: **provar por busca** que não existe (use `rg`/`ls`/ler docs).
- Preferir **estender mecanismos existentes** (router/dispatcher/stores) ao invés de criar “v2 paralelo”.
- Mudanças mínimas, com **testes cobrindo comportamento atual + novo**.
- Nunca “consertar” quebrando invariantes do core (ex.: isolamento multi-tenant, idempotência, SoD).

Problema atual (evidência)
- `engine/core/dispatcher.py` depende de `ENTITY_CONFIG` e falha em entidades do bundle (ex.: `FileOperation`).
- `dispatch_approval_request` é específico (hoje: “Expense only”).

Achados (Prompt 1 — auditoria)
- Existe `generic_approval_index` no `state_store` (parcialmente genérico), mas a persistência/execução em `dispatcher.py` ainda é hardcoded por `entity_type`.
- `bind.kind` suportados hoje no IDL router: `create`, `read`, `list`, `delete`, `approval`, `transition` (não existe `job.*` ainda).
- Não existe flag/env para “habilitar runtime genérico” (nenhum `ENGINE_*GENERIC/*DYNAMIC`).

Escopo do “conserto correto”
- **Bloco Jobs (prioridade para Personal Ops / filesystem):** jobs de 1ª classe + approvals genéricos para jobs + outbox governado + report de resultado.
- **Bloco Entidades (core completo):** storage genérico + workflows genéricos para entidades do bundle (remove `ENTITY_CONFIG`).

Não-objetivos (para evitar “gambiarra”)
- Não adicionar “FileOperation” (ou qualquer entidade de produto) em listas fixas no Engine.
- Não criar endpoints de produto “na mão” no Engine (rotas vêm do bundle).
