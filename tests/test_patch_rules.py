"""Testes das regras de segurança do Patch Engine.

Regras fixadas:
1. O motor nunca se auto-modifica (/home/bazari/engine/**)
2. Templates nunca são alterados (/home/bazari/templates/**)
3. Tudo que é gerado vai para /home/bazari/generated/
"""

import pytest

from patch_engine.patch_engine import PatchEngine, PatchSecurityError


class TestRuleEngineNeverSelfModifies:
    """Regra 1: O motor nunca se auto-modifica."""

    def test_cannot_write_to_engine_root(self):
        """Não pode escrever em /home/bazari/engine/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/engine/malicious.py")

    def test_cannot_write_to_engine_agents(self):
        """Não pode escrever em /home/bazari/engine/agents/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/engine/agents/backdoor.py")

    def test_cannot_write_to_engine_validators(self):
        """Não pode escrever em /home/bazari/engine/validators/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/engine/validators/bypass.py")

    def test_cannot_write_to_engine_orchestrator(self):
        """Não pode escrever em /home/bazari/engine/orchestrator/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/engine/orchestrator/hack.py")

    def test_cannot_write_to_engine_tests(self):
        """Não pode escrever em /home/bazari/engine/tests/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/engine/tests/fake_test.py")

    def test_blocked_paths_include_engine(self):
        """BLOCKED_PATHS deve incluir engine root (portavelmente derivado)."""
        from patch_engine.patch_engine import _ENGINE_ROOT

        # Verifica usando o valor derivado diretamente (sem heurística por substring)
        assert str(_ENGINE_ROOT) in PatchEngine.BLOCKED_PATHS

        # O path deve existir e conter patch_engine/
        assert _ENGINE_ROOT.exists(), f"Engine root should exist: {_ENGINE_ROOT}"
        assert (_ENGINE_ROOT / "patch_engine").exists(), "Engine root should contain patch_engine/"


class TestRuleTemplatesNeverAltered:
    """Regra 2: Templates nunca são alterados."""

    def test_cannot_write_to_templates_root(self):
        """Não pode escrever em /home/bazari/templates/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/templates/malicious.txt")

    def test_cannot_write_to_spring_boot_template(self):
        """Não pode escrever no template spring-boot."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/templates/spring-boot/pom.xml")

    def test_cannot_write_to_react_template(self):
        """Não pode escrever no template react-vite."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/templates/react-vite/package.json")

    def test_cannot_write_to_postgres_template(self):
        """Não pode escrever no template postgres-flyway."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/templates/postgres-flyway/flyway.conf")

    def test_cannot_write_to_docker_template(self):
        """Não pode escrever no template docker."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/bazari/templates/docker/docker-compose.yml")

    def test_blocked_paths_include_templates(self):
        """BLOCKED_PATHS deve incluir templates root SOMENTE se existir."""
        from patch_engine.patch_engine import _TEMPLATES_ROOT

        # Templates só é incluído se o diretório existir
        if _TEMPLATES_ROOT.exists():
            assert str(_TEMPLATES_ROOT) in PatchEngine.BLOCKED_PATHS
        else:
            # Se não existe, não deve estar na lista
            assert str(_TEMPLATES_ROOT) not in PatchEngine.BLOCKED_PATHS


class TestRuleAllGeneratedGoesToGenerated:
    """Regra 3: Tudo que é gerado vai para /home/bazari/generated/."""

    def test_generated_root_is_correct(self):
        """GENERATED_ROOT deve ser /home/bazari/generated."""
        # PatchEngine usa generated_root como parâmetro
        engine = PatchEngine("test", "/home/bazari/generated")
        assert str(engine.generated_root) == "/home/bazari/generated"

    def test_project_root_inside_generated(self):
        """project_root deve estar dentro de generated."""
        engine = PatchEngine("myproject", "/home/bazari/generated")
        assert str(engine.project_root) == "/home/bazari/generated/myproject"

    def test_valid_path_stays_in_project(self):
        """Paths válidos devem ficar dentro do projeto."""
        engine = PatchEngine("demo", "/home/bazari/generated")

        # Simular que o projeto existe
        import tempfile
        import shutil
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        temp_generated = Path(temp_dir) / "generated"
        temp_project = temp_generated / "demo"
        temp_project.mkdir(parents=True)

        try:
            engine_temp = PatchEngine("demo", str(temp_generated))
            valid_path = engine_temp._validate_path("backend/Main.java")

            assert str(valid_path).startswith(str(temp_project))
        finally:
            shutil.rmtree(temp_dir)


