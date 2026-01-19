"""Pipeline Orchestrator - End-to-end NL to Deploy."""

import json
import logging
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.core.runtime_state import runtime_state
from engine.nl.extractors import get_extractor
from engine.nl.schemas.sir_v1 import SIRv1
from engine.nl.schemas.answers_v1 import AnswersV1, Gap, Answer
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps, gaps_to_dict
from engine.nl.answer_apply import apply_answers
from engine.nl.finalizer import finalize
from engine.ise.release import (
    compile_release as ise_compile_release,
    ReleaseResult,
    get_verify_script,
    get_deploy_script,
)
from engine.ise.compiler import compile_bundle
from engine.core.ege_pins import auto_propose_and_accept_pin

# Logger for structured JSON logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone

from .hashes import compute_hash, compute_trace_hashes
from .registry import get_registry, get_dev_runs_dir_for_institution
from .policy_gaps import extract_policy_gaps, build_answers_template, compute_policy_counts
from engine.core.data_root import resolve_namespaced_path


# Pipeline statuses
STATUS_NEEDS_ANSWERS = "NEEDS_ANSWERS"
STATUS_DEPLOYED = "DEPLOYED"
STATUS_ROLLED_BACK = "ROLLED_BACK"
STATUS_FAILED = "FAILED"
STATUS_BUILT = "BUILT"

# Error codes for build
PIPELINE_TEXT_REQUIRED = "PIPELINE_TEXT_REQUIRED"
PIPELINE_BUNDLE_NAME_REQUIRED = "PIPELINE_BUNDLE_NAME_REQUIRED"
PIPELINE_BUILD_WRITE_FAILED = "PIPELINE_BUILD_WRITE_FAILED"
PIPELINE_STAGE_FAILED = "PIPELINE_STAGE_FAILED"

# Error codes for deploy (hard lock institutional)
PIPELINE_ENGINE_SAFE_MODE = "PIPELINE_ENGINE_SAFE_MODE"
PIPELINE_VERIFY_FAILED = "PIPELINE_VERIFY_FAILED"
PIPELINE_DEPLOY_UNAVAILABLE = "PIPELINE_DEPLOY_UNAVAILABLE"


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    status: str
    bundle_name: Optional[str] = None
    release_id: Optional[str] = None

    # Build-specific fields
    run_id: Optional[str] = None
    bundle_path: Optional[str] = None

    # Hashes for traceability
    hash_sir: Optional[str] = None
    hash_draft: Optional[str] = None
    hash_idl_final: Optional[str] = None
    bundle_hash: Optional[str] = None

    # NEEDS_ANSWERS data
    gaps: Optional[List[Dict[str, Any]]] = None
    sir: Optional[Dict[str, Any]] = None
    draft_idl: Optional[Dict[str, Any]] = None

    # Policy gaps specific data (subset of gaps that are policy-related)
    policy_gaps: Optional[List[Dict[str, Any]]] = None
    answers_template: Optional[Dict[str, Any]] = None

    # Error data
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    stage: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {"status": self.status}

        if self.bundle_name:
            result["bundle_name"] = self.bundle_name

        if self.release_id:
            result["release_id"] = self.release_id

        # Build-specific fields
        if self.run_id:
            result["run_id"] = self.run_id
        if self.bundle_path:
            result["bundle_path"] = self.bundle_path

        # Always include hashes if present
        if self.hash_sir:
            result["hash_sir"] = self.hash_sir
        if self.hash_draft:
            result["hash_draft"] = self.hash_draft
        if self.hash_idl_final:
            result["hash_idl_final"] = self.hash_idl_final
        if self.bundle_hash:
            result["bundle_hash"] = self.bundle_hash

        # NEEDS_ANSWERS specific data
        if self.status == STATUS_NEEDS_ANSWERS:
            if self.gaps is not None:
                result["gaps"] = self.gaps
            if self.sir is not None:
                result["sir"] = self.sir
            if self.draft_idl is not None:
                result["draft_idl"] = self.draft_idl
            if self.policy_gaps is not None:
                result["policy_gaps"] = self.policy_gaps
            if self.answers_template is not None:
                result["answers_template"] = self.answers_template

        # Error data
        if self.status in (STATUS_ROLLED_BACK, STATUS_FAILED):
            if self.error_code or self.error_message:
                result["error"] = {}
                if self.error_code:
                    result["error"]["code"] = self.error_code
                if self.error_message:
                    result["error"]["message"] = self.error_message
                if self.exit_code is not None:
                    result["error"]["exit_code"] = self.exit_code
                if self.stage:
                    result["error"]["stage"] = self.stage

        return result


