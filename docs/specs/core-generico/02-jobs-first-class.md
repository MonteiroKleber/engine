# Jobs de 1ª classe (Engine)

Objetivo: governar execução no mundo sem hardcode:
- criar job (job.request)
- (se destrutivo) gerar approval
- enfileirar no outbox (job.enqueue)
- receber report do runtime (persistir resultado + ledger)
- expor status/resultado (job.get)

JobStore mínimo (por instituição/dept)
- `job_id`, `job_type`, `state`, `params_json`
- `result_json` (pequeno) e/ou `artifacts`
- `requested_by_actor_id`, `approval_id` (nullable)
- timestamps + version

Outbox
- Engine escreve payload padronizado e auditável.

## API/IDL (bind.kind) — contrato mínimo
O Engine precisa suportar (via IDL router):
- `job.request` (create):
  - valida `params` contra `JobSpec.params_schema`
  - aplica gates determinísticos para `endpoint_sig`
  - se `approval_required`: cria `approval_id`, marca job como `pending_approval`
  - se `safe`: pode marcar como `enqueued` e escrever outbox imediatamente (decisão determinística do bundle)
- `job.enqueue`:
  - só permitido se job estiver `approved` (ou se `safe`/policy permitir)
  - escreve arquivo no outbox (instituição/dept)
  - emite evento no ledger (ex.: `JOB_ENQUEUED`)
- `job.get`:
  - retorna `state`, timestamps, `result_json`/`artifacts` (quando houver)

## Payload de outbox (neutro e estável)
Formato recomendado (JSON):
- `job_id` (string uuid)
- `institution_id` (string uuid)
- `dept_id` (string|null)
- `job_type` (string, vindo do bundle; ex.: `file.list`)
- `params` (objeto)
- `requested_by` (actor_id)
- `requested_at` (ISO)
- `idempotency_key` (opcional; ou usar job_id como idempotency)

## Resultado (runtime → engine)
O runtime reporta via `POST /runtime/jobs/{job_id}/report` (já existe hoje). O Engine deve:
- validar que job existe e pertence à instituição (isolamento multi-tenant)
- persistir `result_json` (pequeno) e `artifacts` (opcional) no JobStore
- emitir evento idempotente no ledger (ex.: `RUNTIME_JOB_REPORTED`)

## DoD (verificável)
- `curl` consegue:
  - criar job (request)
  - ver job (get)
  - após runtime reportar, ver `result_json` no job.get e evento no ledger
- Testes unitários:
  - isolamento por `institution_id` (job A não acessível por instituição B)
  - idempotência de report
  - approval requerido bloqueia enqueue

