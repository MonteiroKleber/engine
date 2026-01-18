# Etapa 02 — IDL Canônica e Artefatos

Objetivo
- Definir e fixar o que é **IDL canônica** no MVP e quais artefatos são obrigatórios para prova e determinismo.

Escopo
- Schemas e normalização.
- Hashing determinístico.
- Bundle manifest e trace.

Entradas
- Schemas/validadores existentes no engine.
- Bundles existentes (ex.: finance pilot) para validar consistência.

Saídas (artefatos)
- `docs/specs/fase-1/02-idl-artifacts/idl-v1.md`:
  - quais documentos compõem a IDL v1.x no MVP (ex.: `policies.json`, `mandates.json`, `autonomy.json`, `institution_config`, etc.)
  - regras de normalização (ordem de chaves, encoding, final newline, timezone, RNG proibido)
  - política de versionamento (semver)
- `docs/specs/fase-1/02-idl-artifacts/canonical-artifacts.md`:
  - lista de artefatos necessários para auditoria offline
  - formato e local de persistência por deploy/run

Decision points (devem ser resolvidos aqui)
- Default quando faltar contrato: **default-deny** (recomendado) vs default-allow.
  - Se optar por default-deny: bundle inválido quando faltar `policies/mandates/autonomy`.

Regras
- “Draft” não é executável.
- “Canonical” é validada, normalizada e hashada.
- Build/deploy devem ser determinísticos com os mesmos inputs.

Definition of Done (Etapa 02)
- Documento `idl-v1.md` define o mínimo canônico do MVP.
- Documento `canonical-artifacts.md` define prova offline mínima, sem runtime.

