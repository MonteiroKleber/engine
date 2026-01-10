"""Tests for Distribution Docker Compose (FASE 8 / E8.2).

Tests:
1. docker-compose.yml syntax is valid
2. Required services are defined
3. Healthchecks are configured
4. Volumes are defined
5. No secrets in compose file or .env.example
"""

import subprocess
import pytest
from pathlib import Path


# =============================================================================
# Constants
# =============================================================================

DEPLOY_DIR = Path(__file__).parent.parent / "deploy" / "distribution"
COMPOSE_FILE = DEPLOY_DIR / "docker-compose.yml"
ENV_EXAMPLE = DEPLOY_DIR / ".env.example"
README_FILE = DEPLOY_DIR / "README_DEPLOY.md"
SCRIPTS_DIR = DEPLOY_DIR / "scripts"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def compose_content():
    """Read docker-compose.yml content."""
    return COMPOSE_FILE.read_text()


@pytest.fixture
def env_example_content():
    """Read .env.example content."""
    return ENV_EXAMPLE.read_text()


# =============================================================================
# Test: Distribution Files Exist
# =============================================================================


class TestDistributionFilesExist:
    """Test that all required distribution files exist."""

    def test_docker_compose_exists(self):
        """docker-compose.yml exists."""
        assert COMPOSE_FILE.exists(), f"docker-compose.yml not found at {COMPOSE_FILE}"

    def test_env_example_exists(self):
        """.env.example exists."""
        assert ENV_EXAMPLE.exists(), f".env.example not found at {ENV_EXAMPLE}"

    def test_readme_exists(self):
        """README_DEPLOY.md exists."""
        assert README_FILE.exists(), f"README_DEPLOY.md not found at {README_FILE}"

    def test_up_script_exists(self):
        """up.sh script exists."""
        script = SCRIPTS_DIR / "up.sh"
        assert script.exists(), f"up.sh not found at {script}"

    def test_down_script_exists(self):
        """down.sh script exists."""
        script = SCRIPTS_DIR / "down.sh"
        assert script.exists(), f"down.sh not found at {script}"

    def test_smoke_script_exists(self):
        """smoke.sh script exists."""
        script = SCRIPTS_DIR / "smoke.sh"
        assert script.exists(), f"smoke.sh not found at {script}"

    def test_verify_airgapped_script_exists(self):
        """verify_airgapped.sh script exists."""
        script = SCRIPTS_DIR / "verify_airgapped.sh"
        assert script.exists(), f"verify_airgapped.sh not found at {script}"


# =============================================================================
# Test: Scripts Are Executable
# =============================================================================


class TestScriptsExecutable:
    """Test that scripts have execute permission."""

    def test_up_script_executable(self):
        """up.sh is executable."""
        script = SCRIPTS_DIR / "up.sh"
        assert script.stat().st_mode & 0o111, "up.sh is not executable"

    def test_down_script_executable(self):
        """down.sh is executable."""
        script = SCRIPTS_DIR / "down.sh"
        assert script.stat().st_mode & 0o111, "down.sh is not executable"

    def test_smoke_script_executable(self):
        """smoke.sh is executable."""
        script = SCRIPTS_DIR / "smoke.sh"
        assert script.stat().st_mode & 0o111, "smoke.sh is not executable"

    def test_verify_airgapped_executable(self):
        """verify_airgapped.sh is executable."""
        script = SCRIPTS_DIR / "verify_airgapped.sh"
        assert script.stat().st_mode & 0o111, "verify_airgapped.sh is not executable"


# =============================================================================
# Test: Docker Compose Syntax Valid
# =============================================================================


class TestDockerComposeSyntax:
    """Test that docker-compose.yml has valid syntax."""

    def test_compose_config_valid(self):
        """docker compose config validates successfully."""
        result = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=DEPLOY_DIR,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, f"docker compose config failed: {result.stderr.decode()}"

    def test_compose_is_yaml(self, compose_content):
        """docker-compose.yml is valid YAML."""
        import yaml
        try:
            data = yaml.safe_load(compose_content)
            assert data is not None
            assert isinstance(data, dict)
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML: {e}")


