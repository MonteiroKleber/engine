#!/bin/bash
# Deploy Libervia Engine bundle for Docker/containerized environments
# This script moves bundles from STAGING to RELEASES and updates the CURRENT symlink
# No systemd, no rollback to previous - simplified for container use
#
# Usage: Called by compile_release without arguments
# Reads from ENV vars set by the container:
#   - ENGINE_PROD_BUNDLES_ROOT: Root bundles directory

set -e

# Get bundles root from environment (institution-specific or global)
BUNDLES_ROOT="${ENGINE_PROD_BUNDLES_ROOT:-/app/var/bundles}"
STAGING_DIR="$BUNDLES_ROOT/STAGING"
RELEASES_DIR="$BUNDLES_ROOT/releases"
CURRENT_LINK="$BUNDLES_ROOT/CURRENT"

echo "=== Deploying Libervia Engine Bundle (Docker) ==="
echo "Bundles root: $BUNDLES_ROOT"
echo "Staging dir: $STAGING_DIR"
echo ""

# Check staging directory exists
if [ ! -d "$STAGING_DIR" ]; then
    echo "ERROR: Staging directory does not exist: $STAGING_DIR"
    exit 1
fi

# Find bundle(s) in staging - take the first one
BUNDLE=$(find "$STAGING_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

if [ -z "$BUNDLE" ]; then
    echo "ERROR: No bundle found in staging"
    exit 1
fi

BUNDLE_NAME=$(basename "$BUNDLE")
echo "Found bundle: $BUNDLE_NAME"
echo ""

# Generate release ID (UTC timestamp)
RELEASE_ID=$(date -u +"%Y%m%d-%H%M%S")
echo "Release ID: $RELEASE_ID"
echo ""

# Ensure releases directory exists
mkdir -p "$RELEASES_DIR"

# Step 1: Move bundle from staging to releases
echo "Step 1: Moving to releases..."
RELEASE_PATH="$RELEASES_DIR/$RELEASE_ID"
mkdir -p "$RELEASE_PATH"
mv "$BUNDLE" "$RELEASE_PATH/"
echo "  Release path: $RELEASE_PATH/$BUNDLE_NAME"
echo ""

# Step 2: Update CURRENT symlink
echo "Step 2: Updating CURRENT symlink..."
ln -sfn "$RELEASE_PATH/$BUNDLE_NAME" "$CURRENT_LINK"
echo "  CURRENT -> $RELEASE_PATH/$BUNDLE_NAME"
echo ""

# Step 3: Basic health check (if engine is running, curl /health)
# NOTE: Use short timeout to prevent blocking when running from subprocess
echo "Step 3: Health check..."
if curl -sf --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
    echo "  Engine health check: OK"
else
    echo "  NOTE: Engine health check skipped or not available"
fi
echo ""

echo "=== DEPLOYMENT SUCCESSFUL ==="
echo "Bundle: $BUNDLE_NAME"
echo "Release: $RELEASE_ID"
echo "Location: $CURRENT_LINK"
exit 0
