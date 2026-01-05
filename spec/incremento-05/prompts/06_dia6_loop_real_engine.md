# Prompt — Dia 6: Loop real no Engine

Implemente o Dia 6 da Semana 7.

Atualizar `/home/bazari/engine/orchestrator/engine.py` com ordem fixa:
1) Criar repo em `/home/bazari/generated/<project>`
2) Gerar patches
3) Aplicar patches
4) Rodar build validator
5) Falhou → rollback
6) Passou → SUCCESS

Run log inclui:
- `repo_path: /home/bazari/generated/<project>`
- `patch_count`
- `build_ok`
