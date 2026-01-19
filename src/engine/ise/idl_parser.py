"""IDL Parser for MVP."""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

import re

from .errors import (
    ISE_IDL_PARSE_FAILED,
    ISE_IDL_INVALID_JSON,
    ISE_IDL_MISSING_FIELD,
    ISE_IDL_INSUFFICIENT,
    ISE_DEPT_ID_INVALID,
    ISE_CONTRACT_ID_INVALID,
    ISE_CONTRACT_PROVIDER_UNKNOWN,
    ISE_CONTRACT_CONSUMER_UNKNOWN,
    ISE_MANDATE_INVALID,
    ISE_MANDATE_ENDPOINT_INVALID,
    ISE_MANDATE_PHASE_INVALID,
    ISE_MANDATE_RULE_TYPE_INVALID,
    ISE_MANDATE_ID_DUPLICATE,
    ISE_AUTONOMY_INVALID,
    ISE_AUTONOMY_LEVEL_INVALID,
    ISE_AUTONOMY_ENDPOINT_INVALID,
    ISE_AUTONOMY_PHASE_INVALID,
    ISE_AUTONOMY_RULE_ID_DUPLICATE,
)

# Import runtime constants for validation
from engine.core.mandates import (
    ALLOWED_ENDPOINT_SIGS as MANDATE_ALLOWED_ENDPOINT_SIGS,
    ALLOWED_PHASES as MANDATE_ALLOWED_PHASES,
    ALLOWED_RULE_TYPES as MANDATE_ALLOWED_RULE_TYPES,
)
from engine.core.autonomy import (
    ALLOWED_ENDPOINT_SIGS as AUTONOMY_ALLOWED_ENDPOINT_SIGS,
    ALLOWED_PHASES as AUTONOMY_ALLOWED_PHASES,
    MIN_LEVEL as AUTONOMY_MIN_LEVEL,
    MAX_LEVEL as AUTONOMY_MAX_LEVEL,
)


# Approval keywords (PT/EN)
APPROVAL_KEYWORDS_EN = [
    "must be approved", "requires approval", "needs approval",
    "approval required", "approved by", "must approve",
]
APPROVAL_KEYWORDS_PT = [
    "deve ser aprovado", "requer aprovacao", "requer aprovação",
    "precisa de aprovacao", "precisa de aprovação", "aprovado por",
    "devem aprovar", "deve aprovar",
]

# SoD keywords (PT/EN)
SOD_KEYWORDS_EN = [
    "cannot approve their own", "cannot approve your own",
    "self-approval", "segregation", "different person",
    "another person", "their own",
]
SOD_KEYWORDS_PT = [
    "nao pode aprovar sua propria", "não pode aprovar sua própria",
    "auto-aprovacao", "auto-aprovação", "segregacao", "segregação",
    "pessoa diferente", "outra pessoa", "suas proprias", "suas próprias",
    "não podem aprovar",
]


@dataclass
class IDLField:
    """Entity field definition."""
    name: str
    field_type: str
    required: bool = True
    modifiers: List[str] = field(default_factory=list)


@dataclass
class IDLEntity:
    """Entity definition."""
    name: str
    entity_type: str
    fields: List[IDLField] = field(default_factory=list)


@dataclass
class IDLPermission:
    """Actor permission."""
    resource: str
    actions: List[str] = field(default_factory=list)


@dataclass
class IDLActor:
    """Actor definition."""
    name: str
    role: str
    permissions: List[IDLPermission] = field(default_factory=list)
    auth_method: str = "header"


@dataclass
class IDLUseCase:
    """Use case definition."""
    name: str
    actor: str
    main_flow: str
    has_approval: bool = False
    has_sod: bool = False
    approval_role: Optional[str] = None


@dataclass
class IDLDepartment:
    """Department definition for multi-department bundles."""
    dept_id: str
    name: Optional[str] = None
    # Per-dept configuration - can override system-level or be dept-specific
    rbac: Optional[Dict[str, Any]] = None
    workflows: Optional[List[Dict[str, Any]]] = None
    approvals: Optional[Dict[str, Any]] = None
    sod: Optional[Dict[str, Any]] = None
    invariants: Optional[Dict[str, Any]] = None
    entities: Optional[List[Dict[str, Any]]] = None


@dataclass
class IDLContract:
    """Interdepartmental contract definition."""
    contract_id: str
    provider_dept: str
    consumers: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False


@dataclass
class IDLPolicy:
    """Policy rule definition for policies.json v1.1.

    Maps to runtime PolicyRule structure with exact endpoint_sig matching.
    """
    policy_id: str
    phase: str  # "pre" or "post"
    endpoint_sig: str  # exact endpoint signature
    rule_type: str  # numeric_max, numeric_min, string_max_len, required_field, enum_allowlist
    field_path: str  # dot notation e.g. "amount" or "payload.amount"
    value: Any = None  # threshold value for comparison rules
    message: Optional[str] = None  # custom error message


