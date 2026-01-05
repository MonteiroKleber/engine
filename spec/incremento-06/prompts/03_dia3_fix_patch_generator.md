# Prompt — Dia 3: Fix Patch Generator (patches focais)

Implemente o Dia 3 da Semana 8.

Criar:
- `/home/bazari/engine/fix_loop/fix_patch_generator.py`

Entrada:
- error_class
- failing_file
- context (trecho do erro + IR + OAS)

Saída:
- 1 patch mínimo, preferencialmente:
  - adicionar import
  - corrigir tipo
  - ajustar annotation
  - alinhar DTO com OpenAPI
  - ajustar client TS

Proibido:
- reescrever arquivo inteiro
- criar novas entidades
- mudar contrato

Critério de aceite:
- Patch pequeno.
- Patch associado a erro específico.
