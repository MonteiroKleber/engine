# Bazari Agents (scripts de teste)

Scripts simples (sem dependências externas) para rodar cenários E2E contra um Engine já rodando.

## Como usar

1) Crie um arquivo `docs/bazari/bazari.env` (não commite) com as variáveis:

```bash
ENGINE_BASE_URL="http://127.0.0.1:8001"
INSTITUTION_ID="d9c54363-2ae6-416e-9339-4f64dbeb6acd"

USER_TOKEN="..."
MOD_TOKEN="..."
TSM_TOKEN="..."
ADMIN_TOKEN="..."
```

2) Carregue no shell:

```bash
set -a; source docs/bazari/bazari.env; set +a
```

3) Rode um cenário:

```bash
PYTHONPATH=src python3 docs/bazari/bazari_agents.py run --scenario happy
```

Todos:

```bash
PYTHONPATH=src python3 docs/bazari/bazari_agents.py run --scenario all
```

Volume (ex.: 10 reports):

```bash
PYTHONPATH=src python3 docs/bazari/bazari_agents.py run --scenario volume --count 10
```

## Cenários

- `happy`: report → triage → action → submit → approve → apply.
- `abuse`: tenta ações proibidas (espera 403).
- `sod`: tenta self-approve (espera 409).
- `replay`: decide duas vezes (espera 409 na segunda).
- `volume`: cria/triage N reports.

