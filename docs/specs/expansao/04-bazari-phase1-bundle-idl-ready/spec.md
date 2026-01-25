# Expansão 04 — Bundle Bazari Phase 1 “IDL-ready” + E2E em PROD/STRICT/IDL

## Objetivo

Produzir (via caminho canônico `DSL v1.2.2 → IRCS v1 → ISE → bundle`) um **primeiro bundle executável** para a instituição Bazari em `ENGINE_INSTALL_MODE=prod` + `ENGINE_AUTH_MODE=strict` + `ENGINE_API_MODE=idl`, provando:

- Proof offline PASS do bundle gerado
- Migration checks PASS no boot em IDL
- E2E via HTTP (TestClient + lifespan) cobrindo o **MVP Phase 1 (CRUD control-plane)** com ~10 endpoints

## Escopo

Inclui:
- Compilar o DSL canônico `docs/bazari/idl/bazari-phase1.idl` em um bundle temporário (em `tmp_path`) durante o teste.
- Subir o app em modo **PROD/STRICT/IDL** apontando para o bundle compilado.
- Criar instituição e bootstrap de admin key via HTTP (sem shell).
- Provisionar actor tokens e exercitar endpoints Bazari Phase 1 (CRUD).

Não inclui (fases seguintes):
- `bind.kind=transition`/`bind.kind=approval` do Bazari MVP completo (já existe runtime para isso, mas o **bundle “Phase 1”** evita complexidade de workflow no primeiro deploy).
- UI/Console para gerenciamento de bundle/release.

## Fonte de Verdade (IDL)

- DSL canônico: `docs/bazari/idl/bazari-phase1.idl`
- É proibido usar `docs/bazari-mvp.idl`/`docs/bazari-mvp.idl` como fonte na fase 04.

## Regras (hard)

- STRICT real nos testes:
  - requests usam `X-Institution-Id` + `X-Actor-Token`
  - proibido `X-Actor-Id`/`X-Actor-Roles`/`X-Tenant-Id`
- PROD real no teste (preflight ativo):
  - `ENGINE_INSTALL_MODE=prod`
  - `ENGINE_AUTH_MODE=strict`
  - `ENGINE_API_MODE=idl`
  - `ENGINE_ISE_ADMIN_TOKEN` e `ENGINE_CONSOLE_SESSION_SECRET` obrigatórios
- Sem scope creep:
  - Não alterar código do engine nesta fase; se um bug impedir o E2E, parar e abrir uma fase corretiva com allowlist.

## Entregáveis

- `docs/specs/expansao/04-bazari-phase1-bundle-idl-ready/prompts.md`
- `docs/specs/expansao/04-bazari-phase1-bundle-idl-ready/spec.md` (este arquivo)
- `tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py` (novo)

## Hard gates (DoD)

Só marcar ✅ IMPLEMENTADO quando:

1) E2E PROD/STRICT/IDL do Bazari Phase 1 PASS:
   - `PYTHONPATH=src python3 -m pytest tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py -v`
2) Regressão do golden path PASS:
   - `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v`
3) Patch limpo (sem `tmp/`/`var/`):
   - `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`

---

## Status

✅ IMPLEMENTADO (2026-01-25)

### Notas importantes

- O prefixo `/admin/*` é reservado no runtime (middleware trata como “admin endpoint” e força `institution_id=DEFAULT`), então endpoints Bazari foram padronizados para `/moderation/*` (ex.: `GET /moderation/reports`) para funcionar em STRICT.

### Evidências (hard gates)

1) Bazari Phase 1 E2E (PROD/STRICT/IDL):
```
$ PYTHONPATH=src python3 -m pytest tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py -v
========================= 1 passed, 1 warning in 1.62s =========================
```

2) Regressão Finance (STRICT/IDL):
```
$ PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v
============================== 2 passed in 1.08s ===============================
```

3) Patch limpo (sem `tmp/`/`var/`):
```
$ git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true
# (no output)
```
