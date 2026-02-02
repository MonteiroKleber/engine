# SaaS Production Checklist — Libervia Engine + Console

Version: 1.0 | Last Updated: 2026-01-30

## Overview

This checklist covers deploying Libervia Engine and Console in a multi-tenant SaaS environment with strict security enforcement.

---

## 1. Pre-Deployment Requirements

### 1.1 Infrastructure

- [ ] Dedicated server/VM with Ubuntu 22.04+ or equivalent
- [ ] Minimum 4GB RAM, 2 vCPUs
- [ ] SSD storage for ledger performance
- [ ] Network: HTTPS termination (nginx/caddy) + internal HTTP to Engine
- [ ] Firewall: Only expose 443 externally

### 1.2 Security Secrets (generate unique values)

```bash
# Generate session secret (64 chars)
python -c "import secrets; print(secrets.token_hex(32))"

# Generate admin token
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate institution-specific admin keys
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

- [ ] `ENGINE_CONSOLE_SESSION_SECRET` generated and stored securely
- [ ] `ENGINE_ISE_ADMIN_TOKEN` generated and stored securely
- [ ] Per-institution admin keys planned

---

## 2. Engine Configuration

### 2.1 Critical Environment Variables

Copy from `/home/bazari/engine/ops/env/engine.env.example` to `/etc/engine/engine.env`:

```bash
# MANDATORY for production
ENGINE_INSTALL_MODE=prod
ENGINE_AUTH_MODE=strict
ENGINE_CONSOLE_SESSION_SECRET=<generated-64-char-hex>
ENGINE_ISE_ADMIN_TOKEN=<generated-token>
ENGINE_ENV=production
ENGINE_LOG_FORMAT=json
ENGINE_CONSOLE_SECURE_COOKIE=true

# Data paths
ENGINE_DATA_ROOT=/var/lib/engine/data
ENGINE_BUNDLE_PATH=/var/lib/engine/bundles/CURRENT
```

### 2.2 Verification Commands

```bash
# Check environment is set correctly
grep ENGINE_AUTH_MODE /etc/engine/engine.env
# Expected: ENGINE_AUTH_MODE=strict

grep ENGINE_INSTALL_MODE /etc/engine/engine.env
# Expected: ENGINE_INSTALL_MODE=prod
```

### 2.3 Checklist

- [ ] `ENGINE_INSTALL_MODE=prod` (enforces secure defaults)
- [ ] `ENGINE_AUTH_MODE=strict` (requires X-Actor-Token, rejects header spoofing)
- [ ] `ENGINE_CONSOLE_SESSION_SECRET` is unique, 64+ chars
- [ ] `ENGINE_ISE_ADMIN_TOKEN` is unique, not in version control
- [ ] `ENGINE_CONSOLE_SECURE_COOKIE=true` (requires HTTPS)
- [ ] `ENGINE_LOG_FORMAT=json` (for structured logging)
- [ ] `ENGINE_DATA_ROOT` points to secure, backed-up storage

---

## 3. Bundle Deployment

### 3.1 Deploy Bundle

```bash
# Run as root
sudo /home/bazari/engine/ops/scripts/deploy_engine_prod.sh

# Verify bundle
sudo /home/bazari/engine/ops/checks/verify_bundle.sh /var/lib/engine/bundles/CURRENT/finance-pilot
```

### 3.2 Checklist

- [ ] Bundle manifest valid (`bundle.manifest.json`)
- [ ] All contract hashes verified
- [ ] `rbac.json` defines proper roles/permissions
- [ ] `approvals.json` defines approval workflows
- [ ] `autonomy.json` defines agent autonomy levels
- [ ] CURRENT symlink points to verified bundle

---

## 4. Engine Service

### 4.1 Install and Start

```bash
# Install systemd service
sudo /home/bazari/engine/ops/scripts/install_engine_service.sh

# Start engine
sudo systemctl enable engine
sudo systemctl start engine

# Verify status
sudo systemctl status engine
```

### 4.2 Health Check

```bash
# Check health (internal)
curl -s http://localhost:8001/health | jq '.'

# Expected response
{
  "status": "healthy",
  "mode": "ACTIVE",
  "version": "0.1.0",
  "bundle_hash": "sha256:...",
  "ledger_verified": true
}
```

### 4.3 Checklist

- [ ] Engine starts without errors
- [ ] Health returns `"mode": "ACTIVE"`
- [ ] `ledger_verified: true`
- [ ] Logs show `ENGINE_AUTH_MODE=strict`
- [ ] No `UNVERIFIED_IDENTITY_USED` warnings in strict mode

---

## 5. Institution Onboarding

### 5.1 Create Institution

```bash
# Bootstrap first admin key for institution
curl -X POST http://localhost:8001/admin/institutions \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ENGINE_ISE_ADMIN_TOKEN" \
  -d '{
    "institution_id": "acme-corp-uuid",
    "name": "ACME Corporation"
  }'
```

### 5.2 Create Institution Admin Key

```bash
# Create admin key for institution
curl -X POST http://localhost:8001/admin/institutions/acme-corp-uuid/keys \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ENGINE_ISE_ADMIN_TOKEN" \
  -d '{
    "name": "primary-admin",
    "permissions": ["*"]
  }'
