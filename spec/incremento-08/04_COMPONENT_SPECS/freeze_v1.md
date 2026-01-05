# Congelamento v1.0

## Objetivo
Congelar o motor como v1.0.0 com regras de evolução.

## Arquivos
- `/home/bazari/engine/VERSION` deve conter `1.0.0`.
- `/home/bazari/engine/RELEASE_NOTES.md` deve descrever:
  - features principais
  - regras de freeze

## Freeze rules
- Schemas só mudam com bump de versão.
- Templates versionados.
- Policies imutáveis (mudanças exigem bump).

## Aceite (Dia 6)
- Motor identificado como v1.0.0.
