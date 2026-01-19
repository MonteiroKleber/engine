"""Tests for IRCS v1 → Bundle compilation (Etapa 2.2).

Tests the canonical compilation path:
    DSL v1.2.2 → IRCS v1 → ParsedIDL → Emitters → Bundle
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from engine.idl_dsl import parse_dsl
from engine.ise import (
    compile_from_ircs,
    compile_from_ircs_file,
    ircs_to_parsed_idl,
    IRCSAdapterError,
)
from engine.ise.manifest import sha256_str


# Finance DSL v1.2.2 (canonical example)
FINANCE_DSL = '''
system FinancePilot {
  name: "Finance Pilot"
  description: "Governed finance department with approvals, SoD and hard invariants."
  version: 1.0.0
  domain: "finance"
  owner: "Libervia"
  contact: "ops@libervia.xyz"
  tenancy: multi
}

actors {
  human operator {
    name: "Operator"
    description: "Creates and submits expenses."
    authentication: oauth2
    permissions: [finance.expense.create, finance.expense.read, finance.expense.submit]
  }

  human manager {
    name: "Manager"
    description: "Approves expenses under policy constraints."
    authentication: oauth2
    permissions: [finance.expense.read, finance.expense.approve, finance.expense.transition]
  }

  human controller {
    name: "Controller"
    description: "Second approver / financial control."
    authentication: oauth2
    permissions: [finance.expense.read, finance.expense.approve, finance.expense.transition]
  }

  system runtime {
    name: "Runtime"
    description: "Institutional runtime actor."
    authentication: token
    permissions: [runtime.bundle.load, runtime.proof.snapshot, runtime.safe_mode.enter]
  }
}

entities {
  entity Expense {
    storage {
      tenant_field: tenant_id
      version_field: version
    }

    field id: uuid required unique
    field tenant_id: uuid required indexed
    field amount: decimal required min(0)
    field currency: string required
    field description: text required
    field created_by: uuid required indexed
    field created_at: datetime required
    field state: string required indexed
    field version: int required default(1)
  }
}

policy_context {
  field jurisdiction: string required
  field risk_level: string default("low")
  field sanctions_hit: bool default(false)
}

invariants {
  invariant NoNegativeAmount {
    applies_to: Expense
    when: always
    assert: Expense.amount >= 0
    severity: critical
    message: "Expense amount cannot be negative."
  }
}

separation_of_duties {
  rule NoSelfApproval {
    on: Expense
    forbid: Approve when actor.id == Expense.created_by
    severity: critical
    message: "Creator cannot approve their own expense."
  }

  rule NoSubmitterApproval {
    on: Expense
    forbid: Approve when actor.id in history("Submit").actors
    severity: critical
    message: "Submitter cannot approve."
  }
}

workflows {
  workflow ExpenseFlow on Expense {
    state Draft { initial: true }
    state PendingApproval
    state Approved { terminal: true }
    state Rejected { terminal: true }

    transition Submit: Draft -> PendingApproval {
      guard: context.sanctions_hit == false
      effects: [set_state("PendingApproval"), bump_version(1)]
    }

    transition Approve: PendingApproval -> Approved {
      guard: context.risk_level != "high"
      approvals: {
        quorum: 2
        roles: [manager, controller]
        distinct_actors: true
        expires_in: 48h
      }
      effects: [set_state("Approved"), bump_version(1)]
    }

    transition Reject: PendingApproval -> Rejected {
      approvals: {
        quorum: 1
        roles: [controller]
        distinct_actors: true
        expires_in: 48h
      }
      effects: [set_state("Rejected"), bump_version(1)]
    }
  }
}

operations {
  api {
    endpoint expense_create {
      method: POST
      path: "/finance/expenses"
      request: Expense
      response: Expense
      permission: finance.expense.create
      scope: tenant
      idempotency: required
      errors: [400, 401, 403]
      bind: { entity: Expense, kind: create }
    }

    endpoint expense_get {
      method: GET
      path: "/finance/expenses/{id}"
      request: void
      response: Expense
      permission: finance.expense.read
      scope: tenant
      idempotency: none
      errors: [401, 403, 404]
      bind: { entity: Expense, kind: read }
    }

    endpoint expense_submit {
      method: POST
      path: "/finance/expenses/{id}/transitions/submit"
      request: void
      response: any
      permission: finance.expense.submit
      scope: tenant
      idempotency: required
      errors: [401, 403, 409]
      bind: { entity: Expense, kind: transition, workflow: ExpenseFlow, transition: Submit }
    }

    endpoint expense_approve {
      method: POST
      path: "/finance/expenses/{id}/approvals/approve"
      request: void
      response: any
      permission: finance.expense.approve
      scope: tenant
      idempotency: required
      errors: [401, 403, 409]
      bind: { entity: Expense, kind: approval, workflow: ExpenseFlow, transition: Approve, decision: "approve" }
    }
  }
}
'''


class TestIRCSAdapter:
    """Tests for IRCS v1 → ParsedIDL adapter."""

    def test_ircs_to_parsed_idl_basic(self):
        """IRCS v1 converts to ParsedIDL successfully."""
        # Parse DSL to IRCS v1
        ir = parse_dsl(FINANCE_DSL)

        # Convert to ParsedIDL
        parsed = ircs_to_parsed_idl(ir)

        assert parsed.system_name == "Finance Pilot"
        assert parsed.idl_version == "1.1"

    def test_ircs_actors_converted(self):
        """IRCS v1 actors are converted to IDLActor."""
        ir = parse_dsl(FINANCE_DSL)
        parsed = ircs_to_parsed_idl(ir)

        # Check actors
        assert len(parsed.actors) == 4
        actor_roles = [a.role for a in parsed.actors]
        assert "operator" in actor_roles
        assert "manager" in actor_roles
        assert "controller" in actor_roles
        assert "runtime" in actor_roles

        # Check operator permissions
        operator = next(a for a in parsed.actors if a.role == "operator")
        assert operator.auth_method == "oauth2"
        assert len(operator.permissions) > 0

    def test_ircs_entities_converted(self):
        """IRCS v1 entities are converted to IDLEntity."""
        ir = parse_dsl(FINANCE_DSL)
        parsed = ircs_to_parsed_idl(ir)

        # Check entities
        assert len(parsed.entities) == 1
        expense = parsed.entities[0]
        assert expense.name == "Expense"
        assert expense.entity_type == "expense"

        # Check fields
        field_names = [f.name for f in expense.fields]
        assert "id" in field_names
        assert "amount" in field_names
        assert "currency" in field_names

    def test_ircs_usecases_generated_from_operations(self):
        """Usecases are generated from IRCS v1 operations."""
        ir = parse_dsl(FINANCE_DSL)
        parsed = ircs_to_parsed_idl(ir)

        # Check usecases
        assert len(parsed.usecases) > 0
        uc_names = [u.name for u in parsed.usecases]
        assert "expense_create" in uc_names
        assert "expense_approve" in uc_names

        # Check approval detection
        approve_uc = next(u for u in parsed.usecases if u.name == "expense_approve")
        assert approve_uc.has_approval is True
        assert approve_uc.approval_role is not None

    def test_ircs_invalid_version_fails(self):
        """Invalid ir_version raises error."""
        ir = {"ir_version": "invalid.v0"}

        with pytest.raises(IRCSAdapterError) as exc:
            ircs_to_parsed_idl(ir)

        assert "ircs.v1" in exc.value.message


class TestCompileFromIRCS:
    """Tests for compile_from_ircs function."""

    def test_compile_from_ircs_success(self):
        """IRCS v1 compiles to bundle successfully."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-test", tmpdir)

            assert result.success is True
            assert result.bundle_path is not None
            assert result.bundle_name == "finance-test"

            # Check bundle exists
            bundle_path = Path(result.bundle_path)
            assert bundle_path.exists()

    def test_compile_from_ircs_creates_required_contracts(self):
        """Bundle contains all required contracts."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-test", tmpdir)

            assert result.success is True

            # Check required contracts
            required = [
                "rbac.json",
                "approvals.json",
                "workflows.json",
                "sod.json",
                "invariants.json",
                "policies.json",
                "mandates.json",
                "autonomy.json",
                "bundle.manifest.json",
                "contract_ledger.json",
            ]

            for contract in required:
                assert contract in result.contracts, f"Missing contract: {contract}"

    def test_compile_from_ircs_manifest_format(self):
        """Bundle manifest follows loader ABI."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-test", tmpdir)

            assert result.success is True

            # Load manifest
            manifest_path = Path(result.bundle_path) / "bundle.manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)

            # Check manifest structure
            assert "name" in manifest
            assert "version" in manifest
            assert "contracts" in manifest
            assert isinstance(manifest["contracts"], list)

            # Check contract format
            for contract in manifest["contracts"]:
                assert "file" in contract
                assert "sha256" in contract
                assert "required" in contract
                assert contract["sha256"].startswith("SHA256:")

    def test_compile_from_ircs_ledger_has_source_idl_sha256(self):
        """Contract ledger preserves source_idl_sha256."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-test", tmpdir)

            assert result.success is True

            # Load contract ledger
            ledger_path = Path(result.bundle_path) / "contract_ledger.json"
            with open(ledger_path) as f:
                ledger = json.load(f)

            # Check source_idl_sha256 is preserved
            assert "source_idl_sha256" in ledger
            assert len(ledger["source_idl_sha256"]) == 64  # SHA256 hex

            # Verify it matches IRCS v1 source_idl_sha256
            assert ledger["source_idl_sha256"] == ir["source_idl_sha256"]

    def test_compile_from_ircs_hashes_correct(self):
        """Contract hashes in manifest are correct."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-test", tmpdir)

            assert result.success is True
            bundle_path = Path(result.bundle_path)

            # Load manifest
            manifest_path = bundle_path / "bundle.manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)

            # Verify each contract hash
            for contract in manifest["contracts"]:
                contract_file = contract["file"]
                expected_hash = contract["sha256"].replace("SHA256:", "")

                # Skip manifest itself (not hashed against itself)
                if contract_file == "bundle.manifest.json":
                    continue

                contract_path = bundle_path / contract_file
                if contract_path.exists():
                    with open(contract_path) as f:
                        content = f.read()
                    actual_hash = sha256_str(content)
                    assert actual_hash == expected_hash, f"Hash mismatch for {contract_file}"


