# Migração 01 — Diagnóstico (Mapeamento com evidências)

Este documento mapeia os pontos do engine que controlam a migração **Legacy → IDL** e os modos de execução.

## Modos que importam

- `ENGINE_API_MODE` (legacy/idl/both)
  - Registro de rotas IDL: `src/engine/core/idl_router.py` (handler dinâmico e `register_idl_routes`)
  - Colisão legacy vs IDL (evitar em `idl`): `src/engine/api/server.py#L395` (skip routers legacy em `idl`)
- `ENGINE_AUTH_MODE` (dev/strict)
  - Resolução canônica de actor/institution: `src/engine/api/dependencies.py` (usado por IDL router)

## Boot sequence (alto nível)

- Lifespan e checks:
  - `src/engine/api/server.py` (lifespan) executa:
    - ledger verify
    - load bundle
    - preflight
    - migration checks (quando `ENGINE_API_MODE != legacy`)
    - register IDL routes (quando `ENGINE_API_MODE != legacy`)

## Registro IDL e auth STRICT (fato pós-migração)

O handler do IDL router usa o caminho canônico de auth (STRICT funciona; DEV spoof também continua existindo em outros routers).

Evidência:
- `src/engine/core/idl_router.py`
  - `get_actor_context()` chamado no handler: linhas 179–191

## Colisão de rotas (legacy vs IDL)

Evidência:
- `src/engine/api/server.py`
  - routers legacy são incluídos apenas quando `ENGINE_API_MODE != idl`: linhas 395–401

## Bundles no repo (baseline “golden path”)

Os bundles migrados e usados como referência:
- `bundles/finance-pilot` (single-dept)
- `bundles/acme_core` (single-dept)
- `bundles/multi-pilot` (multi-dept: finance/support)

Evidência (Proof offline):
- `PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot` → PASS
- `PYTHONPATH=src python3 -m engine.proof verify bundles/acme_core` → PASS
- `PYTHONPATH=src python3 -m engine.proof verify bundles/multi-pilot` → PASS

