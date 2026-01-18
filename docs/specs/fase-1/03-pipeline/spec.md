# Etapa 03 — Pipeline NL → Canonical IDL → Bundle

Objetivo
- Garantir que o pipeline seja **governado** e tenha separações rígidas:
  - NL → SIR
  - SIR → Draft IDL (não executável)
  - Gap detection → NEEDS_ANSWERS
  - Answers (humano) → Canonical IDL
  - Canonical IDL → Bundle determinístico

Decisão oficial (MVP) — Bundle canônico
- O formato canônico de `bundle.manifest.json` no MVP é o **formato consumido pelo loader** (runtime), conforme `bundles/finance-pilot/bundle.manifest.json`:
  - `{ name, version, description, contracts: [{file, sha256, required}] }`
- O ISE compiler deve emitir `bundle.manifest.json` **nesse formato**, para que o output do pipeline seja carregável pelo runtime sem adaptação manual.
- Campos extras podem existir, mas o loader deve continuar conseguindo carregar apenas com `contracts[]`.

Escopo
- Orquestração e estados do pipeline.
- Persistência de `trace.json` por run.
- Export determinístico (zip) e diff entre versões.
- Compatibilidade ISE → loader:
  - bundles gerados pelo ISE devem subir ACTIVE no runtime (exceto quando houver violação institucional intencional).

Regras
- Sem auto-fix silencioso.
- Se houver gaps, o estado deve ser `NEEDS_ANSWERS` e bloquear build/deploy.
- Bundle emitido deve incluir manifest com hashes (loader-format) e rastreabilidade mínima para a IDL canônica.
- Contratos institucionais mínimos (`policies.json`, `mandates.json`, `autonomy.json`) são obrigatórios por decisão do MVP; ausência deve resultar em bundle inválido (SAFE_MODE no runtime).

Determinismo (MVP)
- O mínimo obrigatório é determinismo dos hashes de contratos no manifest (mesmo conteúdo → mesmo sha256).
- Campos variáveis (ex.: timestamp) devem ser:
  - ou omitidos no MVP,
  - ou controlados por variável de ambiente (ex.: `SOURCE_DATE_EPOCH`/`ENGINE_BUILD_TIMESTAMP`) para builds reproduzíveis em CI quando necessário.

Saídas (artefatos)
- `docs/specs/fase-1/03-pipeline/states.md` com estados e transições.
- `docs/specs/fase-1/03-pipeline/trace-contract.md` com o mínimo do `trace.json`.

Definition of Done (Etapa 03)
- Estados e bloqueios documentados com clareza.
- Trace mínimo definido e ligado ao bundle/deploy.
- Um bundle gerado pelo ISE (via pipeline) é carregável pelo loader sem intervenção manual (manifest compatível).