def _write_deploy_trace(
    bundle_name: str,
    release_id: str,
    bundle_hash: str,
    hashes: Dict[str, str],
    institution_id: Optional[str] = None,
) -> Optional[str]:
    """Write trace.json for deploy operations.

    Creates deploy-traces/<release_id>/trace.json with full audit trail.

    Args:
        bundle_name: Name of the deployed bundle.
        release_id: Release ID from deploy.
        bundle_hash: Hash of the deployed bundle.
        hashes: Dict with hash_sir, hash_draft, hash_idl_final.
        institution_id: Optional institution UUID for namespaced storage.

    Returns:
        Path to trace.json if written, None on error.
    """
    try:
        # Determine deploy-traces directory
        if institution_id:
            traces_dir = resolve_namespaced_path(institution_id, None, "deploy-traces")
        else:
            traces_dir = Path(os.environ.get("BUNDLES_ROOT", "bundles")) / "deploy-traces"

        # Create release-specific directory
        release_dir = traces_dir / release_id
        release_dir.mkdir(parents=True, exist_ok=True)

        # Build trace data
        trace_data = {
            "trace_version": "1.0",
            "operation": "deploy",
            "release_id": release_id,
            "bundle_name": bundle_name,
            "bundle_hash": bundle_hash,
            "sir_sha256": hashes.get("hash_sir"),
            "draft_sha256": hashes.get("hash_draft"),
            "final_idl_sha256": hashes.get("hash_idl_final"),
            "deployed_at": datetime.now(timezone.utc).isoformat(),
            "institution_id": institution_id,
        }

        trace_path = release_dir / "trace.json"
        trace_path.write_text(json.dumps(trace_data, indent=2), encoding="utf-8")

        logger.info(
            "DEPLOY_TRACE_WRITTEN",
            extra={
                "event": "DEPLOY_TRACE_WRITTEN",
                "release_id": release_id,
                "bundle_name": bundle_name,
                "trace_path": str(trace_path),
            },
        )

        return str(trace_path)

    except Exception as e:
        # Trace write errors are non-fatal
        logger.warning(
            "DEPLOY_TRACE_WRITE_FAILED",
            extra={
                "event": "DEPLOY_TRACE_WRITE_FAILED",
                "release_id": release_id,
                "bundle_name": bundle_name,
                "error": str(e),
            },
        )
        return None


