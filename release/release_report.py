"""Release Report Generator - Gera relatorios de release em JSON e Markdown.

Gera:
- Release Report (JSON/MD)
- Caminho do repo gerado
- Comandos (docker compose up/down)
- Resumo do sistema

Este e o bundle industrial final do motor.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_config
from version import __version__, get_version_info


@dataclass
class ReleaseReport:
    """Relatorio completo de um release."""

    # Identificacao
    project: str
    version: str
    timestamp: str
    engine_version: str

    # Caminhos
    repo_path: str
    store_path: str

    # Status
    success: bool
    final_status: str

    # Artefatos
    srs_version: int = 0
    ir_version: int = 0
    oas_version: int = 0
    rbac_version: int = 0
    plan_version: int = 0

    # Metricas
    requirements_count: int = 0
    entities_count: int = 0
    operations_count: int = 0
    tasks_count: int = 0
    patch_count: int = 0

    # Build
    build_ok: bool = False
    fix_attempts: int = 0
    fixes_applied: int = 0

    # Release
    docker_compose_ok: bool = False
    services_running: List[str] = field(default_factory=list)
    smoke_ok: bool = False
    smoke_passed: int = 0
    smoke_failed: int = 0

    # Checklist
    checklist_passed: bool = False
    checklist_items: int = 0
    checklist_failures: List[str] = field(default_factory=list)

    # Erros
    errors: List[str] = field(default_factory=list)

    # Duracao
    duration_ms: float = 0.0
    # Readiness evidence
    readiness_fingerprint: str = ""
    readiness_fingerprint_file: str = ""
    runtime_evidence_dir: str = ""

    # DB volume isolation
    db_volume_name: str = ""

    # Execution ID
    execution_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "project": self.project,
            "version": self.version,
            "timestamp": self.timestamp,
            "engine_version": self.engine_version,
            "execution_id": self.execution_id,
            "repo_path": self.repo_path,
            "store_path": self.store_path,
            "success": self.success,
            "final_status": self.final_status,
            "artifacts": {
                "srs_version": self.srs_version,
                "ir_version": self.ir_version,
                "oas_version": self.oas_version,
                "rbac_version": self.rbac_version,
                "plan_version": self.plan_version,
            },
            "metrics": {
                "requirements_count": self.requirements_count,
                "entities_count": self.entities_count,
                "operations_count": self.operations_count,
                "tasks_count": self.tasks_count,
                "patch_count": self.patch_count,
            },
            "build": {
                "build_ok": self.build_ok,
                "fix_attempts": self.fix_attempts,
                "fixes_applied": self.fixes_applied,
            },
            "release": {
                "docker_compose_ok": self.docker_compose_ok,
                "services_running": self.services_running,
                "smoke_ok": self.smoke_ok,
                "smoke_passed": self.smoke_passed,
                "smoke_failed": self.smoke_failed,
                "readiness_fingerprint": self.readiness_fingerprint,
                "readiness_fingerprint_file": self.readiness_fingerprint_file,
                "runtime_evidence_dir": self.runtime_evidence_dir,
                "db_volume_name": self.db_volume_name,
            },
            "checklist": {
                "passed": self.checklist_passed,
                "total_items": self.checklist_items,
                "failures": self.checklist_failures,
            },
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "commands": self.get_commands(),
            "readiness_fingerprint": self.readiness_fingerprint,
            "readiness_fingerprint_file": self.readiness_fingerprint_file,
            "runtime_evidence_dir": self.runtime_evidence_dir,
        }

    def get_commands(self) -> Dict[str, str]:
        """Retorna comandos para operar o sistema."""
        return {
            "start": f"cd {self.repo_path} && docker compose up -d",
            "stop": f"cd {self.repo_path} && docker compose down",
            "logs": f"cd {self.repo_path} && docker compose logs -f",
            "status": f"cd {self.repo_path} && docker compose ps",
            "restart": f"cd {self.repo_path} && docker compose restart",
        }

    def to_json(self, indent: int = 2) -> str:
        """Converte para JSON formatado."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Converte para Markdown formatado."""
        status_emoji = "✅" if self.success else "❌"
        lines = [
            f"# Release Report: {self.project}",
            "",
            f"**Status:** {status_emoji} {self.final_status.upper()}",
            f"**Engine:** Bazari Engine v{self.engine_version}",
            f"**Generated:** {self.timestamp}",
            "",
            "---",
            "",
            "## System Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Requirements | {self.requirements_count} |",
            f"| Entities | {self.entities_count} |",
            f"| API Operations | {self.operations_count} |",
            f"| Tasks | {self.tasks_count} |",
            f"| Patches | {self.patch_count} |",
            "",
            "## Artifacts",
            "",
            f"| Artifact | Version |",
            f"|----------|---------|",
            f"| SRS | v{self.srs_version} |",
            f"| IR | v{self.ir_version} |",
            f"| OpenAPI | v{self.oas_version} |",
            f"| RBAC | v{self.rbac_version} |",
            f"| PLAN | v{self.plan_version} |",
            "",
            "## Build Status",
            "",
            f"- **Build:** {'✅ OK' if self.build_ok else '❌ FAILED'}",
            f"- **Fix Attempts:** {self.fix_attempts}",
            f"- **Fixes Applied:** {self.fixes_applied}",
            "",
            "## Release Status",
            "",
            f"- **Docker Compose:** {'✅ OK' if self.docker_compose_ok else '❌ FAILED'}",
            f"- **Services:** {', '.join(self.services_running) if self.services_running else 'None'}",
            f"- **Smoke Tests:** {'✅ OK' if self.smoke_ok else '❌ FAILED'} ({self.smoke_passed}/{self.smoke_passed + self.smoke_failed})",
            f"- **DB Volume:** `{self.db_volume_name}`" if self.db_volume_name else "",
            "",
            "## Paths",
            "",
            f"- **Repository:** `{self.repo_path}`",
            f"- **Store:** `{self.store_path}`",
            "",
            "## Commands",
            "",
            "```bash",
            f"# Start services",
            f"cd {self.repo_path} && docker compose up -d",
            "",
            f"# Stop services",
            f"cd {self.repo_path} && docker compose down",
            "",
            f"# View logs",
            f"cd {self.repo_path} && docker compose logs -f",
            "",
            f"# Check status",
            f"cd {self.repo_path} && docker compose ps",
            "```",
            "",
        ]

        if self.errors:
            lines.extend([
                "## Errors",
                "",
            ])
            for error in self.errors[:5]:
                lines.append(f"- {error}")
            lines.append("")

        lines.extend([
            "---",
            "",
            f"*Generated by Bazari Engine v{self.engine_version}*",
            f"*Duration: {self.duration_ms:.2f}ms*",
        ])

        return "\n".join(lines)

    def save(self, output_dir: Path) -> Dict[str, str]:
        """Salva o relatorio em JSON e Markdown.

        Args:
            output_dir: Diretorio de saida

        Returns:
            Dict com caminhos dos arquivos salvos
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Salvar JSON
        json_path = output_dir / f"release_report_{timestamp}.json"
        json_path.write_text(self.to_json())

        # Salvar Markdown
        md_path = output_dir / f"release_report_{timestamp}.md"
        md_path.write_text(self.to_markdown())

        return {
            "json": str(json_path),
            "markdown": str(md_path),
        }


class ReleaseReportGenerator:
    """Gerador de Release Reports.

    Gera relatorios completos a partir do resultado de um run_release().
    """

    def __init__(
        self,
        store_root: Optional[str] = None,
        generated_root: Optional[str] = None,
    ):
        """Inicializa o gerador.

        Args:
            store_root: Diretorio raiz do artifacts store (from config if None)
            generated_root: Diretorio raiz dos projetos gerados (from config if None)
        """
        config = get_config()
        self.store_root = Path(store_root or config.store_root)
        self.generated_root = Path(generated_root or config.generated_root)

    def _compute_db_volume_name(self, execution_id: Optional[str]) -> str:
        """Computa o nome do volume DB baseado no execution_id.

        Args:
            execution_id: ID de execução (ex: petclinic_abc123)

        Returns:
            Nome do volume: postgres_data_<exec_id> ou postgres_data se sem exec_id
        """
        if execution_id:
            return f"postgres_data_{execution_id}"
        return "postgres_data"

    def generate(
        self,
        project: str,
        run_result: Dict[str, Any],
        checklist_result: Optional[Dict[str, Any]] = None,
    ) -> ReleaseReport:
        """Gera um ReleaseReport a partir do resultado de run_release().

        Args:
            project: Nome do projeto
            run_result: Resultado do run_release() (dict ou RunResult.to_dict())
            checklist_result: Resultado do ReleaseChecklist (opcional)

        Returns:
            ReleaseReport completo
        """
        # Extrair dados do run_result
        result = run_result if isinstance(run_result, dict) else run_result

        report = ReleaseReport(
            project=project,
            version="1.0.0",  # Primeira versao do release
            timestamp=datetime.now().isoformat(),
            engine_version=__version__,
            repo_path=result.get("repo_path", str(self.generated_root / project)),
            store_path=str(self.store_root / project),
            success=result.get("success", False),
            final_status=result.get("final_status", "unknown"),
            # Artefatos
            srs_version=result.get("srs_version", 0) or 0,
            ir_version=result.get("ir_version", 0) or 0,
            oas_version=result.get("oas_version", 0) or 0,
            rbac_version=result.get("rbac_version", 0) or 0,
            plan_version=result.get("plan_version", 0) or 0,
            # Metricas
            requirements_count=result.get("requirements_count", 0),
            entities_count=result.get("entities_count", 0),
            operations_count=result.get("operations_count", 0),
            tasks_count=result.get("tasks_count", 0),
            patch_count=result.get("patch_count", 0),
            # Build
            build_ok=result.get("build_ok", False),
            fix_attempts=result.get("fix_attempts", 0),
            fixes_applied=len(result.get("fixes_applied", [])),
            # Release
            docker_compose_ok=result.get("docker_compose_ok", False),
            services_running=result.get("services_running", []),
            smoke_ok=result.get("smoke_ok", False),
            smoke_passed=result.get("smoke_passed", 0),
            smoke_failed=result.get("smoke_failed", 0),
            readiness_fingerprint=result.get("readiness_fingerprint", ""),
            readiness_fingerprint_file=result.get("readiness_fingerprint_file", ""),
            runtime_evidence_dir=result.get("runtime_evidence_dir", ""),
            # DB volume isolation
            db_volume_name=self._compute_db_volume_name(result.get("execution_id")),
            # Execution ID
            execution_id=result.get("execution_id", ""),
            # Erros
            errors=result.get("errors", []),
            duration_ms=result.get("duration_ms", 0.0),
        )

        # Adicionar dados do checklist se disponivel
        if checklist_result:
            report.checklist_passed = checklist_result.get("passed", False)
            report.checklist_items = checklist_result.get("total_items", 0)
            report.checklist_failures = checklist_result.get("blocking_failures", [])

        return report

    def generate_and_save(
        self,
        project: str,
        run_result: Dict[str, Any],
        checklist_result: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Gera e salva o ReleaseReport.

        Args:
            project: Nome do projeto
            run_result: Resultado do run_release()
            checklist_result: Resultado do ReleaseChecklist (opcional)
            output_dir: Diretorio de saida (default: store/project/releases)

        Returns:
            Dict com report e caminhos dos arquivos
        """
        report = self.generate(project, run_result, checklist_result)

        # Determinar diretorio de saida
        if output_dir is None:
            output_dir = self.store_root / project / "releases"

        # Salvar arquivos
        paths = report.save(output_dir)

        return {
            "report": report.to_dict(),
            "files": paths,
        }


def generate_release_report(
    project: str,
    run_result: Dict[str, Any],
    checklist_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Funcao de conveniencia para gerar release report.

    Args:
        project: Nome do projeto
        run_result: Resultado do run_release()
        checklist_result: Resultado do ReleaseChecklist (opcional)

    Returns:
        Dict com report completo
    """
    generator = ReleaseReportGenerator()
    report = generator.generate(project, run_result, checklist_result)
    return report.to_dict()
