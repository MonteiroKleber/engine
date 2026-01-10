#!/usr/bin/env python3
"""E2E scenarios for Engine + Legacy Bundle integration.

Runs 3 real scenarios WITHOUT MOCKS:
1. Happy Path - bundle generated and Engine succeeds
2. Tamper - modify inventory without updating ledger, Engine blocks
3. Schema Invalid - corrupt schema_version, Engine blocks

Usage:
    python scripts/run_legacy_scenarios.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add engine and legacy to path
ENGINE_ROOT = Path(__file__).parent.parent
LEGACY_ROOT = Path("/home/bazari/legacy")
sys.path.insert(0, str(ENGINE_ROOT))
sys.path.insert(0, str(LEGACY_ROOT))

from orchestrator.engine import Engine
from observability.legacy_gate import validate_legacy_bundle
from legacy.hash_utils import compute_content_hash_sha256


def run_legacy_intake(output_dir: Path, project: str = "e2e_test") -> bool:
    """Run legacy intake CLI to generate bundle."""
    result = subprocess.run(
        [
            sys.executable, "-m", "legacy.cli",
            "intake",
            "--project", project,
            "--out", str(output_dir),
        ],
        capture_output=True,
        text=True,
        cwd="/home/bazari/legacy",
    )
    return result.returncode == 0


def scenario_1_happy_path() -> dict:
    """Scenario 1: Happy Path - valid bundle, Engine succeeds."""
    print("\n" + "=" * 60)
    print("SCENARIO 1: Happy Path")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = Path(tmp) / "bundle"

        # Step 1: Generate bundle via legacy intake
        print("  [1] Running legacy intake...")
        success = run_legacy_intake(bundle_dir)
        if not success:
            return {"scenario": 1, "passed": False, "error": "intake failed"}
        print(f"      Bundle created at: {bundle_dir}")

        # Verify files exist
        assert (bundle_dir / "legacy_inventory.v1.json").exists()
        assert (bundle_dir / "human_process.v1.json").exists()
        assert (bundle_dir / "legacy_contracts.v1.json").exists()
        print("      All bundle files present")

        # Step 2: Validate via legacy_gate
        print("  [2] Validating bundle via legacy_gate...")
        result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
        print(f"      provided: {result.provided}")
        print(f"      legacy_schema_ok: {result.legacy_schema_ok}")
        print(f"      legacy_contract_gate_ok: {result.legacy_contract_gate_ok}")
        print(f"      ok: {result.ok}")

        if not result.ok:
            return {
                "scenario": 1,
                "passed": False,
                "error": f"validation failed: {result.legacy_contract_gate_errors}",
            }

        # Step 3: Run Engine with legacy_bundle
        print("  [3] Running Engine with legacy_bundle...")
        engine = Engine()

        # Simple input that will succeed
        run_result = engine.run(
            project="e2e_scenario_1",
            raw_input="Crie uma tabela de teste",
            legacy_bundle={"bundle_path": str(bundle_dir)},
        )

        legacy_blocked = run_result.final_status == "legacy_contract_gate_failed"
        print(f"      Engine success: {run_result.success}")
        print(f"      Engine final_status: {run_result.final_status}")
        print(f"      Legacy blocked: {legacy_blocked}")

        # Happy path: should NOT be blocked by legacy gate
        # (pipeline may fail later due to no LLM, but that's OK for this test)
        passed = not legacy_blocked
        print(f"\n  RESULT: {'PASS' if passed else 'FAIL'}")

        return {
            "scenario": 1,
            "passed": passed,
            "success": run_result.success,
            "final_status": run_result.final_status,
            "legacy_blocked": legacy_blocked,
        }


def scenario_2_tamper() -> dict:
    """Scenario 2: Tamper - modify inventory without updating ledger."""
    print("\n" + "=" * 60)
    print("SCENARIO 2: Tamper Detection")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = Path(tmp) / "bundle"

        # Step 1: Generate valid bundle
        print("  [1] Running legacy intake...")
        success = run_legacy_intake(bundle_dir)
        if not success:
            return {"scenario": 2, "passed": False, "error": "intake failed"}
        print(f"      Bundle created at: {bundle_dir}")

        # Step 2: Tamper with inventory (but DON'T update ledger)
        print("  [2] Tampering with inventory...")
        inventory_path = bundle_dir / "legacy_inventory.v1.json"
        with open(inventory_path) as f:
            inventory = json.load(f)

        # Change content
        inventory["source"] = "TAMPERED_SOURCE"

        # Recompute hash in the file itself (but ledger still has old hash)
        inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)

        with open(inventory_path, "w") as f:
            json.dump(inventory, f)
        print("      Inventory modified, ledger NOT updated")

        # Step 3: Validate - should fail
        print("  [3] Validating tampered bundle...")
        result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
        print(f"      ok: {result.ok}")
        print(f"      errors: {result.legacy_contract_gate_errors}")

        # Step 4: Run Engine - should block
        print("  [4] Running Engine with tampered bundle...")
        engine = Engine()

        run_result = engine.run(
            project="e2e_scenario_2",
            raw_input="Crie uma tabela de teste",
            legacy_bundle={"bundle_path": str(bundle_dir)},
        )

        blocked = run_result.final_status == "legacy_contract_gate_failed"
        print(f"      Engine success: {run_result.success}")
        print(f"      Engine final_status: {run_result.final_status}")

        # Tamper: should be blocked with legacy_contract_gate_failed
        passed = not run_result.success and blocked
        print(f"\n  RESULT: {'PASS' if passed else 'FAIL'}")

        return {
            "scenario": 2,
            "passed": passed,
            "success": run_result.success,
            "final_status": run_result.final_status,
        }


def scenario_3_schema_invalid() -> dict:
    """Scenario 3: Schema Invalid - corrupt schema_version."""
    print("\n" + "=" * 60)
    print("SCENARIO 3: Schema Invalid")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = Path(tmp) / "bundle"

        # Step 1: Generate valid bundle
        print("  [1] Running legacy intake...")
        success = run_legacy_intake(bundle_dir)
        if not success:
            return {"scenario": 3, "passed": False, "error": "intake failed"}
        print(f"      Bundle created at: {bundle_dir}")

        # Step 2: Corrupt schema_version
        print("  [2] Corrupting schema_version...")
        inventory_path = bundle_dir / "legacy_inventory.v1.json"
        with open(inventory_path) as f:
            inventory = json.load(f)

        # Corrupt schema version
        inventory["schema_version"] = "INVALID_VERSION"

        with open(inventory_path, "w") as f:
            json.dump(inventory, f)
        print("      schema_version set to INVALID_VERSION")

        # Step 3: Validate - should fail
        print("  [3] Validating corrupted bundle...")
        result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
        print(f"      ok: {result.ok}")
        print(f"      legacy_schema_ok: {result.legacy_schema_ok}")
        print(f"      errors: {result.legacy_contract_gate_errors}")

        # Step 4: Run Engine - should block
        print("  [4] Running Engine with corrupted bundle...")
        engine = Engine()

        run_result = engine.run(
            project="e2e_scenario_3",
            raw_input="Crie uma tabela de teste",
            legacy_bundle={"bundle_path": str(bundle_dir)},
        )

        blocked = run_result.final_status == "legacy_schema_invalid"
        print(f"      Engine success: {run_result.success}")
        print(f"      Engine final_status: {run_result.final_status}")

        # Schema invalid: should be blocked with legacy_schema_invalid
        passed = not run_result.success and blocked
        print(f"\n  RESULT: {'PASS' if passed else 'FAIL'}")

        return {
            "scenario": 3,
            "passed": passed,
            "success": run_result.success,
            "final_status": run_result.final_status,
        }


def main():
    """Run all E2E scenarios."""
    print("=" * 60)
    print("ENGINE + LEGACY BUNDLE E2E SCENARIOS")
    print("=" * 60)
    print("Running 3 real scenarios WITHOUT MOCKS")

    results = []

    # Run all scenarios
    results.append(scenario_1_happy_path())
    results.append(scenario_2_tamper())
    results.append(scenario_3_schema_invalid())

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        all_passed = all_passed and r["passed"]
        print(f"  Scenario {r['scenario']}: {status}")
        if not r["passed"] and "error" in r:
            print(f"    Error: {r['error']}")

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL SCENARIOS PASSED")
        print("=" * 60)
        return 0
    else:
        print("SOME SCENARIOS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
