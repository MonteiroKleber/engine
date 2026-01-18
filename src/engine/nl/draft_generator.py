"""Draft IDL Generator from SIR."""

from typing import Dict, Any, List, Optional, Union

from engine.nl.schemas.sir_v1 import SIRv1, Policy, Actor, Entity, Workflow, RuntimePolicy
from engine.nl.canonical import canonical_dict, normalize_roles


def generate_draft(sir: SIRv1) -> Dict[str, Any]:
    """Generate draft IDL from SIR.

    Args:
        sir: Structured Intermediate Representation.

    Returns:
        Draft IDL as a dictionary.

    Raises:
        ValueError: If SIR is invalid or has no policies.
    """
    if not sir.extraction.policies:
        raise ValueError("No policies found in SIR")

    draft = {
        "version": "1.0",
        "name": "draft-policy",
        "generated_from": "sir",
    }

    # Generate RBAC section
    rbac = _generate_rbac(sir)
    if rbac["roles"]:
        draft["rbac"] = rbac

    # Generate Approvals section
    approvals = _generate_approvals(sir)
    if approvals["rules"]:
        draft["approvals"] = approvals

    # Generate SoD section
    sod = _generate_sod(sir)
    if sod["rules"]:
        draft["sod"] = sod

    # Generate Invariants section
    invariants = _generate_invariants(sir)
    if invariants:
        draft["invariants"] = invariants

    # Generate Workflows section
    workflows = _generate_workflows(sir)
    if workflows:
        draft["workflows"] = workflows

    # Generate runtime policies section for policies.json v1.1
    runtime_policies = _generate_runtime_policies(sir)
    if runtime_policies:
        draft["policies"] = runtime_policies

    # Generate dept runtime policies for multi-dept mode
    dept_runtime_policies = _generate_dept_runtime_policies(sir)
    if dept_runtime_policies:
        draft["dept_policies"] = dept_runtime_policies

    return canonical_dict(draft)


def _generate_rbac(sir: SIRv1) -> Dict[str, Any]:
    """Generate RBAC section from SIR."""
    roles = []

    # Extract roles from actors
    for actor in sir.extraction.actors:
        for role in actor.roles:
            # Determine permissions based on policies
            permissions = _get_permissions_for_role(role, sir)
            roles.append({
                "name": role.lower(),
                "permissions": sorted(permissions),
            })

    # Deduplicate roles by name
    seen = set()
    unique_roles = []
    for role in sorted(roles, key=lambda r: r["name"]):
        if role["name"] not in seen:
            seen.add(role["name"])
            unique_roles.append(role)

    return {
        "version": "1.0",
        "name": "rbac",
        "roles": unique_roles,
    }


def _get_permissions_for_role(role: str, sir: SIRv1) -> List[str]:
    """Get permissions for a role based on policies and entities."""
    permissions = set()

    # Get entities
    entities = [e.entity_type for e in sir.extraction.entities]
    if not entities:
        entities = ["resource"]

    # Check RBAC policies
    for policy in sir.extraction.policies:
        if policy.policy_type == "rbac":
            for entity in entities:
                # Add basic CRUD permissions
                permissions.add(f"{entity}.read")
                if role in ["manager", "admin", "approver", "supervisor"]:
                    permissions.add(f"{entity}.approve")
                if role in ["analyst", "employee", "user"]:
                    permissions.add(f"{entity}.create")

    # Default permissions based on role type
    for entity in entities:
        if role in ["manager", "admin", "supervisor", "director"]:
            permissions.update([
                f"{entity}.create",
                f"{entity}.read",
                f"{entity}.approve",
            ])
        elif role in ["analyst", "employee", "user"]:
            permissions.update([
                f"{entity}.create",
                f"{entity}.read",
            ])
        elif role in ["viewer", "auditor"]:
            permissions.add(f"{entity}.read")
        elif role == "approver":
            permissions.update([
                f"{entity}.read",
                f"{entity}.approve",
            ])

    return list(permissions)


def _generate_approvals(sir: SIRv1) -> Dict[str, Any]:
    """Generate Approvals section from SIR."""
    rules = []

    # Find approval policies
    for policy in sir.extraction.policies:
        if policy.policy_type == "approval":
            # Determine entity
            entity = "resource"
            if policy.entity_refs and sir.extraction.entities:
                for e in sir.extraction.entities:
                    if e.entity_key in policy.entity_refs:
                        entity = e.entity_type
                        break

            # Determine approver roles
            approver_roles = []
            if policy.actor_refs:
                for actor in sir.extraction.actors:
                    if actor.actor_key in policy.actor_refs:
                        for role in actor.roles:
                            if role in ["manager", "admin", "approver", "supervisor", "director"]:
                                approver_roles.append(role)

            if not approver_roles:
                approver_roles = ["manager"]

            rules.append({
                "rule_name": f"{entity}.create",
                "trigger": {"api": f"POST /finance/{entity}s"},
                "approver_roles": sorted(approver_roles),
                "quorum": 1,
            })

    return {
        "version": "1.0",
        "name": "approvals",
        "rules": sorted(rules, key=lambda r: r["rule_name"]),
    }


