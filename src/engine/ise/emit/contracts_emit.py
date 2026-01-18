"""Interdepartmental contracts emitter."""

import json
from typing import Dict, Any, List

from engine.ise.idl_parser import ParsedIDL, IDLContract


def emit_contracts(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit contracts.json from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        Contracts catalog as dict.
    """
    contracts = []

    for contract in parsed.contracts:
        contracts.append({
            "contract_id": contract.contract_id,
            "provider_dept": contract.provider_dept,
            "consumers": sorted(contract.consumers),
            "input_schema": contract.input_schema,
            "output_schema": contract.output_schema,
            "approval_required": contract.approval_required,
        })

    return {
        "version": "1.0",
        "contracts": sorted(contracts, key=lambda c: c["contract_id"]),
    }


def emit_contracts_json(parsed: ParsedIDL) -> str:
    """Emit contracts catalog as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    return json.dumps(emit_contracts(parsed), indent=2, sort_keys=True)
