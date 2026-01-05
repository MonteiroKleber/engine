"""Compilers module - Gera código a partir dos artefatos."""

from .patch_generator_v1 import PatchGenerator, generate_patches
from .backend_compiler import (
    BackendCompiler,
    BackendOutput,
    GeneratedFile as BackendGeneratedFile,
    compile_backend,
)
from .frontend_compiler import (
    FrontendCompiler,
    FrontendOutput,
    GeneratedFile as FrontendGeneratedFile,
    compile_frontend,
)

__all__ = [
    # Patch Generator
    "PatchGenerator",
    "generate_patches",
    # Backend Compiler
    "BackendCompiler",
    "BackendOutput",
    "BackendGeneratedFile",
    "compile_backend",
    # Frontend Compiler
    "FrontendCompiler",
    "FrontendOutput",
    "FrontendGeneratedFile",
    "compile_frontend",
]
