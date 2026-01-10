#!/bin/bash
# verify_airgapped.sh - Verify air-gapped mode configuration
#
# This script verifies that the Bazari Engine distribution can operate
# in an air-gapped (offline) environment without external network access.
#
# Checks:
#   1. All required images are available locally
#   2. No external DNS resolution is attempted (if possible)
#   3. Network isolation configuration
#   4. Volume mounts for offline data
#
# Usage:
#   ./scripts/verify_airgapped.sh          # Verify configuration
#   ./scripts/verify_airgapped.sh --save   # Save images for transfer
#   ./scripts/verify_airgapped.sh --load   # Load images from archive
#
# Exit codes:
#   0 - Air-gapped mode verified/ready
#   1 - Issues found

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0

# Image archive name
IMAGE_ARCHIVE="bazari-engine-images.tar"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((CHECKS_WARNED++))
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((CHECKS_PASSED++))
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((CHECKS_FAILED++))
}

# Change to deploy directory
cd "$DEPLOY_DIR"

# =============================================================================
# Parse Arguments
# =============================================================================
MODE="verify"
while [[ $# -gt 0 ]]; do
    case $1 in
        --save)
            MODE="save"
            shift
            ;;
        --load)
            MODE="load"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# =============================================================================
# Save Images Mode
# =============================================================================
if [[ "$MODE" == "save" ]]; then
    log_info "Saving Docker images for air-gapped transfer..."

    # Get list of images from compose file
    IMAGES=$(docker compose config --images 2>/dev/null | sort -u)

    if [[ -z "$IMAGES" ]]; then
        log_error "No images found in docker-compose.yml"
        exit 1
    fi

    log_info "Images to save:"
    echo "$IMAGES" | while read -r img; do
        echo "  - $img"
    done

    # Pull images first (ensure they're available)
    log_info "Pulling images..."
    echo "$IMAGES" | while read -r img; do
        docker pull "$img" || true
    done

    # Save to tar archive
    log_info "Saving to $IMAGE_ARCHIVE..."
    docker save -o "$IMAGE_ARCHIVE" $IMAGES

    # Show archive info
    ARCHIVE_SIZE=$(du -h "$IMAGE_ARCHIVE" | cut -f1)
    log_info "Archive created: $IMAGE_ARCHIVE ($ARCHIVE_SIZE)"
    log_info "Transfer this file to the air-gapped environment"
    log_info "Load with: ./scripts/verify_airgapped.sh --load"

    exit 0
fi

# =============================================================================
# Load Images Mode
# =============================================================================
if [[ "$MODE" == "load" ]]; then
    log_info "Loading Docker images from archive..."

    if [[ ! -f "$IMAGE_ARCHIVE" ]]; then
        log_error "Image archive not found: $IMAGE_ARCHIVE"
        log_info "Create it first with: ./scripts/verify_airgapped.sh --save"
        exit 1
    fi

    log_info "Loading from $IMAGE_ARCHIVE..."
    docker load -i "$IMAGE_ARCHIVE"

    log_info "Images loaded successfully"
    log_info "You can now run: ./scripts/up.sh -d"

    exit 0
fi

# =============================================================================
# Verify Mode (default)
# =============================================================================
log_info "Verifying air-gapped mode configuration..."
log_info "Deploy directory: $DEPLOY_DIR"
echo ""

# -----------------------------------------------------------------------------
# Check 1: Docker Available
# -----------------------------------------------------------------------------
log_check "Check 1: Docker is available"
if command -v docker &> /dev/null && docker info &> /dev/null; then
    check_pass "Docker is available and running"
else
    check_fail "Docker is not available"
fi

# -----------------------------------------------------------------------------
# Check 2: Required Images Available Locally
# -----------------------------------------------------------------------------
log_check "Check 2: Required images available locally"
IMAGES=$(docker compose config --images 2>/dev/null | sort -u)
ALL_IMAGES_LOCAL=true

for img in $IMAGES; do
    if docker image inspect "$img" &> /dev/null; then
        check_pass "Image available: $img"
    else
        check_fail "Image NOT available locally: $img"
        ALL_IMAGES_LOCAL=false
    fi
done

if [[ "$ALL_IMAGES_LOCAL" == "false" ]]; then
    log_warn "Some images need to be pulled or loaded from archive"
    log_warn "  Pull: docker compose pull"
    log_warn "  Or load from archive: ./scripts/verify_airgapped.sh --load"
fi

# -----------------------------------------------------------------------------
# Check 3: Image Archive Exists
# -----------------------------------------------------------------------------
log_check "Check 3: Image archive for transfer"
if [[ -f "$IMAGE_ARCHIVE" ]]; then
    ARCHIVE_SIZE=$(du -h "$IMAGE_ARCHIVE" | cut -f1)
    check_pass "Image archive exists: $IMAGE_ARCHIVE ($ARCHIVE_SIZE)"