class TestCompileFromIRCSFile:
    """Tests for compile_from_ircs_file function."""

    def test_compile_from_ircs_file_success(self):
        """Compile from IRCS v1 JSON file."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write IR to file
            ir_path = Path(tmpdir) / "finance.ir.json"
            with open(ir_path, "w") as f:
                json.dump(ir, f, indent=2)

            # Compile from file
            result = compile_from_ircs_file(
                str(ir_path),
                "finance-from-file",
                tmpdir,
            )

            assert result.success is True
            assert result.bundle_name == "finance-from-file"

    def test_compile_from_ircs_file_not_found(self):
        """File not found returns error."""
        result = compile_from_ircs_file(
            "/nonexistent/path.json",
            "test-bundle",
            "/tmp",
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()


class TestDeterminism:
    """Tests for deterministic output."""

    def test_same_input_same_output(self):
        """Same IRCS v1 produces same bundle."""
        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result1 = compile_from_ircs(ir, "bundle1", tmpdir)
            result2 = compile_from_ircs(ir, "bundle2", tmpdir)

            assert result1.success is True
            assert result2.success is True

            # Compare contract hashes (excluding timestamp-dependent files)
            for contract in ["rbac.json", "workflows.json", "approvals.json", "sod.json"]:
                if contract in result1.sha256s and contract in result2.sha256s:
                    assert result1.sha256s[contract] == result2.sha256s[contract], \
                        f"Determinism failure for {contract}"


class TestLoaderCompatibility:
    """Tests for loader compatibility."""

    def setup_method(self):
        """Reset runtime state before each test."""
        from engine.core.runtime_state import runtime_state
        runtime_state.set_active()

    def teardown_method(self):
        """Reset runtime state after each test."""
        from engine.core.runtime_state import runtime_state
        runtime_state.set_active()

    def test_bundle_loads_as_active(self):
        """Bundle generated from IRCS v1 loads as ACTIVE."""
        from engine.loader.load_bundle import load_bundle
        from engine.core.runtime_state import runtime_state

        ir = parse_dsl(FINANCE_DSL)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-load-test", tmpdir)
            assert result.success is True

            bundle_path = Path(result.bundle_path)

            # Load the bundle
            manifest = load_bundle(bundle_path)

            # Should not enter SAFE_MODE
            assert manifest is not None
            assert runtime_state.is_safe_mode() is False
            assert runtime_state.mode == "ACTIVE"


class TestE2E:
    """End-to-end tests."""

    def test_dsl_to_ircs_to_bundle(self):
        """Full pipeline: DSL → IRCS v1 → Bundle."""
        # 1. Parse DSL to IRCS v1
        ir = parse_dsl(FINANCE_DSL)

        assert ir["ir_version"] == "ircs.v1"
        assert ir["source_idl_version"] == "idl.v1.2.2"
        assert "source_idl_sha256" in ir

        # 2. Compile IRCS v1 to bundle
        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_from_ircs(ir, "finance-e2e", tmpdir)

            assert result.success is True

            # 3. Verify bundle structure
            bundle_path = Path(result.bundle_path)

            # Check all required files exist
            required_files = [
                "bundle.manifest.json",
                "contract_ledger.json",
                "rbac.json",
                "approvals.json",
                "workflows.json",
                "sod.json",
                "invariants.json",
                "policies.json",
                "mandates.json",
                "autonomy.json",
            ]

            for filename in required_files:
                filepath = bundle_path / filename
                assert filepath.exists(), f"Missing: {filename}"

            # 4. Verify source_idl_sha256 chain
            with open(bundle_path / "contract_ledger.json") as f:
                ledger = json.load(f)

            assert ledger["source_idl_sha256"] == ir["source_idl_sha256"]
