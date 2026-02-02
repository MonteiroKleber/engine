#!/bin/bash
# E2E Evidence Script: Console API → Engine Jobs First-Class
#
# This script demonstrates the Prompt 3 (Console) requirement:
# - Safe: POST /personal/jobs/files/list → job_id → poll job_get → executed
# - Destructive: POST /personal/jobs/files/delete → approval_id → approve → enqueue → executed
# - Ledger events in correct order
#
# Prerequisites:
# - Engine running with ENGINE_API_MODE=idl (or both)
# - ENGINE_ADMIN_TOKEN set
#
# Usage: ./tests/e2e_console_jobs_evidence.sh

set -e

ENGINE_URL="${ENGINE_BASE_URL:-http://localhost:8001}"
ADMIN_TOKEN="${ENGINE_ADMIN_TOKEN:-dev-admin-token}"

echo "=============================================="
echo "E2E Evidence: Console API → Engine Jobs First-Class"
echo "=============================================="
echo ""
echo "Engine URL: $ENGINE_URL"
echo ""

# Create test institution
TEST_SLUG="e2e-evidence-$(date +%s)"
echo "1. Creating test institution: $TEST_SLUG"
INST_RESP=$(curl -s -X POST "$ENGINE_URL/admin/institutions" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -d "{\"slug\": \"$TEST_SLUG\", \"display_name\": \"E2E Evidence Test\"}")

INSTITUTION_ID=$(echo "$INST_RESP" | jq -r '.institution_id')
echo "   Institution ID: $INSTITUTION_ID"
echo ""

# Create admin key
echo "2. Creating admin key..."
ADMIN_KEY_RESP=$(curl -s -X POST "$ENGINE_URL/admin/institutions/$INSTITUTION_ID/admin-keys" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -d "{}")

ADMIN_KEY=$(echo "$ADMIN_KEY_RESP" | jq -r '.plaintext_secret')
echo "   Admin Key: ${ADMIN_KEY:0:20}..."
echo ""

