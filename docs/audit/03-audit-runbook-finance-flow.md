# Runbook de Auditoria — Fluxo Finance (PROD/STRICT/IDL)

Objetivo: executar e validar um fluxo institucional completo (create → approval → commit) em modo produção, com evidências verificáveis.

## 0) Pré-requisitos

- Python + deps do repo já instaladas
- Execução local (single-instance) em Linux

## 1) Variáveis e modos (recomendado)

Para validação “produção”:

- `ENGINE_INSTALL_MODE=prod`
- `ENGINE_AUTH_MODE=strict`
- `ENGINE_API_MODE=idl` (ou `both` durante migração)

## 2) Subir o engine (exemplo local)

Em um terminal:

```bash
cd /home/bazari/engine
export PYTHONPATH=/home/bazari/engine/src

# ajuste o data root conforme o ambiente do cliente
export ENGINE_DATA_ROOT=/var/lib/libervia_engine
export ENGINE_INSTALL_MODE=prod
export ENGINE_AUTH_MODE=strict
export ENGINE_API_MODE=idl

export ENGINE_CONSOLE_SESSION_SECRET='(secret >= 32 chars)'
export ENGINE_ISE_ADMIN_TOKEN='(admin token)'

python3 -m uvicorn engine.api.server:app --host 127.0.0.1 --port 8001 --log-level info
```

Verificar:

```bash
curl -sS http://127.0.0.1:8001/health
curl -sS http://127.0.0.1:8001/openapi.json | python3 -m json.tool > /dev/null
```

## 3) Preparar instituição, bundle e atores (exemplo)

No repo existe um exemplo executável (artefatos já prontos) em:

- `tmp/flows/run-20260121T201110Z/run.env`
- `tmp/flows/run-20260121T201110Z/validate_e2e.sh`
- `tmp/flows/run-20260121T201110Z/validate_report.md`

Esse exemplo demonstra:

- instituição e tokens de atores em `ENGINE_AUTH_MODE=strict`
- bundle instalado e verificado (`engine.proof`)
- fluxo Finance com approvals e trilha de ledger

Para repetir a validação local, execute:

```bash
cd /home/bazari/engine
bash tmp/flows/run-20260121T201110Z/validate_e2e.sh
```

## 4) Evidências que o auditor deve coletar

### 4.1 Prova offline do bundle

```bash
source tmp/flows/run-20260121T201110Z/run.env
PYTHONPATH=/home/bazari/engine/src python3 -m engine.proof verify "$ENGINE_BUNDLE_PATH" --json | python3 -m json.tool
```

### 4.2 Ledger (append-only + hash-chain)

Exemplo (no data root do run):

- `tmp/flows/run-20260121T201110Z/data/ledger/audit_ledger.jsonl`

O auditor pode:

- verificar integridade (hash-chain) via rotina do engine no boot
- inspecionar eventos críticos: RBAC/MANDATE/AUTONOMY/POLICY/APPROVAL/CASE_COMMITTED

### 4.3 Migração IDL (se aplicável)

Em `ENGINE_API_MODE=idl`, o engine deve falhar no boot se faltar `operations.json` ou se houver `bind.kind` não suportado.

## 5) Resultado esperado (definição objetiva de sucesso)

- `/openapi.json` contém `operationId` do registry (não prefixado)
- `POST /finance/expenses` (IDL-driven) retorna `pending_approval` com `approval_id`
- tentativa de decide pelo requester falha determinísticamente
- decide por approver retorna `COMMITTED`
- `engine.proof verify` PASS para o bundle ativo
- ledger contém trilha suficiente para reconstruir:
  - quem executou
  - sob qual contrato/versão (hashes)
  - sob quais gates/decisões

