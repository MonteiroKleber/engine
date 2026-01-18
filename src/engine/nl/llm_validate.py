"""Validation for LLM extraction output."""

import json
from typing import Dict, Any, Tuple, List, Optional

from engine.nl.extractors.providers.base import (
    LLM_INVALID_JSON,
    LLM_SCHEMA_INVALID,
    LLM_EMPTY_RESPONSE,
)


def validate_llm_extraction(response_text: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Validate LLM extraction response.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Tuple of (is_valid, parsed_data, error_code).
        If valid: (True, data, None)
        If invalid: (False, None, error_code)
    """
    if not response_text or not response_text.strip():
        return False, None, LLM_EMPTY_RESPONSE

    # Try to parse JSON
    try:
        # Handle potential markdown code blocks
        text = response_text.strip()
        if text.startswith("```"):
            # Remove markdown code blocks
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            text = "\n".join(json_lines)

        data = json.loads(text)
    except json.JSONDecodeError:
        return False, None, LLM_INVALID_JSON

    # Validate schema
    errors = _validate_schema(data)
    if errors:
        return False, None, LLM_SCHEMA_INVALID

    return True, data, None


def _validate_schema(data: Dict[str, Any]) -> List[str]:
    """Validate the extraction schema.

    Args:
        data: Parsed JSON data.

    Returns:
        List of validation errors (empty if valid).
    """
    errors = []

    # Must have extraction key
    if "extraction" not in data:
        errors.append("Missing 'extraction' key")
        return errors

    extraction = data["extraction"]

    # Validate actors
    if "actors" in extraction:
        for i, actor in enumerate(extraction["actors"]):
            if not isinstance(actor, dict):
                errors.append(f"actors[{i}] is not a dict")
                continue
            if "actor_key" not in actor:
                errors.append(f"actors[{i}] missing 'actor_key'")
            elif not actor["actor_key"].startswith("actor-"):
                errors.append(f"actors[{i}].actor_key must start with 'actor-'")
            if "name" not in actor:
                errors.append(f"actors[{i}] missing 'name'")
            if "roles" not in actor:
                errors.append(f"actors[{i}] missing 'roles'")
            elif not isinstance(actor.get("roles"), list):
                errors.append(f"actors[{i}].roles must be a list")

    # Validate entities
    if "entities" in extraction:
        for i, entity in enumerate(extraction["entities"]):
            if not isinstance(entity, dict):
                errors.append(f"entities[{i}] is not a dict")
                continue
            if "entity_key" not in entity:
                errors.append(f"entities[{i}] missing 'entity_key'")
            elif not entity["entity_key"].startswith("entity-"):
                errors.append(f"entities[{i}].entity_key must start with 'entity-'")
            if "name" not in entity:
                errors.append(f"entities[{i}] missing 'name'")
            if "entity_type" not in entity:
                errors.append(f"entities[{i}] missing 'entity_type'")

    # Validate policies
    if "policies" in extraction:
        valid_types = {"approval", "sod", "rbac", "invariant"}
        for i, policy in enumerate(extraction["policies"]):
            if not isinstance(policy, dict):
                errors.append(f"policies[{i}] is not a dict")
                continue
            if "policy_key" not in policy:
                errors.append(f"policies[{i}] missing 'policy_key'")
            elif not policy["policy_key"].startswith("policy-"):
                errors.append(f"policies[{i}].policy_key must start with 'policy-'")
            if "policy_type" not in policy:
                errors.append(f"policies[{i}] missing 'policy_type'")
            elif policy["policy_type"] not in valid_types:
                errors.append(f"policies[{i}].policy_type must be one of {valid_types}")
            if "description" not in policy:
                errors.append(f"policies[{i}] missing 'description'")

    return errors


def normalize_llm_extraction(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize LLM extraction data.

    Ensures all keys are lowercase, roles are normalized, etc.

    Args:
        data: Parsed and validated extraction data.

    Returns:
        Normalized extraction data.
    """
    extraction = data.get("extraction", {})

    # Normalize actors
    actors = []
    for actor in extraction.get("actors", []):
        actors.append({
            "actor_key": actor["actor_key"].lower(),
            "name": actor["name"],
            "roles": sorted([r.lower() for r in actor.get("roles", [])]),
            "source_segment": actor.get("source_segment"),
        })

    # Normalize entities
    entities = []
    for entity in extraction.get("entities", []):
        entities.append({
            "entity_key": entity["entity_key"].lower(),
            "name": entity["name"],
            "entity_type": entity["entity_type"].lower(),
            "attributes": entity.get("attributes", {}),
            "source_segment": entity.get("source_segment"),
        })

    # Normalize policies
    policies = []
    for policy in extraction.get("policies", []):
        policies.append({
            "policy_key": policy["policy_key"].lower(),
            "policy_type": policy["policy_type"].lower(),
            "description": policy["description"],
            "actor_refs": sorted([r.lower() for r in policy.get("actor_refs", [])]),
            "entity_refs": sorted([r.lower() for r in policy.get("entity_refs", [])]),
            "conditions": policy.get("conditions", {}),
            "source_segment": policy.get("source_segment"),
        })

    # Normalize workflows
    workflows = []
    for workflow in extraction.get("workflows", []):
        steps = []
        for step in workflow.get("steps", []):
            steps.append({
                "step_key": step["step_key"],
                "action": step["action"],
                "actor_ref": step.get("actor_ref"),
                "entity_ref": step.get("entity_ref"),
                "conditions": step.get("conditions", {}),
            })
        workflows.append({
            "workflow_key": workflow["workflow_key"],
            "name": workflow["name"],
            "steps": steps,
            "source_segment": workflow.get("source_segment"),
        })

    return {
        "extraction": {
            "actors": sorted(actors, key=lambda x: x["actor_key"]),
            "entities": sorted(entities, key=lambda x: x["entity_key"]),
            "policies": sorted(policies, key=lambda x: x["policy_key"]),
            "workflows": sorted(workflows, key=lambda x: x["workflow_key"]),
        }
    }
