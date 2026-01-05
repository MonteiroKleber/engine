# Prompt — Dia 4: Pipeline “texto → rodando” (modo release)

Implemente o Dia 4 da Semana 10.

Atualizar:
- `/home/bazari/engine/orchestrator/engine.py`

Modo release (ordem fixa):
- Gera repo
- Aplica patches
- BuildValidator
- `docker compose up -d`
- Smoke tests

Falha:
- `docker compose down` + rollback

Sucesso:
- sistema permanece rodando

Aceite:
- Uma execução gera sistema rodando.
