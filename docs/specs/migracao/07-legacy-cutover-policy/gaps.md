# Gaps — Migração 07 (Legacy Cutover Policy)

## Resolvido

### GAP-07.1 — Não existia telemetria determinística de uso do legacy em `both`
- **Fix:** `src/engine/core/legacy_telemetry.py` + hooks nos routers legacy.
- **Teste:** `tests/test_legacy_cutover.py` garante:
  - grava somente em `ENGINE_API_MODE=both`
  - não grava em `idl` nem em `legacy`
  - agrega contagens por endpoint_sig

### GAP-07.2 — Console sem visibilidade de “cutover status”
- **Fix:** seção read-only no status do console.

## Ainda aberto (cutover real)

### GAP-07.A — Endpoints legacy-only (sem equivalente IDL) ainda existem
- Alguns bundles têm cobertura IDL parcial (por escolha de escopo do bundle/dispatcher).
- Esses endpoints devem ser o foco do cutover: enquanto existirem, `ENGINE_API_MODE=idl` quebrará esses fluxos (404/unsupported).

### GAP-07.B — Colisão de rotas em `ENGINE_API_MODE=both`
- Em `both`, rotas IDL e legacy podem colidir em `method/path`.
- O critério de cutover deve priorizar:
  1) telemetria em endpoints legacy-only
  2) testes em `ENGINE_API_MODE=idl` (onde legacy não existe)

