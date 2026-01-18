# Etapa 05 — Finance Template “Golden”

Objetivo
- Fixar o **primeiro departamento canônico** (Finance) como referência do MVP.

Escopo (mínimo)
- Endpoint: `POST /finance/expenses`
- Fluxo: create → approval request → approve/reject → commit/reject
- Gates: policies, mandates, approvals, SoD, invariants, freeze/emergency, drift
- State store versionado
- Ledger com eventos mínimos (institutional e de caso)

Saídas (artefatos)
- `docs/specs/fase-1/05-finance-template/finance-contract.md`
  - entidades, invariants, approvals, SoD e políticas mínimas.
- `docs/specs/fase-1/05-finance-template/finance-bundle.md`
  - quais arquivos compõem o bundle Finance e suas versões.

Regras
- Finance é o “golden reference”: outros departamentos derivam dele.
- Mudança em Finance implica mudança correspondente em gates/ledger/proof.

Definition of Done (Etapa 05)
- Bundle Finance completo e canônico (inclui contratos mínimos definidos na Etapa 02/04).
- Testes E2E cobrindo create → approve/reject → commit/reject.

