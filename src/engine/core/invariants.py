"""Invariants - minimal schema validation for expenses."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .errors import INVARIANT_VIOLATION, INVARIANT_SCHEMA_INVALID


@dataclass
class InvariantViolation:
    """Details of an invariant violation."""
    field: str
    message: str
    value: Any


class InvariantsPolicy:
    """Invariants policy loaded from invariants.json."""

    def __init__(self, invariants_data: Dict[str, Any]) -> None:
        """Initialize invariants policy from contract data."""
        self._data = invariants_data

    def get_expense_schema(self) -> Optional[Dict[str, Any]]:
        """Get expense invariants schema."""
        return self._data.get("expense")

    def validate_expense(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str], List[str]]:
        """Validate expense payload against invariants.
        
        Args:
            payload: The expense payload to validate.
            
        Returns:
            Tuple of (ok, error_code, violations).
            - ok=True means all invariants pass.
            - ok=False means violations found.
        """
        schema = self.get_expense_schema()
        if schema is None:
            # No schema defined - allow
            return (True, None, [])
        
        violations = []
        
        # Validate amount
        if "amount" in schema:
            amount_schema = schema["amount"]
            if not isinstance(amount_schema, dict):
                return (False, INVARIANT_SCHEMA_INVALID, ["Invalid amount schema"])
            
            amount = payload.get("amount")
            if amount is None:
                violations.append("amount: required field missing")
            else:
                try:
                    amount_num = float(amount)
                    min_val = amount_schema.get("min")
                    max_val = amount_schema.get("max")
                    
                    if min_val is not None and amount_num < min_val:
                        violations.append(f"amount: {amount_num} is below minimum {min_val}")
                    if max_val is not None and amount_num > max_val:
                        violations.append(f"amount: {amount_num} exceeds maximum {max_val}")
                except (TypeError, ValueError):
                    violations.append(f"amount: invalid numeric value '{amount}'")
        
        # Validate description
        if "description" in schema:
            desc_schema = schema["description"]
            if not isinstance(desc_schema, dict):
                return (False, INVARIANT_SCHEMA_INVALID, ["Invalid description schema"])
            
            description = payload.get("description")
            required = desc_schema.get("required", False)
            max_len = desc_schema.get("max_len")
            
            if description is None:
                if required:
                    violations.append("description: required field missing")
            else:
                if not isinstance(description, str):
                    violations.append(f"description: must be string, got {type(description).__name__}")
                elif max_len is not None and len(description) > max_len:
                    violations.append(f"description: length {len(description)} exceeds max_len {max_len}")
        
        if violations:
            return (False, INVARIANT_VIOLATION, violations)
        
        return (True, None, [])


# Global invariants policy
_invariants_policy: Optional[InvariantsPolicy] = None


def set_invariants_policy(policy: Optional[InvariantsPolicy]) -> None:
    """Set the global invariants policy."""
    global _invariants_policy
    _invariants_policy = policy


def get_invariants_policy() -> Optional[InvariantsPolicy]:
    """Get the global invariants policy."""
    return _invariants_policy


def validate_expense_invariants(payload: Dict[str, Any]) -> Tuple[bool, Optional[str], List[str]]:
    """Validate expense payload against invariants.
    
    Args:
        payload: The expense payload to validate.
        
    Returns:
        Tuple of (ok, error_code, violations).
    """
    policy = get_invariants_policy()
    if policy is None:
        # No policy - allow
        return (True, None, [])
    
    return policy.validate_expense(payload)
