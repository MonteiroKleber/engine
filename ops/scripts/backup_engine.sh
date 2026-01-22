#!/bin/bash
# Libervia Engine - Backup Script
# Creates a compressed backup of all engine data with integrity verification
#
# Usage: ./backup_engine.sh [backup_dir]
#   backup_dir: Directory to store backup (default: /var/backups/engine)
#
# Output: Creates timestamped tarball with manifest

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_info() { echo -e "[INFO] $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Source engine.env if exists (to get ENGINE_DATA_ROOT)
if [[ -f /etc/engine/engine.env ]]; then
    # shellcheck source=/dev/null
    source /etc/engine/engine.env
fi

# Defaults
ENGINE_DATA_ROOT="${ENGINE_DATA_ROOT:-$REPO_DIR/var}"
BACKUP_BASE_DIR="${1:-/var/backups/engine}"
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
BACKUP_NAME="engine-backup-${TIMESTAMP}"
BACKUP_DIR="${BACKUP_BASE_DIR}/${BACKUP_NAME}"

echo "=============================================="
echo "Libervia Engine - Backup"
echo "=============================================="
echo "Timestamp: $TIMESTAMP"
echo "Data Root: $ENGINE_DATA_ROOT"
echo "Backup Dir: $BACKUP_DIR"
echo ""

# Validate source exists
if [[ ! -d "$ENGINE_DATA_ROOT" ]]; then
    log_error "Data root not found: $ENGINE_DATA_ROOT"
    exit 1
fi

# Create backup directory
log_info "Creating backup directory..."
mkdir -p "$BACKUP_DIR"

# Step 1: Backup institutions registry
echo ""
echo "--- Step 1: Backup Institutions Registry ---"
REGISTRY_PATH="${ENGINE_DATA_ROOT}/institutions_registry.jsonl"
if [[ -f "$REGISTRY_PATH" ]]; then
    cp -p "$REGISTRY_PATH" "$BACKUP_DIR/"
    log_ok "Copied institutions_registry.jsonl"
else
    log_warn "No institutions_registry.jsonl found (may be single-tenant)"
fi

# Step 2: Backup institution data
echo ""
echo "--- Step 2: Backup Institution Data ---"
INSTITUTIONS_DIR="${ENGINE_DATA_ROOT}/institutions"
if [[ -d "$INSTITUTIONS_DIR" ]]; then
    # Count institutions
    INST_COUNT=$(find "$INSTITUTIONS_DIR" -maxdepth 1 -mindepth 1 -type d | wc -l)
    log_info "Found $INST_COUNT institution(s)"

    # Copy with rsync (preserves permissions, handles append-only files safely)
    rsync -av --delete "$INSTITUTIONS_DIR/" "$BACKUP_DIR/institutions/"
    log_ok "Copied institution data"
else
    log_warn "No institutions directory found"
    mkdir -p "$BACKUP_DIR/institutions"
fi

# Step 3: Backup engine config
echo ""
echo "--- Step 3: Backup Configuration ---"
if [[ -f /etc/engine/engine.env ]]; then
    cp -p /etc/engine/engine.env "$BACKUP_DIR/engine.env"
    log_ok "Copied /etc/engine/engine.env"
else
    log_warn "No /etc/engine/engine.env found"
fi

# Step 4: Record current bundle symlink
echo ""
echo "--- Step 4: Record Bundle Reference ---"
BUNDLE_CURRENT="/var/lib/engine/bundles/CURRENT"
if [[ -L "$BUNDLE_CURRENT" ]]; then
    readlink -f "$BUNDLE_CURRENT" > "$BACKUP_DIR/CURRENT_BUNDLE_LINK"
    log_ok "Recorded bundle symlink: $(cat "$BACKUP_DIR/CURRENT_BUNDLE_LINK")"
elif [[ -n "${ENGINE_BUNDLE_PATH:-}" ]]; then
    echo "$ENGINE_BUNDLE_PATH" > "$BACKUP_DIR/CURRENT_BUNDLE_LINK"
    log_ok "Recorded ENGINE_BUNDLE_PATH: $ENGINE_BUNDLE_PATH"
else
    log_warn "No bundle symlink or ENGINE_BUNDLE_PATH found"
fi

# Step 5: Generate manifest with checksums
echo ""
echo "--- Step 5: Generate Manifest ---"
MANIFEST_FILE="$BACKUP_DIR/MANIFEST.txt"
{
    echo "# Libervia Engine Backup Manifest"
    echo "# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "# Source: $ENGINE_DATA_ROOT"
    echo ""
    echo "# File checksums (SHA256):"
    find "$BACKUP_DIR" -type f -name "*.jsonl" -o -name "*.json" -o -name "engine.env" | sort | while read -r f; do
        if [[ -f "$f" ]]; then
            sha256sum "$f" | sed "s|$BACKUP_DIR/||"
        fi
    done
} > "$MANIFEST_FILE"
log_ok "Generated manifest"

# Step 6: Create tarball
echo ""
echo "--- Step 6: Create Compressed Archive ---"
TARBALL="${BACKUP_BASE_DIR}/${BACKUP_NAME}.tar.gz"
tar -czf "$TARBALL" -C "$BACKUP_BASE_DIR" "$BACKUP_NAME"
log_ok "Created tarball: $TARBALL"

# Calculate tarball checksum
TARBALL_SHA256=$(sha256sum "$TARBALL" | cut -d' ' -f1)
echo "$TARBALL_SHA256  ${BACKUP_NAME}.tar.gz" > "${TARBALL}.sha256"
log_ok "Created checksum file: ${TARBALL}.sha256"

# Step 7: Cleanup temporary directory
echo ""
echo "--- Step 7: Cleanup ---"
rm -rf "$BACKUP_DIR"
log_ok "Removed temporary directory"

# Summary
echo ""
echo "=============================================="
echo -e "${GREEN}BACKUP COMPLETED${NC}"
echo "=============================================="
echo "Tarball: $TARBALL"
echo "Checksum: $TARBALL_SHA256"
echo "Size: $(du -h "$TARBALL" | cut -f1)"
echo ""
echo "To restore, run:"
echo "  ./restore_engine.sh $TARBALL"
echo ""
