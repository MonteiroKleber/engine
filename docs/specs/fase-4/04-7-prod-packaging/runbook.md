# 04-7 Prod Packaging — Runbook

**Status:** IMPLEMENTADO
**Data:** 2026-01-20
**Baseado em:** spec.md (contrato), mapeamento do runtime atual
**Atualizado:** 2026-01-20 (scripts de backup/restore implementados)

---

## 1. Visão Geral

Este runbook descreve como operar o Libervia Engine em produção usando a infraestrutura existente (systemd + scripts ops/).

### 1.1 Arquitetura de Execução

```
┌──────────────────────────────────────────────────────────────────┐
│  systemd: engine.service                                         │
│  ├── User: bazari                                                │
│  ├── WorkingDirectory: /home/bazari/engine                       │
│  ├── EnvironmentFile: /etc/engine/engine.env                     │
│  └── ExecStart: uvicorn engine.api.server:app --port 8000        │
└──────────────────────────────────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Data Layer                                                      │
│  ├── /var/lib/engine/bundles/CURRENT → release symlink           │
│  ├── /var/lib/engine/bundles/releases/<YYYYMMDD-HHMMSS>/         │
│  └── var/institutions/<uuid>/                                    │
│      ├── ledger.jsonl                                            │
│      ├── state_store/                                            │
│      ├── bundles/                                                │
│      ├── admin_keys.jsonl                                        │
│      └── config.json                                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Startup

### 2.1 Startup Sequence (Runtime)

Ao iniciar, o servidor executa na seguinte ordem (`server.py:lifespan`):

1. **Setup Logging** — Configura logs (JSON em produção)
2. **Verify Ledger** — Se ledger existir, verifica integridade
   - Se falhar → entra em `SAFE_MODE`
3. **Load Bundle** — Carrega bundle de `ENGINE_BUNDLE_PATH`
4. **Run Preflight Checks** — Valida configuração crítica:
   - Path isolation (multi-tenant mode)
   - Session secret configurado (`ENGINE_CONSOLE_SESSION_SECRET`)
   - Se falhar → **hard fail** (não inicia)
5. **Cleanup Dev Runs** — Se `ENGINE_DEV_RUNS_CLEANUP_ON_BOOT=1`
6. **Ready** — Aceita tráfego

### 2.2 Comandos de Startup

```bash
# Iniciar serviço
sudo systemctl start engine.service

# Verificar status
sudo systemctl status engine.service

# Ver logs em tempo real
sudo journalctl -u engine.service -f

# Verificar saúde
curl http://127.0.0.1:8000/health
```

### 2.3 Resposta do /health

**Modo ACTIVE:**
```json
{"status": "ok", "mode": "ACTIVE"}
```

**Modo SAFE_MODE:**
```json
{
  "status": "degraded",
  "mode": "SAFE_MODE",
  "reason_code": "LEDGER_CHAIN_BROKEN",
  "details": ["Event 42 hash mismatch"]
}
```

---

## 3. Deploy

### 3.1 Deploy de Novo Bundle

```bash
# 1. Executar script de deploy (como root)
sudo /home/bazari/engine/ops/scripts/deploy_engine_prod.sh

# O script automaticamente:
# - Copia bundle para staging
# - Verifica integridade
# - Move para releases/<timestamp>
# - Atualiza symlink CURRENT
# - Reinicia engine.service
# - Executa smoke test
# - Se falhar, faz rollback automático
```

### 3.2 Rollback Manual

```bash
# Ver releases disponíveis
ls -la /var/lib/engine/bundles/releases/

# Rollback para release anterior
sudo /home/bazari/engine/ops/scripts/rollback_engine_bundle.sh
# ou manualmente:
sudo ln -sfn /var/lib/engine/bundles/releases/<YYYYMMDD-HHMMSS>/finance-pilot \
             /var/lib/engine/bundles/CURRENT
sudo systemctl restart engine.service
```

---

## 4. Backup & Restore

### 4.1 O que fazer backup

| Componente | Path | Frequência |
|------------|------|------------|
| Institutions Registry | `var/institutions_registry.jsonl` | Diário |
| Institution Data | `var/institutions/<uuid>/` | Diário |
| Bundles Ativos | `/var/lib/engine/bundles/releases/` | Por deploy |
| Config Global | `/etc/engine/engine.env` | Por mudança |

### 4.2 Script de Backup

Utilize o script padronizado:

```bash
# Executar backup (como root ou com permissões de leitura em ENGINE_DATA_ROOT)
sudo /home/bazari/engine/ops/scripts/backup_engine.sh [backup_dir]

# Exemplo:
sudo /home/bazari/engine/ops/scripts/backup_engine.sh /var/backups/engine

