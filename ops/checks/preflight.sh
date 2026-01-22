#!/usr/bin/env bash
# Libervia Engine - Preflight Check Script
# Verifies environment and configuration before startup
#
# This script complements the Python preflight checks in src/engine/core/preflight.py
# which run at server startup. This shell script is for manual pre-deployment checks.
#
# Checks synchronized with preflight.py:
# - ENGINE_CONSOLE_SESSION_SECRET (required, min 32 chars)
# - ENGINE_ISE_ADMIN_TOKEN (required for admin endpoints)
# - Multi-tenant path isolation (absolute paths blocked)
# - Bundle manifest verification
# - Ledger integrity

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ((ERRORS++))
}

log_info() {
    echo -e "[INFO] $1"
}

echo "=============================================="
echo "Libervia Engine - Preflight Check"
echo "=============================================="
echo ""

# 1. Check REQUIRED environment variables (these cause hard fail in runtime)
echo "--- Required Environment Variables ---"

# ENGINE_CONSOLE_SESSION_SECRET - required by preflight.py
if [[ -n "${ENGINE_CONSOLE_SESSION_SECRET:-}" ]]; then
    SECRET_LEN=${#ENGINE_CONSOLE_SESSION_SECRET}
    if [[ $SECRET_LEN -ge 32 ]]; then
        log_ok "ENGINE_CONSOLE_SESSION_SECRET is set ($SECRET_LEN chars)"
    else
        log_error "ENGINE_CONSOLE_SESSION_SECRET is too short ($SECRET_LEN chars, min 32)"
    fi
else
    log_error "ENGINE_CONSOLE_SESSION_SECRET is NOT set (required for console auth)"
    log_info "  Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
fi

# ENGINE_ISE_ADMIN_TOKEN - required for admin endpoints
if [[ -n "${ENGINE_ISE_ADMIN_TOKEN:-}" ]]; then
    log_ok "ENGINE_ISE_ADMIN_TOKEN is set"
else
    log_error "ENGINE_ISE_ADMIN_TOKEN is NOT set (required for admin APIs)"
    log_info "  Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
fi

echo ""

# 2. Check optional environment variables
echo "--- Optional Environment Variables ---"

if [[ -n "${ENGINE_BUNDLE_PATH:-}" ]]; then
    log_ok "ENGINE_BUNDLE_PATH is set: $ENGINE_BUNDLE_PATH"
else
    log_warn "ENGINE_BUNDLE_PATH not set (will use default: bundles/finance-pilot)"
    ENGINE_BUNDLE_PATH="bundles/finance-pilot"
fi

if [[ -n "${ENGINE_DATA_ROOT:-}" ]]; then
    log_ok "ENGINE_DATA_ROOT is set: $ENGINE_DATA_ROOT"
else
    log_info "ENGINE_DATA_ROOT not set (will use default: var)"
fi

if [[ -n "${ENGINE_LEDGER_PATH:-}" ]]; then
    log_ok "ENGINE_LEDGER_PATH is set: $ENGINE_LEDGER_PATH"
else
    log_info "ENGINE_LEDGER_PATH not set (will use namespaced path per institution)"
    ENGINE_LEDGER_PATH="var/audit_ledger.jsonl"
fi

if [[ -n "${ENGINE_LOG_FORMAT:-}" ]]; then
    log_ok "ENGINE_LOG_FORMAT is set: $ENGINE_LOG_FORMAT"
else
    log_info "ENGINE_LOG_FORMAT not set (will use default: text)"
fi

echo ""

# 3. Multi-tenant path isolation check (matches preflight.py logic)
echo "--- Multi-Tenant Path Isolation ---"

# Check if any absolute paths are set that would break multi-tenant isolation
MULTI_TENANT_ISSUE=0

if [[ -n "${ENGINE_LEDGER_PATH:-}" ]] && [[ "${ENGINE_LEDGER_PATH:0:1}" == "/" ]]; then
    log_warn "ENGINE_LEDGER_PATH is absolute: $ENGINE_LEDGER_PATH"
    log_info "  This may break multi-tenant isolation if institutions use require_institution_header_for_runtime=true"
    MULTI_TENANT_ISSUE=1
fi

if [[ -n "${ENGINE_STATE_STORE_DIR:-}" ]] && [[ "${ENGINE_STATE_STORE_DIR:0:1}" == "/" ]]; then
    log_warn "ENGINE_STATE_STORE_DIR is absolute: $ENGINE_STATE_STORE_DIR"
    log_info "  This may break multi-tenant isolation if institutions use require_institution_header_for_runtime=true"
    MULTI_TENANT_ISSUE=1
fi

if [[ $MULTI_TENANT_ISSUE -eq 0 ]]; then
    log_ok "No multi-tenant path isolation issues detected"
fi

echo ""

# 4. Check paths exist
echo "--- Path Validation ---"

if [[ -d "$ENGINE_BUNDLE_PATH" ]]; then
    log_ok "Bundle directory exists: $ENGINE_BUNDLE_PATH"
else
    log_error "Bundle directory NOT FOUND: $ENGINE_BUNDLE_PATH"
fi

LEDGER_DIR=$(dirname "$ENGINE_LEDGER_PATH")
if [[ -d "$LEDGER_DIR" ]]; then
    log_ok "Ledger directory exists: $LEDGER_DIR"
    if [[ -w "$LEDGER_DIR" ]]; then
        log_ok "Ledger directory is writable"
    else
        log_error "Ledger directory is NOT writable: $LEDGER_DIR"
    fi
else
    log_warn "Ledger directory does not exist (will be created): $LEDGER_DIR"
fi

echo ""

# 5. Verify bundle manifest
echo "--- Bundle Manifest ---"

MANIFEST_PATH="$ENGINE_BUNDLE_PATH/bundle.manifest.json"
if [[ -f "$MANIFEST_PATH" ]]; then
    log_ok "Manifest file exists: $MANIFEST_PATH"

    # Verify it's valid JSON
    if python3 -c "import json; json.load(open('$MANIFEST_PATH'))" 2>/dev/null; then
        log_ok "Manifest is valid JSON"

        # Extract and verify contract hashes
        CONTRACTS=$(python3 -c "
import json
with open('$MANIFEST_PATH') as f:
    manifest = json.load(f)
for c in manifest.get('contracts', []):
    print(c.get('file', ''), c.get('sha256', ''), c.get('required', True))
" 2>/dev/null)

        while IFS=' ' read -r file sha256 required; do
            if [[ -n "$file" ]]; then
                CONTRACT_PATH="$ENGINE_BUNDLE_PATH/$file"
                if [[ -f "$CONTRACT_PATH" ]]; then
                    # Verify SHA-256 hash
                    ACTUAL_HASH=$(sha256sum "$CONTRACT_PATH" | cut -d' ' -f1)
                    EXPECTED_HASH=${sha256#SHA256:}

                    if [[ "$ACTUAL_HASH" == "$EXPECTED_HASH" ]]; then
                        log_ok "Contract $file: hash verified"
                    else
                        log_error "Contract $file: hash MISMATCH"
                        log_info "  Expected: $EXPECTED_HASH"
                        log_info "  Actual:   $ACTUAL_HASH"
                    fi
                elif [[ "$required" == "True" ]]; then
                    log_error "Required contract NOT FOUND: $file"
                else
                    log_warn "Optional contract not found: $file"
                fi
            fi
        done <<< "$CONTRACTS"
    else
        log_error "Manifest is NOT valid JSON"
    fi
else
    log_error "Manifest file NOT FOUND: $MANIFEST_PATH"
fi

echo ""

# 6. Verify ledger integrity (if exists)
echo "--- Ledger Verification ---"

if [[ -f "$ENGINE_LEDGER_PATH" ]]; then
    log_info "Ledger file exists: $ENGINE_LEDGER_PATH"

    # Count events
    EVENT_COUNT=$(wc -l < "$ENGINE_LEDGER_PATH")
    log_info "Ledger contains $EVENT_COUNT events"

    # Run Python verification
    VERIFY_RESULT=$(python3 -c "
import sys
sys.path.insert(0, 'src')
from pathlib import Path
from engine.core.ledger import verify_ledger_file

result = verify_ledger_file(Path('$ENGINE_LEDGER_PATH'))
if result.ok:
    print('OK')
else:
    print(f'FAIL:{result.code}:{result.message}')
" 2>/dev/null || echo "FAIL:SCRIPT_ERROR:Could not run verification")

    if [[ "$VERIFY_RESULT" == "OK" ]]; then
        log_ok "Ledger integrity verified"
    else
        CODE=$(echo "$VERIFY_RESULT" | cut -d':' -f2)
        MESSAGE=$(echo "$VERIFY_RESULT" | cut -d':' -f3-)
        log_error "Ledger verification FAILED: $CODE"
        log_info "  Message: $MESSAGE"
    fi
else
    log_info "Ledger file does not exist (will be created on first event)"
fi

echo ""

# 7. Check systemd unit (optional)
echo "--- Systemd Service ---"

if command -v systemctl &> /dev/null; then
    if systemctl list-unit-files | grep -q "engine.service"; then
        log_ok "engine.service unit file exists"

        if systemctl is-enabled engine.service &> /dev/null; then
            log_ok "engine.service is enabled"
        else
            log_warn "engine.service is NOT enabled"
        fi

        if systemctl is-active engine.service &> /dev/null; then
            log_info "engine.service is currently running"
        else
            log_info "engine.service is not running"
        fi
    else
        log_warn "engine.service unit file not found (optional)"
    fi
else
    log_info "systemctl not available (skipping service check)"
fi

echo ""

# Summary
echo "=============================================="
echo "Summary"
echo "=============================================="

if [[ $ERRORS -gt 0 ]]; then
    echo -e "${RED}PREFLIGHT FAILED${NC}"
    echo "  Errors:   $ERRORS"
    echo "  Warnings: $WARNINGS"
    echo ""
    echo "Please fix the errors above before starting the engine."
    exit 1
elif [[ $WARNINGS -gt 0 ]]; then
    echo -e "${YELLOW}PREFLIGHT PASSED WITH WARNINGS${NC}"
    echo "  Errors:   $ERRORS"
    echo "  Warnings: $WARNINGS"
    echo ""
    echo "Engine can start, but review the warnings above."
    exit 0
else
    echo -e "${GREEN}PREFLIGHT PASSED${NC}"
    echo "  Errors:   $ERRORS"
    echo "  Warnings: $WARNINGS"
    echo ""
    echo "Engine is ready to start."
    exit 0
fi
