"""OpenAPI contract emitter."""

import yaml
from typing import Dict, Any

from engine.ise.idl_parser import ParsedIDL


def emit_openapi(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit OpenAPI spec from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        OpenAPI spec as dict.
    """
    paths = {}
    schemas = {}

    for entity in parsed.entities:
        entity_type = entity.entity_type
        entity_name = entity.name
        plural = f"{entity_type}s"

        # Build schema
        properties = {}
        required = []

        for field in entity.fields:
            prop = {}
            if field.field_type == "number":
                prop["type"] = "number"
            elif field.field_type == "string":
                prop["type"] = "string"
            elif field.field_type == "boolean":
                prop["type"] = "boolean"
            else:
                prop["type"] = "string"

            properties[field.name] = prop

            if field.required:
                required.append(field.name)

        # Default schema for expense
        if not properties and entity_type == "expense":
            properties = {
                "amount": {"type": "number"},
                "description": {"type": "string"},
            }
            required = ["amount"]

        schemas[entity_name] = {
            "type": "object",
            "properties": properties,
            "required": required if required else None,
        }

        # Remove None values
        if schemas[entity_name]["required"] is None:
            del schemas[entity_name]["required"]

        # Create path
        paths[f"/finance/{plural}"] = {
            "post": {
                "summary": f"Create {entity_name}",
                "operationId": f"create_{entity_type}",
                "tags": ["finance"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}"}
                        }
                    }
                },
                "responses": {
                    "202": {
                        "description": "Created (pending approval)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        f"{entity_type}_id": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                        "status": {"type": "string"},
                                    }
                                }
                            }
                        }
                    },
                    "422": {"description": "Validation error"},
                }
            }
        }

    # Add approval endpoints
    has_approval = any(uc.has_approval for uc in parsed.usecases)
    if has_approval:
        paths["/approvals/{id}/decide"] = {
            "post": {
                "summary": "Decide on approval",
                "operationId": "decide_approval",
                "tags": ["approvals"],
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "decision": {
                                        "type": "string",
                                        "enum": ["approve", "reject"]
                                    }
                                },
                                "required": ["decision"]
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Decision recorded"},
                    "403": {"description": "Forbidden"},
                    "404": {"description": "Not found"},
                    "409": {"description": "SoD violation"},
                }
            }
        }

    # Add health endpoint
    paths["/health"] = {
        "get": {
            "summary": "Health check",
            "operationId": "health_check",
            "tags": ["system"],
            "responses": {
                "200": {
                    "description": "Healthy",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "status": {"type": "string"},
                                    "mode": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": f"{parsed.system_name} API",
            "version": parsed.version,
        },
        "paths": dict(sorted(paths.items())),
        "components": {
            "schemas": dict(sorted(schemas.items())),
            "securitySchemes": {
                "ActorHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Actor-Id"
                }
            }
        }
    }


def emit_openapi_yaml(parsed: ParsedIDL) -> str:
    """Emit OpenAPI spec as YAML string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        YAML string.
    """
    spec = emit_openapi(parsed)
    return yaml.dump(spec, default_flow_style=False, sort_keys=True, allow_unicode=True)
