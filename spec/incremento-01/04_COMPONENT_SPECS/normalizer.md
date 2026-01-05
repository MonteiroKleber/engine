# intake/normalizer.py — Especificação

## Objetivo
Aplicar limpeza determinística ao texto de entrada (sem LLM).

## Regras (determinísticas)
- `strip()` no início/fim.
- Colapsar espaços duplicados (incluindo tabs) para 1 espaço.
- Limitar tamanho máximo (20k chars); truncar preservando início.
- Converter linhas em bullets:
  - dividir por linhas
  - remover linhas vazias
  - prefixar com `- `

## Saída
- Retornar string normalizada.
