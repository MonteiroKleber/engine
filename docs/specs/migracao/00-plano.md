# Plano Linear — Migração Legacy → IDL

Objetivo final: Engine operando em `prod` + `strict` + `idl` com bundles IDL-ready, runbook validado e política de cutover do legacy baseada em evidências.

## 01 — Diagnóstico
- Mapear: leitura de `ENGINE_API_MODE`, `ENGINE_AUTH_MODE`, `ENGINE_DATA_ROOT`, fluxo de boot, migration checks, IDL router, dispatcher.
- Inventariar bundles do repo e provar (via Proof offline) o estado real de integridade.

Entregáveis: `01-diagnostico/map.md`, `01-diagnostico/gaps.md`.

## 02 — Finance “Golden Path” em IDL
- Bundle referência (mínimo) para `ENGINE_API_MODE=idl` com Proof offline PASS e E2E STRICT via HTTP.
- Resolver colisões de rotas entre legacy/IDL (quando necessário).
- Garantir que IDL router respeita `ENGINE_AUTH_MODE=strict` (token-based, sem spoof).

Entregáveis: spec + prompts da fase, testes E2E, Proof offline.

## 03 — ACME Core em IDL
- Migrar `bundles/acme_core` sem remover governança (mandates/autonomy não podem ficar vazios).
- Proof offline PASS + E2E STRICT.

## 04 — Multi-pilot Multi-dept em IDL
- Migrar `bundles/multi-pilot` (finance + support).
- Corrigir ledger schema legado (se existir) e garantir `source_idl_sha256` real com seeds dentro do bundle.
- Proof offline PASS + E2E STRICT (multi-dept `/d/{dept_id}`).

## 05 — Onboarding + ISE IDL-ready
- Onboarding: gate determinístico em `ENGINE_API_MODE=idl` (não gerar bundle parcial sem `operations.json`).
- ISE: falhar determinísticamente se `source_idl_sha256` ausente no IRCS; não gerar bundle “meio válido”.
- Testes para ambos (tmp_path como data root).

## 06 — Baseline PROD/STRICT/IDL
- Smoke test “boot + /health + /console/login + provisionamento + fluxo mínimo”.
- Runbook final replicável.

## 07 — Legacy Cutover Policy
- Telemetria determinística para uso de rotas legacy em `ENGINE_API_MODE=both`.
- Seção read-only no console “Legacy Cutover Status”.
- Testes com endpoint legacy-only.

## 08 — Admin Key Bootstrap
- Permitir criar a **primeira** admin key de uma instituição non-default via `X-Admin-Token` (one-time), sem shell.
- Testes e runbook.

