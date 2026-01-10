"""Garante que o timeout de readiness permaneça estendido (>= 240s)."""

def test_readiness_timeout_is_extended():
    from release.docker_compose_validator import DockerComposeValidator

    assert DockerComposeValidator.READINESS_TIMEOUT >= 240, "READINESS_TIMEOUT deve ser >= 240 segundos"
