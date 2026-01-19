"""Tests for Legacy Bridge CLI (Etapa 2.7).

These tests verify that:
1. CLI commands work correctly
2. Output is formatted properly
3. Exit codes are correct
"""

import json
import os
import sys
import pytest
from pathlib import Path
from io import StringIO
from unittest.mock import patch

from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers
from engine.legacy_bridge.__main__ import main
from engine.legacy_bridge.models import SourceFormat


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    reset_institution_ledgers()
    yield
    reset_institution_ledgers()


@pytest.fixture
def institution_id() -> str:
    """Test institution ID."""
    return "test-inst-cli-001"


@pytest.fixture
def test_csv_file(tmp_path, monkeypatch, institution_id) -> str:
    """Create a test CSV file in the institution root."""
    inst_root = get_institution_root(institution_id)
    inst_root.mkdir(parents=True, exist_ok=True)

    csv_path = inst_root / "exports" / "expense_report.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("id,amount,date,description\n1,100.00,2024-01-15,Office supplies\n2,250.00,2024-01-16,Travel\n")

    return "exports/expense_report.csv"


class TestRegisterCommand:
    """Test the register command."""

    def test_register_command_success(self, institution_id, test_csv_file, capsys):
        """Register command succeeds with valid input."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
                "--name", "Expense Report 2024",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Asset registered" in captured.out
        assert "expense-report-2024" in captured.out
        assert "SHA256:" in captured.out

    def test_register_command_with_format_auto_schema(self, institution_id, test_csv_file, capsys):
        """Register command extracts schema for CSV."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Schema:" in captured.out

    def test_register_command_invalid_path_fails(self, institution_id, capsys):
        """Register command fails with absolute path."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "invalid-asset",
                "--path", "/etc/passwd",
                "--format", "raw",
            ],
        ):
            exit_code = main()

        assert exit_code == 1

        captured = capsys.readouterr()
        assert "Error" in captured.err or "absolute" in captured.err.lower()

    def test_register_command_nonexistent_file_fails(self, institution_id, capsys):
        """Register command fails with non-existent file."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "missing-asset",
                "--path", "exports/nonexistent.csv",
                "--format", "csv",
            ],
        ):
            exit_code = main()

        assert exit_code == 1


class TestVerifyCommand:
    """Test the verify command."""

    def test_verify_command_match(self, institution_id, test_csv_file, capsys):
        """Verify command returns success for unchanged asset."""
        # First register
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            main()

        # Then verify
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "verify",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "MATCH" in captured.out

    def test_verify_command_drift(self, institution_id, test_csv_file, tmp_path, capsys):
        """Verify command returns failure for modified asset."""
        # First register
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            main()

        # Modify file
        inst_root = get_institution_root(institution_id)
        csv_path = inst_root / "exports" / "expense_report.csv"
        csv_path.write_text("MODIFIED CONTENT\n")

        # Then verify
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "verify",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
            ],
        ):
            exit_code = main()

        assert exit_code == 1

        captured = capsys.readouterr()
        assert "DRIFT_DETECTED" in captured.out

    def test_verify_command_not_found(self, institution_id, capsys):
        """Verify command returns failure for unknown asset."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "verify",
                "--institution", institution_id,
                "--asset-id", "nonexistent-asset",
            ],
        ):
            exit_code = main()

        assert exit_code == 1

        captured = capsys.readouterr()
        assert "ERROR" in captured.out or "not found" in captured.out.lower()


class TestListCommand:
    """Test the list command."""

    def test_list_command_empty(self, institution_id, capsys):
        """List command shows no assets when registry is empty."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "list",
                "--institution", institution_id,
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "No assets" in captured.out

    def test_list_command_with_assets(self, institution_id, test_csv_file, capsys):
        """List command shows registered assets."""
        # Register an asset
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
                "--name", "Expense Report 2024",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            main()

        # List
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "list",
                "--institution", institution_id,
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "expense-report-2024" in captured.out
        assert "Expense Report 2024" in captured.out


class TestVerifyAllCommand:
    """Test the verify-all command."""

    def test_verify_all_command_empty(self, institution_id, capsys):
        """verify-all with no assets returns success."""
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "verify-all",
                "--institution", institution_id,
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "No assets" in captured.out

    def test_verify_all_command_all_ok(self, institution_id, test_csv_file, tmp_path, capsys):
        """verify-all returns success when all assets are OK."""
        # Create another file
        inst_root = get_institution_root(institution_id)
        (inst_root / "exports" / "other.csv").write_text("a,b\n1,2\n")

        # Register assets
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "asset-1",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            main()

        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "asset-2",
                "--path", "exports/other.csv",
                "--format", "csv",
            ],
        ):
            main()

        # Verify all
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "verify-all",
                "--institution", institution_id,
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "2 assets OK" in captured.out

    def test_verify_all_command_with_drift(self, institution_id, test_csv_file, tmp_path, capsys):
        """verify-all returns failure when drift is detected."""
        # Register asset
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "register",
                "--institution", institution_id,
                "--asset-id", "expense-report-2024",
                "--path", test_csv_file,
                "--format", "csv",
            ],
        ):
            main()

        # Modify file
        inst_root = get_institution_root(institution_id)
        csv_path = inst_root / "exports" / "expense_report.csv"
        csv_path.write_text("MODIFIED\n")

        # Verify all
        with patch.object(
            sys,
            "argv",
            [
                "legacy_bridge",
                "verify-all",
                "--institution", institution_id,
            ],
        ):
            exit_code = main()

        assert exit_code == 1

        captured = capsys.readouterr()
        assert "drift detected" in captured.out.lower()