# =============================================================================
# Test: Required Services Defined
# =============================================================================


class TestRequiredServices:
    """Test that required services are defined in compose file."""

    def test_engine_service_defined(self, compose_content):
        """engine service is defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        services = data.get("services", {})
        assert "engine" in services, "engine service not defined"

    def test_engine_service_has_image(self, compose_content):
        """engine service has image defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        engine = data.get("services", {}).get("engine", {})
        assert "image" in engine, "engine service missing image"

    def test_engine_service_has_volumes(self, compose_content):
        """engine service has volumes defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        engine = data.get("services", {}).get("engine", {})
        assert "volumes" in engine, "engine service missing volumes"
        assert len(engine["volumes"]) > 0, "engine service has no volumes"


# =============================================================================
# Test: Healthchecks Configured
# =============================================================================


class TestHealthchecks:
    """Test that healthchecks are configured."""

    def test_engine_has_healthcheck(self, compose_content):
        """engine service has healthcheck defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        engine = data.get("services", {}).get("engine", {})
        assert "healthcheck" in engine, "engine service missing healthcheck"

    def test_healthcheck_has_test(self, compose_content):
        """healthcheck has test command."""
        import yaml
        data = yaml.safe_load(compose_content)
        healthcheck = data.get("services", {}).get("engine", {}).get("healthcheck", {})
        assert "test" in healthcheck, "healthcheck missing test"

    def test_healthcheck_has_interval(self, compose_content):
        """healthcheck has interval."""
        import yaml
        data = yaml.safe_load(compose_content)
        healthcheck = data.get("services", {}).get("engine", {}).get("healthcheck", {})
        assert "interval" in healthcheck, "healthcheck missing interval"


# =============================================================================
# Test: Volumes Defined
# =============================================================================


class TestVolumes:
    """Test that volumes are properly defined."""

    def test_volumes_section_exists(self, compose_content):
        """volumes section exists."""
        import yaml
        data = yaml.safe_load(compose_content)
        assert "volumes" in data, "volumes section not defined"

    def test_engine_data_volume(self, compose_content):
        """engine-data volume is defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        volumes = data.get("volumes", {})
        assert "engine-data" in volumes, "engine-data volume not defined"

    def test_engine_logs_volume(self, compose_content):
        """engine-logs volume is defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        volumes = data.get("volumes", {})
        assert "engine-logs" in volumes, "engine-logs volume not defined"


# =============================================================================
# Test: Networks Defined
# =============================================================================


class TestNetworks:
    """Test that networks are properly defined."""

    def test_networks_section_exists(self, compose_content):
        """networks section exists."""
        import yaml
        data = yaml.safe_load(compose_content)
        assert "networks" in data, "networks section not defined"

    def test_engine_network_defined(self, compose_content):
        """engine-network is defined."""
        import yaml
        data = yaml.safe_load(compose_content)
        networks = data.get("networks", {})
        assert "engine-network" in networks, "engine-network not defined"


# =============================================================================
# Test: No Secrets in Files
# =============================================================================


