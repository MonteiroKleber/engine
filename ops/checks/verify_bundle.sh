#!/bin/bash
# Verify bundle integrity before activation
# Usage: verify_bundle.sh <bundle_path>
# Exit 0 if valid, non-zero if invalid
#
# Supports both single-department and multi-department bundles:
# - Single mode: flat structure with rbac.json, workflows.json, etc.
# - Multi mode: departments/<dept_id>/ subdirectories + contracts.json

set -e

BUNDLE_PATH="${1:?Usage: verify_bundle.sh <bundle_path>}"

echo "=== Verifying bundle: $BUNDLE_PATH ==="

# Check bundle directory exists
if [ ! -d "$BUNDLE_PATH" ]; then
    echo "ERROR: Bundle directory does not exist: $BUNDLE_PATH"
    exit 1
fi

MANIFEST_PATH="$BUNDLE_PATH/bundle.manifest.json"
ERRORS=0

# 1. Check manifest exists
echo "Checking manifest..."
if [ ! -f "$MANIFEST_PATH" ]; then
    echo "ERROR: bundle.manifest.json not found"
    exit 1
fi

# 2. Validate manifest is valid JSON
if ! python3 -c "import json; json.load(open('$MANIFEST_PATH'))" 2>/dev/null; then
    echo "ERROR: bundle.manifest.json is not valid JSON"
    exit 1
fi
echo "  manifest.json: OK"

