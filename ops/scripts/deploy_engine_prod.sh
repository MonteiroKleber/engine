#!/bin/bash
# Deploy Libervia Engine bundle with versioned releases
# Run as root: sudo ./deploy_engine_prod.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUNDLES_DIR="/var/lib/engine/bundles"
RELEASES_DIR="$BUNDLES_DIR/releases"
STAGING_DIR="$BUNDLES_DIR/STAGING"
CURRENT_LINK="$BUNDLES_DIR/CURRENT"
PREVIOUS_LINK="$BUNDLES_DIR/PREVIOUS"

# Source bundle from repo
SOURCE_BUNDLE="$REPO_DIR/bundles/finance-pilot"

echo "=== Deploying Libervia Engine Bundle ==="
echo "Source: $SOURCE_BUNDLE"
echo "Target: $BUNDLES_DIR"
echo ""

# Check source exists
if [ ! -d "$SOURCE_BUNDLE" ]; then
    echo "ERROR: Source bundle not found: $SOURCE_BUNDLE"
    exit 1
fi

# Generate release ID (UTC timestamp)
RELEASE_ID=$(date -u +"%Y%m%d-%H%M%S")
echo "Release ID: $RELEASE_ID"
echo ""

# Ensure directories exist
mkdir -p "$RELEASES_DIR"
mkdir -p "$STAGING_DIR"

# Step 1: Copy to staging
echo "Step 1: Copying to staging..."
STAGING_PATH="$STAGING_DIR/$RELEASE_ID/finance-pilot"
mkdir -p "$STAGING_PATH"
rsync -av --delete "$SOURCE_BUNDLE/" "$STAGING_PATH/"
echo ""

# Step 2: Verify bundle in staging
echo "Step 2: Verifying bundle..."
if ! "$SCRIPT_DIR/../checks/verify_bundle.sh" "$STAGING_PATH"; then
    echo ""
    echo "ERROR: Bundle verification failed!"
    echo "Cleaning up staging..."
    rm -rf "$STAGING_DIR/$RELEASE_ID"
    exit 1
fi
echo ""

# Step 3: Move from staging to releases
echo "Step 3: Moving to releases..."
RELEASE_PATH="$RELEASES_DIR/$RELEASE_ID/finance-pilot"
mkdir -p "$RELEASES_DIR/$RELEASE_ID"
mv "$STAGING_PATH" "$RELEASE_PATH"
rmdir "$STAGING_DIR/$RELEASE_ID" 2>/dev/null || true
echo "  Release path: $RELEASE_PATH"
echo ""

# Step 4: Update symlinks
echo "Step 4: Updating symlinks..."

# Save current as previous (if current exists and is a symlink)
if [ -L "$CURRENT_LINK" ]; then
    CURRENT_TARGET=$(readlink -f "$CURRENT_LINK")
    echo "  Setting PREVIOUS -> $CURRENT_TARGET"
    ln -sfn "$CURRENT_TARGET" "$PREVIOUS_LINK"
fi

# Set current to new release
echo "  Setting CURRENT -> $RELEASE_PATH"
ln -sfn "$RELEASE_PATH" "$CURRENT_LINK"
echo ""

# Step 5: Set permissions
echo "Step 5: Setting permissions..."
chown -R bazari:bazari "$BUNDLES_DIR"
echo ""

# Step 6: Restart service
echo "Step 6: Restarting engine.service..."
systemctl restart engine.service

# Wait for service to start
sleep 3

# Check service is running
if ! systemctl is-active --quiet engine.service; then
    echo "WARNING: Service may not have started properly"
    systemctl status engine.service --no-pager || true
fi
echo ""

# Step 7: Run smoke test
echo "Step 7: Running smoke test..."
if "$SCRIPT_DIR/../checks/smoke_test.sh"; then
    echo ""
    echo "=== DEPLOYMENT SUCCESSFUL ==="
    echo "Release: $RELEASE_ID"
    echo "Current: $CURRENT_LINK -> $RELEASE_PATH"
    if [ -L "$PREVIOUS_LINK" ]; then
        echo "Previous: $PREVIOUS_LINK -> $(readlink -f "$PREVIOUS_LINK")"
    fi
    exit 0
fi

# Smoke test failed - attempt rollback
echo ""
echo "!!! SMOKE TEST FAILED - INITIATING ROLLBACK !!!"
echo ""

# Check if previous exists
if [ ! -L "$PREVIOUS_LINK" ]; then
    echo "ERROR: No PREVIOUS release to rollback to!"
    echo "Manual intervention required."
    exit 1
fi

PREVIOUS_TARGET=$(readlink -f "$PREVIOUS_LINK")
echo "Rolling back to: $PREVIOUS_TARGET"

# Rollback: Set CURRENT to PREVIOUS
ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK"

# Restart service
echo "Restarting service with previous bundle..."
systemctl restart engine.service
sleep 3

# Run smoke test on rollback
echo "Running smoke test after rollback..."
if "$SCRIPT_DIR/../checks/smoke_test.sh"; then
    echo ""
    echo "=== ROLLBACK SUCCESSFUL ==="
    echo "Active release restored to: $PREVIOUS_TARGET"
    echo ""
    echo "FAILED release ($RELEASE_ID) left in releases for debugging."
    echo "Remove manually: rm -rf $RELEASES_DIR/$RELEASE_ID"
    exit 1  # Exit with error since original deploy failed
fi

echo ""
echo "!!! CRITICAL: ROLLBACK ALSO FAILED !!!"
echo "Manual intervention required."
exit 1
