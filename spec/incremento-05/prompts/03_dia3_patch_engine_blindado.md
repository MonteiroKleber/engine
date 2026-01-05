# Prompt — Dia 3: Patch Engine (blindado)

Implemente o Dia 3 da Semana 7.

Local:
- `/home/bazari/engine/patch_engine/`

Regra ABSOLUTA:
- Patch Engine só pode escrever em `/home/bazari/generated/<project>/**`.

Bloqueios obrigatórios:
- Proibir tocar em `/home/bazari/engine/**`.
- Proibir tocar em `/home/bazari/templates/**`.
- Proibir path traversal (`../`).
- Proibir rewrite de arquivo inteiro (>80%).

Rollback:
- Patch inválido gera rollback imediato.

Critério de aceite:
- Patch inválido gera rollback imediato.
