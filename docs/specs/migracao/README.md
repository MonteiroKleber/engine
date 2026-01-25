# Migração (Legacy → IDL) — Documentação

Esta pasta contém o planejamento, especificações e prompts (para Claude Code) usados na migração do Libervia Engine para operar com:

- `ENGINE_API_MODE=idl` (rotas dinâmicas via `operations.json`)
- `ENGINE_AUTH_MODE=strict` (token-based, sem spoof de headers)
- `ENGINE_INSTALL_MODE=prod` (preflight hard gates)

Nota: esta documentação foi reconstruída após uma deleção acidental de arquivos não versionados. A partir de agora, **tudo aqui deve permanecer versionado** (nada importante como untracked).

## Fases

- `00-plano.md`: plano linear completo.
- `01-diagnostico/`: inventário do estado atual (bundles, rotas, checks).
- `02-finance-reference-idl-mode/`: “golden path” single-dept para IDL (finance-pilot).
- `03-acme-core-idl-mode/`: migrar `acme_core` para IDL.
- `04-multi-pilot-multi-dept-idl-mode/`: migrar `multi-pilot` (multi-dept) para IDL.
- `05-onboarding-ise-idl-ready/`: garantir que onboarding/ISE gerem bundles IDL-ready.
- `06-prod-strict-idl-baseline/`: baseline PROD/STRICT/IDL + smoke tests + runbook.
- `07-legacy-cutover-policy/`: telemetria e política de cutover do legacy.
- `08-admin-key-bootstrap/`: bootstrap one-time de admin key por instituição.

