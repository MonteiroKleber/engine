#!/usr/bin/env bash
set -euo pipefail

# Load env produced by Codex
source "$(dirname "$0")/run.env"

PORT=${PORT:-8001}
HOST=${HOST:-127.0.0.1}
BASE="http://$HOST:$PORT"

export PYTHONPATH="/home/bazari/engine/src"
export ENGINE_DATA_ROOT ENGINE_INSTALL_MODE ENGINE_AUTH_MODE ENGINE_ISE_ADMIN_TOKEN ENGINE_CONSOLE_SESSION_SECRET ENGINE_BUNDLE_PATH

# Optional: keep global ledger/state store inside data root (recommended for clean runs)
export ENGINE_LEDGER_PATH="$ENGINE_DATA_ROOT/ledger/audit_ledger.jsonl"
export ENGINE_STATE_STORE_DIR="$ENGINE_DATA_ROOT/state_store"

echo "Starting engine on $BASE"
python3 -m uvicorn engine.api.server:app --host "$HOST" --port "$PORT" --log-level info &
ENGINE_PID=$!
echo $ENGINE_PID > "$(dirname "$0")/engine.pid"

cleanup() {
  echo "Stopping engine pid=$ENGINE_PID"
  kill "$ENGINE_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 1

echo "Health:" 
curl -sS "$BASE/health"; echo

echo "Create expense (operator)" 
EXPENSE_RES=$(curl -sS -X POST "$BASE/finance/expenses" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "X-Institution-Id: $INSTITUTION_ID" \
  -H "Content-Type: application/json" \
  -d '{"amount":2500.00,"currency":"BRL","description":"Test expense"}')

echo "$EXPENSE_RES" | python3 -m json.tool
APPROVAL_ID=$(echo "$EXPENSE_RES" | python3 - <<'PY'
import json,sys
obj=json.load(sys.stdin)
print(obj.get('approval_id') or '')
PY
)

if [ -z "$APPROVAL_ID" ]; then
  echo "ERROR: approval_id missing in response" >&2
  exit 1
fi

echo "Try self-approve as operator (should fail)"
set +e
curl -sS -X POST "$BASE/approvals/$APPROVAL_ID/decide" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "X-Institution-Id: $INSTITUTION_ID" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve","comment":"self-approve"}' | python3 -m json.tool
set -e

echo "Approve as manager (should commit)"
curl -sS -X POST "$BASE/approvals/$APPROVAL_ID/decide" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "X-Institution-Id: $INSTITUTION_ID" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve","comment":"approved"}' | python3 -m json.tool

echo "Offline proof (bundle)"
python3 -m engine.proof verify "$ENGINE_BUNDLE_PATH" --json | python3 -m json.tool

echo "Done. Ledger path: $ENGINE_DATA_ROOT/institutions/$INSTITUTION_ID/audit_ledger.jsonl"
