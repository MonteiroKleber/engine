# Definition of Done — Libervia Engine Pilot

## PT-BR

### Critérios de Aceite para Pilot

O Libervia Engine está pronto para pilot quando **todos** os critérios abaixo são atendidos:

#### 1. Funcionalidade Core
- [ ] POST /finance/expenses cria despesa e retorna 202 com `expense_id` e `approval_id`
- [ ] POST /approvals/{id}/decide com `approve` valida invariantes e comita
- [ ] POST /approvals/{id}/decide com `reject` rejeita e atualiza status
- [ ] GET /health retorna 200 em modo ACTIVE
- [ ] GET /health retorna 503 em modo SAFE_MODE com `reason_code`

#### 2. Segurança e Controle de Acesso
- [ ] RBAC bloqueia acesso sem permissão (403 FORBIDDEN)
- [ ] RBAC bloqueia acesso sem actor (401 UNAUTHORIZED)
- [ ] SoD bloqueia self-approval (409 SOD_VIOLATION)
- [ ] Invariantes bloqueiam valores inválidos (422 INVARIANT_VIOLATION)
- [ ] Rate limiting ativo (429 RATE_LIMIT_EXCEEDED após limite)
- [ ] Body size limit ativo (413 REQUEST_TOO_LARGE)
- [ ] Security headers presentes em todas as respostas

#### 3. Auditoria e Integridade
- [ ] Todos os eventos são gravados no ledger (audit_ledger.jsonl)
- [ ] Cada evento tem hash SHA-256 verificável
- [ ] Chain de hashes é verificada no boot
- [ ] Ledger corrompido entra em SAFE_MODE
- [ ] Request ID é propagado do header ao ledger

#### 4. Operações
- [ ] Bundle é validado no startup (manifest + hashes)
- [ ] Bundle inválido entra em SAFE_MODE
- [ ] State store persiste entre restarts
- [ ] Logs estruturados em JSON
- [ ] Preflight check script funciona

#### 5. Testes
- [ ] Todos os testes unitários passam
- [ ] Todos os testes de integração passam
- [ ] Cobertura de cenários de erro
- [ ] Nenhum teste pulado ou ignorado

#### 6. Documentação
- [ ] RUNBOOK com procedimentos operacionais
- [ ] EXAMPLES com fluxos de uso
- [ ] RELEASE_CHECKLIST para deploy
- [ ] README atualizado

---

## EN

### Acceptance Criteria for Pilot

Libervia Engine is pilot-ready when **all** criteria below are met:

#### 1. Core Functionality
- [ ] POST /finance/expenses creates expense and returns 202 with `expense_id` and `approval_id`
- [ ] POST /approvals/{id}/decide with `approve` validates invariants and commits
- [ ] POST /approvals/{id}/decide with `reject` rejects and updates status
- [ ] GET /health returns 200 in ACTIVE mode
- [ ] GET /health returns 503 in SAFE_MODE with `reason_code`

#### 2. Security and Access Control
- [ ] RBAC blocks access without permission (403 FORBIDDEN)
- [ ] RBAC blocks access without actor (401 UNAUTHORIZED)
- [ ] SoD blocks self-approval (409 SOD_VIOLATION)
- [ ] Invariants block invalid values (422 INVARIANT_VIOLATION)
- [ ] Rate limiting active (429 RATE_LIMIT_EXCEEDED after limit)
- [ ] Body size limit active (413 REQUEST_TOO_LARGE)
- [ ] Security headers present in all responses

#### 3. Audit and Integrity
- [ ] All events are written to ledger (audit_ledger.jsonl)
- [ ] Each event has verifiable SHA-256 hash
- [ ] Hash chain is verified at boot
- [ ] Corrupted ledger enters SAFE_MODE
- [ ] Request ID is propagated from header to ledger

#### 4. Operations
- [ ] Bundle is validated at startup (manifest + hashes)
- [ ] Invalid bundle enters SAFE_MODE
- [ ] State store persists between restarts
- [ ] Structured JSON logs
- [ ] Preflight check script works

#### 5. Tests
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Error scenario coverage
- [ ] No skipped or ignored tests

#### 6. Documentation
- [ ] RUNBOOK with operational procedures
- [ ] EXAMPLES with usage flows
- [ ] RELEASE_CHECKLIST for deploy
- [ ] README updated
