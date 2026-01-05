"""Tests para ReleaseChecklist - Gates finais de release.

Testa a verificacao de:
1. Artefatos presentes (SRS/IR/OAS/RBAC/PLAN)
2. Hashes completos no run log
3. Build ok
4. Smoke ok
5. Blueprint registrado
6. Regras absolutas respeitadas

REGRA: Qualquer item faltando → FAIL.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

from release.release_checklist import (
    ReleaseChecklist,
    ReleaseChecklistResult,
    ChecklistItem,
    run_release_checklist,
)


# ==================== FIXTURES ====================


@pytest.fixture
def tmp_store(tmp_path):
    """Store temporario."""
    store_dir = tmp_path / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir


@pytest.fixture
def tmp_generated(tmp_path):
    """Diretorio generated temporario."""
    gen_dir = tmp_path / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    return gen_dir


@pytest.fixture
def checklist(tmp_store, tmp_generated):
    """ReleaseChecklist com paths temporarios."""
    return ReleaseChecklist(
        store_root=str(tmp_store),
        generated_root=str(tmp_generated),
    )


@pytest.fixture
def complete_project(tmp_store, tmp_generated):
    """Projeto completo com todos os artefatos."""
    project_name = "complete_project"

    # Criar estrutura do store
    project_store = tmp_store / project_name
    project_store.mkdir()

    # Criar artefatos obrigatorios
    for artifact in ["SRS", "IR", "OAS", "RBAC", "PLAN"]:
        artifact_dir = project_store / artifact
        artifact_dir.mkdir()
        ext = "yaml" if artifact == "OAS" else "json"
        (artifact_dir / f"v1.{ext}").write_text('{"test": true}')

    # Criar run log com todos os hashes
    runs_dir = project_store / "runs"
    runs_dir.mkdir()
    run_log = {
        "status": "completed",
        "input_hash": "abc123",
        "srs_hash": "def456",
        "ir_hash": "ghi789",
        "oas_hash": "jkl012",
        "rbac_hash": "mno345",
        "plan_hash": "pqr678",
        "result": {
            "success": True,
            "build_ok": True,
            "smoke_ok": True,
            "release_mode": True,
            "smoke_passed": 5,
            "smoke_failed": 0,
            "blueprint_type": "generic",
            "blueprint_forced_generic": True,
            "repo_path": str(tmp_generated / project_name),
        },
    }
    (runs_dir / "run_001.json").write_text(json.dumps(run_log))

    # Criar repositorio gerado
    repo = tmp_generated / project_name
    repo.mkdir()

    # Backend com seguranca
    backend = repo / "backend"
    backend.mkdir()
    src = backend / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)

    (src / "SecurityConfig.java").write_text("""
        @EnableWebSecurity
        public class SecurityConfig {
            @Bean
            public SecurityFilterChain filterChain(HttpSecurity http) {
                return http
                    .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().authenticated()
                    )
                    .build();
            }
        }
    """)

    (src / "UserController.java").write_text("""
        @RestController
        @RequestMapping("/api/users")
        public class UserController {
            private static final Logger logger = LoggerFactory.getLogger(UserController.class);

            @GetMapping
            public List<User> getUsers() {
                logger.info("Listing users");
                return userService.findAll();
            }
        }
    """)

    # Frontend limpo
    frontend = repo / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "test"}')
    frontend_src = frontend / "src"
    frontend_src.mkdir()
    (frontend_src / "App.tsx").write_text("""
        export default function App() {
            console.log("App started");
            return <div>Hello</div>;
        }
    """)

    return project_name


@pytest.fixture
def incomplete_project(tmp_store, tmp_generated):
    """Projeto incompleto (faltando artefatos)."""
    project_name = "incomplete_project"

    project_store = tmp_store / project_name
    project_store.mkdir()

    # Apenas SRS e IR
    for artifact in ["SRS", "IR"]:
        artifact_dir = project_store / artifact
        artifact_dir.mkdir()
        (artifact_dir / "v1.json").write_text('{"test": true}')

    return project_name


@pytest.fixture
def project_with_violations(tmp_store, tmp_generated):
    """Projeto com violacoes de regras absolutas."""
    project_name = "violations_project"

    # Criar estrutura do store
    project_store = tmp_store / project_name
    project_store.mkdir()

    # Criar todos os artefatos
    for artifact in ["SRS", "IR", "OAS", "RBAC", "PLAN"]:
        artifact_dir = project_store / artifact
        artifact_dir.mkdir()
        ext = "yaml" if artifact == "OAS" else "json"
        (artifact_dir / f"v1.{ext}").write_text('{"test": true}')

    # Criar run log
    runs_dir = project_store / "runs"
    runs_dir.mkdir()
    run_log = {
        "status": "completed",
        "input_hash": "abc123",
        "srs_hash": "def456",
        "ir_hash": "ghi789",
        "oas_hash": "jkl012",
        "rbac_hash": "mno345",
        "plan_hash": "pqr678",
        "result": {
            "success": True,
            "build_ok": True,
            "smoke_ok": True,
            "release_mode": True,
            "blueprint_type": "generic",
            "blueprint_forced_generic": True,
        },
    }
    (runs_dir / "run_001.json").write_text(json.dumps(run_log))

    # Criar repositorio com violacoes
    repo = tmp_generated / project_name
    repo.mkdir()

    backend = repo / "backend"
    backend.mkdir()
    src = backend / "src" / "main" / "java"
    src.mkdir(parents=True)

    # Violacao: logging de senha
    (src / "BadController.java").write_text("""
        public class BadController {
            public void login(String username, String password) {
                logger.info("User login with password: " + password);
            }
        }
    """)

    # Violacao: secret hardcoded
    (src / "Config.java").write_text("""
        public class Config {
            private String apiKey = "sk-1234567890abcdef";
        }
    """)

    return project_name


# ==================== TESTS: BASIC ====================


class TestReleaseChecklistBasic:
    """Testes basicos do ReleaseChecklist."""

    def test_checklist_returns_result(self, checklist, tmp_store):
        """run() deve retornar ReleaseChecklistResult."""
        project = tmp_store / "test"
        project.mkdir()

        result = checklist.run("test")

        assert isinstance(result, ReleaseChecklistResult)
        assert result.project == "test"
        assert result.timestamp is not None

    def test_result_has_items(self, checklist, tmp_store):
        """Resultado deve ter lista de items."""
        project = tmp_store / "test"
        project.mkdir()

        result = checklist.run("test")

        assert hasattr(result, "items")
        assert isinstance(result.items, list)

    def test_result_to_dict(self, checklist, tmp_store):
        """to_dict() deve retornar dicionario completo."""
        project = tmp_store / "test"
        project.mkdir()

        result = checklist.run("test")
        d = result.to_dict()

        assert "project" in d
        assert "passed" in d
        assert "items" in d
        assert "blocking_failures" in d

    def test_result_summary(self, checklist, tmp_store):
        """summary() deve retornar string formatada."""
        project = tmp_store / "test"
        project.mkdir()

        result = checklist.run("test")
        summary = result.summary()

        assert "Release Checklist" in summary
        assert "test" in summary


# ==================== TESTS: ARTIFACTS ====================


class TestArtifactChecks:
    """Testes de verificacao de artefatos."""

    def test_all_artifacts_present_passes(self, checklist, complete_project):
        """Deve passar quando todos os artefatos estao presentes."""
        result = checklist.run(complete_project)

        artifact_items = [i for i in result.items if i.category == "artifacts"]
        assert len(artifact_items) == 5  # SRS, IR, OAS, RBAC, PLAN

        for item in artifact_items:
            assert item.status == "PASS", f"{item.name} should pass"

    def test_missing_artifacts_fails(self, checklist, incomplete_project):
        """Deve falhar quando artefatos estao faltando."""
        result = checklist.run(incomplete_project)

        artifact_items = [i for i in result.items if i.category == "artifacts"]

        # SRS e IR devem passar
        srs = next(i for i in artifact_items if "srs" in i.name)
        ir = next(i for i in artifact_items if "_ir" in i.name)
        assert srs.status == "PASS"
        assert ir.status == "PASS"

        # OAS, RBAC, PLAN devem falhar
        oas = next(i for i in artifact_items if "oas" in i.name)
        rbac = next(i for i in artifact_items if "rbac" in i.name)
        plan = next(i for i in artifact_items if "plan" in i.name)
        assert oas.status == "FAIL"
        assert rbac.status == "FAIL"
        assert plan.status == "FAIL"

    def test_missing_artifacts_blocks_release(self, checklist, incomplete_project):
        """Artefatos faltando devem bloquear o release."""
        result = checklist.run(incomplete_project)

        assert result.passed is False
        assert len(result.blocking_failures) >= 3  # OAS, RBAC, PLAN


# ==================== TESTS: HASHES ====================


class TestHashChecks:
    """Testes de verificacao de hashes."""

    def test_all_hashes_present_passes(self, checklist, complete_project):
        """Deve passar quando todos os hashes estao presentes."""
        result = checklist.run(complete_project)

        hash_item = next(i for i in result.items if i.category == "hashes")
        assert hash_item.status == "PASS"
        assert "Todos os hashes" in hash_item.message

    def test_missing_hashes_fails(self, checklist, tmp_store):
        """Deve falhar quando hashes estao faltando."""
        project_name = "missing_hashes"
        project_store = tmp_store / project_name
        project_store.mkdir()

        # Run log sem alguns hashes
        runs_dir = project_store / "runs"
        runs_dir.mkdir()
        run_log = {
            "status": "completed",
            "input_hash": "abc123",
            "srs_hash": "def456",
            # Faltando: ir_hash, oas_hash, rbac_hash, plan_hash
        }
        (runs_dir / "run_001.json").write_text(json.dumps(run_log))

        result = checklist.run(project_name)

        hash_item = next(i for i in result.items if i.category == "hashes")
        assert hash_item.status == "FAIL"
        assert "faltando" in hash_item.message.lower()

    def test_no_run_log_fails_hashes(self, checklist, tmp_store):
        """Deve falhar se run log nao existe."""
        project = tmp_store / "no_run_log"
        project.mkdir()

        result = checklist.run("no_run_log")

        hash_item = next(i for i in result.items if i.category == "hashes")
        assert hash_item.status == "FAIL"


# ==================== TESTS: BUILD ====================


class TestBuildChecks:
    """Testes de verificacao de build."""

    def test_build_ok_passes(self, checklist, complete_project):
        """Deve passar quando build_ok e True."""
        result = checklist.run(complete_project)

        build_item = next(i for i in result.items if i.category == "build")
        assert build_item.status == "PASS"

    def test_build_failed_fails(self, checklist, tmp_store):
        """Deve falhar quando build_ok e False."""
        project_name = "build_failed"
        project_store = tmp_store / project_name
        project_store.mkdir()

        runs_dir = project_store / "runs"
        runs_dir.mkdir()
        run_log = {
            "result": {
                "build_ok": False,
                "build_errors": ["Compilation failed"],
            }
        }
        (runs_dir / "run_001.json").write_text(json.dumps(run_log))

        result = checklist.run(project_name)

        build_item = next(i for i in result.items if i.category == "build")
        assert build_item.status == "FAIL"
        assert build_item.required is True


# ==================== TESTS: SMOKE ====================


class TestSmokeChecks:
    """Testes de verificacao de smoke tests."""

    def test_smoke_ok_passes(self, checklist, complete_project):
        """Deve passar quando smoke_ok e True."""
        result = checklist.run(complete_project)

        smoke_item = next(i for i in result.items if i.category == "smoke")
        assert smoke_item.status == "PASS"

    def test_smoke_failed_fails(self, checklist, tmp_store):
        """Deve falhar quando smoke_ok e False."""
        project_name = "smoke_failed"
        project_store = tmp_store / project_name
        project_store.mkdir()

        runs_dir = project_store / "runs"
        runs_dir.mkdir()
        run_log = {
            "result": {
                "release_mode": True,
                "smoke_ok": False,
                "smoke_passed": 3,
                "smoke_failed": 2,
            }
        }
        (runs_dir / "run_001.json").write_text(json.dumps(run_log))

        result = checklist.run(project_name)

        smoke_item = next(i for i in result.items if i.category == "smoke")
        assert smoke_item.status == "FAIL"

    def test_smoke_not_release_mode_skips(self, checklist, tmp_store):
        """Deve pular se nao e release mode."""
        project_name = "not_release"
        project_store = tmp_store / project_name
        project_store.mkdir()

        runs_dir = project_store / "runs"
        runs_dir.mkdir()
        run_log = {
            "result": {
                "release_mode": False,
                "build_ok": True,
            }
        }
        (runs_dir / "run_001.json").write_text(json.dumps(run_log))

        result = checklist.run(project_name)

        smoke_item = next(i for i in result.items if i.category == "smoke")
        assert smoke_item.status == "SKIP"


# ==================== TESTS: BLUEPRINT ====================


class TestBlueprintChecks:
    """Testes de verificacao de blueprint."""

    def test_blueprint_registered_passes(self, checklist, complete_project):
        """Deve passar quando blueprint esta registrado."""
        result = checklist.run(complete_project)

        blueprint_item = next(i for i in result.items if i.category == "blueprint")
        assert blueprint_item.status == "PASS"

    def test_forced_generic_passes(self, checklist, tmp_store):
        """FORCED_GENERIC deve passar."""
        project_name = "forced_generic"
        project_store = tmp_store / project_name
        project_store.mkdir()

        runs_dir = project_store / "runs"
        runs_dir.mkdir()
        run_log = {
            "result": {
                "blueprint_type": "custom_unknown",
                "blueprint_forced_generic": True,
            }
        }
        (runs_dir / "run_001.json").write_text(json.dumps(run_log))

        result = checklist.run(project_name)

        blueprint_item = next(i for i in result.items if i.category == "blueprint")
        assert blueprint_item.status == "PASS"

    def test_no_blueprint_fails(self, checklist, tmp_store):
        """Deve falhar se blueprint nao especificado."""
        project_name = "no_blueprint"
        project_store = tmp_store / project_name
        project_store.mkdir()

        runs_dir = project_store / "runs"
        runs_dir.mkdir()
        run_log = {"result": {}}
        (runs_dir / "run_001.json").write_text(json.dumps(run_log))

        result = checklist.run(project_name)

        blueprint_item = next(i for i in result.items if i.category == "blueprint")
        assert blueprint_item.status == "FAIL"


# ==================== TESTS: ABSOLUTE RULES ====================


class TestAbsoluteRules:
    """Testes de verificacao de regras absolutas."""

    def test_clean_code_passes(self, checklist, complete_project):
        """Deve passar quando codigo esta limpo."""
        result = checklist.run(complete_project)

        rules_items = [i for i in result.items if i.category == "rules"]

        for item in rules_items:
            assert item.status in ["PASS", "SKIP"], f"{item.name}: {item.message}"

    def test_pii_logging_fails(self, checklist, project_with_violations):
        """Deve falhar quando ha logging de PII."""
        result = checklist.run(project_with_violations)

        pii_item = next((i for i in result.items if i.name == "no_pii_logging"), None)
        assert pii_item is not None
        assert pii_item.status == "FAIL"

    def test_hardcoded_secrets_fails(self, checklist, project_with_violations):
        """Deve falhar quando ha secrets hardcoded."""
        result = checklist.run(project_with_violations)

        secrets_item = next((i for i in result.items if i.name == "no_hardcoded_secrets"), None)
        assert secrets_item is not None
        assert secrets_item.status == "FAIL"

    def test_no_security_config_fails(self, checklist, tmp_store, tmp_generated):
        """Deve falhar quando nao ha configuracao de seguranca."""
        project_name = "no_security"
        project_store = tmp_store / project_name
        project_store.mkdir()

        # Criar repositorio sem SecurityConfig
        repo = tmp_generated / project_name
        repo.mkdir()
        backend = repo / "backend"
        backend.mkdir()
        src = backend / "src"
        src.mkdir()
        (src / "Controller.java").write_text("public class Controller {}")

        result = checklist.run(project_name)

        auth_item = next((i for i in result.items if i.name == "authenticated_endpoints"), None)
        assert auth_item is not None
        assert auth_item.status == "FAIL"

    def test_no_repo_skips_rules(self, checklist, tmp_store):
        """Deve pular regras se repositorio nao existe."""
        project = tmp_store / "no_repo"
        project.mkdir()

        result = checklist.run("no_repo")

        rules_items = [i for i in result.items if i.category == "rules"]
        # Deve ter pelo menos 1 item SKIP
        assert any(i.status == "SKIP" for i in rules_items)


# ==================== TESTS: OVERALL RESULT ====================


class TestOverallResult:
    """Testes do resultado geral."""

    def test_complete_project_passes(self, checklist, complete_project):
        """Projeto completo deve passar."""
        result = checklist.run(complete_project)

        assert result.passed is True
        assert len(result.blocking_failures) == 0

    def test_incomplete_project_fails(self, checklist, incomplete_project):
        """Projeto incompleto deve falhar."""
        result = checklist.run(incomplete_project)

        assert result.passed is False
        assert len(result.blocking_failures) > 0

    def test_violations_fail(self, checklist, project_with_violations):
        """Projeto com violacoes deve falhar."""
        result = checklist.run(project_with_violations)

        assert result.passed is False

    def test_counters_are_correct(self, checklist, complete_project):
        """Contadores devem estar corretos."""
        result = checklist.run(complete_project)

        assert result.total_items == len(result.items)
        assert result.passed_items + result.failed_items + result.skipped_items == result.total_items


# ==================== TESTS: CONVENIENCE FUNCTION ====================


class TestConvenienceFunction:
    """Testes da funcao de conveniencia."""

    def test_run_release_checklist_returns_dict(self, tmp_store):
        """run_release_checklist deve retornar dict."""
        project = tmp_store / "test"
        project.mkdir()

        # Monkey-patch para usar tmp_store
        import release.release_checklist as module
        original_default = module.ReleaseChecklist.DEFAULT_STORE_ROOT
        module.ReleaseChecklist.DEFAULT_STORE_ROOT = str(tmp_store)

        try:
            result = run_release_checklist("test")
            assert isinstance(result, dict)
            assert "project" in result
            assert "passed" in result
        finally:
            module.ReleaseChecklist.DEFAULT_STORE_ROOT = original_default


# ==================== TESTS: CHECKLIST ITEM ====================


class TestChecklistItem:
    """Testes do ChecklistItem."""

    def test_item_to_dict(self):
        """to_dict() deve incluir todos os campos."""
        item = ChecklistItem(
            name="test_item",
            category="test",
            status="PASS",
            message="Test passed",
            required=True,
            details={"key": "value"},
        )

        d = item.to_dict()

        assert d["name"] == "test_item"
        assert d["category"] == "test"
        assert d["status"] == "PASS"
        assert d["message"] == "Test passed"
        assert d["required"] is True
        assert d["details"] == {"key": "value"}

    def test_item_defaults(self):
        """Item deve ter valores padrao corretos."""
        item = ChecklistItem(
            name="test",
            category="test",
            status="PASS",
            message="OK",
        )

        assert item.required is True
        assert item.details == {}


# ==================== TESTS: ACCEPTANCE ====================


class TestAcceptanceCriteria:
    """Testes dos criterios de aceite."""

    def test_any_missing_item_fails(self, checklist, incomplete_project):
        """Qualquer item faltando deve resultar em FAIL."""
        result = checklist.run(incomplete_project)

        # Projeto incompleto (faltando artefatos)
        assert result.passed is False

    def test_all_required_categories_checked(self, checklist, complete_project):
        """Deve verificar todas as categorias obrigatorias."""
        result = checklist.run(complete_project)

        categories = {item.category for item in result.items}

        assert "artifacts" in categories
        assert "hashes" in categories
        assert "build" in categories
        assert "smoke" in categories
        assert "blueprint" in categories
        assert "rules" in categories

    def test_blocking_failures_listed(self, checklist, incomplete_project):
        """Falhas bloqueantes devem ser listadas."""
        result = checklist.run(incomplete_project)

        assert len(result.blocking_failures) > 0
        # Cada falha deve ter nome e mensagem
        for failure in result.blocking_failures:
            assert ":" in failure  # formato "nome: mensagem"
