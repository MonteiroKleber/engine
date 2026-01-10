"""Verifica que os logs de readiness estão instrumentados com os prefixos esperados."""

from pathlib import Path


def test_readiness_instrumentation_prefixes_present():
    target = Path("release/docker_compose_validator.py")
    content = target.read_text(encoding="utf-8")

    prefixes = [
        "[READINESS][LOOP]",
        "[READINESS][DOCKER_PS]",
        "[READINESS][DOCKER_PS_RAW]",
        "[READINESS][GATE]",
        "[READINESS][HTTP_CHECK]",
        "[READINESS][DECISION]",
    ]

    for prefix in prefixes:
        assert prefix in content, f"Prefixo de log ausente: {prefix}"
