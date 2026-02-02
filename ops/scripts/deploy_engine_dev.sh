#!/bin/bash
# Deploy Libervia Engine bundle for DEV environment
# Uses environment variable for bundles dir

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Use environment variable or default to dev path
BUNDLES_DIR="${ENGINE_PROD_BUNDLES_ROOT:-/home/bazari/engine/var/dev-bundles}"
RELEASES_DIR="$BUNDLES_DIR/releases"
STAGING_DIR="$BUNDLES_DIR/STAGING"
CURRENT_LINK="$BUNDLES_DIR/CURRENT"
PREVIOUS_LINK="$BUNDLES_DIR/PREVIOUS"

# Bundle name from argument or default
BUNDLE_NAME="${1:-personal-ops}"
BUNDLE_HASH="${2:-unknown}"

# Source bundle from staging
SOURCE_BUNDLE="$STAGING_DIR/$BUNDLE_NAME"

echo "=== Deploying Libervia Engine Bundle (DEV) ==="
echo "Source: $SOURCE_BUNDLE"
echo "Target: $BUNDLES_DIR"
echo "Bundle: $BUNDLE_NAME"
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

# Step 1: Move from staging to releases
echo "Step 1: Moving to releases..."
RELEASE_PATH="$RELEASES_DIR/$RELEASE_ID/$BUNDLE_NAME"
mkdir -p "$(dirname "$RELEASE_PATH")"
mv "$SOURCE_BUNDLE" "$RELEASE_PATH"
echo "Moved to: $RELEASE_PATH"
echo ""

# Step 2: Update symlinks
echo "Step 2: Updating symlinks..."

# Backup current to previous
if [ -L "$CURRENT_LINK" ]; then
    CURRENT_TARGET=$(readlink -f "$CURRENT_LINK" || echo "")
    if [ -n "$CURRENT_TARGET" ] && [ -d "$CURRENT_TARGET" ]; then
        rm -f "$PREVIOUS_LINK"
        ln -sf "$CURRENT_TARGET" "$PREVIOUS_LINK"
        echo "Previous: $CURRENT_TARGET"
    fi
fi

# Point current to new release
rm -f "$CURRENT_LINK"
ln -sf "$RELEASE_PATH" "$CURRENT_LINK"
echo "Current: $RELEASE_PATH"
echo ""

echo "=== Deploy Complete ==="
echo "Release: $RELEASE_ID"
echo "Bundle: $BUNDLE_NAME"
