# Gaps — Migração 06 (Baseline PROD/STRICT/IDL)

## Resolvido

### GAP-06.1 — Não existia smoke test cobrindo PROD/STRICT/IDL
- **Fix:** `tests/test_prod_strict_idl_boot.py` valida:
  - boot do app com lifespan
  - `/health` e console acessíveis
  - bootstrap de admin key e criação de actor tokens
  - fluxo mínimo Finance via IDL em STRICT
  - rejeição explícita de spoof (sem `X-Actor-Token`)

### GAP-06.2 — Boot blockers em produção não eram testados
- **Fix:** smoke test cobre falhas determinísticas (ex.: admin token ausente, auth mode inseguro, session secret fraco) via asserts de erro.

## Ainda aberto / observações

- Warning conhecido (não bloqueador): DeprecationWarning do Starlette `TemplateResponse` em testes de console.
- Produção: recomenda-se configurar observabilidade e logs (fora do escopo do baseline).

