# Bazari Engine v1.0.0 - Release Notes

**Release Date:** 2026-01-03

## Overview

Bazari Engine v1.0.0 is the first stable release of the text-to-running-system pipeline.
This version implements the complete flow from natural language requirements to a running
application with backend, frontend, and database.

## Features

### Core Pipeline
- **Intake**: Normalizes raw text input and classifies blueprints
- **SRS Generation**: Converts requirements to structured Software Requirements Specification
- **IR Generation**: Creates Intermediate Representation with domain model
- **Contracts Generation**: Produces OpenAPI 3.0 spec and RBAC policies
- **Plan Generation**: Creates execution plan with ordered tasks

### Validators
- SRS Validator Gate with schema validation
- IR Validator with entity and relationship checks
- OpenAPI Validator (OAS 3.0 compliance)
- RBAC Validator with role and permission checks
- Plan Validator with task dependency verification
- Policy Validator for cross-artifact consistency
- Build Validator for compilation checks

### Code Generation
- **Repo Generator**: Creates project structure from templates
- **Patch Engine**: Applies incremental code patches
- **Patch Generator v1**: Generates patches from PLAN artifacts
- **Fix Loop Agent**: Auto-corrects build errors (up to 3 attempts)

### Templates
- Spring Boot backend (Java 17, Maven)
- React + Vite frontend (TypeScript)
- PostgreSQL with Flyway migrations
- Docker Compose orchestration

### Release Pipeline
- **QA Release Agent**: Smoke tests and checklist validation
- **Smoke Runner**: Backend healthcheck and CRUD tests, frontend build tests
- **Docker Compose Validator**: Ensures required services (postgres, backend, frontend)
- **Release Checklist**: Final gates before release

### Blueprints
- Generic Blueprint (FORCED_GENERIC fallback)
- Blueprint Registry for custom blueprints

### Artifacts Store
- Versioned artifacts (SRS, IR, OAS, RBAC, PLAN)
- Run logs with full hash chain
- YAML and JSON support

## Freeze Rules (v1.0.0)

The following components are frozen and will only change with a version bump:

### Schemas (Immutable in v1.x)
- `schemas/srs.schema.json` - SRS structure
- `schemas/ir.schema.json` - IR structure
- `schemas/plan.schema.json` - PLAN structure
- `schemas/rbac.schema.json` - RBAC structure

### Templates (Versioned)
- `templates/spring-boot/` - Backend template v1.0
- `templates/react-vite/` - Frontend template v1.0
- `templates/postgres-flyway/` - Database template v1.0

### Policies (Immutable in v1.x)
- Authenticated endpoints required
- No PII logging
- No hardcoded secrets
- All artifacts must have hash chain

## API Stability

### Stable APIs (v1.0)
- `Engine.run()` - Artifact generation
- `Engine.run_with_build()` - Full build pipeline
- `Engine.run_release()` - Release pipeline with docker

### Internal APIs (May Change)
- Validator internal methods
- Agent internal methods
- Store internal methods

## Requirements

- Python 3.10+
- Node.js 18+ (for frontend builds)
- Java 17+ (for backend builds)
- Docker & Docker Compose (for release mode)
- Maven 3.8+ (for backend builds)

## Known Limitations

- Blueprint registry only has GenericBlueprint
- Live smoke tests require running services
- Fix loop limited to 3 attempts

## Migration Notes

This is the initial release - no migration required.

## Test Coverage

- 1199 tests passing
- All validators tested
- All agents tested
- Release pipeline tested

## Contributors

- Bazari Engine Team
- Generated with Claude Code

---

For more information, see the project documentation.
