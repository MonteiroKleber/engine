# Prompts — Engine (Core genérico)

## Prompt 1 — Auditoria do core (ponto exato do erro)
Repo: `/home/bazari/engine`

Objetivo: apontar exatamente onde o Engine decide “entity type suportada vs não suportada” e por que `FileOperation` falha.

Checklist:
1) Localizar todos os `Unsupported entity type` e `Approval not supported for entity type`.
2) Provar onde existe `ENTITY_CONFIG` e quais tipos lista.
3) Confirmar quais `bind.kind` o `idl_router` suporta hoje.
4) Checar se já existe runtime genérico escondido por flag/env (e como habilitar). Se não existir, afirmar isso com evidência.

Gate obrigatório (anti-retrabalho):
- Antes de criar qualquer arquivo/classe nova, fazer `rg` e apontar onde algo equivalente já existe.
- Se existir, reaproveitar e justificar por que a extensão é segura.

Notas do Prompt 1 (para orientar os próximos prompts)
- Reuso recomendado:
  - `state_store.index_generic_approval/get_generic_approval` como base para approvals genéricos (faltam targets job/entity e persistência genérica).
  - `_apply_transition_effects` e a infraestrutura de workflow do IDL (já existe), mas bloqueada por `ENTITY_CONFIG`.
  - `legacy_bridge/write_registry.py` como referência de “outbox governado” (para Jobs).
- Gap confirmado:
  - Persistência ainda é hardcoded por `entity_type` no dispatcher; sem flag para ativar runtime genérico.

## Prompt 2 — Implementar Jobs 1ª classe (core neutro)
Base: `engine/docs/specs/core-generico/02-jobs-first-class.md` + `engine/docs/specs/core-generico/05-dispatcher-v3.md`

Objetivo: suportar `job.request/job.enqueue/job.get` via bundle, com JobStore + outbox governado + report auditável.

Regras:
- Zero regra de negócio específica.
- Tudo guiado pelo bundle/registry.
- Testes novos + DoD verificável com curl.
 - Antes de implementar, **provar por busca** se já existe JobStore/job dispatcher/outbox writer (mesmo parcial).
 - Evitar regressão: manter compatibilidade com bind.kinds atuais (create/read/list/delete/approval/transition) e com o legacy bridge.

Estratégia sugerida (mínima e segura)
- Implementar Jobs **em paralelo** ao runtime de entidades existente (não tocar em `ENTITY_CONFIG` ainda).
- Adicionar apenas novos `bind.kind` (`job.request/job.enqueue/job.get`) e um JobStore dedicado.
- Reusar os conectores/outbox do `legacy_bridge` para emitir o payload de job (para minimizar risco).

Checklist DoD (o que você deve mostrar no final)
- `rg` provando que não existe hardcode de “personal/files” no Engine.
- `curl`:
  - cria job `job.request`
  - (se destrutivo) retorna `approval_id`
  - decide approval
  - job vai para outbox e runtime reporta
  - `job.get` mostra `executed` e `result_json`
- Testes passando (apenas o conjunto afetado, sem “fixar o mundo”).

Checklist de regressão (obrigatório):
- Rotas IDL existentes continuam registrando e respondendo igual (snapshot básico do `/openapi.json` ou asserts em testes).
- `/runtime/jobs/{job_id}/report` continua idempotente e isolado por instituição.
- `/approvals/pending` continua correto (requested sem decided).

## Prompt 3 — Approvals genéricos (job_ref + entity_ref)
Base: `engine/docs/specs/core-generico/03-approvals-generic.md`

Objetivo: remover lógica por entity_type e suportar approvals que liberam `job.enqueue`.

Gate obrigatório:
- Antes de mudar approvals, mapear endpoints/fluxos existentes e adicionar testes de proteção (não regredir).

## Prompt 4 — GenericEntityStore (opcional, mas core “completo”)
Base: `engine/docs/specs/core-generico/04-generic-entity-store.md`

Objetivo: eliminar `ENTITY_CONFIG` e suportar entidades definidas no bundle (sem hardcode).

Importante:
- Só iniciar este prompt quando o bloco de Jobs estiver estável, para não misturar migrações grandes.
 - Antes de criar um store novo, verificar o `state_store` atual e possíveis pontos de extensão.