# Save the returned key securely!
```

### 5.3 Create Actor Tokens

```bash
# Create CEO actor token
curl -X POST http://localhost:8001/admin/institutions/acme-corp-uuid/actors \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $INSTITUTION_ADMIN_KEY" \
  -d '{
    "actor_id": "ceo-uuid",
    "roles": ["ceo", "approver"],
    "is_agent": false
  }'
# Save the returned token for the actor!

# Create LLM Agent token
curl -X POST http://localhost:8001/admin/institutions/acme-corp-uuid/actors \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $INSTITUTION_ADMIN_KEY" \
  -d '{
    "actor_id": "org-agent-uuid",
    "roles": ["organizational_agent"],
    "is_agent": true
  }'
```

### 5.4 Checklist

- [ ] Institution created successfully
- [ ] Admin key created and stored securely
- [ ] Human actor tokens created (CEO, CFO, etc.)
- [ ] Agent actor tokens created with `is_agent: true`
- [ ] All tokens stored securely (not in version control)

---

## 6. Console Deployment

See [CONSOLE_DEPLOYMENT.md](./CONSOLE_DEPLOYMENT.md) for frontend deployment.

### 6.1 Quick Checklist

- [ ] Console built with production env vars
- [ ] `VITE_ENGINE_BASE_URL` points to Engine (via HTTPS proxy)
- [ ] Admin credentials NOT in frontend (use backend proxy for admin ops)
- [ ] CORS configured on Engine for Console domain

---

## 7. Smoke Tests

### 7.1 Run Smoke Tests

```bash
# Run automated smoke tests
/home/bazari/engine/ops/checks/smoke_test.sh
```

### 7.2 Manual Verification

```bash
# 1. Health check
curl -s https://engine.example.com/health | jq '.mode'
# Expected: "ACTIVE"

# 2. Actor identity (with valid token)
curl -s https://engine.example.com/v1/observe/actors \
  -H "X-Institution-Id: acme-corp-uuid" \
  -H "X-Admin-Key: $ADMIN_KEY"
# Expected: List of actors

# 3. Approval workflow (requires actor token)
# ... test specific to your bundle
```

### 7.3 Checklist

- [ ] Health returns ACTIVE
- [ ] Admin endpoints require authentication
- [ ] Actor endpoints require X-Actor-Token in strict mode
- [ ] RBAC denies unauthorized actions
- [ ] Ledger records all events

---

## 8. Monitoring & Alerts

### 8.1 Essential Metrics

| Metric | Alert Threshold | Action |
|--------|-----------------|--------|
| Health mode != ACTIVE | Any | Page on-call |
| Error rate > 1% | 1%/5min | Investigate |
| Latency p99 > 2s | 2s | Scale or optimize |
| Ledger write failures | Any | Page on-call |
| SAFE_MODE activated | Any | Page on-call |

### 8.2 Log Monitoring

```bash
# Watch for errors
journalctl -u engine -f | jq 'select(.level == "ERROR")'

# Watch for denied actions
journalctl -u engine -f | jq 'select(.event_type | contains("DENIED"))'

# Watch for auth failures
journalctl -u engine -f | jq 'select(.event_type == "ADMIN_AUTH_FAILED")'
```

---

## 9. Backup & Recovery

### 9.1 Backup Schedule

| Data | Frequency | Retention |
|------|-----------|-----------|
| Ledger | Hourly | 30 days |
| State stores | Daily | 7 days |
| Bundles | Per-release | Indefinite |
| Configs | Per-change | Indefinite |

### 9.2 Backup Commands

```bash
# Backup ledger for institution
sudo /home/bazari/engine/ops/scripts/backup_engine.sh acme-corp-uuid

# Backup all institutions
for inst in $(ls /var/lib/engine/data/institutions/); do
  sudo /home/bazari/engine/ops/scripts/backup_engine.sh $inst
done
```

### 9.3 Recovery

```bash
# Restore from backup
sudo /home/bazari/engine/ops/scripts/restore_engine.sh acme-corp-uuid /path/to/backup.tar.gz
```

---

## 10. Final Sign-Off

### Pre-Production

- [ ] All checklist items above completed
- [ ] Smoke tests pass
- [ ] Backup/restore tested
- [ ] Monitoring configured
- [ ] On-call rotation defined

### Go-Live

| Item | Date | Signed Off By |
|------|------|---------------|
| Engine deployed | ______ | _____________ |
| Console deployed | ______ | _____________ |
| First institution onboarded | ______ | _____________ |
| Smoke tests passed | ______ | _____________ |
| Documentation reviewed | ______ | _____________ |

---

## Quick Reference

### Environment Variables (Required for Production)

```bash
ENGINE_INSTALL_MODE=prod
ENGINE_AUTH_MODE=strict
ENGINE_CONSOLE_SESSION_SECRET=<64-char-hex>
ENGINE_ISE_ADMIN_TOKEN=<unique-token>
ENGINE_ENV=production
ENGINE_LOG_FORMAT=json
ENGINE_CONSOLE_SECURE_COOKIE=true
ENGINE_DATA_ROOT=/var/lib/engine/data
ENGINE_BUNDLE_PATH=/var/lib/engine/bundles/CURRENT
```

### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | System health |
| `POST /admin/institutions` | Create institution |
| `POST /admin/institutions/{id}/keys` | Create admin key |
| `POST /admin/institutions/{id}/actors` | Create actor token |
| `GET /v1/observe/ledger/events` | Audit trail |
| `POST /approvals/{id}/decide` | Approve/reject |
