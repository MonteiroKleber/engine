# Incident Response Runbook — Libervia Engine

Version: 1.0 | Last Updated: 2026-01-30

## Overview

This runbook provides step-by-step procedures for responding to incidents affecting Libervia Engine in production.

---

## 1. Severity Levels

| Level | Description | Response Time | Examples |
|-------|-------------|---------------|----------|
| **P1** | System down, data at risk | 15 min | SAFE_MODE, ledger tampering |
| **P2** | Major feature broken | 1 hour | Auth failures, approvals broken |
| **P3** | Minor issue | 4 hours | Slow performance, UI glitch |
| **P4** | Cosmetic/improvement | Next sprint | Documentation, minor UX |

---

## 2. Initial Assessment

### 2.1 Quick Health Check

```bash
# 1. Check Engine health
curl -s http://localhost:8001/health | jq '.'

# 2. Check service status
sudo systemctl status engine

# 3. Check recent logs for errors
journalctl -u engine -n 50 --no-pager | grep -i error

# 4. Check disk space
df -h /var/lib/engine

# 5. Check memory/CPU
htop  # or: free -m && uptime
```

### 2.2 Severity Classification

| Symptom | Severity |
|---------|----------|
| `mode: "SAFE_MODE"` | P1 |
| `LEDGER_TAMPER_DETECTED` | P1 |
| Service not running | P1 |
| All auth failing | P2 |
| Specific feature broken | P2/P3 |
| Slow but functional | P3 |

---

## 3. P1: SAFE_MODE Activated

### 3.1 Symptoms

- Health check returns `"mode": "SAFE_MODE"`
- Write operations fail with 503
- Dashboard shows degraded state

### 3.2 Immediate Actions

```bash
# 1. Get reason code
curl -s http://localhost:8001/health | jq '.reason_code, .details'

# 2. Check logs for cause
journalctl -u engine -n 100 --no-pager | grep -E "(SAFE_MODE|ERROR|CRITICAL)"
```

### 3.3 Resolution by Reason Code

#### `BUNDLE_MANIFEST_MISSING`

```bash
# Check bundle path
ls -la $ENGINE_BUNDLE_PATH/bundle.manifest.json

# If missing, verify symlink
ls -la /var/lib/engine/bundles/CURRENT

# Fix: redeploy bundle
sudo /home/bazari/engine/ops/scripts/deploy_engine_prod.sh
sudo systemctl restart engine
```

#### `BUNDLE_CONTRACT_HASH_MISMATCH`

```bash
# Check which contract failed
curl -s http://localhost:8001/health | jq '.details'

# Verify bundle integrity
/home/bazari/engine/ops/checks/verify_bundle.sh $ENGINE_BUNDLE_PATH

# Fix: redeploy bundle
sudo /home/bazari/engine/ops/scripts/deploy_engine_prod.sh
sudo systemctl restart engine
```

#### `LEDGER_TAMPER_DETECTED`

**CRITICAL: Do not modify the ledger!**

```bash
# 1. Stop engine (prevent further writes)
sudo systemctl stop engine

# 2. Preserve evidence
sudo cp -r /var/lib/engine/data /var/lib/engine/data.incident.$(date +%Y%m%d%H%M%S)

# 3. Investigate
# Check ledger manually
python -c "
from engine.core.ledger import verify_ledger_file
from pathlib import Path
result = verify_ledger_file(Path('/var/lib/engine/data/institutions/INST_ID/audit_ledger.jsonl'))
print(f'First bad event at: {result.details}')
"

# 4. Contact security team for forensics

# 5. Recovery options:
#    a) Restore from backup (loses events after backup)
#    b) Manual ledger repair (requires audit approval)
```

---

## 4. P1: Service Down

### 4.1 Symptoms

- `systemctl status engine` shows failed
- Health endpoint not responding
- Logs show crash or exception

### 4.2 Immediate Actions

```bash
# 1. Check status
sudo systemctl status engine

# 2. Check recent logs
journalctl -u engine -n 100 --no-pager

# 3. Try restart
sudo systemctl restart engine

# 4. If still failing, check for common issues:
# - Disk full
df -h /var/lib/engine
# - Permission issues
ls -la /var/lib/engine/data
# - Port conflict
ss -tlnp | grep 8001
# - Python environment
which python
python --version
```

### 4.3 Emergency Rollback

```bash
# If restart fails repeatedly
sudo /home/bazari/engine/ops/scripts/rollback_engine_bundle.sh

# This reverts to PREVIOUS bundle version
sudo systemctl restart engine
```

---

## 5. P2: Authentication Failures

### 5.1 Symptoms

- All users getting 401 Unauthorized
- `ADMIN_AUTH_FAILED` events in logs
- Actors cannot perform actions

### 5.2 Diagnosis

```bash
# Check auth mode
curl -s http://localhost:8001/health | jq '.auth_mode'

# Check for auth errors in logs
journalctl -u engine -n 100 | grep -E "(AUTH|401|Unauthorized)"

# Verify admin key works
curl -s http://localhost:8001/admin/institutions/test/depts \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -w "\nHTTP: %{http_code}\n"
```

### 5.3 Common Causes

| Cause | Symptoms | Fix |
|-------|----------|-----|
| Wrong auth mode | Dev tokens in prod | Set `ENGINE_AUTH_MODE=strict`, use proper tokens |
| Expired/revoked tokens | Specific actors fail | Reissue tokens |
| Admin key rotated | All admin ops fail | Update key in env |
| Registry file corrupted | All actors fail | Restore from backup |

### 5.4 Token Reissuance

