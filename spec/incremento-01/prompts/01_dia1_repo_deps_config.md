# Prompt — Dia 1: Repo + deps + config

Implemente o Dia 1 da Semana 3 criando o repositório em `/home/bazari/engine` com **EXATAMENTE** esta árvore (sem arquivos extras):

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

Crie `requirements.txt` com versões travadas:
- pydantic==2.6.4
- pydantic-settings==2.2.1
- jsonschema==4.21.1
- PyYAML==6.0.1
- rich==13.7.1
- python-dotenv==1.0.1
- pytest==8.0.2

Crie `config/engine.yaml` com campos obrigatórios:
- store_root: ./store_data
- project_default_language: pt-BR
- intake.max_questions_per_round: 7
- intake.blueprint_confidence_threshold: 0.85

Regras:
- Não adicionar SDK de LLM.
- `llm/client.py` deve ter interface + mock.

Aceite:
- árvore idêntica
- requirements travado
- config com os campos obrigatórios.
