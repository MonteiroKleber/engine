#!/bin/bash
# Install Libervia Engine systemd service
# Run as root: sudo ./install_engine_service.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Installing Libervia Engine Service ==="

# Create config directory
echo "Creating /etc/engine..."
mkdir -p /etc/engine

# Copy env file if not exists
if [ ! -f /etc/engine/engine.env ]; then
    echo "Copying engine.env.example to /etc/engine/engine.env..."
    cp "$REPO_DIR/ops/env/engine.env.example" /etc/engine/engine.env
    chmod 640 /etc/engine/engine.env
else
    echo "/etc/engine/engine.env already exists, skipping..."
fi

# Create data directories
echo "Creating /var/lib/engine..."
mkdir -p /var/lib/engine/bundles

# Set ownership to bazari
chown -R bazari:bazari /var/lib/engine

# Copy systemd service file
echo "Installing systemd service..."
cp "$REPO_DIR/ops/systemd/engine.service" /etc/systemd/system/engine.service

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service
echo "Enabling engine.service..."
systemctl enable engine.service

echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Run deploy script: sudo ./deploy_engine_prod.sh"
echo "  2. Start service: sudo systemctl start engine.service"
echo "  3. Check status: sudo systemctl status engine.service"
echo "  4. Run smoke test: ./smoke_test.sh"