def run_pipeline(
    text: str,
    bundle_name: str,
    target: str = "production",
    answers: Optional[List[Dict[str, Any]]] = None,
    language: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> PipelineResult:
    """Run the full NL to Deploy pipeline.

    Order:
    1. compile_sir - Extract SIR from natural language
    2. compile_draft - Generate draft IDL from SIR
    3. detect_gaps - Find missing information
    4. If gaps and no answers -> return NEEDS_ANSWERS
    5. If answers -> apply_answers, detect_gaps again
    6. If still gaps -> return NEEDS_ANSWERS
    7. finalize - Produce final IDL
    8. compile_release - Compile and deploy bundle
    9. Return DEPLOYED or ROLLED_BACK (auto-propose pin if institution_id provided)

    Args:
        text: Natural language policy text.
        bundle_name: Name for the bundle.
        target: Deployment target (default: production).
        answers: Optional list of answer dicts with question_id and value.
        language: Optional language hint (auto-detected if not provided).
        institution_id: Optional institution UUID. If provided, enables auto-propose pin on deploy.

    Returns:
        PipelineResult with status and data.
    """
    # Step 0: Check SAFE_MODE - hard lock institutional
    # If engine is in SAFE_MODE, block deploy entirely
    if runtime_state.is_safe_mode():
        logger.warning(
            "PIPELINE_DEPLOY_BLOCKED_SAFE_MODE",
            extra={
                "event": "PIPELINE_DEPLOY_BLOCKED_SAFE_MODE",
                "bundle_name": bundle_name,
                "reason_code": runtime_state.reason_code,
                "details": runtime_state.details,
            },
        )
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            error_code=PIPELINE_ENGINE_SAFE_MODE,
            error_message=f"Deploy blocked: engine in SAFE_MODE ({runtime_state.reason_code})",
        )

    # Step 1: compile_sir
    try:
        extractor = get_extractor()
        sir = extractor.extract(text, language)
        sir_dict = sir.to_dict()
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            error_code="NL_EXTRACTION_FAILED",
            error_message=f"SIR extraction failed: {e}",
        )

    # Step 2: compile_draft
    try:
        draft = generate_draft(sir)
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            hash_sir=compute_hash(sir_dict),
            error_code="NL_DRAFT_FAILED",
            error_message=f"Draft generation failed: {e}",
        )

    # Step 3: detect_gaps
    try:
        gaps = detect_gaps(sir, draft)
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            hash_sir=compute_hash(sir_dict),
            hash_draft=compute_hash(draft),
            error_code="NL_GAP_DETECTION_FAILED",
            error_message=f"Gap detection failed: {e}",
        )

    # Filter to required gaps only
    required_gaps = [g for g in gaps if g.severity == "required"]

    # Step 4: If required gaps and no answers -> NEEDS_ANSWERS
    # Per policy gaps hardening: stop immediately, do NOT call compile_release
    if required_gaps and answers is None:
        gaps_dict = gaps_to_dict(gaps)
        # Extract policy gaps (by prefix)
        policy_gaps_list = extract_policy_gaps(gaps)
        policy_gaps_dict = [g.to_dict() for g in policy_gaps_list]
        # Build answers template (with null placeholders)
        answers_tpl = build_answers_template(gaps)
        return PipelineResult(
            status=STATUS_NEEDS_ANSWERS,
            bundle_name=bundle_name,
            hash_sir=compute_hash(sir_dict),
            hash_draft=compute_hash(draft),
            gaps=gaps_dict.get("gaps", []),
            sir=sir_dict,
            draft_idl=draft,
            policy_gaps=policy_gaps_dict,
            answers_template=answers_tpl,
        )

    # Step 5: If answers -> apply_answers
    if answers is not None and required_gaps:
        try:
            answers_list = [
                Answer(question_id=a["question_id"], value=a["value"])
                for a in answers
            ]
            answers_obj = AnswersV1(answers=answers_list)
            draft, remaining_gaps = apply_answers(draft, gaps, answers_obj)

            # Step 6: Check if still have required gaps
            # Per policy gaps hardening: stop immediately, do NOT call compile_release
            remaining_required = [g for g in remaining_gaps if g.severity == "required"]
            if remaining_required:
                gaps_dict = gaps_to_dict(remaining_gaps)
                # Extract policy gaps (by prefix)
                policy_gaps_list = extract_policy_gaps(remaining_gaps)
                policy_gaps_dict = [g.to_dict() for g in policy_gaps_list]
                # Build answers template (with null placeholders)
                answers_tpl = build_answers_template(remaining_gaps)
                return PipelineResult(
                    status=STATUS_NEEDS_ANSWERS,
                    bundle_name=bundle_name,
                    hash_sir=compute_hash(sir_dict),
                    hash_draft=compute_hash(draft),
                    gaps=gaps_dict.get("gaps", []),
                    sir=sir_dict,
                    draft_idl=draft,
                    policy_gaps=policy_gaps_dict,
                    answers_template=answers_tpl,
                )
        except Exception as e:
            return PipelineResult(
                status=STATUS_FAILED,
                bundle_name=bundle_name,
                hash_sir=compute_hash(sir_dict),
                hash_draft=compute_hash(draft),
                error_code="NL_ANSWERS_FAILED",
                error_message=f"Failed to apply answers: {e}",
            )

    # Step 7: finalize
    try:
        # Allow gaps that are not required
        remaining = [g for g in gaps if g.severity != "required"]
        idl_final = finalize(draft, remaining, allow_gaps=True)
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            hash_sir=compute_hash(sir_dict),
            hash_draft=compute_hash(draft),
            error_code="NL_FINALIZE_FAILED",
            error_message=f"Finalization failed: {e}",
        )

    # Compute trace hashes
    hashes = compute_trace_hashes(sir_dict, draft, idl_final)

    # Step 8a: Pre-compile bundle for explicit verification (redundant check)
    # This is an explicit institutional hard lock before calling compile_release
    idl_json = json.dumps(idl_final)
    verify_script = get_verify_script()

    try:
        # Compile to temp dir for verification
        with tempfile.TemporaryDirectory() as verify_temp_dir:
            pre_compile_result = compile_bundle(
                idl=idl_json,
                bundle_name=bundle_name,
                output_dir=verify_temp_dir,
                validate_finance_pilot=True,
            )

            if not pre_compile_result.success:
                return PipelineResult(
                    status=STATUS_FAILED,
                    bundle_name=bundle_name,
                    **hashes,
                    error_code=pre_compile_result.error_code or "ISE_COMPILE_FAILED",
                    error_message=pre_compile_result.error_message or "Pre-compile failed",
                )

            # Step 8b: Explicit verify_bundle.sh call (redundant institutional check)
            pre_bundle_path = Path(verify_temp_dir) / bundle_name

            if not Path(verify_script).exists():
                return PipelineResult(
                    status=STATUS_FAILED,
                    bundle_name=bundle_name,
                    **hashes,
                    error_code=PIPELINE_DEPLOY_UNAVAILABLE,
                    error_message=f"Verify script not found: {verify_script}",
                )

            try:
                verify_result = subprocess.run(
                    [verify_script, str(pre_bundle_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if verify_result.returncode != 0:
                    logger.warning(
                        "PIPELINE_DEPLOY_VERIFY_FAILED",
                        extra={
                            "event": "PIPELINE_DEPLOY_VERIFY_FAILED",
                            "bundle_name": bundle_name,
                            "exit_code": verify_result.returncode,
                            "output": verify_result.stderr or verify_result.stdout,
                        },
                    )
                    return PipelineResult(
                        status=STATUS_FAILED,
                        bundle_name=bundle_name,
                        **hashes,
                        error_code=PIPELINE_VERIFY_FAILED,
                        error_message="Bundle verification failed (explicit check)",
                        exit_code=verify_result.returncode,
                    )
            except subprocess.TimeoutExpired:
                return PipelineResult(
                    status=STATUS_FAILED,
                    bundle_name=bundle_name,
                    **hashes,
                    error_code=PIPELINE_VERIFY_FAILED,
                    error_message="Verify script timed out",
                )
            except Exception as e:
                return PipelineResult(
                    status=STATUS_FAILED,
                    bundle_name=bundle_name,
                    **hashes,
                    error_code=PIPELINE_DEPLOY_UNAVAILABLE,
                    error_message=f"Verify script error: {e}",
                )

    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            **hashes,
            error_code=PIPELINE_DEPLOY_UNAVAILABLE,
            error_message=f"Pre-verification failed: {e}",
        )

    # Step 9: compile_release (includes internal verification + deploy)
    # Only reached if explicit verification passed
    try:
        release_result = ise_compile_release(
            idl=idl_json,
            bundle_name=bundle_name,
            validate_finance_pilot=True,
            institution_id=institution_id,
        )
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            **hashes,
            error_code="ISE_RELEASE_FAILED",
            error_message=f"Release failed: {e}",
        )

    # Step 9: Return DEPLOYED or ROLLED_BACK
    if release_result.status == "deployed":
        # Step 10: Auto-propose pin on deploy (8.1.1)
        # If institution_id provided, call auto_propose_and_accept_pin
        # This creates a PIN_UPDATE proposal (and auto-accepts if config says so)
        if institution_id is not None:
            try:
                auto_propose_and_accept_pin(
                    institution_id=institution_id,
                    release_id=release_result.release_id or "",
                    bundle_name=bundle_name,
                    actor_id="SYSTEM",
                )
            except Exception as e:
                # Log but don't fail the deploy
                logger.warning(
                    "AUTO_PIN_PROPOSE_FAILED",
                    extra={
                        "event": "AUTO_PIN_PROPOSE_FAILED",
                        "bundle_name": bundle_name,
                        "release_id": release_result.release_id,
                        "institution_id": institution_id,
                        "error": str(e),
                    },
                )

        # Step 11: Write deploy trace for offline proof
        _write_deploy_trace(
            bundle_name=bundle_name,
            release_id=release_result.release_id or "",
            bundle_hash=release_result.bundle_hash or "",
            hashes=hashes,
            institution_id=institution_id,
        )

        return PipelineResult(
            status=STATUS_DEPLOYED,
            bundle_name=bundle_name,
            release_id=release_result.release_id,
            bundle_hash=release_result.bundle_hash,
            **hashes,
        )
    elif release_result.status == "rolled_back":
        return PipelineResult(
            status=STATUS_ROLLED_BACK,
            bundle_name=bundle_name,
            release_id=release_result.release_id,
            bundle_hash=release_result.bundle_hash,
            **hashes,
            error_code=release_result.error_code,
            error_message=release_result.error_message,
            exit_code=release_result.exit_code,
        )
    else:
        # Failed status
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            release_id=release_result.release_id,
            bundle_hash=release_result.bundle_hash,
            **hashes,
            error_code=release_result.error_code,
            error_message=release_result.error_message,
            exit_code=release_result.exit_code,
        )


