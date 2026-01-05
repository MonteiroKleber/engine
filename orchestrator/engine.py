"""Engine principal de orquestração.

Integra todo o pipeline:
- Intake → SRS → IR → OAS/RBAC → PLAN
- Repo generation → Patches → Build
- Fix Loop: auto-correção de erros de build (Semana 8)
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.state_machine import StateMachine, State
from orchestrator.execution_context import ExecutionContext
from intake.normalizer import Normalizer
from intake.blueprint_classifier import BlueprintClassifier
from intake.req_analyst import RequirementsAnalyst
from validators.srs_validator import SRSValidatorGate
from validators.ir_validator import validate_ir
from validators.policy_validator import PolicyValidator
from validators.openapi_validator import validate_openapi
from validators.rbac_validator import validate_rbac
from validators.plan_validator import validate_plan
from validators.build_validator import BuildValidator, BuildComponent, BuildReport
from agents.domain_modeler import DomainModeler
from agents.contracts_agent import ContractsAgent
from agents.planner_agent import PlannerAgent
from store.artifacts_store import ArtifactsStore
from repo.repo_generator import RepoGenerator, ReleaseFailureCategory
from patch_engine.patch_engine import PatchEngine
from compilers.patch_generator_v1 import PatchGenerator
from fix_loop.fix_loop_agent import FixLoopAgent, FixLoopResult, FixAttemptStatus
from blueprints.registry import resolve_blueprint
from release.docker_compose_validator import DockerComposeValidator, DockerComposeUpResult
from release.smoke_runner import SmokeRunner, SmokeReport
from version import __version__ as ENGINE_VERSION, get_version_info

import yaml


@dataclass
class RunResult:
    """Resultado de uma execução do pipeline."""

    success: bool
    execution_id: str
    project: str
    srs_version: Optional[int] = None
    srs_path: Optional[str] = None
    ir_version: Optional[int] = None
    ir_path: Optional[str] = None
    oas_version: Optional[int] = None
    oas_path: Optional[str] = None
    rbac_version: Optional[int] = None
    rbac_path: Optional[str] = None
    plan_version: Optional[int] = None
    plan_path: Optional[str] = None
    blueprint_type: str = "generic"
    blueprint_forced_generic: bool = True  # True if FORCED_GENERIC was used
    requirements_count: int = 0
    entities_count: int = 0
    operations_count: int = 0
    tasks_count: int = 0
    srs_validation_ok: bool = False
    ir_validation_ok: bool = False
    oas_validation_ok: bool = False
    rbac_validation_ok: bool = False
    plan_validation_ok: bool = False
    policy_ok: bool = False
    contracts_policy_ok: bool = False
    plan_policy_ok: bool = False
    # Build phase fields
    repo_path: Optional[str] = None
    patch_count: int = 0
    build_ok: bool = False
    build_errors: List[str] = field(default_factory=list)
    # Fix Loop fields
    fix_attempts: int = 0
    fixes_applied: List[Dict[str, Any]] = field(default_factory=list)
    final_status: str = ""  # "success", "fixed", "failed", "fatal_error"
    fix_loop_aborted_reason: str = ""
    # Release mode fields
    docker_compose_ok: bool = False
    services_running: List[str] = field(default_factory=list)
    smoke_ok: bool = False
    smoke_passed: int = 0
    smoke_failed: int = 0
    release_mode: bool = False
    # Docker evidence fields (run log)
    docker_up_timeout_seconds: int = 300
    docker_compose_command: str = ""
    docker_stdout_tail: str = ""
    docker_stderr_tail: str = ""
    docker_ps_snapshot: str = ""
    docker_logs_backend_tail: str = ""
    docker_logs_frontend_tail: str = ""
    # Build evidence fields (run log)
    build_step_failed: str = ""
    build_stdout_tail: str = ""
    build_stderr_tail: str = ""
    build_exit_code: int = 0
    # Failed repo path
    failed_repo_path: Optional[str] = None
    # General fields
    questions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "success": self.success,
            "execution_id": self.execution_id,
            "project": self.project,
            "srs_version": self.srs_version,
            "srs_path": self.srs_path,
            "ir_version": self.ir_version,
            "ir_path": self.ir_path,
            "oas_version": self.oas_version,
            "oas_path": self.oas_path,
            "rbac_version": self.rbac_version,
            "rbac_path": self.rbac_path,
            "plan_version": self.plan_version,
            "plan_path": self.plan_path,
            "blueprint_type": self.blueprint_type,
            "blueprint_forced_generic": self.blueprint_forced_generic,
            "requirements_count": self.requirements_count,
            "entities_count": self.entities_count,
            "operations_count": self.operations_count,
            "tasks_count": self.tasks_count,
            "srs_validation_ok": self.srs_validation_ok,
            "ir_validation_ok": self.ir_validation_ok,
            "oas_validation_ok": self.oas_validation_ok,
            "rbac_validation_ok": self.rbac_validation_ok,
            "plan_validation_ok": self.plan_validation_ok,
            "policy_ok": self.policy_ok,
            "contracts_policy_ok": self.contracts_policy_ok,
            "plan_policy_ok": self.plan_policy_ok,
            "repo_path": self.repo_path,
            "patch_count": self.patch_count,
            "build_ok": self.build_ok,
            "build_errors": self.build_errors,
            "fix_attempts": self.fix_attempts,
            "fixes_applied": self.fixes_applied,
            "final_status": self.final_status,
            "fix_loop_aborted_reason": self.fix_loop_aborted_reason,
            "docker_compose_ok": self.docker_compose_ok,
            "services_running": self.services_running,
            "smoke_ok": self.smoke_ok,
            "smoke_passed": self.smoke_passed,
            "smoke_failed": self.smoke_failed,
            "release_mode": self.release_mode,
            # Docker evidence
            "docker_up_timeout_seconds": self.docker_up_timeout_seconds,
            "docker_compose_command": self.docker_compose_command,
            "docker_stdout_tail": self.docker_stdout_tail,
            "docker_stderr_tail": self.docker_stderr_tail,
            "docker_ps_snapshot": self.docker_ps_snapshot,
            "docker_logs_backend_tail": self.docker_logs_backend_tail,
            "docker_logs_frontend_tail": self.docker_logs_frontend_tail,
            # Build evidence
            "build_step_failed": self.build_step_failed,
            "build_stdout_tail": self.build_stdout_tail,
            "build_stderr_tail": self.build_stderr_tail,
            "build_exit_code": self.build_exit_code,
            # Failed repo
            "failed_repo_path": self.failed_repo_path,
            "questions": self.questions,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }

    def summary(self) -> str:
        """Retorna resumo do run."""
        lines = [
            f"{'='*50}",
            f"Run Result: {'SUCCESS' if self.success else 'FAILED'}",
            f"{'='*50}",
            f"Execution ID: {self.execution_id}",
            f"Project: {self.project}",
            f"Blueprint: {self.blueprint_type}",
            f"Requirements: {self.requirements_count}",
            f"Entities: {self.entities_count}",
            f"Operations: {self.operations_count}",
            f"Tasks: {self.tasks_count}",
            f"Patches: {self.patch_count}",
            f"SRS Validation: {'OK' if self.srs_validation_ok else 'FAILED'}",
            f"IR Validation: {'OK' if self.ir_validation_ok else 'FAILED'}",
            f"OAS Validation: {'OK' if self.oas_validation_ok else 'FAILED'}",
            f"RBAC Validation: {'OK' if self.rbac_validation_ok else 'FAILED'}",
            f"PLAN Validation: {'OK' if self.plan_validation_ok else 'FAILED'}",
            f"Policy Check: {'OK' if self.policy_ok else 'FAILED'}",
            f"Contracts Policy: {'OK' if self.contracts_policy_ok else 'FAILED'}",
            f"Plan Policy: {'OK' if self.plan_policy_ok else 'FAILED'}",
            f"Build: {'OK' if self.build_ok else 'FAILED' if self.repo_path else 'SKIPPED'}",
            f"Fix Attempts: {self.fix_attempts}",
            f"Final Status: {self.final_status or 'N/A'}",
        ]

        if self.release_mode:
            lines.append(f"Docker Compose: {'OK' if self.docker_compose_ok else 'FAILED'}")
            if self.services_running:
                lines.append(f"Services Running: {', '.join(self.services_running)}")
            lines.append(f"Smoke Tests: {'OK' if self.smoke_ok else 'FAILED'} ({self.smoke_passed}/{self.smoke_passed + self.smoke_failed})")

        if self.fixes_applied:
            lines.append(f"Fixes Applied: {len(self.fixes_applied)}")
            for fix in self.fixes_applied[:3]:
                desc = fix.get('description', 'unknown')
                lines.append(f"  - {desc}")

        if self.success:
            lines.append(f"SRS Version: v{self.srs_version}")
            lines.append(f"SRS Path: {self.srs_path}")
            lines.append(f"IR Version: v{self.ir_version}")
            lines.append(f"IR Path: {self.ir_path}")
            lines.append(f"OAS Version: v{self.oas_version}")
            lines.append(f"OAS Path: {self.oas_path}")
            lines.append(f"RBAC Version: v{self.rbac_version}")
            lines.append(f"RBAC Path: {self.rbac_path}")
            lines.append(f"PLAN Version: v{self.plan_version}")
            lines.append(f"PLAN Path: {self.plan_path}")
            if self.repo_path:
                lines.append(f"Repo Path: {self.repo_path}")
        else:
            if self.errors:
                lines.append(f"Errors: {', '.join(self.errors)}")
            if self.build_errors:
                lines.append(f"Build Errors: {', '.join(self.build_errors[:3])}")
            if self.fix_loop_aborted_reason:
                lines.append(f"Fix Loop Aborted: {self.fix_loop_aborted_reason}")
            if self.questions:
                lines.append("Questions:")
                for q in self.questions:
                    lines.append(f"  - {q}")

        lines.append(f"Duration: {self.duration_ms:.2f}ms")
        lines.append("="*50)

        return "\n".join(lines)


class Engine:
    """Orquestrador principal do sistema.

    Pipeline completo (artifacts):
    1. normalize
    2. classify blueprint
    3. req_analyst → SRS
    4. validate SRS
    5. save SRS (vN)
    6. domain_modeler → IR
    7. validate IR
    8. policy validator (IR)
    9. save IR (vN)
    10. contracts_agent → OpenAPI + RBAC
    11. validate OpenAPI
    12. validate RBAC
    13. policy validator (contracts)
    14. save OpenAPI (vN)
    15. save RBAC (vN)
    16. planner_agent → PLAN
    17. validate PLAN
    18. policy validator (PLAN)
    19. save PLAN (vN)
    20. write run log with all hashes

    Pipeline completo (com build):
    21. create repo em /home/bazari/generated/<project>
    22. generate patches
    23. apply patches
    24. run build validator
    25. falhou → rollback
    26. passou → SUCCESS

    Attributes:
        VERSION: Engine version string (e.g., "1.0.0")
    """

    # Engine version
    VERSION = ENGINE_VERSION

    # Root para projetos gerados
    GENERATED_ROOT = "/home/bazari/generated"
    TEMPLATES_ROOT = "/home/bazari/templates"

    def __init__(self, store_root: str = "./store_data") -> None:
        self.state_machine = StateMachine()
        self.context = ExecutionContext()

        # Componentes do pipeline
        self.normalizer = Normalizer()
        self.classifier = BlueprintClassifier()
        self.analyst = RequirementsAnalyst()
        self.srs_validator_gate = SRSValidatorGate()
        self.domain_modeler = DomainModeler()
        self.contracts_agent = ContractsAgent()
        self.planner_agent = PlannerAgent()
        self.policy_validator = PolicyValidator()
        self.store = ArtifactsStore(store_root)

    def run(
        self,
        project: str,
        raw_input: str,
        title: Optional[str] = None,
    ) -> RunResult:
        """Executa o pipeline completo até IR.

        Args:
            project: Nome do projeto
            raw_input: Texto bruto de entrada
            title: Título do projeto (opcional)

        Returns:
            RunResult com resultado da execução
        """
        start_time = datetime.now()
        execution_id = f"{project}_{uuid.uuid4().hex[:8]}"
        project_title = title or f"Sistema {project.title()}"

        # Inicializar resultado
        result = RunResult(
            success=False,
            execution_id=execution_id,
            project=project,
        )

        # Hashes para rastreabilidade
        input_hash: Optional[str] = None
        srs_hash: Optional[str] = None
        ir_hash: Optional[str] = None
        oas_hash: Optional[str] = None
        rbac_hash: Optional[str] = None
        plan_hash: Optional[str] = None

        try:
            # 1. Normalize
            self.state_machine.transition(State.INTAKE)
            normalized = self.normalizer.normalize(raw_input)
            # Calcular hash do input normalizado
            input_hash = self._compute_hash(normalized.get("normalized", ""))

            # 2. Classify blueprint
            classification = self.classifier.classify(normalized)
            result.blueprint_type = classification.selected_blueprint

            # 2b. Resolve blueprint from registry (FORCED_GENERIC if not found)
            from blueprints.generic_blueprint import GenericBlueprint
            blueprint_class = resolve_blueprint(result.blueprint_type)
            result.blueprint_forced_generic = (blueprint_class == GenericBlueprint)

            # 3. REQ Analyst → SRS
            self.state_machine.transition(State.PROCESSING)
            srs = self.analyst.generate_srs(normalized, project_title)
            result.requirements_count = len(srs.get("requirements", []))

            # 4. Validate SRS
            self.state_machine.transition(State.VALIDATING)
            can_proceed, validated_srs, questions = self.srs_validator_gate.process(srs)

            if not can_proceed:
                # SRS inválido - bloqueia pipeline, não segue para IR
                result.srs_validation_ok = False
                result.questions = questions or []
                result.errors = ["SRS validation failed"]
                self._write_run_log(
                    execution_id, result, "srs_validation_failed",
                    input_hash=input_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.srs_validation_ok = True

            # 5. Save SRS (vN)
            srs_version = self.store.next_version(project, "SRS")
            srs_path = self.store.save_artifact(project, "SRS", srs_version, validated_srs)
            result.srs_version = srs_version
            result.srs_path = str(srs_path)
            # Calcular hash do SRS salvo
            srs_hash = self._compute_file_hash(srs_path)

            # 6. Domain Modeler → IR
            ir = self.domain_modeler.generate_ir(validated_srs)
            result.entities_count = len(ir.get("domain", {}).get("entities", []))

            # 7. Validate IR
            ir_report = validate_ir(ir)
            if not ir_report.ok:
                # IR inválido - não salvar IR
                result.ir_validation_ok = False
                result.errors = ["IR validation failed"] + ir_report.errors
                self._write_run_log(
                    execution_id, result, "ir_validation_failed",
                    input_hash=input_hash, srs_hash=srs_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.ir_validation_ok = True

            # 8. Policy Validator (IR)
            policy_result = self.policy_validator.validate(ir)
            if not policy_result[0]:
                # Policy failed - não salvar IR
                result.policy_ok = False
                result.errors = ["Policy validation failed"] + policy_result[1]
                self._write_run_log(
                    execution_id, result, "policy_failed",
                    input_hash=input_hash, srs_hash=srs_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.policy_ok = True

            # 9. Save IR (vN)
            ir_version = self.store.next_version(project, "IR")
            # Adicionar versão ao IR antes de salvar
            ir["meta"]["version"] = f"v{ir_version}"
            ir["meta"]["srs_version"] = f"v{srs_version}"
            ir_path = self.store.save_artifact(project, "IR", ir_version, ir)
            result.ir_version = ir_version
            result.ir_path = str(ir_path)
            # Calcular hash do IR salvo
            ir_hash = self._compute_file_hash(ir_path)

            # 10. Contracts Agent → OpenAPI + RBAC
            openapi_yaml, rbac = self.contracts_agent.generate_contracts(ir)
            openapi_dict = yaml.safe_load(openapi_yaml)
            result.operations_count = self._count_operations(openapi_dict)

            # 11. Validate OpenAPI
            oas_report = validate_openapi(openapi_dict)
            if not oas_report.ok:
                result.oas_validation_ok = False
                result.errors = ["OpenAPI validation failed"] + oas_report.errors
                self._write_run_log(
                    execution_id, result, "oas_validation_failed",
                    input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.oas_validation_ok = True

            # 12. Validate RBAC
            rbac_report = validate_rbac(rbac)
            if not rbac_report.ok:
                result.rbac_validation_ok = False
                result.errors = ["RBAC validation failed"] + rbac_report.errors
                self._write_run_log(
                    execution_id, result, "rbac_validation_failed",
                    input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.rbac_validation_ok = True

            # 13. Policy Validator (Contracts) - verificar consistência OAS/RBAC
            contracts_policy_result = self.policy_validator.validate_contracts(openapi_dict, rbac)
            if not contracts_policy_result[0]:
                result.contracts_policy_ok = False
                result.errors = ["Contracts policy validation failed"] + contracts_policy_result[1]
                self._write_run_log(
                    execution_id, result, "contracts_policy_failed",
                    input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.contracts_policy_ok = True

            # 14. Save OpenAPI (vN)
            oas_version = self.store.next_version(project, "OAS")
            oas_path = self.store.save_text_artifact(
                project, "OAS", oas_version, openapi_yaml, ext="yaml"
            )
            result.oas_version = oas_version
            result.oas_path = str(oas_path)
            oas_hash = self._compute_file_hash(oas_path)

            # 15. Save RBAC (vN)
            rbac_version = self.store.next_version(project, "RBAC")
            rbac_path = self.store.save_artifact(project, "RBAC", rbac_version, rbac)
            result.rbac_version = rbac_version
            result.rbac_path = str(rbac_path)
            rbac_hash = self._compute_file_hash(rbac_path)

            # 16. Planner Agent → PLAN
            plan = self.planner_agent.generate_plan(ir, openapi_dict, rbac)

            # 16b. Apply blueprint to PLAN (FORCED_GENERIC = no-op, just reorder)
            blueprint_instance = blueprint_class()
            blueprint_result = blueprint_instance.apply(ir, openapi_dict, rbac, plan)
            plan = blueprint_result.plan  # Use the (possibly reordered) plan

            result.tasks_count = len(plan.get("tasks", []))

            # 17. Validate PLAN
            plan_report = validate_plan(plan)
            if not plan_report.ok:
                result.plan_validation_ok = False
                result.errors = ["PLAN validation failed"] + plan_report.errors
                self._write_run_log(
                    execution_id, result, "plan_validation_failed",
                    input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash,
                    oas_hash=oas_hash, rbac_hash=rbac_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.plan_validation_ok = True

            # 18. Policy Validator (PLAN) - verificar consistência do plano
            plan_policy_result = self.policy_validator.validate_plan(plan, ir=ir, openapi=openapi_dict)
            if not plan_policy_result[0]:
                result.plan_policy_ok = False
                result.errors = ["PLAN policy validation failed"] + plan_policy_result[1]
                self._write_run_log(
                    execution_id, result, "plan_policy_failed",
                    input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash,
                    oas_hash=oas_hash, rbac_hash=rbac_hash
                )
                self._finalize_result(result, start_time)
                return result

            result.plan_policy_ok = True

            # 19. Save PLAN (vN)
            plan_version = self.store.next_version(project, "PLAN")
            plan["meta"]["version"] = f"v{plan_version}"
            plan_path = self.store.save_artifact(project, "PLAN", plan_version, plan)
            result.plan_version = plan_version
            result.plan_path = str(plan_path)
            plan_hash = self._compute_file_hash(plan_path)

            # 20. Write run log with all hashes
            self.state_machine.transition(State.COMPLETED)
            result.success = True
            self._write_run_log(
                execution_id, result, "completed",
                input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash,
                oas_hash=oas_hash, rbac_hash=rbac_hash, plan_hash=plan_hash
            )

        except Exception as e:
            self.state_machine.transition(State.ERROR)
            result.errors = [str(e)]
            self._write_run_log(
                execution_id, result, "error",
                input_hash=input_hash, srs_hash=srs_hash, ir_hash=ir_hash,
                oas_hash=oas_hash, rbac_hash=rbac_hash, plan_hash=plan_hash
            )

        self._finalize_result(result, start_time)
        return result

    def _finalize_result(self, result: RunResult, start_time: datetime) -> None:
        """Calcula duração final."""
        end_time = datetime.now()
        result.duration_ms = (end_time - start_time).total_seconds() * 1000

    def _compute_hash(self, content: str) -> str:
        """Computa hash SHA256 (primeiros 16 chars) de uma string."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _compute_file_hash(self, file_path) -> str:
        """Computa hash SHA256 (primeiros 16 chars) de um arquivo."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return self._compute_hash(content)

    def _count_operations(self, openapi_dict: Dict[str, Any]) -> int:
        """Conta número de operações no OpenAPI."""
        count = 0
        paths = openapi_dict.get("paths", {})
        http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
        for path_item in paths.values():
            if isinstance(path_item, dict):
                for method in path_item.keys():
                    if method.lower() in http_methods:
                        count += 1
        return count

    def _write_run_log(
        self,
        execution_id: str,
        result: RunResult,
        status: str,
        input_hash: Optional[str] = None,
        srs_hash: Optional[str] = None,
        ir_hash: Optional[str] = None,
        oas_hash: Optional[str] = None,
        rbac_hash: Optional[str] = None,
        plan_hash: Optional[str] = None,
    ) -> None:
        """Escreve log de execução com hashes."""
        payload = {
            "status": status,
            "result": result.to_dict(),
            "state": self.state_machine.current_state.value,
            "timestamp": datetime.now().isoformat(),
        }
        if input_hash:
            payload["input_hash"] = input_hash
        if srs_hash:
            payload["srs_hash"] = srs_hash
        if ir_hash:
            payload["ir_hash"] = ir_hash
        if oas_hash:
            payload["oas_hash"] = oas_hash
        if rbac_hash:
            payload["rbac_hash"] = rbac_hash
        if plan_hash:
            payload["plan_hash"] = plan_hash
        # Build phase fields
        if result.repo_path:
            payload["repo_path"] = result.repo_path
        if result.patch_count > 0:
            payload["patch_count"] = result.patch_count
        payload["build_ok"] = result.build_ok
        # Fix Loop fields
        if result.fix_attempts > 0:
            payload["fix_attempts"] = result.fix_attempts
        if result.fixes_applied:
            payload["fixes_applied"] = result.fixes_applied
        if result.final_status:
            payload["final_status"] = result.final_status
        if result.fix_loop_aborted_reason:
            payload["fix_loop_aborted_reason"] = result.fix_loop_aborted_reason
        # Blueprint info (FORCED_GENERIC = "GENERIC")
        payload["blueprint"] = "GENERIC" if result.blueprint_forced_generic else result.blueprint_type.upper()
        self.store.write_run_log(execution_id, payload, project=result.project)

    def run_with_build(
        self,
        project: str,
        raw_input: str,
        title: Optional[str] = None,
        skip_build: bool = False,
        enable_fix_loop: bool = True,
    ) -> RunResult:
        """Executa o pipeline completo incluindo build e Fix Loop.

        Fluxo com Fix Loop (Semana 8):
        1. run() - gera todos os artefatos (SRS, IR, OAS, RBAC, PLAN)
        2. create repo em /home/bazari/generated/<project>
        3. generate patches
        4. apply patches
        5. run build validator
        6. Se falhar E enable_fix_loop: chamar FixLoopAgent
        7. Repetir até sucesso ou erro fatal
        8. Se falhar após fix loop → rollback

        Run log inclui: fix_attempts, fixes_applied[], final_status

        Args:
            project: Nome do projeto
            raw_input: Texto bruto de entrada
            title: Título do projeto (opcional)
            skip_build: Se True, pula a fase de build (para testes)
            enable_fix_loop: Se True, tenta corrigir erros de build automaticamente

        Returns:
            RunResult com resultado da execução
        """
        # 1. Executar pipeline de artefatos
        result = self.run(project, raw_input, title)

        # Se falhou antes do PLAN, retornar imediatamente
        if not result.success:
            result.final_status = "artifacts_failed"
            return result

        # Se skip_build, retornar após artefatos
        if skip_build:
            result.final_status = "artifacts_only"
            return result

        # Continuar com build phase
        start_time = datetime.now()

        try:
            # Carregar artefatos necessários
            plan = self._load_artifact(project, "PLAN", result.plan_version)
            ir = self._load_artifact(project, "IR", result.ir_version)
            oas = self._load_yaml_artifact(project, "OAS", result.oas_version)
            rbac = self._load_artifact(project, "RBAC", result.rbac_version)

            # 2. Create repo em /home/bazari/generated/<project>
            self.state_machine.transition(State.PROCESSING)
            repo_generator = RepoGenerator(
                templates_root=self.TEMPLATES_ROOT,
                output_root=self.GENERATED_ROOT,
            )

            # Verificar se repo já existe
            if repo_generator.repo_exists(project):
                # Para re-runs, deletar e recriar
                repo_generator.delete_repo(project)

            repo_path = repo_generator.create_repo(project)
            result.repo_path = str(repo_path)

            # 3. Generate patches
            patch_generator = PatchGenerator(project, self.GENERATED_ROOT)
            patchset = patch_generator.generate(plan, ir, oas, rbac)
            result.patch_count = len(patchset.patches)

            # 4. Apply patches
            patch_engine = PatchEngine(project, self.GENERATED_ROOT)
            patch_dicts = [p.to_dict() for p in patchset.patches]
            patch_result = patch_engine.apply_patches(patch_dicts)

            if not patch_result.success:
                # Patch application failed
                result.success = False
                result.build_ok = False
                result.build_errors = patch_result.errors
                result.errors.append("Patch application failed")
                result.final_status = "patch_failed"
                self._write_run_log(
                    result.execution_id, result, "patch_failed"
                )
                self._finalize_result(result, start_time)
                return result

            # 5. Run build validator
            self.state_machine.transition(State.VALIDATING)
            build_validator = BuildValidator(self.GENERATED_ROOT)

            # Tentar apenas frontend por enquanto (Maven pode não estar disponível)
            build_report = build_validator.validate(project, BuildComponent.FRONTEND)

            if build_report.ok:
                # Build passed on first try → SUCCESS
                result.build_ok = True
                result.final_status = "success"
                self.state_machine.transition(State.COMPLETED)
                self._write_run_log(
                    result.execution_id, result, "build_completed"
                )
                self._finalize_result(result, start_time)
                return result

            # 6. Build failed - tentar Fix Loop se habilitado
            if not enable_fix_loop:
                # Fix Loop desabilitado - preservar repo em _failed/ para debug
                result.success = False
                result.build_ok = False
                result.build_errors = build_report.errors
                result.final_status = "build_failed"

                # Mover para _failed/ em vez de deletar (preserva para auditoria)
                try:
                    failed_path = repo_generator.move_to_failed(project)
                    if failed_path:
                        result.errors.append(f"Repo moved to: {failed_path}")
                except Exception:
                    pass

                result.errors.append("Build validation failed (fix loop disabled)")
                self._write_run_log(
                    result.execution_id, result, "build_failed"
                )
                self._finalize_result(result, start_time)
                return result

            # 7. Executar Fix Loop
            fix_loop_result = self._run_fix_loop(
                project,
                build_report,
                "frontend",  # step
                result,
            )

            if fix_loop_result.success:
                # Fix Loop corrigiu os erros!
                result.build_ok = True
                result.final_status = "fixed"
                self.state_machine.transition(State.COMPLETED)
                self._write_run_log(
                    result.execution_id, result, "build_fixed"
                )
            else:
                # Fix Loop não conseguiu corrigir
                result.success = False
                result.build_ok = False
                result.fix_loop_aborted_reason = fix_loop_result.aborted_reason
                result.final_status = "fatal_error"

                # Mover para _failed/ em vez de deletar (preserva para auditoria)
                try:
                    failed_path = repo_generator.move_to_failed(project)
                    if failed_path:
                        result.errors.append(f"Repo moved to: {failed_path}")
                except Exception:
                    pass

                result.errors.append(f"Fix loop failed: {fix_loop_result.aborted_reason}")
                self._write_run_log(
                    result.execution_id, result, "fix_loop_failed"
                )

        except Exception as e:
            self.state_machine.transition(State.ERROR)
            result.success = False
            result.build_ok = False
            result.final_status = "error"
            result.errors.append(f"Build phase error: {str(e)}")
            self._write_run_log(
                result.execution_id, result, "build_error"
            )

        self._finalize_result(result, start_time)
        return result

    def _run_fix_loop(
        self,
        project: str,
        initial_build_report: BuildReport,
        step: str,
        result: RunResult,
    ) -> FixLoopResult:
        """Executa o Fix Loop para corrigir erros de build.

        Args:
            project: Nome do projeto
            initial_build_report: Report do build inicial que falhou
            step: Etapa do build ("backend", "frontend")
            result: RunResult para atualizar com informações do fix loop

        Returns:
            FixLoopResult com resultado do loop
        """
        # Criar o Fix Loop Agent
        fix_agent = FixLoopAgent(project, self.GENERATED_ROOT)

        # Converter build report para stderr/stdout
        stderr = "\n".join(initial_build_report.errors)
        stdout = "\n".join(initial_build_report.warnings)
        exit_code = 1

        # Executar fix loop
        fix_result = fix_agent.run(stderr, stdout, exit_code, step)

        # Atualizar result com informações do fix loop
        result.fix_attempts = fix_result.total_attempts

        # Extrair fixes aplicados
        for attempt in fix_result.attempts:
            if attempt.patch_applied:
                result.fixes_applied.append(attempt.patch_applied.to_dict())

        return fix_result

    def _load_artifact(self, project: str, artifact_type: str, version: int) -> Dict[str, Any]:
        """Carrega um artefato JSON do store."""
        artifact = self.store.load_version(project, artifact_type, version)
        if artifact is None:
            raise FileNotFoundError(f"Artifact not found: {project}/{artifact_type}/v{version}")
        return artifact

    def _load_yaml_artifact(self, project: str, artifact_type: str, version: int) -> Dict[str, Any]:
        """Carrega um artefato YAML do store."""
        content = self.store.load_text_artifact(project, artifact_type, version, ext="yaml")
        if content is None:
            raise FileNotFoundError(f"Artifact not found: {project}/{artifact_type}/v{version}.yaml")
        return yaml.safe_load(content)

    def run_release(
        self,
        project: str,
        raw_input: str,
        title: Optional[str] = None,
        enable_fix_loop: bool = True,
    ) -> RunResult:
        """Executa o pipeline completo em modo release.

        Pipeline "texto → rodando":
        1. run_with_build() - gera artefatos, repo, patches, build
        2. DockerComposeValidator.ensure_valid() - garante docker-compose.yml
        3. docker compose up -d
        4. SmokeRunner.run() - smoke tests

        Falha em qualquer etapa:
        - docker compose down + rollback (remove repo)

        Sucesso:
        - sistema permanece rodando

        Args:
            project: Nome do projeto
            raw_input: Texto bruto de entrada
            title: Título do projeto (opcional)
            enable_fix_loop: Se True, tenta corrigir erros de build automaticamente

        Returns:
            RunResult com resultado da execução
        """
        # Marcar como modo release
        start_time = datetime.now()

        # 1. Executar pipeline com build
        result = self.run_with_build(
            project,
            raw_input,
            title,
            skip_build=False,
            enable_fix_loop=enable_fix_loop,
        )

        # Marcar como release mode
        result.release_mode = True
        result.docker_up_timeout_seconds = DockerComposeValidator.DOCKER_UP_TIMEOUT

        # Se build falhou, usar status canônico BUILD_FAILED
        if not result.build_ok:
            result.final_status = ReleaseFailureCategory.BUILD_FAILED.value
            failed_path = self._rollback_release(
                project, ReleaseFailureCategory.BUILD_FAILED
            )
            if failed_path:
                result.failed_repo_path = str(failed_path)
            self._finalize_result(result, start_time)
            return result

        # A partir daqui, precisamos de rollback em caso de falha
        docker_validator = DockerComposeValidator(self.GENERATED_ROOT)
        smoke_runner = SmokeRunner(self.GENERATED_ROOT)

        try:
            # 2. Garantir docker-compose.yml válido
            compose_ok, compose_result = docker_validator.ensure_valid(project)

            if not compose_ok:
                # Docker compose inválido → DOCKER_UP_FAILED (policy violation)
                result.success = False
                result.docker_compose_ok = False
                result.final_status = ReleaseFailureCategory.DOCKER_UP_FAILED.value
                result.errors.append("Docker compose validation failed")
                if compose_result.errors:
                    result.errors.extend(compose_result.errors)

                failed_path = self._rollback_release(
                    project, ReleaseFailureCategory.DOCKER_UP_FAILED
                )
                if failed_path:
                    result.failed_repo_path = str(failed_path)
                self._write_run_log(
                    result.execution_id, result, "docker_compose_failed"
                )
                self._finalize_result(result, start_time)
                return result

            result.docker_compose_ok = True

            # 2.1. Gate: Validar build contexts e Dockerfiles existem (pré-docker)
            context_result = docker_validator.validate_build_contexts(project)

            if not context_result.valid:
                # Build contexts ou Dockerfiles não existem → DOCKER_UP_FAILED
                result.success = False
                result.docker_compose_ok = False
                result.final_status = ReleaseFailureCategory.DOCKER_UP_FAILED.value
                result.errors.append("Docker build context/Dockerfile validation failed")
                if context_result.errors:
                    result.errors.extend(context_result.errors)
                if context_result.missing_context_paths:
                    result.errors.append(
                        f"Missing contexts: {', '.join(context_result.missing_context_paths)}"
                    )
                if context_result.missing_dockerfile_paths:
                    result.errors.append(
                        f"Missing Dockerfiles: {', '.join(context_result.missing_dockerfile_paths)}"
                    )

                failed_path = self._rollback_release(
                    project, ReleaseFailureCategory.DOCKER_UP_FAILED
                )
                if failed_path:
                    result.failed_repo_path = str(failed_path)
                self._write_run_log(
                    result.execution_id, result, "docker_context_failed"
                )
                self._finalize_result(result, start_time)
                return result

            # 3. docker compose up -d (timeout: 300s conforme política)
            up_result = docker_validator.test_docker_compose_up(
                project,
                detach=True,
                timeout=DockerComposeValidator.DOCKER_UP_TIMEOUT,
            )

            # Coletar evidências de Docker no result
            result.docker_compose_command = up_result.docker_compose_command
            result.docker_stdout_tail = up_result.stdout[:500] if up_result.stdout else ""
            result.docker_stderr_tail = up_result.stderr[:500] if up_result.stderr else ""
            result.docker_ps_snapshot = up_result.docker_ps_snapshot
            result.docker_logs_backend_tail = up_result.docker_logs_backend_tail
            result.docker_logs_frontend_tail = up_result.docker_logs_frontend_tail

            if not up_result.success:
                # docker compose up falhou → DOCKER_UP_FAILED
                result.success = False
                result.docker_compose_ok = False
                result.final_status = ReleaseFailureCategory.DOCKER_UP_FAILED.value
                result.errors.append(f"docker compose up failed: {up_result.stderr[:200]}")

                # Tentar docker compose down antes de rollback
                docker_validator.stop_services(project)
                failed_path = self._rollback_release(
                    project, ReleaseFailureCategory.DOCKER_UP_FAILED
                )
                if failed_path:
                    result.failed_repo_path = str(failed_path)
                self._write_run_log(
                    result.execution_id, result, "docker_up_failed"
                )
                self._finalize_result(result, start_time)
                return result

            result.services_running = up_result.services_started

            # 3.1. Readiness loop (máximo 120s, poll a cada 2s)
            readiness_result = docker_validator.wait_for_readiness(project)

            # Atualizar evidências com readiness
            result.docker_ps_snapshot = readiness_result.docker_ps_snapshot
            result.docker_logs_backend_tail = readiness_result.docker_logs_backend_tail
            result.docker_logs_frontend_tail = readiness_result.docker_logs_frontend_tail

            if not readiness_result.readiness_ok:
                # Containers subiram mas app não ficou ready → SMOKE_FAILED
                result.success = False
                result.smoke_ok = False
                result.final_status = ReleaseFailureCategory.SMOKE_FAILED.value
                result.errors.append(
                    f"Services not ready after {readiness_result.readiness_duration_ms:.0f}ms"
                )

                docker_validator.stop_services(project)
                failed_path = self._rollback_release(
                    project, ReleaseFailureCategory.SMOKE_FAILED
                )
                if failed_path:
                    result.failed_repo_path = str(failed_path)
                self._write_run_log(
                    result.execution_id, result, "readiness_failed"
                )
                self._finalize_result(result, start_time)
                return result

            # 4. Smoke tests (só após readiness confirmada)
            smoke_report = smoke_runner.run_smoke_tests(project)

            result.smoke_passed = sum(1 for r in smoke_report.results if r.status == "PASS")
            result.smoke_failed = sum(1 for r in smoke_report.results if r.status == "FAIL")

            if smoke_report.overall_status == "FAIL":
                # Smoke tests falharam → SMOKE_FAILED
                result.success = False
                result.smoke_ok = False
                result.final_status = ReleaseFailureCategory.SMOKE_FAILED.value

                # Coletar erros dos smoke tests
                failed_tests = [r for r in smoke_report.results if r.status == "FAIL"]
                for test in failed_tests[:3]:  # Limitar a 3 erros
                    result.errors.append(f"Smoke test failed: {test.name} - {test.message}")

                # docker compose down + rollback
                docker_validator.stop_services(project)
                failed_path = self._rollback_release(
                    project, ReleaseFailureCategory.SMOKE_FAILED
                )
                if failed_path:
                    result.failed_repo_path = str(failed_path)
                self._write_run_log(
                    result.execution_id, result, "smoke_failed"
                )
                self._finalize_result(result, start_time)
                return result

            # 5. Sucesso! Sistema permanece rodando
            result.success = True
            result.smoke_ok = True
            result.final_status = "running"
            self.state_machine.transition(State.COMPLETED)

            self._write_run_log(
                result.execution_id, result, "release_completed"
            )

        except Exception as e:
            # Erro inesperado → UNKNOWN_RELEASE_FAILED
            result.success = False
            result.final_status = ReleaseFailureCategory.UNKNOWN_RELEASE_FAILED.value
            result.errors.append(f"Release error: {str(e)}")

            # Tentar docker compose down e rollback
            try:
                docker_validator.stop_services(project)
            except Exception:
                pass
            failed_path = self._rollback_release(
                project, ReleaseFailureCategory.UNKNOWN_RELEASE_FAILED
            )
            if failed_path:
                result.failed_repo_path = str(failed_path)

            self._write_run_log(
                result.execution_id, result, "release_error"
            )

        self._finalize_result(result, start_time)
        return result

    def _rollback_release(
        self,
        project: str,
        category: Optional[ReleaseFailureCategory] = None,
    ) -> Optional[Path]:
        """Rollback de um release: move repo para _failed/<CATEGORY>/.

        Preserva logs, saída do build e arquivos para debug/auditoria.
        NUNCA apaga o repo.

        Args:
            project: Nome do projeto
            category: Categoria canônica da falha (BUILD_FAILED, DOCKER_UP_FAILED, etc.)

        Returns:
            Path do diretório de destino em _failed/<CATEGORY>/, ou None se falhou
        """
        try:
            repo_generator = RepoGenerator(
                templates_root=self.TEMPLATES_ROOT,
                output_root=self.GENERATED_ROOT,
            )
            if repo_generator.repo_exists(project):
                return repo_generator.move_to_failed(project, category)
        except Exception:
            # Ignorar erros no rollback
            pass
        return None
