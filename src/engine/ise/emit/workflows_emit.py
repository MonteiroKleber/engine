"""Workflows contract emitter."""

import json
from typing import Dict, Any, List

from engine.ise.idl_parser import ParsedIDL


def emit_workflows(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit workflows contract from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        Workflows contract as dict.
    """
    workflows = []

    for uc in parsed.usecases:
        steps = []
        step_num = 0

        # Parse main_flow into steps
        flow_parts = uc.main_flow.split("->") if "->" in uc.main_flow else [uc.main_flow]

        for part in flow_parts:
            action = part.strip().lower()
            if not action:
                continue

            step = {
                "step_key": f"step-{step_num:03d}",
                "action": action,
            }

            # Assign actor based on action
            if action == "approve" and uc.approval_role:
                step["actor_ref"] = f"actor-{uc.approval_role}"
            elif uc.actor:
                step["actor_ref"] = f"actor-{uc.actor}"

            # Add entity ref if we have entities
            if parsed.entities:
                step["entity_ref"] = f"entity-{parsed.entities[0].entity_type}"

            steps.append(step)
            step_num += 1

        if not steps:
            # Default workflow
            steps = [
                {
                    "step_key": "step-000",
                    "action": "create",
                    "actor_ref": f"actor-{uc.actor}" if uc.actor else "actor-user",
                }
            ]
            if uc.has_approval:
                steps.append({
                    "step_key": "step-001",
                    "action": "approve",
                    "actor_ref": f"actor-{uc.approval_role}" if uc.approval_role else "actor-manager",
                })

        workflows.append({
            "workflow_key": f"workflow-{_normalize_key(uc.name)}",
            "name": uc.name or "Default Workflow",
            "steps": steps,
        })

    # Ensure at least one workflow
    if not workflows:
        workflows.append({
            "workflow_key": "workflow-default",
            "name": "Default Workflow",
            "steps": [
                {"step_key": "step-000", "action": "create"},
            ],
        })

    return {
        "version": "1.0",
        "name": "workflows",
        "workflows": sorted(workflows, key=lambda w: w["workflow_key"]),
    }


def _normalize_key(text: str) -> str:
    """Normalize text to a valid key."""
    if not text:
        return "default"
    key = text.lower().strip()
    key = "".join(c if c.isalnum() else "_" for c in key)
    while "__" in key:
        key = key.replace("__", "_")
    return key.strip("_") or "default"


def emit_workflows_json(parsed: ParsedIDL) -> str:
    """Emit workflows contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    return json.dumps(emit_workflows(parsed), indent=2, sort_keys=True)
