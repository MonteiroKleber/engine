# Prompt — Dia 5: Patch Generator v1

Implemente o Dia 5 da Semana 7.

Criar `/home/bazari/engine/compilers/patch_generator_v1.py`.

Entrada:
- PLAN
- IR
- OAS
- RBAC

Saída:
- Lista de patches
- Cada patch aponta para `/home/bazari/generated/<project>/...`

Regras:
- Mesma entrada → mesmos patches.
- Nenhum patch fora de `generated/`.

Critério de aceite:
- Determinístico.
- Nenhum patch fora de `generated/`.
