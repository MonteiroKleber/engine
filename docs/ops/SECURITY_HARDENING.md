# Security Hardening Checklist — Libervia Engine

Version: 1.0 | Last Updated: 2026-01-30

## Overview

This document describes security configurations and hardening measures for Libervia Engine in production environments. Based on security audit findings from Fase 7.

---

## 1. Authentication Modes

### 1.1 Strict Mode (Production Required)

```bash
# /etc/engine/engine.env
ENGINE_AUTH_MODE=strict
```

**What strict mode enforces:**
- Requires `X-Actor-Token` header for all actor-authenticated requests
- Ignores `X-Actor-Id` and `X-Actor-Roles` headers (prevents spoofing)
- Validates tokens against the actor registry
- Emits `ACTOR_TOKEN_VERIFIED` event on successful auth

**What dev mode allows (DO NOT USE IN PRODUCTION):**
- Accepts `X-Actor-Id` and `X-Actor-Roles` headers without verification
- Emits `UNVERIFIED_IDENTITY_USED` warning event
- Suitable only for local development

### 1.2 Verification

```bash
# Check auth mode
curl -s http://localhost:8001/health | jq '.auth_mode'
# Expected in production: "strict"

# Test that header spoofing is rejected in strict mode
curl -X GET http://localhost:8001/v1/some-endpoint \
  -H "X-Actor-Id: fake-actor" \
  -H "X-Actor-Roles: admin"
# Expected: 401 Unauthorized (in strict mode)
# Expected: Request accepted (in dev mode - VULNERABLE)
```

---

## 2. Admin Authentication

### 2.1 Authentication Methods

| Method | Header | Use Case |
|--------|--------|----------|
| Admin Key | `X-Admin-Key` | Per-institution admin operations |
| Admin Token | `X-Admin-Token` | System-level operations (ISE, multi-tenant) |

### 2.2 Admin Endpoints Protected

All `/admin/*` endpoints require admin authentication:

| Endpoint | Method | Auth Required |
|----------|--------|---------------|
| `/admin/institutions` | POST | X-Admin-Token |
| `/admin/institutions/{id}/keys` | POST | X-Admin-Token or X-Admin-Key |
| `/admin/institutions/{id}/actors` | POST/GET | X-Admin-Key |
| `/admin/institutions/{id}/depts` | GET | X-Admin-Key |
| `/admin/institutions/{id}/depts/{id}/activate` | POST | X-Admin-Key |
| `/admin/institutions/{id}/depts/{id}/deactivate` | POST | X-Admin-Key |

### 2.3 Fixed Vulnerability (Fase 7)

**Issue:** `admin_depts.py` endpoints had broken authentication (function passed as default instead of called).

**Fix Applied:** All three endpoints now properly call `require_admin_auth(request, institution_id)`.

**Verification:**
```bash
# Attempt unauthenticated access
curl -X GET http://localhost:8001/admin/institutions/test-id/depts
# Expected: 401 Unauthorized

# With valid admin key
curl -X GET http://localhost:8001/admin/institutions/test-id/depts \
  -H "X-Admin-Key: valid-key"
# Expected: 200 OK (if institution exists)
```

---

## 3. Install Mode

### 3.1 Production Mode

```bash
# /etc/engine/engine.env
ENGINE_INSTALL_MODE=prod
```

**What prod mode enforces:**
- Requires `ENGINE_ISE_ADMIN_TOKEN` to be set
- Requires `ENGINE_AUTH_MODE=strict`
- Creates new institutions with secure default configurations
- Preflight check fails if requirements not met

### 3.2 Preflight Validation

```bash
# Run preflight check
/home/bazari/engine/ops/checks/preflight.sh

# Expected output for production:
# ✓ ENGINE_INSTALL_MODE=prod
# ✓ ENGINE_AUTH_MODE=strict
# ✓ ENGINE_ISE_ADMIN_TOKEN is set
# ✓ All checks passed
```

---

## 4. RBAC (Role-Based Access Control)

### 4.1 Configuration

RBAC policies are defined in the bundle's `rbac.json`:

```json
{
  "policies": [
    {
      "name": "ceo_approve",
      "roles": ["ceo", "cfo"],
      "permissions": ["expense.approve"],
      "conditions": {}
    }
  ]
}
```

### 4.2 Gate Behavior

- If no RBAC policy exists for a permission, access is **DENIED** (fail-closed)
- All RBAC decisions are logged to the ledger as `RBAC_DECISION` events
- Policies are loaded at startup from the bundle

### 4.3 Verification

```bash
# Check RBAC events in ledger
curl -s http://localhost:8001/v1/observe/ledger/events?event_type=RBAC_DECISION \
  -H "X-Institution-Id: $INST_ID" \
  -H "X-Admin-Key: $ADMIN_KEY" | jq '.events[:3]'
```

---

## 5. Approval Workflows

### 5.1 Separation of Duties (SoD)

The approval system enforces SoD:
- Requesters cannot approve their own requests
- Quorum rules can require multiple approvers
- All decisions logged to ledger

### 5.2 Approval Events

| Event Type | Description |
|------------|-------------|
| `APPROVAL_REQUESTED` | New approval request created |
| `APPROVAL_DECIDED` | Approval granted or rejected |
| `APPROVAL_SoD_VIOLATION` | Attempt to self-approve blocked |

---

## 6. Ledger Integrity

