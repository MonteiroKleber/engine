# fix_loop/fix_loop_agent.py — Fix Loop Agent

## Objetivo
Executar autocorreção limitada e governada quando o build falha.

## Constantes
- `MAX_FIX_ATTEMPTS = 3`

## Fluxo fixo
Pseudo:
- `attempts = 0`
- `while attempts < MAX_FIX_ATTEMPTS:`
  - `classify_error()`
  - `generate_fix_patch()`
  - `apply_patch()`
  - `validate_build()`
  - `if success: break`
  - `attempts += 1`

## Regras absolutas
- Cada iteração:
  - 1 patch
  - 1 causa (um error_class)
- Nunca tocar fora de `/home/bazari/generated/<project>`.
- Patches passam pelas mesmas rules da Semana 7.
- Sem loops infinitos.

## Saídas (para run log)
- `fix_attempts`
- `fixes_applied[]` (uma entrada por tentativa, com `error_class` e resumo do patch)
- `final_status`

## Critério de aceite (Dia 2)
- Loop interrompe corretamente.
- Nunca entra em loop infinito.
