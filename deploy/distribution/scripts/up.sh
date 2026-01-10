#!/bin/bash
# up.sh - Start Bazari Engine distribution
#
# Usage:
#   ./scripts/up.sh              # Start in foreground
#   ./scripts/up.sh -d           # Start in detached mode
#   ./scripts/up.sh --build      # Rebuild containers before starting
#
# Environment:
#   Set ENGINE_AIRGAPPED=true for air-gapped mode

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

# Check if .env exists, create from example if not
if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        log_warn ".env not found, creating from .env.example"
        cp .env.example .env
    fi
fi

# Parse arguments
DETACH=""
BUILD=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--detach)
            DETACH="-d"
            shift
            ;;
        --build)
            BUILD="--build"
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

if ! docker info &> /dev/null; then
    log_error "Docker daemon is not running"
    exit 1
fi

# Check docker compose availability
if ! docker compose version &> /dev/null; then
    log_error "docker compose is not available"
    exit 1
fi

log_info "Starting Bazari Engine distribution..."
log_info "Deploy directory: $DEPLOY_DIR"

# Validate compose file
log_info "Validating docker-compose.yml..."
if ! docker compose config --quiet 2>/dev/null; then
    log_error "Invalid docker-compose.yml configuration"
    docker compose config
    exit 1
fi

# Check if air-gapped mode is enabled
if [[ "${ENGINE_AIRGAPPED:-false}" == "true" ]]; then
    log_warn "Air-gapped mode is ENABLED"
    log_warn "Ensure images are pre-loaded with: docker load -i bazari-engine-images.tar"
fi

# Start services
log_info "Starting services..."
docker compose up $DETACH $BUILD $EXTRA_ARGS

if [[ -n "$DETACH" ]]; then
    log_info "Services started in detached mode"
    log_info "View logs: docker compose logs -f"
    log_info "Stop: ./scripts/down.sh"

    # Wait a moment and check health
    sleep 3
    log_info "Checking service status..."
    docker compose ps
fi

log_info "Done!"
