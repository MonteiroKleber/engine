# Gaps — Migração 05 (Onboarding + ISE IDL-ready)

## Resolvido (hard gates)

### GAP-05.1 — Onboarding aceitava template sem operations em IDL mode
- **Correção:** gate “IDL-ready template” em `src/engine/console/bundle_generator.py`.
- **Resultado esperado:** em `ENGINE_API_MODE=idl`, falha determinística com `MIGRATION_MISSING_OPERATIONS` e sem deixar lixo no data root.

### GAP-05.2 — ISE podia gerar bundle sem `source_idl_sha256`
- **Correção:** falha determinística no compile quando IRCS não tem `source_idl_sha256`.
- **Error code:** `ISE_SOURCE_IDL_SHA256_MISSING` (em `src/engine/ise/errors.py`).

## Ainda aberto (melhorias futuras)

### GAP-05.A — ISE não embute `source.idl` físico no bundle (apenas o hash)
- Não é bloqueador do modo IDL (âncora existe via `source_idl_sha256`), mas reduz auditabilidade “self-contained”.
- Próximo passo recomendado: quando houver suporte, escrever `source.idl` no bundle gerado pelo ISE e referenciar no manifest como `required:false`.

