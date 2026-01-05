"""Fix Loop module - Auto-correção de erros de build."""

from .error_classifier import BuildErrorClassifier, BuildErrorType, ClassifiedError
from .fix_loop_agent import FixLoopAgent, FixLoopResult, FixAttemptStatus, run_fix_loop
from .fix_patch_generator import FixPatchGenerator, FocalPatch, PatchContext

__all__ = [
    "BuildErrorClassifier",
    "BuildErrorType",
    "ClassifiedError",
    "FixLoopAgent",
    "FixLoopResult",
    "FixAttemptStatus",
    "run_fix_loop",
    "FixPatchGenerator",
    "FocalPatch",
    "PatchContext",
]
