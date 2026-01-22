#!/bin/bash
# Libervia Engine - Restore Script
# Restores engine data from a backup tarball
#
# Usage: ./restore_engine.sh <backup_tarball> [target_data_root]
#   backup_tarball: Path to backup .tar.gz file
#   target_data_root: Target directory (default: ENGINE_DATA_ROOT or ./var)
#
# IMPORTANT: This script does NOT merge data. Target must be empty or non-existent.
#            Stop the engine service before running this script.

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

# Arguments
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup_tarball> [target_data_root]"
    echo ""
    echo "Arguments:"
    echo "  backup_tarball     Path to backup .tar.gz file"
    echo "  target_data_root   Target directory (optional, uses ENGINE_DATA_ROOT)"
    echo ""
    echo "IMPORTANT: Stop engine.service before running this script!"
    exit 1
fi

BACKUP_TARBALL="$1"

# Source engine.env if exists (to get ENGINE_DATA_ROOT)
if [[ -f /etc/engine/engine.env ]]; then
    # shellcheck source=/dev/null
    source /etc/engine/engine.env
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET_DATA_ROOT="${2:-${ENGINE_DATA_ROOT:-$REPO_DIR/var}}"

echo "=============================================="
echo "Libervia Engine - Restore"
echo "=============================================="
echo "Backup: $BACKUP_TARBALL"
echo "Target: $TARGET_DATA_ROOT"
echo ""

# Validate backup file exists
if [[ ! -f "$BACKUP_TARBALL" ]]; then
    log_error "Backup file not found: $BACKUP_TARBALL"
    exit 1
fi

# Verify checksum if available
CHECKSUM_FILE="${BACKUP_TARBALL}.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
    log_info "Verifying backup checksum..."
    EXPECTED_SHA256=$(cat "$CHECKSUM_FILE" | cut -d' ' -f1)
    ACTUAL_SHA256=$(sha256sum "$BACKUP_TARBALL" | cut -d' ' -f1)
    if [[ "$EXPECTED_SHA256" != "$ACTUAL_SHA256" ]]; then
        log_error "Checksum mismatch!"
        log_error "  Expected: $EXPECTED_SHA256"
        log_error "  Actual:   $ACTUAL_SHA256"
        exit 1
    fi
    log_ok "Checksum verified"
else
    log_warn "No checksum file found, skipping verification"
fi

# Check engine service is stopped
if command -v systemctl &> /dev/null && systemctl is-active --quiet engine.service 2>/dev/null; then
    log_error "engine.service is running!"
    log_error "Stop the service first: sudo systemctl stop engine.service"
    exit 1
fi

# Safety check: target should be empty or non-existent
if [[ -d "$TARGET_DATA_ROOT" ]]; then
    INST_DIR="$TARGET_DATA_ROOT/institutions"
    if [[ -d "$INST_DIR" ]] && [[ -n "$(ls -A "$INST_DIR" 2>/dev/null)" ]]; then
        log_error "Target institutions directory is not empty: $INST_DIR"
        log_error "This script does NOT merge data."
        log_error ""
        log_error "Options:"
        log_error "  1. Remove existing data: rm -rf $TARGET_DATA_ROOT/*"
        log_error "  2. Specify a different target: $0 $BACKUP_TARBALL /path/to/new/root"
        exit 1
    fi
fi

# Create temporary extraction directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Step 1: Extract backup
echo ""
echo "--- Step 1: Extract Backup ---"
tar -xzf "$BACKUP_TARBALL" -C "$TEMP_DIR"
log_ok "Extracted tarball"

