# Blueprints

Blueprints are domain-specific templates that pre-fill IDL Drafts with common patterns, entities, and business rules.

## Registry Location

Blueprints are stored in the registry:

```
/home/bazari/engine/blueprints/registry/
├── index.json          # Registry index
└── blueprints/         # Blueprint files
    ├── petclinic-v1.json
    └── ...
```

## Registry Index

The `index.json` tracks all registered blueprints:

```json
{
  "schema_version": "blueprint_registry.v1",
  "blueprints": [
    {
      "blueprint_id": "petclinic-v1",
      "path": "blueprints/petclinic-v1.json",
      "content_hash_sha256": "sha256:abc123...",
      "domain": "healthcare",
      "version": "1.0.0"
    }
  ],
  "integrity_hash_sha256": "sha256:def456..."
}
```

## Blueprint Structure

Each blueprint defines:

```json
{
  "schema_version": "blueprint.v1",
  "blueprint_id": "petclinic-v1",
  "name": "Pet Clinic",
  "domain": "healthcare",
  "version": "1.0.0",
  "description": "Veterinary clinic management system",
  "prefilled_actors": ["Admin", "Veterinarian", "Owner"],
  "prefilled_entities": [
    {
      "name": "Pet",
      "fields": [
        {"name": "name", "type": "string"},
        {"name": "birthDate", "type": "date"},
        {"name": "species", "type": "enum", "values": ["DOG", "CAT"]}
      ]
    },
    {
      "name": "Owner",
      "fields": [
        {"name": "firstName", "type": "string"},
        {"name": "lastName", "type": "string"},
        {"name": "telephone", "type": "string"}
      ]
    }
  ],
  "prefilled_usecases": [
    "CreatePet",
    "UpdatePet",
    "FindPetsByOwner",
    "CreateOwner"
  ],
  "invariants": [
    {
      "name": "pet_must_have_owner",
      "description": "Every pet must be associated with an owner",
      "severity": "must"
    }
  ]
}
```

## Applying a Blueprint

### During Wizard Export

```bash
python main.py wizard export <session_id> --blueprint-id petclinic-v1
```

### Blueprint Merge Behavior

When a blueprint is applied:

1. Blueprint actors are merged with session actors
2. Blueprint entities are added (session entities take precedence)
3. Blueprint use cases are merged
4. Blueprint invariants are added to the draft

### Verification

The export runlog records blueprint application:

```json
{
  "blueprint_applied": {
    "blueprint_id": "petclinic-v1",
    "content_hash_sha256": "sha256:abc123...",
    "merge_summary": {
      "actors_added": 2,
      "entities_added": 3,
      "usecases_added": 4,
      "invariants_added": 1
    }
  }
}
```

## Listing Available Blueprints

View the registry index:

```bash
cat /home/bazari/engine/blueprints/registry/index.json
```

Or programmatically:

```python
from blueprints.registry_v1 import load_registry

registry = load_registry()
for bp in registry["blueprints"]:
    print(f"{bp['blueprint_id']} - {bp['domain']} v{bp['version']}")
```

## Registry Integrity

The registry uses content hashes for integrity verification.

### Verify Registry

```python
from blueprints.registry_v1 import verify_registry

try:
    verify_registry()
    print("Registry integrity OK")
except RegistryIntegrityError as e:
    print(f"INTEGRITY: {e}")
```

### Integrity Errors

| Error | Cause |
|-------|-------|
| `INTEGRITY: Blueprint hash mismatch` | Blueprint file was modified |
| `INTEGRITY: Registry hash mismatch` | Index file was modified |
| `INTEGRITY: Blueprint not found` | Blueprint file missing |

## Creating a Blueprint

### Step 1: Create Blueprint File

Create a new blueprint JSON in `blueprints/registry/blueprints/`:

```json
{
  "schema_version": "blueprint.v1",
  "blueprint_id": "myapp-v1",
  "name": "My Application",
  "domain": "custom",
  "version": "1.0.0",
  "description": "Custom application template",
  "prefilled_actors": ["Admin", "User"],
  "prefilled_entities": [
    {
      "name": "Item",
      "fields": [
        {"name": "name", "type": "string"},
        {"name": "status", "type": "enum", "values": ["ACTIVE", "INACTIVE"]}
      ]
    }
  ],
  "prefilled_usecases": ["CreateItem", "ListItems"],
  "invariants": []
}
```

### Step 2: Validate Blueprint

```python
from blueprints.blueprint_v1 import load_blueprint, validate_blueprint

blueprint = load_blueprint("blueprints/registry/blueprints/myapp-v1.json")
validate_blueprint(blueprint)  # Raises if invalid
```

### Step 3: Register Blueprint

```python
from blueprints.registry_v1 import register_blueprint

register_blueprint(
    blueprint_id="myapp-v1",
    blueprint_path="blueprints/myapp-v1.json",
    domain="custom",
    version="1.0.0"
)
```

### Step 4: Verify Registration

```bash
cat /home/bazari/engine/blueprints/registry/index.json | grep myapp
```

## Blueprint Selection

The engine can auto-select blueprints based on domain:

```python
from blueprints.registry_v1 import find_blueprints_by_domain

healthcare_blueprints = find_blueprints_by_domain("healthcare")
```

## Schema Reference

Blueprint schema: `/home/bazari/engine/schemas/blueprint.v1.json`

Key constraints:
- `blueprint_id`: Unique identifier (pattern: `^[a-z][a-z0-9-]*-v[0-9]+$`)
- `domain`: One of predefined domains
- `version`: Semantic version string
- `prefilled_entities`: Array of entity definitions

## Next Steps

After applying a blueprint:
1. [Run the engine](04_running_engine.md)
