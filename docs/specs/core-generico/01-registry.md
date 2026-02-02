# Registry canônico do bundle

Objetivo: ao ativar um bundle, o Engine constrói um registry em memória (instituição/dept) que vira fonte única para roteamento, validação, autorização e execução.

Componentes mínimos
- OperationSpec (já existe via `operations.json`)
- EntitySpec (schema + constraints)
- WorkflowSpec (states/transitions/guards/effects)
- ApprovalSpec (target: entity/job)
- JobSpec (params/result schema + risk + approval_required)

Fonte
- Exclusivamente dos artefatos do bundle (nunca hardcoded).

