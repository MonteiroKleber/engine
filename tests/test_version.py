"""Tests para version module - Engine v1.0.0.

Verifica:
- VERSION file existe e contem 1.0.0
- Version module exporta versao correta
- Engine.VERSION esta definido
- Freeze rules estao configuradas
"""

import pytest
from pathlib import Path


class TestVersionFile:
    """Testes do arquivo VERSION."""

    def test_version_file_exists(self):
        """VERSION file deve existir."""
        version_file = Path(__file__).parent.parent / "VERSION"
        assert version_file.exists(), "VERSION file not found"

    def test_version_file_contains_1_0_0(self):
        """VERSION file deve conter 1.0.0."""
        version_file = Path(__file__).parent.parent / "VERSION"
        content = version_file.read_text().strip()
        assert content == "1.0.0", f"Expected 1.0.0, got {content}"


class TestVersionModule:
    """Testes do modulo version."""

    def test_version_string(self):
        """__version__ deve ser 1.0.0."""
        from version import __version__
        assert __version__ == "1.0.0"

    def test_get_version(self):
        """get_version() deve retornar 1.0.0."""
        from version import get_version
        assert get_version() == "1.0.0"

    def test_version_info(self):
        """get_version_info() deve retornar dict completo."""
        from version import get_version_info

        info = get_version_info()

        assert info["version"] == "1.0.0"
        assert info["major"] == 1
        assert info["minor"] == 0
        assert info["patch"] == 0
        assert info["name"] == "Bazari Engine"
        assert "codename" in info
        assert "release_date" in info

    def test_version_string_formatted(self):
        """version_string() deve retornar string formatada."""
        from version import version_string

        s = version_string()

        assert "Bazari Engine" in s
        assert "1.0.0" in s

    def test_semantic_version_parts(self):
        """MAJOR, MINOR, PATCH devem estar corretos."""
        from version import MAJOR, MINOR, PATCH

        assert MAJOR == 1
        assert MINOR == 0
        assert PATCH == 0


class TestFreezeRules:
    """Testes das freeze rules."""

    def test_schemas_frozen(self):
        """Schemas devem estar frozen."""
        from version import is_frozen
        assert is_frozen("schemas") is True

    def test_templates_frozen(self):
        """Templates devem estar frozen."""
        from version import is_frozen
        assert is_frozen("templates") is True

    def test_policies_frozen(self):
        """Policies devem estar frozen."""
        from version import is_frozen
        assert is_frozen("policies") is True

    def test_unknown_not_frozen(self):
        """Componentes desconhecidos nao estao frozen."""
        from version import is_frozen
        assert is_frozen("unknown_component") is False


class TestCompatibility:
    """Testes de compatibilidade de versao."""

    def test_compatible_with_1_0_0(self):
        """Deve ser compativel com 1.0.0."""
        from version import check_compatibility
        assert check_compatibility("1.0.0") is True

    def test_compatible_with_1_0(self):
        """Deve ser compativel com 1.0."""
        from version import check_compatibility
        assert check_compatibility("1.0") is True

    def test_not_compatible_with_2_0_0(self):
        """Nao deve ser compativel com 2.0.0 (major diferente)."""
        from version import check_compatibility
        assert check_compatibility("2.0.0") is False

    def test_not_compatible_with_0_9_0(self):
        """Nao deve ser compativel com 0.9.0 (major diferente)."""
        from version import check_compatibility
        assert check_compatibility("0.9.0") is False

    def test_compatible_with_lower_minor(self):
        """Deve ser compativel com minor menor."""
        from version import check_compatibility
        # 1.0.0 e compativel com requisito 1.0.0
        assert check_compatibility("1.0.0") is True


class TestEngineVersion:
    """Testes da versao no Engine."""

    def test_engine_has_version(self):
        """Engine deve ter atributo VERSION."""
        from orchestrator.engine import Engine
        assert hasattr(Engine, "VERSION")

    def test_engine_version_is_1_0_0(self):
        """Engine.VERSION deve ser 1.0.0."""
        from orchestrator.engine import Engine
        assert Engine.VERSION == "1.0.0"


class TestReleaseNotes:
    """Testes do RELEASE_NOTES.md."""

    def test_release_notes_exists(self):
        """RELEASE_NOTES.md deve existir."""
        release_notes = Path(__file__).parent.parent / "RELEASE_NOTES.md"
        assert release_notes.exists(), "RELEASE_NOTES.md not found"

    def test_release_notes_contains_version(self):
        """RELEASE_NOTES.md deve mencionar v1.0.0."""
        release_notes = Path(__file__).parent.parent / "RELEASE_NOTES.md"
        content = release_notes.read_text()
        assert "1.0.0" in content

    def test_release_notes_has_freeze_rules(self):
        """RELEASE_NOTES.md deve documentar freeze rules."""
        release_notes = Path(__file__).parent.parent / "RELEASE_NOTES.md"
        content = release_notes.read_text()
        assert "Freeze" in content or "freeze" in content


class TestAcceptanceCriteria:
    """Testes dos criterios de aceite."""

    def test_motor_identified_as_v1_0_0(self):
        """Motor deve ser identificado como v1.0.0."""
        from version import __version__
        from orchestrator.engine import Engine

        # Version module
        assert __version__ == "1.0.0"

        # Engine class
        assert Engine.VERSION == "1.0.0"

        # VERSION file
        version_file = Path(__file__).parent.parent / "VERSION"
        assert version_file.read_text().strip() == "1.0.0"