@dataclass
class IDLMandateLimit:
    """A limit rule within a mandate (IDL v1.1)."""
    rule_type: str  # numeric_max, numeric_min, string_max_len, required_field, enum_allowlist
    field_path: str  # dot notation e.g. "amount" or "payload.amount"
    value: Any = None  # threshold value
    message: Optional[str] = None  # custom error message


@dataclass
class IDLMandate:
    """Mandate definition for IDL v1.1.

    Maps to runtime Mandate structure.
    """
    mandate_id: str
    endpoint_sig: str  # exact endpoint signature
    phase: str  # "pre" or "post"
    allowed_roles: List[str] = field(default_factory=list)
    limits: List[IDLMandateLimit] = field(default_factory=list)
    message: Optional[str] = None  # custom message


@dataclass
class IDLAutonomyRule:
    """Autonomy rule definition for IDL v1.1."""
    rule_id: str
    endpoint_sig: str  # exact endpoint signature
    phase: str  # "pre" or "post"
    required_level: int  # 0..4


@dataclass
class IDLAutonomy:
    """Autonomy definition for IDL v1.1."""
    current_level: int  # 0..4
    rules: List[IDLAutonomyRule] = field(default_factory=list)


@dataclass
class ParsedIDL:
    """Parsed IDL structure."""
    system_name: str
    version: str
    idl_version: str = "1.0"  # IDL format version (1.0 = legacy, 1.1 = mandates/autonomy first-class)
    actors: List[IDLActor] = field(default_factory=list)
    entities: List[IDLEntity] = field(default_factory=list)
    usecases: List[IDLUseCase] = field(default_factory=list)
    departments: List[IDLDepartment] = field(default_factory=list)
    contracts: List[IDLContract] = field(default_factory=list)
    policies: List[IDLPolicy] = field(default_factory=list)  # single mode policies
    dept_policies: Dict[str, List[IDLPolicy]] = field(default_factory=dict)  # multi mode policies
    # IDL v1.1: mandates/autonomy first-class
    mandates: List[IDLMandate] = field(default_factory=list)  # single mode mandates
    autonomy: Optional[IDLAutonomy] = None  # single mode autonomy
    dept_mandates: Dict[str, List[IDLMandate]] = field(default_factory=dict)  # multi mode mandates
    dept_autonomy: Dict[str, IDLAutonomy] = field(default_factory=dict)  # multi mode autonomy

    @property
    def is_multi_dept(self) -> bool:
        """Check if this is a multi-department bundle."""
        return len(self.departments) > 0

    def validate_for_finance_pilot(self) -> tuple:
        """Validate IDL has required elements for finance-pilot MVP.

        Returns:
            Tuple of (is_valid, missing_items_list).
        """
        missing = []

        # Must have expense entity
        has_expense = any(e.entity_type == "expense" for e in self.entities)
        if not has_expense:
            missing.append("expense entity")

        return (len(missing) == 0, missing)


