# 04-7 Prod Packaging — Checklist de Pré-Produção

**Status:** DRAFT
**Data:** 2026-01-20
**Baseado em:** spec.md (contrato), mapeamento do runtime atual

---

## 1. Variáveis de Ambiente

### 1.1 OBRIGATÓRIAS (Hard Fail se Ausentes)

| Variável | Descrição | Validação | Exemplo |
|----------|-----------|-----------|---------|
| `ENGINE_CONSOLE_SESSION_SECRET` | Secret para assinar cookies | Min 32 chars | `$(python -c "import secrets; print(secrets.token_hex(32))")` |
| `ENGINE_ISE_ADMIN_TOKEN` | Token para APIs admin | Non-empty | `$(python -c "import secrets; print(secrets.token_urlsafe(32))")` |

### 1.2 RECOMENDADAS PARA PRODUÇÃO

| Variável | Descrição | Default | Prod Recomendado |
|----------|-----------|---------|------------------|
| `ENGINE_ENV` | Ambiente | `development` | `production` |
| `ENGINE_LOG_FORMAT` | Formato de log | `text` | `json` |
| `ENGINE_CONSOLE_SECURE_COOKIE` | Cookie Secure flag | `auto` | `true` |
| `ENGINE_DATA_ROOT` | Raiz de dados | `var` | `/var/lib/engine/data` |
| `ENGINE_BUNDLE_PATH` | Path do bundle | `bundles/finance-pilot` | `/var/lib/engine/bundles/CURRENT` |

### 1.3 OPCIONAIS (Com Defaults)

| Variável | Descrição | Default |
|----------|-----------|---------|
| `ENGINE_RATE_LIMIT_PER_MINUTE` | Rate limit global | `100` |
| `ENGINE_MAX_BODY_BYTES` | Max body size | `262144` (256KB) |
| `ENGINE_CONSOLE_SESSION_TTL_HOURS` | TTL da sessão | `8` |
| `ENGINE_CORS_ORIGINS` | CORS origins (CSV) | `(none)` |
| `ENGINE_DEV_RUNS_CLEANUP_ON_BOOT` | Limpar dev runs | `0` |
| `ENGINE_DEV_RUNS_TTL_HOURS` | TTL de dev runs | `24` |
| `ENGINE_DEV_RUNS_MAX_RUNS` | Max dev runs | `200` |

### 1.4 MULTI-TENANT (Se Aplicável)

| Variável | Descrição | Regra |
|----------|-----------|-------|
| `ENGINE_LEDGER_PATH` | Path do ledger | NÃO usar absolute se multi-tenant |
| `ENGINE_STATE_STORE_DIR` | Dir state store | NÃO usar absolute se multi-tenant |
| `ENGINE_INSTITUTIONS_REGISTRY_PATH` | Registry | Default: `var/institutions_registry.jsonl` |
| `ENGINE_INSTITUTIONS_DIR` | Dir instituições | Default: `var/institutions` |

---

## 2. Permissões e Paths

### 2.1 Checklist de Diretórios

- [ ] `/etc/engine/` existe e tem permissão 750
- [ ] `/etc/engine/engine.env` existe e tem permissão 640
- [ ] `/var/lib/engine/` existe e é de propriedade do user do serviço
- [ ] `/var/lib/engine/bundles/` existe
- [ ] `/var/lib/engine/bundles/CURRENT` é symlink válido para bundle
- [ ] Data root (`ENGINE_DATA_ROOT`) é writable pelo user do serviço

### 2.2 Checklist de Arquivos

- [ ] Bundle manifest existe: `<bundle>/bundle.manifest.json`
- [ ] Hashes dos contracts batem com manifest
- [ ] Se ledger existe, verificar integridade antes de iniciar

---

## 3. Rede e Segurança

### 3.1 Portas

| Porta | Uso | Exposição |
|-------|-----|-----------|
| 8000 | API/Console | Via reverse proxy (nginx/traefik) |

### 3.2 Checklist de Segurança

- [ ] `ENGINE_CONSOLE_SECURE_COOKIE=true` se HTTPS
- [ ] Reverse proxy configurado com HTTPS
- [ ] Headers de segurança aplicados pelo engine (X-Frame-Options, etc.)
- [ ] Rate limiting ativo (default 100/min)
- [ ] Body size limit ativo (default 256KB)
- [ ] Admin token é strong (32+ chars, random)
- [ ] Session secret é strong (32+ chars, random)

