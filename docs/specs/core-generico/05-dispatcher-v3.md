# Dispatcher/Router v3 — bind.kinds de Job

Situação atual
- `idl_router` suporta apenas create/read/list/delete/approval/transition.

Objetivo
Adicionar bind.kinds para jobs (guiado pelo bundle):
- `job.request`
- `job.enqueue`
- `job.get`

Regras
- Nada de endpoints/tipos hardcoded de produto.

## Mudanças esperadas (pontos de integração)
- `engine/core/idl_router.py`: reconhecer novos `bind.kind` e rotear para handlers do dispatcher.
- `engine/core/dispatcher.py` (ou módulo novo): implementar `dispatch_job_request/dispatch_job_enqueue/dispatch_job_get`.
- Ledger: emitir eventos mínimos (`JOB_REQUESTED`, `JOB_ENQUEUED`, `RUNTIME_JOB_REPORTED`).

