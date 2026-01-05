# Prompt — Dia 2: Fix Loop Agent (núcleo da autonomia)

Implemente o Dia 2 da Semana 8.

Criar:
- `/home/bazari/engine/fix_loop/fix_loop_agent.py`

Implementar fluxo fixo:
- `MAX_FIX_ATTEMPTS = 3`
- `while attempts < MAX_FIX_ATTEMPTS:`
  - classify_error()
  - generate_fix_patch()
  - apply_patch()
  - validate_build()
  - if success: break

Regras absolutas:
- Cada iteração: 1 patch, 1 causa.
- Nunca tocar fora de `/home/bazari/generated/<project>`.
- Patches passam pelas mesmas rules da Semana 7.

Critério de aceite:
- Loop interrompe corretamente.
- Nunca entra em loop infinito.
