"""Legacy Write Registry - Governed write actions with ledger integration.

This module manages governed write actions to legacy systems:
- Intent creation with governance gate evaluation
- Approval flow integration (GAP 3: no self-approved)
- Outbox file creation for allowed actions
- Full audit trail in ledger
- Agent auto-solicitation on deny (GAP 4)

Etapa 4.3: Legacy Bridge Write-Mode (Governado)
GAP 3: Eliminar "self-approved" e decisões implícitas em writes críticos
GAP 4: Agentes como atores governados - auto-solicitação quando negado
"""

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.ledger import get_ledger_for_institution
from engine.core.actor_context import ActorContext
from engine.core.mandates import evaluate_mandates, MandateEvalResult
from engine.core.autonomy import evaluate_autonomy, AutonomyEvalResult
from engine.core.policy import evaluate_policies, PolicyEvalResult
from engine.core.approvals import (
    get_approvals_policy,
    generate_approval_id,
    emit_approval_requested,
    compute_payload_sha256,
)
from engine.core.install_mode import is_prod_mode, is_dev_mode
from engine.core.errors import (
    LEGACY_WRITE_ACTION_TYPE_UNKNOWN,
    LEGACY_WRITE_PARAMS_INVALID,
    LEGACY_WRITE_DENIED_MANDATE,
    LEGACY_WRITE_DENIED_AUTONOMY,
    LEGACY_WRITE_DENIED_POLICY,
    LEGACY_WRITE_OUTBOX_FAILED,
    LEGACY_WRITE_NO_APPROVAL_RULE_PROD,
    LEGACY_WRITE_NO_ADMIN_ROLE_DEV,
    LEGACY_WRITE_PENDING_APPROVAL,
)
from engine.legacy_bridge.write_models import (
    LegacyWriteAction,
    ActionStatus,
    ACTION_SCHEMAS,
    validate_action_params,
    compute_intent_sha256,
)
from engine.legacy_bridge.connectors.outbox_connector import (
    OutboxConnector,
    OutboxWriteResult,
)


# Ledger event types for Legacy Write
LEGACY_WRITE_INTENT_CREATED = "LEGACY_WRITE_INTENT_CREATED"
LEGACY_WRITE_APPROVAL_REQUESTED = "LEGACY_WRITE_APPROVAL_REQUESTED"
LEGACY_WRITE_ALLOWED = "LEGACY_WRITE_ALLOWED"
LEGACY_WRITE_DENIED = "LEGACY_WRITE_DENIED"
LEGACY_WRITE_ENQUEUED = "LEGACY_WRITE_ENQUEUED"
LEGACY_WRITE_ACKED = "LEGACY_WRITE_ACKED"


@dataclass
class WriteResult:
    """Result of a write action attempt."""

    success: bool
    action: Optional[LegacyWriteAction] = None
    outbox_path: Optional[str] = None
    outbox_sha256: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    denied_by: Optional[str] = None  # MANDATE | AUTONOMY | POLICY
    pending_approval: bool = False  # True if awaiting approval decision
    approval_id: Optional[str] = None  # Approval ID if pending


