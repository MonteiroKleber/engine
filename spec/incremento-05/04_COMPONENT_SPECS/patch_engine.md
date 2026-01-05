# patch_engine/ — Patch Engine (blindado)

## Objetivo
Aplicar patches ao repo gerado com regras de segurança e rollback.

## Local
- `/home/bazari/engine/patch_engine/`

## Regra absoluta (escopo de escrita)
O Patch Engine só pode escrever em:
- `/home/bazari/generated/<project>/**`

## Bloqueios obrigatórios
- Proibir tocar em `/home/bazari/engine/**`.
- Proibir tocar em `/home/bazari/templates/**`.
- Proibir path traversal (ex.: `../`).
- Proibir rewrite de arquivo inteiro (>80% do conteúdo modificado).

## Rollback (obrigatório)
- Patch inválido ou falha ao aplicar → rollback imediato para estado anterior.
- Rollback deve restaurar todos os arquivos afetados no batch.

## Modelo de patch (recomendado)
- `path`: path absoluto do alvo (sempre sob generated)
- `type`: `create|update|delete`
- `diff` ou `patch_text`: conteúdo patch (formato a definir) OU “replace” com limite de rewrite

## Critério de aceite (Dia 3)
- Patch inválido gera rollback imediato.
