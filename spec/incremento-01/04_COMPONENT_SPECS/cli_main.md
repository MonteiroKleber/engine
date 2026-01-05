# main.py (CLI) — Especificação

## Comando
`python main.py --project <name> --input "<texto>"`

## Comportamento
- Executa pipeline do `orchestrator/engine.py`.
- Imprime resumo do run (ok/erro, versão salva, perguntas se inválido).
- Persiste artefatos e log conforme regras.
