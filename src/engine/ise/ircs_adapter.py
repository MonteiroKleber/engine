"""IRCS v1 → ParsedIDL Adapter.

Converts IRCS v1 canonical JSON (from IDL DSL v1.2.2) to the ParsedIDL
dataclass used by existing ISE emitters.

This adapter enables the canonical compilation path:
    DSL v1.2.2 → IRCS v1 → ParsedIDL → Emitters → Bundle
"""

import json
from typing import Any, Dict, List, Optional

from .idl_parser import (
    ParsedIDL,
    IDLActor,
    IDLEntity,
    IDLField,
    IDLPermission,
    IDLUseCase,
    IDLParseError,
)
from .errors import (
    ISE_IDL_PARSE_FAILED,
    ISE_IDL_INVALID_JSON,
)


# IRCS v1 constants
IRCS_V1_VERSION = "ircs.v1"
SOURCE_IDL_V122 = "idl.v1.2.2"


class IRCSAdapterError(Exception):
    """Error during IRCS v1 → ParsedIDL conversion."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def ircs_to_parsed_idl(ir: Dict[str, Any]) -> ParsedIDL:
    """Convert IRCS v1 JSON to ParsedIDL.

    Args:
        ir: IRCS v1 dict (from parse_dsl or loaded from ir.json)

    Returns:
        ParsedIDL instance ready for emitters

    Raises:
        IRCSAdapterError: If IRCS v1 is invalid or conversion fails
    """
    # Validate IR version
    ir_version = ir.get("ir_version")
    if ir_version != IRCS_V1_VERSION:
        raise IRCSAdapterError(
            code=ISE_IDL_PARSE_FAILED,
            message=f"Expected ir_version '{IRCS_V1_VERSION}', got '{ir_version}'",
            details={"ir_version": ir_version},
        )

    # Extract system info
    system = ir.get("system", {})
    system_name = system.get("name") or system.get("id") or "Unknown"
    version = system.get("version") or ir.get("source_idl_version", "0.0.0")

    # Convert actors
    actors = _convert_actors(ir.get("actors", []))

    # Convert entities (with invariants attached)
    entities = _convert_entities(ir.get("entities", []), ir.get("invariants", []))

    # Generate usecases from workflows + operations
    usecases = _generate_usecases(
        ir.get("workflows", []),
        ir.get("operations", {}),
        ir.get("separation_of_duties", []),
    )

    return ParsedIDL(
        system_name=system_name,
        version=version,
        idl_version="1.1",  # IRCS v1 maps to IDL v1.1 (mandates/autonomy first-class)
        actors=actors,
        entities=entities,
        usecases=usecases,
        departments=[],  # Single mode for now
        contracts=[],
        policies=[],
        mandates=[],
        autonomy=None,
    )


def _convert_actors(actors_data: List[Dict[str, Any]]) -> List[IDLActor]:
    """Convert IRCS v1 actors to IDLActor list.

    IRCS v1 actor format:
    {
        "kind": "human",
        "id": "operator",
        "name": "Operator",
        "auth": "oauth2",
        "permissions": ["finance.expense.create", ...]
    }
    """
    actors = []
    for actor_data in actors_data:
        actor_id = actor_data.get("id", "")
        name = actor_data.get("name", actor_id.title())
        kind = actor_data.get("kind", "human")
        auth = actor_data.get("auth", "none")
        perms_list = actor_data.get("permissions", [])

        # Group permissions by resource
        permissions = _group_permissions(perms_list)

        actors.append(IDLActor(
            name=name,
            role=actor_id.lower(),
            permissions=permissions,
            auth_method=auth,
        ))

    return sorted(actors, key=lambda a: a.role)


def _group_permissions(perms_list: List[str]) -> List[IDLPermission]:
    """Group permission strings by resource.

    Example: ["finance.expense.create", "finance.expense.read"]
    → [IDLPermission(resource="finance.expense", actions=["create", "read"])]
    """
    perm_map: Dict[str, List[str]] = {}
    for perm in perms_list:
        if "." in perm:
            # Split resource.action
            parts = perm.rsplit(".", 1)
            resource, action = parts[0], parts[1]
        else:
            resource, action = perm, "*"

        if resource not in perm_map:
            perm_map[resource] = []
        perm_map[resource].append(action)

    return [
        IDLPermission(resource=res, actions=sorted(acts))
        for res, acts in sorted(perm_map.items())
    ]


def _convert_entities(
    entities_data: List[Dict[str, Any]],
    invariants_data: List[Dict[str, Any]],
) -> List[IDLEntity]:
    """Convert IRCS v1 entities to IDLEntity list.

    IRCS v1 entity format:
    {
        "name": "Expense",
        "storage": {"tenant_field": "tenant_id", "version_field": "version"},
        "fields": [
            {"name": "id", "type": "uuid", "required": true, "unique": true},
            ...
        ]
    }
    """
    entities = []
    for entity_data in entities_data:
        name = entity_data.get("name", "")
        fields_data = entity_data.get("fields", [])

        # Convert fields
        fields = []
        for field_data in fields_data:
            field_name = field_data.get("name", "")
            field_type = field_data.get("type", "string")
            required = field_data.get("required", False)

            # Collect modifiers
            modifiers = []
            if required:
                modifiers.append("required")
            if field_data.get("unique"):
                modifiers.append("unique")
            if field_data.get("indexed"):
                modifiers.append("indexed")

            fields.append(IDLField(
                name=field_name,
                field_type=field_type,
                required=required,
                modifiers=modifiers,
            ))

        entities.append(IDLEntity(
            name=name,
            entity_type=name.lower(),
            fields=fields,
        ))

    return sorted(entities, key=lambda e: e.entity_type)


def _generate_usecases(
    workflows_data: List[Dict[str, Any]],
    operations_data: Dict[str, Any],
    sod_data: List[Dict[str, Any]],
) -> List[IDLUseCase]:
    """Generate IDLUseCase from workflows and operations.

    IRCS v1 workflow format:
    {
        "name": "ExpenseFlow",
        "on_entity": "Expense",
        "states": [...],
        "transitions": [
            {
                "name": "Submit",
                "from": "Draft",
                "to": "PendingApproval",
                "guard": {...},
                "approvals": {...},
                "effects": [...]
            }
        ]
    }

    IRCS v1 operations format:
    {
        "api": [
            {
                "id": "expense_create",
                "method": "POST",
                "path": "/finance/expenses",
                "bind": {"entity": "Expense", "kind": "create"}
            }
        ]
    }
    """
    usecases = []

    # Build SoD lookup by (entity, action)
    sod_lookup: Dict[tuple, Dict[str, Any]] = {}
    for sod_rule in sod_data:
        entity = sod_rule.get("on_entity", "")
        action = sod_rule.get("forbid", {}).get("action", "")
        if entity and action:
            sod_lookup[(entity.lower(), action.lower())] = sod_rule

    # Process API operations
    api_endpoints = operations_data.get("api", [])
    for endpoint in api_endpoints:
        endpoint_id = endpoint.get("id", "")
        bind = endpoint.get("bind", {})
        entity = bind.get("entity", "")
        kind = bind.get("kind", "read")
        workflow = bind.get("workflow")
        transition = bind.get("transition")
        permission = endpoint.get("permission", "")

        # Determine actor from permission prefix
        actor = _infer_actor_from_permission(permission)

        # Determine if approval/sod required
        has_approval = False
        approval_role = None
        has_sod = False

        if workflow and transition:
            # Find transition in workflows
            for wf in workflows_data:
                if wf.get("name") == workflow:
                    for tr in wf.get("transitions", []):
                        if tr.get("name") == transition:
                            approvals = tr.get("approvals")
                            if approvals:
                                has_approval = True
                                roles = approvals.get("roles", [])
                                if roles:
                                    approval_role = roles[0]
                            break

            # Check SoD
            sod_key = (entity.lower(), transition.lower())
            if sod_key in sod_lookup:
                has_sod = True

        # Create usecase
        main_flow = f"{kind}: {endpoint.get('method', 'GET')} {endpoint.get('path', '')}"

        usecases.append(IDLUseCase(
            name=endpoint_id,
            actor=actor,
            main_flow=main_flow,
            has_approval=has_approval,
            has_sod=has_sod,
            approval_role=approval_role,
        ))

    # If no API endpoints, create default usecase from workflows
    if not usecases and workflows_data:
        for wf in workflows_data:
            wf_name = wf.get("name", "default")
            entity = wf.get("on_entity", "")

            has_approval = any(
                tr.get("approvals") for tr in wf.get("transitions", [])
            )
            approval_role = None
            for tr in wf.get("transitions", []):
                approvals = tr.get("approvals")
                if approvals:
                    roles = approvals.get("roles", [])
                    if roles:
                        approval_role = roles[0]
                        break

            # Check SoD for any transition
            has_sod = any(
                (entity.lower(), tr.get("name", "").lower()) in sod_lookup
                for tr in wf.get("transitions", [])
            )

            usecases.append(IDLUseCase(
                name=wf_name,
                actor="user",
                main_flow=" -> ".join(
                    tr.get("name", "") for tr in wf.get("transitions", [])
                ),
                has_approval=has_approval,
                has_sod=has_sod,
                approval_role=approval_role,
            ))

    return sorted(usecases, key=lambda u: u.name)


def _infer_actor_from_permission(permission: str) -> str:
    """Infer actor name from permission string.

    Example: "finance.expense.create" → "operator"
             "finance.expense.approve" → "manager"
    """
    if not permission:
        return "user"

    # Common permission → actor mappings
    if "approve" in permission:
        return "manager"
    if "create" in permission or "submit" in permission:
        return "operator"
    if "read" in permission:
        return "operator"

    return "user"


def load_ircs_from_file(file_path: str) -> Dict[str, Any]:
    """Load IRCS v1 JSON from file.

    Args:
        file_path: Path to ir.json file

    Returns:
        IRCS v1 dict

    Raises:
        IRCSAdapterError: If file is invalid or not found
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise IRCSAdapterError(
            code=ISE_IDL_PARSE_FAILED,
            message=f"IRCS v1 file not found: {file_path}",
        )
    except json.JSONDecodeError as e:
        raise IRCSAdapterError(
            code=ISE_IDL_INVALID_JSON,
            message=f"Invalid JSON in IRCS v1 file: {e}",
        )


def get_source_idl_sha256(ir: Dict[str, Any]) -> Optional[str]:
    """Extract source_idl_sha256 from IRCS v1.

    This hash should be preserved through the compilation chain
    for audit trail integrity.
    """
    return ir.get("source_idl_sha256")
