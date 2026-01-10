# Installation Guide

## Prerequisites

### Local Installation

- Python 3.10 or higher
- pip (Python package manager)
- Docker and Docker Compose (for release mode)

### Docker Distribution

- Docker 20.10 or higher
- Docker Compose v2

## Local Installation

### Step 1: Verify Python Version

```bash
python --version
# Expected: Python 3.10.x or higher
```

### Step 2: Clone Repository

```bash
cd /home/bazari
git clone <repository-url> engine
cd engine
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `pyyaml` - YAML processing
- `jsonschema` - Schema validation
- `jinja2` - Template rendering

### Step 4: Verify Installation

```bash
python main.py --version
# Expected: Bazari Engine v1.0.0 (Genesis)
```

### Step 5: Run Tests

```bash
python -m pytest tests/ -v
```

## Docker Distribution Installation

The docker-compose distribution is located at `/home/bazari/engine/deploy/distribution/`.

### Step 1: Navigate to Distribution

```bash
cd /home/bazari/engine/deploy/distribution
```

### Step 2: Configure Environment

```bash
cp .env.example .env
# Edit .env if needed
```

### Step 3: Start Services

```bash
./scripts/up.sh -d
```

### Step 4: Verify Deployment

```bash
./scripts/smoke.sh
```

### Step 5: Check Service Status

```bash
docker compose ps
```

## Directory Structure

After installation, your directory structure should be:

```
/home/bazari/
├── engine/                     # Engine source (immutable)
│   ├── main.py                 # Main entry point
│   ├── wizard/                 # Wizard module
│   ├── episodes/               # Episode management
│   ├── blueprints/             # Blueprint registry
│   ├── auditpack/              # AuditPack generator
│   ├── observability/          # Telemetry
│   ├── schemas/                # JSON schemas
│   ├── deploy/distribution/    # Docker distribution
│   └── VERSION                 # Version file
├── generated/                  # Generated projects (created on first run)
└── templates/                  # Code templates (immutable)
```

## Air-Gapped Installation

For environments without internet access.

### Preparation (Online Machine)

```bash
cd /home/bazari/engine/deploy/distribution

# Save Docker images
./scripts/verify_airgapped.sh --save

# This creates: bazari-engine-images.tar
```

### Transfer Files

Copy to air-gapped machine:
- `bazari-engine-images.tar`
- `/home/bazari/engine/` directory (entire engine source)

### Installation (Offline Machine)

```bash
cd /home/bazari/engine/deploy/distribution

# Load Docker images
./scripts/verify_airgapped.sh --load

# Enable air-gapped mode
echo "ENGINE_AIRGAPPED=true" >> .env

# Start services
./scripts/up.sh -d

# Verify air-gapped configuration
./scripts/verify_airgapped.sh
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_VERSION` | `1.0.0` | Engine version |
| `ENGINE_SOURCE` | `../../` | Path to engine source |
| `GENERATED_ROOT` | `/tmp/generated` | Output directory |
| `TELEMETRY_ENABLED` | `true` | Enable telemetry |
| `ENGINE_AIRGAPPED` | `false` | Air-gapped mode |

### Paths Configuration

Default paths in `main.py`:

```python
# Store root (artifacts)
--store-root=/home/bazari/engine/demo_store

# Generated projects
GENERATED_ROOT=/home/bazari/generated/
```

## Verification Commands

### Check Version

```bash
python main.py --version
```

### Check Wizard

```bash
python -m wizard.wizard_cli --help
```

### Check Episodes CLI

```bash
python -m episodes.episodes_cli --help
```

### Check Docker (if using distribution)

```bash
docker exec bazari-engine python -c "from version import __version__; print(__version__)"
```

## Uninstallation

### Local Installation

```bash
# Remove generated data
rm -rf /home/bazari/generated/*
rm -rf /home/bazari/engine/demo_store/*

# Remove engine (optional)
rm -rf /home/bazari/engine
```

### Docker Distribution

```bash
cd /home/bazari/engine/deploy/distribution

# Stop and remove containers
./scripts/down.sh -v

# Remove images
docker rmi $(docker compose config --images)
```

## Next Steps

After installation:
1. [Start a wizard session](02_onboarding_wizard.md)
2. [Run the engine](04_running_engine.md)
