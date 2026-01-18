"""Pipeline - End-to-end Natural Language to Deploy orchestration.

This module provides the full pipeline from natural language text
to deployed bundle in a single operation.

Pipeline stages:
1. compile_sir - Extract SIR from natural language
2. compile_draft - Generate draft IDL from SIR
3. detect_gaps - Find missing information
4. apply_answers - Fill gaps with user answers (if provided)
5. finalize - Produce final validated IDL
6. compile_release - Compile bundle and deploy
"""

__all__ = [
    "run_pipeline",
    "PipelineResult",
    "compute_hash",
]
