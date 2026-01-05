"""Tests for release/release_report.py - Release Report Generator."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

from release.release_report import (
    ReleaseReport,
    ReleaseReportGenerator,
    generate_release_report,
)


class TestReleaseReport:
    """Tests for ReleaseReport dataclass."""

    def _create_report(self, **overrides) -> ReleaseReport:
        """Create a ReleaseReport with default values."""
        defaults = {
            "project": "test-project",
            "version": "1.0.0",
            "timestamp": "2026-01-03T10:00:00",
            "engine_version": "1.0.0",
            "repo_path": "/home/bazari/generated/test-project",
            "store_path": "/home/bazari/engine/demo_store/test-project",
            "success": True,
            "final_status": "release_ok",
            "srs_version": 1,
            "ir_version": 1,
            "oas_version": 1,
            "rbac_version": 1,
            "plan_version": 1,
            "requirements_count": 5,
            "entities_count": 3,
            "operations_count": 12,
            "tasks_count": 8,
            "patch_count": 4,
            "build_ok": True,
            "fix_attempts": 0,
            "fixes_applied": 0,
            "docker_compose_ok": True,
            "services_running": ["postgres", "backend", "frontend"],
            "smoke_ok": True,
            "smoke_passed": 5,
            "smoke_failed": 0,
            "checklist_passed": True,
            "checklist_items": 10,
            "checklist_failures": [],
            "errors": [],
            "duration_ms": 1234.56,
        }
        defaults.update(overrides)
        return ReleaseReport(**defaults)

    def test_create_release_report(self):
        """Test creating a ReleaseReport."""
        report = self._create_report()

        assert report.project == "test-project"
        assert report.version == "1.0.0"
        assert report.success is True
        assert report.final_status == "release_ok"

    def test_release_report_to_dict(self):
        """Test converting ReleaseReport to dictionary."""
        report = self._create_report()
        data = report.to_dict()

        assert data["project"] == "test-project"
        assert data["version"] == "1.0.0"
        assert data["success"] is True
        assert "artifacts" in data
        assert "metrics" in data
        assert "build" in data
        assert "release" in data
        assert "checklist" in data
        assert "commands" in data

    def test_release_report_artifacts_section(self):
        """Test artifacts section in to_dict."""
        report = self._create_report(
            srs_version=2,
            ir_version=3,
            oas_version=4,
            rbac_version=5,
            plan_version=6,
        )
        data = report.to_dict()

        artifacts = data["artifacts"]
        assert artifacts["srs_version"] == 2
        assert artifacts["ir_version"] == 3
        assert artifacts["oas_version"] == 4
        assert artifacts["rbac_version"] == 5
        assert artifacts["plan_version"] == 6

    def test_release_report_metrics_section(self):
        """Test metrics section in to_dict."""
        report = self._create_report(
            requirements_count=10,
            entities_count=5,
            operations_count=20,
            tasks_count=15,
            patch_count=8,
        )
        data = report.to_dict()

        metrics = data["metrics"]
        assert metrics["requirements_count"] == 10
        assert metrics["entities_count"] == 5
        assert metrics["operations_count"] == 20
        assert metrics["tasks_count"] == 15
        assert metrics["patch_count"] == 8

    def test_release_report_build_section(self):
        """Test build section in to_dict."""
        report = self._create_report(
            build_ok=True,
            fix_attempts=2,
            fixes_applied=1,
        )
        data = report.to_dict()

        build = data["build"]
        assert build["build_ok"] is True
        assert build["fix_attempts"] == 2
        assert build["fixes_applied"] == 1

    def test_release_report_release_section(self):
        """Test release section in to_dict."""
        report = self._create_report(
            docker_compose_ok=True,
            services_running=["postgres", "backend"],
            smoke_ok=True,
            smoke_passed=10,
            smoke_failed=2,
        )
        data = report.to_dict()

        release = data["release"]
        assert release["docker_compose_ok"] is True
        assert release["services_running"] == ["postgres", "backend"]
        assert release["smoke_ok"] is True
        assert release["smoke_passed"] == 10
        assert release["smoke_failed"] == 2

    def test_release_report_checklist_section(self):
        """Test checklist section in to_dict."""
        report = self._create_report(
            checklist_passed=False,
            checklist_items=10,
            checklist_failures=["Failure 1", "Failure 2"],
        )
        data = report.to_dict()

        checklist = data["checklist"]
        assert checklist["passed"] is False
        assert checklist["total_items"] == 10
        assert checklist["failures"] == ["Failure 1", "Failure 2"]

    def test_release_report_get_commands(self):
        """Test get_commands method."""
        report = self._create_report(
            repo_path="/home/bazari/generated/myproject"
        )
        commands = report.get_commands()

        assert "start" in commands
        assert "stop" in commands
        assert "logs" in commands
        assert "status" in commands
        assert "restart" in commands

        assert "docker compose up -d" in commands["start"]
        assert "docker compose down" in commands["stop"]
        assert "docker compose logs -f" in commands["logs"]
        assert "docker compose ps" in commands["status"]
        assert "docker compose restart" in commands["restart"]

        assert "/home/bazari/generated/myproject" in commands["start"]

    def test_release_report_to_json(self):
        """Test to_json method."""
        report = self._create_report()
        json_str = report.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert data["project"] == "test-project"
        assert data["success"] is True

    def test_release_report_to_json_with_indent(self):
        """Test to_json with custom indent."""
        report = self._create_report()
        json_str = report.to_json(indent=4)

        # Should have 4-space indentation
        assert "    " in json_str

        # Should still be valid
        data = json.loads(json_str)
        assert data["project"] == "test-project"

    def test_release_report_to_markdown(self):
        """Test to_markdown method."""
        report = self._create_report()
        md = report.to_markdown()

        # Should contain key sections
        assert "# Release Report:" in md
        assert "test-project" in md
        assert "## System Summary" in md
        assert "## Artifacts" in md
        assert "## Build Status" in md
        assert "## Release Status" in md
        assert "## Paths" in md
        assert "## Commands" in md

    def test_release_report_markdown_success_status(self):
        """Test markdown shows success status correctly."""
        report = self._create_report(success=True, final_status="release_ok")
        md = report.to_markdown()

        assert "✅" in md
        assert "RELEASE_OK" in md

    def test_release_report_markdown_failed_status(self):
        """Test markdown shows failed status correctly."""
        report = self._create_report(success=False, final_status="build_failed")
        md = report.to_markdown()

        assert "❌" in md
        assert "BUILD_FAILED" in md

    def test_release_report_markdown_with_errors(self):
        """Test markdown includes errors section when errors exist."""
        report = self._create_report(
            success=False,
            errors=["Error 1", "Error 2", "Error 3"],
        )
        md = report.to_markdown()

        assert "## Errors" in md
        assert "Error 1" in md
        assert "Error 2" in md

    def test_release_report_markdown_limits_errors(self):
        """Test markdown limits errors to 5."""
        errors = [f"Error {i}" for i in range(10)]
        report = self._create_report(success=False, errors=errors)
        md = report.to_markdown()

        # Should include first 5
        assert "Error 0" in md
        assert "Error 4" in md

    def test_release_report_save(self):
        """Test save method creates JSON and MD files."""
        report = self._create_report()

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = report.save(tmpdir)

            assert "json" in paths
            assert "markdown" in paths

            # Files should exist
            assert Path(paths["json"]).exists()
            assert Path(paths["markdown"]).exists()

            # JSON should be valid
            json_content = Path(paths["json"]).read_text()
            data = json.loads(json_content)
            assert data["project"] == "test-project"

            # Markdown should have content
            md_content = Path(paths["markdown"]).read_text()
            assert "Release Report" in md_content

    def test_release_report_save_creates_directory(self):
        """Test save creates output directory if needed."""
        report = self._create_report()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "nested" / "path"
            paths = report.save(output_dir)

            assert Path(paths["json"]).exists()
            assert Path(paths["markdown"]).exists()

    def test_release_report_with_empty_services(self):
        """Test report with no services running."""
        report = self._create_report(services_running=[])
        md = report.to_markdown()

        assert "None" in md or "Services:** None" in md


class TestReleaseReportGenerator:
    """Tests for ReleaseReportGenerator class."""

    def _create_run_result(self, **overrides) -> Dict[str, Any]:
        """Create a mock run result."""
        defaults = {
            "project": "test-project",
            "success": True,
            "final_status": "release_ok",
            "repo_path": "/home/bazari/generated/test-project",
            "srs_version": 1,
            "ir_version": 1,
            "oas_version": 1,
            "rbac_version": 1,
            "plan_version": 1,
            "requirements_count": 5,
            "entities_count": 3,
            "operations_count": 12,
            "tasks_count": 8,
            "patch_count": 4,
            "build_ok": True,
            "fix_attempts": 0,
            "fixes_applied": [],
            "docker_compose_ok": True,
            "services_running": ["postgres", "backend", "frontend"],
            "smoke_ok": True,
            "smoke_passed": 5,
            "smoke_failed": 0,
            "errors": [],
            "duration_ms": 1234.56,
        }
        defaults.update(overrides)
        return defaults

    def test_create_generator(self):
        """Test creating a ReleaseReportGenerator."""
        generator = ReleaseReportGenerator()

        assert generator.store_root is not None
        assert generator.generated_root is not None

    def test_create_generator_with_custom_paths(self):
        """Test creating generator with custom paths."""
        generator = ReleaseReportGenerator(
            store_root="/custom/store",
            generated_root="/custom/generated",
        )

        assert str(generator.store_root) == "/custom/store"
        assert str(generator.generated_root) == "/custom/generated"

    def test_generate_basic_report(self):
        """Test generating a basic report."""
        generator = ReleaseReportGenerator(
            store_root="/store",
            generated_root="/generated",
        )
        run_result = self._create_run_result()

        report = generator.generate("test-project", run_result)

        assert isinstance(report, ReleaseReport)
        assert report.project == "test-project"
        assert report.success is True

    def test_generate_extracts_artifacts(self):
        """Test generator extracts artifact versions."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result(
            srs_version=2,
            ir_version=3,
            oas_version=4,
            rbac_version=5,
            plan_version=6,
        )

        report = generator.generate("test-project", run_result)

        assert report.srs_version == 2
        assert report.ir_version == 3
        assert report.oas_version == 4
        assert report.rbac_version == 5
        assert report.plan_version == 6

    def test_generate_extracts_metrics(self):
        """Test generator extracts metrics."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result(
            requirements_count=10,
            entities_count=5,
            operations_count=20,
            tasks_count=15,
            patch_count=8,
        )

        report = generator.generate("test-project", run_result)

        assert report.requirements_count == 10
        assert report.entities_count == 5
        assert report.operations_count == 20
        assert report.tasks_count == 15
        assert report.patch_count == 8

    def test_generate_extracts_build_info(self):
        """Test generator extracts build info."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result(
            build_ok=True,
            fix_attempts=2,
            fixes_applied=[{"desc": "fix1"}, {"desc": "fix2"}],
        )

        report = generator.generate("test-project", run_result)

        assert report.build_ok is True
        assert report.fix_attempts == 2
        assert report.fixes_applied == 2

    def test_generate_extracts_release_info(self):
        """Test generator extracts release info."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result(
            docker_compose_ok=True,
            services_running=["postgres", "backend"],
            smoke_ok=True,
            smoke_passed=10,
            smoke_failed=2,
        )

        report = generator.generate("test-project", run_result)

        assert report.docker_compose_ok is True
        assert report.services_running == ["postgres", "backend"]
        assert report.smoke_ok is True
        assert report.smoke_passed == 10
        assert report.smoke_failed == 2

    def test_generate_with_checklist_result(self):
        """Test generator includes checklist result."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result()
        checklist_result = {
            "passed": True,
            "total_items": 10,
            "blocking_failures": [],
        }

        report = generator.generate("test-project", run_result, checklist_result)

        assert report.checklist_passed is True
        assert report.checklist_items == 10
        assert report.checklist_failures == []

    def test_generate_with_failed_checklist(self):
        """Test generator with failed checklist."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result()
        checklist_result = {
            "passed": False,
            "total_items": 10,
            "blocking_failures": ["Missing SRS", "Build failed"],
        }

        report = generator.generate("test-project", run_result, checklist_result)

        assert report.checklist_passed is False
        assert report.checklist_failures == ["Missing SRS", "Build failed"]

    def test_generate_handles_missing_fields(self):
        """Test generator handles missing fields gracefully."""
        generator = ReleaseReportGenerator()
        run_result = {
            "success": True,
            "final_status": "ok",
        }

        report = generator.generate("test-project", run_result)

        assert report.project == "test-project"
        assert report.srs_version == 0
        assert report.build_ok is False
        assert report.services_running == []

    def test_generate_handles_none_versions(self):
        """Test generator handles None artifact versions."""
        generator = ReleaseReportGenerator()
        run_result = self._create_run_result(
            srs_version=None,
            ir_version=None,
        )

        report = generator.generate("test-project", run_result)

        assert report.srs_version == 0
        assert report.ir_version == 0

    def test_generate_and_save(self):
        """Test generate_and_save method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ReleaseReportGenerator(
                store_root=tmpdir,
                generated_root="/generated",
            )
            run_result = self._create_run_result()

            result = generator.generate_and_save(
                "test-project",
                run_result,
                output_dir=Path(tmpdir) / "releases",
            )

            assert "report" in result
            assert "files" in result
            assert result["report"]["project"] == "test-project"

            # Files should exist
            assert Path(result["files"]["json"]).exists()
            assert Path(result["files"]["markdown"]).exists()

    def test_generate_and_save_default_output_dir(self):
        """Test generate_and_save uses default output dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = ReleaseReportGenerator(
                store_root=tmpdir,
                generated_root="/generated",
            )
            run_result = self._create_run_result()

            result = generator.generate_and_save("test-project", run_result)

            # Should use store_root/project/releases
            assert "releases" in result["files"]["json"]


class TestGenerateReleaseReportFunction:
    """Tests for generate_release_report convenience function."""

    def test_generate_release_report_basic(self):
        """Test convenience function generates report."""
        run_result = {
            "success": True,
            "final_status": "release_ok",
            "repo_path": "/generated/test",
            "srs_version": 1,
            "ir_version": 1,
            "oas_version": 1,
            "rbac_version": 1,
            "plan_version": 1,
            "build_ok": True,
            "docker_compose_ok": True,
            "smoke_ok": True,
            "smoke_passed": 5,
            "smoke_failed": 0,
            "services_running": [],
            "errors": [],
        }

        report = generate_release_report("test-project", run_result)

        assert isinstance(report, dict)
        assert report["project"] == "test-project"
        assert report["success"] is True

    def test_generate_release_report_with_checklist(self):
        """Test convenience function with checklist."""
        run_result = {
            "success": True,
            "final_status": "release_ok",
        }
        checklist_result = {
            "passed": True,
            "total_items": 10,
            "blocking_failures": [],
        }

        report = generate_release_report("test-project", run_result, checklist_result)

        assert report["checklist"]["passed"] is True
        assert report["checklist"]["total_items"] == 10


class TestReleaseReportEdgeCases:
    """Edge case tests for release report."""

    def test_report_with_special_characters_in_project(self):
        """Test report handles special characters in project name."""
        report = ReleaseReport(
            project="my-project_v2.0",
            version="1.0.0",
            timestamp="2026-01-03T10:00:00",
            engine_version="1.0.0",
            repo_path="/generated/my-project_v2.0",
            store_path="/store/my-project_v2.0",
            success=True,
            final_status="ok",
        )

        json_str = report.to_json()
        data = json.loads(json_str)
        assert data["project"] == "my-project_v2.0"

    def test_report_with_unicode_in_errors(self):
        """Test report handles unicode in errors."""
        report = ReleaseReport(
            project="test",
            version="1.0.0",
            timestamp="2026-01-03T10:00:00",
            engine_version="1.0.0",
            repo_path="/generated/test",
            store_path="/store/test",
            success=False,
            final_status="failed",
            errors=["Erro: não encontrado", "Falha: índice inválido"],
        )

        json_str = report.to_json()
        data = json.loads(json_str)
        assert "não encontrado" in data["errors"][0]

    def test_report_with_long_paths(self):
        """Test report handles long file paths."""
        long_path = "/very/long/path" + "/nested" * 20 + "/project"
        report = ReleaseReport(
            project="test",
            version="1.0.0",
            timestamp="2026-01-03T10:00:00",
            engine_version="1.0.0",
            repo_path=long_path,
            store_path=long_path,
            success=True,
            final_status="ok",
        )

        commands = report.get_commands()
        assert long_path in commands["start"]

    def test_report_with_high_metrics(self):
        """Test report handles high metric values."""
        report = ReleaseReport(
            project="test",
            version="1.0.0",
            timestamp="2026-01-03T10:00:00",
            engine_version="1.0.0",
            repo_path="/generated/test",
            store_path="/store/test",
            success=True,
            final_status="ok",
            requirements_count=10000,
            entities_count=5000,
            operations_count=50000,
            tasks_count=100000,
            patch_count=25000,
        )

        data = report.to_dict()
        assert data["metrics"]["requirements_count"] == 10000
        assert data["metrics"]["operations_count"] == 50000