class TestPathTraversalPrevention:
    """Testes de prevenção de path traversal."""

    def test_simple_path_traversal(self):
        """Path traversal simples deve ser bloqueado."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("../secret.txt")

    def test_nested_path_traversal(self):
        """Path traversal aninhado deve ser bloqueado."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("src/../../etc/passwd")

    def test_deep_path_traversal(self):
        """Path traversal profundo deve ser bloqueado."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("a/b/c/../../../../../../../etc/shadow")

    def test_encoded_path_traversal_not_decoded(self):
        """Path com .. literal deve ser bloqueado (não decodifica URL)."""
        engine = PatchEngine("test")

        # O detector olha para ".." literal na string
        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("..%2F..%2Fetc/passwd")  # Contém ".."

    def test_mixed_separators_blocked(self):
        """Path traversal com separadores mistos deve ser bloqueado."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("src\\..\\..\\etc\\passwd")


class TestRewriteRatioProtection:
    """Testes de proteção contra reescrita excessiva."""

    def test_small_change_allowed(self):
        """Mudança pequena (<80%) deve ser permitida."""
        engine = PatchEngine("test")

        old = "line1\nline2\nline3\nline4\nline5\n"
        new = "line1\nline2\nline3 modified\nline4\nline5\n"

        # Não deve lançar exceção
        engine._check_rewrite_ratio(old, new, "test.txt")

    def test_full_rewrite_blocked(self):
        """Reescrita total (100%) deve ser bloqueada."""
        engine = PatchEngine("test")

        # Strings completamente diferentes para garantir >80% mudança
        old = "a" * 100
        new = "z" * 100  # 100% diferente

        with pytest.raises(PatchSecurityError, match="Rewrite ratio"):
            engine._check_rewrite_ratio(old, new, "test.txt")

    def test_81_percent_change_blocked(self):
        """Mudança de 81% deve ser bloqueada."""
        engine = PatchEngine("test")

        old = "a" * 100
        new = "a" * 19 + "b" * 81  # 81% diferente

        with pytest.raises(PatchSecurityError, match="Rewrite ratio"):
            engine._check_rewrite_ratio(old, new, "test.txt")

    def test_new_file_no_limit(self):
        """Arquivo novo (old vazio) não tem limite."""
        engine = PatchEngine("test")

        # Não deve lançar exceção
        engine._check_rewrite_ratio("", "completely new content", "new.txt")

    def test_custom_max_ratio(self):
        """max_rewrite_ratio customizado deve funcionar."""
        engine = PatchEngine("test", max_rewrite_ratio=0.50)

        old = "a" * 100
        new = "a" * 49 + "b" * 51  # 51% diferente

        with pytest.raises(PatchSecurityError, match="Rewrite ratio"):
            engine._check_rewrite_ratio(old, new, "test.txt")


class TestAbsolutePathsOutsideProject:
    """Testes de paths absolutos fora do projeto."""

    def test_absolute_path_to_etc(self):
        """Não pode acessar /etc/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/etc/passwd")

    def test_absolute_path_to_root(self):
        """Não pode acessar /."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/malicious.sh")

    def test_absolute_path_to_home(self):
        """Não pode acessar /home/ diretamente."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/home/other_user/secret.txt")

    def test_absolute_path_to_tmp(self):
        """Não pode acessar /tmp/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/tmp/exploit.sh")

    def test_absolute_path_to_var(self):
        """Não pode acessar /var/."""
        engine = PatchEngine("test")

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/var/log/syslog")