else
    log_warn "No image archive found. Create with: ./scripts/verify_airgapped.sh --save"
fi

# -----------------------------------------------------------------------------
# Check 4: Environment Variables
# -----------------------------------------------------------------------------
log_check "Check 4: Air-gapped environment configuration"

# Load .env if exists
if [[ -f .env ]]; then
    source .env 2>/dev/null || true
fi

if [[ "${ENGINE_AIRGAPPED:-false}" == "true" ]]; then
    check_pass "ENGINE_AIRGAPPED=true (air-gapped mode enabled)"
else
    log_warn "ENGINE_AIRGAPPED is not set to true"
    log_warn "  Set ENGINE_AIRGAPPED=true in .env for strict air-gapped mode"
fi

# -----------------------------------------------------------------------------
# Check 5: No External URLs in Compose
# -----------------------------------------------------------------------------
log_check "Check 5: No external URLs in docker-compose.yml"
EXTERNAL_URLS=$(grep -E 'https?://' docker-compose.yml 2>/dev/null | grep -v '#' || true)
if [[ -z "$EXTERNAL_URLS" ]]; then
    check_pass "No external URLs in docker-compose.yml"
else
    log_warn "External URLs found in docker-compose.yml (review for air-gapped):"
    echo "$EXTERNAL_URLS" | head -5
fi

# -----------------------------------------------------------------------------
# Check 6: Volume Mounts
# -----------------------------------------------------------------------------
log_check "Check 6: Local volume mounts configured"
VOLUMES=$(docker compose config --volumes 2>/dev/null | wc -l)
if [[ $VOLUMES -gt 0 ]]; then
    check_pass "Local volumes configured ($VOLUMES volumes)"
else
    log_warn "No local volumes configured - data may not persist"
fi

# -----------------------------------------------------------------------------
# Check 7: Network Configuration
# -----------------------------------------------------------------------------
log_check "Check 7: Network isolation"
# Check if network is internal
if grep -q "internal: true" docker-compose.yml 2>/dev/null; then
    check_pass "Network configured as internal (no external access)"
else
    log_warn "Network not configured as internal"
    log_warn "  For strict air-gapped mode, set 'internal: true' in network config"
fi

# -----------------------------------------------------------------------------
# Check 8: DNS Resolution Test (if container running)
# -----------------------------------------------------------------------------
log_check "Check 8: External DNS resolution (if container running)"
if docker ps --format '{{.Names}}' | grep -q "bazari-engine"; then
    # Try to resolve an external domain - should fail in air-gapped mode
    DNS_TEST=$(docker exec bazari-engine bash -c "timeout 2 python -c \"import socket; socket.gethostbyname('google.com')\" 2>&1" || echo "BLOCKED")
    if [[ "$DNS_TEST" == *"BLOCKED"* ]] || [[ "$DNS_TEST" == *"timed out"* ]] || [[ "$DNS_TEST" == *"Errno"* ]]; then
        check_pass "External DNS resolution blocked/unavailable"
    else
        log_warn "External DNS resolution succeeded - not fully air-gapped"
        log_warn "  Consider network isolation or firewall rules"
    fi
else
    log_warn "Container not running - skipping DNS test"
fi

# -----------------------------------------------------------------------------
# Check 9: No pip install at runtime (for strict air-gapped)
# -----------------------------------------------------------------------------
log_check "Check 9: Runtime pip installs"
PIP_INSTALLS=$(grep -c "pip install" docker-compose.yml 2>/dev/null || echo "0")
if [[ $PIP_INSTALLS -gt 0 ]]; then
    log_warn "docker-compose.yml contains 'pip install' commands"
    log_warn "  For strict air-gapped mode, pre-install dependencies in image"
    log_warn "  Or mount a pre-downloaded packages directory"
else
    check_pass "No runtime pip installs in compose file"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "=============================================="
echo "AIR-GAPPED VERIFICATION SUMMARY"
echo "=============================================="
echo -e "Checks Passed:  ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Checks Failed:  ${RED}$CHECKS_FAILED${NC}"
echo -e "Warnings:       ${YELLOW}$CHECKS_WARNED${NC}"
echo ""

if [[ $CHECKS_FAILED -eq 0 ]]; then
    if [[ $CHECKS_WARNED -eq 0 ]]; then
        log_info "Air-gapped mode FULLY VERIFIED!"
    else
        log_info "Air-gapped mode READY (with warnings)"
        log_warn "Review warnings above for strict air-gapped compliance"
    fi
    echo ""
    echo "To run in air-gapped mode:"
    echo "  1. Set ENGINE_AIRGAPPED=true in .env"
    echo "  2. Ensure images are pre-loaded: ./scripts/verify_airgapped.sh --load"
    echo "  3. Start: ./scripts/up.sh -d"
    exit 0
else
    log_error "Air-gapped mode verification FAILED"
    log_error "Fix the issues above before deploying in air-gapped environment"
    exit 1
fi
