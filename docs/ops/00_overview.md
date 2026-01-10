# Bazari Engine - Operations Manual

Version: 1.0.0

## Purpose

This manual provides standard operating procedures (SOPs) for the Bazari Engine, covering the complete lifecycle from project onboarding to audit package generation.

## System Overview

Bazari Engine is a deterministic application generator that transforms natural language specifications into complete, deployable systems with full audit trail.

### Core Components

| Component | Description | Location |
|-----------|-------------|----------|
| Engine | Main pipeline orchestrator | `/home/bazari/engine/` |
| Wizard | Interactive onboarding tool | `wizard/wizard_cli.py` |
| Episodes | Execution tracking system | `episodes/episode_store.py` |
| Blueprints | Domain-specific templates | `blueprints/registry/` |
| AuditPack | Audit package generator | `auditpack/auditpack.py` |

### Data Directories

| Directory | Purpose |
|-----------|---------|
| `/home/bazari/engine/` | Engine source code (immutable) |
| `/home/bazari/generated/` | Generated projects output |
| `/home/bazari/templates/` | Code templates (immutable) |
| `.engine/episodes/` | Episode store (per project) |
| `.engine/wizard/sessions/` | Wizard sessions |

## Operational Lifecycle

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Wizard    │───▶│  Blueprint  │───▶│   Engine    │
│   (Start)   │    │   (Apply)   │    │   (Run)     │
└─────────────┘    └─────────────┘    └─────────────┘
                                            │
                                            ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  AuditPack  │◀───│  Approval   │◀───│  Episode    │
│  (Export)   │    │   (Gate)    │    │  (Created)  │
└─────────────┘    └─────────────┘    └─────────────┘
```

### Lifecycle Stages

1. **Onboarding (Wizard)**: Create project session, define requirements
2. **Blueprint Application**: Apply domain-specific template to IDL Draft
3. **Pipeline Execution**: Run engine to generate system artifacts
4. **Episode Creation**: Automatically create execution record
5. **Approval Gate**: Human approval before release
6. **Change Requests**: Incremental changes with full traceability
7. **Audit Export**: Generate verifiable audit package

## Key Concepts

### Episode

An episode is an immutable record of a single pipeline execution. Each episode contains:
- Manifest with integrity hashes
- Runlog with execution details
- Generated artifacts
- Approvals (if any)
- Change request reference (if applicable)

### Approval Gate

The approval gate blocks release until human approval is registered. This ensures no system goes to production without explicit sign-off.

### Change Request (CR)

A formal request to modify an existing episode. CRs create a chain of episodes linked by `previous_episode_id`.

### AuditPack

A reproducible, verifiable ZIP archive containing all evidence needed for offline audit. Includes cryptographic hashes for integrity verification.

## Document Index

| Document | Content |
|----------|---------|
| [01_installation.md](01_installation.md) | Local and Docker installation |
| [02_onboarding_wizard.md](02_onboarding_wizard.md) | Wizard session lifecycle |
| [03_blueprints.md](03_blueprints.md) | Blueprint registry and application |
| [04_running_engine.md](04_running_engine.md) | Pipeline execution modes |
| [05_approvals_and_episodes.md](05_approvals_and_episodes.md) | Episode management and approvals |
| [06_change_requests.md](06_change_requests.md) | CR workflow and episode chaining |
| [07_auditpack_and_audits.md](07_auditpack_and_audits.md) | Audit package generation |
| [08_troubleshooting.md](08_troubleshooting.md) | Common issues and solutions |

## Quick Reference

### Essential Commands

```bash
# Check version
python main.py --version

# Start wizard session
python main.py wizard start --project MyProject --domain healthcare

# Export wizard session
python main.py wizard export <session_id>

# Run pipeline (skip build)
python main.py --project myproject --input "My system spec" --skip-build

# Run pipeline (full release)
python main.py --project myproject --input spec.idl --input-mode idl --release

# Approve episode
python -m episodes.episodes_cli approve --episode-id <id> --decision approve --reason "..." --approver-name "..." --role "..."

# Create change request execution
python -m episodes.episodes_cli change --previous-episode-id <id> --cr change_request.json

# Generate audit pack
python -m episodes.episodes_cli auditpack --episode-id <id> --out audit.zip
```

### Status Codes

| Status | Description |
|--------|-------------|
| `success` | Execution completed successfully |
| `blocked` | Execution blocked by gate |
| `failed` | Execution failed with error |

### Error Prefixes

| Prefix | Domain |
|--------|--------|
| `SCHEMA:` | Schema validation error |
| `INTEGRITY:` | Integrity verification failure |
| `GOVERNANCE:` | Governance/approval violation |
| `SECURITY:` | Security policy violation |
| `POLICY:` | Business policy violation |

## Support Contacts

- Documentation: `/home/bazari/engine/docs/`
- Issue Tracker: GitHub Issues
- Engine Logs: `./demo_store/<project>/runlog.json`
