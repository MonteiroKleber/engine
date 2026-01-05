# compilers/patch_generator_v1.py — Patch Generator v1

## Objetivo
Gerar patches determinísticos a partir de:
- PLAN
- IR
- OAS
- RBAC

## Local
- `/home/bazari/engine/compilers/patch_generator_v1.py`

## Saída
- Lista de patches.
- Cada patch aponta para:
  - `/home/bazari/generated/<project>/...`

## Regras
- Mesma entrada → mesmos patches.
- Nenhum patch fora de `generated/`.

## Critério de aceite (Dia 5)
- Determinismo garantido.
- Nenhum patch fora de `generated/`.
