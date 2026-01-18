# Etapa 04 — Runtime Gates (Enforcement)

Objetivo
- Garantir que o runtime bloqueie execução sempre que qualquer gate falhar, com erro determinístico e evento no ledger.

Gates obrigatórios (MVP)
- Policies (pre e post)
- Mandates (autonomia revogável)
- Approvals
- Separation of Duties (SoD)
- Invariants (pre-commit)
- Freeze institucional
- Emergency stop
- Drift enforcement (EGE)

Decisão oficial (MVP) — Contratos mínimos e SAFE_MODE
- `policies.json`, `mandates.json`, `autonomy.json` são contratos institucionais mínimos obrigatórios.
- Ausência de qualquer um deles no bundle executável deve resultar em **bundle inválido** e **SAFE_MODE** no boot (enforcement via `bundle.manifest.json` e loader).

Regras
- Nenhum endpoint mutável sem:
  - institution context
  - dept context
  - gates aplicados
- Toda decisão de allow/deny deve registrar evento no ledger.
- Erros devem ser determinísticos, com `case_id/request_id/actor_id` quando aplicável.

Semântica canônica (MVP) — gates institucionais
- Policies:
  - Contrato pode ser vazio (`policies: []`) e isso significa “sem regras adicionais”, não SAFE_MODE.
  - Se uma policy aplicável falhar → deny (`POLICY_DENIED`).
- Mandates:
  - “Nenhuma execução fora de mandato” significa: se `mandates.json` existe mas **não há mandate aplicável** ao `(endpoint_sig, phase)` → deny (`MANDATE_DENIED`).
  - Mandate válido e aplicável pode conceder; caso contrário nega.
- Autonomy:
  - Se `autonomy.json` existe mas **não há regra aplicável** ao `(endpoint_sig, phase)` → deny (`AUTONOMY_INSUFFICIENT`).
  - Se há regra aplicável: allow apenas se `current_level >= required_level`.

Saídas (artefatos)
- `docs/specs/fase-1/04-runtime-gates/gates-matrix.md`
  - para cada endpoint mutável: quais gates são aplicados e em que ordem.
- `docs/specs/fase-1/04-runtime-gates/errors.md`
  - códigos e payloads de erro esperados para falhas de gate.

Definition of Done (Etapa 04)
- Matriz de gates completa para o departamento Finance.
- Semântica canônica implementada e coberta por testes:
  - sem mandate aplicável → deny
  - sem autonomy rule aplicável → deny
  - políticas/invariants/sod/approvals continuam bloqueantes como antes
  - eventos allow/deny emitidos no ledger para policy/mandate/autonomy
