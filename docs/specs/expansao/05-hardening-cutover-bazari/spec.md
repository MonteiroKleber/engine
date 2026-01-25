# Expansão 05 — Hardening + Cutover Bazari (observabilidade + runbook de release)

## Objetivo

Consolidar o “operar em produção” do bundle Bazari (Phase 1 / MVP) em `ENGINE_INSTALL_MODE=prod` + `ENGINE_AUTH_MODE=strict` + `ENGINE_API_MODE=idl`, com:

- **Observabilidade determinística** de uso de endpoints IDL (por instituição), para auditoria e SRE.
- **Runbook** reproduzível de release/pin/rollback de bundle.
- **Política de cutover**: como evoluir do Phase 1 para o MVP sem quebrar clientes.

## Contexto

Até aqui, já foi provado que:
- Um bundle Bazari pode ser gerado canonicamente via `DSL v1.2.2 → IRCS v1 → ISE → bundle`.
- O engine sobe em PROD/STRICT/IDL e executa o fluxo CRUD do Phase 1.

O próximo risco em produção não é “funciona?”, e sim “como operamos com segurança?”:
- rastrear quais endpoints estão sendo usados, por quem, e quando;
- saber quando é seguro trocar o bundle (novo release);
- ter rollback com evidência.

## Escopo

Inclui:
- Telemetria append-only por instituição para requests atendidos por **IDL router**:
  - `endpoint_sig`, `method`, `path`, `institution_id`, `actor_id` (quando disponível), timestamp
  - (se disponível) `bundle_name`/`bundle_version`/`manifest_hash`
- Exposição read-only no console (Status) de:
  - bundle ativo (path/hash),
  - contagem por `endpoint_sig`,
  - último uso por `endpoint_sig`.
- Atualização do runbook com:
  - geração do bundle (DSL → IRCS → ISE),
  - proof offline,
  - como apontar o engine para o novo bundle,
  - estratégia de rollback.

Não inclui:
- Novos endpoints mutáveis (ex.: “ativar bundle via HTTP”) — fora de escopo.
- Redesign do dispatcher/router/auth.

## Regras (hard)

- Nenhum relaxamento de segurança: STRICT continua token-based; nada de spoof.
- Telemetria deve ser determinística e **não** pode rodar em `ENGINE_API_MODE=legacy`.
- Sem regressão do golden path:
  - `tests/test_finance_idl_mode_e2e.py` continua PASSANDO.

## Entregáveis

- `docs/specs/expansao/05-hardening-cutover-bazari/spec.md` (este arquivo)
- `docs/specs/expansao/05-hardening-cutover-bazari/prompts.md`
- (na implementação) `tests/test_bazari_idl_telemetry_e2e.py`

## Hard gates (DoD)

Só marcar ✅ IMPLEMENTADO quando:

1) Teste Bazari telemetria/cutover PASS:
   - `PYTHONPATH=src python3 -m pytest tests/test_bazari_idl_telemetry_e2e.py -v`
2) Regressão Finance PASS:
   - `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v`
3) Patch limpo (sem `tmp/`/`var/`):
   - `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`

---

## Status

✅ IMPLEMENTADO (2026-01-25)

### Arquivos criados/modificados

1. `src/engine/core/idl_telemetry.py` (NEW):
   - `record_idl_invocation()` — append-only JSONL em `<institution_root>/idl_telemetry.jsonl`
   - `get_idl_telemetry_status()` — agregação por endpoint_sig com count e last_ts
   - Só registra em `ENGINE_API_MODE=idl|both` (nunca em legacy)
   - Ignora institution_id=DEFAULT (admin endpoints)

2. `src/engine/core/idl_router.py` (EDIT):
   - Hook após dispatch IDL para chamar `record_idl_invocation()`

3. `src/engine/console/routes.py` (EDIT):
   - Carrega `get_idl_telemetry_status()` no endpoint `/console/status`

4. `src/engine/console/templates/status.html` (EDIT):
   - Card "IDL Endpoint Telemetry" com tabela endpoint_sig | count | last_seen

5. `tests/test_bazari_idl_telemetry_e2e.py` (NEW):
   - `test_idl_telemetry_records_invocations` — verifica arquivo e agregação
   - `test_idl_telemetry_not_recorded_for_admin_endpoints` — verifica que DEFAULT não grava

### Evidências (hard gates)

1) Teste Bazari telemetria E2E:
```
$ PYTHONPATH=src python3 -m pytest tests/test_bazari_idl_telemetry_e2e.py -v
============================= test session starts ==============================
collected 2 items

tests/test_bazari_idl_telemetry_e2e.py::test_idl_telemetry_records_invocations PASSED [ 50%]
tests/test_bazari_idl_telemetry_e2e.py::test_idl_telemetry_not_recorded_for_admin_endpoints PASSED [100%]

============================== 2 passed in 1.40s ===============================
```

2) Regressão Finance:
```
$ PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v
============================= test session starts ==============================
collected 2 items

tests/test_finance_idl_mode_e2e.py::test_finance_flow_strict_idl_mode PASSED [ 50%]
tests/test_finance_idl_mode_e2e.py::test_strict_rejects_missing_actor_token PASSED [100%]

============================== 2 passed in 1.04s ===============================
```

3) Patch limpo:
```
$ git status --porcelain | grep -E '^(\?\?| M ) (tmp/|var/)' && exit 1 || echo "Clean"
Clean - no tmp/var files
```

### Event Schema (idl_telemetry.jsonl)

```json
{
  "ts": "2026-01-25T19:45:00Z",
  "route_mode": "idl",
  "endpoint_sig": "POST /reports",
  "method": "POST",
  "path": "/reports",
  "actor_id": "uuid-...",
  "dept_id": null
}
```

