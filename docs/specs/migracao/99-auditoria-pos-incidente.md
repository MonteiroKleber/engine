# Auditoria Pós-Incidente (Claude Code) — Estado Atual vs `docs/specs/`

Este documento registra as **inconsistências encontradas** após deleções/reverts e o que ainda falta para voltar ao estado **auditável (“como estava” ou melhor)**.

## Situação Atual (verificável)

- Bundles migrados com Proof offline PASS:
  - `PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot`
  - `PYTHONPATH=src python3 -m engine.proof verify bundles/acme_core`
  - `PYTHONPATH=src python3 -m engine.proof verify bundles/multi-pilot`
- Testes hard-gate restaurados (arquivos existem):
  - `tests/test_finance_idl_mode_e2e.py`
  - `tests/test_acme_core_idl_mode_e2e.py`
  - `tests/test_multi_pilot_idl_mode_e2e.py`
  - `tests/test_onboarding_idl_ready.py`
  - `tests/test_ise_idl_ready.py`
  - `tests/test_prod_strict_idl_boot.py`
  - `tests/test_observe_actors.py` (API `/v1/observe/actors`)

## Inconsistências / Gaps Abertos

### GAP-01 — `map.md`/`gaps.md` placeholders (perda de conteúdo)
Vários arquivos de `map.md` e `gaps.md` estavam praticamente vazios (placeholders), e não refletiam o nível de evidência que existia antes.

**Ação:** reescrever cada `map.md` e `gaps.md` com:
- paths + símbolos (funções/módulos)
- outputs literais dos hard gates
- decisões (por que foi feito assim)

**Status:** em andamento (este arquivo guia a auditoria; as fases 03–08 foram re-hidratadas com conteúdo mínimo + comandos).

### GAP-02 — Duplicidade de IDL Bazari (risco de fonte errada)
Existem dois arquivos “fonte” do Bazari:
- IDL canônico do Bazari: `docs/bazari/idl/bazari-mvp.idl`
  - Nota: o arquivo antigo `docs/bazari-mvp.idl` não deve mais ser usado (evita duplicação/ambiguidade).

**Ação:** escolher um caminho canônico e remover/arquivar o outro com nota no README.

### GAP-03 — DoD ainda não revalidado “end-to-end”
Mesmo com testes/bundles restaurados, falta um “hard gate” consolidado único (um comando) para validar tudo que é *criticamente* parte da migração, e registrar o output literal na documentação.

**Ação:** criar um checklist/command set (ex.: `make verify-migration`) ou documentar comando padrão no `README.md` da migração.

### GAP-04 — Endpoint de observabilidade via API ausente
O endpoint usado na operação (`/v1/observe/actors`) não estava presente no app (router não registrado).

**Correção:** reintroduzido `src/engine/api/observe.py` e registrado em `src/engine/api/server.py`.  
**Teste:** `python -m pytest tests/test_observe_actors.py -v`.

## Validação Recomendada (rodar e colar outputs)

```bash
PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot
PYTHONPATH=src python3 -m engine.proof verify bundles/acme_core
PYTHONPATH=src python3 -m engine.proof verify bundles/multi-pilot

PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v
PYTHONPATH=src python3 -m pytest tests/test_acme_core_idl_mode_e2e.py -v
PYTHONPATH=src python3 -m pytest tests/test_multi_pilot_idl_mode_e2e.py -v
PYTHONPATH=src python3 -m pytest tests/test_onboarding_idl_ready.py -v
PYTHONPATH=src python3 -m pytest tests/test_ise_idl_ready.py -v
PYTHONPATH=src python3 -m pytest tests/test_prod_strict_idl_boot.py -v
```