class IDLParseError(Exception):
    """IDL parsing error."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def parse_idl(idl_input: Any) -> ParsedIDL:
    """Parse IDL input (JSON string or dict) into structured form.

    Args:
        idl_input: IDL as JSON string or dict.

    Returns:
        ParsedIDL structure.

    Raises:
        IDLParseError: On parse failures.
    """
    # Parse JSON if string
    if isinstance(idl_input, str):
        try:
            idl_data = json.loads(idl_input)
        except json.JSONDecodeError as e:
            raise IDLParseError(
                code=ISE_IDL_INVALID_JSON,
                message=f"Invalid JSON: {e}",
            )
    elif isinstance(idl_input, dict):
        idl_data = idl_input
    else:
        raise IDLParseError(
            code=ISE_IDL_PARSE_FAILED,
            message=f"IDL must be JSON string or dict, got {type(idl_input).__name__}",
        )

    # Extract system info
    system_name = idl_data.get("system") or idl_data.get("name") or idl_data.get("system_name") or "Unknown"
    version = idl_data.get("version") or "0.0.0"
    idl_version = idl_data.get("idl_version") or "1.0"  # Default to legacy

    # Parse departments (multi-dept mode)
    departments = _parse_departments(idl_data)

    # Parse actors from RBAC section
    actors = _parse_actors(idl_data)

    # Parse entities
    entities = _parse_entities(idl_data)

    # Parse usecases (from workflows or usecases section)
    usecases = _parse_usecases(idl_data)

    # Parse interdepartmental contracts
    contracts = _parse_contracts(idl_data, departments)

    # Parse policies (single mode)
    policies = _parse_policies(idl_data.get("policies", []))

    # Parse dept_policies (multi mode)
    dept_policies = _parse_dept_policies(idl_data.get("dept_policies", {}), departments)

    # IDL v1.1: Parse mandates/autonomy
    mandates: List[IDLMandate] = []
    autonomy: Optional[IDLAutonomy] = None
    dept_mandates: Dict[str, List[IDLMandate]] = {}
    dept_autonomy: Dict[str, IDLAutonomy] = {}

    if idl_version == "1.1":
        # Parse single-mode mandates
        mandates = _parse_mandates(idl_data.get("mandates", []))

        # Parse single-mode autonomy
        autonomy_data = idl_data.get("autonomy")
        if autonomy_data:
            autonomy = _parse_autonomy(autonomy_data)

        # Parse multi-dept mandates
        dept_mandates = _parse_dept_mandates(
            idl_data.get("dept_mandates", {}), departments
        )

        # Parse multi-dept autonomy
        dept_autonomy = _parse_dept_autonomy(
            idl_data.get("dept_autonomy", {}), departments
        )

    return ParsedIDL(
        system_name=system_name,
        version=version,
        idl_version=idl_version,
        actors=actors,
        entities=entities,
        usecases=usecases,
        departments=departments,
        contracts=contracts,
        policies=policies,
        dept_policies=dept_policies,
        mandates=mandates,
        autonomy=autonomy,
        dept_mandates=dept_mandates,
        dept_autonomy=dept_autonomy,
    )


def _parse_actors(idl_data: Dict[str, Any]) -> List[IDLActor]:
    """Parse actors from IDL."""
    actors = []

    # From rbac section
    rbac = idl_data.get("rbac", {})
    roles = rbac.get("roles", [])

    for role_data in roles:
        if not isinstance(role_data, dict):
            continue

        name = role_data.get("name", "")
        if not name:
            continue

        # Parse permissions
        permissions = []
        for perm in role_data.get("permissions", []):
            if isinstance(perm, str) and "." in perm:
                resource, action = perm.rsplit(".", 1)
                # Find or create permission for resource
                found = False
                for p in permissions:
                    if p.resource == resource:
                        p.actions.append(action)
                        found = True
                        break
                if not found:
                    permissions.append(IDLPermission(resource=resource, actions=[action]))

        actors.append(IDLActor(
            name=name.title(),
            role=name.lower(),
            permissions=permissions,
        ))

    # From actors section if present
    actors_section = idl_data.get("actors", [])
    for actor_data in actors_section:
        if not isinstance(actor_data, dict):
            continue

        name = actor_data.get("name", "")
        role = actor_data.get("role", name.lower() if name else "")

        if not role:
            continue

        # Check if already exists
        if any(a.role == role for a in actors):
            continue

        # Parse permissions if present
        permissions = []
        for perm_data in actor_data.get("permissions", []):
            if isinstance(perm_data, dict):
                resource = perm_data.get("resource", "")
                actions = perm_data.get("actions", [])
                if resource:
                    permissions.append(IDLPermission(resource=resource, actions=actions))

        actors.append(IDLActor(
            name=name.title() if name else role.title(),
            role=role.lower(),
            permissions=permissions,
            auth_method=actor_data.get("auth_method", "header"),
        ))

    return sorted(actors, key=lambda a: a.role)


def _parse_entities(idl_data: Dict[str, Any]) -> List[IDLEntity]:
    """Parse entities from IDL."""
    entities = []

    # From entities section
    entities_section = idl_data.get("entities", [])
    for entity_data in entities_section:
        if not isinstance(entity_data, dict):
            continue

        name = entity_data.get("name", "")
        entity_type = entity_data.get("entity_type") or entity_data.get("type", name.lower())

        # Parse fields
        fields = []
        for field_data in entity_data.get("fields", []):
            if isinstance(field_data, dict):
                fields.append(IDLField(
                    name=field_data.get("name", ""),
                    field_type=field_data.get("type", "string"),
                    required=field_data.get("required", True),
                    modifiers=field_data.get("modifiers", []),
                ))

        entities.append(IDLEntity(
            name=name.title() if name else entity_type.title(),
            entity_type=entity_type.lower(),
            fields=fields,
        ))

    # From invariants section - extract entity names
    invariants = idl_data.get("invariants", {})
    for key in invariants:
        if key in ("version", "name"):
            continue

        entity_type = key.lower()
        if not any(e.entity_type == entity_type for e in entities):
            # Create entity from invariants
            schema = invariants[key]
            fields = []
            if isinstance(schema, dict):
                for field_name, constraints in schema.items():
                    if isinstance(constraints, dict):
                        fields.append(IDLField(
                            name=field_name,
                            field_type="number" if "min" in constraints or "max" in constraints else "string",
                            required=constraints.get("required", True),
                        ))

            entities.append(IDLEntity(
                name=entity_type.title(),
                entity_type=entity_type,
                fields=fields,
            ))

    return sorted(entities, key=lambda e: e.entity_type)


def _parse_usecases(idl_data: Dict[str, Any]) -> List[IDLUseCase]:
    """Parse usecases from IDL."""
    usecases = []

    # From usecases section
    usecases_section = idl_data.get("usecases", [])
    for uc_data in usecases_section:
        if not isinstance(uc_data, dict):
            continue

        name = uc_data.get("name", "")
        actor = uc_data.get("actor", "")
        main_flow = uc_data.get("main_flow", "")
        description = uc_data.get("description", "")
        explicit_approval_role = uc_data.get("approval_role")

        # Combine text for keyword detection
        combined_text = f"{main_flow} {description}"

        # Detect approval/sod from combined text
        has_approval, approval_role = _detect_approval(combined_text, idl_data)
        has_sod = _detect_sod(combined_text)

        # Use explicit approval_role if provided
        if explicit_approval_role:
            has_approval = True
            approval_role = explicit_approval_role

        usecases.append(IDLUseCase(
            name=name,
            actor=actor,
            main_flow=main_flow,
            has_approval=has_approval,
            has_sod=has_sod,
            approval_role=approval_role,
        ))

    # From workflows section
    workflows = idl_data.get("workflows", [])
    for wf_data in workflows:
        if not isinstance(wf_data, dict):
            continue

        name = wf_data.get("name") or wf_data.get("workflow_key", "")
        steps = wf_data.get("steps", [])

        # Extract actor and flow from steps
        actors_in_wf = set()
        flow_parts = []
        has_approval = False
        has_sod = False
        approval_role = None

        for step in steps:
            if isinstance(step, dict):
                action = step.get("action", "")
                actor_ref = step.get("actor_ref", "")
                if actor_ref:
                    actors_in_wf.add(actor_ref.replace("actor-", ""))
                flow_parts.append(action)

                if action.lower() == "approve":
                    has_approval = True
                    if actor_ref:
                        approval_role = actor_ref.replace("actor-", "")

        main_flow = " -> ".join(flow_parts)

        # Also check approvals section
        if not has_approval:
            approvals = idl_data.get("approvals", {})
            if approvals.get("rules"):
                has_approval = True
                for rule in approvals["rules"]:
                    roles = rule.get("approver_roles", [])
                    if roles:
                        approval_role = roles[0]
                        break

        # Check sod section
        if not has_sod:
            sod = idl_data.get("sod", {})
            if sod.get("rules"):
                has_sod = True

        usecases.append(IDLUseCase(
            name=name,
            actor=list(actors_in_wf)[0] if actors_in_wf else "",
            main_flow=main_flow,
            has_approval=has_approval,
            has_sod=has_sod,
            approval_role=approval_role,
        ))

    # Infer from approvals/sod sections if no usecases
    if not usecases:
        approvals = idl_data.get("approvals", {})
        sod = idl_data.get("sod", {})

        has_approval = bool(approvals.get("rules"))
        has_sod = bool(sod.get("rules"))

        approval_role = None
        if has_approval:
            for rule in approvals.get("rules", []):
                roles = rule.get("approver_roles", [])
                if roles:
                    approval_role = roles[0]
                    break

        if has_approval or has_sod:
            usecases.append(IDLUseCase(
                name="default_workflow",
                actor="user",
                main_flow="create -> approve" if has_approval else "create",
                has_approval=has_approval,
                has_sod=has_sod,
                approval_role=approval_role,
            ))

    return sorted(usecases, key=lambda u: u.name)


def _detect_approval(text: str, idl_data: Dict[str, Any]) -> tuple:
    """Detect approval requirement from text.

    Returns:
        Tuple of (has_approval, approval_role).
    """
    text_lower = text.lower()

    # Check keywords
    for kw in APPROVAL_KEYWORDS_EN + APPROVAL_KEYWORDS_PT:
        if kw in text_lower:
            # Try to extract role
            role = _extract_approval_role(text, idl_data)
            return True, role

    return False, None


def _extract_approval_role(text: str, idl_data: Dict[str, Any]) -> Optional[str]:
    """Extract approval role from text or IDL."""
    text_lower = text.lower()

    # Common approval roles
    approval_roles = ["manager", "admin", "supervisor", "director", "approver"]

    for role in approval_roles:
        if role in text_lower:
            return role

    # Check RBAC for roles with approve permission
    rbac = idl_data.get("rbac", {})
    for role_data in rbac.get("roles", []):
        perms = role_data.get("permissions", [])
        if any("approve" in p for p in perms):
            return role_data.get("name")

    return "manager"  # Default


def _detect_sod(text: str) -> bool:
    """Detect SoD requirement from text."""
    text_lower = text.lower()

    for kw in SOD_KEYWORDS_EN + SOD_KEYWORDS_PT:
        if kw in text_lower:
            return True

    return False


def validate_for_finance_pilot(parsed: ParsedIDL) -> None:
    """Validate IDL has required elements for finance-pilot MVP.

    Args:
        parsed: Parsed IDL.

    Raises:
        IDLParseError: If validation fails.
    """
    # Must have expense entity for finance-pilot
    has_expense = any(e.entity_type == "expense" for e in parsed.entities)

    if not has_expense:
        raise IDLParseError(
            code=ISE_IDL_INSUFFICIENT,
            message="Finance pilot requires 'expense' entity",
            details={"missing": "expense entity"},
        )

    # If usecases indicate approval, must have approver role
    for uc in parsed.usecases:
        if uc.has_approval and not uc.approval_role:
            # Check if any actor has approve permission
            has_approver = any(
                any("approve" in p.actions for p in a.permissions)
                for a in parsed.actors
            )
            if not has_approver:
                raise IDLParseError(
                    code=ISE_IDL_INSUFFICIENT,
                    message="Approval required but no approver role defined",
                    details={"usecase": uc.name},
                )


# Regex for validating department IDs
DEPT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_dept_id(dept_id: str) -> None:
    """Validate department ID format.

    Args:
        dept_id: Department identifier to validate.

    Raises:
        IDLParseError: If dept_id is invalid.
    """
    if not dept_id or not DEPT_ID_PATTERN.match(dept_id):
        raise IDLParseError(
            code=ISE_DEPT_ID_INVALID,
            message=f"Invalid department ID: '{dept_id}'. Must match [a-zA-Z0-9_-]+",
            details={"dept_id": dept_id},
        )


def _validate_contract_id(contract_id: str) -> None:
    """Validate contract ID format.

    Args:
        contract_id: Contract identifier to validate.

    Raises:
        IDLParseError: If contract_id is invalid.
    """
    if not contract_id or not DEPT_ID_PATTERN.match(contract_id):
        raise IDLParseError(
            code=ISE_CONTRACT_ID_INVALID,
            message=f"Invalid contract ID: '{contract_id}'. Must match [a-zA-Z0-9_-]+",
            details={"contract_id": contract_id},
        )


def _parse_departments(idl_data: Dict[str, Any]) -> List[IDLDepartment]:
    """Parse departments from IDL for multi-department bundles.

    Args:
        idl_data: Parsed IDL data.

    Returns:
        List of parsed departments.

    Raises:
        IDLParseError: If department validation fails.
    """
    departments = []
    departments_section = idl_data.get("departments", [])

    if not departments_section:
        return departments

    for dept_data in departments_section:
        if not isinstance(dept_data, dict):
            continue

        dept_id = dept_data.get("dept_id", "")
        _validate_dept_id(dept_id)

        departments.append(IDLDepartment(
            dept_id=dept_id,
            name=dept_data.get("name"),
            rbac=dept_data.get("rbac"),
            workflows=dept_data.get("workflows"),
            approvals=dept_data.get("approvals"),
            sod=dept_data.get("sod"),
            invariants=dept_data.get("invariants"),
            entities=dept_data.get("entities"),
        ))

    return sorted(departments, key=lambda d: d.dept_id)


def _parse_contracts(
    idl_data: Dict[str, Any],
    departments: List[IDLDepartment],
) -> List[IDLContract]:
    """Parse interdepartmental contracts from IDL.

    Args:
        idl_data: Parsed IDL data.
        departments: List of parsed departments for validation.

    Returns:
        List of parsed contracts.

    Raises:
        IDLParseError: If contract validation fails.
    """
    contracts = []
    contracts_section = idl_data.get("contracts", [])

    if not contracts_section:
        return contracts

    # Build set of valid dept_ids for validation
    valid_depts = {d.dept_id for d in departments}

    for contract_data in contracts_section:
        if not isinstance(contract_data, dict):
            continue

        contract_id = contract_data.get("contract_id", "")
        _validate_contract_id(contract_id)

        provider_dept = contract_data.get("provider_dept", "")
        if provider_dept not in valid_depts:
            raise IDLParseError(
                code=ISE_CONTRACT_PROVIDER_UNKNOWN,
                message=f"Contract '{contract_id}' has unknown provider: '{provider_dept}'",
                details={"contract_id": contract_id, "provider_dept": provider_dept},
            )

        consumers = contract_data.get("consumers", [])
        for consumer in consumers:
            if consumer not in valid_depts:
                raise IDLParseError(
                    code=ISE_CONTRACT_CONSUMER_UNKNOWN,
                    message=f"Contract '{contract_id}' has unknown consumer: '{consumer}'",
                    details={"contract_id": contract_id, "consumer": consumer},
                )

        contracts.append(IDLContract(
            contract_id=contract_id,
            provider_dept=provider_dept,
            consumers=consumers,
            input_schema=contract_data.get("input_schema", {}),
            output_schema=contract_data.get("output_schema", {}),
            approval_required=contract_data.get("approval_required", False),
        ))

    return sorted(contracts, key=lambda c: c.contract_id)


def _parse_policies(policies_data: List[Dict[str, Any]]) -> List[IDLPolicy]:
    """Parse policies from IDL (single mode).

    Args:
        policies_data: List of policy dicts from IDL.

    Returns:
        List of parsed IDLPolicy objects.
    """
    policies = []

    for policy_data in policies_data:
        if not isinstance(policy_data, dict):
            continue

        policies.append(IDLPolicy(
            policy_id=policy_data.get("policy_id", ""),
            phase=policy_data.get("phase", "pre"),
            endpoint_sig=policy_data.get("endpoint_sig", ""),
            rule_type=policy_data.get("rule_type", ""),
            field_path=policy_data.get("field_path", ""),
            value=policy_data.get("value"),
            message=policy_data.get("message"),
        ))

    return sorted(policies, key=lambda p: p.policy_id)


def _parse_dept_policies(
    dept_policies_data: Dict[str, List[Dict[str, Any]]],
    departments: List[IDLDepartment],
) -> Dict[str, List[IDLPolicy]]:
    """Parse dept_policies from IDL (multi mode).

    Args:
        dept_policies_data: Dict mapping dept_id to list of policy dicts.
        departments: List of parsed departments for validation.

    Returns:
        Dict mapping dept_id to list of IDLPolicy objects.

    Raises:
        IDLParseError: If dept_id in dept_policies is invalid.
    """
    # Build set of valid dept_ids for validation
    valid_depts = {d.dept_id for d in departments}

    result: Dict[str, List[IDLPolicy]] = {}

    for dept_id, policies_data in dept_policies_data.items():
        # Validate dept_id format
        _validate_dept_id(dept_id)

        # Validate dept_id exists in departments (only if departments are defined)
        if valid_depts and dept_id not in valid_depts:
            raise IDLParseError(
                code=ISE_DEPT_ID_INVALID,
                message=f"dept_policies contains unknown department: '{dept_id}'",
                details={"dept_id": dept_id, "valid_depts": list(valid_depts)},
            )

        # Parse policies for this department
        policies = _parse_policies(policies_data)
        if policies:
            result[dept_id] = policies

    return result


# =============================================================================
# IDL v1.1: Mandates Parsing
# =============================================================================


def _parse_mandate_limit(limit_data: Dict[str, Any], mandate_id: str) -> IDLMandateLimit:
    """Parse a single mandate limit from IDL.

    Args:
        limit_data: Limit definition dict.
        mandate_id: Parent mandate ID for error context.

    Returns:
        IDLMandateLimit object.

    Raises:
        IDLParseError: If limit validation fails.
    """
    rule_type = limit_data.get("rule_type", "")

    if not rule_type:
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message=f"Mandate '{mandate_id}': limit missing rule_type",
            details={"mandate_id": mandate_id},
        )

    if rule_type not in MANDATE_ALLOWED_RULE_TYPES:
        raise IDLParseError(
            code=ISE_MANDATE_RULE_TYPE_INVALID,
            message=f"Mandate '{mandate_id}': invalid rule_type '{rule_type}'. "
            f"Allowed: {sorted(MANDATE_ALLOWED_RULE_TYPES)}",
            details={"mandate_id": mandate_id, "rule_type": rule_type},
        )

    field_path = limit_data.get("field_path", "")
    if not field_path:
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message=f"Mandate '{mandate_id}': limit missing field_path",
            details={"mandate_id": mandate_id},
        )

    return IDLMandateLimit(
        rule_type=rule_type,
        field_path=field_path,
        value=limit_data.get("value"),
        message=limit_data.get("message"),
    )


def _parse_single_mandate(mandate_data: Dict[str, Any], seen_ids: set) -> IDLMandate:
    """Parse a single mandate from IDL.

    Args:
        mandate_data: Mandate definition dict.
        seen_ids: Set of already-seen mandate_ids for duplicate detection.

    Returns:
        IDLMandate object.

    Raises:
        IDLParseError: If mandate validation fails.
    """
    mandate_id = mandate_data.get("mandate_id", "")

    # Validate mandate_id
    if not mandate_id or not mandate_id.strip():
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message="Mandate missing mandate_id",
            details={"mandate_data": mandate_data},
        )

    if mandate_id in seen_ids:
        raise IDLParseError(
            code=ISE_MANDATE_ID_DUPLICATE,
            message=f"Duplicate mandate_id: '{mandate_id}'",
            details={"mandate_id": mandate_id},
        )
    seen_ids.add(mandate_id)

    # Validate endpoint_sig
    endpoint_sig = mandate_data.get("endpoint_sig", "")
    if not endpoint_sig:
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message=f"Mandate '{mandate_id}': missing endpoint_sig",
            details={"mandate_id": mandate_id},
        )

    if endpoint_sig not in MANDATE_ALLOWED_ENDPOINT_SIGS:
        raise IDLParseError(
            code=ISE_MANDATE_ENDPOINT_INVALID,
            message=f"Mandate '{mandate_id}': invalid endpoint_sig '{endpoint_sig}'. "
            f"Allowed: {sorted(MANDATE_ALLOWED_ENDPOINT_SIGS)}",
            details={"mandate_id": mandate_id, "endpoint_sig": endpoint_sig},
        )

    # Validate phase
    phase = mandate_data.get("phase", "")
    if not phase:
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message=f"Mandate '{mandate_id}': missing phase",
            details={"mandate_id": mandate_id},
        )

    if phase not in MANDATE_ALLOWED_PHASES:
        raise IDLParseError(
            code=ISE_MANDATE_PHASE_INVALID,
            message=f"Mandate '{mandate_id}': invalid phase '{phase}'. "
            f"Allowed: {sorted(MANDATE_ALLOWED_PHASES)}",
            details={"mandate_id": mandate_id, "phase": phase},
        )

    # Parse allowed_roles
    allowed_roles = mandate_data.get("allowed_roles", [])
    if not isinstance(allowed_roles, list):
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message=f"Mandate '{mandate_id}': allowed_roles must be a list",
            details={"mandate_id": mandate_id},
        )

    # Parse limits (optional)
    limits: List[IDLMandateLimit] = []
    limits_data = mandate_data.get("limits", [])
    if not isinstance(limits_data, list):
        raise IDLParseError(
            code=ISE_MANDATE_INVALID,
            message=f"Mandate '{mandate_id}': limits must be a list",
            details={"mandate_id": mandate_id},
        )

    for limit_data in limits_data:
        if isinstance(limit_data, dict):
            limits.append(_parse_mandate_limit(limit_data, mandate_id))

    return IDLMandate(
        mandate_id=mandate_id,
        endpoint_sig=endpoint_sig,
        phase=phase,
        allowed_roles=allowed_roles,
        limits=limits,
        message=mandate_data.get("message"),
    )


def _parse_mandates(mandates_data: List[Dict[str, Any]]) -> List[IDLMandate]:
    """Parse mandates list from IDL (single mode).

    Args:
        mandates_data: List of mandate dicts from IDL.

    Returns:
        List of IDLMandate objects.

    Raises:
        IDLParseError: If any mandate validation fails.
    """
    if not isinstance(mandates_data, list):
        return []

    mandates: List[IDLMandate] = []
    seen_ids: set = set()

    for mandate_data in mandates_data:
        if not isinstance(mandate_data, dict):
            continue
        mandates.append(_parse_single_mandate(mandate_data, seen_ids))

    return sorted(mandates, key=lambda m: m.mandate_id)


def _parse_dept_mandates(
    dept_mandates_data: Dict[str, List[Dict[str, Any]]],
    departments: List[IDLDepartment],
) -> Dict[str, List[IDLMandate]]:
    """Parse dept_mandates from IDL (multi mode).

    Args:
        dept_mandates_data: Dict mapping dept_id to list of mandate dicts.
        departments: List of parsed departments for validation.

    Returns:
        Dict mapping dept_id to list of IDLMandate objects.

    Raises:
        IDLParseError: If validation fails.
    """
    valid_depts = {d.dept_id for d in departments}
    result: Dict[str, List[IDLMandate]] = {}

    for dept_id, mandates_data in dept_mandates_data.items():
        # Validate dept_id format
        _validate_dept_id(dept_id)

        # Validate dept_id exists in departments (only if departments are defined)
        if valid_depts and dept_id not in valid_depts:
            raise IDLParseError(
                code=ISE_DEPT_ID_INVALID,
                message=f"dept_mandates contains unknown department: '{dept_id}'",
                details={"dept_id": dept_id, "valid_depts": list(valid_depts)},
            )

        # Parse mandates for this department (with dept-scoped duplicate checking)
        if not isinstance(mandates_data, list):
            continue

        mandates: List[IDLMandate] = []
        seen_ids: set = set()

        for mandate_data in mandates_data:
            if isinstance(mandate_data, dict):
                mandates.append(_parse_single_mandate(mandate_data, seen_ids))

        if mandates:
            result[dept_id] = sorted(mandates, key=lambda m: m.mandate_id)

    return result


# =============================================================================
# IDL v1.1: Autonomy Parsing
# =============================================================================


def _parse_autonomy_rule(rule_data: Dict[str, Any], seen_ids: set) -> IDLAutonomyRule:
    """Parse a single autonomy rule from IDL.

    Args:
        rule_data: Rule definition dict.
        seen_ids: Set of already-seen rule_ids for duplicate detection.

    Returns:
        IDLAutonomyRule object.

    Raises:
        IDLParseError: If rule validation fails.
    """
    rule_id = rule_data.get("rule_id", "")

    # Validate rule_id
    if not rule_id or not rule_id.strip():
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message="Autonomy rule missing rule_id",
            details={"rule_data": rule_data},
        )

    if rule_id in seen_ids:
        raise IDLParseError(
            code=ISE_AUTONOMY_RULE_ID_DUPLICATE,
            message=f"Duplicate autonomy rule_id: '{rule_id}'",
            details={"rule_id": rule_id},
        )
    seen_ids.add(rule_id)

    # Validate endpoint_sig
    endpoint_sig = rule_data.get("endpoint_sig", "")
    if not endpoint_sig:
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message=f"Autonomy rule '{rule_id}': missing endpoint_sig",
            details={"rule_id": rule_id},
        )

    if endpoint_sig not in AUTONOMY_ALLOWED_ENDPOINT_SIGS:
        raise IDLParseError(
            code=ISE_AUTONOMY_ENDPOINT_INVALID,
            message=f"Autonomy rule '{rule_id}': invalid endpoint_sig '{endpoint_sig}'. "
            f"Allowed: {sorted(AUTONOMY_ALLOWED_ENDPOINT_SIGS)}",
            details={"rule_id": rule_id, "endpoint_sig": endpoint_sig},
        )

    # Validate phase
    phase = rule_data.get("phase", "")
    if not phase:
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message=f"Autonomy rule '{rule_id}': missing phase",
            details={"rule_id": rule_id},
        )

    if phase not in AUTONOMY_ALLOWED_PHASES:
        raise IDLParseError(
            code=ISE_AUTONOMY_PHASE_INVALID,
            message=f"Autonomy rule '{rule_id}': invalid phase '{phase}'. "
            f"Allowed: {sorted(AUTONOMY_ALLOWED_PHASES)}",
            details={"rule_id": rule_id, "phase": phase},
        )

    # Validate required_level
    required_level = rule_data.get("required_level")
    if required_level is None:
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message=f"Autonomy rule '{rule_id}': missing required_level",
            details={"rule_id": rule_id},
        )

    if not isinstance(required_level, int):
        raise IDLParseError(
            code=ISE_AUTONOMY_LEVEL_INVALID,
            message=f"Autonomy rule '{rule_id}': required_level must be an integer",
            details={"rule_id": rule_id, "required_level": required_level},
        )

    if required_level < AUTONOMY_MIN_LEVEL or required_level > AUTONOMY_MAX_LEVEL:
        raise IDLParseError(
            code=ISE_AUTONOMY_LEVEL_INVALID,
            message=f"Autonomy rule '{rule_id}': required_level {required_level} "
            f"out of range [{AUTONOMY_MIN_LEVEL}..{AUTONOMY_MAX_LEVEL}]",
            details={"rule_id": rule_id, "required_level": required_level},
        )

    return IDLAutonomyRule(
        rule_id=rule_id,
        endpoint_sig=endpoint_sig,
        phase=phase,
        required_level=required_level,
    )


def _parse_autonomy(autonomy_data: Dict[str, Any]) -> IDLAutonomy:
    """Parse autonomy section from IDL (single mode).

    Args:
        autonomy_data: Autonomy definition dict.

    Returns:
        IDLAutonomy object.

    Raises:
        IDLParseError: If autonomy validation fails.
    """
    if not isinstance(autonomy_data, dict):
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message="Autonomy section must be a dict",
            details={"type": type(autonomy_data).__name__},
        )

    # Validate current_level
    current_level = autonomy_data.get("current_level")
    if current_level is None:
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message="Autonomy missing current_level",
            details={},
        )

    if not isinstance(current_level, int):
        raise IDLParseError(
            code=ISE_AUTONOMY_LEVEL_INVALID,
            message="Autonomy current_level must be an integer",
            details={"current_level": current_level},
        )

    if current_level < AUTONOMY_MIN_LEVEL or current_level > AUTONOMY_MAX_LEVEL:
        raise IDLParseError(
            code=ISE_AUTONOMY_LEVEL_INVALID,
            message=f"Autonomy current_level {current_level} "
            f"out of range [{AUTONOMY_MIN_LEVEL}..{AUTONOMY_MAX_LEVEL}]",
            details={"current_level": current_level},
        )

    # Parse rules
    rules: List[IDLAutonomyRule] = []
    rules_data = autonomy_data.get("rules", [])

    if not isinstance(rules_data, list):
        raise IDLParseError(
            code=ISE_AUTONOMY_INVALID,
            message="Autonomy rules must be a list",
            details={"type": type(rules_data).__name__},
        )

    seen_ids: set = set()
    for rule_data in rules_data:
        if isinstance(rule_data, dict):
            rules.append(_parse_autonomy_rule(rule_data, seen_ids))

    return IDLAutonomy(
        current_level=current_level,
        rules=sorted(rules, key=lambda r: r.rule_id),
    )


def _parse_dept_autonomy(
    dept_autonomy_data: Dict[str, Dict[str, Any]],
    departments: List[IDLDepartment],
) -> Dict[str, IDLAutonomy]:
    """Parse dept_autonomy from IDL (multi mode).

    Args:
        dept_autonomy_data: Dict mapping dept_id to autonomy dict.
        departments: List of parsed departments for validation.

    Returns:
        Dict mapping dept_id to IDLAutonomy objects.

    Raises:
        IDLParseError: If validation fails.
    """
    valid_depts = {d.dept_id for d in departments}
    result: Dict[str, IDLAutonomy] = {}

    for dept_id, autonomy_data in dept_autonomy_data.items():
        # Validate dept_id format
        _validate_dept_id(dept_id)

        # Validate dept_id exists in departments (only if departments are defined)
        if valid_depts and dept_id not in valid_depts:
            raise IDLParseError(
                code=ISE_DEPT_ID_INVALID,
                message=f"dept_autonomy contains unknown department: '{dept_id}'",
                details={"dept_id": dept_id, "valid_depts": list(valid_depts)},
            )

        # Parse autonomy for this department
        if isinstance(autonomy_data, dict):
            result[dept_id] = _parse_autonomy(autonomy_data)

    return result
