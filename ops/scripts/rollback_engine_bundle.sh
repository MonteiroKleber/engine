#!/bin/bash
# Rollback Libervia Engine bundle to previous release
# Run as root: sudo ./rollback_engine_bundle.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLES_DIR="/var/lib/engine/bundles"
CURRENT_LINK="$BUNDLES_DIR/CURRENT"
PREVIOUS_LINK="$BUNDLES_DIR/PREVIOUS"

echo "=== Rolling back Libervia Engine Bundle ==="
echo ""

# Check PREVIOUS exists
if [ ! -L "$PREVIOUS_LINK" ]; then
    echo "ERROR: No PREVIOUS release to rollback to!"
    echo "PREVIOUS symlink does not exist: $PREVIOUS_LINK"
    exit 1
fi

PREVIOUS_TARGET=$(readlink -f "$PREVIOUS_LINK")
echo "PREVIOUS target: $PREVIOUS_TARGET"

# Check PREVIOUS target directory exists
if [ ! -d "$PREVIOUS_TARGET" ]; then
    echo "ERROR: PREVIOUS target directory does not exist!"
    echo "Path: $PREVIOUS_TARGET"
    exit 1
fi

# Show current state
if [ -L "$CURRENT_LINK" ]; then
    CURRENT_TARGET=$(readlink -f "$CURRENT_LINK")
    echo "CURRENT target:  $CURRENT_TARGET"
    
    if [ "$CURRENT_TARGET" = "$PREVIOUS_TARGET" ]; then
        echo ""
        echo "WARNING: CURRENT and PREVIOUS point to the same release."
        echo "No rollback needed."
        exit 0
    fi
fi
echo ""

# Confirm rollback
echo "This will:"
echo "  1. Set CURRENT -> $PREVIOUS_TARGET"
echo "  2. Restart engine.service"
echo "  3. Run smoke test"
echo ""

# Perform rollback
echo "Step 1: Updating CURRENT symlink..."
ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK"
echo "  CURRENT -> $PREVIOUS_TARGET"
echo ""

# Restart service
echo "Step 2: Restarting engine.service..."
systemctl restart engine.service
sleep 3

# Check service status
if ! systemctl is-active --quiet engine.service; then
    echo "WARNING: Service may not have started properly"
    systemctl status engine.service --no-pager || true
fi
echo ""

# Run smoke test
echo "Step 3: Running smoke test..."
if "$SCRIPT_DIR/../checks/smoke_test.sh"; then
    echo ""
    echo "=== ROLLBACK SUCCESSFUL ==="
    echo "Active release: $PREVIOUS_TARGET"
    exit 0
fi

echo ""
echo "!!! SMOKE TEST FAILED AFTER ROLLBACK !!!"
echo "Manual intervention required."
exit 1
