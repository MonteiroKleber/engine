"""Verifica que o release_report inclui os campos de readiness proof."""

from release.release_report import ReleaseReportGenerator


def test_release_report_contains_readiness_fields(tmp_path):
    generator = ReleaseReportGenerator(store_root=str(tmp_path / "store"), generated_root=str(tmp_path / "gen"))

    run_result = {
        "repo_path": "/path/to/repo",
        "success": False,
        "final_status": "SMOKE_FAILED",
        "readiness_fingerprint": "DCV_FINGERPRINT_20260105_B",
        "readiness_fingerprint_file": "/path/to/repo/.engine_readiness_fingerprint.txt",
        "runtime_evidence_dir": "/path/to/repo/.engine_evidence",
    }

    report = generator.generate("proj", run_result)
    data = report.to_dict()

    assert data["readiness_fingerprint"] == "DCV_FINGERPRINT_20260105_B"
    assert data["readiness_fingerprint_file"].endswith(".engine_readiness_fingerprint.txt")
    assert data["runtime_evidence_dir"].endswith(".engine_evidence")
