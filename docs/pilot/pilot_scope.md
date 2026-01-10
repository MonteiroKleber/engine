# Pilot Scope - Sistema de Atendimento ao Cliente

## Pilot Identifier
- **Pilot ID**: `PILOT-2026-001`
- **Execution Date**: 2026-01-08
- **Executor**: Bazari Engine Validation Team

## System Description

### Domain: Customer Service Management
A realistic CRUD + API system for managing customer service tickets in a financial services context.

### Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| **Ticket** | Customer service request | id, customer_id, subject, status, priority, created_at |
| **Customer** | Customer profile | id, name, email, phone, tier |
| **Agent** | Service agent | id, name, department, skills |
| **Resolution** | Ticket resolution record | id, ticket_id, agent_id, resolution_text, resolved_at |

### Use Cases

| Use Case | Description | Actors |
|----------|-------------|--------|
| **CreateTicket** | Open new support ticket | Customer, System |
| **AssignTicket** | Assign ticket to agent | System, Manager |
| **ResolveTicket** | Mark ticket as resolved | Agent |
| **EscalateTicket** | Escalate to higher tier | Agent, System |
| **ListTickets** | Query tickets with filters | Agent, Manager |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /tickets | Create new ticket |
| GET | /tickets/{id} | Get ticket by ID |
| PUT | /tickets/{id}/assign | Assign to agent |
| PUT | /tickets/{id}/resolve | Resolve ticket |
| PUT | /tickets/{id}/escalate | Escalate ticket |
| GET | /tickets | List tickets with filters |

## Pilot Objectives

### Episode A - Initial Generation
1. Generate complete system from IDL specification
2. Validate all governance gates pass
3. Obtain explicit human approval
4. Execute release with full audit trail

### Episode B - Governed Change
1. Add new field `sla_deadline` to Ticket entity
2. Add new use case `CheckSLABreach`
3. Validate change governance (Impact Gate)
4. Obtain approval for change
5. Execute release maintaining audit chain

## Success Criteria

- [ ] Episode A completes with `release_ok: true`
- [ ] Episode B links to Episode A via `previous_episode_id`
- [ ] Both episodes have valid `episode_root_hash_sha256`
- [ ] AuditPack ZIP verifies offline with matching hashes
- [ ] No governance gates bypassed
- [ ] All artifacts traceable in ContractLedger

## Constraints

- **No shortcuts**: Every gate must pass legitimately
- **No manual modifications**: All changes via engine pipeline
- **Full traceability**: Every artifact logged
- **Explicit approval**: Human approval registered in RunLog
