"""Garante que o template docker-compose não define container_name."""

from pathlib import Path


def test_docker_compose_template_has_no_container_name():
    template_path = Path("/home/bazari/templates/docker/docker-compose.yml")
    content = template_path.read_text(encoding="utf-8")
    assert "container_name:" not in content, "container_name deve ser removido do template docker-compose.yml"
