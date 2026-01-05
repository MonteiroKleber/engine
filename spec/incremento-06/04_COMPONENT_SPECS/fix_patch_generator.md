# fix_loop/fix_patch_generator.py — Fix Patch Generator

## Objetivo
Gerar 1 patch mínimo e focal para uma classe de erro.

## Entrada
- `error_class`
- `failing_file`
- `context` (trecho do erro + IR + OAS)

## Saída
- 1 patch mínimo (preferencialmente):
  - adicionar import
  - corrigir tipo
  - ajustar annotation
  - alinhar DTO com OpenAPI
  - ajustar client TS

## Proibido
- reescrever arquivo inteiro
- criar novas entidades
- mudar contrato (OAS/RBAC)

## Critério de aceite (Dia 3)
- Patch pequeno.
- Patch associado a erro específico.