# 3. Detect mode (single vs multi)
BUNDLE_MODE=$(python3 -c "
import json
manifest = json.load(open('$MANIFEST_PATH'))
print(manifest.get('mode', 'single'))
")
echo "  Bundle mode: $BUNDLE_MODE"

# 4. Check contract_ledger.json exists (required for ledger operations)
echo "Checking contract_ledger.json..."
if [ ! -f "$BUNDLE_PATH/contract_ledger.json" ]; then
    echo "  ERROR: contract_ledger.json not found"
    ERRORS=$((ERRORS + 1))
else
    if ! python3 -c "import json; json.load(open('$BUNDLE_PATH/contract_ledger.json'))" 2>/dev/null; then
        echo "  ERROR: contract_ledger.json is not valid JSON"
        ERRORS=$((ERRORS + 1))
    else
        echo "  contract_ledger.json: OK"
    fi
fi

# 5. Validate each file listed in manifest contracts
echo "Checking contracts from manifest..."
CONTRACTS=$(python3 -c "
import json
manifest = json.load(open('$MANIFEST_PATH'))
contracts = manifest.get('contracts', [])
# contracts is a list: [{file: ..., sha256: ...}, ...]
for contract in contracts:
    filename = contract.get('file', '')
    sha256_hash = contract.get('sha256', '')
    print(f'{filename}|{sha256_hash}')
")

while IFS='|' read -r FILE EXPECTED_HASH; do
    [ -z "$FILE" ] && continue

    CONTRACT_PATH="$BUNDLE_PATH/$FILE"

    # Check file exists
    if [ ! -f "$CONTRACT_PATH" ]; then
        echo "  ERROR: Contract missing: $FILE"
        ERRORS=$((ERRORS + 1))
        continue
    fi

    # Validate JSON/YAML syntax
    if [[ "$FILE" == *.json ]]; then
        if ! python3 -c "import json; json.load(open('$CONTRACT_PATH'))" 2>/dev/null; then
            echo "  ERROR: Invalid JSON in $FILE"
            ERRORS=$((ERRORS + 1))
            continue
        fi
    elif [[ "$FILE" == *.yaml ]] || [[ "$FILE" == *.yml ]]; then
        if ! python3 -c "import yaml; yaml.safe_load(open('$CONTRACT_PATH'))" 2>/dev/null; then
            echo "  ERROR: Invalid YAML in $FILE"
            ERRORS=$((ERRORS + 1))
            continue
        fi
    fi

    # Verify SHA256 hash if provided
    if [ -n "$EXPECTED_HASH" ]; then
        # Remove SHA256: prefix if present
        EXPECTED_HASH="${EXPECTED_HASH#SHA256:}"

        ACTUAL_HASH=$(sha256sum "$CONTRACT_PATH" | cut -d' ' -f1)

        if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
            echo "  ERROR: Hash mismatch for $FILE"
            echo "    Expected: $EXPECTED_HASH"
            echo "    Actual:   $ACTUAL_HASH"
            ERRORS=$((ERRORS + 1))
            continue
        fi
    fi

    echo "  $FILE: OK"
done <<< "$CONTRACTS"

# 6. Multi-mode specific checks
if [ "$BUNDLE_MODE" = "multi" ]; then
    echo "Checking multi-department specific files..."

    # 6a. Check contracts.json exists
    if [ ! -f "$BUNDLE_PATH/contracts.json" ]; then
        echo "  ERROR: contracts.json not found (required for multi mode)"
        ERRORS=$((ERRORS + 1))
    else
        if ! python3 -c "import json; json.load(open('$BUNDLE_PATH/contracts.json'))" 2>/dev/null; then
            echo "  ERROR: contracts.json is not valid JSON"
            ERRORS=$((ERRORS + 1))
        else
            echo "  contracts.json: OK"
        fi
    fi

    # 6b. Check departments directory exists
    if [ ! -d "$BUNDLE_PATH/departments" ]; then
        echo "  ERROR: departments/ directory not found (required for multi mode)"
        ERRORS=$((ERRORS + 1))
    else
        echo "  departments/: OK"
    fi

    # 6c. Verify each department listed in manifest has required artifacts
    DEPARTMENTS=$(python3 -c "
import json
manifest = json.load(open('$MANIFEST_PATH'))
departments = manifest.get('departments', [])
for dept in departments:
    print(dept)
")

    REQUIRED_ARTIFACTS="rbac.json workflows.json approvals.json sod.json invariants.json openapi.yaml"

    while read -r DEPT; do
        [ -z "$DEPT" ] && continue

        DEPT_PATH="$BUNDLE_PATH/departments/$DEPT"

        if [ ! -d "$DEPT_PATH" ]; then
            echo "  ERROR: Department directory not found: departments/$DEPT"
            ERRORS=$((ERRORS + 1))
            continue
        fi

        echo "  Checking department: $DEPT"
        for ARTIFACT in $REQUIRED_ARTIFACTS; do
            ARTIFACT_PATH="$DEPT_PATH/$ARTIFACT"
            if [ ! -f "$ARTIFACT_PATH" ]; then
                echo "    ERROR: Missing artifact: departments/$DEPT/$ARTIFACT"
                ERRORS=$((ERRORS + 1))
            else
                # Validate JSON/YAML syntax
                if [[ "$ARTIFACT" == *.json ]]; then
                    if ! python3 -c "import json; json.load(open('$ARTIFACT_PATH'))" 2>/dev/null; then
                        echo "    ERROR: Invalid JSON in departments/$DEPT/$ARTIFACT"
                        ERRORS=$((ERRORS + 1))
                    fi
                elif [[ "$ARTIFACT" == *.yaml ]] || [[ "$ARTIFACT" == *.yml ]]; then
                    if ! python3 -c "import yaml; yaml.safe_load(open('$ARTIFACT_PATH'))" 2>/dev/null; then
                        echo "    ERROR: Invalid YAML in departments/$DEPT/$ARTIFACT"
                        ERRORS=$((ERRORS + 1))
                    fi
                fi
            fi
        done
    done <<< "$DEPARTMENTS"

# 7. Single-mode specific checks
else
    echo "Checking single-department specific files..."

    # Check openapi.yaml exists (optional but warn)
    if [ ! -f "$BUNDLE_PATH/openapi.yaml" ]; then
        echo "  WARN: openapi.yaml not found (optional)"
    else
        if ! python3 -c "import yaml; yaml.safe_load(open('$BUNDLE_PATH/openapi.yaml'))" 2>/dev/null; then
            echo "  ERROR: openapi.yaml is not valid YAML"
            ERRORS=$((ERRORS + 1))
        else
            echo "  openapi.yaml: OK"
        fi
    fi
fi

# Summary
echo ""
if [ $ERRORS -gt 0 ]; then
    echo "=== VERIFICATION FAILED: $ERRORS error(s) ==="
    exit 1
fi

echo "=== VERIFICATION PASSED ==="
exit 0
