# orchestrator/engine.py — Modo release (texto → rodando)

## Objetivo
Executar o modo release com ordem fixa e rollback/teardown em falhas.

## Ordem fixa (modo release)
1) Gera repo
2) Aplica patches
3) BuildValidator
4) `docker compose up -d`
5) Smoke tests

## Falha
- Em qualquer falha após subir docker:
  - `docker compose down`
  - rollback do repo para o estado anterior

## Sucesso
- Sistema permanece rodando.
- Emitir release bundle.

## Critério de aceite (Dia 4)
- Uma execução gera sistema rodando.
