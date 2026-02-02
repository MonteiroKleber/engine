# Approvals genéricos (entity/job)

Objetivo: approval aponta para target genérico e o Engine resolve via registry + stores genéricos.

Target
- `entity_ref`: {entity_type, entity_id, transition?}
- `job_ref`: {job_id, action? (enqueue)}

DoD
- Nenhum `if entity_type == ...` no fluxo.
- Tests cobrindo job_ref e entity_ref.

## Contrato mínimo de payload no ledger
Para permitir `/approvals/pending` e debugabilidade, o `APPROVAL_REQUESTED` deve carregar:
- `approval_id`
- `target_kind`: `job` | `entity`
- `target_ref`:
  - job: `{ "job_id": "...", "action": "enqueue" }`
  - entity: `{ "entity_type": "...", "entity_id": "...", "transition": "..." }`
- `rule_name` / `step` (derivado do workflow/transition do bundle, não hardcoded)

## Decisão
Em `APPROVAL_DECIDED`, o engine deve:
- bloquear decisão repetida
- aplicar SoD e regras do bundle
- se aprovado:
  - job_ref: liberar `job.enqueue`
  - entity_ref: liberar transition/commit

