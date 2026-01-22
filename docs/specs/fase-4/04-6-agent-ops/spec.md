# Fase 4 — Etapa 4.6: Agent Ops / Observability mínima

**Data:** 2026-01-20  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-4/00-plano.md` (Etapa 4.6)

## Objetivo

Adicionar o mínimo necessário para operar agentes (IA ou não) com visibilidade e governança:

- visualizar ações por `actor_id`
- visualizar tentativas negadas e motivo (gate)
- ter um “registry” simples de agentes (metadados e escopo) por instituição/dept

## Escopo

Inclui
- Read model (query) para ledger por `actor_id` e por `dept_id`
- Console pages para:
  - “Agents” (lista)
  - “Agent detail” (últimas ações + negadas)
  - “Denied attempts” (filtro por gate, dept, endpoint)
- Registry simples persistido (append-only) com `agent_id/actor_id`, roles e escopo

Não inclui
- Execução autônoma de agentes
- Ferramenta de prompt/agent builder
- Scheduler/queue de jobs

## Regras não negociáveis

- Não permitir que o console vire “atalho” de execução fora de governança.
- Read-only por padrão. Se existir qualquer ação mutável, ela deve ser governada e explicitamente aprovada no spec.
- Multi-tenant: isolamento por `(institution_id, dept_id)` sempre.

## Entregas mínimas

- `docs/specs/fase-4/04-6-agent-ops/api.md`
- `docs/specs/fase-4/04-6-agent-ops/gaps.md`
- Implementação de read model + console pages + testes

## Definition of Done

- Console mostra lista de agentes e histórico por agente (com base no ledger).
- Console mostra “denied attempts” com razão determinística (gate/código).
- Testes cobrindo isolamento (duas instituições, dois depts).

