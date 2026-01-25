# Prompts — Migração 02 (Finance Reference — IDL)

## PROMPT 02.x (Histórico resumido)
Esta fase teve várias iterações para evitar falsos positivos, principalmente:
- Proof offline determinístico (hashes coerentes no ledger/manifest).
- E2E STRICT real (sem spoof) usando `X-Actor-Token`.
- IDL router respeitando `ENGINE_AUTH_MODE=strict` (reuso do `get_actor_context()`).