def _generate_sod(sir: SIRv1) -> Dict[str, Any]:
    """Generate SoD section from SIR."""
    rules = []

    # Find SoD policies
    for policy in sir.extraction.policies:
        if policy.policy_type == "sod":
            # Determine entity
            entity = "resource"
            if policy.entity_refs and sir.extraction.entities:
                for e in sir.extraction.entities:
                    if e.entity_key in policy.entity_refs:
                        entity = e.entity_type
                        break

            rules.append({
                "rule_name": f"no_self_approval_{entity}",
                "constraint": "no_self_approval",
                "scope": {"entity": entity},
            })

    return {
        "version": "1.0",
        "name": "sod",
        "rules": sorted(rules, key=lambda r: r["rule_name"]),
    }


def _generate_invariants(sir: SIRv1) -> Dict[str, Any]:
    """Generate Invariants section from SIR."""
    invariants = {}

    # Find invariant policies
    for policy in sir.extraction.policies:
        if policy.policy_type == "invariant":
            # Determine entity
            entity = "resource"
            if policy.entity_refs and sir.extraction.entities:
                for e in sir.extraction.entities:
                    if e.entity_key in policy.entity_refs:
                        entity = e.entity_type
                        break

            # Parse conditions for limits
            conditions = policy.conditions.get("indicators", [])
            schema = {}

            for indicator in conditions:
                indicator_lower = indicator.lower()
                if "maximum" in indicator_lower or "max" in indicator_lower or "at most" in indicator_lower:
                    schema["amount"] = schema.get("amount", {})
                    schema["amount"]["max"] = 1000000  # Placeholder
                if "minimum" in indicator_lower or "min" in indicator_lower or "at least" in indicator_lower:
                    schema["amount"] = schema.get("amount", {})
                    schema["amount"]["min"] = 0.01  # Placeholder

            if not schema:
                # Default schema
                schema = {
                    "amount": {"min": 0.01, "max": 1000000000},
                    "description": {"max_len": 280, "required": False},
                }

            invariants[entity] = schema

    return {
        "version": "1.0",
        "name": "invariants",
        **invariants,
    } if invariants else {}


def _generate_workflows(sir: SIRv1) -> List[Dict[str, Any]]:
    """Generate Workflows section from SIR."""
    workflows = []

    for workflow in sir.extraction.workflows:
        steps = []
        for step in workflow.steps:
            step_dict = {
                "step_key": step.step_key,
                "action": step.action,
            }
            if step.actor_ref:
                step_dict["actor_ref"] = step.actor_ref
            if step.entity_ref:
                step_dict["entity_ref"] = step.entity_ref
            if step.conditions:
                step_dict["conditions"] = step.conditions
            steps.append(step_dict)

        workflows.append({
            "workflow_key": workflow.workflow_key,
            "name": workflow.name,
            "steps": steps,
        })

    return sorted(workflows, key=lambda w: w["workflow_key"])


def _runtime_policy_to_dict(policy: RuntimePolicy) -> Dict[str, Any]:
    """Convert RuntimePolicy to dict format for IDL.

    Does NOT modify or validate the policy - just converts.
    """
    result: Dict[str, Any] = {
        "policy_id": policy.policy_id,
        "phase": policy.phase,
        "endpoint_sig": policy.endpoint_sig,
        "rule_type": policy.rule_type,
        "field_path": policy.field_path,
    }
    if policy.value is not None:
        result["value"] = policy.value
    if policy.message:
        result["message"] = policy.message
    return result


def _generate_runtime_policies(sir: SIRv1) -> List[Dict[str, Any]]:
    """Generate runtime policies section from SIR.

    Directly outputs extracted runtime policies without modification.
    Does NOT infer or generate policies - only outputs what was extracted.
    """
    policies = []

    for policy in sir.extraction.runtime_policies:
        policies.append(_runtime_policy_to_dict(policy))

    return sorted(policies, key=lambda p: p["policy_id"])


def _generate_dept_runtime_policies(sir: SIRv1) -> Dict[str, List[Dict[str, Any]]]:
    """Generate dept runtime policies section from SIR.

    Directly outputs extracted dept runtime policies without modification.
    Does NOT infer or generate policies - only outputs what was extracted.
    """
    result: Dict[str, List[Dict[str, Any]]] = {}

    for dept_id, policies in sir.extraction.dept_runtime_policies.items():
        dept_policies = []
        for policy in policies:
            dept_policies.append(_runtime_policy_to_dict(policy))
        result[dept_id] = sorted(dept_policies, key=lambda p: p["policy_id"])

    return dict(sorted(result.items()))