class LegacyWriteRegistry:
    """Registry for governed legacy write actions.

    Manages:
    - actions_registry.jsonl: Append-only action log
    - state.json: Current state for fast lookup

    Governance flow (GAP 3 compliant):
    1. Validate action type and params
    2. Emit LEGACY_WRITE_INTENT_CREATED
    3. Check approvals policy for this endpoint
       - If rule exists: create approval request, return PENDING_APPROVAL
       - If no rule + prod mode: deny deterministically
       - If no rule + dev mode: allow only with admin role + mandate
    4. Evaluate governance gates (mandate -> autonomy -> policy)
    5. If allowed: write outbox + emit LEGACY_WRITE_ENQUEUED
    6. If denied: emit LEGACY_WRITE_DENIED

    Note: approved_by is NEVER set to requester (self-approved eliminated).
    """

    def __init__(self, institution_id: str, dept_id: Optional[str] = None) -> None:
        """Initialize write registry for an institution.

        Args:
            institution_id: Institution UUID.
            dept_id: Optional department ID for multi-dept mode.
        """
        self._institution_id = institution_id
        self._dept_id = dept_id
        self._lock = threading.Lock()

        # Resolve paths
        inst_root = get_institution_root(institution_id)
        if dept_id:
            self._write_root = inst_root / "depts" / dept_id / "legacy_bridge"
        else:
            self._write_root = inst_root / "legacy_bridge"

        self._actions_path = self._write_root / "actions_registry.jsonl"
        self._state_path = self._write_root / "write_state.json"

        # Initialize connectors
        self._outbox = OutboxConnector(institution_id, dept_id)

        # In-memory state cache
        self._state: Dict[str, Any] = {"schema_version": "1.0", "actions": {}}
        self._load_state()

    def _ensure_dir(self) -> None:
        """Ensure write directory exists."""
        self._write_root.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> None:
        """Load state from state.json if exists."""
        if self._state_path.exists():
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._state = {"schema_version": "1.0", "actions": {}}

    def _save_state(self) -> None:
        """Save current state to state.json."""
        self._ensure_dir()
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _append_action(self, action: LegacyWriteAction) -> None:
        """Append action to actions JSONL."""
        self._ensure_dir()
        with open(self._actions_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(action.to_dict(), sort_keys=True) + "\n")

    def _emit_ledger_event(
        self,
        event_type: str,
        action_id: str,
        step: str,
        payload: Dict[str, Any],
        actor_id: str = "system",
        actor_roles: Optional[List[str]] = None,
    ) -> None:
        """Emit event to audit ledger."""
        ledger = get_ledger_for_institution(self._institution_id)
        ledger.append(
            event_type=event_type,
            tenant_id=self._institution_id,
            actor_id=actor_id,
            actor_roles=actor_roles or (["system"] if actor_id == "system" else []),
            case_id=action_id,
            step=step,
            payload=payload,
            dept_id=self._dept_id,
        )

    def _build_endpoint_sig(self, action_type: str) -> str:
        """Build endpoint signature for governance gates.

        Args:
            action_type: Type of action.

        Returns:
            Endpoint signature string.
        """
        return f"POST /bridge/write/{action_type}"

    def request_write(
        self,
        action_type: str,
        params: Dict[str, Any],
        actor_id: str,
        actor_roles: Optional[List[str]] = None,
        is_agent: bool = False,
        on_behalf_of: Optional[str] = None,
    ) -> WriteResult:
        """Request a governed write action.

        Flow (GAP 3 compliant - no self-approved):
        1. Validate action type and params
        2. Create action with intent hash
        3. Emit LEGACY_WRITE_INTENT_CREATED
        4. Check approvals policy for this endpoint
           - If rule exists: create approval request, return PENDING_APPROVAL
           - If no rule + prod mode: deny deterministically
           - If no rule + dev mode: allow only with admin role + mandate
        5. Evaluate governance gates (mandate -> autonomy -> policy)
        6. If allowed: write outbox + emit events
        7. If denied: record denial + emit LEGACY_WRITE_DENIED
           - GAP 4: If caller is agent, also create agent request

        Args:
            action_type: Type of action (e.g., "increase_limit").
            params: Action parameters.
            actor_id: Actor requesting the action.
            actor_roles: Roles of the actor.
            is_agent: GAP 4 - True if this actor is a governed agent.
            on_behalf_of: GAP 4 - Actor ID this agent is acting for (delegation).

        Returns:
            WriteResult with success status and details.
        """
        with self._lock:
            # 1. Validate action type
            if action_type not in ACTION_SCHEMAS:
                return WriteResult(
                    success=False,
                    error_code=LEGACY_WRITE_ACTION_TYPE_UNKNOWN,
                    error_message=f"Unknown action type: {action_type}",
                )

            # 2. Validate params
            validation_errors = validate_action_params(action_type, params)
            if validation_errors:
                return WriteResult(
                    success=False,
                    error_code=LEGACY_WRITE_PARAMS_INVALID,
                    error_message="; ".join(validation_errors),
                )

            # 3. Create action
            action_id = str(uuid.uuid4())
            action = LegacyWriteAction(
                action_id=action_id,
                action_type=action_type,
                params=params,
                requested_by=actor_id,
                institution_id=self._institution_id,
                dept_id=self._dept_id,
                status=ActionStatus.PENDING.value,
            )

            # 4. Emit LEGACY_WRITE_INTENT_CREATED
            # GAP 4: Include on_behalf_of in payload for audit
            intent_payload = {
                "action_id": action_id,
                "action_type": action_type,
                "params_sha256": action.intent_sha256,
                "requested_by": actor_id,
            }
            if on_behalf_of:
                intent_payload["on_behalf_of"] = on_behalf_of
            if is_agent:
                intent_payload["is_agent"] = True

            self._emit_ledger_event(
                event_type=LEGACY_WRITE_INTENT_CREATED,
                action_id=action_id,
                step=f"LEGACY_WRITE:{action_type}",
                payload=intent_payload,
                actor_id=actor_id,
                actor_roles=actor_roles,
            )

            # 5. Check approvals policy (GAP 3)
            endpoint_sig = self._build_endpoint_sig(action_type)
            actor_ctx = ActorContext(actor_id=actor_id, roles=actor_roles or [])

            approvals_policy = get_approvals_policy(self._dept_id)
            approval_rule = None
            if approvals_policy:
                approval_rule = approvals_policy.get_rule_for_api(endpoint_sig)

            if approval_rule:
                # Rule exists: create approval request and return PENDING_APPROVAL
                return self._create_approval_request(
                    action=action,
                    rule=approval_rule,
                    params=params,
                    actor_id=actor_id,
                    actor_roles=actor_roles,
                )
            else:
                # No rule: check install mode
                if is_prod_mode():
                    # Prod mode: deny deterministically (no self-approve)
                    return self._handle_denial(
                        action=action,
                        denied_by="NO_APPROVAL_RULE",
                        reason="No approval rule configured for this action in production mode",
                        actor_id=actor_id,
                        actor_roles=actor_roles,
                        error_code=LEGACY_WRITE_NO_APPROVAL_RULE_PROD,
                        is_agent=is_agent,
                        on_behalf_of=on_behalf_of,
                    )
                else:
                    # Dev mode: allow only with admin role + mandate
                    if not self._has_admin_role(actor_roles):
                        return self._handle_denial(
                            action=action,
                            denied_by="NO_ADMIN_ROLE",
                            reason="Dev mode requires 'admin' role when no approval rule is configured",
                            actor_id=actor_id,
                            actor_roles=actor_roles,
                            error_code=LEGACY_WRITE_NO_ADMIN_ROLE_DEV,
                            is_agent=is_agent,
                            on_behalf_of=on_behalf_of,
                        )
                    # Admin role present, continue to governance gates

            # 6. Evaluate governance gates
            # 6a. Mandate gate
            mandate_result = evaluate_mandates(
                phase="pre",
                dept_id=self._dept_id,
                endpoint_sig=endpoint_sig,
                actor=actor_ctx,
                payload=params,
                institution_id=self._institution_id,
            )

            if not mandate_result.allow:
                return self._handle_denial(
                    action=action,
                    denied_by="MANDATE",
                    reason=self._format_mandate_denial(mandate_result),
                    actor_id=actor_id,
                    actor_roles=actor_roles,
                    is_agent=is_agent,
                    on_behalf_of=on_behalf_of,
                )

            # 6b. Autonomy gate
            autonomy_result = evaluate_autonomy(
                phase="pre",
                dept_id=self._dept_id,
                endpoint_sig=endpoint_sig,
            )

            if autonomy_result.decision != "allow":
                return self._handle_denial(
                    action=action,
                    denied_by="AUTONOMY",
                    reason=autonomy_result.reason or f"Autonomy level insufficient: {autonomy_result.current_level} < {autonomy_result.required_level}",
                    actor_id=actor_id,
                    actor_roles=actor_roles,
                    is_agent=is_agent,
                    on_behalf_of=on_behalf_of,
                )

            # 6c. Policy gate
            policy_result = evaluate_policies(
                phase="pre",
                dept_id=self._dept_id,
                endpoint_sig=endpoint_sig,
                payload=params,
            )

            if not policy_result.allow:
                return self._handle_denial(
                    action=action,
                    denied_by="POLICY",
                    reason=self._format_policy_denial(policy_result),
                    actor_id=actor_id,
                    actor_roles=actor_roles,
                    is_agent=is_agent,
                    on_behalf_of=on_behalf_of,
                )

            # 7. All gates passed - emit LEGACY_WRITE_ALLOWED
            # Note: approved_by is NOT set to requester (GAP 3 compliant)
            # In dev mode without approval rule, we record "dev_admin_bypass"
            action.mandate_id = mandate_result.mandate_id
            action.status = ActionStatus.ENQUEUED.value
            action.enqueued_at = datetime.now(timezone.utc).isoformat()

            self._emit_ledger_event(
                event_type=LEGACY_WRITE_ALLOWED,
                action_id=action_id,
                step=f"LEGACY_WRITE:{action_type}",
                payload={
                    "action_id": action_id,
                    "mandate_id": mandate_result.mandate_id,
                    "autonomy_level": autonomy_result.current_level,
                    "approval_mode": "dev_admin_bypass",  # GAP 3: explicit bypass mode
                    "admin_actor_id": actor_id,  # Who used the bypass
                },
                actor_id=actor_id,
                actor_roles=actor_roles,
            )

            # 8. Write to outbox
            outbox_result = self._outbox.write_action(action)

            if not outbox_result.success:
                return WriteResult(
                    success=False,
                    action=action,
                    error_code=LEGACY_WRITE_OUTBOX_FAILED,
                    error_message=outbox_result.error_message,
                )

            # 9. Emit LEGACY_WRITE_ENQUEUED
            self._emit_ledger_event(
                event_type=LEGACY_WRITE_ENQUEUED,
                action_id=action_id,
                step=f"LEGACY_WRITE:{action_type}",
                payload={
                    "action_id": action_id,
                    "outbox_path": outbox_result.outbox_path,
                    "outbox_sha256": outbox_result.outbox_sha256,
                },
                actor_id=actor_id,
                actor_roles=actor_roles,
            )

            # 10. Persist action
            self._append_action(action)
            self._state.setdefault("actions", {})[action_id] = action.to_dict()
            self._save_state()

            return WriteResult(
                success=True,
                action=action,
                outbox_path=outbox_result.outbox_path,
                outbox_sha256=outbox_result.outbox_sha256,
            )

    def _has_admin_role(self, actor_roles: Optional[List[str]]) -> bool:
        """Check if actor has admin role.

        Args:
            actor_roles: List of actor roles.

        Returns:
            True if actor has 'admin' role.
        """
        if not actor_roles:
            return False
        return "admin" in actor_roles

    def _create_approval_request(
        self,
        action: LegacyWriteAction,
        rule: Any,  # ApprovalRule
        params: Dict[str, Any],
        actor_id: str,
        actor_roles: Optional[List[str]],
    ) -> WriteResult:
        """Create an approval request for the action.

        Args:
            action: The LegacyWriteAction.
            rule: The ApprovalRule that triggered.
            params: Action parameters.
            actor_id: Actor requesting.
            actor_roles: Actor's roles.

        Returns:
            WriteResult with pending_approval=True.
        """
        # Generate approval ID
        approval_id = generate_approval_id()

        # Update action with approval info
        action.status = ActionStatus.PENDING_APPROVAL.value
        action.approval_id = approval_id

        # Compute payload hash
        params_bytes = json.dumps(params, sort_keys=True).encode("utf-8")
        payload_sha256 = compute_payload_sha256(params_bytes)

        # Build actor context for approval request
        actor_ctx = ActorContext(actor_id=actor_id, roles=actor_roles or [])

        # Emit APPROVAL_REQUESTED event (via approvals subsystem)
        emit_approval_requested(
            approval_id=approval_id,
            rule=rule,
            actor=actor_ctx,
            payload_sha256=payload_sha256,
        )

        # Emit LEGACY_WRITE_APPROVAL_REQUESTED event (correlates action_id with approval_id)
        self._emit_ledger_event(
            event_type=LEGACY_WRITE_APPROVAL_REQUESTED,
            action_id=action.action_id,
            step=f"LEGACY_WRITE:{action.action_type}",
            payload={
                "action_id": action.action_id,
                "approval_id": approval_id,
                "approval_rule": rule.rule_name,
                "approver_roles": rule.approver_roles,
                "params_sha256": action.intent_sha256,
            },
            actor_id=actor_id,
            actor_roles=actor_roles,
        )

        # Persist action in PENDING_APPROVAL state
        self._append_action(action)
        self._state.setdefault("actions", {})[action.action_id] = action.to_dict()
        self._save_state()

        return WriteResult(
            success=False,  # Not yet successful (pending approval)
            action=action,
            pending_approval=True,
            approval_id=approval_id,
            error_code=LEGACY_WRITE_PENDING_APPROVAL,
            error_message="Action requires approval before execution",
        )

    def complete_approved_action(
        self,
        action_id: str,
        approved_by: str,
        approver_roles: Optional[List[str]] = None,
    ) -> WriteResult:
        """Complete an approved action by writing to outbox.

        Called after approval decision is made via /approvals/{id}/decide.

        Args:
            action_id: The action ID to complete.
            approved_by: Actor ID who approved (NOT the requester).
            approver_roles: Roles of the approver.

        Returns:
            WriteResult with outbox details.
        """
        with self._lock:
            # Get action
            action = self.get_action(action_id)
            if not action:
                return WriteResult(
                    success=False,
                    error_code="LEGACY_WRITE_ACTION_NOT_FOUND",
                    error_message=f"Action not found: {action_id}",
                )

            # Verify action is in PENDING_APPROVAL state
            if action.status != ActionStatus.PENDING_APPROVAL.value:
                return WriteResult(
                    success=False,
                    error_code="LEGACY_WRITE_INVALID_STATE",
                    error_message=f"Action is not pending approval: {action.status}",
                )

            # Evaluate governance gates (post-approval)
            endpoint_sig = self._build_endpoint_sig(action.action_type)
            actor_ctx = ActorContext(actor_id=approved_by, roles=approver_roles or [])

            # Mandate gate
            mandate_result = evaluate_mandates(
                phase="post",
                dept_id=self._dept_id,
                endpoint_sig=endpoint_sig,
                actor=actor_ctx,
                payload=action.params,
                institution_id=self._institution_id,
            )

            if not mandate_result.allow:
                return self._handle_denial(
                    action=action,
                    denied_by="MANDATE",
                    reason=self._format_mandate_denial(mandate_result),
                    actor_id=approved_by,
                    actor_roles=approver_roles,
                )

            # Autonomy gate
            autonomy_result = evaluate_autonomy(
                phase="post",
                dept_id=self._dept_id,
                endpoint_sig=endpoint_sig,
            )

            if autonomy_result.decision != "allow":
                return self._handle_denial(
                    action=action,
                    denied_by="AUTONOMY",
                    reason=autonomy_result.reason or f"Autonomy level insufficient",
                    actor_id=approved_by,
                    actor_roles=approver_roles,
                )

            # Policy gate
            policy_result = evaluate_policies(
                phase="post",
                dept_id=self._dept_id,
                endpoint_sig=endpoint_sig,
                payload=action.params,
            )

            if not policy_result.allow:
                return self._handle_denial(
                    action=action,
                    denied_by="POLICY",
                    reason=self._format_policy_denial(policy_result),
                    actor_id=approved_by,
                    actor_roles=approver_roles,
                )

            # Update action with approval info
            action.approved_by = approved_by  # GAP 3: actual approver, not requester
            action.mandate_id = mandate_result.mandate_id
            action.status = ActionStatus.ENQUEUED.value
            action.enqueued_at = datetime.now(timezone.utc).isoformat()

            # Emit LEGACY_WRITE_ALLOWED
            self._emit_ledger_event(
                event_type=LEGACY_WRITE_ALLOWED,
                action_id=action.action_id,
                step=f"LEGACY_WRITE:{action.action_type}",
                payload={
                    "action_id": action.action_id,
                    "mandate_id": mandate_result.mandate_id,
                    "autonomy_level": autonomy_result.current_level,
                    "approval_mode": "formal_approval",  # GAP 3: formal approval
                    "approved_by": approved_by,  # Actual approver
                    "approval_id": action.approval_id,
                },
                actor_id=approved_by,
                actor_roles=approver_roles,
            )

            # Write to outbox
            outbox_result = self._outbox.write_action(action)

            if not outbox_result.success:
                return WriteResult(
                    success=False,
                    action=action,
                    error_code=LEGACY_WRITE_OUTBOX_FAILED,
                    error_message=outbox_result.error_message,
                )

            # Emit LEGACY_WRITE_ENQUEUED
            self._emit_ledger_event(
                event_type=LEGACY_WRITE_ENQUEUED,
                action_id=action.action_id,
                step=f"LEGACY_WRITE:{action.action_type}",
                payload={
                    "action_id": action.action_id,
                    "outbox_path": outbox_result.outbox_path,
                    "outbox_sha256": outbox_result.outbox_sha256,
                },
                actor_id=approved_by,
                actor_roles=approver_roles,
            )

            # Update persisted action
            self._append_action(action)
            self._state["actions"][action.action_id] = action.to_dict()
            self._save_state()

            return WriteResult(
                success=True,
                action=action,
                outbox_path=outbox_result.outbox_path,
                outbox_sha256=outbox_result.outbox_sha256,
            )

    def reject_action(
        self,
        action_id: str,
        rejected_by: str,
        reason: Optional[str] = None,
        rejector_roles: Optional[List[str]] = None,
    ) -> WriteResult:
        """Reject a pending approval action.

        Called after approval decision is made via /approvals/{id}/decide with reject.

        Args:
            action_id: The action ID to reject.
            rejected_by: Actor ID who rejected.
            reason: Optional rejection reason.
            rejector_roles: Roles of the rejector.

        Returns:
            WriteResult with denial details.
        """
        with self._lock:
            # Get action
            action = self.get_action(action_id)
            if not action:
                return WriteResult(
                    success=False,
                    error_code="LEGACY_WRITE_ACTION_NOT_FOUND",
                    error_message=f"Action not found: {action_id}",
                )

            # Verify action is in PENDING_APPROVAL state
            if action.status != ActionStatus.PENDING_APPROVAL.value:
                return WriteResult(
                    success=False,
                    error_code="LEGACY_WRITE_INVALID_STATE",
                    error_message=f"Action is not pending approval: {action.status}",
                )

            return self._handle_denial(
                action=action,
                denied_by="APPROVAL_REJECTED",
                reason=reason or "Approval request rejected",
                actor_id=rejected_by,
                actor_roles=rejector_roles,
            )

    def get_action_by_approval_id(self, approval_id: str) -> Optional[LegacyWriteAction]:
        """Get action by its approval ID.

        Args:
            approval_id: Approval ID.

        Returns:
            LegacyWriteAction if found.
        """
        for data in self._state.get("actions", {}).values():
            if data.get("approval_id") == approval_id:
                return LegacyWriteAction.from_dict(data)
        return None

    def _handle_denial(
        self,
        action: LegacyWriteAction,
        denied_by: str,
        reason: str,
        actor_id: str,
        actor_roles: Optional[List[str]],
        error_code: Optional[str] = None,
        is_agent: bool = False,
        on_behalf_of: Optional[str] = None,
    ) -> WriteResult:
        """Handle action denial.

        GAP 4: If caller is an agent, also creates an agent request
        for institutional tracking and future resolution.

        Args:
            action: The action being denied.
            denied_by: Gate that denied (MANDATE | AUTONOMY | POLICY | NO_APPROVAL_RULE | etc).
            reason: Denial reason.
            actor_id: Actor who requested.
            actor_roles: Roles of the actor.
            error_code: Optional explicit error code (overrides default mapping).
            is_agent: GAP 4 - True if this actor is a governed agent.
            on_behalf_of: GAP 4 - Actor ID this agent is acting for.

        Returns:
            WriteResult with denial details.
        """
        action.status = ActionStatus.DENIED.value
        action.denied_by = denied_by
        action.denied_reason = reason

        # Build deny payload with GAP 4 context
        deny_payload = {
            "action_id": action.action_id,
            "denied_by": denied_by,
            "reason": reason,
        }
        if on_behalf_of:
            deny_payload["on_behalf_of"] = on_behalf_of
        if is_agent:
            deny_payload["is_agent"] = True

        # Emit LEGACY_WRITE_DENIED
        self._emit_ledger_event(
            event_type=LEGACY_WRITE_DENIED,
            action_id=action.action_id,
            step=f"LEGACY_WRITE:{action.action_type}",
            payload=deny_payload,
            actor_id=actor_id,
            actor_roles=actor_roles,
        )

        # Persist denied action
        self._append_action(action)
        self._state.setdefault("actions", {})[action.action_id] = action.to_dict()
        self._save_state()

        # GAP 4: If agent, create agent request for institutional tracking
        if is_agent:
            self._create_agent_request(
                agent_actor_id=actor_id,
                on_behalf_of=on_behalf_of,
                action_type=action.action_type,
                deny_code=denied_by,
                deny_reason=reason,
            )

        # Use explicit error_code if provided, else map from denied_by
        if error_code is None:
            error_code_map = {
                "MANDATE": LEGACY_WRITE_DENIED_MANDATE,
                "AUTONOMY": LEGACY_WRITE_DENIED_AUTONOMY,
                "POLICY": LEGACY_WRITE_DENIED_POLICY,
            }
            error_code = error_code_map.get(denied_by, "LEGACY_WRITE_DENIED")

        return WriteResult(
            success=False,
            action=action,
            error_code=error_code,
            error_message=reason,
            denied_by=denied_by,
        )

    def _create_agent_request(
        self,
        agent_actor_id: str,
        on_behalf_of: Optional[str],
        action_type: str,
        deny_code: str,
        deny_reason: str,
    ) -> None:
        """Create an agent request when an agent is denied.

        GAP 4: Agents create institutional requests when denied,
        enabling admin visibility and future resolution.

        Args:
            agent_actor_id: The agent's actor ID.
            on_behalf_of: Who the agent was acting for.
            action_type: Type of action attempted.
            deny_code: Denial code (MANDATE, AUTONOMY, POLICY, etc).
            deny_reason: Human-readable denial reason.
        """
        from engine.agent_ops.agent_requests import get_agent_requests_registry

        try:
            registry = get_agent_requests_registry(
                institution_id=self._institution_id,
                dept_id=self._dept_id,
            )
            endpoint_sig = self._build_endpoint_sig(action_type)

            registry.create_request(
                agent_actor_id=agent_actor_id,
                on_behalf_of=on_behalf_of,
                endpoint_sig=endpoint_sig,
                action_type=action_type,
                deny_code=deny_code,
                deny_details={"reason": deny_reason},
            )
        except Exception:
            # Don't fail the denial if agent request fails
            pass

    def _format_mandate_denial(self, result: MandateEvalResult) -> str:
        """Format mandate denial reason."""
        if result.violations:
            messages = [v.message for v in result.violations if v.message]
            if messages:
                return "; ".join(messages)
        return "No valid mandate for this action"

    def _format_policy_denial(self, result: PolicyEvalResult) -> str:
        """Format policy denial reason."""
        if result.violations:
            messages = [v.message for v in result.violations if v.message]
            if messages:
                return "; ".join(messages)
        return "Policy violation"

    def get_action(self, action_id: str) -> Optional[LegacyWriteAction]:
        """Get action by ID.

        Args:
            action_id: Action UUID.

        Returns:
            LegacyWriteAction if found.
        """
        data = self._state.get("actions", {}).get(action_id)
        if data:
            return LegacyWriteAction.from_dict(data)
        return None

    def list_actions(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[LegacyWriteAction]:
        """List actions, optionally filtered by status.

        Args:
            status: Filter by status (pending, enqueued, denied, etc.).
            limit: Maximum number of actions to return.

        Returns:
            List of LegacyWriteAction.
        """
        actions = []
        for data in self._state.get("actions", {}).values():
            if status and data.get("status") != status:
                continue
            actions.append(LegacyWriteAction.from_dict(data))
            if len(actions) >= limit:
                break
        return actions
