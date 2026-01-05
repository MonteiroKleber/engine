# llm/client.py e llm/prompts.py — Especificação

## Objetivo
Manter apenas interface/mocks para futura integração.

## Regras
- Não adicionar dependências de SDK.
- `client.py`: definir interface mínima (ex.: `complete(prompt)`) e um mock previsível.
- `prompts.py`: conter constantes/strings (sem lógica pesada) se necessário.