def build_pipeline(
    text: str,
    bundle_name: str,
    answers: Optional[List[Dict[str, Any]]] = None,
    language: Optional[str] = None,
    bundles_root: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> PipelineResult:
    """Run NL to Build pipeline (no deploy).

    Builds bundle in sandbox dev-runs directory without deploying.
    Does NOT call compile_release, scripts, or subprocess.

    Order:
    1. compile_sir - Extract SIR from natural language
    2. compile_draft - Generate draft IDL from SIR
    3. detect_gaps - Find missing information
    4. If gaps and no answers -> return NEEDS_ANSWERS
    5. If answers -> apply_answers, detect_gaps again
    6. If still gaps -> return NEEDS_ANSWERS
    7. finalize - Produce final IDL
    8. compile_bundle - Compile bundle to dev-runs sandbox
    9. Return BUILT

    Args:
        text: Natural language policy text.
        bundle_name: Name for the bundle.
        answers: Optional list of answer dicts with question_id and value.
        language: Optional language hint (auto-detected if not provided).
        bundles_root: Root directory for bundles (default: bundles). Ignored if institution_id is set.
        institution_id: Institution UUID for namespaced storage. If set, dev-runs go under institution root.

    Returns:
        PipelineResult with status and data.
    """
    # Generate run_id (UUID v4)
    run_id = str(uuid.uuid4())

    # Determine output directory
    if institution_id is not None:
        # Use institution-namespaced dev-runs directory
        dev_runs_dir = get_dev_runs_dir_for_institution(institution_id)
        output_dir = str(dev_runs_dir / run_id)
    else:
        # Legacy: use bundles_root/dev-runs/run_id
        root = bundles_root or os.environ.get("ENGINE_PROD_BUNDLES_ROOT", "bundles")
        output_dir = str(Path(root) / "dev-runs" / run_id)

    # Step 1: compile_sir
    try:
        extractor = get_extractor()
        sir = extractor.extract(text, language)
        sir_dict = sir.to_dict()
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            run_id=run_id,
            error_code=PIPELINE_STAGE_FAILED,
            error_message=f"SIR extraction failed: {e}",
            stage="compile_sir",
        )

    # Step 2: compile_draft
    try:
        draft = generate_draft(sir)
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            run_id=run_id,
            hash_sir=compute_hash(sir_dict),
            error_code=PIPELINE_STAGE_FAILED,
            error_message=f"Draft generation failed: {e}",
            stage="compile_draft",
        )

    # Step 3: detect_gaps
    try:
        gaps = detect_gaps(sir, draft)
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            run_id=run_id,
            hash_sir=compute_hash(sir_dict),
            hash_draft=compute_hash(draft),
            error_code=PIPELINE_STAGE_FAILED,
            error_message=f"Gap detection failed: {e}",
            stage="detect_gaps",
        )

    # Filter to required gaps only
    required_gaps = [g for g in gaps if g.severity == "required"]

    # Step 4: If required gaps and no answers -> NEEDS_ANSWERS
    if required_gaps and answers is None:
        gaps_dict = gaps_to_dict(gaps)
        # Extract policy gaps (by prefix)
        policy_gaps_list = extract_policy_gaps(gaps)
        policy_gaps_dict = [g.to_dict() for g in policy_gaps_list]
        # Build answers template (with null placeholders)
        answers_tpl = build_answers_template(gaps)
        return PipelineResult(
            status=STATUS_NEEDS_ANSWERS,
            bundle_name=bundle_name,
            run_id=run_id,
            hash_sir=compute_hash(sir_dict),
            hash_draft=compute_hash(draft),
            gaps=gaps_dict.get("gaps", []),
            sir=sir_dict,
            draft_idl=draft,
            policy_gaps=policy_gaps_dict,
            answers_template=answers_tpl,
        )

    # Step 5: If answers -> apply_answers
    if answers is not None and required_gaps:
        try:
            answers_list = [
                Answer(question_id=a["question_id"], value=a["value"])
                for a in answers
            ]
            answers_obj = AnswersV1(answers=answers_list)
            draft, remaining_gaps = apply_answers(draft, gaps, answers_obj)

            # Step 6: Check if still have required gaps
            remaining_required = [g for g in remaining_gaps if g.severity == "required"]
            if remaining_required:
                gaps_dict = gaps_to_dict(remaining_gaps)
                # Extract policy gaps (by prefix)
                policy_gaps_list = extract_policy_gaps(remaining_gaps)
                policy_gaps_dict = [g.to_dict() for g in policy_gaps_list]
                # Build answers template (with null placeholders)
                answers_tpl = build_answers_template(remaining_gaps)
                return PipelineResult(
                    status=STATUS_NEEDS_ANSWERS,
                    bundle_name=bundle_name,
                    run_id=run_id,
                    hash_sir=compute_hash(sir_dict),
                    hash_draft=compute_hash(draft),
                    gaps=gaps_dict.get("gaps", []),
                    sir=sir_dict,
                    draft_idl=draft,
                    policy_gaps=policy_gaps_dict,
                    answers_template=answers_tpl,
                )
        except Exception as e:
            return PipelineResult(
                status=STATUS_FAILED,
                bundle_name=bundle_name,
                run_id=run_id,
                hash_sir=compute_hash(sir_dict),
                hash_draft=compute_hash(draft),
                error_code=PIPELINE_STAGE_FAILED,
                error_message=f"Failed to apply answers: {e}",
                stage="apply_answers",
            )

    # Step 7: finalize
    try:
        # Allow gaps that are not required
        remaining = [g for g in gaps if g.severity != "required"]
        idl_final = finalize(draft, remaining, allow_gaps=True)
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            run_id=run_id,
            hash_sir=compute_hash(sir_dict),
            hash_draft=compute_hash(draft),
            error_code=PIPELINE_STAGE_FAILED,
            error_message=f"Finalization failed: {e}",
            stage="finalize",
        )

    # Compute trace hashes
    hashes = compute_trace_hashes(sir_dict, draft, idl_final)

    # Step 8: compile_bundle (NOT compile_release - no deploy)
    # Sandbox builds skip finance-pilot validation for experimentation
    try:
        idl_json = json.dumps(idl_final)
        compile_result = compile_bundle(
            idl=idl_json,
            bundle_name=bundle_name,
            output_dir=output_dir,
            validate_finance_pilot=False,  # Sandbox builds skip validation
        )
    except Exception as e:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            run_id=run_id,
            **hashes,
            error_code=PIPELINE_BUILD_WRITE_FAILED,
            error_message=f"Bundle compilation failed: {e}",
            stage="compile_bundle",
        )

    if not compile_result.success:
        return PipelineResult(
            status=STATUS_FAILED,
            bundle_name=bundle_name,
            run_id=run_id,
            **hashes,
            error_code=compile_result.error_code or PIPELINE_BUILD_WRITE_FAILED,
            error_message=compile_result.error_message or "Bundle compilation failed",
            stage="compile_bundle",
        )

    # Step 9: Persist trace.json and idl_final.idl
    try:
        run_dir = Path(output_dir)  # output_dir is already root/dev-runs/run_id

        # Write idl_final.idl
        idl_final_path = run_dir / "idl_final.idl"
        idl_final_path.write_text(json.dumps(idl_final, indent=2), encoding="utf-8")

        # Compute bundle artifact hashes
        bundle_path = Path(compile_result.bundle_path)
        manifest_path = bundle_path / "bundle.manifest.json"
        ledger_path = bundle_path / "contract_ledger.json"

        manifest_hash = ""
        if manifest_path.exists():
            manifest_hash = compute_hash(manifest_path.read_bytes())

        ledger_hash = ""
        if ledger_path.exists():
            ledger_hash = compute_hash(ledger_path.read_bytes())

        # Compute policy counts for trace
        runtime_policies_count = len(sir.extraction.runtime_policies)
        dept_runtime_policies_count = sum(
            len(policies) for policies in sir.extraction.dept_runtime_policies.values()
        )
        # gaps here is empty (we succeeded) but we still record the counts
        # For a successful build, gaps will be empty at this point
        policy_counts = compute_policy_counts(
            gaps=[],  # No gaps at this point - build succeeded
            runtime_policies_count=runtime_policies_count,
            dept_runtime_policies_count=dept_runtime_policies_count,
        )

        # Write trace.json
        trace_data = {
            "run_id": run_id,
            "bundle_name": bundle_name,
            "mode": compile_result.mode,
            "sir_sha256": hashes["hash_sir"],
            "draft_sha256": hashes["hash_draft"],
            "final_idl_sha256": hashes["hash_idl_final"],
            "bundle_manifest_sha256": manifest_hash,
            "contract_ledger_sha256": ledger_hash,
            # Policy counts
            "policy_count": policy_counts["policy_count"],
            "policy_gap_count": policy_counts["policy_gap_count"],
            "has_policy_gaps": policy_counts["has_policy_gaps"],
        }
        # Include departments list for multi mode
        if compile_result.mode == "multi" and compile_result.departments:
            trace_data["departments"] = compile_result.departments
        trace_path = run_dir / "trace.json"
        trace_path.write_text(json.dumps(trace_data, indent=2), encoding="utf-8")
    except Exception:
        # Trace write errors are non-fatal
        pass

    # Step 10: Emit DEV_RUN_CREATED to registry
    try:
        registry = get_registry(institution_id=institution_id)
        registry.emit_created(
            run_id=run_id,
            bundle_name=bundle_name,
            bundle_path=compile_result.bundle_path,
        )
    except Exception:
        # Registry errors are non-fatal - log but continue
        pass

    # Step 11: Return BUILT
    return PipelineResult(
        status=STATUS_BUILT,
        bundle_name=bundle_name,
        run_id=run_id,
        bundle_path=compile_result.bundle_path,
        bundle_hash=compile_result.bundle_hash,
        **hashes,
    )
