# Fase 1 (MVP EDAP) — Plano Linear

Objetivo da Fase 1: entregar o **MVP DONE** conforme Definition of Done, com foco em **governança determinística**, **prova offline**, **multi-instituição real** e **1 departamento canônico (Finance)**.

Princípios (não negociáveis)
- Contrato antes de código.
- Decisão fora da execução.
- Determinismo antes de automação.
- IA como assistente, nunca como autoridade.
- Nada roda fora de mandato, policy e gates explícitos.

Escopo da Fase 1 (sequência oficial)
1) Baseline e Gap Report (contra DoD)
2) IDL canônica e artefatos (normalização, hash, manifest, trace)
3) Pipeline NL → Canonical IDL → Bundle (com NEEDS_ANSWERS e bloqueios)
4) Runtime gates (policy, mandates, approvals, SoD, invariants, freeze, emergency, drift)
5) Finance template “golden” end-to-end
6) Multi-instituição e segurança administrativa (keys, config v1.3, isolamento)
7) EGE mínimo + rollback/safe mode + prova offline + checklist final do MVP

Decision points (precisam ser decididos e depois “fixados”)
- Default de execução sem contratos: **default-deny** (recomendado) vs default-allow.
  - Para cumprir “nenhuma execução fora de mandato”, o caminho consistente é **default-deny** quando `mandates/policies/autonomy` estiverem ausentes ou inválidos no bundle.
- O que é canônico: “o que o engine aceita e executa”, mas com artefatos e schemas versionados.

Artefatos canônicos da Fase 1 (mínimo)
- Bundle determinístico com `bundle.manifest.json` e hashes.
- `contract_ledger.json` (ou equivalente) com hashes/contratos.
- `audit_ledger.jsonl` append-only com hash-chain.
- `trace.json` persistido por run/deploy (para prova offline).

Critério final (MVP DONE)
O MVP está DONE quando uma instituição consegue operar o departamento Finance em produção, com autonomia controlada, reversível, auditável offline e bloqueável instantaneamente, sem depender de confiança em pessoas ou em IA.