---

## 4. Systemd

### 4.1 Checklist de Instalação

- [ ] Service unit copiado para `/etc/systemd/system/engine.service`
- [ ] `systemctl daemon-reload` executado
- [ ] `systemctl enable engine.service` executado
- [ ] `EnvironmentFile=/etc/engine/engine.env` apontando correto
- [ ] User no service file tem permissões nos paths

### 4.2 Verificação

```bash
# Service está habilitado?
systemctl is-enabled engine.service

# Service está ativo?
systemctl is-active engine.service

# Ver status
systemctl status engine.service
```

---

## 5. Bundle

### 5.1 Checklist de Bundle

- [ ] `bundle.manifest.json` existe
- [ ] Todos os contracts listados existem
- [ ] Hashes SHA256 verificados
- [ ] `rbac.json` válido
- [ ] `workflows.json` válido
- [ ] `policies.json` válido (se existir)
- [ ] `approvals.json` válido (se existir)

### 5.2 Verificação

```bash
# Executar verificação de bundle
/home/bazari/engine/ops/checks/verify_bundle.sh <bundle_path>

# Ou via preflight completo
/home/bazari/engine/ops/checks/preflight.sh
```

---

## 6. Healthcheck

### 6.1 Verificação Pós-Startup

```bash
# Health check básico
curl -s http://127.0.0.1:8000/health | jq

# Esperado:
# {"status": "ok", "mode": "ACTIVE"}

# Se retornar SAFE_MODE, verificar reason_code
```

### 6.2 Smoke Test

```bash
# Executar smoke test completo
/home/bazari/engine/ops/checks/smoke_test.sh
```

---

## 7. Console

### 7.1 Checklist do Console

- [ ] `ENGINE_CONSOLE_SESSION_SECRET` configurado (min 32 chars)
- [ ] `ENGINE_ISE_ADMIN_TOKEN` configurado
- [ ] Consegue acessar `/console/` no browser
- [ ] Login funciona com admin token
- [ ] CSRF token presente em forms

### 7.2 Teste de Login

```bash
# Testar login via curl
curl -v -X POST http://127.0.0.1:8000/console/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "admin_token=SEU_TOKEN"

# Esperado: 302 redirect para /console/ com Set-Cookie
```

---

## 8. Backup

### 8.1 Checklist de Backup

- [ ] Script de backup configurado
- [ ] Diretório de backup com espaço suficiente
- [ ] Backup inclui:
  - [ ] `var/institutions_registry.jsonl`
  - [ ] `var/institutions/*/`
  - [ ] `/etc/engine/engine.env`
- [ ] Retenção de backups definida
- [ ] Teste de restore validado

---

## 9. Checklist Final de Go-Live

### 9.1 Pré-Deploy

- [ ] Todas as env vars obrigatórias configuradas
- [ ] Bundle verificado e deployado
- [ ] Permissões de diretório corretas
- [ ] Backup do estado atual feito

### 9.2 Deploy

- [ ] Service iniciado com sucesso
- [ ] Health check retorna `{"status": "ok", "mode": "ACTIVE"}`
- [ ] Smoke test passa
- [ ] Console acessível via browser
- [ ] Login funciona

### 9.3 Pós-Deploy

- [ ] Logs sendo gerados corretamente
- [ ] Monitoramento configurado (health endpoint)
- [ ] Alertas configurados para SAFE_MODE
- [ ] Documentação de operação revisada

---

## 10. Referência Rápida

### Gerar Secrets

```bash
# Session secret (32+ chars hex)
python -c "import secrets; print(secrets.token_hex(32))"

# Admin token (URL-safe)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Estrutura de /etc/engine/engine.env

```bash
# Obrigatórias
ENGINE_CONSOLE_SESSION_SECRET=<64_char_hex>
ENGINE_ISE_ADMIN_TOKEN=<random_token>

# Produção
ENGINE_ENV=production
ENGINE_LOG_FORMAT=json
ENGINE_CONSOLE_SECURE_COOKIE=true

# Paths
ENGINE_DATA_ROOT=/var/lib/engine/data
ENGINE_BUNDLE_PATH=/var/lib/engine/bundles/CURRENT

# Limites (ajustar conforme necessário)
ENGINE_RATE_LIMIT_PER_MINUTE=100
ENGINE_MAX_BODY_BYTES=262144
```