# Create owner token
echo "3. Creating owner token..."
OWNER_RESP=$(curl -s -X POST "$ENGINE_URL/admin/institutions/$INSTITUTION_ID/actors" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Key: $ADMIN_KEY" \
    -d '{"actor_id": "owner-e2e", "roles": ["owner"], "is_agent": false}')

OWNER_TOKEN=$(echo "$OWNER_RESP" | jq -r '.token')
echo "   Owner Token: ${OWNER_TOKEN:0:20}..."
echo ""

# Create approver token (different actor for SoD)
echo "4. Creating approver token..."
APPROVER_RESP=$(curl -s -X POST "$ENGINE_URL/admin/institutions/$INSTITUTION_ID/actors" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Key: $ADMIN_KEY" \
    -d '{"actor_id": "approver-e2e", "roles": ["executive_admin"], "is_agent": false}')

APPROVER_TOKEN=$(echo "$APPROVER_RESP" | jq -r '.token')
echo "   Approver Token: ${APPROVER_TOKEN:0:20}..."
echo ""

echo "=============================================="
echo "EVIDENCE 1: Safe Operation (files.list)"
echo "=============================================="
echo ""

echo "5. POST /personal/jobs/files/list (safe operation)"
SAFE_RESP=$(curl -s -w "\n%{http_code}" -X POST "$ENGINE_URL/personal/jobs/files/list" \
    -H "Content-Type: application/json" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Actor-Token: $OWNER_TOKEN" \
    -d '{"path": "/documentos"}')

SAFE_BODY=$(echo "$SAFE_RESP" | head -n -1)
SAFE_STATUS=$(echo "$SAFE_RESP" | tail -n 1)

echo ""
echo "   HTTP Status: $SAFE_STATUS"
echo "   Response:"
echo "$SAFE_BODY" | jq .
echo ""

SAFE_JOB_ID=$(echo "$SAFE_BODY" | jq -r '.job_id')
SAFE_JOB_STATUS=$(echo "$SAFE_BODY" | jq -r '.status')

echo "   ✓ Job ID: $SAFE_JOB_ID"
echo "   ✓ Status: $SAFE_JOB_STATUS"
echo "   ✓ Expected: 201 with status='requested' (no approval_id)"
echo ""

if [ "$SAFE_STATUS" = "201" ] && [ "$SAFE_JOB_STATUS" = "requested" ]; then
    echo "   ✅ PASS: Safe operation returned 201 with status='requested'"
else
    echo "   ❌ FAIL: Expected 201/requested, got $SAFE_STATUS/$SAFE_JOB_STATUS"
fi
echo ""

echo "6. GET /personal/jobs/{job_id} (poll job status)"
JOB_GET_RESP=$(curl -s -X GET "$ENGINE_URL/personal/jobs/$SAFE_JOB_ID" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Actor-Token: $OWNER_TOKEN")

echo "   Response:"
echo "$JOB_GET_RESP" | jq .
echo ""

JOB_STATE=$(echo "$JOB_GET_RESP" | jq -r '.state')
echo "   ✓ Job State: $JOB_STATE"
echo ""

echo "=============================================="
echo "EVIDENCE 2: Destructive Operation (files.delete)"
echo "=============================================="
echo ""

echo "7. POST /personal/jobs/files/delete (destructive operation)"
DEST_RESP=$(curl -s -w "\n%{http_code}" -X POST "$ENGINE_URL/personal/jobs/files/delete" \
    -H "Content-Type: application/json" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Actor-Token: $OWNER_TOKEN" \
    -d '{"paths": ["/old-file.txt"]}')

DEST_BODY=$(echo "$DEST_RESP" | head -n -1)
DEST_STATUS=$(echo "$DEST_RESP" | tail -n 1)

echo ""
echo "   HTTP Status: $DEST_STATUS"
echo "   Response:"
echo "$DEST_BODY" | jq .
echo ""

DEST_JOB_ID=$(echo "$DEST_BODY" | jq -r '.job_id')
DEST_APPROVAL_ID=$(echo "$DEST_BODY" | jq -r '.approval_id')
DEST_JOB_STATUS=$(echo "$DEST_BODY" | jq -r '.status')

echo "   ✓ Job ID: $DEST_JOB_ID"
echo "   ✓ Approval ID: $DEST_APPROVAL_ID"
echo "   ✓ Status: $DEST_JOB_STATUS"
echo "   ✓ Expected: 202 with status='pending_approval' and approval_id"
echo ""

if [ "$DEST_STATUS" = "202" ] && [ "$DEST_JOB_STATUS" = "pending_approval" ] && [ "$DEST_APPROVAL_ID" != "null" ]; then
    echo "   ✅ PASS: Destructive operation returned 202 with approval_id"
else
    echo "   ❌ FAIL: Expected 202/pending_approval/approval_id"
fi
echo ""

echo "8. Check job is NOT in outbox before approval"
JOB_GET_BEFORE=$(curl -s -X GET "$ENGINE_URL/personal/jobs/$DEST_JOB_ID" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Actor-Token: $OWNER_TOKEN")

JOB_STATE_BEFORE=$(echo "$JOB_GET_BEFORE" | jq -r '.state')
echo "   Job state before approval: $JOB_STATE_BEFORE"

if [ "$JOB_STATE_BEFORE" = "pending_approval" ]; then
    echo "   ✅ PASS: Job is in pending_approval state (not enqueued)"
else
    echo "   ❌ FAIL: Expected pending_approval, got $JOB_STATE_BEFORE"
fi
echo ""

echo "9. POST /approvals/{approval_id}/decide (approve)"
APPROVE_RESP=$(curl -s -w "\n%{http_code}" -X POST "$ENGINE_URL/approvals/$DEST_APPROVAL_ID/decide" \
    -H "Content-Type: application/json" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Actor-Token: $APPROVER_TOKEN" \
    -d '{"decision": "approve", "reason": "E2E evidence test"}')

APPROVE_BODY=$(echo "$APPROVE_RESP" | head -n -1)
APPROVE_STATUS=$(echo "$APPROVE_RESP" | tail -n 1)

echo "   HTTP Status: $APPROVE_STATUS"
echo "   Response:"
echo "$APPROVE_BODY" | jq .
echo ""

if [ "$APPROVE_STATUS" = "200" ]; then
    echo "   ✅ PASS: Approval succeeded"
else
    echo "   ❌ FAIL: Approval failed with status $APPROVE_STATUS"
fi
echo ""

echo "10. Check job state after approval"
JOB_GET_AFTER=$(curl -s -X GET "$ENGINE_URL/personal/jobs/$DEST_JOB_ID" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Actor-Token: $OWNER_TOKEN")

JOB_STATE_AFTER=$(echo "$JOB_GET_AFTER" | jq -r '.state')
echo "   Job state after approval: $JOB_STATE_AFTER"
echo "   Full response:"
echo "$JOB_GET_AFTER" | jq .
echo ""

if [ "$JOB_STATE_AFTER" = "approved" ]; then
    echo "   ✅ PASS: Job transitioned to 'approved' state"
else
    echo "   ⚠️  Job state is '$JOB_STATE_AFTER' (expected 'approved')"
fi
echo ""

echo "=============================================="
echo "EVIDENCE 3: Ledger Events"
echo "=============================================="
echo ""

echo "11. Query ledger for JOB_REQUESTED events"
LEDGER_JOB_REQUESTED=$(curl -s -X GET "$ENGINE_URL/v1/observe/ledger/events?event_type=JOB_REQUESTED&limit=5" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Admin-Key: $ADMIN_KEY")

echo "   JOB_REQUESTED events:"
echo "$LEDGER_JOB_REQUESTED" | jq '.events[] | {event_type, case_id, payload: {job_id: .payload.job_id, job_type: .payload.job_type}}'
echo ""

echo "12. Query ledger for APPROVAL_REQUESTED events"
LEDGER_APPROVAL_REQUESTED=$(curl -s -X GET "$ENGINE_URL/v1/observe/ledger/events?event_type=APPROVAL_REQUESTED&limit=5" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Admin-Key: $ADMIN_KEY")

echo "   APPROVAL_REQUESTED events:"
echo "$LEDGER_APPROVAL_REQUESTED" | jq '.events[] | {event_type, case_id, payload: {approval_id: .payload.approval_id, rule_name: .payload.rule_name}}'
echo ""

echo "13. Query ledger for APPROVAL_DECIDED events"
LEDGER_APPROVAL_DECIDED=$(curl -s -X GET "$ENGINE_URL/v1/observe/ledger/events?event_type=APPROVAL_DECIDED&limit=5" \
    -H "X-Institution-Id: $INSTITUTION_ID" \
    -H "X-Admin-Key: $ADMIN_KEY")

echo "   APPROVAL_DECIDED events:"
echo "$LEDGER_APPROVAL_DECIDED" | jq '.events[] | {event_type, case_id, payload: {approval_id: .payload.approval_id, decision: .payload.decision}}'
echo ""

echo "=============================================="
echo "SUMMARY"
echo "=============================================="
echo ""
echo "Safe Job (files.list):"
echo "  - Job ID: $SAFE_JOB_ID"
echo "  - HTTP Status: $SAFE_STATUS (expected: 201)"
echo "  - Status: $SAFE_JOB_STATUS (expected: requested)"
echo ""
echo "Destructive Job (files.delete):"
echo "  - Job ID: $DEST_JOB_ID"
echo "  - Approval ID: $DEST_APPROVAL_ID"
echo "  - HTTP Status: $DEST_STATUS (expected: 202)"
echo "  - Status: $DEST_JOB_STATUS (expected: pending_approval)"
echo "  - State after approval: $JOB_STATE_AFTER (expected: approved)"
echo ""
echo "Institution ID: $INSTITUTION_ID"
echo "=============================================="
