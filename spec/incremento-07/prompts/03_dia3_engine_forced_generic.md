# Prompt — Dia 3: Integração no Engine (FORCED_GENERIC)

Implemente o Dia 3 da Semana 9.

Atualizar:
- `/home/bazari/engine/orchestrator/engine.py`

Fluxo obrigatório:
- Classificador tenta identificar blueprint.
- Se não existir → FORCED_GENERIC.
- Engine registra no run log:
  - `"blueprint": "GENERIC"`

Regras:
- Nenhum caminho alternativo.
