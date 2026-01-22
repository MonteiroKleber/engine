# E2E Validation Report

**Timestamp:** 2026-01-21T18:14:37-03:00
**INSTITUTION_ID:** a38c63d0-4ceb-4630-8474-7d2ad5713ecf
**ENGINE_DATA_ROOT:** tmp/flows/run-20260121T201110Z/data
**ENGINE_BUNDLE_PATH:** tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/bundles/finance-pilot
**ENGINE_INSTALL_MODE:** prod
**ENGINE_AUTH_MODE:** strict

---


## A) Health Check

**Endpoint:** GET /health
**Status:** 200
**Response:**
```json
{"status":"ok","mode":"ACTIVE"}
```
**Result:** ✅ PASS

## B) Proof Verify (Offline)

**Command:** `python3 -m engine.proof verify "$ENGINE_BUNDLE_PATH" --json`
**Output:**
```json
{
  "passed": true,
  "error_code": null,
  "error_message": null,
  "bundle_name": "finance-pilot",
  "bundle_version": "1.0.0",
  "source_idl_sha256": "9ef76983753ab85c6b6435ce8583279bd2738f55137e2474d682d976d9a3274c",
  "manifest_hash": "27159fbfe7f3eb6322d1efae674bd92082d831982e83e6ab4b2c9459c1cc4275",
  "contracts_verified": 10,
  "details": {}
}
```
**Result:** ✅ PASS

## C) Agent Delegation (Bot on-behalf-of Operator)

**Endpoint:** POST /finance/expenses
**Headers:**
- X-Actor-Token: Hl8AqNqdFuOfFdgb7Cw8CBh***MASKED***
- X-On-Behalf-Of: 739bffc8-d000-4c90-9886-1c71eab001e3
- X-Institution-Id: a38c63d0-4ceb-4630-8474-7d2ad5713ecf
**Status Code:** 202
**Response:**
```json
{"status":"pending_approval","expense_id":"eff0e0c5-5d25-483c-93a3-e2877be34050","approval_id":"e400deb8-7309-42bd-8941-4e2e12736647","step":"APPROVAL:expense.create"}
```
**Approval ID:** `e400deb8-7309-42bd-8941-4e2e12736647`
**Result:** ✅ PASS

## D) Legacy Write Governed

**Endpoint:** POST /console/bridge/write/increase_limit
**Auth:** X-Admin-Token: 9Cfk1oMeO2ESCsDItKIhrCa***MASKED***
**Body:** multipart/form-data
**Status Code:** 403
**Response:**
```json
{"error":"LEGACY_WRITE_NO_APPROVAL_RULE_PROD","message":"No approval rule configured for this action in production mode","denied_by":"NO_APPROVAL_RULE","action_id":"beca3d60-2453-46fb-a841-705e3e7646e5"}
```

**Outbox Evidence:**
```

```
**Note:** 403 Forbidden as expected in prod mode without approval rule
**Result:** ✅ PASS

## E) Approvals Flow

### E.1) Create Expense as Operator
**Endpoint:** POST /finance/expenses
**Headers:** X-Actor-Token: _-EOGakgC5eNAzWtE8bK187***MASKED***, X-Institution-Id: a38c63d0-4ceb-4630-8474-7d2ad5713ecf
**Status Code:** 202
**Response:**
```json
{"status":"pending_approval","expense_id":"55911f68-ee8c-407e-aeb4-e285f3519f1a","approval_id":"0b928dd4-3418-4e44-a82d-e0acab6e665b","step":"APPROVAL:expense.create"}
```
**Approval ID:** `0b928dd4-3418-4e44-a82d-e0acab6e665b`

### E.2) Self-Approve Attempt (Expected: FAIL)
**Endpoint:** POST /approvals/0b928dd4-3418-4e44-a82d-e0acab6e665b/decide
**Headers:** X-Actor-Token: _-EOGakgC5eNAzWtE8bK187***MASKED*** (same as creator)
**Status Code:** 403
**Response:**
```json
{"code":"APPROVAL_FORBIDDEN","message":"Forbidden"}
```
**Note:** Self-approval correctly blocked ✅

### E.3) Manager Approval (Expected: SUCCESS)
**Endpoint:** POST /approvals/0b928dd4-3418-4e44-a82d-e0acab6e665b/decide
**Headers:** X-Actor-Token: LQNCYR6aHwHQlgokM6AkOFo***MASKED***
**Status Code:** 200
**Response:**
```json
{"status":"decided","approval_id":"0b928dd4-3418-4e44-a82d-e0acab6e665b","expense_id":"55911f68-ee8c-407e-aeb4-e285f3519f1a","decision":"approve","case_status":"COMMITTED"}
```
**Note:** Manager approval successful ✅
**Result:** ✅ PASS

## F) Data Paths Evidence

**Ledger files:**
```
tmp/flows/run-20260121T201110Z/data/ledger/audit_ledger.jsonl
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/bundles/finance-pilot/contract_ledger.json
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/audit_ledger.jsonl
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/tmp/flows/run-20260121T201110Z/data/ledger/audit_ledger.jsonl
```

**Outbox files:**
```
```

**State files:**
```
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/state_store.json
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/actors/actors_state.json
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/tmp/flows/run-20260121T201110Z/data/state_store/state_store.json
tmp/flows/run-20260121T201110Z/data/institutions/a38c63d0-4ceb-4630-8474-7d2ad5713ecf/depts/finance/legacy_bridge/write_state.json
```

## Summary

- **Passed:** 5
- **Failed:** 0
- **Total:** 5

**Overall:** ✅ ALL TESTS PASSED
