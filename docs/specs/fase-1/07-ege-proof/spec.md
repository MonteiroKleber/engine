# Etapa 07 — EGE, Rollback/SAFE_MODE e Prova Offline

Objetivo
- Fechar o MVP com governança de evolução (EGE), contenção automática e prova offline auditável.

Decisões já fixadas (Fase 1)
- Bundle canônico no runtime usa `bundle.manifest.json` no formato do loader: `{name, version, description, contracts:[{file, sha256, required}]}`.
- Contratos institucionais mínimos são obrigatórios e devem estar `required=true` no manifest:
  - `policies.json`, `mandates.json`, `autonomy.json`
- “Prova offline” não pode depender de execução do runtime nem de DB mutável.

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

Requisitos específicos de prova offline (MVP)
- `bundle.manifest.json` deve permitir verificação offline de integridade por SHA256 de cada contrato listado.
- `contract_ledger.json` não pode ser placeholder vazio. Deve, no mínimo, conter:
  - `manifest_hash` (ou hash equivalente do manifest/bundle)
  - `idl_hash` (hash do IDL fonte usado na compilação)
  - lista de contratos com hashes de conteúdo
  - carimbo de tempo UTC
- `trace.json` deve existir para runs/deploys governados e registrar:
  - inputs relevantes, decisões/gates, artefatos gerados e referências (hashes/paths)
  - motivo de bloqueio quando houver NEEDS_ANSWERS, drift, freeze, emergency ou falha

Definition of Done (Etapa 07)
- Checklist final do MVP preenchida com evidências.
- Prova offline demonstrável com os artefatos mínimos.
