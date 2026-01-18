"""Interdepartmental contracts - catalog and validation."""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.loader.load_bundle import get_bundle_context
from engine.core.errors import (
    CONTRACT_NOT_FOUND,
    CONTRACT_PROVIDER_MISMATCH,
    CONTRACT_CONSUMER_FORBIDDEN,
)


@dataclass
class ContractDef:
    """Definition of an interdepartmental contract."""

    contract_id: str
    provider_dept: str
    consumers: List[str]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContractDef":
        """Create from dictionary."""
        return cls(
            contract_id=data.get("contract_id", ""),
            provider_dept=data.get("provider_dept", ""),
            consumers=data.get("consumers", []),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            approval_required=data.get("approval_required", False),
        )


class ContractCatalog:
    """Catalog of interdepartmental contracts."""

    def __init__(self, contracts_data: Optional[Dict[str, Any]] = None) -> None:
        """Initialize catalog from contracts.json data.

        Args:
            contracts_data: Parsed contracts.json content.
        """
        self._contracts: Dict[str, ContractDef] = {}
        if contracts_data:
            self._load_contracts(contracts_data)

    def _load_contracts(self, data: Dict[str, Any]) -> None:
        """Load contracts from catalog data."""
        contracts_list = data.get("contracts", [])
        for contract_data in contracts_list:
            contract = ContractDef.from_dict(contract_data)
            if contract.contract_id:
                self._contracts[contract.contract_id] = contract

    def find_contract(self, contract_id: str) -> Optional[ContractDef]:
        """Find contract by ID.

        Args:
            contract_id: Contract identifier.

        Returns:
            ContractDef or None if not found.
        """
        return self._contracts.get(contract_id)

    def list_contracts(self) -> List[ContractDef]:
        """List all contracts."""
        return list(self._contracts.values())


def get_contract_catalog() -> Optional[ContractCatalog]:
    """Get contract catalog from current bundle context.

    Returns:
        ContractCatalog or None if not in multi-mode or no catalog.
    """
    bundle_ctx = get_bundle_context()
    if bundle_ctx is None:
        return None

    if bundle_ctx.mode != "multi":
        return None

    if bundle_ctx.contracts_catalog is None:
        return None

    return ContractCatalog(bundle_ctx.contracts_catalog)


def find_contract(contract_id: str) -> Optional[ContractDef]:
    """Find contract by ID from current bundle.

    Args:
        contract_id: Contract identifier.

    Returns:
        ContractDef or None if not found.
    """
    catalog = get_contract_catalog()
    if catalog is None:
        return None
    return catalog.find_contract(contract_id)


def validate_consumer(contract: ContractDef, consumer_dept: str) -> bool:
    """Check if department is authorized consumer of contract.

    Args:
        contract: Contract definition.
        consumer_dept: Department attempting to invoke.

    Returns:
        True if authorized, False otherwise.
    """
    return consumer_dept in contract.consumers


def validate_provider(contract: ContractDef, provider_dept: str) -> bool:
    """Check if department is the provider of contract.

    Args:
        contract: Contract definition.
        provider_dept: Department attempting to decide.

    Returns:
        True if is provider, False otherwise.
    """
    return contract.provider_dept == provider_dept


def compute_payload_sha256(payload: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of payload (canonical JSON).

    Args:
        payload: Payload dictionary.

    Returns:
        SHA256 hash prefixed with "SHA256:".
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    hash_hex = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"SHA256:{hash_hex}"


def generate_case_id() -> str:
    """Generate a new case ID (UUID)."""
    return str(uuid.uuid4())
