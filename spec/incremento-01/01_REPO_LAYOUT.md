# Estrutura do repositório e convenções

## Árvore obrigatória (exata)
Aplicar **exatamente** esta árvore em `/home/bazari/engine`:

/home/bazari/engine/
├── main.py
├── config/engine.yaml
├── orchestrator/
│   ├── engine.py
│   ├── state_machine.py
│   └── execution_context.py
├── intake/
│   ├── normalizer.py
│   ├── blueprint_classifier.py
│   └── req_analyst.py
├── schemas/
│   ├── srs.schema.json
│   ├── blueprint.schema.json
├── validators/
│   ├── srs_validator.py
│   └── policy_validator.py
├── store/
│   ├── artifacts_store.py
│   └── fs_layout.md
├── llm/
│   ├── client.py
│   └── prompts.py
└── tests/
   ├── test_srs_schema.py
   └── test_intake_flow.py

## Artifact Store (layout fixo)
Raiz configurável: `store_root` (default `./store_data`).

Layout:
- `store_data/`
  - `{project_name}/`
    - `SRS/`
      - `v1.json`
      - `v2.json`
    - `logs/`
    - `runs/`
      - `{execution_id}.json`

### Convenções
- `kind` inicial usado no incremento: `SRS`.
- Versionamento sequencial: `v1`, `v2`, ... (sem buracos).
- Run log: **um arquivo JSON por execução** em `runs/{execution_id}.json`.

## Contratos (alto nível)
- `engine.run(project, raw_text) -> RunResult`.
- `RunResult` deve conter pelo menos: `execution_id`, `project`, `blueprint`, `srs_validation` e informações de persistência (versão salva, paths).
