# Etapa 07 — EGE, Rollback/SAFE_MODE e Prova Offline

Objetivo
- Fechar o MVP com governança de evolução (EGE), contenção automática e prova offline auditável.

Escopo (mínimo)
- Drift detection e enforcement (bloqueio quando drift ACTIVE).
- Pin governado após deploy (ou mecanismo equivalente acordado).
- Rollback automático em falha de deploy.
- SAFE_MODE em:
  - bundle inválido
  - ledger corrompido
  - schema inválido
- Prova offline: com apenas
  - `audit_ledger.jsonl`
  - `bundle.manifest.json`
  - `contract_ledger.json`
  - `trace.json`
  deve ser possível reconstruir:
  - o que foi decidido
  - sob quais regras
  - com quais inputs/limites
  - em qual versão institucional

Saídas (artefatos)
- `docs/specs/fase-1/07-ege-proof/proof-offline.md`
- `docs/specs/fase-1/07-ege-proof/mvp-checklist.md` (a checklist final do “DONE”)

Regras
- Nada “meio aplicado”: falhou, volta.
- Auditoria não depende de DB mutável nem do runtime rodando.

Definition of Done (Etapa 07)
- Checklist final do MVP preenchida com evidências.
- Prova offline demonstrável com os artefatos mínimos.

