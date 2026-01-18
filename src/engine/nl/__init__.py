"""Natural Language to IDL Pipeline.

This module provides the NL compilation pipeline that transforms
natural language policy descriptions into structured IDL.

Pipeline stages:
1. SIR (Structured Intermediate Representation) - Extract entities from text
2. Draft - Generate initial IDL from SIR
3. Gaps - Detect missing information
4. Answers Apply - Fill gaps with user answers
5. Finalize - Produce final validated IDL
"""

__all__ = [
    "compile_sir",
    "generate_draft",
    "detect_gaps",
    "apply_answers",
    "finalize",
]