# Find the backup directory inside
BACKUP_DIR=$(find "$TEMP_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)
if [[ -z "$BACKUP_DIR" ]]; then
    log_error "No directory found in backup tarball"
    exit 1
fi
log_info "Backup directory: $BACKUP_DIR"

# Step 2: Verify manifest
echo ""
echo "--- Step 2: Verify Manifest ---"
MANIFEST_FILE="$BACKUP_DIR/MANIFEST.txt"
if [[ -f "$MANIFEST_FILE" ]]; then
    log_ok "Manifest found"
    # Verify checksums of critical files
    VERIFY_ERRORS=0
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue

        EXPECTED_HASH=$(echo "$line" | cut -d' ' -f1)
        FILE_PATH=$(echo "$line" | cut -d' ' -f3-)

        if [[ -f "$BACKUP_DIR/$FILE_PATH" ]]; then
            ACTUAL_HASH=$(sha256sum "$BACKUP_DIR/$FILE_PATH" | cut -d' ' -f1)
            if [[ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]]; then
                log_error "Checksum mismatch: $FILE_PATH"
                ((VERIFY_ERRORS++))
            fi
        fi
    done < "$MANIFEST_FILE"

    if [[ $VERIFY_ERRORS -gt 0 ]]; then
        log_error "Manifest verification failed with $VERIFY_ERRORS errors"
        exit 1
    fi
    log_ok "All file checksums verified"
else
    log_warn "No manifest file found, skipping verification"
fi

# Step 3: Create target directory
echo ""
echo "--- Step 3: Prepare Target ---"
mkdir -p "$TARGET_DATA_ROOT"
log_ok "Target directory ready: $TARGET_DATA_ROOT"

# Step 4: Restore institutions registry
echo ""
echo "--- Step 4: Restore Institutions Registry ---"
if [[ -f "$BACKUP_DIR/institutions_registry.jsonl" ]]; then
    cp -p "$BACKUP_DIR/institutions_registry.jsonl" "$TARGET_DATA_ROOT/"
    log_ok "Restored institutions_registry.jsonl"
else
    log_warn "No institutions_registry.jsonl in backup"
fi

# Step 5: Restore institution data
echo ""
echo "--- Step 5: Restore Institution Data ---"
if [[ -d "$BACKUP_DIR/institutions" ]]; then
    INST_COUNT=$(find "$BACKUP_DIR/institutions" -maxdepth 1 -mindepth 1 -type d | wc -l)
    log_info "Restoring $INST_COUNT institution(s)..."
    rsync -av "$BACKUP_DIR/institutions/" "$TARGET_DATA_ROOT/institutions/"
    log_ok "Restored institution data"
else
    log_warn "No institutions directory in backup"
    mkdir -p "$TARGET_DATA_ROOT/institutions"
fi

# Step 6: Restore config (optional, with confirmation)
echo ""
echo "--- Step 6: Restore Configuration ---"
if [[ -f "$BACKUP_DIR/engine.env" ]]; then
    if [[ -f /etc/engine/engine.env ]]; then
        log_warn "Existing /etc/engine/engine.env found"
        log_info "Backup config saved to: $TARGET_DATA_ROOT/engine.env.backup"
        cp -p "$BACKUP_DIR/engine.env" "$TARGET_DATA_ROOT/engine.env.backup"
        log_info "To apply: sudo cp $TARGET_DATA_ROOT/engine.env.backup /etc/engine/engine.env"
    else
        log_info "No existing config, consider copying from backup:"
        log_info "  sudo mkdir -p /etc/engine"
        log_info "  sudo cp $BACKUP_DIR/engine.env /etc/engine/engine.env"
    fi
else
    log_warn "No engine.env in backup"
fi

# Step 7: Show bundle reference
echo ""
echo "--- Step 7: Bundle Reference ---"
if [[ -f "$BACKUP_DIR/CURRENT_BUNDLE_LINK" ]]; then
    BUNDLE_REF=$(cat "$BACKUP_DIR/CURRENT_BUNDLE_LINK")
    log_info "Backup was using bundle: $BUNDLE_REF"
    log_info "Ensure this bundle is deployed before starting the engine"
else
    log_warn "No bundle reference in backup"
fi

# Step 8: Validate restored data (basic)
echo ""
echo "--- Step 8: Validate Restored Data ---"
VALIDATION_ERRORS=0

# Check registry is valid JSONL
if [[ -f "$TARGET_DATA_ROOT/institutions_registry.jsonl" ]]; then
    if python3 -c "
import json
import sys
with open('$TARGET_DATA_ROOT/institutions_registry.jsonl') as f:
    for line in f:
        if line.strip():
            json.loads(line)
" 2>/dev/null; then
        log_ok "institutions_registry.jsonl is valid JSONL"
    else
        log_error "institutions_registry.jsonl is invalid"
        ((VALIDATION_ERRORS++))
    fi
fi

# Check ledger files are valid JSONL
for ledger in "$TARGET_DATA_ROOT"/institutions/*/ledger.jsonl; do
    if [[ -f "$ledger" ]]; then
        if python3 -c "
import json
import sys
with open('$ledger') as f:
    for line in f:
        if line.strip():
            json.loads(line)
" 2>/dev/null; then
            log_ok "Valid: $(basename "$(dirname "$ledger")")/ledger.jsonl"
        else
            log_error "Invalid: $ledger"
            ((VALIDATION_ERRORS++))
        fi
    fi
done

if [[ $VALIDATION_ERRORS -gt 0 ]]; then
    log_error "Validation completed with $VALIDATION_ERRORS errors"
    exit 1
fi

# Summary
echo ""
echo "=============================================="
echo -e "${GREEN}RESTORE COMPLETED${NC}"
echo "=============================================="
echo "Data Root: $TARGET_DATA_ROOT"
echo ""
echo "Next steps:"
echo "  1. Verify ENGINE_DATA_ROOT in /etc/engine/engine.env points to: $TARGET_DATA_ROOT"
echo "  2. Ensure bundle is deployed (see bundle reference above)"
echo "  3. Start the service: sudo systemctl start engine.service"
echo "  4. Run health check: curl http://127.0.0.1:8000/health"
echo ""
