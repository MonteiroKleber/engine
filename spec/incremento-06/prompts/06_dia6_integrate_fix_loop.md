# Prompt — Dia 6: Integração total do Fix Loop no Engine

Implemente o Dia 6 da Semana 8.

Atualizar:
- `/home/bazari/engine/orchestrator/engine.py`

Fluxo final:
- Gerar repo
- Gerar patches iniciais
- Apply patches
- BuildValidator
- Se falhar: chamar FixLoopAgent
- Repetir até sucesso ou erro fatal

Run log agora inclui:
- `fix_attempts`
- `fixes_applied[]`
- `final_status`

Critério de aceite:
- Build quebrado → corrigido automaticamente (casos simples).