# Output:
# - /var/backups/engine/engine-backup-YYYYMMDD-HHMMSS.tar.gz
# - /var/backups/engine/engine-backup-YYYYMMDD-HHMMSS.tar.gz.sha256
```

**O script automaticamente:**
- Copia `institutions_registry.jsonl`
- Copia todos os dados de `institutions/<uuid>/`
- Copia `/etc/engine/engine.env`
- Registra referência do bundle atual
- Gera manifesto com checksums SHA256
- Cria tarball comprimido

### 4.3 Restore

Utilize o script padronizado:

```bash
# IMPORTANTE: Parar o serviço primeiro!
sudo systemctl stop engine.service

# Executar restore
sudo /home/bazari/engine/ops/scripts/restore_engine.sh <backup_tarball> [target_data_root]

# Exemplo:
sudo /home/bazari/engine/ops/scripts/restore_engine.sh \
  /var/backups/engine/engine-backup-20260120-143000.tar.gz \
  /var/lib/engine/data

# Reiniciar serviço
sudo systemctl start engine.service
```

**O script automaticamente:**
- Verifica checksum do tarball (se `.sha256` existir)
- Verifica que engine.service está parado
- Recusa restaurar se target não estiver vazio (sem merge)
- Extrai e valida manifesto
- Restaura institutions registry e dados
- Valida que arquivos JSONL são válidos
- Exibe próximos passos

**IMPORTANTE:** O restore de ledgers append-only é seguro, mas eventos adicionados após o backup serão perdidos. O script NÃO faz merge de dados — o target deve estar vazio.

---

## 5. Troubleshooting

### 5.1 Serviço Não Inicia

```bash
# Ver erro de startup
sudo journalctl -u engine.service -n 100 --no-pager

# Erros comuns:
# - "Preflight check failed: SESSION_SECRET_MISSING"
#   → Set ENGINE_CONSOLE_SESSION_SECRET in /etc/engine/engine.env
#
# - "LEDGER_VERIFY_FAILED"
#   → Ledger corrompido, verificar com:
#   python -c "from engine.core.ledger import verify_ledger_file; print(verify_ledger_file(...))"
```

### 5.2 Saúde Degradada (SAFE_MODE)

```bash
# Verificar razão
curl http://127.0.0.1:8000/health | jq

# Ações por código:
# LEDGER_CHAIN_BROKEN → Verificar backup, considerar restore
# LEDGER_HASH_MISMATCH → Mesmo que acima
# SESSION_SECRET_MISSING → Configurar env var
```

### 5.3 Console Inacessível

```bash
# 1. Verificar session secret
grep ENGINE_CONSOLE_SESSION_SECRET /etc/engine/engine.env

# 2. Verificar admin token
grep ENGINE_ISE_ADMIN_TOKEN /etc/engine/engine.env

# 3. Testar login via curl
curl -X POST http://127.0.0.1:8000/console/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "admin_token=YOUR_TOKEN"
```

### 5.4 Requests 429 (Rate Limit)

```bash
# Verificar/ajustar rate limit
grep ENGINE_RATE_LIMIT_PER_MINUTE /etc/engine/engine.env
# Default: 100/min/IP/path
```

---

## 6. Monitoramento

### 6.1 Health Check (Load Balancer)

```
GET /health
Expected: 200 {"status": "ok", "mode": "ACTIVE"}
Unhealthy: 503 (SAFE_MODE)
```

### 6.2 Logs

```bash
# Logs estruturados (JSON)
sudo journalctl -u engine.service -o json

# Filtrar por evento
sudo journalctl -u engine.service | grep LEDGER_VERIFY
```

### 6.3 Métricas Básicas

```bash
# Contagem de eventos no ledger
wc -l /var/lib/engine/institutions/*/ledger.jsonl

# Tamanho do state store
du -sh /var/lib/engine/institutions/*/state_store/
```

---

## 7. Operações de Emergência

### 7.1 Freeze Mode (Parar Escritas)

Via API admin:
```bash
curl -X PUT http://127.0.0.1:8000/admin/institutions/<id>/config \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"freeze_mode": true}'
```

### 7.2 Emergency Stop (Bloquear Endpoints)

```bash
curl -X PUT http://127.0.0.1:8000/admin/institutions/<id>/config \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "emergency_stop": {
      "enabled": true,
      "blocked_endpoints": ["POST /finance/expenses"]
    }
  }'
```

### 7.3 EGE Rollback

```bash
# Se detectado drift, rollback via API
curl -X POST http://127.0.0.1:8000/admin/ege/<institution_id>/rollback \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_release_id": "<YYYYMMDD-HHMMSS>"}'
```

---

## 8. Referência de Arquivos

| Path | Descrição |
|------|-----------|
| `/etc/engine/engine.env` | Configuração de produção |
| `/etc/systemd/system/engine.service` | Unit file systemd |
| `/var/lib/engine/bundles/` | Bundles de produção |
| `/home/bazari/engine/var/` | Data root (dev/prod mixed) |
| `/home/bazari/engine/ops/` | Scripts operacionais |
