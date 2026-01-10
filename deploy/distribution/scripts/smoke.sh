#!/bin/bash
# smoke.sh - Smoke tests for Bazari Engine distribution
#
# Verifies:
#   1. Services are running and healthy
#   2. Engine version command works
#   3. Wizard (if available) responds
#   4. Basic functionality test
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed
#
# Usage:
#   ./scripts/smoke.sh
#   ./scripts/smoke.sh --verbose

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

VERBOSE=false
TESTS_PASSED=0
TESTS_FAILED=0

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

test_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

test_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Change to deploy directory
cd "$DEPLOY_DIR"

log_info "Running smoke tests for Bazari Engine distribution..."
log_info "Deploy directory: $DEPLOY_DIR"
echo ""

# =============================================================================
# Test 1: Docker Compose Config Valid
# =============================================================================
log_test "Test 1: Docker Compose configuration is valid"
if docker compose config --quiet 2>/dev/null; then
    test_pass "docker-compose.yml is valid"
else
    test_fail "docker-compose.yml is invalid"
fi

# =============================================================================
# Test 2: Services Running
# =============================================================================
log_test "Test 2: Services are running"
if docker compose ps --status running 2>/dev/null | grep -q "engine"; then
    test_pass "Engine service is running"
else
    test_fail "Engine service is not running"
fi

# =============================================================================
# Test 3: Engine Health Check
# =============================================================================
log_test "Test 3: Engine container is healthy"
HEALTH=$(docker inspect --format='{{.State.Health.Status}}' bazari-engine 2>/dev/null || echo "unknown")
if [[ "$HEALTH" == "healthy" ]]; then
    test_pass "Engine container is healthy"
elif [[ "$HEALTH" == "starting" ]]; then
    log_warn "Engine container still starting, waiting..."
    sleep 10
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' bazari-engine 2>/dev/null || echo "unknown")
    if [[ "$HEALTH" == "healthy" ]]; then
        test_pass "Engine container is healthy (after wait)"
    else
        test_fail "Engine container health: $HEALTH"
    fi
else
    test_fail "Engine container health: $HEALTH"
fi

# =============================================================================
# Test 4: Engine Version
# =============================================================================
log_test "Test 4: Engine version command"
VERSION_OUTPUT=$(docker exec bazari-engine python -c "from version import __version__; print(__version__)" 2>&1 || echo "ERROR")
if [[ "$VERSION_OUTPUT" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    test_pass "Engine version: $VERSION_OUTPUT"
else
    test_fail "Engine version failed: $VERSION_OUTPUT"
fi

# =============================================================================
# Test 5: Python Environment
# =============================================================================
log_test "Test 5: Python environment is functional"
PYTHON_TEST=$(docker exec bazari-engine python -c "import json, yaml, jsonschema; print('OK')" 2>&1 || echo "ERROR")
if [[ "$PYTHON_TEST" == "OK" ]]; then
    test_pass "Python dependencies available"
else
    test_fail "Python dependencies missing: $PYTHON_TEST"
fi

# =============================================================================
# Test 6: Wizard Module (if available)
# =============================================================================
log_test "Test 6: Wizard module is importable"
WIZARD_TEST=$(docker exec bazari-engine python -c "from wizard.wizard_cli import main; print('OK')" 2>&1 || echo "ERROR")
if [[ "$WIZARD_TEST" == "OK" ]]; then
    test_pass "Wizard module available"
else
    log_warn "Wizard module not available: $WIZARD_TEST"
    # Not a failure - wizard is optional
    test_pass "Wizard module check (optional component)"
fi

# =============================================================================
# Test 7: Data Volume Mounted
# =============================================================================
log_test "Test 7: Data volume is writable"
VOLUME_TEST=$(docker exec bazari-engine bash -c "touch /data/.smoke_test && rm /data/.smoke_test && echo OK" 2>&1 || echo "ERROR")
if [[ "$VOLUME_TEST" == "OK" ]]; then
    test_pass "Data volume is writable"
else
    test_fail "Data volume not writable: $VOLUME_TEST"
fi

# =============================================================================
# Test 8: Logs Volume Mounted
# =============================================================================
log_test "Test 8: Logs volume is writable"
LOGS_TEST=$(docker exec bazari-engine bash -c "touch /logs/.smoke_test && rm /logs/.smoke_test && echo OK" 2>&1 || echo "ERROR")
if [[ "$LOGS_TEST" == "OK" ]]; then
    test_pass "Logs volume is writable"
else
    test_fail "Logs volume not writable: $LOGS_TEST"
fi

# =============================================================================
# Test 9: Engine Source Mounted
# =============================================================================
log_test "Test 9: Engine source is mounted"
SOURCE_TEST=$(docker exec bazari-engine bash -c "test -f /app/engine/VERSION && cat /app/engine/VERSION" 2>&1 || echo "ERROR")
if [[ "$SOURCE_TEST" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    test_pass "Engine source mounted (VERSION: $SOURCE_TEST)"
else
    test_fail "Engine source not mounted properly: $SOURCE_TEST"
fi

# =============================================================================
# Test 10: Telemetry Module
# =============================================================================
log_test "Test 10: Telemetry module is available"
TELEMETRY_TEST=$(docker exec bazari-engine python -c "from observability.telemetry import TelemetryEmitter; print('OK')" 2>&1 || echo "ERROR")
if [[ "$TELEMETRY_TEST" == "OK" ]]; then
    test_pass "Telemetry module available"
else
    test_fail "Telemetry module not available: $TELEMETRY_TEST"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "=============================================="
echo "SMOKE TEST SUMMARY"
echo "=============================================="
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    log_info "All smoke tests PASSED!"
    exit 0
else
    log_error "$TESTS_FAILED smoke test(s) FAILED"
    exit 1
fi