### 6.1 Hash Chain

The audit ledger uses a hash chain for tamper detection:
- Each event includes the hash of the previous event
- Startup verifies the entire chain
- Tampering triggers `SAFE_MODE`

### 6.2 Verification

```bash
# Verify ledger integrity
python -c "
from engine.core.ledger import verify_ledger_file
from pathlib import Path
result = verify_ledger_file(Path('/var/lib/engine/data/institutions/INST_ID/audit_ledger.jsonl'))
print(f'OK: {result.ok}, Code: {result.code}')
"
```

### 6.3 Tampering Response

If tampering is detected:
1. Engine enters `SAFE_MODE`
2. Write operations are blocked
3. Alert: `LEDGER_TAMPER_DETECTED`
4. **Do not modify the ledger** - preserve for forensics

---

## 7. Network Security

### 7.1 Internal vs External Access

| Endpoint | Internal | External |
|----------|----------|----------|
| `/health` | Yes | Yes (read-only) |
| `/admin/*` | Yes | No |
| `/v1/*` | Yes | Via proxy with auth |

### 7.2 Recommended Architecture

```
[Internet] → [nginx/Caddy HTTPS] → [Engine :8001 HTTP internal]
                    ↓
            [Console static files]
```

### 7.3 Firewall Rules

```bash
# Allow only internal access to Engine
ufw allow from 10.0.0.0/8 to any port 8001
ufw allow from 172.16.0.0/12 to any port 8001
ufw allow from 192.168.0.0/16 to any port 8001
# Block external access
ufw deny 8001
```

---

## 8. Secrets Management

### 8.1 Required Secrets

| Secret | Purpose | Storage |
|--------|---------|---------|
| `ENGINE_CONSOLE_SESSION_SECRET` | Cookie signing | env file |
| `ENGINE_ISE_ADMIN_TOKEN` | System admin | env file |
| Per-institution admin keys | Institution admin | secure vault |
| Actor tokens | User/agent auth | secure vault |

### 8.2 Best Practices

- [ ] Never commit secrets to version control
- [ ] Rotate secrets on suspected compromise
- [ ] Use environment files with restricted permissions (600)
- [ ] Consider secrets manager (Vault, AWS Secrets Manager, etc.)

```bash
# Set proper permissions on env file
chmod 600 /etc/engine/engine.env
chown root:root /etc/engine/engine.env
```

---

## 9. Console Security

### 9.1 Known Architecture Decision

**Current:** Admin credentials passed via environment variables to Console.

**Risk:** `VITE_` prefixed variables are embedded in the browser bundle.

**Mitigation Options:**
1. **Backend proxy** (Recommended): Implement a backend service that holds admin credentials and proxies admin requests
2. **Actor tokens only**: Console uses only actor tokens, admin ops via CLI
3. **Session-based**: Use Engine's console session endpoints

### 9.2 Checklist

- [ ] No admin credentials in production frontend build
- [ ] HTTPS enforced (secure cookies)
- [ ] CSP headers configured
- [ ] CORS restricted to Console domain only

---

## 10. Monitoring & Alerting

### 10.1 Security Events to Monitor

| Event | Severity | Action |
|-------|----------|--------|
| `ADMIN_AUTH_FAILED` | High | Alert, investigate |
| `RBAC_DECISION` (denied) | Medium | Log, review patterns |
| `UNVERIFIED_IDENTITY_USED` | Critical | Should not occur in prod |
| `SAFE_MODE` activated | Critical | Page on-call |
| `LEDGER_TAMPER_DETECTED` | Critical | Page on-call, forensics |
| `APPROVAL_SoD_VIOLATION` | High | Alert, investigate |

### 10.2 Log Queries

```bash
# Failed admin auth attempts
journalctl -u engine | jq 'select(.event_type == "ADMIN_AUTH_FAILED")'

# Unverified identity (should be zero in prod)
journalctl -u engine | jq 'select(.event_type == "UNVERIFIED_IDENTITY_USED")'

# Denied RBAC decisions
journalctl -u engine | jq 'select(.event_type == "RBAC_DECISION" and .allowed == false)'
```

---

## 11. Security Checklist Summary

### Critical (Must Have)

- [ ] `ENGINE_AUTH_MODE=strict`
- [ ] `ENGINE_INSTALL_MODE=prod`
- [ ] Admin endpoints require authentication
- [ ] HTTPS for all external traffic
- [ ] Secrets not in version control

### High (Should Have)

- [ ] Firewall restricts Engine port
- [ ] Ledger integrity verified on startup
- [ ] Security events monitored
- [ ] Secrets rotated periodically

### Medium (Nice to Have)

- [ ] Backend proxy for admin operations
- [ ] Rate limiting configured
- [ ] IP allowlisting for admin endpoints
- [ ] Penetration testing completed

---

## Appendix: Vulnerability History

### Fixed in Fase 7 (2026-01-30)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| F7-001 | Critical | `admin_depts.py` auth bypass | Proper `require_admin_auth()` calls |
| F7-002 | Medium | Console `useEngine` import broken | Changed to `useEngineApi` |

### Known Limitations (Not Vulnerabilities)

| Item | Description | Mitigation |
|------|-------------|------------|
| Dev mode default | Code defaults to dev mode | Production env must set `strict` |
| Console admin creds | Frontend can hold admin keys | Use backend proxy |