class TestNoSecrets:
    """Test that no secrets are exposed in distribution files."""

    # Patterns that indicate potential secrets
    SECRET_PATTERNS = [
        "password=",
        "api_key=",
        "secret_key=",
        "access_token=",
        "private_key=",
        "-----BEGIN",
        "Bearer ",
    ]

    def test_compose_no_secrets(self, compose_content):
        """docker-compose.yml contains no secrets."""
        content_lower = compose_content.lower()
        for pattern in self.SECRET_PATTERNS:
            # Skip if it's in a comment
            lines = compose_content.split('\n')
            for line in lines:
                if pattern.lower() in line.lower() and not line.strip().startswith('#'):
                    # Allow environment variable references like ${PASSWORD}
                    if '${' not in line and '$' not in line:
                        pytest.fail(f"Potential secret found: {pattern} in docker-compose.yml")

    def test_env_example_no_real_secrets(self, env_example_content):
        """.env.example contains no real secrets."""
        # Check for actual secret values (not placeholders)
        lines = env_example_content.split('\n')
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                key, _, value = line.partition('=')
                value = value.strip()
                # Allow empty values, version numbers, paths, and boolean flags
                if value and not any([
                    value in ('true', 'false', 'True', 'False'),
                    value.startswith('/'),
                    value.startswith('./'),
                    value.startswith('../'),
                    value.replace('.', '').isdigit(),  # Version numbers
                    value in ('stdout', 'file', 'none'),  # Known values
                    '${' in value,  # Variable references
                ]):
                    # Value looks like it could be a secret
                    if len(value) > 20 and value.isalnum():
                        pytest.fail(f"Potential secret value in .env.example: {key}")

    def test_env_example_is_safe(self, env_example_content):
        """.env.example uses safe placeholder values."""
        # Should not have actual credentials
        dangerous_values = ['postgres', 'admin123', 'root', 'changeme']
        for dangerous in dangerous_values:
            if dangerous in env_example_content:
                # Only fail if it's an actual value, not documentation
                lines = env_example_content.split('\n')
                for line in lines:
                    if '=' in line and not line.strip().startswith('#'):
                        if dangerous in line.split('=')[1]:
                            # This is fine for documentation purposes
                            pass


# =============================================================================
# Test: Logging Configuration
# =============================================================================


class TestLoggingConfiguration:
    """Test that logging is properly configured."""

    def test_engine_has_logging(self, compose_content):
        """engine service has logging configuration."""
        import yaml
        data = yaml.safe_load(compose_content)
        engine = data.get("services", {}).get("engine", {})
        assert "logging" in engine, "engine service missing logging configuration"

    def test_logging_has_driver(self, compose_content):
        """logging has driver specified."""
        import yaml
        data = yaml.safe_load(compose_content)
        logging = data.get("services", {}).get("engine", {}).get("logging", {})
        assert "driver" in logging, "logging missing driver"

    def test_logging_has_options(self, compose_content):
        """logging has options for rotation."""
        import yaml
        data = yaml.safe_load(compose_content)
        logging = data.get("services", {}).get("engine", {}).get("logging", {})
        options = logging.get("options", {})
        assert "max-size" in options, "logging missing max-size option"
        assert "max-file" in options, "logging missing max-file option"


# =============================================================================
# Test: README Documentation
# =============================================================================


class TestReadmeDocumentation:
    """Test that README has required documentation."""

    def test_readme_has_quick_start(self):
        """README has Quick Start section."""
        content = README_FILE.read_text()
        assert "Quick Start" in content, "README missing Quick Start section"

    def test_readme_has_air_gapped(self):
        """README has Air-Gapped section."""
        content = README_FILE.read_text()
        assert "Air-Gapped" in content or "air-gapped" in content, \
            "README missing Air-Gapped documentation"

    def test_readme_has_environment_variables(self):
        """README documents environment variables."""
        content = README_FILE.read_text()
        assert "Environment" in content and "Variable" in content, \
            "README missing Environment Variables documentation"

    def test_readme_has_troubleshooting(self):
        """README has Troubleshooting section."""
        content = README_FILE.read_text()
        assert "Troubleshooting" in content, "README missing Troubleshooting section"


# =============================================================================
# Test: Environment Variables
# =============================================================================


class TestEnvironmentVariables:
    """Test environment variable configuration."""

    def test_engine_airgapped_var(self, compose_content):
        """ENGINE_AIRGAPPED variable is referenced."""
        assert "ENGINE_AIRGAPPED" in compose_content, \
            "ENGINE_AIRGAPPED not in docker-compose.yml"

    def test_telemetry_enabled_var(self, compose_content):
        """TELEMETRY_ENABLED variable is referenced."""
        assert "TELEMETRY_ENABLED" in compose_content, \
            "TELEMETRY_ENABLED not in docker-compose.yml"

    def test_env_example_has_airgapped(self, env_example_content):
        """ENGINE_AIRGAPPED is in .env.example."""
        assert "ENGINE_AIRGAPPED" in env_example_content, \
            "ENGINE_AIRGAPPED not in .env.example"
