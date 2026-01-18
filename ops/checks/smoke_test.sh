#!/bin/bash
# Smoke test for Libervia Engine production deployment
# Run as: ./smoke_test.sh

set -e

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
LEDGER_PATH="${ENGINE_LEDGER_PATH:-/var/lib/engine/audit_ledger.jsonl}"
STATE_PATH="${ENGINE_STATE_PATH:-/var/lib/engine/state_store.json}"

ANALYST_ID="$(cat /proc/sys/kernel/random/uuid)"
MANAGER_ID="$(cat /proc/sys/kernel/random/uuid)"

echo "=== Libervia Engine Smoke Test ==="
echo "Base URL: $BASE_URL"
echo "Analyst ID: $ANALYST_ID"
echo "Manager ID: $MANAGER_ID"
echo ""

# Test 1: Health check
echo "Test 1: Health check..."
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/health")
HEALTH_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
HEALTH_BODY=$(echo "$HEALTH_RESPONSE" | head -n -1)

if [ "$HEALTH_CODE" != "200" ]; then
    echo "FAILED: Health check returned $HEALTH_CODE"
    echo "Response: $HEALTH_BODY"
    exit 1
fi

if ! echo "$HEALTH_BODY" | grep -q '"status":"ok"'; then
    echo "FAILED: Health check response invalid"
    echo "Response: $HEALTH_BODY"
    exit 1
fi
echo "PASSED: Health check OK"
echo ""

# Test 2: Create expense
echo "Test 2: Create expense..."
CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$BASE_URL/finance/expenses" \
    -H "Content-Type: application/json" \
    -H "X-Actor-Id: $ANALYST_ID" \
    -H "X-Actor-Roles: analyst" \
    -d '{"amount": 100, "description": "Smoke test expense"}')
CREATE_CODE=$(echo "$CREATE_RESPONSE" | tail -1)
CREATE_BODY=$(echo "$CREATE_RESPONSE" | head -n -1)

if [ "$CREATE_CODE" != "202" ]; then
    echo "FAILED: Create expense returned $CREATE_CODE"
    echo "Response: $CREATE_BODY"
    exit 1
fi

APPROVAL_ID=$(echo "$CREATE_BODY" | grep -o '"approval_id":"[^"]*"' | cut -d'"' -f4)
EXPENSE_ID=$(echo "$CREATE_BODY" | grep -o '"expense_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$APPROVAL_ID" ]; then
    echo "FAILED: No approval_id in response"
    echo "Response: $CREATE_BODY"
    exit 1
fi
echo "PASSED: Expense created (expense_id=$EXPENSE_ID, approval_id=$APPROVAL_ID)"
echo ""

# Test 3: Approve expense
echo "Test 3: Approve expense..."
APPROVE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$BASE_URL/approvals/$APPROVAL_ID/decide" \
    -H "Content-Type: application/json" \
    -H "X-Actor-Id: $MANAGER_ID" \
    -H "X-Actor-Roles: manager" \
    -d '{"decision": "approve", "reason": "Smoke test approval"}')
APPROVE_CODE=$(echo "$APPROVE_RESPONSE" | tail -1)
APPROVE_BODY=$(echo "$APPROVE_RESPONSE" | head -n -1)

if [ "$APPROVE_CODE" != "200" ]; then
    echo "FAILED: Approve returned $APPROVE_CODE"
    echo "Response: $APPROVE_BODY"
    exit 1
fi

if ! echo "$APPROVE_BODY" | grep -q '"case_status":"COMMITTED"'; then
    echo "FAILED: case_status is not COMMITTED"
    echo "Response: $APPROVE_BODY"
    exit 1
fi
echo "PASSED: Expense approved and committed"
echo ""

# Test 4: Check ledger file exists
echo "Test 4: Check ledger file..."
if [ ! -f "$LEDGER_PATH" ]; then
    echo "FAILED: Ledger file not found at $LEDGER_PATH"
    exit 1
fi
echo "PASSED: Ledger file exists at $LEDGER_PATH"
echo ""

# Test 5: Check state store file exists
echo "Test 5: Check state store file..."
if [ ! -f "$STATE_PATH" ]; then
    echo "FAILED: State store file not found at $STATE_PATH"
    exit 1
fi
echo "PASSED: State store file exists at $STATE_PATH"
echo ""

echo "=== All smoke tests PASSED ==="
exit 0
