"""
AST node classes for IDL DSL v1.2.2.

These nodes represent the parsed structure of an IDL document.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class ActorKind(Enum):
    HUMAN = "human"
    SYSTEM = "system"
    EXTERNAL = "external"


class AuthMethod(Enum):
    NONE = "none"
    BASIC = "basic"
    TOKEN = "token"
    OAUTH2 = "oauth2"
    CERTIFICATE = "certificate"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TenancyMode(Enum):
    SINGLE = "single"
    MULTI = "multi"


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ScopeType(Enum):
    OWN = "own"
    TENANT = "tenant"
    DEPARTMENT = "department"
    ALL = "all"


class IdempotencyMode(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"


class BindKind(Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    TRANSITION = "transition"
    APPROVAL = "approval"
    # Jobs-first bind kinds (dispatched via job_dispatcher.py)
    JOB_REQUEST = "job.request"
    JOB_ENQUEUE = "job.enqueue"
    JOB_GET = "job.get"


# ============================================================
# Base AST Node
# ============================================================


@dataclass
class ASTNode:
    """Base class for all AST nodes."""

    line: int = 0
    column: int = 0


# ============================================================
# Expression AST Nodes (typed AST for IRCS v1)
# ============================================================


@dataclass
class ExprNode(ASTNode):
    """Base class for expression nodes."""

    pass


@dataclass
class AlwaysExpr(ExprNode):
    """Represents 'always' keyword in predicates."""

    pass


@dataclass
class LiteralValue(ExprNode):
    """A literal value (number, string, boolean)."""

    value: Any = field(default=None)
    type_name: str = field(default="")  # "int", "decimal", "string", "bool"


@dataclass
class RefPath(ExprNode):
    """A reference path like 'entity.field' or 'actor.id'."""

    path: str = field(default="")
    type_name: Optional[str] = None  # inferred or explicit


@dataclass
class HistoryRef(ExprNode):
    """history() reference (v1.2.2)."""

    step_name: str = field(default="")  # e.g., "Submit"
    attr: str = field(default="")  # "actors", "count", "last_actor", "last_at"
    type_name: Optional[str] = None  # inferred based on attr


@dataclass
class CompareExpr(ExprNode):
    """Comparison expression: lhs op rhs."""

    op: str = field(default="")  # "==", "!=", ">", ">=", "<", "<=", "in"
    lhs: Optional[ExprNode] = None
    rhs: Optional[ExprNode] = None


@dataclass
class AndExpr(ExprNode):
    """Logical AND of expressions."""

    exprs: list[ExprNode] = field(default_factory=list)


@dataclass
class OrExpr(ExprNode):
    """Logical OR of expressions."""

    exprs: list[ExprNode] = field(default_factory=list)


@dataclass
class NotExpr(ExprNode):
    """Logical NOT of expression."""

    expr: Optional[ExprNode] = None


# ============================================================
# System Section
# ============================================================


@dataclass
class SystemNode(ASTNode):
    """system { ... } section."""

    id: str = ""
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    domain: Optional[str] = None
    owner: Optional[str] = None
    contact: Optional[str] = None
    tenancy: TenancyMode = TenancyMode.SINGLE


# ============================================================
# Actors Section
# ============================================================


@dataclass
class ActorNode(ASTNode):
    """An actor definition."""

    id: str = ""
    kind: ActorKind = ActorKind.HUMAN
    name: Optional[str] = None
    description: Optional[str] = None
    auth: AuthMethod = AuthMethod.NONE
    permissions: list[str] = field(default_factory=list)


# ============================================================
# Entities Section
# ============================================================


@dataclass
class FieldModifier(ASTNode):
    """Field modifier (required, unique, indexed, default, min, max)."""

    kind: str = ""  # "required", "unique", "indexed", "default", "min", "max"
    value: Optional[Any] = None  # for default, min, max


@dataclass
class FieldNode(ASTNode):
    """A field definition in an entity."""

    name: str = ""
    type_name: str = ""
    modifiers: list[FieldModifier] = field(default_factory=list)

    @property
    def required(self) -> bool:
        return any(m.kind == "required" for m in self.modifiers)

    @property
    def unique(self) -> bool:
        return any(m.kind == "unique" for m in self.modifiers)

    @property
    def indexed(self) -> bool:
        return any(m.kind == "indexed" for m in self.modifiers)

    @property
    def default_value(self) -> Optional[Any]:
        for m in self.modifiers:
            if m.kind == "default":
                return m.value
        return None

    @property
    def min_value(self) -> Optional[Any]:
        for m in self.modifiers:
            if m.kind == "min":
                return m.value
        return None

    @property
    def max_value(self) -> Optional[Any]:
        for m in self.modifiers:
            if m.kind == "max":
                return m.value
        return None


@dataclass
class StorageNode(ASTNode):
    """Storage configuration for an entity."""

    tenant_field: Optional[str] = None
    version_field: Optional[str] = None


@dataclass
class EntityNode(ASTNode):
    """An entity definition."""

    name: str = ""
    fields: list[FieldNode] = field(default_factory=list)
    storage: Optional[StorageNode] = None


# ============================================================
# Policy Context Section
# ============================================================


@dataclass
class ContextFieldNode(ASTNode):
    """A field in policy_context."""

    name: str = ""
    type_name: str = ""
    required: bool = False
    default_value: Optional[Any] = None


@dataclass
class PolicyContextNode(ASTNode):
    """policy_context { ... } section."""

    fields: list[ContextFieldNode] = field(default_factory=list)


# ============================================================
# Invariants Section
# ============================================================


@dataclass
class InvariantNode(ASTNode):
    """An invariant definition."""

    name: str = ""
    applies_to: str = ""  # entity name
    when_expr: Optional[ExprNode] = None  # predicate expression
    assert_expr: Optional[ExprNode] = None  # assertion expression
    severity: Severity = Severity.MEDIUM
    message: Optional[str] = None


# ============================================================
# Separation of Duties Section
# ============================================================


@dataclass
class ForbidExpr(ASTNode):
    """forbid: Action when predicate."""

    action: str = ""  # transition name
    when_expr: Optional[ExprNode] = None


@dataclass
class SodRuleNode(ASTNode):
    """A separation of duties rule."""

    name: str = ""
    on_entity: str = ""
    forbid: Optional[ForbidExpr] = None
    severity: Severity = Severity.CRITICAL
    message: Optional[str] = None


# ============================================================
# Workflows Section
# ============================================================


@dataclass
class StateNode(ASTNode):
    """A workflow state."""

    name: str = ""
    initial: bool = False
    terminal: bool = False


@dataclass
class ApprovalsNode(ASTNode):
    """Approval requirements for a transition."""

    quorum: int = 1
    roles: list[str] = field(default_factory=list)
    distinct_actors: bool = True
    expires_in: Optional[str] = None  # duration string like "48h"


@dataclass
class EffectNode(ASTNode):
    """An effect step."""

    name: str = ""  # e.g., "set_state", "bump_version"
    args: list[Any] = field(default_factory=list)


@dataclass
class TransitionNode(ASTNode):
    """A workflow transition."""

    name: str = ""
    from_state: str = ""
    to_state: str = ""
    guard: Optional[ExprNode] = None
    approvals: Optional[ApprovalsNode] = None
    effects: list[EffectNode] = field(default_factory=list)


@dataclass
class WorkflowNode(ASTNode):
    """A workflow definition."""

    name: str = ""
    on_entity: str = ""
    states: list[StateNode] = field(default_factory=list)
    transitions: list[TransitionNode] = field(default_factory=list)


# ============================================================
# Operations Section
# ============================================================


@dataclass
class BindSpec(ASTNode):
    """Binding specification for an endpoint."""

    entity: str = ""
    kind: BindKind = BindKind.READ
    workflow: Optional[str] = None
    transition: Optional[str] = None
    decision: Optional[str] = None
    job_type: Optional[str] = None  # For job.request/enqueue/get bind kinds


@dataclass
class EndpointNode(ASTNode):
    """An API endpoint definition."""

    id: str = ""
    method: HttpMethod = HttpMethod.GET
    path: Optional[str] = None
    path_params: list[str] = field(default_factory=list)  # CHANGE-5: Extracted path parameters
    request_type: Optional[str] = None
    response_type: Optional[str] = None
    permission: Optional[str] = None
    scope: ScopeType = ScopeType.TENANT
    idempotency: IdempotencyMode = IdempotencyMode.NONE
    errors: list[int] = field(default_factory=list)
    bind: Optional[BindSpec] = None


@dataclass
class ApiSection(ASTNode):
    """api { ... } section within operations."""

    endpoints: list[EndpointNode] = field(default_factory=list)


@dataclass
class OperationsNode(ASTNode):
    """operations { ... } section."""

    api: Optional[ApiSection] = None


# ============================================================
# Document Root
# ============================================================


@dataclass
class DocumentNode(ASTNode):
    """Root node of an IDL document."""

    system: Optional[SystemNode] = None
    actors: list[ActorNode] = field(default_factory=list)
    entities: list[EntityNode] = field(default_factory=list)
    policy_context: Optional[PolicyContextNode] = None
    invariants: list[InvariantNode] = field(default_factory=list)
    separation_of_duties: list[SodRuleNode] = field(default_factory=list)
    workflows: list[WorkflowNode] = field(default_factory=list)
    operations: Optional[OperationsNode] = None
