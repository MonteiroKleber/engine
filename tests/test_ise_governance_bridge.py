import json
from pathlib import Path

from engine.ise.compiler import compile_from_ircs


def test_ise_emits_non_empty_mandates_and_autonomy_from_ircs(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    ir = {
        "ir_version": "ircs.v1",
        "source_idl_version": "idl.v1.2.2",
        "source_idl_sha256": "a" * 64,
        "system": {"id": "T", "name": "T", "owner": "T", "domain": "t", "description": "t", "contact": "t"},
        "actors": [
            {
                "kind": "human",
                "id": "user",
                "name": "User",
                "auth": "oauth2",
                "permissions": ["reports.create"],
            },
        ],
        "entities": [],
        "invariants": [],
        "separation_of_duties": [],
        "workflows": [],
        "operations": {
            "api": [
                {
                    "id": "report_create",
                    "method": "POST",
                    "path": "/reports",
                    "permission": "reports.create",
                    "scope": "tenant",
                    "idempotency": "required",
                    "errors": [400, 401, 403],
                    "bind": {"entity": "ContentReport", "kind": "create"},
                    "request_type": "any",
                    "response_type": "any",
                    "path_params": [],
                }
            ]
        },
    }

    result = compile_from_ircs(ir, bundle_name="t_bundle", output_dir=str(out_dir))
    assert result.success, (result.error_code, result.error_message)

    bundle_path = Path(result.bundle_path)

    mandates = json.loads((bundle_path / "mandates.json").read_text(encoding="utf-8"))
    assert mandates["mandate_schema_version"] == "1.0"
    assert mandates["mandates"], "mandates.json must not be empty for IRCS v1 bundles"

    assert {
        "mandate_id": "report_create:pre",
        "endpoint_sig": "POST /reports",
        "phase": "pre",
        "allowed_roles": ["user"],
    } in mandates["mandates"]

    autonomy = json.loads((bundle_path / "autonomy.json").read_text(encoding="utf-8"))
    assert autonomy["autonomy_schema_version"] == "1.0"
    assert autonomy["rules"], "autonomy.json must not be empty for IRCS v1 bundles"

    assert {
        "rule_id": "report_create:pre",
        "endpoint_sig": "POST /reports",
        "phase": "pre",
        "required_level": 0,
    } in autonomy["rules"]