```bash
# Revoke old token
curl -X POST http://localhost:8001/admin/institutions/$INST_ID/actors/revoke \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"token_sha256": "old-token-hash"}'

# Issue new token
curl -X POST http://localhost:8001/admin/institutions/$INST_ID/actors \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_id": "actor-uuid",
    "roles": ["ceo", "approver"],
    "is_agent": false
  }'
```

---

## 6. P2: Approval System Broken

### 6.1 Symptoms

- Approve/Reject buttons not working
- 500 errors on `/approvals/{id}/decide`
- Pending approvals not showing

### 6.2 Diagnosis

```bash
# Check pending approvals
curl -s http://localhost:8001/v1/observe/ledger/events?event_type=APPROVAL_REQUESTED \
  -H "X-Institution-Id: $INST_ID" \
  -H "X-Admin-Key: $ADMIN_KEY" | jq '.events[:5]'

# Test approval decision
curl -X POST http://localhost:8001/approvals/$APPROVAL_ID/decide \
  -H "X-Institution-Id: $INST_ID" \
  -H "X-Actor-Token: $ACTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve"}' \
  -v
```

### 6.3 Common Causes

| Cause | Symptoms | Fix |
|-------|----------|-----|
| State store locked | Timeouts | Restart engine |
| Quorum not met | Can't approve | Check approval rules |
| SoD violation | Self-approve blocked | Use different approver |
| Case already decided | 400 error | Check case status |

---

## 7. Console Issues

### 7.1 Console Not Loading

```bash
# Check Console is served
curl -s -o /dev/null -w "%{http_code}" https://console.example.com/
# Expected: 200

# Check nginx/Caddy status
sudo systemctl status nginx
sudo nginx -t

# Check files exist
ls -la /var/www/libervia-console/
```

### 7.2 Console Can't Reach Engine

```bash
# Check CORS
curl -X OPTIONS https://api.example.com/health \
  -H "Origin: https://console.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -v 2>&1 | grep -i "access-control"

# Check ENGINE_CORS_ORIGINS in env
grep CORS /etc/engine/engine.env
```

### 7.3 Console Shows Errors

1. Open browser DevTools → Console
2. Check for:
   - CORS errors → Configure `ENGINE_CORS_ORIGINS`
   - 401 errors → Check auth configuration
   - Network errors → Check Engine is reachable

---

## 8. Performance Issues

### 8.1 Symptoms

- Slow API responses (>2s)
- High CPU/memory usage
- Timeouts

### 8.2 Diagnosis

```bash
# Check resource usage
htop
iostat -x 1 5

# Check Engine metrics
curl -s http://localhost:8001/health | jq '.metrics'

# Check ledger size
wc -l /var/lib/engine/data/institutions/*/audit_ledger.jsonl
du -sh /var/lib/engine/data/

# Check for slow queries in logs
journalctl -u engine | grep -E "duration.*[0-9]{4,}ms"
```

### 8.3 Mitigations

| Issue | Mitigation |
|-------|------------|
| Large ledger | Archive old events |
| Memory pressure | Increase RAM, restart |
| CPU bound | Scale horizontally |
| Disk I/O | Move to SSD |

---

## 9. Data Recovery

### 9.1 Restore from Backup

```bash
# List available backups
ls -la /var/lib/engine/backups/

# Stop engine
sudo systemctl stop engine

# Restore specific institution
sudo /home/bazari/engine/ops/scripts/restore_engine.sh \
  $INSTITUTION_ID \
  /var/lib/engine/backups/INST_ID-20260130-120000.tar.gz

# Start engine
sudo systemctl start engine

# Verify
curl -s http://localhost:8001/health | jq '.mode'
```

### 9.2 Point-in-Time Recovery

For critical data loss, contact the platform team with:
- Timestamp of last known good state
- Description of data loss
- Affected institution IDs

---

## 10. Communication

### 10.1 Internal Escalation

| Severity | Contact |
|----------|---------|
| P1 | On-call engineer + manager |
| P2 | On-call engineer |
| P3 | Team Slack channel |
| P4 | Issue tracker |

### 10.2 External Communication (if customer-facing)

1. Acknowledge the issue
2. Provide estimated time to resolution (if known)
3. Update regularly (every 30 min for P1)
4. Post-incident summary

### 10.3 Post-Incident

- [ ] Root cause identified
- [ ] Fix implemented
- [ ] Post-mortem scheduled
- [ ] Documentation updated
- [ ] Monitoring improved (if applicable)

---

## 11. Quick Reference

### Common Commands

```bash
# Health check
curl -s http://localhost:8001/health | jq '.'

# Service control
sudo systemctl status engine
sudo systemctl restart engine
sudo systemctl stop engine

# Logs
journalctl -u engine -f
journalctl -u engine -n 100 --no-pager

# Rollback
sudo /home/bazari/engine/ops/scripts/rollback_engine_bundle.sh

# Backup
sudo /home/bazari/engine/ops/scripts/backup_engine.sh $INST_ID

# Restore
sudo /home/bazari/engine/ops/scripts/restore_engine.sh $INST_ID /path/to/backup.tar.gz
```

### Key Files

| File | Purpose |
|------|---------|
| `/etc/engine/engine.env` | Environment config |
| `/var/lib/engine/bundles/CURRENT` | Active bundle |
| `/var/lib/engine/data/` | Institution data |
| `/var/log/engine/` | Log files |

### Emergency Contacts

| Role | Contact |
|------|---------|
| On-call engineer | [PagerDuty/OpsGenie] |
| Platform lead | [Contact] |
| Security team | [Contact] |
