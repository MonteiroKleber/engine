# Bazari LLM Agent (Claude) — testes sem provisionamento

Este runner usa **Claude (Anthropic)** como “cérebro” para escolher as chamadas e validar o comportamento do Engine.

Ele **não cria tokens** (sem provisionamento). Você fornece tokens prontos via env.

## Requisitos

- Engine rodando (ex.: `http://127.0.0.1:8001`)
- `ANTHROPIC_API_KEY` configurada
- `INSTITUTION_ID` e tokens STRICT:
  - `USER_TOKEN`
  - `MOD_TOKEN`
  - `TSM_TOKEN`
  - `ADMIN_TOKEN`

## Setup rápido

Crie `docs/bazari/bazari_llm.env` (não commitar):

```bash
ENGINE_BASE_URL="http://127.0.0.1:8001"
INSTITUTION_ID="d9c54363-2ae6-416e-9339-4f64dbeb6acd"

USER_TOKEN="..."
MOD_TOKEN="..."
TSM_TOKEN="..."
ADMIN_TOKEN="..."

ANTHROPIC_API_KEY="..."
# opcional:
CLAUDE_MODEL="claude-sonnet-4-5"
```

Carregar:

```bash
set -a; source docs/bazari/bazari_llm.env; set +a
```

## Rodar

Happy path:

```bash
PYTHONPATH=src python3 docs/bazari/bazari_llm_agent.py run --scenario happy
```

SoD (valida separação de deveres com proposer == decider):

```bash
PYTHONPATH=src python3 docs/bazari/bazari_llm_agent.py run --scenario sod_strict --max-steps 30 --max-requests 60
```

Todos:

```bash
PYTHONPATH=src python3 docs/bazari/bazari_llm_agent.py run --scenario all
```

## Logs

O runner salva um JSONL com cada passo em:

- `~/.local/state/libervia_llm_runs/` (ou `XDG_STATE_HOME` se definido)
