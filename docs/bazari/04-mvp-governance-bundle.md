# Bazari — MVP Governance Bundle

Este documento descreve o escopo inicial do bundle Bazari (governança de moderação para social + chat).

Nota: este arquivo foi restaurado após uma limpeza de untracked; ajuste/complete conforme necessário.

## Objetivo
- Governar ações sensíveis (reports/blocks/moderation actions) via engine em `prod/strict/idl`.
- Data plane (posts/mensagens) permanece no app Bazari; o engine governa o control plane com auditoria.

## Fases
- Fase 01: CRUD + list via read + delete mínimo (ChatBlock)
- Fase 02: transitions (workflows)
- Fase 03: approvals genéricos (ModerationAction)

