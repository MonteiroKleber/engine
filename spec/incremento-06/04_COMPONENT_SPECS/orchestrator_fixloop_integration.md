# orchestrator/engine.py — Integração total do Fix Loop

## Objetivo
Integrar o Fix Loop ao fluxo real de geração e build.

## Fluxo final
1) Gerar repo
2) Gerar patches iniciais
3) Apply patches
4) BuildValidator
5) Se falhar: chamar FixLoopAgent
6) Repetir até:
   - sucesso
   - ou erro fatal
   - ou max tentativas atingido

## Run log (novo)
- `fix_attempts`
- `fixes_applied[]`
- `final_status`

## Critério de aceite (Dia 6)
- Build quebrado → corrigido automaticamente (casos simples).
