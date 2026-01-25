# Runbook — PROD/STRICT/IDL (Migração 06)

Este runbook descreve o **caminho canônico** para operar uma instituição em produção com:
- `ENGINE_INSTALL_MODE=prod`
- `ENGINE_AUTH_MODE=strict`
- `ENGINE_API_MODE=idl`

## 1) Pré-requisitos de env

Obrigatórios:
- `ENGINE_ISE_ADMIN_TOKEN` (secreto, forte)
- `ENGINE_CONSOLE_SESSION_SECRET` (>= 32 chars)
- `ENGINE_DATA_ROOT` (diretório do data root)
- `ENGINE_BUNDLE_PATH` apontando para bundle IDL-ready

Recomendado (exemplo local):
```bash
export ENGINE_BASE_URL="http://127.0.0.1:8001"
```

## 2) Subir o engine

Exemplo (repo local):
```bash
cd /home/bazari/engine
set -a; source "/home/bazari/libervia_data/bazari_prod/engine.env"; set +a
PYTHONPATH="/home/bazari/engine/src" python3 -m uvicorn engine.api.server:app --host 127.0.0.1 --port 8001 --log-level info
```

## 3) Criar instituição (global admin token)

```bash
curl -sS -X POST "$ENGINE_BASE_URL/admin/institutions" \
  -H "X-Admin-Token: $ENGINE_ISE_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"slug":"bazari","display_name":"Bazari"}'
```

Saída inclui `institution_id`.

## 4) Bootstrap: criar primeira admin key da instituição (one-time)

```bash
curl -sS -X POST "$ENGINE_BASE_URL/admin/institutions/<INSTITUTION_ID>/admin-keys" \
  -H "X-Admin-Token: $ENGINE_ISE_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Guarde com segurança o `plaintext_secret` (este é o `X-Admin-Key`).

## 5) Provisionar actor tokens (STRICT)

```bash
curl -sS -X POST "$ENGINE_BASE_URL/admin/institutions/<INSTITUTION_ID>/actors" \
  -H "X-Institution-Id: <INSTITUTION_ID>" \
  -H "X-Admin-Key: <ADMIN_KEY_PLAINTEXT>" \
  -H "Content-Type: application/json" \
  -d '{"actor_id":"<UUID>","roles":["analyst"]}'
```

Repita para roles que vão operar o fluxo (ex.: `manager`).

## 6) Chamar operações (IDL + STRICT)

Exemplo (Finance golden path):
```bash
curl -sS -X POST "$ENGINE_BASE_URL/finance/expenses" \
  -H "X-Institution-Id: <INSTITUTION_ID>" \
  -H "X-Actor-Token: <ACTOR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "description": "teste"}'
```

## 7) Observabilidade (read-only)

Para ver atividade por actor (ledger-derived):
```bash
curl -sS "$ENGINE_BASE_URL/v1/observe/actors?limit=20" \
  -H "X-Institution-Id: <INSTITUTION_ID>" \
  -H "X-Admin-Key: <ADMIN_KEY_PLAINTEXT>"
```

