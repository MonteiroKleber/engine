#!/bin/bash
# down.sh - Stop Bazari Engine distribution
#
# Usage:
#   ./scripts/down.sh              # Stop and remove containers
#   ./scripts/down.sh -v           # Also remove volumes
#   ./scripts/down.sh --volumes    # Also remove volumes
#
# Note: By default, volumes are preserved to maintain data between restarts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Change to deploy directory
cd "$DEPLOY_DIR"

# Parse arguments
VOLUMES=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--volumes)
            VOLUMES="-v"
            shift
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

# Check Docker availability
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed or not in PATH"
    exit 1
fi

log_info "Stopping Bazari Engine distribution..."

# Show current status before stopping
log_info "Current status:"
docker compose ps 2>/dev/null || true

# Stop services
log_info "Stopping services..."
docker compose down $VOLUMES $EXTRA_ARGS

if [[ -n "$VOLUMES" ]]; then
    log_warn "Volumes have been removed (data cleared)"
else
    log_info "Volumes preserved (use -v to remove)"
fi

log_info "Done!"
