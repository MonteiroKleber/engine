"""
IRCS v1 Emitter - Converts AST to IRCS v1 canonical JSON.

Produces deterministic JSON output with:
- ir_version: "ircs.v1"
- source_idl_version: "idl.v1.2.2"
- source_idl_sha256: SHA256 of source DSL text (UTF-8)
"""

import hashlib
import json
from typing import Any, Optional

from .ast_nodes import (
    DocumentNode,
    SystemNode,
    ActorNode,
    EntityNode,
    FieldNode,
    StorageNode,
    PolicyContextNode,
    ContextFieldNode,
    InvariantNode,
    SodRuleNode,
    WorkflowNode,
    StateNode,
    TransitionNode,
    ApprovalsNode,
    EffectNode,
    OperationsNode,
    ApiSection,
    EndpointNode,
    BindSpec,
    ExprNode,
    AlwaysExpr,
    LiteralValue,
    RefPath,
    HistoryRef,
    CompareExpr,
    AndExpr,
    OrExpr,
    NotExpr,
)


class IRCSEmitter:
    """Emits IRCS v1 JSON from parsed AST."""

    IR_VERSION = "ircs.v1"
    SOURCE_IDL_VERSION = "idl.v1.2.2"

    def __init__(self, ast: DocumentNode, source: str):
        self.ast = ast
        self.source = source
        self._source_hash: Optional[str] = None

    def emit(self) -> dict:
        """Emit IRCS v1 JSON dictionary."""
        ir = {
            "ir_version": self.IR_VERSION,
            "source_idl_version": self.SOURCE_IDL_VERSION,
            "source_idl_sha256": self._compute_source_hash(),
        }

        # System section
        ir["system"] = self._emit_system(self.ast.system) if self.ast.system else {}

        # Department (derived from system)
        ir["department"] = self._emit_department(self.ast.system) if self.ast.system else {}

        # Policy context
        ir["policy_context"] = self._emit_policy_context(self.ast.policy_context)

        # Actors
        ir["actors"] = [self._emit_actor(a) for a in self.ast.actors]

        # Entities
        ir["entities"] = [self._emit_entity(e) for e in self.ast.entities]

        # Invariants
        ir["invariants"] = [self._emit_invariant(i) for i in self.ast.invariants]

        # Separation of Duties
        ir["separation_of_duties"] = [self._emit_sod_rule(r) for r in self.ast.separation_of_duties]

        # Workflows
        ir["workflows"] = [self._emit_workflow(w) for w in self.ast.workflows]

        # Operations
        ir["operations"] = self._emit_operations(self.ast.operations)

        # Runtime (defaults)
        ir["runtime"] = self._emit_runtime()

        return ir

    def emit_json(self, indent: int = 2) -> str:
        """Emit deterministic JSON string."""
        ir = self.emit()
        return json.dumps(ir, indent=indent, sort_keys=True, ensure_ascii=False)

    def _compute_source_hash(self) -> str:
        """Compute SHA256 of source DSL text (UTF-8)."""
        if self._source_hash is None:
            self._source_hash = hashlib.sha256(self.source.encode("utf-8")).hexdigest()
        return self._source_hash

    # ============================================================
    # System & Department
    # ============================================================

    def _emit_system(self, node: SystemNode) -> dict:
        """Emit system section."""
        result = {
            "id": node.id,
            "name": node.name or node.id,
        }
        if node.description:
            result["description"] = node.description
        if node.domain:
            result["domain"] = node.domain
        if node.owner:
            result["owner"] = node.owner
        if node.contact:
            result["contact"] = node.contact
        return result

    def _emit_department(self, system: Optional[SystemNode]) -> dict:
        """Emit department section (derived from system)."""
        if not system:
            return {}

        dept_id = system.domain or system.id.lower()
        return {
            "dept_id": dept_id,
            "name": system.name or system.id,
            "namespace": dept_id,
            "tenancy": system.tenancy.value,
            "entrypoints": {
                "api_prefix": f"/{dept_id}",
                "permission_prefix": f"{dept_id}.",
                "event_prefix": f"{dept_id}.",
            },
        }

    # ============================================================
    # Policy Context
    # ============================================================

    def _emit_policy_context(self, node: Optional[PolicyContextNode]) -> dict:
        """Emit policy_context section."""
        if not node:
            return {"schema": []}

        return {
            "schema": [self._emit_context_field(f) for f in node.fields],
        }

    def _emit_context_field(self, field: ContextFieldNode) -> dict:
        """Emit a policy context field."""
        result = {
            "name": field.name,
            "type": field.type_name,
            "required": field.required,
        }
        if field.default_value is not None:
            result["default"] = field.default_value
        return result

    # ============================================================
    # Actors
    # ============================================================

    def _emit_actor(self, node: ActorNode) -> dict:
        """Emit an actor definition."""
        return {
            "kind": node.kind.value,
            "id": node.id,
            "name": node.name or node.id,
            "description": node.description or "",
            "auth": node.auth.value,
            "permissions": node.permissions,
        }

    # ============================================================
    # Entities
    # ============================================================

    def _emit_entity(self, node: EntityNode) -> dict:
        """Emit an entity definition."""
        result = {
            "name": node.name,
            "storage": self._emit_storage(node.storage),
            "fields": [self._emit_field(f) for f in node.fields],
        }
        return result

    def _emit_storage(self, node: Optional[StorageNode]) -> dict:
        """Emit storage configuration."""
        if not node:
            return {}
        result = {}
        if node.tenant_field:
            result["tenant_field"] = node.tenant_field
        if node.version_field:
            result["version_field"] = node.version_field
        return result

    def _emit_field(self, node: FieldNode) -> dict:
        """Emit a field definition."""
        result = {
            "name": node.name,
            "type": node.type_name,
            "required": node.required,
        }
        if node.unique:
            result["unique"] = True
        if node.indexed:
            result["indexed"] = True
        if node.default_value is not None:
            result["default"] = node.default_value
        if node.min_value is not None:
            result["min"] = node.min_value
        if node.max_value is not None:
            result["max"] = node.max_value
        return result

    # ============================================================
    # Invariants
    # ============================================================

    def _emit_invariant(self, node: InvariantNode) -> dict:
        """Emit an invariant definition."""
        return {
            "name": node.name,
            "applies_to": node.applies_to,
            "when": self._emit_expr(node.when_expr),
            "assert": self._emit_expr(node.assert_expr),
            "severity": node.severity.value,
            "message": node.message or "",
        }

    # ============================================================
    # Separation of Duties
    # ============================================================

    def _emit_sod_rule(self, node: SodRuleNode) -> dict:
        """Emit a SoD rule."""
        return {
            "name": node.name,
            "on_entity": node.on_entity,
            "forbid": {
                "action": node.forbid.action,
                "when": self._emit_expr(node.forbid.when_expr),
            },
            "severity": node.severity.value,
            "message": node.message or "",
        }

    # ============================================================
    # Workflows
    # ============================================================

    def _emit_workflow(self, node: WorkflowNode) -> dict:
        """Emit a workflow definition."""
        return {
            "name": node.name,
            "on_entity": node.on_entity,
            "state_field": "state",  # Convention
            "states": [self._emit_state(s) for s in node.states],
            "transitions": [self._emit_transition(t) for t in node.transitions],
        }

    def _emit_state(self, node: StateNode) -> dict:
        """Emit a workflow state."""
        return {
            "name": node.name,
            "initial": node.initial,
            "terminal": node.terminal,
        }

    def _emit_transition(self, node: TransitionNode) -> dict:
        """Emit a workflow transition."""
        result = {
            "name": node.name,
            "from": node.from_state,
            "to": node.to_state,
        }

        if node.guard:
            result["guard"] = self._emit_expr(node.guard)
        else:
            # CHANGE-2: Emit explicit {"kind": "always"} instead of null
            result["guard"] = {"kind": "always"}

        if node.approvals:
            result["approvals"] = self._emit_approvals(node.approvals)
        else:
            result["approvals"] = None

        result["effects"] = [self._emit_effect(e) for e in node.effects]

        return result

    def _emit_approvals(self, node: ApprovalsNode) -> dict:
        """Emit approval requirements."""
        result = {
            "quorum": node.quorum,
            "roles": node.roles,
            "distinct_actors": node.distinct_actors,
        }
        if node.expires_in:
            result["expires_in"] = node.expires_in
        return result

    def _emit_effect(self, node: EffectNode) -> dict:
        """Emit an effect step."""
        # Map effect names to IRCS kinds
        kind_map = {
            "set_state": "set_state",
            "bump_version": "bump_version",
        }

        result = {
            "kind": kind_map.get(node.name, node.name),
        }

        # Add effect-specific fields
        if node.name == "set_state" and node.args:
            result["value"] = node.args[0]
        elif node.name == "bump_version" and node.args:
            result["field"] = "version"
            result["by"] = node.args[0]

        return result

    # ============================================================
    # Operations
    # ============================================================

    def _emit_operations(self, node: Optional[OperationsNode]) -> dict:
        """Emit operations section."""
        if not node or not node.api:
            return {"api": []}

        return {
            "api": [self._emit_endpoint(e) for e in node.api.endpoints],
        }

    def _emit_endpoint(self, node: EndpointNode) -> dict:
        """Emit an endpoint definition."""
        result = {
            "id": node.id,
            "method": node.method.value,
            "path": node.path or "",
            "path_params": node.path_params,  # CHANGE-5: Include extracted path parameters
            "request_type": node.request_type or "void",
            "response_type": node.response_type or "void",
            "permission": node.permission or "",
            "scope": node.scope.value,
            "idempotency": node.idempotency.value,
            "errors": node.errors,
        }

        if node.bind:
            result["bind"] = self._emit_bind_spec(node.bind)

        return result

    def _emit_bind_spec(self, node: BindSpec) -> dict:
        """Emit bind specification."""
        result = {
            "entity": node.entity,
            "kind": node.kind.value,
        }
        if node.workflow:
            result["workflow"] = node.workflow
        if node.transition:
            result["transition"] = node.transition
        if node.decision:
            result["decision"] = node.decision
        return result

    # ============================================================
    # Runtime
    # ============================================================

    def _emit_runtime(self) -> dict:
        """Emit runtime configuration (defaults)."""
        return {
            "safe_mode": {
                "enabled": True,
                "on_invariant_violation": "enter",
                "on_contract_tamper": "enter",
            },
            "proof": {
                "snapshot_enabled": True,
            },
            "gate_order": [
                "safe_mode",
                "rbac",
                "policy_pre",
                "sod",
                "workflow",
                "invariants",
                "commit",
                "policy_post",
                "ledger_finalize",
            ],
        }

    # ============================================================
    # Expression Emission (Typed AST)
    # ============================================================

    def _emit_expr(self, node: ExprNode) -> dict:
        """Emit an expression as typed AST."""
        if isinstance(node, AlwaysExpr):
            return {"kind": "always"}

        if isinstance(node, LiteralValue):
            return {
                "lit": node.value,
                "type": node.type_name,
            }

        if isinstance(node, RefPath):
            return {
                "ref": node.path,
                "type": node.type_name or "unknown",
            }

        if isinstance(node, HistoryRef):
            return {
                "history": node.step_name,
                "attr": node.attr,
                "type": node.type_name or "unknown",
            }

        if isinstance(node, CompareExpr):
            return {
                "kind": "compare",
                "op": node.op,
                "lhs": self._emit_expr(node.lhs),
                "rhs": self._emit_expr(node.rhs),
            }

        if isinstance(node, AndExpr):
            return {
                "kind": "and",
                "exprs": [self._emit_expr(e) for e in node.exprs],
            }

        if isinstance(node, OrExpr):
            return {
                "kind": "or",
                "exprs": [self._emit_expr(e) for e in node.exprs],
            }

        if isinstance(node, NotExpr):
            return {
                "kind": "not",
                "expr": self._emit_expr(node.expr),
            }

        raise ValueError(f"Unknown expression type: {type(node)}")
