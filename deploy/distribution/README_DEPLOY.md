# Bazari Engine Distribution

Standalone distribution package for deploying Bazari Engine v1.0.0 via Docker Compose.

## Overview

This distribution is designed to be:
- **Self-contained**: No external dependencies at runtime
- **Air-gapped ready**: Can operate in isolated networks
- **Reproducible**: Deterministic deployment across environments
- **Observable**: Built-in telemetry and logging

## Quick Start

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Start services
./scripts/up.sh -d

# 3. Verify deployment
./scripts/smoke.sh

# 4. View logs
docker compose logs -f engine

# 5. Stop services
./scripts/down.sh
```

## Directory Structure

```
deploy/distribution/
├── docker-compose.yml      # Main compose file
├── .env.example            # Environment template (no secrets)
├── README_DEPLOY.md        # This file
└── scripts/
    ├── up.sh               # Start services
    ├── down.sh             # Stop services
    ├── smoke.sh            # Run smoke tests
    └── verify_airgapped.sh # Verify air-gapped mode
```

## Services

### Engine (Main Service)

The core Bazari Engine runner.

| Property | Value |
|----------|-------|
| Container | `bazari-engine` |
| Image | `python:3.10-slim` |
| Working Dir | `/app/engine` |
| Health Check | Python import test |

**Running Engine Commands:**

```bash
# Check version
docker exec bazari-engine python -c "from version import __version__; print(__version__)"

# Run engine
docker exec bazari-engine python main.py --project demo --input "My system" --skip-build

# Access shell
docker exec -it bazari-engine bash
```

### Wizard (Optional)

Interactive wizard for project configuration. Uncomment in `docker-compose.yml` if needed.

```bash
# Start wizard session
docker exec bazari-engine python -m wizard.wizard_cli start --project MyProject --domain healthcare

# Export session
docker exec bazari-engine python -m wizard.wizard_cli export <session_id>
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_VERSION` | `1.0.0` | Engine version tag |
| `ENGINE_SOURCE` | `../../` | Path to engine source |
| `GENERATED_ROOT` | `/tmp/generated` | Generated projects directory |
| `TELEMETRY_ENABLED` | `true` | Enable telemetry output |
| `ENGINE_AIRGAPPED` | `false` | Air-gapped mode flag |

### Volumes

| Volume | Container Path | Purpose |
|--------|---------------|---------|
| `engine-data` | `/data` | Persistent data (episodes, artifacts) |
| `engine-logs` | `/logs` | Log files |
| `${ENGINE_SOURCE}` | `/app/engine` | Engine source (read-only) |
| `${GENERATED_ROOT}` | `/home/bazari/generated` | Generated projects |

## Ports

By default, no ports are exposed externally. If you need external access:

1. Uncomment port mappings in `docker-compose.yml`
2. Configure firewall rules appropriately
3. Consider TLS termination for production

## Air-Gapped Mode

For environments without internet access.

### Preparation (Online Machine)

```bash
# 1. Save all required images to archive
./scripts/verify_airgapped.sh --save

# This creates: bazari-engine-images.tar
# Transfer this file to the air-gapped machine
```

### Deployment (Offline Machine)

```bash
# 1. Load images from archive
./scripts/verify_airgapped.sh --load

# 2. Enable air-gapped mode
echo "ENGINE_AIRGAPPED=true" >> .env

# 3. Start services
./scripts/up.sh -d

# 4. Verify configuration
./scripts/verify_airgapped.sh
```

### Air-Gapped Verification

The `verify_airgapped.sh` script checks:
- All required images available locally
- No external DNS resolution
- Network isolation configuration
- Volume mounts for offline data

### Strict Air-Gapped Mode

For complete network isolation, add to `docker-compose.yml`:

```yaml
networks:
  engine-network:
    driver: bridge
    internal: true  # No external network access
```

## Smoke Tests

Run comprehensive smoke tests:

```bash
./scripts/smoke.sh
```

Tests include:
1. Docker Compose configuration validation
2. Service running status
3. Container health checks
4. Engine version command
5. Python dependencies
6. Wizard module availability
7. Volume write permissions
8. Telemetry module

## Health Checks

The engine container includes a health check:

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

Check container health:

```bash
docker inspect --format='{{.State.Health.Status}}' bazari-engine
```

## Logging

Logs are persisted in the `engine-logs` volume and use Docker's json-file driver:

```bash
# View real-time logs
docker compose logs -f engine

# View last 100 lines
docker compose logs --tail 100 engine

# Export logs
docker compose logs engine > engine.log
```

Log rotation is configured:
- Max size: 10MB per file
- Max files: 3

## Troubleshooting

### Container Won't Start

```bash
# Check compose config
docker compose config

# View container logs
docker compose logs engine

# Check health status
docker inspect bazari-engine --format='{{json .State.Health}}'
```

### Python Dependencies Missing

If pip install fails in air-gapped mode:

```bash
# Option 1: Pre-download wheels
pip download pyyaml jsonschema jinja2 -d ./wheels/

# Option 2: Build custom image with dependencies
docker build -t bazari-engine:custom .
```

### Volume Permission Issues

```bash
# Check volume mounts
docker exec bazari-engine ls -la /data /logs

# Fix permissions if needed
docker exec bazari-engine chmod 777 /data /logs
```

### Network Issues in Air-Gapped Mode

```bash
# Verify no external access
docker exec bazari-engine python -c "import socket; socket.gethostbyname('google.com')"
# Should fail with: socket.gaierror: [Errno -2] Name or service not known

# Check network isolation
docker network inspect deploy_engine-network
```

## Security Considerations

1. **No Secrets in Repository**: All secrets should be provided via environment variables or mounted files
2. **Read-Only Source**: Engine source is mounted read-only
3. **Non-Root User**: Consider running as non-root in production
4. **Network Isolation**: Use internal networks for air-gapped deployments
5. **Volume Permissions**: Review and restrict volume access as needed

## Production Checklist

Before deploying to production:

- [ ] Review and customize `.env` file
- [ ] Configure appropriate volume permissions
- [ ] Set up log rotation/forwarding
- [ ] Configure network isolation if needed
- [ ] Set up health monitoring
- [ ] Document rollback procedure
- [ ] Test backup/restore of volumes
- [ ] Verify air-gapped operation (if applicable)

## Support

For issues and feature requests:
- GitHub: https://github.com/bazari/engine/issues
- Documentation: /home/bazari/engine/docs/

## Version

- Distribution Version: 1.0.0
- Engine Version: 1.0.0
- Compose File Version: 3.8
