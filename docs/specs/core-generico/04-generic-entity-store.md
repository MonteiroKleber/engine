# GenericEntityStore (storage genérico)

Objetivo: suportar entidades definidas por bundle e remover `ENTITY_CONFIG`.

Modelo mínimo
- chave: (institution_id, dept_id, entity_type, entity_id)
- campos: state, version, data_json, timestamps

Validação
- payload validado contra schema do bundle (EntitySpec).

Execução (dispatcher)
- `create/read/list/delete/transition` devem resolver `EntitySpec` e `WorkflowSpec` pelo registry do bundle.
- `transition` aplica guard/effects do bundle (determinístico), com controle de concorrência por `version`.

DoD (verificável)
- Uma entidade definida em bundle de teste consegue:
  - `create` + `read`
  - `transition` com guard true/false
  - ledger registra os eventos com `case_id` e `step` corretos

